# Ahead on the App Store: listing draft

The text for App Store Connect, with the evidence behind each answer. A draft: the screenshots, the demo video and the conditions for pressing Submit are open in [#29](https://github.com/Jog-sama/AHEAD/issues/29). The app's native code (`Ahead/PrivacyInfo.xcprivacy`, `Bridge/Speech.swift`, its `project.yml`) is in a separate private repository; the lines cited from it are quoted here.

Rules relied on, as read on developer.apple.com on 2026-11-09 (quote the live page before citing one): App Review Guidelines 1.4.1 (medical apps with inaccurate information), 2.1 (final, working build; hardware or demo access needed to review), 2.5.2 (self-contained bundle), 4.2 (more than a repackaged website), 5.1.1(i) (a privacy policy linked in the metadata and in the app, with retention and deletion stated), 5.1.1(ii) (purpose strings that describe the use); Accessibility Nutrition Labels (a feature may be claimed only when every common task can be completed with it, assessed on each device; first launch and settings count as common tasks; labels are voluntary now and expected to become required).

## Listing

| Field | Text |
| --- | --- |
| Name (30) | Ahead Cane (the App Store Connect record's name; the home-screen name is Ahead) |
| Subtitle (30) | Extra cues beside your cane |
| Category | Primary Utilities; secondary Health & Fitness is not used, because it invites the medical reading of 1.4.1 |
| Support URL | https://aheadcane.github.io/support/ |
| Privacy policy URL | https://aheadcane.github.io/privacy/ (also in the app: Settings › Privacy policy) |
| Marketing URL | https://aheadcane.github.io/ |
| Version | 1.0 (`project.yml`, setting group `aheadBuild`) |
| Copyright | 2026 Jonas Neves (to confirm with the team; #29) |

### Description

> Ahead adds a second kind of cue for people who walk with a white cane. Your cane finds the ground. Ahead uses your iPhone's LiDAR sensor, worn in a chest pocket or mount, to feel for what the cane misses: a branch, a sign or an open door at chest and head height. It tells you with vibration under your finger: nothing within 2.5 metres is silent, a slow pulse means something is within 2.5 metres, and a fast pulse means within 1 metre.
>
> Hold the button and ask a question about what is in front of you. Ahead takes a photo, listens, and answers in one spoken sentence, for example what a sign says.
>
> An optional cane attachment with a distance sensor and a small motor connects over Bluetooth, but the app works with only the phone.
>
> Ahead never replaces your cane or your own judgement, and silence does not mean the way is clear. It never tells you whether it is safe to cross a street. It is not a medical device and makes no medical claim. Ahead is new and has had little testing; please use it as an addition you can ignore.
>
> Needs an iPhone with a LiDAR sensor (12 Pro or a later Pro model) and iOS 26 for asking by voice.
>
> What leaves the phone: when you ask a question, the photo, the distances and your question go to our server and on to Anthropic's Claude. The app also registers a random id and the phone's name with our server. No tracking.

Wording kept from the README: "never replaces the cane", the distances as measured, "no medical claim". It avoids "navigation aid", "safe", "detect obstacles for you" and any figure for accuracy, which 1.4.1 asks to be backed by data we do not have (no outdoor walk has been recorded with the eval kit yet).

Promotional text (170): "A second cue beside your cane: LiDAR pulses for what is at chest and head height, and a spoken answer when you ask. Never a replacement for your cane."

### Keywords (100)

`cane,blind,low vision,accessibility,LiDAR,obstacle,haptic,white cane,mobility,assistive`

(87 characters.) "Navigation" is left out on purpose.

## App Privacy answers

Matches `Ahead/PrivacyInfo.xcprivacy` and the privacy policy page. Tracking: **No**; no tracking domains.

| Data type | Collected | Linked to the user | Used for | Evidence |
| --- | --- | --- | --- | --- |
| Photos or Videos | Yes | No | App functionality | the photo sent with a question: `ios/Ahead/index.html` `cloudAsk`, `snapshot`; the Worker does not store it (`worker/src/index.js` `ask`); Anthropic receives it |
| Other User Content | Yes | No | App functionality | the question's text, same path |
| Device ID | Yes | No | App functionality | the random id the app makes and registers with the Worker (`loadDevice`, `enroll`); not an Apple advertising or vendor id |
| Email Address | Yes | No | App functionality | only if the person fills the beta form on the web; not collected by the app. TestFlight only; remove from the store answers if the beta form is gone by release |
| Everything else | No | | | no location (the Ahead build asks for none), contacts, health, usage or diagnostics; no SDKs, no analytics |

"Linked to the user: No" holds because no account, email or Apple id is joined to the device id on the server (the phone's own name is stored beside the id; see the privacy page). If the beta email is ever joined to a device id, this answer changes.

The speech-to-text runs on the phone: `Bridge/Speech.swift` uses the iOS 26 `SpeechTranscriber` with a downloaded on-device model, so the usage string "on this phone" is accurate. Before iOS 26 the voice question reports "needs iOS 26".

## Age rating answers

All "None" or "No": cartoon or fantasy violence, realistic violence, sexual content, nudity, profanity, horror, alcohol, tobacco and drugs, gambling, contests, unrestricted web access (the page is bundled; it loads only the Worker and the privacy page), user-generated content (none shown to others). Medical or health information: **None**, since the app makes no health claim. The tool's result is expected to be 4+; the safety use is covered in the description and the in-app statement, not by the rating.

## Accessibility Nutrition Label answers

Apple's criterion: a feature is claimed only if all common tasks can be done with it. Ahead's common tasks are: first launch (safety statement, then Feel the code), Start and Stop a walk, ask a question (button or voice), connect the cane, Settings. Evidence is from reading `ios/Ahead/index.html`; **nothing here has been run under VoiceOver, Voice Control or at 200% text by a person**. Claim a feature only after the check in the right column is done.

| Feature | Claim now? | Evidence from the code | Check before claiming |
| --- | --- | --- | --- |
| VoiceOver | Not yet; intended | the page is built for it: labelled controls (`aria-label` on the icon button and sections), the distance table has a label, results are `aria-live` outputs, the walk state is deliberately not live so VoiceOver does not narrate every change (line 129), a walk starts without the screen by the Action Button, Siri or VoiceOver's two-finger double tap (README) | one person who uses VoiceOver walks every common task on a LiDAR iPhone and on a non-LiDAR one, and the dialogs (safety, privacy, Feel the code, Settings) are reachable and dismissable |
| Voice Control | No | native buttons with visible text labels, but the settings toggles and the icon-only Settings button have names that differ (`aria-label=Settings`) | run Voice Control through each task |
| Larger Text | No | text uses `font: -apple-system-body` so it scales, but the walk screen is one non-scrolling screen (`main{height:calc(100dvh …)}`), so 200% text may clip the controls | set the largest sizes and complete a walk start and an ask |
| Dark Interface | Yes after a glance | `color-scheme: light dark` and `light-dark()` colours throughout | open every dialog in dark mode and look |
| Differentiate Without Color Alone | No | the state box changes colour (far, slow, fast) and also shows a word, and the pulses carry the state; not checked for every status | a colour-blind pass over the corridor table and the state box |
| Sufficient Contrast | No | colours were chosen with `--dim` and `--blue-t` for contrast but no ratio was measured | measure with Accessibility Inspector |
| Reduced Motion | Yes after a glance | no keyframe animation; two transitions, switched off under `prefers-reduced-motion` (line 114) | confirm with the setting on |
| Captions, Audio Descriptions | Not applicable | no video or recorded speech; Ahead speaks with the system voice and plays short tones | leave unclaimed |

What this means for a first submission: label nothing as supported that was not checked; the labels are voluntary today.

## Safety statement in the app

Shown once on first launch, before anything else; reopened from Settings › Safety statement:

> Ahead is an extra cue and never a replacement for your cane or your own judgement. It senses only what is ahead of the phone at chest and head height, and it can miss things: glass, thin poles, steps and drops, moving vehicles, and anything outside the camera's view. Silence does not mean the way is clear. It never tells you whether to cross a street. Keep using your cane and your usual skills, and stop if you are unsure. Ahead is still being tested, is not a medical device, makes no medical claim, and its answers to questions can be wrong.

The cloud also never judges a crossing: `isCrossing` in the Worker, on the question and on the answer, and the page's own check (`CROSSING`).

## Screenshots

Taken on a real LiDAR iPhone, 6.9-inch size (iPhone 16 or 17 Pro Max), no mock-ups, per 2.3.3. The app targets iPhone only (`TARGETED_DEVICE_FAMILY: 1` in the private repo's `project.yml`), so no iPad set.

1. The walk screen before Start, "Ready".
2. The walk screen mid-walk with the distance grid and the state box.
3. Asking: the button held, with a spoken answer in the result line.
4. The safety statement.
5. Settings, showing the cane and the privacy policy.

## Review notes (App Review Information)

Draft, to be pasted with the demo video's link. Sign-in required: **off**. There is no account, no demo mode and no reviewer switch.

> Ahead is an iPhone app for people who walk with a white cane. It uses the phone's LiDAR sensor to give vibration cues for objects at chest and head height, and answers a spoken question about a photo. There is no account. The cane attachment and the thumb lever are optional Bluetooth boards; these steps need neither.
>
> A video of a person walking with the app and its cane attachment is at <LINK, no login>.
>
> 1. Open the app, read the safety statement and tap Done.
> 2. Tap Start. The app asks for Camera and Motion. On an iPhone with LiDAR the screen shows the distance grid, and the phone vibrates faster as something comes within 2.5 m and then 1 m. On an iPhone without LiDAR (anything but a 12 Pro or later Pro model), Start says "This iPhone has no LiDAR sensor, so the walk cue cannot run" and speaks it. This is expected: the sensor cannot be emulated.
> 3. Hold "What is ahead", say a question such as "what does the sign say", and release. The app asks for Microphone and Speech Recognition the first time. The photo and the question go to our server and on to Anthropic's API. The phone registers with the server automatically the first time the app opens, within daily limits, so no approval is needed; if the daily limit is reached the app says so aloud and the other features work. Questions about crossing a street are never answered, by design. Spoken questions need iOS 26: on iOS 17 to 25 the button reports "Could not listen: needs iOS 26", and a plain tap answers from the photo on the phone without sending it.
> 4. Tap "Connect cane". The app asks for Bluetooth. Without the board it finds nothing and the line under it says so. This step is expected to fail without the hardware.
>
> Other purpose strings exist because the shared code links those frameworks; the app never asks for them.
>
> Contact: <contact, open in #29>

Step 3's iOS 17 to 25 sentence is from the code: `Bridge/Speech.swift:19` refuses before iOS 26, and `answer` in `ios/Ahead/index.html` sends only a spoken question to the cloud; a tap labels the photo and reads its text on the phone.

## Open before submission

Listed with owners in the tracker: the demo video at a login-free link, the screenshots, the contact details above, the copyright holder, a support email address, retention periods on the privacy page, an accessibility pass by a VoiceOver user, and whether to keep the email row in App Privacy.
