# ESP32-C3 firmware and unloaded calibration

## Configuration

The firmware uses Arduino-ESP32 **3.2.0**'s LEDC API (`ledcAttach`, `ledcWrite`) at **50Hz, 14-bit** PWM. It does not depend on AVR Servo or an unverified third-party servo library. Logical angles 0..180 map to 500..2500µs, close to one horn degree each on an SG90 clone; the bounds 60..120 give 1167..1833µs, and neutral is 1500µs. These are control values until a protractor on this servo confirms the scale.

```bash
cp firmware/TactileVector/config.example.h firmware/TactileVector/config.h
open -e firmware/TactileVector/config.h
```

Fill Wi-Fi SSID/password and copy the generated `TV_DEVICE_TOKEN` from `.env`. Escape quotes/backslashes correctly inside C++ strings. Set `SERVO_PIN` to the GPIO verified by the [hardware procedure](HARDWARE.md). Only set verification flags true after doing those checks. The example remains disabled with `SERVO_PIN=-1`; no physical pin is recommended by this artifact.

The pin guard conservatively excludes boot straps, USB, flash/power-related pins and UART pins. It is a second check, not proof of correct routing. If your board only exposes excluded pins, investigate its exact schematic before changing policy.

## Arduino CLI on macOS

```bash
brew install arduino-cli
arduino-cli core update-index --additional-urls https://espressif.github.io/arduino-esp32/package_esp32_index.json
arduino-cli core install esp32:esp32@3.2.0 --additional-urls https://espressif.github.io/arduino-esp32/package_esp32_index.json
arduino-cli board list
arduino-cli compile --fqbn esp32:esp32:esp32c3:CDCOnBoot=cdc firmware/TactileVector
```

Use the actual port from `board list`, not an invented serial number. Then, with the servo horn removed and wiring checked:

```bash
TV_SERIAL_PORT=/dev/cu.usbmodemREPLACE_WITH_ACTUAL_PORT
arduino-cli upload --fqbn esp32:esp32:esp32c3:CDCOnBoot=cdc --port "$TV_SERIAL_PORT" firmware/TactileVector
arduino-cli monitor --port "$TV_SERIAL_PORT" --config baudrate=115200
```

Set the placeholder first. If not detected, use a known data cable, another USB port, and confirm the exact board's boot procedure. Many C3 boards require holding BOOT while briefly pressing RESET, then releasing BOOT to enter download mode; board-specific documentation controls. Arduino IDE alternative: install “esp32 by Espressif Systems” version 3.2.0, select ESP32C3 Dev Module, USB CDC On Boot enabled, correct port, open the `.ino`, compile/upload.

After reboot Serial prints either `SAFE DISABLED` (no PWM) or `PWM ready; neutral`, and an IP once Wi-Fi connects. The public `/health` includes `configured`, nominal command angle, bounds, timeout, Wi-Fi and failsafe flags. A disabled board returns `configured:false` and cannot be armed by the backend.

## Endpoint contract

- `GET /health`: no actuation, JSON status.
- `GET /steer?angle=90` with `X-Device-Token`: exactly one integer, inclusive 60..120. Decimal/sign/garbage/extra/duplicate arguments are rejected. The proposed Gemini `buzz=1` parameter is deliberately not implemented.
- Command token does not go in the URL. No credentials are printed on Serial.
- Only valid, accepted commands refresh the firmware timeout. Polling health or sending bad requests cannot keep an old direction alive.
- On timeout (800ms from last accepted command) or Wi-Fi loss, an independent FreeRTOS task requests neutral. It checks about every 10ms; scheduling and physical motion time are not guaranteed or measured here. Network reconnect does not restore the previous angle.
- Startup at neutral may itself move a powered servo. Keep the horn off during first boot.

## Calibration

1. Keep servo horn off; use verified 5V, common GND, correctly routed signal. Power board then servo with no thumb contact.
2. Set backend real device mode and `TV_LEFT=84`, `TV_RIGHT=96`. Arm, hold NEUTRAL briefly; release. Watch for reboot, buzz or excessive heat.
3. Power off servo, install horn centered for intended travel, secure its retaining screw and soft lever. Ensure no collision through the small sweep.
4. Arm and briefly hold left/right without touching. If orientation is backwards, swap left/right values in `.env` and restart Python.
5. Expand to 78/102, the default (about ±12° on an SG90 clone, 3–4 mm at a 15–20 mm paddle), and wider only if a walker cannot feel it. Keep hardware hard bounds intact. Changing nominal bounds requires re-reviewing Python ACK validation and tests as well as firmware.
6. Once verified, allow very light resting-thumb contact while seated and supervised. Never use the thumb as a hard stop. A soft deflecting paddle is preferable to a rigid force lever.
7. Test loss of browser, backend and Wi-Fi with an unloaded horn. Confirm neutral while servo power remains available. Disconnection of power makes motion/position uncontrolled; firmware cannot fix it.

## Local C++ policy checks

On a Mac with Xcode command-line tools:

```bash
c++ -std=c++17 -Wall -Wextra -Werror tests/firmware_policy.cpp -o /tmp/tactilevector-policy
/tmp/tactilevector-policy
```

These checks exercise the actual shared angle parser, PWM mapping, bounds, unsigned timer rollover and timeout policy. They do not emulate the ESP32 peripheral, FreeRTOS scheduler, electrical output, or shaft movement. Full target compilation results are in [verification](../evidence/VERIFICATION.md); no USB hardware was attached in the build environment.
