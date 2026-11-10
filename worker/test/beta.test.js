import { test } from "node:test";
import assert from "node:assert/strict";
import worker from "../src/index.js";
import { ascToken } from "../src/beta.js";

// A stand-in for D1 that understands only the statements beta.js issues.
function d1() {
  const rows = [];
  const stmt = (sql) => ({
    bind: (...a) => ({
      first: async () => rows.find((r) => r.email.toLowerCase() === a[0].toLowerCase()) ?? null,
      run: async () => {
        if (sql.startsWith("INSERT")) rows.push({ id: rows.length + 1, email: a[0], created: a[1], device: a[2], role: a[3], status: a[4], source: a[5], error: null });
        else if (sql.includes("status='invited'")) Object.assign(rows.find((r) => r.email === a[0]), { status: "invited", error: null });
        else if (sql.includes("status='failed'")) Object.assign(rows.find((r) => r.email === a[1]), { status: "failed", error: a[0] });
      },
    }),
    all: async () => ({ results: sql.includes("WHERE status") ? rows.filter((r) => r.status === "queued" || r.status === "failed") : rows }),
  });
  return { rows, prepare: stmt };
}
function kv() {
  const m = new Map();
  return { m, get: async (k) => m.get(k) ?? null, put: async (k, v) => void m.set(k, v), delete: async (k) => void m.delete(k), list: async () => ({ keys: [] }) };
}
const ORIGIN = { Origin: "https://aheadcane.github.io", "Content-Type": "application/json", "CF-Connecting-IP": "203.0.113.7" };
const form = (over = {}) => new Request("https://ahead-ask.test/beta", { method: "POST", headers: ORIGIN, body: JSON.stringify({ email: "a@example.com", device: "iphone-15-pro", role: "cane", consent: true, ...over }) });
const owner = (path, method = "GET") => new Request(`https://ahead-ask.test${path}`, { method, headers: { ...ORIGIN, Authorization: "Bearer tok" } });

async function p8() {
  const pair = await crypto.subtle.generateKey({ name: "ECDSA", namedCurve: "P-256" }, true, ["sign", "verify"]);
  const der = new Uint8Array(await crypto.subtle.exportKey("pkcs8", pair.privateKey));
  return { pair, pem: `-----BEGIN PRIVATE KEY-----\n${btoa(String.fromCharCode(...der))}\n-----END PRIVATE KEY-----` };
}

test("without the App Store Connect key a request is kept as queued, a repeat does not add a row, and the list is owner-only", async () => {
  const env = { OWNER_TOKEN: "tok", DEVICES: kv(), BETA: d1() };
  let res = await worker.fetch(form(), env);
  assert.deepEqual(await res.json(), { status: "queued" });
  res = await worker.fetch(form({ email: "A@Example.com" }), env);
  assert.deepEqual(await res.json(), { status: "queued" });
  assert.equal(env.BETA.rows.length, 1);
  assert.equal(env.BETA.rows[0].role, "cane");
  assert.equal((await worker.fetch(new Request("https://ahead-ask.test/beta/list", { headers: ORIGIN }), env)).status, 401);
  const list = await (await worker.fetch(owner("/beta/list"), env)).json();
  assert.equal(list.asc, false);
  assert.equal(list.rows.length, 1);
});

test("a bad email, model, role or missing consent is refused with a sentence the page can read", async () => {
  const env = { OWNER_TOKEN: "tok", DEVICES: kv(), BETA: d1() };
  for (const [over, error] of [[{ email: "nope" }, "email"], [{ device: "iphone-9" }, "device"], [{ role: "x" }, "role"], [{ consent: false }, "consent"]]) {
    const res = await worker.fetch(form(over), env);
    assert.equal(res.status, 400);
    const j = await res.json();
    assert.equal(j.error, error);
    assert.ok(j.message.endsWith("."));
  }
  assert.equal(env.BETA.rows.length, 0);
});

test("a phone without LiDAR is recorded and told so, with no invitation asked for", async () => {
  const env = { OWNER_TOKEN: "tok", DEVICES: kv(), BETA: d1(), ASC_KEY_ID: "K", ASC_ISSUER_ID: "I", ASC_PRIVATE_KEY: "unused" };
  const res = await worker.fetch(form({ device: "no-lidar" }), env);
  assert.deepEqual(await res.json(), { status: "no-lidar" });
});

test("the sixth request in an hour from one address is 429, and only a hash of the address is stored", async () => {
  const env = { OWNER_TOKEN: "tok", DEVICES: kv(), BETA: d1() };
  for (let i = 0; i < 5; i++) assert.equal((await worker.fetch(form({ email: `p${i}@example.com` }), env)).status, 200);
  assert.equal((await worker.fetch(form({ email: "p6@example.com" }), env)).status, 429);
  assert.ok([...env.DEVICES.m.keys()].every((k) => !k.includes("203.0.113.7")));
});

test("with the key set a request is added to the external group, a known tester is added by id, and a failure keeps the row", async () => {
  const { pair, pem } = await p8();
  const env = { OWNER_TOKEN: "tok", DEVICES: kv(), BETA: d1(), ASC_KEY_ID: "KID", ASC_ISSUER_ID: "ISS", ASC_PRIVATE_KEY: pem, ASC_APP_ID: "123", ASC_GROUP_NAME: "Team" };
  const calls = [];
  let testerStatus = 201;
  const real = globalThis.fetch;
  globalThis.fetch = async (url, init = {}) => {
    calls.push([init.method || "GET", String(url), init.body && JSON.parse(init.body), init.headers?.Authorization]);
    const reply = (status, data) => new Response(status === 204 ? null : JSON.stringify(data), { status });
    if (String(url).includes("/apps/123/betaGroups")) return reply(200, { data: [{ id: "int", attributes: { name: "Team", isInternalGroup: true } }, { id: "grp", attributes: { name: "Team", isInternalGroup: false } }] });
    if (String(url).endsWith("/v1/betaTesters")) return reply(testerStatus, testerStatus === 201 ? {} : { errors: [{ detail: "already exists" }] });
    if (String(url).includes("filter[email]")) return reply(200, { data: [{ id: "tst" }] });
    if (String(url).includes("/relationships/betaTesters")) return reply(204, {});
    throw new Error(`unexpected ${url}`);
  };
  try {
    let res = await worker.fetch(form(), env);
    assert.deepEqual(await res.json(), { status: "invited" });
    const create = calls.find((c) => c[1].endsWith("/v1/betaTesters"));
    assert.equal(create[2].data.attributes.email, "a@example.com");
    assert.deepEqual(create[2].data.relationships.betaGroups.data, [{ type: "betaGroups", id: "grp" }], "the external group, not the internal one");
    // The bearer token is a valid ES256 JWT for Apple's audience.
    const [h, b, s] = create[3].replace("Bearer ", "").split(".");
    const dec = (x) => JSON.parse(atob(x.replace(/-/g, "+").replace(/_/g, "/")));
    assert.deepEqual([dec(h).alg, dec(h).kid, dec(b).iss, dec(b).aud], ["ES256", "KID", "ISS", "appstoreconnect-v1"]);
    assert.ok(dec(b).exp - dec(b).iat <= 1200);
    const sig = Uint8Array.from(atob(s.replace(/-/g, "+").replace(/_/g, "/")), (c) => c.charCodeAt(0));
    assert.ok(await crypto.subtle.verify({ name: "ECDSA", hash: "SHA-256" }, pair.publicKey, sig, new TextEncoder().encode(`${h}.${b}`)));

    testerStatus = 409;
    res = await worker.fetch(form({ email: "known@example.com" }), env);
    assert.deepEqual(await res.json(), { status: "invited" });
    assert.ok(calls.some((c) => c[1].endsWith("/betaGroups/grp/relationships/betaTesters")));

    testerStatus = 422;
    res = await worker.fetch(form({ email: "bad@example.com" }), env);
    assert.deepEqual(await res.json(), { status: "queued" });
    const row = env.BETA.rows.find((r) => r.email === "bad@example.com");
    assert.equal(row.status, "failed");
    assert.match(row.error, /asc 422/);

    testerStatus = 201;
    const flushed = await (await worker.fetch(owner("/beta/flush", "POST"), env)).json();
    assert.deepEqual(flushed, { asc: true, waiting: 1, invited: 1 });
    assert.equal(row.status, "invited");
  } finally {
    globalThis.fetch = real;
  }
});

test("ascToken reads a key written with literal \\n and signs", async () => {
  const { pem } = await p8();
  const token = await ascToken({ ASC_KEY_ID: "K", ASC_ISSUER_ID: "I", ASC_PRIVATE_KEY: pem.replace(/\n/g, "\\n") });
  assert.equal(token.split(".").length, 3);
});
