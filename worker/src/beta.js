// The beta request form's half of the Worker: POST /beta stores a request in D1 and asks App Store Connect to add the
// email to the external TestFlight group, so Apple sends the invitation and App Store Connect's tester list stays the
// source of truth. Without the ASC key the row stays "queued"; the owner's POST /beta/flush sends the queued ones once
// the three ASC secrets exist.

export const DEVICES = {
  "iphone-12-pro": true, "iphone-12-pro-max": true,
  "iphone-13-pro": true, "iphone-13-pro-max": true,
  "iphone-14-pro": true, "iphone-14-pro-max": true,
  "iphone-15-pro": true, "iphone-15-pro-max": true,
  "iphone-16-pro": true, "iphone-16-pro-max": true,
  "iphone-17-pro": true, "iphone-17-pro-max": true,
  "no-lidar": false,
};
export const ROLES = ["cane", "helper"];
const EMAIL = /^[^\s@<>()"',;:\\]+@[^\s@<>()"',;:\\]+\.[^\s@<>()"',;:\\]{2,}$/;
const HOUR_LIMIT = 5;

const enc = new TextEncoder();
const b64u = (bytes) => btoa(String.fromCharCode(...new Uint8Array(bytes))).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
const sha = async (t) => [...new Uint8Array(await crypto.subtle.digest("SHA-256", enc.encode(t)))].map((b) => b.toString(16).padStart(2, "0")).join("");

export const ascConfigured = (env) => Boolean(env.ASC_KEY_ID && env.ASC_ISSUER_ID && env.ASC_PRIVATE_KEY);

// ES256 JWT for the App Store Connect API: aud appstoreconnect-v1, valid at most 20 minutes (Apple's token rules).
export async function ascToken(env, now = Date.now()) {
  const pem = String(env.ASC_PRIVATE_KEY).replace(/\\n/g, "\n").replace(/-----[A-Z ]+-----|\s+/g, "");
  const key = await crypto.subtle.importKey("pkcs8", Uint8Array.from(atob(pem), (c) => c.charCodeAt(0)), { name: "ECDSA", namedCurve: "P-256" }, false, ["sign"]);
  const iat = Math.floor(now / 1000);
  const head = b64u(enc.encode(JSON.stringify({ alg: "ES256", kid: env.ASC_KEY_ID, typ: "JWT" })));
  const body = b64u(enc.encode(JSON.stringify({ iss: env.ASC_ISSUER_ID, iat, exp: iat + 600, aud: "appstoreconnect-v1" })));
  const sig = await crypto.subtle.sign({ name: "ECDSA", hash: "SHA-256" }, key, enc.encode(`${head}.${body}`));
  return `${head}.${body}.${b64u(sig)}`;
}

async function asc(env, token, path, init = {}) {
  const res = await fetch(`https://api.appstoreconnect.apple.com${path}`, {
    ...init,
    headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
  });
  const text = await res.text();
  let data = null;
  try { data = JSON.parse(text); } catch {}
  return { status: res.status, data, text };
}

const ascError = (r) => `asc ${r.status} ${(r.data?.errors?.[0]?.detail || r.text).slice(0, 200)}`;

// Adds `email` to the external group. A tester Apple already knows (409) is added to the group by id instead.
export async function invite(env, email) {
  const token = await ascToken(env);
  const groups = await asc(env, token, `/v1/apps/${env.ASC_APP_ID}/betaGroups?limit=200`);
  if (groups.status !== 200) throw new Error(ascError(groups));
  const group = (groups.data.data || []).find((g) => g.attributes?.name === env.ASC_GROUP_NAME && !g.attributes?.isInternalGroup);
  if (!group) throw new Error(`asc no external group named ${env.ASC_GROUP_NAME}`);
  const made = await asc(env, token, "/v1/betaTesters", {
    method: "POST",
    body: JSON.stringify({
      data: {
        type: "betaTesters",
        attributes: { email },
        relationships: { betaGroups: { data: [{ type: "betaGroups", id: group.id }] } },
      },
    }),
  });
  if (made.status === 201 || made.status === 200) return;
  if (made.status !== 409) throw new Error(ascError(made));
  const found = await asc(env, token, `/v1/betaTesters?filter[email]=${encodeURIComponent(email)}`);
  const tester = found.status === 200 && found.data.data?.[0];
  if (!tester) throw new Error(ascError(made));
  const added = await asc(env, token, `/v1/betaGroups/${group.id}/relationships/betaTesters`, {
    method: "POST",
    body: JSON.stringify({ data: [{ type: "betaTesters", id: tester.id }] }),
  });
  if (added.status >= 300 && added.status !== 409) throw new Error(ascError(added));
}

// Sends one row's invitation and records the outcome. Never throws.
async function send(env, row) {
  if (!ascConfigured(env)) return "queued";
  try {
    await invite(env, row.email);
    await env.BETA.prepare("UPDATE beta SET status='invited', error=NULL WHERE email=?").bind(row.email).run();
    return "invited";
  } catch (e) {
    console.error("beta invite failed:", e && e.message);
    await env.BETA.prepare("UPDATE beta SET status='failed', error=? WHERE email=?").bind(String(e?.message).slice(0, 300), row.email).run();
    return "queued";
  }
}

async function turnstileOk(env, token, ip) {
  if (!env.TURNSTILE_SECRET) return true;
  if (typeof token !== "string" || !token) return false;
  const form = new URLSearchParams({ secret: env.TURNSTILE_SECRET, response: token });
  if (ip) form.set("remoteip", ip);
  try {
    const res = await fetch("https://challenges.cloudflare.com/turnstile/v0/siteverify", { method: "POST", body: form });
    return Boolean((await res.json()).success);
  } catch {
    return false;
  }
}

// Five requests an hour per address. Only a hash of the address is kept, and only for two hours.
async function limited(env, ip) {
  const key = `rl:beta:${(await sha(ip || "unknown")).slice(0, 16)}:${Math.floor(Date.now() / 3_600_000)}`;
  const n = Number(await env.DEVICES.get(key)) || 0;
  if (n >= HOUR_LIMIT) return true;
  await env.DEVICES.put(key, String(n + 1), { expirationTtl: 7200 });
  return false;
}

const SOURCES = /^[a-z0-9-]{1,24}$/;

export async function betaRequest(request, env, headers, json) {
  let body;
  try {
    body = await request.json();
  } catch {
    return json({ error: "bad request" }, 400, headers);
  }
  const email = String(body?.email || "").trim();
  if (email.length > 254 || !EMAIL.test(email)) return json({ error: "email", message: "That does not look like an email address." }, 400, headers);
  if (!(body?.device in DEVICES)) return json({ error: "device", message: "Choose your iPhone model." }, 400, headers);
  if (!ROLES.includes(body?.role)) return json({ error: "role", message: "Say whether you use a white cane or help someone who does." }, 400, headers);
  if (body.consent !== true) return json({ error: "consent", message: "The consent box needs to be ticked." }, 400, headers);
  const ip = request.headers.get("CF-Connecting-IP");
  if (await limited(env, ip)) return json({ error: "rate", message: "Too many requests from this network. Try again in an hour." }, 429, headers);
  if (!(await turnstileOk(env, body.token, ip))) return json({ error: "turnstile", message: "The check that you are a person did not pass. Reload the page and try again." }, 403, headers);

  const source = SOURCES.test(String(body.source || "")) ? body.source : "form";
  const had = await env.BETA.prepare("SELECT email, status FROM beta WHERE email=?").bind(email).first();
  if (had) {
    // The same person asking twice gets the same answer, and a request that is still waiting is tried again.
    const status = had.status === "queued" || had.status === "failed" ? await send(env, had) : had.status;
    return json({ status: status === "no-lidar" ? "no-lidar" : status }, 200, headers);
  }
  const status = DEVICES[body.device] ? "queued" : "no-lidar";
  await env.BETA.prepare("INSERT INTO beta (email, created, device, role, status, source) VALUES (?, ?, ?, ?, ?, ?)")
    .bind(email, Date.now(), body.device, body.role, status, source).run();
  return json({ status: status === "queued" ? await send(env, { email }) : status }, 200, headers);
}

// The owner's view: GET /beta/list, and POST /beta/flush to send every row still waiting.
export async function betaOwner(request, env, path, headers, json) {
  if (path === "/beta/list" && request.method === "GET") {
    const { results } = await env.BETA.prepare("SELECT id, email, created, device, role, status, source, error FROM beta ORDER BY id").all();
    return json({ asc: ascConfigured(env), rows: results }, 200, headers);
  }
  if (path === "/beta/flush" && request.method === "POST") {
    const { results } = await env.BETA.prepare("SELECT email FROM beta WHERE status IN ('queued','failed')").all();
    if (!ascConfigured(env)) return json({ asc: false, waiting: results.length }, 200, headers);
    let invited = 0;
    for (const row of results) if ((await send(env, row)) === "invited") invited++;
    return json({ asc: true, waiting: results.length, invited }, 200, headers);
  }
  return json({ error: "not found" }, 404, headers);
}
