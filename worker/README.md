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
The design rules behind them: no LLM narration while walking, never a crossing verdict, the model's distances
overwritten by LiDAR, an abstain flag, something spoken within a second.

| | Prompt | Code |
| --- | --- | --- |
| Never judge whether to cross, go or step | rule 1 | `isCrossing` on the question (before the call) and the answer: `{answer: "I do not judge crossings.", abstain: true, reason: "crossing"}` |
| No distances; the phone speaks the LiDAR distance | rule 2; the corridor reaches the model as bearings and bands, not numbers | `stripDistances` removes a number with m, metres, meters, feet, ft, steps, paces or yards, with its hedge and tail |
| Only what is in the path at chest and head height, and signs | rule 3 | |
| Unsure means abstain with a one-clause reason | rule 4 | `finish` clamps the reason to one clause, 12 words |
| ≤ 25 words, speakable, no markdown | the prompt asks | `speakable` strips markdown and cuts at a sentence boundary |
| 8 s, then speak anyway | | `AbortController`; every error, refusal or truncation returns `Not sure.` with 200 |

## Contract

`POST /` from an enrolled phone, or with `Authorization: Bearer <OWNER_TOKEN>`; anything else is 401.

A phone never holds a shared secret. On first launch the page makes a P-256 key that stays on the phone and sends
`POST /enroll` `{id, name, key}` (UUID, phone name, public JWK). The Worker approves it at once: `{status: "approved", fp}`.
Approval is not a person's judgment; the limits are what bound the cost. Each ask is signed: headers `X-Device`,
`X-Time` (ms) and `X-Signature`, ECDSA P-256 with SHA-256 over `<time>.<sha256 hex of the body>`, base64url; a time more
than a minute off is refused. Limits, each read from `env` (a `vars` entry in `wrangler.jsonc` or a dashboard variable)
with the default in `src/index.js`:

| Variable | Default | Over it |
| --- | --- | --- |
| `DEVICE_DAY_CAP` | 40 asks a phone a day | 429 `reason: "daily limit"` |
| `GLOBAL_DAY_CAP` | 1000 asks a day over all phones | 429 `reason: "global limit"` |
| `ENROLL_DAY_CAP` | 500 new phones a day | `/enroll` 429 |
| (fixed) | 10 enrollments an address an hour | `/enroll` 429 |

The page speaks a plain sentence for each 429. The counts can be passed by a few in a burst: cost control, not a fence;
they are in the `DEVICES` KV (`use:<id>:<day>`, `use:all:<day>`, `enrolled:<day>`), and only a hash of an address is
kept, two hours. Anyone can enroll a key, so the model's reach is bounded by the global cap, not by who is asking;
App Attest (Jog-sama/AHEAD#28) is the later proof that a key lives in the real app.

The owner's switch is the block list: `./devices.sh list` shows each phone with today's count, today's totals and the
blocked ids; `block <id>` removes the phone's key and refuses that id when it enrolls again; `unblock <id>` lifts it. A
blocked phone that clears its app's storage makes a new id, so a block is for an honest phone, not for an attacker.
The token comes from `.dev.vars`. `GET /enroll/<id>` answers `approved`, `blocked` or `unknown`. The mirror's phone
proves itself with a signature over `mirror.<code>.<time>` or the owner token; a blocked phone's open mirror socket lasts
until it closes.

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

## Beta requests

`POST /beta` from the form at jonasneves.com/bridge/ahead/beta/ (`site/beta/index.html`): `{email, device, role, consent: true, source?, token?}`. `device` is one of the LiDAR iPhones in `DEVICES` (`src/beta.js`) or `no-lidar`; `role` is `cane` or `helper`. The row goes into D1 (`ahead-beta`, binding `BETA`, schema in `migrations/`), then the Worker asks App Store Connect to add the email to the external group named `ASC_GROUP_NAME` of app `ASC_APP_ID` (both in `wrangler.jsonc`), so Apple sends the TestFlight invitation and App Store Connect's tester list stays the source of truth. A tester Apple already knows (409) is added to the group by id. A phone without LiDAR is stored as `no-lidar` and no invitation is asked for.

The answer is `{status}`: `invited`, `queued` (no ASC key yet, or Apple refused; the row stays and `error` holds Apple's message), or `no-lidar`; a refused field is 400 `{error: <field>, message}` with a sentence the page reads aloud. The same email asked twice is one row. Five requests an hour per address (429); only a hash of the address is kept, two hours, in the `DEVICES` KV. If `TURNSTILE_SECRET` is set, `token` must pass Cloudflare Turnstile's siteverify; unset, the form relies on the rate limit alone.

Owner only (`Authorization: Bearer <OWNER_TOKEN>`): `GET /beta/list`, `POST /beta/flush` (sends every `queued` or `failed` row once the ASC key exists). `./beta.sh list | flush` wraps both.

Secrets, set with `npx wrangler secret put`: `ASC_KEY_ID` (the key's id), `ASC_ISSUER_ID` (App Store Connect › Users and Access › Integrations), `ASC_PRIVATE_KEY` (the whole text of the downloaded `AuthKey_<id>.p8`; Apple lets it be downloaded once), and optionally `TURNSTILE_SECRET`. The key's role needs access to TestFlight testers (App Manager). Apple's token rules (ES256, `aud` `appstoreconnect-v1`, at most 20 minutes) are what `ascToken` follows; the request body of `POST /v1/betaTesters` is the JSON:API shape and had not been run against Apple at the time of writing, so the first real request is the check (`./beta.sh list` shows a refusal's message).

## Deploy

```sh
npm test                                   # the guardrails, no network
npx wrangler secret put ANTHROPIC_API_KEY  # a key from platform.claude.com
npx wrangler secret put OWNER_TOKEN        # e.g. openssl rand -hex 24; the owner's, for devices.sh and curl, never a phone's
npx wrangler d1 migrations apply ahead-beta --remote   # once, and after a new file in migrations/
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
