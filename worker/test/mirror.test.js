import { test } from "node:test";
import assert from "node:assert/strict";
import worker, { Mirror, ROOM } from "../src/index.js";

// A stand-in for the Durable Object's WebSocket context: tags, attachments and the sockets each side sent.
function room(token = "tok") {
  const sockets = [];
  const ctx = {
    acceptWebSocket(ws, tags) {
      ws.tags = tags;
      sockets.push(ws);
    },
    getWebSockets: (tag) => sockets.filter((ws) => ws.open && (!tag || ws.tags.includes(tag))),
    getTags: (ws) => ws.tags,
  };
  const m = new Mirror(ctx, { OWNER_TOKEN: token });
  const join = (tag) => {
    const ws = {
      tags: [tag],
      open: true,
      sent: [],
      att: null,
      send(t) {
        this.sent.push(JSON.parse(t));
      },
      close(code) {
        this.open = false;
        this.closed = code;
      },
      serializeAttachment(a) {
        this.att = a;
      },
      deserializeAttachment() {
        return this.att;
      },
    };
    ctx.acceptWebSocket(ws, [tag]);
    if (tag === "send") ws.serializeAttachment({ auth: false, since: Date.now() });
    else {
      ws.send(JSON.stringify({ type: "phone", on: m.senders().length > 0 }));
      if (m.last) ws.send(m.last);
      m.tellSenders();
    }
    return ws;
  };
  return { m, join };
}

test("the phone must say the shared token first; anything else closes the socket", () => {
  const { m, join } = room();
  const bad = join("send");
  m.webSocketMessage(bad, JSON.stringify({ type: "state", t: {} }));
  assert.equal(bad.closed, 4001);
  const wrong = join("send");
  m.webSocketMessage(wrong, JSON.stringify({ type: "hello", token: "nope" }));
  assert.equal(wrong.closed, 4001);
  const late = join("send");
  late.serializeAttachment({ auth: false, since: Date.now() - 6000 });
  m.webSocketMessage(late, JSON.stringify({ type: "hello", token: "tok" }));
  assert.equal(late.closed, 4001);
});

test("snapshots reach every viewer, a late viewer gets the last one, and the phone hears how many watch", () => {
  const { m, join } = room();
  const viewer = join("watch");
  assert.deepEqual(viewer.sent, [{ type: "phone", on: false }]);
  const phone = join("send");
  m.webSocketMessage(phone, JSON.stringify({ type: "hello", token: "tok" }));
  assert.equal(phone.closed, undefined);
  assert.deepEqual(phone.sent, [{ type: "watchers", n: 1 }]);
  assert.deepEqual(viewer.sent.at(-1), { type: "phone", on: true });

  const snap = JSON.stringify({ type: "state", t: { state: "Watching" } });
  m.webSocketMessage(phone, snap);
  m.webSocketMessage(phone, JSON.stringify({ type: "row", row: ["0.10", "state"] }));
  assert.deepEqual(viewer.sent.slice(-2), [JSON.parse(snap), { type: "row", row: ["0.10", "state"] }]);

  const late = join("watch");
  assert.deepEqual(late.sent, [{ type: "phone", on: true }, JSON.parse(snap)]);
  assert.deepEqual(phone.sent.at(-1), { type: "watchers", n: 2 });

  m.webSocketClose(late);
  assert.deepEqual(phone.sent.at(-1), { type: "watchers", n: 1 });
  m.webSocketClose(phone);
  assert.deepEqual(viewer.sent.at(-1), { type: "phone", on: false });
  assert.equal(m.last, null);
});

test("a viewer's messages go nowhere", () => {
  const { m, join } = room();
  const phone = join("send");
  m.webSocketMessage(phone, JSON.stringify({ type: "hello", token: "tok" }));
  const viewer = join("watch");
  m.webSocketMessage(viewer, JSON.stringify({ type: "state", t: { state: "forged" } }));
  assert.equal(m.last, null);
  assert.equal(phone.sent.filter((x) => x.type === "state").length, 0);
});

test("the Worker routes /mirror/<code> to the room, and only a page origin or none may open one", async () => {
  const seen = [];
  const env = {
    OWNER_TOKEN: "tok",
    MIRROR: { idFromName: (n) => `id:${n}`, get: (id) => ({ fetch: (r) => (seen.push([id, r.url]), new Response("ok")) }) },
  };
  const req = (code, headers = {}) =>
    new Request(`https://ahead-ask.test/mirror/${code}`, { headers: { Upgrade: "websocket", Origin: "https://jonasneves.com", ...headers } });
  assert.ok(ROOM.test("ABCD2345") && !ROOM.test("abcd2345") && !ROOM.test("ABCD0145"));
  assert.equal((await worker.fetch(req("ABCD2345"), env)).status, 200);
  assert.deepEqual(seen, [["id:ABCD2345", "https://ahead-ask.test/mirror/ABCD2345"]]);
  assert.equal((await worker.fetch(req("ABCD2345", { Origin: "null" }), env)).status, 200);
  const noOrigin = new Request("https://ahead-ask.test/mirror/ABCD2345", { headers: { Upgrade: "websocket" } });
  assert.equal((await worker.fetch(noOrigin, env)).status, 200);
  assert.equal((await worker.fetch(req("ABCD2345", { Origin: "https://evil.example" }), env)).status, 403);
  assert.equal((await worker.fetch(req("short"), env)).status, 404);
  const plain = new Request("https://ahead-ask.test/mirror/ABCD2345", { headers: { Origin: "https://jonasneves.com" } });
  assert.equal((await worker.fetch(plain, env)).status, 426);
  assert.equal(seen.length, 3);
});
