# Verification

- The Python tests cover marker compatibility, actuator auth/ACK, stale generation, watchdog, obstacle geometry, ambiguity, reversal, unknown→neutral, voice grounding, outbox retries/dedup and dataset split.
- Real YOLO11n + Depth Anything V2 Small inference executed on Ultralytics bus.jpg on this Mac runtime. Detected bus and people; returned unknown/neutral for insufficient floor evidence. Initial four measured inference times: 138.7, 62.1, 61.1, 60.6 ms. These are processing times, not phone/network/physical latency. See perception-inference.json and real-image-final.json.
- Original Chromium browser test passed: manual press/release, camera, Stop, microphone transport, no overflow/errors. Desktop WebKit loaded and authenticated. Fake media and mock device; NOT physical iOS hardware.
- Informer Vite production build passed. Two Node webhook tests passed with injected SQL function. No tenant deployment/Postgres connection tested.
- The firmware has not been reflashed, and no physical servo or phone/network test has been run.
- Tinker guard tests use a fake sampler. No authenticated Tinker inference, training, trained checkpoint, native audio fine-tuning, real Whisper inference or sponsor qualification has been run.

The raw per-check files beside this report are authoritative for the latest executed checks. Full hardware acceptance and indoor held-out navigation evaluation remain outstanding.

Final checks also passed: actual localhost HTTP camera→backend→ESP32 simulator, Ruff, JavaScript syntax, compiled C++ safety policy, and obstacle-mode Chromium auto-arm/diagnostics/neutral fallback/voice/hazards/Stop.
