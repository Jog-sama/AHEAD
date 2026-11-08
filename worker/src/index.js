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

export function checkToken(header, secret) {
  if (typeof header !== "string" || typeof secret !== "string" || !secret) return false;
  const m = /^Bearer\s+(\S+)\s*$/.exec(header);
  if (!m) return false;
  const a = new TextEncoder().encode(m[1]);
  const b = new TextEncoder().encode(secret);
  let diff = a.length ^ b.length;
  for (let i = 0; i < Math.max(a.length, b.length); i++) diff |= (a[i] ?? 0) ^ (b[i] ?? 0);
  return diff === 0;
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
    h["Access-Control-Allow-Methods"] = "POST, OPTIONS";
    h["Access-Control-Allow-Headers"] = "Authorization, Content-Type";
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

export default {
  async fetch(request, env) {
    const origin = request.headers.get("Origin");
    const headers = corsHeaders(origin);
    if (request.method === "OPTIONS") {
      const allowed = origin === null || Boolean(headers["Access-Control-Allow-Origin"]);
      return new Response(null, { status: allowed ? 204 : 403, headers });
    }
    if (request.method !== "POST") return json({ error: "POST only" }, 405, headers);
    if (!checkToken(request.headers.get("Authorization"), env.SHARED_TOKEN)) return json({ error: "unauthorized" }, 401, headers);

    let body;
    try {
      body = await request.json();
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
