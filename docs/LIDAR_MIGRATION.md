# LiDAR + semantic-floor upgrade — migration from the working November 7 build

## Precisely what this changes

- **Adds** `POST /api/arkit/frame?generation=N&sequence=N` to the SAME authenticated FastAPI backend and existing `Controller` (same ESP32 firmware, configured angles, 800 ms hardware neutral timeout, generation fencing, 3-frame consensus and watchdog).
- Accepts synchronized unrotated RGB camera JPEG + metric sceneDepth/confidence + world camera pose + ARKit-classified floor anchor. Projects points into gravity-aligned world coordinates; scores three local candidate wedge corridors across three forward bands. Insufficient floor evidence, tracking or high-confidence LiDAR returns -> UNKNOWN/neutral. Glass, drops, stairs and unseen hazards are **not solved**.
- Adds opt-in ADE20K semantic floor segmentation for the previous Safari RGB-only mode. This is more meaningful than carpet color matching but still is not verified traversability.
- **Preserves and does not overwrite** original `web/app.js` (including your local auto-arm fix), green-card mode, manual mode, `.env`, TLS certificates, ESP32 firmware, known GPIO4 wiring, installed model weights, local databases, existing environments and servo calibration.
- Includes iOS Swift source + XcodeGen project recipe. **Not compiled or tested on an iPhone in this environment.**

## Mac update — exact commands

1. Stop current Uvicorn with **Ctrl+C**. No hardware rewiring and **no ESP32 flash**.
2. Download `TactileVector-LiDAR-v2.zip` into `~/Downloads`, then run:

```bash
mkdir -p ~/Downloads/tv-lidar-stage
unzip -o "$HOME/Downloads/TactileVector-LiDAR-v2.zip" -d "$HOME/Downloads/tv-lidar-stage"
python3 "$HOME/Downloads/tv-lidar-stage/tactilevector/scripts/upgrade_lidar.py" "$HOME/Code/tactilevector"
cd ~/Code/tactilevector
source .venv-obstacle/bin/activate
TV_OBSTACLE_ENGINE=opencv python -m pytest -q
```

**Important:** The updater checks exact hashes of Astra's prior `backend/app.py` and `backend/obstacles.py`. If you changed those locally it **stops without modifying anything**, rather than overwriting your fixes. Only the two existing backend files and new add-on files are overlaid. It prints `BACKUP: ...` for rollback.

3. Start the **same** server and HTTPS certs; keep the ESP32 battery powered:

```bash
cd ~/Code/tactilevector
source .venv-obstacle/bin/activate
TV_OBSTACLE_ENGINE=neural python -m uvicorn backend.app:create_app \
  --factory --host 0.0.0.0 --port 8443 \
  --ssl-certfile certs/server.pem --ssl-keyfile certs/server-key.pem
```

4. Your original iPhone Safari URL and dashboard remain usable. In Safari, verify **Manual**, **Green target**, and **Stop** first. LiDAR requires a *native* iOS app; Safari mode does **not** magically gain LiDAR access.

## Build the iPhone LiDAR companion

```bash
brew install xcodegen
cd ~/Code/tactilevector/ios/TactileVectorLiDAR
xcodegen generate
open TactileVectorLiDAR.xcodeproj
```

- Install/open Xcode, select your iPhone 17 Pro as Run destination, choose your Apple development team under **Signing & Capabilities**, change bundle ID if necessary, and press **Run**. You may need to enable Developer Mode on the iPhone.
- STOP the Safari camera before starting the native app. Do not operate both simultaneously.
- Enter the **same** Mac HTTPS address and current dashboard `TV_API_KEY` into the native app. If Safari already worked, its locally trusted development certificate should work for the native URLSession too; the app does not disable certificate checks.
- Point the phone slightly down and slowly pan across unobstructed floor to let ARKit classify a floor plane; then hold it **stationary**, with **unloaded servo**, for tests.
- Tap `Start + Arm`. The app sends 80x60 LiDAR depth/confidence and camera pose to the Mac at up to ~3.3 fps, which uses the same tested ESP32 transport. `STOP + Neutral` calls `/api/stop`.

## Optional semantic RGB baseline (Mac Safari)

**Only** if you want to compare LiDAR with RGB-only floor classification and your Mac can process three models within the existing safety latency:

```bash
cd ~/Code/tactilevector
source .venv-obstacle/bin/activate
python -m scripts.prepare_semantic  # downloads optional SegFormer checkpoint
TV_RGB_SEGMENTER=segformer TV_OBSTACLE_ENGINE=neural python -m uvicorn \
  backend.app:create_app --factory --host 0.0.0.0 --port 8443 \
  --ssl-certfile certs/server.pem --ssl-keyfile certs/server-key.pem
```

If the additional CPU model causes stale frames, revert to `TV_RGB_SEGMENTER=none` and use the measured LiDAR route. There is no claim of verified scene segmentation performance on your carpet; actual pretrained checkpoint inference was **not run** in this build environment.

## Validation and rollback

- Tests included: metric unprojection, left/right/center obstruction examples, no-floor/low-confidence fail-closed, API auth/arming/generation/stale/stop checks. Original Python suite also passes.
- The native app and actual phone+servo interaction **must be compiled and verified on your Mac/iPhone**. ARKit sceneDepth is unavailable in the iOS Simulator. There is no absolute safe-path guarantee.
- To roll back: stop Uvicorn, run:

```bash
python3 "$HOME/Downloads/tv-lidar-stage/tactilevector/scripts/upgrade_lidar.py" --rollback /EXACT/BACKUP/PATH/PRINTED/ABOVE
```

Restart your old known-working server. Do not delete the rollback backup. If you changed any new files after upgrade, copy those changes elsewhere first because rollback removes newly added files.

**Security:** the previous chat exposed `TV_API_KEY` and `TV_DEVICE_TOKEN`; rotate them for shared-network use before demos. Native app does not store the dashboard key on disk. Do not upload `.env` or local certificate private keys to GitHub.
