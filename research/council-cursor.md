Opening `council-brief.md` and following its review instructions.
Gathering published evidence across the brief's ten dimensions via web research.
# Design review: AI-assisted cane (author hardware stack)

## 1. Verdict

The **four-tier split** (reflex on MCU → fused perception on phone → sparse on-device language → on-request cloud) matches how ETAs that survived field use and the adoption literature describe **latency, cognitive load, and trust** (e.g. hybrid reflex &lt;50 ms vs cloud 1–2 s: [hackernoon hybrid vision assistant](https://hackernoon.com/building-a-hybrid-mobile-ai-vision-assistant-with-litert-gemini-nano-and-vertex-ai); VIS4ION ~30 fps / ~100 ms obstacle path vs ~1 Hz VLM: [arXiv:2311.13939](https://doi.org/10.48550/arxiv.2311.13939)). The **single highest-leverage change** is to **shrink tier 2 and defer tier 3–4**: ship **one** grip haptic channel driven by ESP32 fusion (ToF + ultrasonic + swing gating), use the phone **first** for **ARKit LiDAR proximity haptics only** (no live YOLO, no scene LLM), and treat Magnifier / People / Door APIs and optional cloud as **explicit user actions**, not background narration ([AFB on cacophony](https://afb.org/aw/23/10/18078); WorldScribe erroneous descriptions ~16%: [arXiv:2408.06627](https://arxiv.org/pdf/2408.06627v1.pdf)).

---

## 2. Findings (ranked by impact)

**F1** [effort: S] [surface: esp32 | process] **Never let cloud or speech sit on the safety path.** Reflex must complete on the grip motor with no BLE/Wi‑Fi/cellular in the loop; phone↔board link for walks must be **BLE** given your Wi‑Fi/internet constraint. Cloud vision over LTE is **hundreds of ms to seconds** and fails in dead zones—fine for “what is this?” not for last-metre dodge. [VIS4ION](https://doi.org/10.48550/arxiv.2311.13939); [OpenGlass ~993 ms median](https://aclanthology.org/2026.acl-demo.82/)

**F2** [effort: M] [surface: hardware | esp32] **Your tier-1 sensor story must match what you wire:** glass and many outdoor cases break **VL53L0X alone** (sun: datasheet ~50–80 cm outdoor; mirror/glass: [ST community](https://stcommunity.st.com/t5/imaging-sensors/is-it-possible-to-detect-glass-walls-in-general-environments/td-p/151204); comparison: [BugbotLab](https://www.bugbotlab.com/learn/distance-sensors-compared/)). The design’s **ultrasonic-for-glass** is right but **not yet on the BOM**—without it, do not market glass/overhead confidence. **Judgment:** add downward ToF + ultrasonic + IMU swing gating before promising drop-off/glass.

**F3** [effort: S] [surface: process | phone] **Abandonment is driven by false alarms and fatigue as much as by missing features.** ETA literature cites **~25–75% non-adoption** and **~30% abandonment at one year** ([TAD-221502](https://doi.org/10.3233/TAD-221502)); WeWALK/Sunu/BSVSB threads describe **beeping at nothing → ignoring real hits** ([Reddit WeWALK value](https://www.reddit.com/r/Blind/comments/1iuptdc/the_wewalk_cane_is_not_worth_the_money/); [BSVSB Sunu](https://www.bsvsb.org/hilfe-information/beratung/testberichte/hindernismelder)). **Filter aggressively** (sweep-phase gating: [elex.6.794](https://doi.org/10.1587/elex.6.794); filtered FP ~0.14%: [PMC8234202](https://pmc.ncbi.nlm.nih.gov/articles/PMC8234202/)).

**F4** [effort: S] [surface: phone] **Keep the haptic/audio vocabulary tiny and trained.** Distance → **pulse rate**; sector → **tactor location** beats intensity-only ([Frontiers haptic nav](https://www.frontiersin.org/journals/ict/articles/10.3389/fict.2017.00023/full)); multimodal nav **raised cognitive load** vs cane alone ([Sound-of-Vision PMC7602506](https://pmc.ncbi.nlm.nih.gov/articles/PMC7602506/)). **One motor on the grip** until users can map ≤4 distance bins; second channel on the phone only after tier 1 is trusted.

**F5** [effort: M] [surface: phone] **Defer real-time YOLO + custom detector.** Feasible on 15 Pro in bursts ([Ultralytics Core ML notes](https://docs.ultralytics.com/integrations/coreml)), but sustained ARKit + ANE **throttles** ([YOLOv5 thermal issue](https://github.com/ultralytics/yolov5/issues/1044)) and camera is **already owned by ARKit** in your stack. **Week-one phone win:** fuse **6×8 LiDAR grid** + `VNDetectHumanRectanglesRequest` (full body, iOS 15+) for people/poles—not 80-class COCO at 30 Hz ([WWDC21 Vision](https://developer.apple.com/videos/play/wwdc2021/10040/)).

**F6** [effort: S] [surface: phone | cloud] **Tier-3 “one sentence on scene change” is higher risk than it sounds.** BLV users disagree on verbosity; WorldScribe had **~16% erroneous** descriptions ([2408.06627](https://arxiv.org/pdf/2408.06627v1.pdf)); VQA hallucinations are trusted and blamed on the user ([CHI 2025 BLV VQA](https://dl.acm.org/doi/full/10.1145/3746059.3747597)). **Judgment:** no autonomous scene LLM in v0; use **AVSpeech** only for user-triggered Magnifier-style tasks or NFC/POI labels.

**F7** [effort: S] [surface: process] **You cannot substitute for O&M + blind cohorts with blindfolded testing alone.** Blind users walk faster; electronic aids **slow** ambulation vs white cane; blindfolded groups are weak proxies ([s10209-020-00712-z](https://doi.org/10.1007/s10209-020-00712-z)). Blindfolded work is still useful for **false-alarm rate / hour** and **tier-1 latency** on a fixed course—document the gap in any write-up.

**F8** [effort: S] [surface: process | hardware] **Position as complement to white-cane contact, not replacement.** COMS qualitative work warns smart canes may **reduce tactile engagement** and encourage **audio overreliance** ([Taylor & Francis 2026](https://www.tandfonline.com/doi/full/10.1080/17483107.2026.2626466)); IIT SmartCane and WeWALK marketing use the same frame ([IIT SmartCane](https://assistech.iitd.ac.in/smartcane.php)). **Hard fail-safe:** dead battery = ordinary cane.

**F9** [effort: M] [surface: esp32] **Power: run tier 1 without Wi‑Fi AP during walks.** ESP32-C3 + BLE modem-sleep ~order 27 mA average on similar boards ([Seeed low power PDF](https://files.seeedstudio.com/wiki/Seeed-Studio-XIAO-ESP32/Low_Power_Consumption.pdf)); intermittent ERM pulses are cheap vs always-on radio ([IISTJ vibration budget](https://www.iistj.org/publishedpapers/120336_PAPER.pdf)). **Judgment:** MCP/AP only for bench config; BLE + light sleep on the street.

**F10** [effort: L] [surface: phone] **Do not rebuild full wayfinding in three weeks.** Reuse **BlindSquare** + beacons ([CNIB model](https://cnib-accesslabs.ca/inclusive-built-environment/navigation-wayfinding/blindsquare/)), **Soundscape community** audio landmarks ([soundscape-community](https://github.com/soundscape-community/soundscape)), **NFC at known places** ([PERCEPT-II](https://doi.org/10.1109/embc.2014.6944417)). Cane MCU should not own GPS turn-by-turn.

**F11** [effort: S] [surface: process] **Cost, stigma, training predict non-use.** HCII 2022: **~66% cite cost**; only **~19% tried** a smart cane ([hcii2022 PDF](https://yiwenmollyw.github.io/assets/pdf/hcii2022.pdf)); stigma/aesthetics ([TAD 2020](https://www.tandfonline.com/doi/full/10.1080/17483107.2020.1768308)). A hobby prototype should avoid **medical/ETA marketing** unless you accept FDA/CE path ([FDA KHY cane class](https://www.accessdata.fda.gov/scripts/cdrh/cfdocs/cfPCD/classification.cfm?ID=KHY); [Soundscape disclaimer](https://www.microsoft.com/en-us/research/product/soundscape/)).

**F12** [effort: S] [surface: phone] **Camera-forward cane inherits social risk.** BLV bystanders want **parity in knowing when recorded** ([arXiv:2210.12232](https://arxiv.org/html/2210.12232v1)); avoid faces/attribute narration in public ([CHI PVI concerns](https://dl.acm.org/doi/full/10.1145/3506857)).

**F13** [effort: M] [surface: hardware] **Sensor placement:** literature uses **multi-angle ultrasonic fans** (e.g. 38°/58°/85° + drop-off ~27°: [ICORR 2013 AAWC](https://vigir.missouri.edu/~gdesouza/Research/Conference_CDs/IEEE_ICORR_2013/contents/papers/117.pdf)) and **cane-tilt compensation** ([ACM 3308561](https://doi.org/10.1145/3308561.3354627)). **Judgment:** one upward VL53L0X on a fixed mount will mis-aim across users unless IMU-tilt-compensated in firmware.

**F14** [effort: S] [surface: phone] **Reuse Apple primitives before custom CV:** **Door Detection**, **People**, **Point & Speak** in Magnifier—Apple positions these as **not** for high-risk navigation ([Apple support](https://support.apple.com/guide/iphone/detect-doors-people-and-furniture-around-you-iph35c335575/ios))—same liability tier you want for v0.

**F15** [effort: L] [surface: phone] **Adjacent products already own “agent + scene”:** Glide (~$1,499 + subscription: [glidance.io](https://www.glidance.io/product)); NOA complements cane with spatial audio + phone GPS ([biped.ai FAQ](https://www.biped.ai/faq/)). **Copy architecture (complement, tiered latency), not feature parity.**

---

### Dimension coverage (brief §22–32)

| # | Topic | Summary |
|---|--------|---------|
| 1 | User/O&M evidence | See §3; adoption/abandonment + alarm fatigue above. |
| 2 | Sensor physics | ToF sun/glass limits; ultrasonic rain false echoes; multi-angle + swing gating; UltraCane overhead vs ground ([659794](https://www.tandfonline.com/doi/abs/10.1080/10400435.2012.659794)). |
| 3 | Feedback | Pulse-rate distance, preserve environmental hearing; bone conduction/transparency earphones align with [EJ765543](https://files.eric.ed.gov/fulltext/EJ765543.pdf). |
| 4 | Phone perception | LiDAR grid + Vision humans first; OIV7/YOLO later; walkable segmentation conservative bias ([arXiv:2607.21137](https://arxiv.org/html/2607.21137)). |
| 5 | Language/reasoning | On-device LLM only user-triggered; cloud optional; bound hallucination ([3746059](https://dl.acm.org/doi/full/10.1145/3746059.3747597)). |
| 6 | Wayfinding | Integrate BlindSquare/Soundscape/NFC; not cane-ESP32 core. |
| 7 | Safety/ethics | Fail-open; wellness labeling; privacy; informed consent for non-BLV testers—document limits. |
| 8 | Hardware/power | ESP32+BLE+sensors+motor viable with sleep; phone 1 h AR+NE needs duty-cycle management (**judgment**). |
| 9 | Process | Blindfold metrics: FP/h, detection by height, speed; [Access 2024 VR eval](https://doi.org/10.1109/access.2024.3471177). |
| 10 | Adjacent work | IIT SmartCane ≈ your tier 1; Magnifier; Glide/NOA for positioning—not rebuild. |

Where web fetch was blocked in this environment, findings above rely on subagent-sourced URLs and **judgment** where noted.

---

## 3. What a blind user would tell the author

*Synthesized from studies, O&M interviews, and product complaints—not a single user.*

“I already have a white cane that **never needs charging** and tells me the ground truth. If your thing beeps or buzzes when nothing’s there, I’ll **turn it off** and you’ve wasted my money—that’s what people say about WeWALK and Sunu when the sensor lies ([AppleVis WeWALK thread](https://mail.applevis.com/forum/assistive-technology/any-experience-wewalk); [Sunu Reddit](https://www.reddit.com/r/Blind/comments/9jzfhr/another_day_with_sunu_its_not_looking_good/)). **Overhead branches and storefront glass** are why I’d try an electronic aid at all—the cane doesn’t catch those—but only if it’s **faster than my ears** and doesn’t fight them. I need **short, rare** audio; if you narrate the sidewalk I can’t hear cars ([Cal Poly ETA design](https://digitalcommons.calpoly.edu/cgi/viewcontent.cgi?article=1019&context=meng_fac)). **£700+ for GPS that points the wrong way** isn’t mobility, it’s frustration ([Vision Ireland WeWALK review](https://vi.ie/review-of-the-wewalk-smart-cane-2/)). In busy streets, **continuous buzz is confusion**—trainers in India said calm environments only ([W4A 2024](https://dl.acm.org/doi/full/10.1145/3677846.3677847)). Don’t ask me to **trust an AI** to say it’s safe to cross; I’ll use my cane skills and maybe **BlindSquare** for the intersection I already know ([blindsquare.com/about](https://www.blindsquare.com/about/)). If the battery dies mid-block, I must still have **a normal cane**—no heavier grip, no wobble. And if I’m on the bus, I don’t want you **filming strangers** without a way they know ([arXiv:2210.12232](https://arxiv.org/html/2210.12232v1)). Show O&M instructors that this **trains with** long-cane technique, not **instead of** it ([COMS 2026](https://www.tandfonline.com/doi/full/10.1080/17483107.2026.2626466)).”

---

## 4. What to explicitly NOT build (first pass)

| Do not build | Why |
|--------------|-----|
| Continuous scene narration / on-device LLM tier | Load + error rate ([PMC7602506](https://pmc.ncbi.nlm.nih.gov/articles/PMC7602506/); [WorldScribe](https://arxiv.org/pdf/2408.06627v1.pdf)) |
| Real-time 80-class YOLO + live camera stream in Bridge v0 | ARKit lock-in, thermal, weeks of native work |
| Cloud obstacle reflex | Latency, dead zones ([VIS4ION](https://doi.org/10.48550/arxiv.2311.13939)) |
| Cane-mounted Wi‑Fi AP while walking + phone internet | Your constraint; BLE only |
| Full turn-by-turn / indoor positioning on ESP32 | BlindSquare/Soundscape/NFC lanes exist |
| Drop-off/stair certainty from one VL53L0X | Ground ≠ UltraCane parity without downward array ([s10209-020-00712-z](https://doi.org/10.1007/s10209-020-00712-z)) |
| “Smart cane replaces contact” positioning | O&M + liability ([COMS 2026](https://www.tandfonline.com/doi/full/10.1080/17483107.2026.2626466)) |
| Glass detection with ToF only | Documented failure mode ([BugbotLab](https://www.bugbotlab.com/learn/distance-sensors-compared/)) |
| Second grip motor + spatial audio + speech concurrently | &lt;40% prefer all modalities on ([PMC11612587](https://pmc.ncbi.nlm.nih.gov/articles/PMC11612587/)) |

---

## 5. Recommended build order (first three weeks)

**Week 1 — Tier 1 standalone (ESP32 only)**  
- Mount **upward VL53L0X**; procure **HC-SR04 or equivalent** for glass-forward cone; **IMU** for swing phase—**suppress** ranging during ground tap ([elex.6.794](https://doi.org/10.1587/elex.6.794)).  
- **One ERM** in grip: 4 distance bands → pulse rate ([Frontiers](https://www.frontiersin.org/journals/ict/articles/10.3389/fict.2017.00023/full)).  
- No Wi‑Fi on street; BLE GATT for logging only.  
- **Test:** blindfolded fixed course; log **false positives/h**, reaction time, weight with dead battery = plain cane.

**Week 2 — Phone LiDAR haptics (minimal Bridge)**  
- Stream **6×8 LiDAR**; map **min/center distance** to **Core Haptics** on second channel OR same rhythm via AirPods haptics—**no speech**.  
- Optional: **Vision human rectangles** on ARKit frame at low rate for “person ahead” band.  
- **Do not** start YOLO training or cloud tier.  
- **Test:** compare ESP32-only vs ESP32+LiDAR for overhead vs wide obstacles; phone thermal after 30 min walk (**judgment**: target &lt; sustained AR session).

**Week 3 — Integration, reuse, escalation shell**  
- BLE: sync config, session log, **button → “describe”** using **still photo + Magnifier/Door/Point & Speak** or one-shot cloud vision **on user hold**—never auto.  
- NFC tag at home/desk for mode preset ([PERCEPT-II pattern](https://doi.org/10.1109/embc.2014.6944417)).  
- Write **non-navigation wellness disclaimer** ([Soundscape model](https://www.microsoft.com/en-us/research/product/soundscape/)).  
- **Defer:** Core ML YOLO, on-device Foundation Models scene tier, walkable segmentation, downward ToF unless week-1 ground false alarms are measured.

**After week 3 (if signal is good):** add ultrasonic/downward stack; then nano YOLO on ARKit frames; only then sparse on-device captions with **abstain** when uncertain ([OpenGlass](https://aclanthology.org/2026.acl-demo.82/)).

---

*Read-only review per [council-brief.md](file:///Users/jonasneves/.claude/jobs/df152b72/tmp/council-empty/council-brief.md); no repository files modified.*
