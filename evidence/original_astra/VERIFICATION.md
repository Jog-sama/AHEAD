# Executed verification

Build task completed on Nov 6–7, 2026. Execution host: Linux x86_64, Python 3.12.14. The user's Mac/iPhone/ESP32 were not connected to this environment.

| Check | Actual result |
|---|---|
| Python test suite | **37 passed**, 2.12s in final run; one third-party Starlette/AnyIO deprecation warning |
| Lint | Ruff: all checks passed |
| JavaScript | `node --check web/app.js` passed |
| Real local TCP integration | Two Uvicorn processes: JPEG → FastAPI/OpenCV → HTTP ESP32 simulator. Left/center/right, Stop, stale-input rejection passed |
| Firmware shared safety policy | Native C++ build with warnings as errors passed parsing, bounds, PWM calculation, timeout and millis rollover assertions |
| Full target firmware compilation | **PASS**, Arduino-ESP32 3.2.0, target `esp32:esp32:esp32c3:CDCOnBoot=cdc`; 983956 bytes flash (75%), 37680 bytes globals (11%) |
| Browser behavior | Chromium 134 / Playwright 1.51.1 at 390×844: authenticated connect, manual nudge/release, fake-camera frame upload, Stop, fake-microphone audio upload passed; no JS errors or horizontal overflow |
| Desktop WebKit | Not executed successfully: required Linux shared libraries unavailable. It is not a substitute for iPhone testing anyway |
| Transcript audit | Full original text reviewed, 697 reader lines; architectural mapping and corrections in docs/SPEC_AUDIT.md |

## What those results do and do not establish

The full firmware compiled with the shipped safe-disabled example configuration (`SERVO_PIN=-1`, verification flags false). This checks actual Arduino/C3 types, HTTP, Wi-Fi, FreeRTOS and LEDC APIs. No final GPIO was selected; no binary was flashed; no PWM waveform or servo motion was observed. The archive contains source, not a preconfigured flash binary.

The simulator reproduces the firmware's response schema, authentication, angle range and timeout model. The native test exercises the same `Safety.h` used by the sketch. Neither proves scheduler timing or an electrical failsafe on hardware.

HTTP smoke-run software backend elapsed samples were 12.48, 4.90, 4.45, 7.43, 6.15 and 4.19 ms on this host. These are six **local simulated** measurements, not a benchmark, phone/Wi-Fi measurement, real servo latency, or support for a <50ms claim. Two-frame confirmation adds time; physical latency remains unmeasured.

The browser check used fake camera/microphone devices and a localhost secure-context exception, with the application's CSP enabled. It validates the implemented UI flow, not iPhone trusted-certificate installation, hardware media capture, acoustic output, or physical actuation. A temporary screenshot was reviewed for layout and is not included as a real-camera artifact.

Optional local Whisper transcription has a fake-transcriber plumbing test. No weights, microphone utterance or neural inference were run. Default audio behavior explicitly reports capture-only. No Tinker credentials/training/inference or Informer deployment/delivery were used.

## Still requires the user's equipment

- Exact shield pin labels/rail routing, signal GPIO, bank rating and safe servo power connection.
- Electrical voltage/current/transient checks, flashing, unloaded calibration and soft-lever mounting.
- iPhone Safari HTTPS trust, actual camera/microphone permissions and audible speech.
- Real camera-to-servo direction, input/network/power-loss behavior and latency measurements.
- Any neural perception, object finding, metric distance, sponsor model or civic hazard dashboard.

Reproduce the software checks with `python scripts/verify.py`. Individual outputs are preserved beside this report. Follow docs/ACCEPTANCE.md for physical checks; all its boxes intentionally remain unchecked.
