# Current upgrade verification

- 64 Python tests passed (original 37 plus new tests), covering marker compatibility, actuator auth/ACK, stale generation, watchdog, obstacle geometry, ambiguity, reversal, unknown→neutral, voice grounding, outbox retries/dedup, migration/rollback and dataset split.
- Real YOLO11n + Depth Anything V2 Small inference executed on Ultralytics bus.jpg on this Mac runtime. Detected bus and people; returned unknown/neutral for insufficient floor evidence. Initial four measured inference times: 138.7, 62.1, 61.1, 60.6 ms. These are processing times, not phone/network/physical latency. See perception-inference.json and real-image-final.json.
- Original Chromium browser test passed: manual press/release, camera, Stop, microphone transport, no overflow/errors. Desktop WebKit loaded and authenticated. Fake media and mock device; NOT physical iOS hardware.
- Informer Vite production build passed. Two Node webhook tests passed with injected SQL function. No tenant deployment/Postgres connection tested.
- Firmware and device client byte identity verified in source-integrity.json. No reflash, physical servo test or current phone/network test performed.
- Tinker guard tests use a fake sampler. No authenticated Tinker inference, training, trained checkpoint, native audio fine-tuning, real Whisper inference or sponsor qualification is claimed.
- Historical Astra evidence is preserved separately in original_astra/ and is not a claim of testing during this upgrade.

The raw per-check files beside this report are authoritative for the latest executed checks. Full hardware acceptance and indoor held-out navigation evaluation remain outstanding.

Final checks also passed: actual localhost HTTP camera→backend→ESP32 simulator, Ruff, JavaScript syntax, compiled C++ safety policy, and obstacle-mode Chromium auto-arm/diagnostics/neutral fallback/voice/hazards/Stop.
