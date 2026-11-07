# Source audit and delivered changes

Read the complete original Pasted text(1).txt: 696 lines. Modified the extracted TactileVector(1).zip in place. This is an incremental upgrade of Astra's project, not a replacement. Source hashes are in evidence/source-integrity.json.

| Feature | Existing Astra ZIP | Delivered update |
|---|---|---|
| iPhone JPEG → FastAPI → ESP32 | Implemented; user reports physical success | Existing endpoints/auth/ACK protocol retained |
| Manual cues, Stop, watchdog | Implemented | Retained; original tests pass |
| Green target tracking | Implemented, target-following semantics | Preserved as cv test mode |
| Object recognition | Absent | YOLO11n COCO detector, real-image inference executed |
| Relative depth | Absent | Depth Anything V2 Small, local CPU inference executed |
| Free-space decisions | Absent | Appearance-connected floor plus depth geometry and expanded object exclusions; confidence gate, three-frame debounce, neutral on direction changes/unknown |
| Voice | Rules, browser speech, optional local Whisper | Local object clock callouts; no fabricated distance; typed and transcribed input |
| Tinker | TinkerPending placeholder | Optional native SDK image/text sampling, grounded-output rejection, bounded SFT script and scene-level dataset split; no live API call/training performed |
| Informer | Typed event and disconnected sender | Durable SQLite outbox, dedup/retry, opt-in signed webhook export, Postgres migration, webhook receiver, map/table dashboard and 7-day SQL summary |
| GPS / photos | Absent | Explicit phone location, expires after 60s; no photos stored/exported |
| Find & Lock | Absent | Object location voice only; physical target lock deferred |
| Weekly facilities agent | Absent | Deterministic seven-day summary; no autonomous agent or notifications |
| Buzzer / extra motors | Not integrated | Unchanged; no firmware changes |

Gemini's original choices retained: snap-on Anker/ESP32/one-servo module; iPhone camera/mic → Mac compute; YOLO/depth; separate fast perception and optional semantic voice; Tinker and Entrinsik boundaries. Explicit changes/limits: preserve Astra's authenticated /steer interface rather than Gemini's unauthenticated sketch; preserve current one-servo hardware; no browser LiDAR claim; use relative depth rather than metric distances; local ASR + image/text Tinker rather than native audio fine-tuning; reject unsupported cloud answers; no physical Find & Lock or blindfold demo; metadata candidates replace automatic asserted ADA violations/photo uploads. Sub-50ms end-to-end and sponsor qualification are NOT established.

Core implementation: backend/obstacles.py, controller.py, app.py, spatial_voice.py. Original backend/device.py and entire firmware directory are byte-identical. Decision and status gain additive fields. /api/arm adds obstacle; manual and cv retain meanings. /api/frame retains JPEG, generation, sequence and response contract. 0.5s frame freshness, 0.7s backend input expiry, 800ms firmware expiry and angle bounds stay intact.

Confidence is a heuristic evidence score, not a calibrated safety probability. Floor estimation assumes an approximately planar, visible ground surface with consistent appearance, facing camera orientation, and relative depth increasing toward the camera. Uncertain geometry causes abstention. No walking benchmark is claimed.

Next stages: validate recorded indoor scenes from YOUR mounted iPhone; tune thresholds on held-out scenes; run stationary hardware acceptance; obtain Tinker credentials and a labeled scene dataset, evaluate a trained checkpoint against baseline; deploy and verify Informer in your tenant; only then consider native audio, physical target lock and additional sensors.
