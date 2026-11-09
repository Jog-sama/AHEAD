import { test } from "node:test";
import assert from "node:assert/strict";
import worker, { Mirror, CROSSING } from "../src/index.js";

// A stand-in for the KV namespace: get with a type, put with a TTL, delete, list by prefix.
function kv() {
  const m = new Map();
  return {
    m,
    async get(k, type) {
      const v = m.get(k);
      return v === undefined ? null : type === "json" ? JSON.parse(v) : v;
    },
    async put(k, v) {
      m.set(k, v);
    },
    async delete(k) {
      m.delete(k);
    },
    async list({ prefix }) {
      return { keys: [...m.keys()].filter((k) => k.startsWith(prefix)).map((name) => ({ name })) };
    },
  };
}

const PIXEL = "/9j/4AAQSkZJRgABAQAAAQABAAD/2wBDAP//////////////////////////////////////////////////////////////////////////////////////wgALCAABAAEBAREA/8QAFBABAAAAAAAAAAAAAAAAAAAAAP/aAAgBAQABPxA=";
const ORIGIN = { Origin: "https://jonasneves.com", "Content-Type": "application/json" };
const b64url = (buf) => btoa(String.fromCharCode(...new Uint8Array(buf))).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
const sha256 = async (text) => [...new Uint8Array(await crypto.subtle.digest("SHA-256", new TextEncoder().encode(text)))].map((b) => b.toString(16).padStart(2, "0")).join("");

// A phone: a keypair, an id, and signed requests.
async function phone() {
  const pair = await crypto.subtle.generateKey({ name: "ECDSA", namedCurve: "P-256" }, true, ["sign", "verify"]);
  const key = await crypto.subtle.exportKey("jwk", pair.publicKey);
  const id = crypto.randomUUID();
  const sign = async (message) => b64url(await crypto.subtle.sign({ name: "ECDSA", hash: "SHA-256" }, pair.privateKey, new TextEncoder().encode(message)));
  const ask = async (body, time = Date.now()) => {
    const raw = JSON.stringify(body);
    return new Request("https://ahead-ask.test/", {
      method: "POST",
      headers: { ...ORIGIN, "X-Device": id, "X-Time": String(time), "X-Signature": await sign(`${time}.${await sha256(raw)}`) },
      body: raw,
    });
  };
  return { id, key, sign, ask, enroll: () => new Request("https://ahead-ask.test/enroll", { method: "POST", headers: ORIGIN, body: JSON.stringify({ id, name: "Jonas's iPhone\u001b[31m", key: { ...key, d: "never-stored" } }) }) };
}
const owner = (path, method) => new Request(`https://ahead-ask.test${path}`, { method, headers: { ...ORIGIN, Authorization: "Bearer tok" } });

test("a phone enrolls and is approved at once, its signed asks pass, a stranger's do not, a block turns it off", async () => {
  const env = { OWNER_TOKEN: "tok", ANTHROPIC_API_KEY: "key", DEVICES: kv() };
  const p = await phone();

  let res = await worker.fetch(await p.ask({ image: PIXEL, question: "Can I cross?" }), env);
  assert.equal(res.status, 401);
  assert.deepEqual(await res.json(), { error: "unauthorized" });

  res = await worker.fetch(p.enroll(), env);
  const enrolled = await res.json();
  assert.equal(enrolled.status, "approved");
  assert.match(enrolled.fp, /^[0-9a-f]{8}$/);
  assert.equal(JSON.parse(env.DEVICES.m.get(`device:${p.id}`)).key.d, undefined, "the private half is never stored");
  res = await worker.fetch(new Request(`https://ahead-ask.test/enroll/${p.id}`, { headers: ORIGIN }), env);
  assert.deepEqual(await res.json(), { status: "approved" });

  res = await worker.fetch(owner("/devices", "GET"), env);
  const list = await res.json();
  assert.equal(list.approved.length, 1);
  assert.equal(list.approved[0].name, "Jonas's iPhone[31m", "the escape character is stripped, the rest of the name stays");
  assert.equal(list.approved[0].fp, enrolled.fp);

  res = await worker.fetch(await p.ask({ image: PIXEL, question: "Can I cross?" }), env);
  assert.equal(res.status, 200);
  assert.deepEqual(await res.json(), CROSSING);
  assert.equal(env.DEVICES.m.get(`use:${p.id}:${new Date().toISOString().slice(0, 10)}`), "1");
  assert.equal(env.DEVICES.m.get(`use:all:${new Date().toISOString().slice(0, 10)}`), "1");

  const other = await phone();
  const rebind = new Request("https://ahead-ask.test/enroll", { method: "POST", headers: ORIGIN, body: JSON.stringify({ id: p.id, name: "x", key: other.key }) });
  assert.equal((await worker.fetch(rebind, env)).status, 409, "an approved id never takes a second key");
  assert.equal((await worker.fetch(p.enroll(), env)).status, 200, "the same key re-enrolling is fine");

  const stale = await worker.fetch(await p.ask({ image: PIXEL, question: "Can I cross?" }, Date.now() - 120_000), env);
  assert.equal(stale.status, 401);
  const stranger = await phone();
  const forged = await stranger.ask({ image: PIXEL, question: "Can I cross?" });
  forged.headers.set("X-Device", p.id);
  assert.equal((await worker.fetch(forged, env)).status, 401);

  res = await worker.fetch(owner(`/devices/${p.id}`, "DELETE"), env);
  assert.deepEqual(await res.json(), { status: "blocked" });
  assert.equal((await worker.fetch(await p.ask({ image: PIXEL, question: "Can I cross?" }), env)).status, 401);
  res = await worker.fetch(p.enroll(), env);
  assert.equal(res.status, 403, "a blocked id cannot enroll again");
  assert.deepEqual(await res.json(), { status: "blocked" });
  assert.deepEqual((await (await worker.fetch(owner("/devices", "GET"), env)).json()).blocked, [p.id]);
  await worker.fetch(owner(`/devices/${p.id}`, "POST"), env);
  assert.equal((await worker.fetch(p.enroll(), env)).status, 200, "unblocking lets it enroll again");
});

test("the owner routes need the owner token; a phone over its daily quota, or all phones over the global cap, are told so", async () => {
  const env = { OWNER_TOKEN: "tok", ANTHROPIC_API_KEY: "key", DEVICES: kv(), DEVICE_DAY_CAP: "2", GLOBAL_DAY_CAP: "3" };
  assert.equal((await worker.fetch(new Request("https://ahead-ask.test/devices", { headers: ORIGIN }), env)).status, 401);
  const [p, q] = [await phone(), await phone()];
  await worker.fetch(p.enroll(), env);
  await worker.fetch(q.enroll(), env);
  const ask = async (who) => worker.fetch(await who.ask({ image: PIXEL, question: "Can I cross?" }), env);
  assert.equal((await ask(p)).status, 200);
  assert.equal((await ask(p)).status, 200);
  let res = await ask(p);
  assert.equal(res.status, 429);
  assert.equal((await res.json()).reason, "daily limit");
  assert.equal((await ask(q)).status, 200, "another phone still has its own quota");
  res = await ask(q);
  assert.equal(res.status, 429);
  assert.equal((await res.json()).reason, "global limit");
});

test("enrolling is limited per address and per day", async () => {
  const hdr = { ...ORIGIN, "CF-Connecting-IP": "198.51.100.9" };
  const env = { OWNER_TOKEN: "tok", DEVICES: kv() };
  const codes = [];
  for (let i = 0; i < 11; i++) {
    const p = await phone();
    const req = p.enroll();
    codes.push((await worker.fetch(new Request(req, { headers: hdr }), env)).status);
  }
  assert.deepEqual(codes, [...Array(10).fill(200), 429]);
  const small = { OWNER_TOKEN: "tok", DEVICES: kv(), ENROLL_DAY_CAP: "1" };
  assert.equal((await worker.fetch((await phone()).enroll(), small)).status, 200);
  assert.equal((await worker.fetch((await phone()).enroll(), small)).status, 429);
});

test("the mirror accepts a device's signature over mirror.<time> in place of the owner token", async () => {
  const env = { OWNER_TOKEN: "tok", DEVICES: kv() };
  const p = await phone();
  await worker.fetch(p.enroll(), env);
  const sockets = [];
  const store = new Map();
  const ctx = { storage: { get: async (k) => store.get(k), put: async (k, v) => void store.set(k, v) }, acceptWebSocket: (ws, tags) => sockets.push(Object.assign(ws, { tags })), getWebSockets: (tag) => sockets.filter((w) => w.open && w.tags.includes(tag)), getTags: (ws) => ws.tags };
  const m = new Mirror(ctx, env);
  const ws = { open: true, sent: [], att: { auth: false, since: Date.now(), code: "ABCDEFGH" }, send(t) { this.sent.push(JSON.parse(t)); }, close(c) { this.open = false; this.closed = c; }, serializeAttachment(a) { this.att = a; }, deserializeAttachment() { return this.att; } };
  ctx.acceptWebSocket(ws, ["send"]);
  const viewer = { open: true, sent: [], att: null, send(t) { this.sent.push(JSON.parse(t)); }, close() { this.open = false; }, serializeAttachment() {}, deserializeAttachment() { return null; } };
  ctx.acceptWebSocket(viewer, ["watch"]);
  const time = Date.now();
  // The snapshot follows the hello before the signature check has finished, as the phone sends it.
  const snap = JSON.stringify({ type: "state", t: { state: "Watching" } });
  const first = m.webSocketMessage(ws, JSON.stringify({ type: "hello", device: { id: p.id, time, sig: await p.sign(`mirror.ABCDEFGH.${time}`) } }));
  const second = m.webSocketMessage(ws, snap);
  await Promise.all([first, second]);
  assert.equal(ws.closed, undefined, "the early snapshot must not be read as a bad hello");
  assert.equal(ws.att.auth, true);
  assert.deepEqual(viewer.sent.at(-1), JSON.parse(snap), "the queued snapshot reaches the viewer after the hello passes");
  assert.equal(m.last, snap);
  const bad = { ...ws, open: true, att: { auth: false, since: Date.now(), code: "ABCDEFGH" }, sent: [] };
  ctx.acceptWebSocket(bad, ["send"]);
  await m.webSocketMessage(bad, JSON.stringify({ type: "hello", device: { id: p.id, time, sig: "AAAA" } }));
  assert.equal(bad.closed, 4001);
  const other = { ...ws, open: true, att: { auth: false, since: Date.now(), code: "ZZZZZZZZ" }, sent: [] };
  ctx.acceptWebSocket(other, ["send"]);
  await m.webSocketMessage(other, JSON.stringify({ type: "hello", device: { id: p.id, time, sig: await p.sign(`mirror.ABCDEFGH.${time}`) } }));
  assert.equal(other.closed, 4001, "a hello for one room opens no other");
  const intruder = await phone();
  await worker.fetch(intruder.enroll(), env);
  const t2 = Date.now();
  const taken = { ...ws, open: true, att: { auth: false, since: Date.now(), code: "ABCDEFGH" }, sent: [] };
  ctx.acceptWebSocket(taken, ["send"]);
  await m.webSocketMessage(taken, JSON.stringify({ type: "hello", device: { id: intruder.id, time: t2, sig: await intruder.sign(`mirror.ABCDEFGH.${t2}`) } }));
  assert.equal(taken.closed, 4001, "an enrolled stranger cannot send into a room another device holds");
});
