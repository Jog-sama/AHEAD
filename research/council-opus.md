## Verdict

Splitting the design into tiers by latency is sound, and so is keeping the cane's ground contact untouched. The problem is that the design is built for continuous perception. It assumes the user wants a stream of detections, distances and sentences. The published evidence says blind users mostly want two things. The first is a warning for the one hazard class the cane physically misses: head- and chest-height obstacles. The second is help with destinations and the "last few metres" (finding the door, the bus, the entrance), asked for when they want it. They switch off or abandon whatever chatters at them.

**The single change that would most improve the design:** make it silent by default. Tier 1 should handle only head and chest height, using a sensor that actually works in sunlight. Tiers 2–4 should become one push-to-ask query path on the phone (LiDAR plus an answer from a cloud or on-device model), not an always-on YOLO detector feeding an LLM narrator.

---

## Findings, ranked by impact

**1. Build for the gap the cane leaves, not for obstacles in general.** [effort: S] [surface: process]
- In a survey of 10 completely blind, O&M-trained cane users, *destination-focused navigation* averaged 4.1/5 and *obstacle avoidance* 2.4/5. Participants "valued the cane's tactile role and wanted tools that extend, rather than replace, it." ([arXiv 2504.19345](https://arxiv.org/html/2504.19345v1))
- On r/Blind, a commenter said of WeWALK: "the only thing I'm really interested in is the chest above detection." ([r/Blind](https://reddit.birdcat.cafe/r/Blind/comments/1k0khgz/wewalk_smart_cane_2_review_the_ultimate_in))
- The IIT Delhi SmartCane's early version only detected up to knee level, so users "often collided" with raised bars. The fix was above-knee detection at about 3 m. ([TRANSED 2010 paper](https://mrugipanchal.github.io/project/media/Smartcane/Smartcane-TRANSED-2010.pdf), [Deccan Chronicle](https://www.pressreader.com/india/deccan-chronicle/20140401/281741267384676))
- **Implication:** the downward drop-off ToF duplicates what the cane tip already does better. Drop it (see "What I would not build").

**2. The VL53L0X is the wrong part for tier 1 outdoors.** [effort: S] [surface: hardware]
- An ST engineer says sunlight at 940 nm swamps its faint laser. An ST forum answer puts the range at about 2 m indoors but about 50 cm in bright sun. A noon test in California measured about 35 cm. ([Pololu forum](https://forum.pololu.com/t/vl53l0x-and-sunlight/23950), [ST community](https://community.st.com/t5/imaging-sensors/1-can-vl53l-series-sensors-used-in-outdoor-environment-light/m-p/219600), [JetsonHacks](https://jetsonhacks.com/2016/11/29/lidar-on-a-chip-outside-nvidia-jetson-development-kits/amp/))
- At about 1.3 m/s walking pace, 35–50 cm is roughly 0.3 s of warning, which is useless (my judgment).
- WeWALK chose ultrasonic for exactly this job: head-to-waist warning over 80–250 cm, with the vibration delivered through the handle buttons. ([WeWALK manual](https://support.wewalk.io/en/article/wewalk-user-manual/), [EASTIN](https://www.eastin.eu/en/searches/products/detail/database-vlibank/id-G21251))
- Ultrasonic copes better with rain and dust, though mist can cause false echoes. ([NTU-JET](https://journals.ntu.edu.iq/index.php/NTU-JET/article/download/2044/846/11919))
- **Recommendation:** one upward-angled ultrasonic sensor (a waterproof one, JSN-SR04T class) as the primary tier-1 sensor. If you want a second opinion, a hooded VL53L1X; Pololu recommends hooding and the L1X for bright light.
- I found no source that tests glass directly. It is physically plausible that ultrasonic sees glass and IR ToF often misses it, but that is my judgment. Apple says sunlight lowers LiDAR depth confidence, and secondary sources say glass and black surfaces are missed. ([Apple confidenceMap](https://developer.apple.com/documentation/arkit/ardepthdata/confidencemap.md))

**3. Replace "detector + LLM narrator" with push-to-ask.** [effort: M] [surface: phone]
- Interviewed blind and low-vision users of MLLM apps report "frequent overly verbose outputs, omissions of critical details, and hallucinations." ([arXiv 2503.05899](https://ar5iv.labs.arxiv.org/html/2503.05899))
- Be My AI "often buries useful answers in lengthy descriptions." (UMD study, via [root-nation](https://root-nation.com/de/news-de/it-news-de/de-ai-apps-blind-users-umd-study/))
- In a diary study of scene-description apps, satisfaction averaged 2.76/5 and trust 2.43/4. ([arXiv 2403.15604](https://arxiv.org/html/2403.15604v2))
- Tactile working memory fell from about 5 items in the lab to **about 1.6** in realistic dual-task walking. ([review of the vibration-belt study](https://a11y-paradise.onrender.com/reviews/69cc94b7c731a1eca70e0126))
- **Implication:** a "speak when the scene changes" narrator spends attention the user needs for traffic sound and cane feedback. Give the user a physical button (on the ESP32, over BLE) or an AirPods gesture that asks "what's ahead?". Answer in one sentence, with distance from LiDAR.

**4. Mount the phone on the chest, never on the cane.** [effort: S] [surface: hardware]
- Comfort ratings: chest 4.0, head 3.4, cane 3.1. ([arXiv 2504.19345](https://arxiv.org/html/2504.19345v1))
- Cane sweep was the main cause of degraded camera pose. Holding the cane still raised outdoor pose accuracy from 39.5% to 83.2%. (same source)
- The strongest controlled evidence in this field is a chest camera plus two vibrating wristbands. In a double-masked RCT with 31 cane or guide-dog users, it reported about 37% fewer collisions. ([ScienceDaily](https://www.sciencedaily.com/releases/2021/07/210722112958.htm), [EurekAlert](https://www.eurekalert.org/news-releases/466327))
- A chest-mounted phone running LiDAR is therefore a credible *second* head/chest detector. Cane tier 1 must still work without it.

**5. Don't build a YOLO detector in weeks one to three; reuse Apple first.** [effort: L if built] [surface: phone]
- Magnifier's Detection Mode already fuses camera, LiDAR and on-device ML for Door Detection, People Detection and descriptions. ([MacRumors](https://www.macrumors.com/2022/05/17/apple-previews-new-accessibility-features/), [Apple accessibility](https://apple.com/ph/accessibility))
- User views are mixed. One blind AppleVis user called it "hard to use… more like a gimmick." ([AppleVis](https://applevis.com/comment/187240))
- That makes it a good **baseline to beat**, not something to rebuild.
- The only YOLOv8n figure I found for an iPhone 15 Pro is a self-reported "~15+ FPS" with thermal auto-throttling. It is unverified. ([HF model card](https://huggingface-proxy-6ci.pages.dev/divinetribe/yolov8n-oiv7-coreml))
- A native ARKit-frame detector is the largest single piece of new work in the plan.

**6. Tier 3 (on-device LLM) adds latency and risk for little gain.** [effort: S to remove] [surface: phone]
- Apple's on-device model has a 4,096-token context shared between input and output. ([WWDC26 session](https://developer.apple.com/videos/play/wwdc2026/8121/?time=253))
- Image input arrived only recently, and I could not confirm it for iOS 26. ([natashatherobot](https://www.natashatherobot.com/p/apple-foundation-models))
- For turning detector labels into speech, a deterministic template is faster, testable and never hallucinates. An example would be "Person, 2 metres, left" (my judgment).
- Use Foundation Models only to parse spoken *questions* into a JSON intent (find door / read sign / describe).

**7. Bound what the cloud model is allowed to answer.** [effort: S] [surface: cloud]
- Be My AI beta testers saw "basic errors, sometimes with misleading matter-of-fact confidence." ([OpenAI GPT-4V system card](https://openai.relayto.com/e/gpt-4v-ision-pp0hebn6yo9bj/ISn7nyKu2))
- Blind users are "among the most vulnerable to AI errors they cannot readily check." ([ASSETS'24, arXiv 2408.06546](https://arxiv.org/html/2408.06546v1))
- A student pipeline measured about 6.1 s for GPT-based answers versus about 2 s for YOLO. ([ASU poster](https://forge.engineering.asu.edu/wp-content/uploads/2024/07/Kelly-Raines.pdf))
- Cloud setups add "multi-second delays and network jitter." ([OpenGlass, ACL'26 demo](https://aclanthology.org/2026.acl-demo.82.pdf))
- **Rules (my judgment):**
  - Never ask the model "is it safe to cross?" or "is the path clear?". The system prompt should refuse clearance questions.
  - Don't let the model's distances stand. Overwrite them with LiDAR distances, or drop them.
  - Speak something within about 1 s ("Looking…") so the user knows a request is in flight.
  - State that the answer is uncertain when it is.

**8. Haptic vocabulary: three states, one motor, coded by pulse rate.** [effort: S] [surface: esp32]
- Given the 1.6-item working-memory result (finding 3), use: silent / slow pulse (obstacle 1–2.5 m) / fast pulse (under 1 m).
- Cane tapping can mask vibration while walking. ([ThermalCane review](https://a11y-paradise.onrender.com/reviews/69b994c70987446936d5a905))
- So put the motor where the index finger rests, as WeWALK does, and make pulses long, at least 80 ms (my judgment).
- UltraCane users found the vibration "a little strong… ok after a while" and say it "requires specific training." ([vi.ie review](https://vi.ie/product-reviews-ultracane-an-electronic-white-cane-for-the-blind/))
- Make intensity a user setting, not a code.

**9. Audio output: bone conduction for speech, AirPods transparency mode only if you need spatial audio.** [effort: S] [surface: phone]
- Users hesitate to use headphone-based wayfinding because it masks environmental sound. ([Georgia Tech bonephones](https://repository.gatech.edu/entities/publication/d22df9f0-06df-4188-8e2b-f1efcc1567fc), [IEICE](https://ken.ieice.org/ken/paper/201506192b09/eng/))
- Bone conduction localizes worse because of its uneven frequency response. ([IEEE VR 2019](https://unpaywall.org/10.1109%2FVR.2019.8798218))
- Spatial-audio cues therefore lose value on bone conduction.

**10. Fail-safe behaviour.** [effort: S] [surface: esp32]
- Hardware should drive the motor low on brown-out (pull-down on the gate, my judgment).
- Use a distinct "I'm off" pattern at low battery and when BLE drops, then go silent.
- Never emit a "path clear" signal. Silence must mean "no information," not "safe."
- Tier 1 must not depend on BLE.

**11. Weight and grip.** [effort: S] [surface: hardware]
- WeWALK went from 252 g to 190 g between generations and users noticed. First-generation users also broke it in rain. ([AppleVis](https://applevis.com/comment/167138))
- Budget for an added mass of 100 g or less at the grip, and seal it to IP54 (judgment).

**12. Power.** [effort: S] [surface: hardware]
- My estimate, from typical datasheet ranges and not verified:
  - ESP32-C3 on BLE with modem sleep: about 20–40 mA
  - ultrasonic sensor at 10 Hz: about 5–10 mA
  - ERM motor: about 60–80 mA while pulsing, at a low duty cycle
- A 500 mAh LiPo should give roughly 8–12 h. Don't run the Wi-Fi AP or the MCP server at runtime.
- **Phone:** I found no measured numbers for an hour of ARKit sceneDepth plus Neural Engine. Thermal throttling is widely reported. ([Apple forums](https://developer.apple.com/forums/thread/689458), [Unity thermal sample](https://docs.unity3d.com/Packages/com.unity.xr.arfoundation@6.4/manual/samples/arkit/thermal-state.html))
- Run ARKit only during a query or a short burst, and log `ProcessInfo.thermalState`.

**13. Wayfinding: reuse existing apps, don't build it.** [effort: S] [surface: phone]
- Soundscape's MIT-licensed code lives on in VoiceVista and Soundscape Community. ([VoiceVista App Store](https://apps.apple.com/app/6450388413), [Double Tap](https://doubletaponair.com/soundscape-community-brings-popular-navigation-app-back/))
- One cheap, distinctive addition: NFC or iBeacon tags at the user's own places (front door, bus stop pole), read by the phone (judgment).

**14. Regulation and privacy.** [effort: S] [surface: process]
- In the US, mechanical canes are Class I and exempt under 21 CFR 890.3075. Battery-powered electronic vision aids are Class I under 886.5900. ([FindLaw 890.3075](https://codes.findlaw.com/cfr/title-21-food-and-drugs/cfr-sect-21-890-3075/), [Cornell 886.5905 context](https://www.law.cornell.edu/cfr/text/21/886.5905))
- A personal, undistributed prototype is outside the scope of marketing rules. If you distribute it, re-check FDA and EU MDR (judgment).
- **Privacy (judgment):** recording sessions for training captures bystanders. Blur faces before storing, keep recordings local, and use only on-request photos at runtime.

**15. Blindfolded testing is biased and unsafe without controls.** [effort: S] [surface: process]
- Blindfolded sighted participants are "insufficient substitutes for expert cane users." ([Santos et al., UNESP](https://repositorio.unesp.br/entities/publication/2ac7aa54-3c39-4ebb-af3d-238696a7ecb8/full))
- Martinez/Koester recommend mixing blind and blindfolded testers and using NASA-TLX. ([slides](https://cvhci.iar.kit.edu/~dkoester/publications/martinezICCHP2014tlx-slides.pdf))
- The author cannot validate *usefulness*, only *engineering metrics*. Say so in any write-up.

---

## What a blind user would tell the author

- **"The cane already finds the ground. Find what it can't."** Users prize the cane's tactile role and want tools that extend it ([arXiv 2504.19345](https://arxiv.org/html/2504.19345v1)). The feature people single out on WeWALK is above-chest detection ([r/Blind](https://reddit.birdcat.cafe/r/Blind/comments/1k0khgz/wewalk_smart_cane_2_review_the_ultimate_in)). WeWALK's own manual says it cannot detect stairs, curbs or holes; the cane does that ([WeWALK manual](https://support.wewalk.io/en/article/wewalk-user-manual/)).
- **"My problem is getting *there*, not dodging things."** "There are so many things to trip on before I even get to the door." "I've been left behind because I didn't realize the bus had pulled up behind another." "It's like a maze with no signs I can read." (P10, P4, P7, [arXiv 2504.19345](https://arxiv.org/html/2504.19345v1))
- **"Don't make me put on a harness *and* grab my cane."** That was AppleVis users' reaction to Biped NOA, along with: current tech "isn't accurate enough that a cane or something touching the ground wouldn't still be required" ([AppleVis](https://applevis.com/comment/171381)). A reviewer of Strap's chest-worn Ara: "I couldn't recommend this product" ([AppleVis](https://applevis.com/comment/170111)).
- **"Shut up unless I ask, and get to the point."** Verbose, buried answers and confident errors are the top AI complaints ([arXiv 2503.05899](https://ar5iv.labs.arxiv.org/html/2503.05899); [GPT-4V card](https://openai.relayto.com/e/gpt-4v-ision-pp0hebn6yo9bj/ISn7nyKu2)).
- **"Don't block my ears."** Traffic sound is the user's primary sensor ([Georgia Tech](https://repository.gatech.edu/entities/publication/d22df9f0-06df-4188-8e2b-f1efcc1567fc)).
- **"It has to survive rain and not die on me."** On WeWALK gen 1: "broken… a few times because I had to use it in the rain." On gen 1's design: it "felt like it hadn't been developed with any input from anyone blind" ([AppleVis](https://applevis.com/comment/167138)). Sunu Band was returned over battery failure, and an app update "made the band useless" ([AppleVis Sunu review](https://www.applevis.com/reviews/sunu-band), [Product Hunt](https://www.producthunt.com/posts/sunu-band)).
- **"Don't make me need a sighted person to set it up."** ([Product Hunt](https://www.producthunt.com/posts/sunu-band))
- **"Cost and subscriptions matter."** WeWALK's GPT feature moved to a monthly fee ([AppleVis](https://applevis.com/comment/167159)). About 40% of users fund assistive tech out of pocket ([PMC review](https://pmc.ncbi.nlm.nih.gov/articles/PMC12832816/)).
- **"Don't draw attention to me."** Devices that make a disability visible are less likely to be kept long-term (same PMC review).
- **"Training matters more than features."** Many devices ship without training ([PMC](https://pmc.ncbi.nlm.nih.gov/articles/PMC12832816/)). Early users misread electronic travel aid feedback ([Taylor & Francis abstract](https://informahealthcare.com/doi/abs/10.1080/17483107.2020.1785565)).

---

## What I would explicitly NOT build

- **The downward drop-off ToF.** It duplicates the cane tip, is unreliable on dark asphalt and in sun, and every curb would produce a false alarm.
- **A real-time YOLO detector (for now).** It is L effort, a thermal burden, and largely covered by Magnifier Detection Mode. Revisit only if the push-to-ask logs show a specific class that is missed constantly.
- **An LLM narrator that speaks on scene change.** It is the feature users mute, for the cognitive-load reasons in finding 3.
- **Spatial-audio object sonification over bone conduction.** Localization is poor and it competes with traffic sound.
- **A second haptic channel or a multi-pattern vocabulary.** Working memory under walking load is about 1.6 items.
- **Fall detection on the cane.** iPhone and Apple Watch already do it (judgment).
- **Cane-mounted camera or phone.** Swing ruins pose and blur ([arXiv 2504.19345](https://arxiv.org/html/2504.19345v1)).
- **Turn-by-turn wayfinding.** Use VoiceVista or Soundscape.
- **Any "all clear" output, from any tier.**
- **The Wi-Fi AP or MCP server at runtime.** Keep it for bench debugging only.

---

## Build order, weeks 1–3

**Week 1: tier 1 standalone, outdoors.**
- One waterproof ultrasonic sensor angled up about 15–25° from the grip, plus a hooded VL53L1X if you have one, logged side by side. ESP32-C3 on BLE only, one ERM motor under the index finger, the three-state pulse code, brown-out-safe motor drive, and a low-battery pattern.
- Bench-log raw ranges at 10 Hz in sun, shade, rain, against glass, foliage, signposts, and the underside of truck tailgates.
- **Metrics:**
  - warning lead time at 1.3 m/s
  - false alarms per minute on a clear sidewalk
  - misses on a set of foam head-height targets
  - mA draw
- Testing is blindfolded only with a sighted spotter, on a closed course, with soft targets.

**Week 2: push-to-ask on a chest-mounted phone.**
- A grip button sends a BLE notify to Bridge. Bridge runs a short ARKit burst and returns the minimum distance in the 6×8 grid's upper rows ("obstacle at head height, 1.8 m, slightly left"). It takes a still photo and speaks within 1 s.
- Optionally send the photo plus the depth summary to the cloud VLM. Use a constrained prompt: describe, read signs, locate the door or entrance; refuse clearance questions; overwrite distances with LiDAR values.
- Log latency to first audio, total latency, thermal state, and battery percentage per hour.
- Run Magnifier Detection Mode on the same routes as a baseline.

**Week 3: fuse and harden.**
- Use the phone's LiDAR as an optional second opinion for tier 1 (agreement raises urgency; LiDAR alone never suppresses a cane alert).
- Use Foundation Models only to parse spoken intents.
- Add NFC or iBeacon personal landmarks if time allows.
- Run an hour-long endurance walk and record NASA-TLX for the blindfolded tester.
- Write up results, stating plainly that usefulness is unvalidated without blind testers. Plan the first contact with an O&M instructor or a local blind users' group as the next milestone, before building a detector.

**Datasets, if you later train anything:**
- Pedestrian-signal images (809, red/green) ([Mendeley](https://data.mendeley.com/datasets/9tm59d3nsn))
- Community crosswalk and signal sets of uneven quality ([Roboflow blind_assist1](https://universe.roboflow.com/markus-x-cgbeg/blind_assist1))

I found no reliable benchmark for head-height obstacles, so the week-1 logs would be the best data you have.

**Not verified, so treat as judgment:**
- YOLO frame rate and thermal behaviour on the iPhone 15 Pro
- the ESP32 power estimates
- how ultrasonic and ToF each behave on glass
- whether the current on-device Foundation Model accepts images
