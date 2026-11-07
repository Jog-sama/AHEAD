# Acceptance checks and measurement worksheet

Do these in order. Check a box only after observing the result. Stop on abnormal heating, hard binding, resets, reversed polarity, or unexpected movement. This checklist is not evidence those tests have already passed.

## Software (can run without hardware)

- [ ] `python -m pytest -q` passes.
- [ ] `python scripts/http_smoke.py` passes real local TCP/HTTP camera→backend→simulated-device checks.
- [ ] C++ safety policy test passes.
- [ ] With mock banner visible, Arm then hold left, center, right; release requests neutral and disarms.
- [ ] Wrong backend token is rejected; stale generations cannot move the controller.
- [ ] OpenCV green target in each lane produces the correct command after two frames. Blank/ambiguous/red-blocked frames return neutral.
- [ ] Microphone upload is acknowledged honestly; typed/read status produces a short clock-face cue, with text fallback.

## Electrical and unloaded hardware

| Measurement / identity | Record before powering servo |
|---|---|
| Board model/revision + matching documentation URL | __________ |
| Shield model/revision + rail selector position | __________ |
| Documented GND contact | __________ |
| GPIO number and verified signal contact | __________ |
| Bank model / rated output / number of actual usable outputs | __________ |
| Servo supply connection and connector polarity | __________ |
| Idle servo supply voltage | __________ V |
| Voltage during small unloaded movement | __________ V |
| Supply current capacity / wiring and connector rating | __________ |
| Servo model / positional behavior confirmed | __________ |

- [ ] All wiring done unpowered; servo is not connected to 3V3.
- [ ] Common ground confirmed; two positive supplies not tied together; no board backfeed path.
- [ ] Firmware initially disabled without verified config. `/health` truthfully shows this.
- [ ] Target compile succeeds; flash succeeds; serial gives device IP.
- [ ] Horn off on first configured boot; neutral stable, no resets or abnormal heat.
- [ ] Initial 88/92 cues move slightly in correct directions; neutral is non-pressing.
- [ ] Supply stays within the actual servo's documented range during movement. No cable/connector heating.
- [ ] Repeated small moves do not reboot ESP32 or trip the bank; bank does not auto-off during idle.

## Full iPhone → physical servo

- [ ] Safari sees trusted HTTPS without certificate warning; rear camera and microphone permission succeed.
- [ ] Real-device banner visible; backend ACK matches the command, independently observe horn position.
- [ ] Green target left/center/right produces correct physical cues while person remains stationary.
- [ ] No target / two targets / red exclusion → neutral; no automatic hazardous scene interpretation.
- [ ] Target crosses zones → neutral while changing, then stable new direction; no rapid flapping.
- [ ] Press Stop during active streaming → neutral and disarm; old frames cannot restart motion.
- [ ] Release manual button / lose pointer focus / switch tabs → neutral, or firmware timeout if final request lost.
- [ ] Close Safari / lock phone → powered servo returns neutral.
- [ ] Kill Python while off-center → powered ESP32 timeout returns neutral.
- [ ] Disconnect Wi-Fi while off-center → powered servo returns neutral; reconnect does not auto-rearm.
- [ ] Restart ESP32 while unloaded → neutral; backend needs fresh arm/input.
- [ ] Disconnect servo power → do **not** assume neutral; confirm accessible power isolation and remove thumb.
- [ ] Stop button is understood as a software command; physical power disconnect is accessible to supervisor.
- [ ] Soft lever cannot trap thumb and does not rely on skin friction to stop travel.

## Measure instead of claiming latency

Record at least 20 direction transitions per lane with stable lighting/network. UI shows encoding/upload/response round trip, Python reports backend processing+device HTTP, and device HTTP records ACK latency. None measures physical shaft completion. Two-frame confirmation itself adds a frame interval, so a blanket sub-50ms claim is inappropriate.

For physical latency, use external video that simultaneously captures target change and servo motion, with a known recording frame rate. Count frames from target change to first movement and to completion. Record measurement method, sample count, median/p95/max and failures. Do not subtract unrelated clocks from phone/laptop/ESP32 without synchronization.

| Metric | N | Median | p95 | Max | Conditions |
|---|---:|---:|---:|---:|---|
| Phone JPEG request round trip | ___ | ___ | ___ | ___ | ___ |
| Backend elapsed time | ___ | ___ | ___ | ___ | ___ |
| Device HTTP ACK | ___ | ___ | ___ | ___ | ___ |
| Target change → visible motion | ___ | ___ | ___ | ___ | ___ |
| Last command → visible neutral after dropout | ___ | ___ | ___ | ___ | ___ |

## Ninety-second demo script

1. “This removable grip gives a directional thumb cue using one servo. Today we are demonstrating a controlled tabletop prototype.”
2. With the seated participant sighted, show green target left/right/center and the corresponding physical cue.
3. Remove target and demonstrate uncertainty→neutral. Stop the input and demonstrate timeout→neutral.
4. Ask/read “status” for a concise clock-face cue. Label microphone capture-only if ASR is not enabled.
5. Explain sponsor adapters as optional work, not an already deployed hazard network. Show only real measured results.
