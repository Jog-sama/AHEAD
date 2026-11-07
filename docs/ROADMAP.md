# Weekend roadmap

Dates use Durham / America/New_York: Friday Nov 6, Saturday Nov 7, Sunday Nov 8, 2026. Gemini's Saturday 5pm placeholder and Sunday 8:30/9am finish/submission times are transcript claims, not independently verified event rules. Confirm with organizers before scheduling around them.

| Phase | Do | Done when |
|---|---|---|
| Tonight: software | Run mock; install dependencies; test UI/manual/camera; set up trusted HTTPS | iPhone frames reach Python and deterministic L/C/R commands appear |
| Tonight: electrical | Verify GPIO/rails; establish rated 5V servo supply + common ground; flash horn-off | Neutral and tiny unloaded movements work without resets |
| Tonight: complete loop | Switch to real ESP32; green target → cue; Stop/lost-input tests | Observed physical L/C/R + neutral after failure, all while stationary |
| Tonight: packaging | Strap servo/body to a removable padded sleeve; soft lever; power disconnect | Stable tabletop grip with no trapped finger or wire strain |
| Saturday morning | Complete physical acceptance, improve mount from actual measurements, record latency/dropout behavior | Reproducible demo and measured results, not guessed performance |
| Saturday afternoon | Optional local ASR; optional neural scene/depth model with held-out evaluation | Voice/vision benefits demonstrated without weakening timeout behavior |
| Saturday sponsor work | Verify Tinker model/account; train small dataset if feasible. Verify Informer tenant/handler, then send clearly labeled test event | Real recorded training/inference/delivery evidence, or leave feature labeled pending |
| Saturday evening | Polish explanation and diagrams; build a dashboard only against actual Informer docs/tenant | Show real capability; keep mock/demo data visibly labeled |
| Sunday early | Freeze features, rerun tests/acceptance, charge devices, rehearse offline/manual fallback | A 90-second stationary demo works repeatedly |
| Sunday submission | Record short video, architecture, spec corrections, test results, limitations; confirm official deadline | Submission documents actual implemented work |

If time is short, omit neural models and sponsor integration before compromising the physical vertical slice. The fallback is the same hardware with manual directional cues, explicitly demonstrated as manual. A mock-device banner must never be hidden to imply a connected servo.

Potential team split: one person owns power/mechanics, one the Mac/iPhone network and software, one model evaluation/data, one sponsor/dashboard and pitch. These are suggested roles, not assumptions about team members' availability.
