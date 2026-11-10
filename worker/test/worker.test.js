import { test } from "node:test";
import assert from "node:assert/strict";
import worker, { CROSSING, NO_ANSWER } from "../src/index.js";

const env = { OWNER_TOKEN: "tok", ANTHROPIC_API_KEY: "key", DEVICES: { get: async () => null } };
const PIXEL = "/9j/4AAQSkZJRgABAQAAAQABAAD/2wBDAP//////////////////////////////////////////////////////////////////////////////////////wgALCAABAAEBAREA/8QAFBABAAAAAAAAAAAAAAAAAAAAAP/aAAgBAQABPxA=";
const post = (body, headers = {}) =>
  new Request("https://ahead-ask.test/", {
    method: "POST",
    headers: { Authorization: "Bearer tok", Origin: "https://aheadcane.github.io", "Content-Type": "application/json", ...headers },
    body: typeof body === "string" ? body : JSON.stringify(body),
  });

test("OPTIONS answers allowed origins, including the app's null origin", async () => {
  for (const origin of ["https://aheadcane.github.io", "null"]) {
    const res = await worker.fetch(new Request("https://ahead-ask.test/", { method: "OPTIONS", headers: { Origin: origin } }), env);
    assert.equal(res.status, 204, origin);
    assert.equal(res.headers.get("Access-Control-Allow-Origin"), origin);
  }
  const res = await worker.fetch(new Request("https://ahead-ask.test/", { method: "OPTIONS", headers: { Origin: "https://evil.example" } }), env);
  assert.equal(res.status, 403);
  assert.equal(res.headers.get("Access-Control-Allow-Origin"), null);
});

test("a wrong or missing token is a 401 the page can read", async () => {
  const res = await worker.fetch(post({ image: PIXEL }, { Authorization: "Bearer nope" }), env);
  assert.equal(res.status, 401);
  assert.equal(res.headers.get("Access-Control-Allow-Origin"), "https://aheadcane.github.io");
  const none = await worker.fetch(post({ image: PIXEL }, { Authorization: "" }), env);
  assert.equal(none.status, 401);
});

test("a crossing question is answered without calling the model", async () => {
  const saved = globalThis.fetch;
  globalThis.fetch = () => assert.fail("model called");
  try {
    const res = await worker.fetch(post({ image: PIXEL, corridor: null, question: "Is it safe to cross?" }), env);
    assert.equal(res.status, 200);
    assert.deepEqual(await res.json(), CROSSING);
  } finally {
    globalThis.fetch = saved;
  }
});

test("a malformed body is a 400 that still speaks", async () => {
  const res = await worker.fetch(post("{not json"), env);
  assert.equal(res.status, 400);
  assert.deepEqual(await res.json(), { ...NO_ANSWER, reason: "bad request" });
  const noImage = await worker.fetch(post({ question: "what is ahead" }), env);
  assert.equal(noImage.status, 400);
});

test("the model's JSON goes through the guardrails; a failure speaks Not sure", async () => {
  const saved = globalThis.fetch;
  const reply = (body) => Promise.resolve(new Response(JSON.stringify(body), { status: 200 }));
  try {
    globalThis.fetch = (url, init) => {
      const sent = JSON.parse(init.body);
      assert.equal(sent.model, "claude-opus-5-5");
      assert.equal(sent.output_config.format.type, "json_schema");
      assert.equal(sent.messages[0].content[0].type, "image");
      assert.match(sent.messages[0].content[1].text, /head height: something near, right/);
      assert.doesNotMatch(sent.messages[0].content[1].text, /1\.6/);
      return reply({
        stop_reason: "end_turn",
        content: [{ type: "text", text: JSON.stringify({ answer: "A **branch** about 2 metres ahead at head height.", abstain: false, reason: "" }) }],
      });
    };
    const corridor = [[null, null, null, null, null, null, null, null, null], [null, null, null, null, null, null, 1.6, null, null]];
    const res = await worker.fetch(post({ image: PIXEL, corridor, question: null }), env);
    assert.deepEqual(await res.json(), { answer: "A branch at head height.", abstain: false });

    globalThis.fetch = () => Promise.resolve(new Response("overloaded", { status: 529 }));
    const down = await worker.fetch(post({ image: PIXEL, corridor: null, question: null }), env);
    assert.equal(down.status, 200);
    assert.deepEqual(await down.json(), NO_ANSWER);

    globalThis.fetch = () => reply({ stop_reason: "refusal", content: [] });
    const refused = await worker.fetch(post({ image: PIXEL, corridor: null, question: null }), env);
    assert.deepEqual(await refused.json(), NO_ANSWER);
  } finally {
    globalThis.fetch = saved;
  }
});
