> **Obstacle upgrade:** Start with [MIGRATION.md](MIGRATION.md). See docs/UPGRADE_AUDIT.md and docs/SPONSOR_SETUP.md for current capabilities. The original baseline documentation below is retained for compatibility; statements that neural vision and sponsor wiring are absent describe the prior version.

# Build tonight, in this order

**You only need one positional SG90.** Keep the Anker cylinder as the removable grip body. The Mac does the compute; the iPhone supplies normal camera video and microphone input. No Raspberry Pi, ultrasonic sensor, second servo, LiDAR, Tinker account, or Informer account is needed for the core demo.

1. **Run mock first.** Follow the README command block. Connect with the locally generated key. Arm and hold a direction; release returns neutral and disarms. This confirms the UI/backend before wiring.
2. **Resolve the physical blockers.** Identify the exact shield GND, supply rail, and a safe output GPIO. Obtain a multimeter and safe 5V servo power connection if you do not already have them. Do not plug a servo into an unknown red/black/yellow header. [Hardware instructions](docs/HARDWARE.md).
3. **Power the unloaded servo safely.** The simplest bench test is ESP32 powered through laptop USB, servo from a separate verified 5V supply, and their grounds tied together. Do not join the two positive rails. A power-bank USB output needs a suitable rated breakout or verified shield path; a plain cable is not a bare 5V terminal.
4. **Configure and flash.** Edit ignored `firmware/TactileVector/config.h`, leaving GPIO unchosen until verified. Start horn-off and set left/right to 88/92 in `.env` for first calibration. [Flash instructions](docs/FIRMWARE.md).
5. **Use the real device.** Edit `.env`: `TV_DEVICE=esp32`, its serial-reported IP, matching device token. Restart the backend and test a brief manual nudge.
6. **Put Safari on trusted HTTPS.** Follow the mkcert/iPhone trust steps. Use a shared 2.4GHz-capable network with client isolation disabled. [Mac/iPhone guide](docs/SETUP_MAC.md).
7. **Run the camera slice.** Start rear camera, choose OpenCV, arm. Move one large green card between the three lower camera zones. After two matching frames the servo indicates that zone. Remove it and the servo returns neutral. Add a red card in its zone and the cue is rejected.
8. **Mount last.** Use a padded removable sleeve, straps, a fixed servo, and a soft rounded lever. Keep the phone separately supported until the grip is stable. No glue/heat/screws into the battery case. [Mounting instructions](docs/HARDWARE.md).
9. **Verify fail-safe behavior.** Release controls, cover camera, close Safari, turn off Wi-Fi, stop Python. Observe neutral where power remains; document failures. Do not use a thumb to obstruct a stalled servo. [Checklist](docs/ACCEPTANCE.md).

**Voice tonight:** Tap Read status / Speak latest cue for a short clock-face output. Hold the microphone button to capture and upload a clip. By default the backend honestly reports no transcription. Optional local Whisper adds recognition of questions such as “status”; it is isolated from servo control. See [extensions](docs/EXTENSIONS.md).

**Success tonight:** a sighted person stays seated, a teammate moves the green target, and the physical lever indicates left/center/right. Show measured request timings and demonstrate lost-input neutral. This is a controlled cue demonstrator, not evidence of safe real-world navigation.
