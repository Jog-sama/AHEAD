// Cloudflare Worker behind the "ask" button of a blind cane user's phone page.
// The phone sends a photo and a LiDAR corridor; Claude answers in one short
// spoken sentence or two, under guardrails that live both in the prompt and in
// code. The phone speaks distances itself from the LiDAR, so the model's
// numbers are stripped here, and a crossing verdict is never given: the model
// cannot see traffic well enough and a wrong "go" costs a life.

const MODEL = "claude-opus-5-5";
const TIMEOUT_MS = 8000;
const MAX_WORDS = 25;
const ALLOWED_ORIGINS = ["https://jonasneves.com", "null"];

export const NO_ANSWER = { answer: "Not sure.", abstain: true, reason: "no answer" };
export const CROSSING = { answer: "I do not judge crossings.", abstain: true, reason: "crossing" };

const SYSTEM = `You help a blind person who walks with a white cane. The cane finds the ground and anything below the waist; you cover what it misses: obstacles at chest and head height in the path ahead, and what signs say. Answer in plain speakable English, one or two sentences, at most ${MAX_WORDS} words, no markdown, no lists.

Rules:
1. Never say whether it is safe to cross, go, step, or proceed. If asked, set abstain true with reason "crossing" and leave answer empty.
2. Never state a distance or a count of steps; the phone speaks distances from its LiDAR. Say where (slightly left, straight ahead) and what, not how far.
3. Describe only what is in the path at chest and head height (branches, signs, poles, awnings, people, open doors, vehicles' mirrors) and the text of signs. Do not describe the scene, the weather, or things to the side unless asked.
4. When the photo is too dark, blurred, or ambiguous, or the question is about something you cannot see, set abstain true with a short reason in one clause.
5. Answer the question if one was asked; otherwise say what is in the path, or that you see nothing in the path.`;

const SCHEMA = {
  type: "object",
  properties: {
    answer: { type: "string", description: "The spoken answer. Empty when abstaining." },
    abstain: { type: "boolean" },
    reason: { type: "string", description: "One clause when abstaining, otherwise empty." },
  },
  required: ["answer", "abstain", "reason"],
  additionalProperties: false,
};

// Guardrail (a): crossing and go/no-go judgments, in the question or the answer.
const CROSSING_PATTERNS = [
  /\bcross(?:ing|walk|es|ed)?\b/i,
  /\b(?:safe|clear|ok|okay|fine|good|time)\s+to\s+(?:cross|go|step|walk|proceed|continue|move)\b/i,
  /\b(?:can|could|should|may|shall)\s+(?:i|we|you)\s+(?:cross|go|step|walk|proceed|continue|move)\b/i,
  /\bis\s+(?:it|the\s+(?:way|path|road|street|coast))\s+(?:safe|clear|free)\b/i,
  /\b(?:the\s+)?(?:way|path|road|street|coast)\s+is\s+(?:clear|safe|free)\b/i,
  /\b(?:go\s+ahead|you\s+(?:can|may)\s+(?:go|step|walk|proceed)|(?:don'?t|do\s+not)\s+walk\s+sign|walk\s+sign(?:al)?|(?:green|red)\s+(?:light|man)|traffic\s+light)\b/i,
];

export function isCrossing(text) {
  if (typeof text !== "string" || !text) return false;
  return CROSSING_PATTERNS.some((re) => re.test(text));
}

// Guardrail (b): a number followed by a length unit, with its hedge and its tail.
const NUMBER =
  String.raw`(?:\d+(?:[.,]\d+)?|half\s+an?|a\s+couple\s+of|a\s+few|several|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|thirteen|fourteen|fifteen|twenty|thirty|forty|fifty|hundred)`;
const UNIT = String.raw`(?:m|metres?|meters?|ft|feet|foot|steps?|paces?|yards?|yds?)`;
const DISTANCE = new RegExp(
  String.raw`(?:\b(?:about|around|roughly|approximately|approx\.?|nearly|almost|over|under|some|just|only|at|within|at\s+least|at\s+most|less\s+than|more\s+than)\s+)*` +
    String.raw`\b${NUMBER}\s*-?\s*${UNIT}\b` +
    String.raw`(?:\s+(?:away|ahead|out|off|from\s+you|in\s+front(?:\s+of\s+you)?|to\s+your\s+(?:left|right)|on\s+your\s+(?:left|right)))?`,
  "gi",
);

export function stripDistances(text) {
  if (typeof text !== "string") return "";
  let out = text.replace(DISTANCE, " ");
  out = out
    .replace(/\s*\b(?:is|are|at|about|around|roughly|approximately|in|within|of)\s*([.;!?]|$)/gi, "$1")
    .replace(/\s*,\s*([.;!?]|$)/g, "$1")
    .replace(/,(?:\s*,)+/g, ",")
    .replace(/\s+([.,;:!?])/g, "$1")
    .replace(/\s{2,}/g, " ")
    .replace(/^\s*[,;:]\s*/, "")
    .trim();
  return out;
}

export function speakable(text) {
  if (typeof text !== "string") return "";
  let out = text
    .replace(/[*_`#>~]/g, "")
    .replace(/^\s*[-•]\s+/gm, "")
    .replace(/\s+/g, " ")
    .trim();
  if (!/\w/.test(out)) return "";
  const words = out.split(" ");
  if (words.length > MAX_WORDS) {
    const cut = words.slice(0, MAX_WORDS).join(" ");
    const lastStop = Math.max(cut.lastIndexOf(". "), cut.lastIndexOf("? "), cut.lastIndexOf("! "));
    out = lastStop > 0 ? cut.slice(0, lastStop + 1) : cut.replace(/[,;:]?$/, ".");
  }
  if (out && !/[.!?]$/.test(out)) out += ".";
  return out;
}

export function sameToken(given, secret) {
  if (typeof given !== "string" || typeof secret !== "string" || !secret) return false;
  const a = new TextEncoder().encode(given);
  const b = new TextEncoder().encode(secret);
  let diff = a.length ^ b.length;
  for (let i = 0; i < Math.max(a.length, b.length); i++) diff |= (a[i] ?? 0) ^ (b[i] ?? 0);
  return diff === 0;
}

export function checkToken(header, secret) {
  const m = typeof header === "string" && /^Bearer\s+(\S+)\s*$/.exec(header);
  return m ? sameToken(m[1], secret) : false;
}

// Devices: a phone makes a P-256 key on first launch and enrolls its public half with a name; the owner approves the
// device once (POST /devices/<id> with the owner token), and from then on the phone signs each request, so no secret
// is typed into or shipped with the app, and one phone is revoked without touching the others. KV: `pending:<id>` and
// `device:<id>` hold {name, key, since}; `use:<id>:<day>` counts the day's asks.
const DEVICE_ID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/;
const SKEW_MS = 60_000;
const DAY_CAP = 300;
const PENDING_TTL_S = 3600;  // approval happens with the phone in hand; the page re-enrolls while it waits
const PENDING_MAX = 20;

const fromB64url = (s) => Uint8Array.from(atob(String(s).replace(/-/g, "+").replace(/_/g, "/")), (c) => c.charCodeAt(0));
const hex = (buf) => [...new Uint8Array(buf)].map((b) => b.toString(16).padStart(2, "0")).join("");
export const sha256 = async (text) => hex(await crypto.subtle.digest("SHA-256", new TextEncoder().encode(text)));

export function publicJwk(key) {
  if (!key || key.kty !== "EC" || key.crv !== "P-256" || typeof key.x !== "string" || typeof key.y !== "string") return null;
  return { kty: "EC", crv: "P-256", x: key.x, y: key.y };
}

// Eight hex characters of the key, shown on the phone and in the owner's list, so the owner approves the phone in
// hand and not one that enrolled with the same name.
export const fingerprint = async (key) => (await sha256(`${key.x}.${key.y}`)).slice(0, 8);

export async function verifySignature(jwk, message, signature) {
  try {
    const key = await crypto.subtle.importKey("jwk", jwk, { name: "ECDSA", namedCurve: "P-256" }, false, ["verify"]);
    return await crypto.subtle.verify({ name: "ECDSA", hash: "SHA-256" }, key, fromB64url(signature), new TextEncoder().encode(message));
  } catch {
    return false;
  }
}

// The approved device behind a signature over `message`, or null; `time` must be within a minute of now.
export async function signedBy(env, id, time, signature, message) {
  const t = Number(time);
  if (!DEVICE_ID.test(String(id)) || !Number.isFinite(t) || Math.abs(Date.now() - t) > SKEW_MS) return null;
  const d = await env.DEVICES.get(`device:${id}`, "json");
  if (!d || !(await verifySignature(d.key, message, signature))) return null;
  return { id, ...d };
}

const day = () => new Date().toISOString().slice(0, 10);

async function enroll(request, env, headers) {
  let body;
  try {
    body = await request.json();
  } catch {
    return json({ error: "bad request" }, 400, headers);
  }
  const id = String(body?.id || "");
  const key = publicJwk(body?.key);
  const name = String(body?.name || "").replace(/[^\P{C}]/gu, "").trim().slice(0, 40) || "a phone";
  if (!DEVICE_ID.test(id) || !key) return json({ error: "bad request" }, 400, headers);
  const fp = await fingerprint(key);
  // An id already bound to another key is refused, never rebound: a phone whose store lost its key makes a new id.
  const sameKey = (d) => d && d.key.x === key.x && d.key.y === key.y;
  const approved = await env.DEVICES.get(`device:${id}`, "json");
  if (approved) return sameKey(approved) ? json({ status: "approved", fp }, 200, headers) : json({ error: "id taken" }, 409, headers);
  const pending = await env.DEVICES.get(`pending:${id}`, "json");
  if (pending && !sameKey(pending)) return json({ error: "id taken" }, 409, headers);
  if (!pending) {
    if ((await env.DEVICES.list({ prefix: "pending:", limit: PENDING_MAX })).keys.length >= PENDING_MAX) return json({ error: "try later" }, 429, headers);
    await env.DEVICES.put(`pending:${id}`, JSON.stringify({ name, key, fp, since: Date.now() }), { expirationTtl: PENDING_TTL_S });
  }
  return json({ status: "pending", fp }, 200, headers);
}

async function enrollStatus(id, env, headers) {
  if (!DEVICE_ID.test(id)) return json({ status: "unknown" }, 404, headers);
  if (await env.DEVICES.get(`device:${id}`)) return json({ status: "approved" }, 200, headers);
  if (await env.DEVICES.get(`pending:${id}`)) return json({ status: "pending" }, 200, headers);
  return json({ status: "unknown" }, 404, headers);
}

// The owner's view and switch: GET /devices lists both sets, POST /devices/<id> approves, DELETE /devices/<id> revokes.
async function devices(request, env, path, headers) {
  if (!checkToken(request.headers.get("Authorization"), env.OWNER_TOKEN)) return json({ error: "unauthorized" }, 401, headers);
  const id = path.slice("/devices/".length);
  if (path === "/devices" && request.method === "GET") {
    const read = async (prefix) => {
      const { keys } = await env.DEVICES.list({ prefix });
      return Promise.all(
        keys.map(async ({ name }) => {
          const id = name.slice(prefix.length);
          const d = await env.DEVICES.get(name, "json");
          const today = prefix === "device:" ? Number(await env.DEVICES.get(`use:${id}:${day()}`)) || 0 : undefined;
          return { id, name: d?.name, fp: d?.fp, since: d?.since, today };
        }),
      );
    };
    return json({ approved: await read("device:"), pending: await read("pending:") }, 200, headers);
  }
  if (!DEVICE_ID.test(id)) return json({ error: "no such device" }, 404, headers);
  if (request.method === "POST") {
    const p = await env.DEVICES.get(`pending:${id}`, "json");
    if (!p) return (await env.DEVICES.get(`device:${id}`)) ? json({ status: "approved" }, 200, headers) : json({ error: "no such device" }, 404, headers);
    await env.DEVICES.put(`device:${id}`, JSON.stringify({ ...p, since: Date.now() }));
    await env.DEVICES.delete(`pending:${id}`);
    return json({ status: "approved", name: p.name }, 200, headers);
  }
  if (request.method === "DELETE") {
    await env.DEVICES.delete(`device:${id}`);
    await env.DEVICES.delete(`pending:${id}`);
    return json({ status: "revoked" }, 200, headers);
  }
  return json({ error: "GET, POST or DELETE" }, 405, headers);
}

// The corridor goes to the model as bearings and bands, never as numbers,
// so it has nothing to echo.
const BEARINGS = ["far left", "left", "left", "slightly left", "straight ahead", "slightly right", "right", "right", "far right"];

export function describeCorridor(corridor) {
  if (!Array.isArray(corridor) || corridor.length !== 2) return "No LiDAR reading.";
  const bands = ["chest height", "head height"];
  const parts = [];
  corridor.forEach((cells, b) => {
    if (!Array.isArray(cells)) return;
    let best = null;
    cells.forEach((d, i) => {
      if (typeof d === "number" && Number.isFinite(d) && d > 0 && (best === null || d < best.d)) best = { d, i };
    });
    if (!best) return;
    const range = best.d < 1 ? "very near" : best.d < 2.5 ? "near" : "farther off";
    parts.push(`${bands[b]}: something ${range}, ${BEARINGS[Math.min(best.i, 8)]}`);
  });
  return parts.length ? `LiDAR: ${parts.join("; ")}.` : "LiDAR: nothing in the corridor.";
}

// Applies every code-side guardrail to what the model returned.
export function finish(raw, question) {
  if (!raw || typeof raw !== "object") return NO_ANSWER;
  if (isCrossing(question) || isCrossing(raw.answer) || isCrossing(raw.reason)) return CROSSING;
  if (raw.abstain === true) {
    const reason = speakable(stripDistances(String(raw.reason || ""))).replace(/[.!?]$/, "").split(/[,;.]/)[0].trim() || "no answer";
    return { answer: "Not sure.", abstain: true, reason: reason.split(/\s+/).slice(0, 12).join(" ") };
  }
  const answer = speakable(stripDistances(raw.answer));
  if (!answer) return NO_ANSWER;
  return { answer, abstain: false };
}

function corsHeaders(origin) {
  const h = { "Content-Type": "application/json; charset=utf-8", Vary: "Origin" };
  if (origin !== null && ALLOWED_ORIGINS.includes(origin)) {
    h["Access-Control-Allow-Origin"] = origin;
    h["Access-Control-Allow-Methods"] = "GET, POST, DELETE, OPTIONS";
    h["Access-Control-Allow-Headers"] = "Authorization, Content-Type, X-Device, X-Time, X-Signature";
    h["Access-Control-Max-Age"] = "86400";
  }
  return h;
}

function json(body, status, headers) {
  return new Response(JSON.stringify(body), { status, headers });
}

async function ask(env, { image, corridor, question }) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), TIMEOUT_MS);
  try {
    const text = [describeCorridor(corridor), question ? `Question: ${question}` : "No question; say what is in the path."].join("\n");
    const res = await fetch("https://api.anthropic.com/v1/messages", {
      method: "POST",
      signal: controller.signal,
      headers: {
        "content-type": "application/json",
        "x-api-key": env.ANTHROPIC_API_KEY,
        "anthropic-version": "2026-10-21",
        "anthropic-beta": "server-side-fallback-2026-07-01",
      },
      body: JSON.stringify({
        model: MODEL,
        max_tokens: 400,
        fallbacks: "default",
        system: SYSTEM,
        output_config: { effort: "low", format: { type: "json_schema", schema: SCHEMA } },
        messages: [
          {
            role: "user",
            content: [
              { type: "image", source: { type: "base64", media_type: "image/jpeg", data: image } },
              { type: "text", text },
            ],
          },
        ],
      }),
    });
    if (!res.ok) throw new Error(`api ${res.status} ${(await res.text()).slice(0, 300)}`);
    const msg = await res.json();
    if (msg.stop_reason === "refusal" || msg.stop_reason === "max_tokens") throw new Error(msg.stop_reason);
    const block = (msg.content || []).find((c) => c.type === "text");
    return JSON.parse(block.text);
  } finally {
    clearTimeout(timer);
  }
}

// Mirror: the phone shows its screen on a computer during a demo. One Durable Object per room code holds one
// WebSocket from the phone (the sender, which proves itself in its first message: the owner token, or its device's
// signature over `mirror.<code>.<time>`) and any number of
// viewers (the page opened on a computer with the code; the code, 8 characters from a 32-letter alphabet, is the
// only thing a viewer needs). Every message from the phone is a full snapshot of what its screen shows, so the
// latest one is replayed to a viewer that joins late; the photo never passes through here.
export const ROOM = /^[A-HJ-NP-Z2-9]{8}$/;
const HELLO_MS = 5000;

export class Mirror {
  constructor(ctx, env) {
    this.ctx = ctx;
    this.env = env;
    this.last = null;
  }

  fetch(request) {
    const role = new URL(request.url).searchParams.get("role") === "send" ? "send" : "watch";
    const pair = new WebSocketPair();
    const [client, server] = [pair[0], pair[1]];
    this.ctx.acceptWebSocket(server, [role]);
    if (role === "send") {
      server.serializeAttachment({ auth: false, since: Date.now(), code: new URL(request.url).pathname.slice("/mirror/".length) });
    } else {
      server.send(JSON.stringify({ type: "phone", on: this.senders().length > 0 }));
      if (this.last) server.send(this.last);
      this.tellSenders();
    }
    return new Response(null, { status: 101, webSocket: client });
  }

  senders() {
    return this.ctx.getWebSockets("send").filter((ws) => ws.deserializeAttachment()?.auth);
  }

  broadcast(tag, text) {
    for (const ws of this.ctx.getWebSockets(tag)) {
      try {
        ws.send(text);
      } catch {}
    }
  }

  tellSenders(except) {
    const n = this.ctx.getWebSockets("watch").filter((w) => w !== except).length;
    for (const ws of this.senders()) {
      try {
        ws.send(JSON.stringify({ type: "watchers", n }));
      } catch {}
    }
  }

  async webSocketMessage(ws, message) {
    if (typeof message !== "string" || !this.ctx.getTags(ws).includes("send")) return;
    const state = ws.deserializeAttachment() || {};
    if (!state.auth) {
      // The phone's first snapshot follows its hello at once, and a device hello is verified against KV, an await
      // other events run through; what arrives meanwhile waits in a queue instead of being read as a failed hello.
      this.queued ??= new Map();
      if (this.queued.has(ws)) {
        this.queued.get(ws).push(message);
        return;
      }
      let hello = null;
      try {
        hello = JSON.parse(message);
      } catch {}
      let ok = hello?.type === "hello" && Date.now() - (state.since || 0) <= HELLO_MS;
      if (ok && hello.device) {
        const d = hello.device;
        this.queued.set(ws, []);
        ok = Boolean(await signedBy(this.env, d.id, d.time, d.sig, `mirror.${state.code}.${d.time}`));
      } else if (ok) ok = sameToken(hello.token, this.env.OWNER_TOKEN);
      const later = this.queued.get(ws) || [];
      this.queued.delete(ws);
      if (!ok) {
        ws.close(4001, "unauthorized");
        return;
      }
      ws.serializeAttachment({ auth: true });
      ws.send(JSON.stringify({ type: "watchers", n: this.ctx.getWebSockets("watch").length }));
      this.broadcast("watch", JSON.stringify({ type: "phone", on: true }));
      for (const m of later) this.relay(m);
      return;
    }
    this.relay(message);
  }

  relay(message) {
    if (message.length > 65536) return;
    if (message.startsWith('{"type":"state"')) this.last = message;
    this.broadcast("watch", message);
  }

  webSocketClose(ws) {
    this.gone(ws);
  }

  webSocketError(ws) {
    this.gone(ws);
  }

  gone(ws) {
    this.queued?.delete(ws);
    const tags = this.ctx.getTags(ws);
    try {
      ws.close(1000);
    } catch {}
    if (tags.includes("send")) {
      if (ws.deserializeAttachment()?.auth && this.senders().filter((s) => s !== ws).length === 0) {
        this.last = null;
        this.broadcast("watch", JSON.stringify({ type: "phone", on: false }));
      }
    } else {
      this.tellSenders(ws);
    }
  }
}

function mirror(request, env, origin, headers) {
  const code = new URL(request.url).pathname.slice("/mirror/".length);
  if (!ROOM.test(code)) return json({ error: "no such room" }, 404, headers);
  if (origin !== null && !ALLOWED_ORIGINS.includes(origin)) return json({ error: "forbidden" }, 403, headers);
  if (request.headers.get("Upgrade")?.toLowerCase() !== "websocket") return json({ error: "websocket only" }, 426, headers);
  return env.MIRROR.get(env.MIRROR.idFromName(code)).fetch(request);
}

export default {
  async fetch(request, env) {
    const origin = request.headers.get("Origin");
    const headers = corsHeaders(origin);
    const path = new URL(request.url).pathname;
    if (path.startsWith("/mirror/")) return mirror(request, env, origin, headers);
    if (request.method === "OPTIONS") {
      const allowed = origin === null || Boolean(headers["Access-Control-Allow-Origin"]);
      return new Response(null, { status: allowed ? 204 : 403, headers });
    }
    if (origin !== null && !ALLOWED_ORIGINS.includes(origin)) return json({ error: "forbidden" }, 403, headers);
    if (path === "/enroll" && request.method === "POST") return enroll(request, env, headers);
    if (path.startsWith("/enroll/") && request.method === "GET") return enrollStatus(path.slice("/enroll/".length), env, headers);
    if (path === "/devices" || path.startsWith("/devices/")) return devices(request, env, path, headers);
    if (path !== "/") return json({ error: "not found" }, 404, headers);
    if (request.method !== "POST") return json({ error: "POST only" }, 405, headers);

    // Either the owner's token or an approved device's signature over the time and the body's hash.
    const raw = await request.text();
    let who = checkToken(request.headers.get("Authorization"), env.OWNER_TOKEN) ? "owner" : null;
    if (!who) {
      const h = (n) => request.headers.get(n) || "";
      const d = await signedBy(env, h("X-Device"), h("X-Time"), h("X-Signature"), `${h("X-Time")}.${await sha256(raw)}`);
      if (!d) {
        const pending = DEVICE_ID.test(h("X-Device")) && (await env.DEVICES.get(`pending:${h("X-Device")}`));
        return json({ error: pending ? "pending approval" : "unauthorized" }, 401, headers);
      }
      const useKey = `use:${d.id}:${day()}`;
      const used = Number(await env.DEVICES.get(useKey)) || 0;
      if (used >= DAY_CAP) return json({ ...NO_ANSWER, reason: "daily limit" }, 429, headers);
      await env.DEVICES.put(useKey, String(used + 1), { expirationTtl: 2 * 86400 });
      who = d.name;
    }

    let body;
    try {
      body = JSON.parse(raw);
    } catch {
      return json({ ...NO_ANSWER, reason: "bad request" }, 400, headers);
    }
    const image = typeof body?.image === "string" ? body.image.replace(/^data:image\/\w+;base64,/, "").replace(/\s+/g, "") : "";
    if (!image || !/^[A-Za-z0-9+/]+=*$/.test(image) || image.length > 7_000_000) {
      return json({ ...NO_ANSWER, reason: "bad request" }, 400, headers);
    }
    const question = typeof body.question === "string" && body.question.trim() ? body.question.trim().slice(0, 300) : null;
    if (isCrossing(question)) return json(CROSSING, 200, headers);

    try {
      const raw = await ask(env, { image, corridor: body.corridor ?? null, question });
      return json(finish(raw, question), 200, headers);
    } catch (e) {
      console.error("ask failed:", e && e.message); // the status and the API's message; never the key or the image
      return json(NO_ANSWER, 200, headers);
    }
  },
};
