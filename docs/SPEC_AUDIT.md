# Full Gemini specification audit

**Source reviewed:** the user's `Pasted text(1).txt`, retrieved from the saved file during this Work task. The full reader output contains 697 lines (the task called it 696); it ends with the Sunday judge-fair Step 15. All sections were reviewed, including earlier discarded project ideas, inventory interpretation, final TactileVector concept, and roadmap. A copy is in `GEMINI_ORIGINAL.txt`.

At task start the transcript was not attached. The user was asked to attach it; the saved original subsequently became accessible and was read in full. This artifact therefore incorporates a completed transcript audit, not a summary-only claim. Photos mentioned inside the transcript are references, not embedded pixels; this does **not** verify those photos or the shield pin labels.

Priority: the final Gemini TactileVector proposal, amended by the user's current one-servo hardware inventory and explicit safety constraints. Earlier rover/turret alternatives are context, not requirements to silently substitute. “Safety correction” below means an intentional departure, not a claim Gemini originally specified it.

| Architectural choice | Gemini evidence (reader lines) | Implementation | Audit |
|---|---|---|---|
| Modular snap-on grip | 604–640 | Removable sleeve around cylindrical Anker; strap-on mounting retained | Match |
| Battery is handle/chassis | 619–628, 653 | Cylinder retained; exact model/ports unverified | Match with verification requirement |
| Servo count | 469 says 2; 474 one or two; final 657 one | Exactly one positional SG90; current inventory authoritative | Final-spec match / current hardware constraint |
| Thumb-nudge output | 472–478, 644 | One left/neutral/right soft lever; no floor traction | Match |
| Motorized floor wheel/cane | Earlier 94–108, 395–402; superseded at 468 | No wheel, DC motor, shaft or pan-tilt in MVP | Final-spec match |
| ESP32-C3 and expansion shield | 428, 651 | C3-targeted Arduino LEDC implementation; no extra servo controller | Match |
| Shield colors prove pinout | 437, 596, 665 | No assumed rail routing; GPIO unset, verification flags false, voltage/continuity procedure | Safety correction |
| Servo supply through shield | 621 | Conditional on measured/rated 5V rail; separate bench servo supply otherwise | Safety correction |
| iPhone powers ESP32 | 433 advises against it | iPhone does not power board/servo | Match, explanation of accessory error not treated as verified diagnosis |
| Phone camera/mic + laptop | 568–588, 655, 671–674 | Safari getUserMedia + HTTPS JPEG/audio → FastAPI | Match |
| Safari LiDAR | 478, 513 | Ordinary RGB camera only; no LiDAR assumption | Platform correction |
| HTTP control | 574, 667 | `/steer?angle=X` retained, added token/bounds/timeout | Match + hardening |
| Example wide angle 45° | 600 | Initial 88/92, defaults 80/100, hard bounds 75..105 | Safety correction; shaft angles uncalibrated |
| Buzzer / button | 507–511, 565 | Optional parts; phone records/speaks; no unverified GPIO use | Deferred; not required for tonight |
| 5FPS camera stream | 582 | Sequential 640×480-max JPEG uploads capped at 5FPS | Match as target, not measured guarantee |
| YOLO/DepthAnythingV2/MediaPipe fast loop | 586, 674 | Dependency-free manual + OpenCV colored-target baseline first; optional vision Protocol | Deliberate baseline change authorized by current task; not real path safety |
| Less than 50ms latency | 478, 586, 644, 697 | Measured software timing fields; no claimed motion latency | Unsupported guarantee removed |
| Short clock-face responses | 487, 588, 646 | 10/12/2 o'clock concise cues; no invented object/distance | Match grammar; semantic object finding deferred |
| Voice recording | 582 | Hold-to-record, max 4sec UI; negotiated codec; optional local CPU Whisper | Match capture; default explicitly capture-only |
| Active target lock | 517, 535 | Not implemented; camera target demonstrates directional cues only | Deferred; one axis is not 2-DOF tracking |
| Tinker Inkling multimodal | 484, 646, 676 | Official docs confirm multimodal family and show Inkling-2-Small; local protocol, unconfigured adapter | Interface only; no trained model, credentials, or results |
| Tinker model IDs/access | Same | Cookbook/model listing naming can differ; verify account's live capabilities before choosing ID | Operational uncertainty documented |
| Entrinsik hazard map | 491, 648, 683–685 | Verified-contract optional signed-webhook sender; typed event | Interface only; no deployed dashboard/map or synthetic GPS presented as real |
| Automatic ADA hazard recognition | 491 | Disabled; marker CV cannot label hazards or ADA compliance | Safety/data-quality correction |
| GPS | 491, 683 | Optional nullable schema fields; browser does not request location | Deferred; no inferred coordinates |
| Real parts availability | 426, 440–453, 650–661 | Current user-owned list separated from unknown/borrowed parts | Corrected interpretation; no invented ownership |
| Mounting with hot glue | 503, 600, 623 | Sleeve/plate/straps; no heat/drilling into battery, guarded soft horn | Safety correction |
| Blindfolded judge walking | 543, 697 | Stationary, sighted, supervised only | Required safety correction |
| Weekend phases | 663–697 | Tonight vertical slice; Saturday refine/integrations; Sunday hardening/video | Match priorities; actual event deadlines must be checked with organizers |
| Prize/price/competitor claims | 494, 535–540, 614–617 | Treated as pitch hypotheses; not measured/certified results | Unsupported claims not repeated as fact |
| Secrets | Not detailed | Ignored local .env/config.h, random local tokens, no embedded sponsor keys | Necessary implementation addition |
| Power loss and stale input | Not detailed | Independent firmware watchdog, backend input lease, stop generations, no auto-rearm | Necessary implementation addition |

## Assumptions to resolve physically

- The available servo is a positional SG90-style device, compatible with the verified supply and 3.3V signal. Clone behavior is not guaranteed.
- The exact board/shield layout, power-bank model/output rating, breakout availability, and jumper current rating remain unknown.
- A shared network permits Mac↔ESP32 and iPhone↔Mac traffic. iPhone hotspot routing must be tested.
- Directional cues correspond to the person's viewpoint only after camera/horn orientation calibration.
- Software requests and ACKs establish command transport, not achieved physical angle or safe contact force.
- Mac setup, trusted certificate installation and actual iOS media capture require the user's devices.
