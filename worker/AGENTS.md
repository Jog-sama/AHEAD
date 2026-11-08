# Ahead, ask

A Cloudflare Worker behind the "ask" button of the Ahead page (`phone-bridge`, `docs/ahead/index.html`). The phone sends one photo and
its LiDAR corridor; the Worker asks Claude and returns one or two speakable sentences. The cane finds the ground; the
page's haptics cover chest and head height from LiDAR; this is for the question the sensors cannot answer: what is
that, what does the sign say.

Model `claude-opus-5-5` at `effort: low`, structured output (`output_config.format`, JSON schema) so the reply always
parses, `fallbacks: "default"` so a classifier refusal is re-run server side. The phone speaks within the 8 s budget
either way: any failure returns `Not sure.` with HTTP 200.

## Guardrails

Each is in the system prompt and again in code (`src/index.js`), because a prompt is advice and the code is the floor.
The reasons are from the design council in `../research/handoff.md`: no LLM narration while walking, never a
crossing verdict, the model's distances overwritten by LiDAR, an abstain flag, something spoken within a second.

| | Prompt | Code |
| --- | --- | --- |
| Never judge whether to cross, go or step | rule 1 | `isCrossing` on the question (before the call) and the answer: `{answer: "I do not judge crossings.", abstain: true, reason: "crossing"}` |
| No distances; the phone speaks the LiDAR distance | rule 2; the corridor reaches the model as bearings and bands, not numbers | `stripDistances` removes a number with m, metres, meters, feet, ft, steps, paces or yards, with its hedge and tail |
| Only what is in the path at chest and head height, and signs | rule 3 | |
| Unsure means abstain with a one-clause reason | rule 4 | `finish` clamps the reason to one clause, 12 words |
| ≤ 25 words, speakable, no markdown | the prompt asks | `speakable` strips markdown and cuts at a sentence boundary |
| 8 s, then speak anyway | | `AbortController`; every error, refusal or truncation returns `Not sure.` with 200 |

## Contract

`POST /` from an approved phone, or with `Authorization: Bearer <OWNER_TOKEN>`; anything else is 401.

A phone never holds a shared secret. On first launch the page makes a P-256 key that never leaves the phone and sends
`POST /enroll` `{id, name, key}` (a UUID, the phone's name, the public JWK); the answer is `{status: "pending", fp}`
until the owner runs `./devices.sh approve <id>` (`list` shows who is waiting with the same eight-character `fp` the
phone shows, so the owner approves the phone in hand and not one that enrolled under the same name; `revoke <id>`
removes a phone; the token comes from `.dev.vars`). Twenty phones may wait at once. `GET /enroll/<id>` answers the status. An approved phone signs each ask: headers `X-Device`,
`X-Time` (ms) and `X-Signature`, ECDSA P-256 with SHA-256 over `<time>.<sha256 hex of the body>`, base64url; a time
more than a minute off is refused, and a phone gets 300 asks a day (429 past that, `reason: "daily limit"`; the
count is a KV read then write, so a burst can pass it by a few, which is cost control, not a fence). A
pending phone's ask is 401 `{error: "pending approval"}`, which the page shows. Keys and counts live in the `DEVICES`
KV namespace. The mirror's phone proves itself the same way, with a signature over `mirror.<code>.<time>`, or with the owner
token; a revoked phone's open mirror socket lasts until it closes.

`GET /mirror/<code>` upgraded to a WebSocket is the demo mirror: the phone connects with `?role=send` and says
`{type: "hello", token}` or `{type: "hello", device: {id, time, sig}}` within 5 s (else closed with 4001); a computer
connects with no role and needs only the code (8 characters, no 0, O, 1 or I). Whatever the phone then sends goes
to every viewer: `{type: "state", …}`, a snapshot of its screen as text and cell classes, kept and replayed to a
viewer that joins late; `{type: "row", row}` and `{type: "reset"}` for the walk log. Viewers hear
`{type: "phone", on}`; the phone hears `{type: "watchers", n}`. One Durable Object (`Mirror`, SQLite-backed) per code;
nothing is stored. The photo never passes through it.

Request: `{image, corridor, question}`. `image` is base64 JPEG without a `data:` prefix (send the long side at
1092 px or less; the API does not resize below that). `corridor` is `[[9], [9]]` or null: the chest band then the head
band, metres or null per cell, 30° left to 30° right, the 5th-percentile distance per cell, as `depth.start` emits it.
`question` is a string or null.

Response, always JSON: `{answer, abstain, reason?}`. `answer` is at most 25 words. `abstain: true` comes with a
`reason`: `"crossing"`, `"no answer"`, or the model's one clause.

CORS: `https://jonasneves.com` and `null` (the page bundled in the app), with `OPTIONS`. Add an origin to
`ALLOWED_ORIGINS` in `src/index.js`.

## Deploy

```sh
npm test                                   # the guardrails, no network
npx wrangler secret put ANTHROPIC_API_KEY  # a key from platform.claude.com
npx wrangler secret put OWNER_TOKEN        # e.g. openssl rand -hex 24; the owner's, for devices.sh and curl, never a phone's
npx wrangler deploy
```

Locally, `npx wrangler dev` reads both from a `.dev.vars` file (ignored by git; `devices.sh` reads `OWNER_TOKEN`
from it too). Then, with any real JPEG (the API rejects a synthetic one-pixel file with "Could not process image"):

```sh
curl -s https://ahead-ask.<account>.workers.dev/ \
  -H "Authorization: Bearer $OWNER_TOKEN" -H "Content-Type: application/json" \
  -d "{\"image\":\"$(base64 -i photo.jpg | tr -d '\\n')\",\"corridor\":[[null,null,null,null,1.2,null,null,null,null],[null,null,null,null,null,null,null,null,null]],\"question\":\"What is ahead?\"}"
```

Expect a described obstacle for a street photo, and `{"answer":"Not sure.","abstain":true,"reason":...}` for anything
that is not a scene (measured 2026-11-07: an app icon answered "the image is a cartoon drawing" in 2.1 s round trip).
Any failure is logged as `ask failed: <status> <API message>`, readable with `npx wrangler tail ahead-ask`.
If answers arrive past the 8 s budget on a phone network, `claude-haiku-5-5` is the swap; it reads images too.
