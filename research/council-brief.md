# Brief: design review of an AI-assisted cane for a blind pedestrian, built from hardware the author already owns

You are reviewing a design on your own, as a single expert. Read-only: do NOT modify any files, do not run build commands or test suites. Research the open web where you can; cite every source you use with a URL. Where you cannot verify a claim online, mark it as your own judgment.

## The decision this feeds

The author has a few weeks, one developer, and an existing stack. They are deciding (a) which sensing and feedback to build first, (b) what the division of labour between the cane's microcontroller, the phone and the cloud should be, and (c) what to leave out. They cannot interview blind users or orientation-and-mobility (O&M) instructors before building, so one of your jobs is to stand in for that interview with published evidence: user studies, reviews, forum threads, product post-mortems and complaints about existing electronic travel aids and smart canes (WeWALK, UltraCane, Sunu Band, BuzzClip, Miniguide, Ray, Smart Cane from IIT Delhi, Glidance Glide, Biped NOA, Envision glasses, Seeing AI, Be My Eyes, Ara by Strap Technologies, and others you find).

## The hardware and software already in hand

- ESP32-C3 boards running a Wi-Fi access point and an MCP tool server; a VL53L0X time-of-flight sensor wired to one of them; GPIO, ADC, an onboard LED. BLE is available on the C3.
- An iPhone 15 Pro running "Bridge", the author's own app: a web view with a JavaScript bridge to native features. Already working from a web page: LiDAR depth through ARKit as a 6×8 grid of distances at up to 30 Hz with centre and minimum distance in metres; a still-image Vision classifier, OCR, face/pose/barcode detection on a still image; the camera (still photos, lens choice, torch); Core Haptics with intensity and sharpness, patterns and a live continuous vibration; CoreMotion; AirPods head motion; pedometer and activity (walking/standing); proximity sensor; Core Location, significant-location, geofenced regions and iBeacon ranging; NFC read and write; on-device speech transcription; AVSpeechSynthesizer text-to-speech; on-device sound classification (~300 classes); Apple Foundation Models (iOS 26 on-device LLM) with JSON-schema output and streaming; Translation; Natural Language embeddings; Bluetooth LE central (scan/connect/read/write/subscribe); UDP/TCP sockets, Bonjour, phone-to-phone peer sessions; local and push notifications; Live Activities; HomeKit; Face ID; keep-awake and brightness. Camera frames are not yet exposed to the page as a live stream for inference; a native real-time detector would be new work.
- A MacBook (Apple silicon) for development.
- Access to a frontier LLM API (vision-capable) over the phone's cellular connection.
- Constraints the design must respect: the phone cannot be on the ESP32's Wi-Fi and the internet at the same time, so any phone↔board link that coexists with cloud access must be BLE. ARKit holds the camera, so LiDAR depth and the page's own getUserMedia cannot run together; a native detector would have to use ARKit's frame. Hard constraint: the white cane's ground contact must never be replaced; electronics may only add, and the device must be safe when its battery dies.

## The author's current working design (critique it, do not assume it is right)

Four tiers by latency: (1) a reflex tier on the ESP32 with upward-angled ToF for head/chest-height obstacles, downward ToF for drop-offs, an ultrasonic for glass, an IMU for swing phase and falls, driving a vibration motor in the grip directly; (2) a perception tier on the phone fusing LiDAR depth with a real-time object detector (YOLO-class, Core ML, Neural Engine) so each detection carries a distance, output as spatial-audio cues or a second haptic channel; (3) a reasoning tier using the on-device LLM to speak one short sentence only when the scene changes; (4) an escalation tier that sends a photo plus a depth summary to a cloud vision LLM on request or when the local model is unsure. The MacBook is used only for recording sessions and training/converting models, never at runtime. Output audio through bone conduction or transparency-mode earbuds, never occluding the ears. Build order: tier 1 standalone first, then LiDAR haptics, then the detector, then cloud.

## Dimensions to cover (every one; say "nothing to add" where that is honest)

1. What blind users and O&M instructors actually report wanting, using, and abandoning in electronic travel aids: what features were kept, what was switched off, why devices were abandoned, what they say about false alarms, vibration fatigue, audio occlusion, speech verbosity, social acceptability, weight, battery, cost. Cite studies and user reviews. This is the stand-in for the user interview: be concrete and quote where you can.
2. Sensor physics and placement: ToF vs ultrasonic vs LiDAR vs stereo/mono depth in sunlight, rain, on glass, on dark/absorbent surfaces, for drop-offs and stairs; cane swing compensation; where sensors go on a cane; angles; what commercial canes chose and why.
3. Feedback modality: haptic vocabularies that people learn fast, one vs two motors, pulse rate vs intensity coding, spatial audio vs speech vs tones, bone conduction, what the research says about cognitive load while walking.
4. Phone perception: object detection on iPhone (YOLO variants in Core ML, Apple's own Vision requests, real-time performance and thermal/battery on an iPhone 15 Pro), fusing boxes with LiDAR depth, which classes actually matter to a pedestrian, monocular depth models, segmentation of the walkable path, crossing/traffic-light detection, door and stair detection.
5. Language and reasoning: using a small on-device LLM to summarise a scene stream; when to speak; how commercial products handle verbosity; the role of a cloud vision LLM, its latency over cellular, cost, and what it should and should not be asked; hallucination risk in safety-relevant answers and how to bound it.
6. Wayfinding and orientation: GPS/precision locating, geofences and beacons, NFC tags at known places, indoor positioning, what has worked (e.g. Soundscape, BlindSquare, Microsoft Soundscape's open-sourcing) and whether the cane should do any of it.
7. Safety, failure modes and ethics: fail-safe behaviour, what happens when the battery dies or the phone drops its connection, legal/regulatory status (is it a medical device?), liability, privacy of a camera worn in public, informed consent for testing without blind users.
8. Hardware and power: battery life of ESP32-C3 plus sensors plus a motor; phone battery and heat under ARKit + Neural Engine for an hour; mounting the phone on a cane or chest; weight budget.
9. Development process under a time limit of a few weeks: what to prototype first, how to test blindfolded safely (and the known gap between blindfolded sighted testers and blind users), what metrics to record, which published datasets or benchmarks exist.
10. Anything the author has not thought of: adjacent work (Glide, NOA, Biped, academic smart canes, Apple's own accessibility features like Door Detection and Point and Speak in Magnifier) that already solves part of this and should be reused or copied rather than rebuilt.

## Deliverable shape

1. Verdict in 2–3 sentences: is the four-tier design right, and what single change would most improve it.
2. Findings ranked by impact, each tagged [effort: S/M/L] [surface: esp32 | phone | cloud | hardware | process], each with its evidence (URL) or marked as judgment.
3. The user-interview stand-in: a section titled "What a blind user would tell the author", written from the evidence you found, with citations.
4. What you would explicitly NOT build, and why.
5. A recommended build order for the first three weeks.
