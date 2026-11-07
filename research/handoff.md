# Cane project handoff (Duke Triangle hackathon)

Working design under review: an AI-assisted white cane built from the owner's stack: ESP32-C3 with a VL53L0X and BLE
(esp32-labs/), iPhone 15 Pro running Bridge (phone-bridge/, LiDAR depth grid, haptics, speech, on-device LLM, BLE,
camera), a MacBook for development only, and a cloud vision LLM for escalation. Full brief every reviewer got:
cane-brief.md in this folder. Council outputs land in council-out/ (one .md per external model) when the run finishes.

## Verified so far (read at the source, not from a summary)

- Manduchi & Kurniawan 2011, survey of 307 blind/legally blind adults
  (https://tr.soe.ucsc.edu/sites/default/files/technical-reports/UCSC-SOE-10-24.pdf): 13% have a head-level collision at
  least monthly, 7% a fall at least monthly; only 2% of blind respondents never had a head-level collision. 86% of
  head-level collisions are outdoors, tree branches the majority, then poles, signs, construction, trucks; indoors,
  doors and cabinets left ajar. 23% of head-level collisions had medical consequences; 43% changed how they walk
  afterwards, 26% lost confidence. Mobility aid (cane vs dog) makes no significant difference to the rates.
- Scientific Reports 2026, NOA vest vs BuzzClip vs cane alone, 13 blind adults, indoor
  (https://pmc.ncbi.nlm.nih.gov/articles/PMC12909938/): both devices slowed walking (0.68 → 0.60 and 0.57 m/s).
  BuzzClip (ultrasonic clip, vibration) raised NASA-TLX workload 3.18 → 6.22 and frustration 2.77 → 7.54; complaints:
  vibrations too weak to tell from the cane tip (4/13), too frequent (5/13), no height or field-of-view info (5/13).
  NOA (camera vest, spatial audio) cut body contacts 2.92 → 1.62 and 12/13 would adopt it, but 8/13 called it heavy
  (1.3 kg). Authors: precision of feedback matters more than modality; weight kills adoption; test outdoors.
- Martinez et al. ICCHP 2014 (https://cvhci.iar.kit.edu/publications_986.php): for white-cane users, audio feedback
  for short-range obstacles carried about 22× the NASA-TLX workload of cane-mounted haptics; blindfolded sighted
  testers showed the opposite preference, so blindfolded testing misleads on modality.
- VL53L0X/L1X in direct sun: SPADs saturate, range falls to ~30 cm (ST community threads). Low-e glass blocks 940 nm.
- GuideTouch, HRI 2026 (arXiv 2601.13813): ESP32 + two VL53L5CX 8×8 ToF, 4 motors; simpler haptic vocabularies
  (10 patterns) were recognised far better than richer ones (92.9% vs 78.4%).
- No published FPS for YOLO11n Core ML on an iPhone 15 Pro; vendor claims of 60+ fps are unsourced. Measure it.
- ARKit LiDAR battery/thermal: no published per-hour figures; profile thermalState over an hour.

## Council synthesis (2026-11-07)

Seats: Codex gpt-6-astra, Antigravity gemini-4-argon-high, Cursor composer-2.5, Opus claude-opus-5-5 as same-family
control. Grok grok-4.7 produced nothing in 20 minutes (harness fault, not an abstention). Full reports: council-out/.
Convergence counts the three external families. Claims marked "verified" were read at the source by this session.

### Convergent (3 of 3 external, plus Opus)
1. Build for the one gap the cane leaves: head and chest height. Verified: 10 O&M-trained blind cane users rated
   "navigation is about finding my destination" 4.1/5 and "about avoiding obstacles" 2.4/5 (arXiv 2504.19345).
2. The VL53L0X is the wrong outdoor sensor: ~80 cm on white, ~50 cm on grey in daylight (datasheet-level figures from
   two members, matched by a third-party summary; forum tests 30–50 cm). Under half a second of warning at walking
   pace. Use a waterproof ultrasonic (JSN-SR04T class) angled up, or a hooded VL53L1X; log both side by side.
3. Drop the downward drop-off ToF. The cane tip already does it; cane pitch and sweep make range swings larger than a
   curb; a missing return is ambiguous (sun, dark asphalt, water, drop).
4. No LLM narration while walking. One physical button (BLE from the ESP32) = push-to-ask. Deterministic templates
   ("Pole, 1 o'clock, 2 m") for anything automatic. On-device model (4,096-token context) only to parse spoken intent
   or summarise on request. Cloud model: never answer "is it safe to cross" or "is the path clear", JSON with an
   abstain flag, overwrite its distances with LiDAR, say "Looking…" within 1 s. Verified: Ara "just buzzed a lot",
   buzzed when the user's arms moved, returned (Living Blindfully ep. 281).
5. Defer the YOLO detector. ARKit owns the camera, no verified FPS on a 15 Pro, thermal risk. Benchmark Apple
   Magnifier Door/People Detection first as the baseline to beat; Cursor suggests VNDetectHumanRectanglesRequest on
   the ARKit frame as a cheap "person ahead" band.
6. One haptic channel, three states (silent / slow pulse 1–2.5 m / fast pulse <1 m), distance as pulse rate, intensity
   a user setting. Tactile working memory while walking is ~1.6–2 items. Sparse pulses only in the grip, under the
   index finger, ≥80 ms, so they are not confused with cane-tip vibration (4/13 did in the 2026 study, verified).
7. BLE only at runtime; the Wi-Fi AP and MCP server stay on the bench.
8. Silence never means "clear". Distinct pattern on BLE drop, ARKit tracking loss, low battery; then quiet. Dead
   battery = ordinary cane. Motor gate pulled low on brown-out.
9. Reuse wayfinding (VoiceVista / Soundscape Community, BlindSquare); NFC or iBeacon only as personal landmarks.
10. Blindfolded testing yields engineering metrics (false alarms per 100 m, lead distance, latency, thermal), not
    usefulness. Say so in the write-up. Verified: Martinez 2014.
11. If ever distributed: 21 CFR 886.5900 "electronic vision aid", Class I, 510(k)-exempt (verified at LII). A
    personal prototype is outside marketing rules. Describe it as an experimental supplementary aid.

### Code-anchored finding Opus missed (Antigravity, Codex)
Bridge/Depth.swift reduces each 6×8 cell by the MEAN of confident pixels. At 2.5 m a cell is ~36 cm wide, so a 5 cm
pole or branch averages into the background and disappears. Fix natively: filter confidenceMap ≥ medium, crop the
ground plane by camera pitch, reduce the upper corridor into ~9 azimuth columns × 2 height bands reporting the 5th
percentile distance at 10–15 Hz. Send that to the page, not frames. (Verified against the source.)

### Divergent, with this session's verdict
- Where tier 1 lives. Antigravity: invert the order, chest-mounted phone LiDAR is the primary sensor, cane carries only
  a BLE button + IMU. Codex, Cursor, Opus: cane ultrasonic first. Evidence favours the chest: a double-masked RCT of
  31 cane/dog users with a chest camera and two wristbands cut collisions 37% over a month (Pundlik, JAMA Ophthalmol
  2021, verified); chest comfort 4.0 vs cane 3.1, cane sweep drops camera pose accuracy 83%→40% (arXiv 2504.19345,
  verified). The phone path is also faster: it is a Swift change in code we own plus Core Haptics. But LiDAR
  confidence drops in sun and costs phone battery; the ultrasonic is sun-immune and cheap. Verdict: phone corridor
  first (days), cane ultrasonic second as the sun-proof backup, one grip motor for sparse head-height pulses.
- Glass. Antigravity: ultrasonic misses glass beyond ~10–15° incidence. Cursor, Opus: ultrasonic is the glass sensor.
  Neither tested. Glass doors are approached near head-on, the case ultrasonic handles. Bench it on a real door.
- Spatial audio. Antigravity for (AirPods transparency + head motion); Opus against over bone conduction; Codex later.
  Verdict: defer; haptic is the primary channel (22× lower workload than audio for cane users, Martinez 2014, verified).

### Not verified, treat as judgment
WorldScribe "~16% erroneous" (Cursor); phone draw 4.5–6 W and throttling in 15–25 min (Antigravity); "25–75%
non-adoption, 30% abandonment at one year" (Cursor); Antigravity's Cuturi/Dos Santos citations for grip-vibration
masking (the Dos Santos paper is a cane comparison, not a masking study); SmartCane user counts.

### Pitch-ready facts (all verified at source)
- 307 blind adults: 13% hit a head-level obstacle at least monthly, 7% fall at least monthly; only 2% of blind
  respondents never hit one; 86% outdoors, tree branches the majority; 23% of head hits needed medical care; 43%
  changed how they walk, 26% lost confidence; cane vs dog makes no difference (Manduchi & Kurniawan 2011).
- Chest camera + wristband haptics: 37% fewer collisions, n=31, double-masked, home use (JAMA Ophthalmology 2021).
- Blind users want destination help over obstacle avoidance, 4.1 vs 2.4 of 5 (arXiv 2504.19345).
- Haptic beats audio for cane users: ~22× lower NASA-TLX workload (ICCHP 2014).
- Existing aids slow walking and raise workload: BuzzClip workload 3.2→6.2, frustration 2.8→7.5; NOA cut body contacts
  2.9→1.6 but 8/13 called it too heavy (Scientific Reports 2026).

### Build order (consolidated)
Week 1: native depth corridor in Depth.swift + Core Haptics on a chest-mounted phone, walking-gated by CoreMotion;
ESP32 as BLE peripheral with one button, IMU, one upward ultrasonic, one ERM under the index finger, 3-state code,
brown-out-safe. Bench-log ranges in sun, shade, rain, glass, foliage, signposts. Metrics: false alarms per 100 m,
lead distance at 1.2 m/s, latency, mA, thermal.
Week 2: button → push-to-ask: ARKit burst + still photo, template answer within 1 s, optional cloud with the
guardrails; Magnifier Detection Mode on the same route as baseline; one-hour battery/thermal log.
Week 3: fuse (phone agreement raises urgency, never suppresses a cane alert), watchdog patterns, NFC landmark, hour
walk with NASA-TLX, write-up stating usefulness is unvalidated without blind testers. Defer YOLO, segmentation,
downward ToF, fall detection, wayfinding.

## Build step 1 done (2026-11-07, uncommitted in phone-bridge)
`depth.start {hz?, mount?}` now also emits `corridor`: 2 height bands (0.6–1.3 m, 1.3–2.0 m above ground) × 9 columns
over ±30° of straight ahead, each the 5th-percentile horizontal distance in metres or null. Heights and bearings come
from each pixel's 3D position and gravity, so any orientation works; `mount` is the camera height, default 1.3 m.
The 6×8 mean grid, center and min are unchanged. Builds for iOS; not yet installed on the phone (needs the cable).
Next: a page that maps corridor → Core Haptics three-state code, walking-gated by CoreMotion.

## Build sprint 2 (2026-11-07 evening)
- Ahead is its own iOS app (phone-bridge target `Ahead`, bundle com.jonasneves.ahead), installed on the phone; page
  docs/ahead/index.html is bundled at build time. `./install.sh Ahead`, `./testflight.sh Ahead` (needs an App Store
  Connect record; name not chosen yet, "Ahead" alone likely taken).
- Page: cane over BLE (service c0de0001-ca9e-4a11-8e8d-000000000001) fused with LiDAR, push-to-ask (photo + on-device
  labels/OCR, voice question to cloud), NFC landmark tags "landmark:<name>", battery log; CSV columns
  t_s,event,walking,state,dist_m,band,col,src,ms,text,battery_pct,thermal.
- Cloud: https://ahead-ask.jonasneves.workers.dev/ (`worker/` here). Opus 5.5,
  JSON output, refuses crossings, strips distances, "Not sure." on failure. Measured 2.1 s round trip from the Mac.
- Firmware: esp32-labs/cane/ (PlatformIO, ESP32-C3 SuperMini; pins in README). Parts to buy: JSN-SR04T-2.0/3.0,
  Adafruit 1201 coin ERM, 2N2222A, 1N4148, 1 kΩ, 10 kΩ, 100 µF, tactile button. VL53L0X build for today's bench.
- Eval kit: `eval/` here (walk-protocol.md, bench-log.csv, nasa-tlx.md, analyze.py).
- Verified for slides: Manduchi & Kurniawan's own conclusion states "13% of the respondents experienced head-level
  accidents at least once a month" (300 answered; 18% legally blind vs 9% blind). A reviewer doubted it; the text holds.
