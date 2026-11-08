# Cane

Can the cane itself warn of what is at chest and head height, the one gap a cane leaves (Manduchi & Kurniawan 2011:
head-level collisions are the common accident of blind pedestrians, most of them outdoors, tree branches first)? An
ESP32-C3 on the cane's grip: one distance sensor angled up along the cane's axis, one button, one coin vibration motor
under the index finger. It is a BLE peripheral named `Cane`; the Ahead app's page fuses its distance with the phone's
LiDAR corridor and writes an urgency back. The cane plays the higher of the phone's urgency and its own, fast pulses
only, and the phone's expires 1.5 s after it was written, so a dropped link neither silences the cane nor leaves it buzzing. Nothing
on the cane talks Wi-Fi.

## Pins

ESP32-C3 SuperMini on its [AITRIP expansion board](https://www.amazon.com/dp/B0DCZGQMPL). The expansion board charges a 1S lithium cell and runs
the board from it; what its 5V pin carries while on the cell is not recorded here, so nothing below depends on it.

| GPIO | Wire | Note |
| --- | --- | --- |
| 5 | ultrasonic TRIG | |
| 6 | ultrasonic ECHO | a JSN-SR04T-2.0 or -3.0, rated 3–5.5 V, from the 3V3 pin, so ECHO is 3.3 V; the C3's pins take no more. The 5 V-only revision is not covered |
| 4, 3 | VL53L0X SDA, SCL | the `vl53l0x` build; 3V3 and GND |
| 7 | motor, through an NPN | 7 → 1 kΩ → base of a 2N2222A or S8050; emitter to GND; the motor between 3V3 and the collector, with 100 µF from 3V3 to GND beside it against the inrush (the monitor's first line says `after a brown-out` if that was not enough); a 1N4148 across the motor, cathode to 3V3; 10 kΩ from base to GND, which is what holds the motor off while the pins float through a reset or brown-out |
| 21 | button, to GND | internal pull-up; the board's BOOT button (GPIO 9) counts as the same button, for the bench. Not GPIO 2: the ROM reads it as a strapping pin at reset |
| 0 | battery, optional | the cell through 100 kΩ to GPIO 0, 100 kΩ and 100 nF from there to GND (the ADC wants a low source impedance); build with `-DCANE_BATTERY_PIN=0` (and `-DCANE_BATTERY_DIVIDER=` the ratio if not 2). Unwired, status says 0xFF |
| 8 | the board's LED | on while a phone is connected |

Every wired pin is a `-DCANE_*_PIN` build flag (`src/main.cpp`, top).

The `devkit-*` builds are the same firmware on an ESP32 DevKit V1 (WROOM-32, the bench spare, 2026-11-07), whose pins
differ: button D4 to D13, which the firmware holds low because the board has only two GND pins (its BOOT button on 0
counts too), VL53L0X SDA D21 and SCL D22, ultrasonic TRIG 18 and ECHO 19, motor 23, LED 2. Its serial port is a CP2102, `/dev/cu.usbserial-*`; with no board plugged in, PlatformIO may pick a Bluetooth speaker's port instead, so name it: `--upload-port /dev/cu.usbserial-0001`. Not 1 or 3, which are that port, and not 6 to 11,
the flash.

## Build and flash

```sh
cd firmware/cane
pio run -t upload                    # the JSN-SR04T, default
pio run -e vl53l0x -t upload         # the VL53L0X instead, for the bench until the ultrasonic arrives
pio run -e devkit-vl53l0x -t upload  # either, with devkit- in front, on the ESP32 DevKit V1
pio run -e devkit-vl53l0x-thumb -t upload  # the DevKit with the thumb lever's servo too, on GPIO 26 (firmware/thumb/src/config.h)
pio device monitor                   # one line a second: mm=830 (790-860) local=2 phone=0 played=2 fault=0 bat=255 ble=advertising up=42s reset=1
```

The second number pair is the second's lowest and highest reading; `bat=255` is 0xFF, no divider wired.

## GATT

Shared with the Ahead app's page (`ios/Ahead/index.html`); a change here is a change there.

| | UUID `c0de000N-ca9e-4a11-8e8d-000000000001` | Bytes |
| --- | --- | --- |
| service | N = 1, advertised | |
| distance | N = 2, notify, 10 Hz | uint16 little-endian mm along the cane's axis; 0xFFFF nothing in reach |
| button | N = 3, notify | uint8: 1 short press, on release; 2 long press, when 600 ms down passes (no 1 follows) |
| motor | N = 4, write without response | uint8: 0 silent, 1 slow (held and echoed, plays nothing on the cane), 2 fast; honoured for 1.5 s from the write |
| status | N = 5, notify, every 5 s and on change (battery moves in steps of 2) | battery percent (0xFF unknown), flags: bit0 sensor fault, bit1 the pulses playing are the phone's, bit2 the cane's own cue is settled; then the phone's motor value as the cane holds it (0 once 1.5 s pass without a write), which is how the page knows its writes arrive |

Motor code: fast pulses only, 100 ms on every 200 ms, under 1.0 m; a state change starts with a pulse. Slow pulses
from 2.5 m stay on the phone, worn at the chest: steady buzzing in the grip masks the ground texture the cane carries
up its shaft, and an active buzzer standing in for the motor on the bench beeped at everything in the room. The cane's own state is fast under 1.0 m, up at once
and down after 4 frames (400 ms). Played = max(own, phone's if under 1.5 s old), and only fast plays; a phone write
of 0 never silences the cane's own warning. The motor stays off until a phone has connected once since power-on, so
the board is quiet on the bench; that first connection plays one 300 ms buzz, so a walker can tell a cane that is
warning from one that is not. After that a dropped link leaves the cane warning on its own.
A reading that stays within 10 cm for 5 s settles: the cane's own cue rests, after five seconds of reporting the same
thing, and comes back with a pulse the moment the reading moves by 10 cm or more. Walking changes the reading, so a
walker never settles; standing at a counter does. The status line says `settled`, status bit2 is set, and the phone's
cue is untouched. The BuzzClip sleeps the same way after 5–7 s at a fixed distance
([its manual](https://manuals.online/imerciv/security-sensor/buzzclip/user-manual/1x8yf): irritation while standing
near something); 5 of 13 users in a [2026 study](https://pmc.ncbi.nlm.nih.gov/articles/PMC12909938/) still found it
too frequent, so this alone is not enough.

Fail-safes: the motor pin is driven low first thing at boot and the motor's base pull-down holds it off before that,
through a brown-out reset included; sensor fault (no echo edge for 1 s, the VL53L0X not answering, or no frame for 1 s,
which also covers a stuck sensor task) drops the cane's own reading so it cannot drive the motor, while a cue the phone
writes still plays, sets bit0 and keeps the distance stream going at 0xFFFF; the task watchdog resets the board 3 s after `loop()` stalls; advertising restarts on
disconnect. Until the sensor's first frame the status says fault and the motor stays off.

## Testing with nRF Connect

nRF Connect for Mobile (Nordic, iOS or Android), Scanner tab: `Cane`, advertising the service UUID. Connect, open the
service: each characteristic carries its name as a user description.

1. Distance: tap the down arrows on `distance` to subscribe; the value changes 10 times a second. Point the sensor at
   a wall at a measured distance; the two bytes are little-endian, so `0x38 0x07` is 0x0738 = 1848 mm. `FF FF` is
   nothing in reach.
2. Button: subscribe to `button`; a tap gives `01` on release, a hold gives `02` at 0.6 s and nothing on release.
3. Motor: before connecting, a hand under 1 m of the sensor plays nothing; connecting plays one 300 ms buzz. Then,
   on `motor`, write `01` (write without response, UInt8): no pulses, and the status echoes `01`; `02`: fast pulses
   for 1.5 s. Write `00` with a hand under 1 m of the sensor: it keeps pulsing fast, since the cane's own state wins.
4. Status: subscribe to `status`; `FF 00` every 5 s with no battery divider and the sensor answering; `FF 01` with
   the sensor unplugged, and the motor stops within a second even while a `02` is live; `FF 02` while a written state plays.
5. Link drop: with `02` playing, disconnect: the pulses stop within 1.5 s; the Scanner shows `Cane` again at once.
6. Settle: a hand held still under 1 m for 5 s: the pulses stop and the monitor says `settled`; move it 10 cm: pulses
   at once.
7. Watchdog and brown-out: pull the cell with the motor pulsing; it stays off on the reset, and the monitor's first
   line says `after a brown-out` when that was the reset's cause.

## Bench log

`eval/bench-log.csv`, at the repo root: one row per reading. `read_m` from the monitor line's mm (the second's range in the notes when it swings). Conditions to cover: sun, shade,
rain, glass at 0°, 15° and 30° incidence, foliage, signposts; surfaces as they are (brick, painted metal, glass,
leaves, cloth). The ultrasonic and the VL53L0X side by side where both are at hand, since the question the log
answers is which sensor to keep: the VL53L0X ranges about 0.8 m on white and 0.5 m on grey in daylight, an
ultrasonic is sun-proof but misses glass past a small angle of incidence by some accounts, and neither has been
measured here.

## Results

Not run yet: written 11-07, before the parts arrived; both builds compile. Open: which JSN-SR04T revision arrives and
whether it runs from 3.3 V; what the ultrasonic reads off glass at 15° and 30°; false pulses per 100 m walked with
the cane swinging; the ERM's inrush on the cell and whether a brown-out ever shows in the monitor.
