# Optional integrations

## Tinker
Install `python -m pip install -r requirements-tinker.txt` in your active environment. Set TINKER_API_KEY locally, TV_TINKER_ENABLED=1 and TV_TINKER_MODEL to an account-accessible model (default thinkingmachines/Inkling-2-Small). Optional TV_TINKER_CHECKPOINT is a real sampler checkpoint path. Restart. “Ask Tinker · sends frame” explicitly sends the current frame and typed question. After local Whisper transcription, the question field is populated so the same button can use it. Voice never commands the servo. Cloud failures, ungrounded answers and stale results use local fallback/unknown.

This SDK adapter and training code have not been authenticated against your account. Guard logic is unit tested with a fake sampler. Base-model sampling does not qualify as fine-tuning. Startup/imports/rendering are kept off the event loop; the query has an eight-second deadline and results older than three seconds are withheld.

Prepare real consented JPEG examples, resized to camera limits, in JSONL. Fields: scene_id, image (relative path), question, answer (at most 8 words). Include unknown/occlusion examples. No fabricated dataset is bundled.

```bash
python -m scripts.train_spatial /path/to/examples.jsonl
python -m scripts.train_spatial /path/to/examples.jsonl --run --max-steps 20 --epochs 1
```
The first command validates without API calls. The second spends account credits and runs LoRA SFT; it saves metrics, held-out rows and the actual checkpoint path under data/tinker-training. The split separates scene_id values. Evaluate held-out performance against baseline before claiming improvement. Native audio training, paid inference, model-account availability and successful training were NOT verified here.

Official references: https://tinker-docs.thinkingmachines.ai/cookbook/inkling/ ; https://tinker-docs.thinkingmachines.ai/cookbook/inkling/tml-renderers/ ; https://tinker-docs.thinkingmachines.ai/cookbook/inkling/images/ ; https://github.com/thinking-machines-lab/tinker-cookbook/blob/main/tinker_cookbook/supervised/common.py

## Entrinsik Informer
Local candidate metadata is stored in data/hazards.sqlite3, including simulated labels when using a mock device. The outbox deduplicates the same label/lane signature for 30 seconds, keeps 5000 records, retries with bounded backoff and preserves event IDs. This is candidate review, not an ADA compliance or unique-hazard determination. Coordinates are null unless you tap Attach location (60-second lifetime). Clearing location affects future events only. No image/audio is stored or sent by this integration.

```bash
cd integrations/informer
npm ci
npx informer-init
```
Use your actual tenant connection credentials in that folder's ignored .env. informer-init assigns the real app identity; do not invent an ID. Then:

```bash
npm run workspace:init
npm run dev
npm run deploy
```
The dashboard includes the app's Postgres-backed observations, optional OpenStreetMap location pins and a seven-day count summary. Map tiles load only when requested. Duke is merely the initial map center, never a fabricated event location. Deployment to a tenant and its Postgres have not been tested. JavaScript build and handler tests passed.

After deploying, retrieve the exact signed hazards webhook URL from your app's webhooks listing (`GET /api/apps/{id}/webhooks`). In the MAIN Python project's .env set TV_INFORMER_WEBHOOK_URL to that URL and TV_INFORMER_AUTO_SEND=1. Restart. Verify one candidate is delivered and duplicate event IDs create only one row. Sender credentials stay on the Mac. Do not paste the signed URL into the phone UI.

It sends no facilities emails or work orders. The seven-day summary is a plain SQL query.

References: https://docs.entrinsik.com/developer/apps/reference/webhooks/ ; https://docs.entrinsik.com/developer/apps/reference/server-routes/ ; https://docs.entrinsik.com/developer/apps/reference/workspace-cli/
