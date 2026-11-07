The four-tier design separates computation sensibly, but its first tier is already too ambitious for one developer and three weeks, and the continuous reasoning tier has no demonstrated benefit. **The single most valuable change is to make the first build one narrowly defined, deterministic upper-body obstacle warning, with user-requested descriptions as a separate feature.** Preserve the cane’s ground contact, tactile information, grip, folding and use without power; successful electronics must not degrade those properties.

This is a single-expert, read-only review. I changed no files and ran no builds or tests. Recommendations and proposed acceptance criteria below are **my engineering judgment**; published findings and specifications have linked sources. Product testimonials and forum reports establish individual experiences, not population-wide adoption or abandonment rates.

**Findings ranked by impact**

**1. Define success as useful additional warning during ordinary cane use.**  
[effort: S] [surface: process]

The correct criterion is fewer hazardous body contacts, with tolerable nuisance alerts, effort and walking delay. Detection accuracy alone cannot establish that.

There is evidence that supplementary sensing can help: a randomized, four-week home-use study involving **31 visually impaired participants** found fewer obstacle contacts when a chest-camera system activated its wristband warnings. Participants continued using their habitual mobility aids. This supports investigating supplementary warnings, without establishing that your sensor or feedback design will work. [Pundlik et al., 2021](https://pubmed.ncbi.nlm.nih.gov/34292298/)

Conversely, a **13-participant indoor study** found that NOA reduced body contacts, while BuzzClip did not improve mobility incidents; both slowed walking relative to the cane alone. Different sensing and feedback were bundled together, so this does not isolate audio versus vibration. [Pittet et al., 2026](https://www.nature.com/articles/s41598-026-37578-9)

**My judgment:** start with protruding and hanging obstacles beyond the cane tip’s coverage. Exclude electronic drop-off protection, traffic decisions and fall detection from the first prototype. Without blind-user testing, three weeks can establish technical feasibility and failure behavior, not usability or safety for independent travel.

**2. The owned VL53L0X is an indoor feasibility sensor until outdoor measurements establish otherwise.**  
[effort: M] [surface: hardware]

ST’s specified full-field test reports typical maximum ranges of **0.8 m on an 88%-reflective white target and 0.5 m on a 17%-reflective gray target under overcast-equivalent illumination**. Those conditions are substantially more favorable than many real obstacles: small branches do not fill the field of view. At an assumed walking speed of 1 m/s, 0.5 m provides only 0.5 seconds before reaching the measured surface, before accounting for processing and response. [VL53L0X datasheet, Table 12](https://www.st.com/resource/en/datasheet/vl53l0x.pdf)

| Technology | Relevant limitation | Consequence for this build |
|---|---|---|
| VL53L0X optical ToF | Ambient infrared and weak returns reduce usable range. One measurement covers a nominal 25° field. | Test the actual materials, target sizes and lighting; “up to 2 m” is insufficient. |
| Ultrasound | Can detect transparent barriers, but oblique smooth surfaces can reflect sound away; fabric and curved objects can produce weak echoes. | Complementary sensing, without guaranteed glass detection. WeWALK’s manual explicitly identifies acoustic absorption and weather limitations. |
| iPhone LiDAR/ARKit | Reflective and strongly absorbing surfaces reduce confidence; lighting affects measurements. | Preserve confidence and invalid-depth states. It shares optical failure mechanisms with the cane’s ToF sensor. |
| Stereo depth | Needs correspondence between views. Sunlight can help textured scenes; textureless, reflective and transparent surfaces remain difficult. | New cameras, calibration and processing are unjustified here. |
| Monocular learned depth | Depth is inferred from image content; metric output still requires validation under unfamiliar conditions. | Useful for later comparison, unsuitable as the initial drop-off safeguard. |

Sources: [ST](https://www.st.com/resource/en/datasheet/vl53l0x.pdf), [WeWALK operating limitations](https://wewalk.io/en/support-articles/), [Apple depth confidence](https://developer.apple.com/documentation/arkit/ardepthdata/confidencemap), [RealSense stereo guidance](https://dev.realsenseai.com/docs/tuning-depth-cameras-for-best-performance/), [Apple Depth Pro research](https://github.com/apple-aiml-research/ml-depth-pro).

**Placement is part of sensing accuracy. My judgment:**

- Mount a removable module near the grip or upper fold, clear of the gripping surface and cane joints.
- Make pitch adjustable. Choose it from hand height, target height and warning distance: the central-ray angle is approximately `atan((target height − sensor height) / forward distance)`.
- Map the complete detection volume. A ray aimed at head height farther away may pass below the head at close range.
- Cane swing scans sideways. A side-wall detection can be physically correct and irrelevant to forward travel. An IMU can estimate orientation; it cannot recover obstacles the beam never observed.
- A downward sensor’s missing return could mean a drop, sunlight, dark material, water, excessive distance or sensor failure. Stairs require geometry over space and time. Keep ground-contact detection authoritative.

Commercial designs support adjustable placement: IIT Delhi’s SmartCane mounts on the top fold with an adjustable sensor mechanism. UltraCane uses separate forward and upward ultrasonic coverage and two tactile feedback buttons. These are useful design precedents, not guarantees of complete coverage. [SmartCane](https://assistech.iitd.ernet.in/smartcane.php), [UltraCane manufacturer’s user guide, archived copy](https://manualzilla.com/doc/5844391/user-guide---ultracane)

Rain also requires enclosure, drainage and wet-window testing. An exposed development board and sensor have no established outdoor operating envelope.

**3. Assign responsibility by failure independence as well as latency.**  
[effort: M] [surface: esp32]

**My recommended division:**

| Component | Responsibility |
|---|---|
| ESP32 | Sensor validity, bounded filtering, local warning decisions, motor timing, physical mute/status control, battery monitoring and watchdog. |
| Phone native code | ARKit capture, depth processing, optional detection, timestamps, confidence, lifecycle handling, BLE and feedback arbitration. |
| Web page | Accessible controls, configuration, logs and noncritical interaction. |
| On-device LLM | Optional wording of an already selected, validated observation. |
| Cloud | Explicitly requested interpretation of a captured image. |
| MacBook | Development and controlled recording/replay. Nothing to add to the proposed runtime exclusion. |

Use **BLE**, respecting the stated networking constraint. Keep MCP and Wi-Fi out of the walking warning path. A cloud response must not acquire authority to change warning thresholds or suppress local sensing.

Every phone-derived message should carry a sequence number, capture timestamp, validity and expiry. Expire stale commands locally; do not leave a continuous vibration running because the last packet requested it. Local sensing should continue when the phone disconnects.

Explicitly handle startup, muted, degraded, unavailable and low-battery states. Silence must never be presented as proof of a clear path. A startup motor pulse plus a known-target check is useful, although neither proves complete sensor coverage.

This matters on iOS: ARKit documents interruptions when camera capture becomes unavailable, including backgrounding; Core Haptics can stop because of suspension, audio interruptions or system errors. Keeping the screen awake does not eliminate these cases. [ARKit interruptions](https://developer.apple.com/documentation/arkit/arsessionobserver/sessionwasinterrupted(_:)), [Core Haptics stoppages](https://developer.apple.com/documentation/corehaptics/chhapticengine/stoppedhandler-swift.property)

A fully depleted battery cannot announce its own failure. Low-battery warnings and accessible status checks help, but the fundamental protection remains an ordinary usable cane and no learned dependence on electronic silence.

**4. Begin with one obstacle-warning channel and very few meanings.**  
[effort: M] [surface: hardware]

**My judgment:** use one localized tactile actuator initially, with two readily distinguishable pulse rates for proximity. Let intensity be adjustable for detectability rather than making it another simultaneous information dimension. Add a distinct, infrequent status pattern; provide spoken status on request.

A second motor should encode a useful spatial distinction, such as left/right or upper/forward. Encoding “ESP32 information” versus “phone information” makes the user interpret implementation details. Two motors in one grip also need testing for mechanical coupling.

Research does not establish a universal best modality. A study comparing auditory and tactile navigation found faster auditory performance overall, with the difference reduced by simulated street noise; participants also requested adjustable vibration strength. [Comparing Tactile to Auditory Guidance](https://www.frontiersin.org/journals/human-neuroscience/articles/10.3389/fnhum.2019.00443/full)

For this prototype:

- Use tactile warnings for immediate proximity; short speech for requested identity or status.
- Provide a physical mute control and a shorter-range setting for confined environments.
- Use hysteresis and bounded persistence to prevent threshold chatter. Measure the extra delay these introduce.
- Avoid continuous vibration as the default. Record vibration duty cycle and discomfort.
- Treat phone vibration through clothing as an unverified channel until tested in its actual mount.

Bone conduction keeps the ear canal open, but it still adds sound and attention demands. Transparency-mode earbuds are not equivalent to unaided hearing. **My judgment:** spatial audio deserves a later, optional comparison; neither audio arrangement should be assumed harmless to traffic listening, localization or conversation.

**5. Native ARKit data access is the necessary phone improvement.**  
[effort: M] [surface: phone]

The 6×8 grid can support a coarse proximity experiment. It cannot reliably provide a distance for every detection: a small object may share a cell with background, and a cell minimum may belong to something else.

ARKit exposes a camera image, scene depth and depth-confidence map associated with the frame. Apple’s point-cloud example is a better starting point than opening another camera stream. [ARKit scene-depth example](https://developer.apple.com/documentation/arkit/displaying-a-point-cloud-using-scene-depth)

**My implementation judgment:**

1. Process `ARFrame.capturedImage` and corresponding depth natively.
2. Preserve orientation, crop/resize transforms, camera intrinsics, timestamps and confidence.
3. Undo detector preprocessing before mapping boxes into depth coordinates.
4. Estimate depth from a spatially consistent cluster of valid samples; inspect foreground/background mixing.
5. Return “distance unavailable” when association is ambiguous.
6. Send compact observations to JavaScript rather than full video frames.

Neither the box center nor its minimum depth is universally correct. A person’s box can contain distant background between their limbs; its minimum can belong to an unrelated foreground object. Segmentation can improve association, but it adds work and still needs validation.

Reject low-confidence and stale measurements; do not turn holes in a depth map into navigable space. Smoothed depth also needs moving-object checks because temporal smoothing can preserve obsolete geometry.

**6. Object labels are secondary to obstacle geometry; generic YOLO misses important pedestrian categories.**  
[effort: L] [surface: phone]

The existing Vision classifier produces image classifications. It does not supply general-purpose object boxes. Apple’s live-object example uses a Core ML model through Vision. [Image classification](https://developer.apple.com/documentation/vision/vnclassifyimagerequest), [live object recognition](https://developer.apple.com/documentation/vision/recognizing-objects-in-live-capture)

A small YOLO model exported to Core ML is a reasonable later experiment. YOLOv8n/YOLO11n are possible starting points; current Ultralytics documentation also supports newer models. Pin the selected model and exporter, and verify its license before distribution. Core ML can schedule across CPU, GPU and Neural Engine; export alone does not prove the whole computation runs on the Neural Engine. [Core ML export documentation](https://docs.ultralytics.com/integrations/coreml)

**Performance uncertainty:** I found no directly applicable, sustained one-hour benchmark for **iPhone 15 Pro + ARKit depth + this detector + Bridge + feedback**. The official Ultralytics performance page examined uses an iPhone 17 Pro and distinguishes model-only, preprocessing and live-camera measurements. Those timings cannot establish your phone’s throughput or heat. [Ultralytics benchmark conditions](https://github.com/ultralytics/yolo-ios-app/blob/main/docs/performance.md)

**My judgment:** start detector experiments at 5–10 inferences/second, drop queued frames, and measure capture-to-cue age. This is an initial workload setting, not a promised performance figure.

Useful categories depend on the task:

- **Immediate warning:** any protrusion into the travel corridor, including an unrecognized branch, open window or sign.
- **Requested context:** people, bicycles, vehicles and large movable objects.
- **Destination finding:** doors, entrances, stairs, lifts, counters and signs.
- **Deferred safety research:** curb edges, descending stairs, holes, pedestrian signals and crossing alignment.

Standard COCO detection includes people, bicycles, vehicles and traffic lights, but lacks explicit door, stair, curb, hole and branch classes. A traffic-light box does not identify the relevant pedestrian signal or permission to cross. [COCO detection class list](https://docs.ultralytics.com/datasets/detect/coco/)

Walkable-path segmentation is potentially useful later, but a region labeled “sidewalk” establishes neither clearance nor a safe surface. Monocular depth adds another model before the already available depth sensor has been adequately characterized.

**7. Remove continuous scene reasoning; offer requested descriptions with bounded authority.**  
[effort: S] [surface: phone]

“Speak when the scene changes” is too broad: walking produces constant visual change. Relevance must be selected before generating language.

Apple identifies summarization and classification as suitable Foundation Models tasks, while warning about limitations in logical reasoning and requiring availability checks. The iOS 26 model’s documented context window is 4,096 tokens per session, so an indefinitely appended scene stream is also inappropriate. [Foundation Models capabilities](https://developer.apple.com/documentation/FoundationModels/generating-content-and-performing-tasks-with-foundation-models), [context management](https://developer.apple.com/documentation/technotes/tn3193-managing-the-on-device-foundation-model-s-context-window)

**My judgment:** deterministic templates should come first: “Object ahead,” “Depth unavailable,” or a requested object description. Later, pass the LLM a small structured set of current observations. Keep distances, directions and priority decisions outside generation. JSON-schema compliance establishes structure, not truth.

Use one speech queue with cancellation and interruption. Repetition should depend on a materially changed situation or user request. Allow more detail on demand; brevity alone can omit information the user needs.

For cloud vision:

- Trigger by explicit request, preferably while stationary.
- Capture the image and depth summary together. Preserve unknown regions and coordinate meaning.
- Ask about visible text, objects or scene context.
- Never ask it to authorize crossing, declare a route safe, establish absence of hazards, or replace missing sensor measurements.
- Discard cancelled or superseded answers; identify them as descriptions of a snapshot.
- Treat photographed text as content, never as instructions to the application.

Be My Eyes explicitly prohibits using its service to cross streets and warns against safety-critical reliance on Be My AI. That is a relevant boundary for this design. [Be My Eyes safety terms](https://www.bemyeyes.com/terms-of-service/)

**Latency:** no verified cellular latency applies to the unspecified API, carrier and location. Budget for variable, seconds-scale interaction and outages—my planning assumption—and measure capture-to-first-useful-speech at median and tail latency.

**Cost illustration:** Google lists Gemini 2.5 Pro standard short-context rates of $1.25/million input tokens and $10/million output tokens. Assuming **1,000 billed input tokens including the image and 200 total billed output/reasoning tokens per request**, 100 requests cost about **$0.33**, excluding other services. This is arithmetic under stated assumptions, not an estimate of your actual request size or chosen API. [Google pricing](https://cloud.google.com/model-garden/pricing)

**8. Power, weight and mounting are first-week constraints.**  
[effort: M] [surface: hardware]

The inventory contains one ToF sensor. It does not establish ownership of the extra sensors, motor, motor driver, protected portable battery, charger, physical controls or enclosure needed for the proposed standalone tier.

**My judgment:** acquire only the parts needed for one sensor and one actuator. Drive the motor through an appropriate transistor/driver and protection, rather than directly from GPIO; check motor-induced voltage dips and resets. Keep Wi-Fi disabled during normal BLE operation.

ST lists approximately **19 mA typical active ranging current at 2.8 V**. ESP32 chip sleep figures do not predict an active development board’s consumption, which also includes regulators, LEDs and peripherals. [VL53L0X electrical specifications](https://www.st.com/resource/en/datasheet/vl53l0x.pdf), [ESP32-C3 datasheet](https://documentation.espressif.com/esp32-c3_datasheet_en.html)

For a **hypothetical 1,000 mAh, 3.7 V battery**, 85% usable energy and a **measured** average load of 0.3–0.6 W would imply roughly **5–10 hours**. Neither that load nor that runtime has been verified here. Measure battery-side energy and motor duty cycle.

The iPhone 15 Pro weighs **187 g before its mount**. I would mount it securely on the chest for the first comparison, keeping it removable for deliberate pointing. This avoids adding that mass to the swinging cane, but introduces clothing obstruction, torso-heading and heat-management problems. [Apple specifications](https://support.apple.com/en-sg/111829)

A provisional cane-module target of **under 100 g added mass** is my design budget, not an established comfort threshold. Measure balance and wrist effort as well as mass.

Phone battery drain and heat after an hour remain **unknown**. Record battery percentage points consumed, thermal state, frame age and sustained throughput under the actual mount, brightness, cellular activity and ambient conditions. Apple explicitly recommends testing adverse thermal conditions. [Apple testing guidance](https://help.apple.com/xcode/mac/current/en.lproj/dev308429d42.html)

**9. Reuse existing orientation and interpretation tools before building equivalents.**  
[effort: S] [surface: phone]

GPS, geofences and significant-location changes can provide broad orientation; they cannot establish curb position or crossing alignment. Apple explicitly says iBeacon ranging does not provide precise distance. NFC can identify a known tagged location once found, but does not guide the user to the tag. The proposed NFC use is **my judgment**, contingent on permission, tactile discoverability and maintained tags. [Apple iBeacon guidance](https://developer.apple.com/documentation/corelocation/determining-the-proximity-to-an-ibeacon-device)

Useful precedents and reuse opportunities:

| Existing work | What to reuse or learn |
|---|---|
| Soundscape | Spatial landmarks and user-controlled orientation. Microsoft released its code and retired the original service; inspect maintained successors before relying on it. |
| BlindSquare | Announcement filters, mute, requested location information and deployed beacon infrastructure. Indoor positioning includes installation and maintenance work. |
| Magnifier | Evaluate Door Detection, People Detection and Point and Speak before recreating those interactions. They are app features; do not assume public APIs expose their complete behavior. |
| Seeing AI / Be My Eyes | Existing reading, photo-description and human-assistance workflows provide baselines for whether a custom description feature adds value. |
| Envision | Requested concise scene description followed by questions is a useful interaction precedent. |
| Biped NOA | Wide coverage and spatial warning prioritization warrant study; its multi-camera hardware differs substantially from this phone prototype. |
| Glidance Glide | Target finding, physical guidance and braking address a different device category. Copying its primary-mobility ambition would violate this brief’s scope. |

Sources: [Soundscape transition](https://www.microsoft.com/en-us/research/blog/microsoft-soundscape-new-horizons-with-a-community-driven-approach/), [BlindSquare guide](https://www.blindsquare.com/user-guide/), [Magnifier detection](https://support.apple.com/en-gb/guide/iphone/iph35c335575/27/ios/27), [Point and Speak](https://images.apple.com/mideast/ios/ios-17/a/pdf/iOS_All_New_Features.pdf), [Microsoft’s Seeing AI listing](https://play.google.com/store/apps/details?id=com.microsoft.seeingai), [Be My AI workflow](https://support.bemyeyes.com/hc/en-us/articles/18133134809105-Using-Be-My-AI), [Envision descriptions](https://support.letsenvision.com/hc/en-us/articles/7603823400849-Describe-Scene), [NOA](https://biped.ai/), [Glide FAQ](https://www.glidance.io/frequently-asked-questions).

Apple itself warns against relying on Detection Mode for navigation or situations involving possible injury. Reuse establishes a baseline, not safety certification.

**10. Regulatory status and testing consent need a defined intended use.**  
[effort: M] [surface: process]

**Medical-device status is unresolved for this design.** Jurisdiction and intended purpose matter. The US Class I “cane” provision describes minimal weight-support devices; it does not automatically settle classification of an electronic orientation aid. FDA software guidance and UK MHRA assistive-technology guidance both make intended purpose consequential. [21 CFR 890.3075](https://www.ecfr.gov/current/title-21/chapter-I/subchapter-H/part-890/subpart-D/section-890.3075), [FDA](https://www.fda.gov/medical-devices/digital-health-center-excellence/step-1-software-function-intended-medical-purpose), [MHRA](https://www.gov.uk/government/publications/assistive-technology-definition-and-safe-use/assistive-technology-definition-and-safe-use)

**My judgment:** describe the current work as an experimental supplementary warning aid with a measured operating envelope. Before distributing it or making injury-prevention claims, obtain jurisdiction-specific classification and liability advice. A disclaimer or participant consent should not be treated as eliminating responsibility.

Process images locally and transiently by default. Make recording and cloud transmission explicit; avoid face identification, continuous audio recording and unnecessary location retention. Research recordings need separate consent, access restrictions and a deletion policy. Public-camera rules depend on location and purpose; the UK ICO identifies additional intrusion risks from body-worn capture. [ICO body-worn video guidance](https://ico.org.uk/for-organisations/uk-gdpr-guidance-and-resources/cctv-and-video-surveillance/guidance-on-video-surveillance-including-cctv/additional-considerations-for-technologies-other-than-cctv/body-worn-video-bwv/)

For sighted volunteers, disclose the experimental status, known failures, recording and withdrawal arrangements. Their agreement permits participation under the protocol; it does not validate the device for blind pedestrians.

**What a blind user would tell the author**

These are evidence-based paraphrases. The quoted passages are actual published wording; the surrounding interpretation is mine.

- **Make the extra information worth attending to.** SmartCane’s FAQ directly addresses users finding continuous crowd vibration irritating and confusing, and recommends switching the device off temporarily. The practical lesson is that an accurate proximity alert can still be unwanted. Its reassurance about crowd hazards should not become your safety rule. [SmartCane FAQ](https://smartcane.saksham.org/?page_id=804)

- **Let me reduce unnecessary alerts.** An AppleVis Sunu reviewer initially reported greater confidence after adjusting sonar settings: “I wasn't swamped with unnecessary feedback.” Another user reported unpredictable false detections and missed known obstacles, and returned the device. [Sunu user review and comments](https://www.applevis.com/reviews/sunu-band)

- **A successful first outing is insufficient.** That same initially positive Sunu reviewer later returned the product after charging faults, a replacement unit and casing failure. This is unusually useful longitudinal evidence: sensor usefulness did not overcome reliability problems. [Follow-up on the same review](https://www.applevis.com/reviews/sunu-band)

- **Preserve what I already feel through my cane.** In the NOA/BuzzClip study, participants reported confusing BuzzClip vibration with cane feedback. They appreciated its low weight, while some found NOA bulky; nevertheless, 12 of 13 said they would consider NOA. That was short-term stated preference after indoor testing, not sustained adoption. [Pittet et al.](https://www.nature.com/articles/s41598-026-37578-9)

- **Fewer words are useful only if the remaining information answers my question.** In the same study, participants preferred the conventional deep-learning object-finding version over the generative version, whose indications were judged less adequate. Envision’s requested short description with optional follow-up offers a practical alternative to continuous narration. [Study](https://www.nature.com/articles/s41598-026-37578-9), [Envision](https://support.letsenvision.com/hc/en-us/articles/7603823400849-Describe-Scene)

- **Do not make me change my gait to accommodate your sensors.** In a 2024 Living Blindfully account, Amanda Lacy described returning an Ara after difficult setup, unclear status sounds, ambiguous obstacle vibration and alerts triggered by her arms. Her description of its feedback was: “It just buzzed a lot.” This concerns the version she used, not a verified claim about every subsequent version. [Firsthand account](https://www.livingblindfully.com/lb0281transcript/)

- **Some of us use these aids selectively and value them.** A Miniguide user in a WeWALK discussion reported improved efficiency in obstacle-heavy environments and wanted an integrated device to free a hand. Others questioned cost, durability and usefulness compared with an ordinary cane and smartphone. The £700 complaint in that discussion is a historical individual purchase report, not a current price quote. [User discussion, including manufacturer response](https://www.reddit.com/r/Blind/comments/1iuptdc/the_wewalk_cane_is_not_worth_the_money/)

- **Clothing and ordinary maintenance matter.** AFB’s BuzzClip reviewer found attachment easier on a shirt than a heavy down jacket. Mounting trials must include coats, gloves and normal movement. Social acceptability also includes whether the device looks acceptable to its wearer and whether it requires awkward public interaction; the Sunu comments show appearance can matter, but do not establish a universal preference. [AFB review](https://www.afb.org/aw/full-issue?id=13952), [Sunu comments](https://www.applevis.com/reviews/sunu-band)

- **Training and accessible setup are part of the device.** O&M professionals’ research identifies affordability and technology training as barriers and emphasizes the expertise of clients. SmartCane’s manufacturer describes confidence developing over weeks of regular practice. Neither supports assuming immediate mastery after a brief demonstration. [O&M professionals study](https://pubmed.ncbi.nlm.nih.gov/32643468/), [SmartCane training guidance](https://smartcane.saksham.org/?page_id=804)

Ray provides a further useful precedent: its manual includes both a mode suppressing constant background signals and a trainer connection that reproduces the learner’s feedback. I found insufficient independent longitudinal Ray evidence to claim why users retain or abandon it. [Caretec Ray manual](https://www.caretec.at/downloads/eng/Ray_ba_en_0811.pdf)

I likewise found no basis for a universal vibration-fatigue limit, acceptable device weight, or preference for bone conduction over haptics. Those remain user-dependent questions.

**What I would explicitly not build**

These exclusions are **my scope judgment for the first three weeks**:

- **Downward ToF drop-off protection:** ambiguous missing returns and moving geometry require a separate validation effort.
- **Cane-based fall detection:** a dropped or swung cane is an unreliable proxy for the wearer’s body.
- **Automatic cloud escalation on uncertainty:** uncertainty may reflect poor capture or missing depth; another model cannot be assumed to repair it.
- **Continuous scene narration or an LLM warning controller:** adds latency, workload and unverified assertions before a need is established.
- **Traffic-light crossing instructions:** signal recognition cannot establish safe crossing conditions.
- **A new navigation engine or general indoor positioning system:** infrastructure, map maintenance and localization would consume the schedule.
- **Custom model training, stereo hardware or monocular-depth replacement:** characterize existing sensing first.
- **A rich haptic vocabulary or simultaneous competing warning channels:** test simple signals before adding meanings.
- **Face recognition, sound-classifier safety decisions or unrelated Bridge integrations:** no demonstrated contribution to the first objective.

**Recommended build order for the first three weeks**

The sequence below is **my proposed development plan**, not a claim that it has been validated.

| Week | Work | Required result before expanding |
|---|---|---|
| **1 — Characterize one warning** | Evaluate existing accessibility tools as baselines. Obtain the minimal actuator, driver, controls, battery and mount. Measure the VL53L0X against walls, thin poles, branches, fabric, dark targets and glass at multiple angles, indoors and outdoors. Build local validity checks, two proximity pulse rates, mute, status and low-battery behavior. | An explicit operating envelope; measured warning delay and misses; ordinary cane handling preserved with power off. If outdoor range is inadequate, retain an indoor prototype or make a justified sensor change. |
| **2 — Compare phone depth** | Add BLE status/logging and stale-message handling. Expose native ARKit confidence, timestamps and depth geometry. Compare coarse phone-depth warnings with the standalone sensor using one active warning mode at a time. Exercise screen lock, app switching, calls, disconnects, covered sensors, restarts and depleted power. | No stale warning persistence or false “clear” state; a one-hour battery/thermal record; evidence that phone depth adds useful coverage. |
| **3 — Evaluate and add one requested capability** | Run repeated controlled comparisons against the ordinary cane. Add requested OCR or snapshot description using existing Bridge functions if the warning work is stable. Prototype a small detector only if an observed task requires it and sufficient time remains. | A failure report and repeatable demonstration suitable for later blind-user/O&M evaluation. If the core warning remains unreliable, use the week to correct or reject it. |

Before walking trials, define these measurements:

- Hazard encounters detected early enough, broken down by obstacle, material, lighting, angle and motion.
- Misses, spurious detections, and **real detections that were irrelevant to the route** as separate counts.
- Capture-to-actuator delay, stale-data duration and outage duration.
- Body contacts and near misses separately from normal cane contacts.
- Walking time, stops, deviations, cue interpretation errors, discomfort and workload.
- Alerts per minute, vibration duty cycle, mute usage, energy consumption and thermal state.

For eventual semantic work, useful sources include [SideGuide](https://ytaek-oh.github.io/sideguide) for sidewalk imagery, instance annotations and stereo disparity; [Mapillary Vistas](https://openaccess.thecvf.com/content_ICCV_2017/papers/Neuhold_The_Mapillary_Vistas_ICCV_2017_paper.pdf) for street-scene segmentation; and [VizWiz Quality Issues](https://vizwiz.org/tasks-and-datasets/image-quality-issues/) for photographs actually taken by blind users. They support component evaluation; none establishes safe pedestrian guidance.

Begin physical tests sighted. Any blindfolded trial should use a cleared, level, enclosed area, soft obstacles and an attentive spotter with immediate stopping authority. Exclude roads, real drops, stairs and platform edges. Blindfolded sighted testing can reveal engineering defects, but research explicitly cautions that its results cannot necessarily generalize to blind users. [Travel-aid evaluation review](https://eprints.gla.ac.uk/271318/1/271318.pdf)

At three weeks, the defensible completion state is a characterized supplementary prototype with documented limitations. Independent travel readiness remains unknown until appropriate users and O&M professionals can evaluate it.
