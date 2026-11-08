# Thumb

TactileVector's one SG90 under the thumb, driven by the Ahead app over Bluetooth instead of by the Mac over Wi-Fi. The
board is a BLE peripheral named `Thumb` and the last two bytes of its address (`Thumb 3F2A`); the app's page (`ios/Ahead/index.html`, Settings › Thumb lever) decides left,
right or neutral from the phone's LiDAR corridor and writes the angle. No Wi-Fi, no token, no IP address, no Mac.
The Wi-Fi sketch in `firmware/TactileVector/` stays for the Mac path; both share its `Safety.h`.
The servo and its service are `src/Thumb.h`, which the cane firmware also carries (`devkit-vl53l0x-thumb` in
`firmware/cane`), so one board can be both: it advertises as `Cane` and its code, with this service in the scan response, and the page
attaches the lever to the cane's link, dropping the link only once neither uses it.

## Configure, build, flash

```sh
cd firmware/thumb
cp src/config.example.h src/config.h   # the same SERVO_PIN, PIN_VERIFIED, POWER_VERIFIED as firmware/TactileVector/config.h
pio run -t upload                      # ESP32-C3
pio run -e devkit -t upload --upload-port /dev/cu.usbserial-0001   # ESP32 DevKit V1; name the port, or PlatformIO may pick another
pio device monitor                     # one line a second: angle=90 servo=ready neutral-hold ble=advertising up=12s
```

Until `config.h` names a verified pin and supply, the board advertises and answers but emits no PWM, and the page
says the servo is disabled. Wiring and power are as for the Wi-Fi sketch: [docs/HARDWARE.md](../../docs/HARDWARE.md).
Calibrate with the horn off: Settings › Thumb lever, Left and Right angles (60 to 120, on opposite sides of 90; 78 and 102 by default, about 12 degrees each way on an SG90 clone), then
hold a test button with the walk stopped.

## GATT

Shared with the page; a change here is a change there.

| | UUID `c0de001N-ca9e-4a11-8e8d-000000000001` | Bytes |
| --- | --- | --- |
| service | N = 1, advertised | |
| angle | N = 2, write without response | uint8 degrees, 60 to 120 (500..2500 us scale, `Safety.h`); anything else is dropped; honoured for 800 ms |
| status | N = 3, notify, every second and on change | the angle the board holds; flags: bit0 servo disabled (no verified pin, or a PWM write failed, after which the pin is held low with no pulses), bit1 neutral because no fresh angle holds another |

Fail-safes: the servo goes to neutral 800 ms after the last angle and at once on disconnect, from its own task, so a
stalled BLE host or `loop()` does not hold a cue; the task watchdog resets the board 3 s after `loop()` stalls;
advertising restarts on disconnect. Neutral still holds torque: unplug servo power to clear a jam. Any phone in range
can connect and write an angle, as with the cane; the bounds and the timeout are the only guard.

## Results

Compiled for the C3 and the DevKit, with and without a pin configured (2026-11-08). Run on an ESP32 DevKit V1, servo signal on GPIO 26 and power from VIN on laptop USB, both alone and inside `devkit-vl53l0x-thumb` (2026-11-08): the servo followed 80, 90 and 100 written from the app, and the status echoed each. Not measured: degrees of horn travel per step, deflection under a resting thumb, and whether a walker feels ±12°.
