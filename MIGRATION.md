# Update your WORKING project — no firmware reflash

Stop the current Mac backend first. Keep your ESP32 firmware, GPIO4 wiring, existing .env, device token, calibrated angles, HTTPS certificates and network setup.

Download TactileVector-ObstacleUpdate.zip into Downloads. Change ONLY TV_CURRENT below to the absolute path of your working project. The updater edits that project and makes a rollback backup of each overwritten file. It preserves firmware, .env, certificates, models, data and existing virtual environments.

```bash
TV_CURRENT="/absolute/path/to/your/working/tactilevector"
TV_UPDATE="$HOME/Downloads/TactileVector-ObstacleUpdate"
mkdir -p "$TV_UPDATE"
unzip -o "$HOME/Downloads/TactileVector-ObstacleUpdate.zip" -d "$TV_UPDATE"
python3 "$TV_UPDATE/tactilevector/scripts/upgrade_existing.py" "$TV_CURRENT"
cd "$TV_CURRENT"
python3 -m venv .venv-obstacle
source .venv-obstacle/bin/activate
python -m pip install -r requirements-perception.txt -r requirements-dev.txt
python -m scripts.prepare_vision
TV_OBSTACLE_ENGINE=opencv python -m pytest -q
```

Use Python 3.11+ (3.12 tested). Model preparation explicitly downloads YOLO11n and Depth Anything V2 Small, then warms them up. Weights are not bundled in this source ZIP. Do not run configure.py again. Existing .env is retained. No new mandatory environment entries.

Restart with your SAME known-working server command, from the working project with .venv-obstacle active. If using the original certificate paths:

```bash
python -m uvicorn backend.app:create_app --factory --host 0.0.0.0 --port 8443 --ssl-certfile certs/server.pem --ssl-keyfile certs/server-key.pem
```

Keep one worker; no --reload. Reuse your existing phone HTTPS URL and access key. Reload Safari. Connect → select “Obstacle scene” → Start camera (auto-arms). If camera is already on, tap Arm. Point the rear camera slightly down so the ground occupies the lower half. Keep the phone fixed for the initial stationary demo.

1. Verify Manual left/right and Stop first with unloaded servo. Direction calibration still uses your existing TV_LEFT/TV_RIGHT.
2. Select “Green target tracking · TEST ONLY” to recover the old behavior unchanged: green left follows left.
3. In obstacle mode: a left obstruction produces a right cue only when right-side floor evidence supports it. A central obstruction with two indistinguishable openings stays neutral. Three consistent frames are required. Neutral can mean uncertain, blocked, or centered: read the displayed phrase.
4. Cover the camera / point at a wall / stop the stream: expect uncertainty or watchdog disarm, not a directional cue. Missing models always stay neutral.
5. Ask “where is the chair” or “what is ahead”. Object names depend on detections; no meters/feet are inferred. Existing microphone input needs the optional local Whisper setup in docs/EXTENSIONS.md. In the new environment reinstall requirements-voice.txt if you previously enabled Whisper; retain TV_WHISPER_MODEL.

Optional .env settings (defaults shown):
```dotenv
TV_OBSTACLE_ENGINE=neural
TV_MODEL_DEVICE=cpu
TV_YOLO_MODEL=models/yolo11n.pt
TV_DEPTH_MODEL=models/depth-anything-v2-small
TV_SENSITIVITY=conservative
TV_TINKER_ENABLED=0
TV_INFORMER_AUTO_SEND=0
```
Use TV_SENSITIVITY=strict to require more floor support. TV_OBSTACLE_ENGINE=opencv is observation-only fallback; it never authorizes obstacle-mode cues. MPS is optional, CPU was tested. Do not increase watchdog deadlines to hide slow inference. A stale-frame error means neutral/stop and investigate latency.

Rollback: stop backend, run `python3 scripts/upgrade_existing.py /path/printed-backup-directory --rollback`, reactivate your OLD virtual environment, and run your old server command. Dependency changes were isolated in .venv-obstacle. Preserve the backup until phone/hardware acceptance is complete. The supplied ZIP predates your local configuration; local firmware/config.h is deliberately excluded from the updater.

Scope: stationary, sighted, supervised demonstration. No blindfold walking. Relative monocular depth and apparent floor are not verified navigability; glass, stairs/drops, unusual surfaces and hidden objects remain limitations.
