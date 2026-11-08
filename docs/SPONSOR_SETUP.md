# Optional integrations

## Tinker
Install `python -m pip install -r requirements-tinker.txt`. Prepare the small attributed dataset, validate it, then explicitly start paid training:

This SDK adapter and training code have not been authenticated against your account. Guard logic is unit tested with a fake sampler. Base-model sampling does not qualify as fine-tuning. Startup/imports/rendering are kept off the event loop; the query has an eight-second deadline and results older than three seconds are withheld.

```bash
python -m scripts.prepare_spatial_dataset
python -m scripts.train_spatial data/tinker-spatial/dataset.jsonl
python -m scripts.train_spatial data/tinker-spatial/dataset.jsonl --run
```
The sources file records author, source page and license. Its spatial transforms are explicit; every source scene stays entirely in train or held-out data. Training runs LoRA SFT and samples both base and fine-tuned checkpoints on held-out scenes, saving exact-match and safe-format metrics under `data/tinker-training`. Set the resulting checkpoint path in `TV_TINKER_CHECKPOINT`, then `TV_TINKER_ENABLED=1`. Runtime output must match a phrase grounded by current perception; voice cannot command the servo. Do not claim improvement unless `evaluation.json` shows it.

Official references: https://tinker-docs.thinkingmachines.ai/cookbook/inkling/ ; https://tinker-docs.thinkingmachines.ai/cookbook/inkling/images/ ; https://tinker-docs.thinkingmachines.ai/tinker/quickstart/

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
The dashboard includes the app's Postgres-backed observations, optional OpenStreetMap location pins and a seven-day count summary. Map tiles load only when requested. Duke is merely the initial map center, never a fabricated event location. Deployment and tenant Postgres execution were not performed here. JavaScript build and handler tests passed.

Before deploy, set `AHEAD_WEBHOOK_SECRET` in the App's Informer Environment panel. After deploying, copy the exact signed hazards URL from the Webhooks panel. Put that URL and the same 32+ character secret in the Mac's ignored `.env` as `TV_INFORMER_WEBHOOK_URL` and `TV_INFORMER_WEBHOOK_SECRET`, then set `TV_INFORMER_AUTO_SEND=1`. Informer's signed URL gates the route and AHEAD adds an HMAC over the exact JSON body. Verify one candidate arrives and a repeat within the five-minute cluster increments `duplicate_count` instead of creating a second map item.

No facilities emails or work orders are created. Seven-day summaries are deterministic SQL, not an untested AI-agent claim.

References: https://docs.entrinsik.com/developer/apps/reference/server-routes/ ; https://docs.entrinsik.com/developer/guides/magic-apps/webhooks/ ; https://docs.entrinsik.com/developer/guides/magic-apps/deployment/
