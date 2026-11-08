# Cane

Can the cane itself warn of what is at chest and head height, the one gap a cane leaves (Manduchi & Kurniawan 2011:
head-level collisions are the common accident of blind pedestrians, most of them outdoors, tree branches first)? An
ESP32-C3 on the cane's grip: one distance sensor angled up along the cane's axis, one button, one coin vibration motor
under the index finger. It is a BLE peripheral named `Cane`; phone-bridge's page fuses its distance with the phone's
LiDAR corridor and writes an urgency back. The cane plays the higher of the phone's urgency and its own, and the
phone's expires 1.5 s after it was written, so a dropped link neither silences the cane nor leaves it buzzing. Nothing
on the cane talks Wi-Fi.

## Pins

ESP32-C3 SuperMini on its expansion board (AGENTS.md § Boards). The expansion board charges a 1S lithium cell and runs
the board from it; what its 5V pin carries while on the cell is not recorded here, so nothing below depends on it.

| GPIO | Wire | Note |
| --- | --- | --- |
| 5 | ultrasonic TRIG | |
| 6 | ultrasonic ECHO | a JSN-SR04T-2.0 or -3.0, rated 3–5.5 V, from the 3V3 pin, so ECHO is 3.3 V; the C3's pins take no more. The 5 V-only revision is not covered |
| 4, 3 | VL53L0X SDA, SCL | the `vl53l0x` build; 3V3 and GND, as in `gateway/`'s distance add-on |
| 7 | motor, through an NPN | 7 → 1 kΩ → base of a 2N2222A or S8050; emitter to GND; the motor between 3V3 and the collector, with 100 µF from 3V3 to GND beside it against the inrush (the monitor's first line says `after a brown-out` if that was not enough); a 1N4148 across the motor, cathode to 3V3; 10 kΩ from base to GND, which is what holds the motor off while the pins float through a reset or brown-out |
| 21 | button, to GND | internal pull-up; the board's BOOT button (GPIO 9) counts as the same button, for the bench. Not GPIO 2: the ROM reads it as a strapping pin at reset |
| 0 | battery, optional | the cell through 100 kΩ to GPIO 0, 100 kΩ and 100 nF from there to GND (the ADC wants a low source impedance); build with `-DCANE_BATTERY_PIN=0` (and `-DCANE_BATTERY_DIVIDER=` the ratio if not 2). Unwired, status says 0xFF |
| 8 | the board's LED | on while a phone is connected |

Every wired pin is a `-DCANE_*_PIN` build flag (`src/main.cpp`, top).

The `devkit-*` builds are the same firmware on an ESP32 DevKit V1 (WROOM-32, the bench spare, 2026-11-07), whose pins
differ: button D4 to GND (its BOOT button on 0 counts too), VL53L0X SDA D21 and SCL D22, ultrasonic TRIG 18 and ECHO 19,
motor 23, LED 2. Its serial port is a CP2102, `/dev/cu.usbserial-*`. Not 1 or 3, which are that port, and not 6 to 11,
the flash.

## Build and flash

```sh
cd cane
pio run -t upload                    # the JSN-SR04T, default
pio run -e vl53l0x -t upload         # the VL53L0X instead, for the bench until the ultrasonic arrives
pio run -e devkit-vl53l0x -t upload  # either, with devkit- in front, on the ESP32 DevKit V1
pio device monitor                   # one line a second: mm=1830 (1790-1860) local=1 phone=0 played=1 fault=0 bat=255 ble=advertising up=42s reset=1
```

The second number pair is the second's lowest and highest reading; `bat=255` is 0xFF, no divider wired.

## GATT

Shared with phone-bridge's page; a change here is a change there.

| | UUID `c0de000N-ca9e-4a11-8e8d-000000000001` | Bytes |
| --- | --- | --- |
| service | N = 1, advertised | |
| distance | N = 2, notify, 10 Hz | uint16 little-endian mm along the cane's axis; 0xFFFF nothing in reach |
| button | N = 3, notify | uint8: 1 short press, on release; 2 long press, when 600 ms down passes (no 1 follows) |
| motor | N = 4, write without response | uint8: 0 silent, 1 slow, 2 fast; honoured for 1.5 s from the write |
| status | N = 5, notify, every 5 s and on change (battery moves in steps of 2) | battery percent (0xFF unknown), flags: bit0 sensor fault, bit1 the pulses playing are the phone's |

Motor code: slow is 100 ms on every 600 ms, fast 100 ms on every 200 ms; a state change starts with a pulse. The
cane's own state is slow under 2.5 m and fast under 1.0 m, up at once and down after 4 frames (400 ms) at the lower
level. Played = max(own, phone's if under 1.5 s old); a phone write of 0 never silences the cane's own warning.

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
3. Motor: on `motor`, write `01` (write without response, UInt8): slow pulses for 1.5 s, then silence unless the
   sensor sees something under 2.5 m; `02`: fast pulses. Write `00` with a hand under 1 m of the sensor: it keeps
   pulsing fast, since the cane's own state wins.
4. Status: subscribe to `status`; `FF 00` every 5 s with no battery divider and the sensor answering; `FF 01` with
   the sensor unplugged, and the motor stops within a second even while a `02` is live; `FF 02` while a written state plays.
5. Link drop: with `02` playing, disconnect: the pulses stop within 1.5 s; the Scanner shows `Cane` again at once.
6. Watchdog and brown-out: pull the cell with the motor pulsing; it stays off on the reset, and the monitor's first
   line says `after a brown-out` when that was the reset's cause.

## Bench log

`results/bench-log.csv`: one row per reading, its header the columns. `read_mm` from the monitor line (the second's range in the notes when it swings). Conditions to cover: sun, shade,
rain, glass at 0°, 15° and 30° incidence, foliage, signposts; surfaces as they are (brick, painted metal, glass,
leaves, cloth). The ultrasonic and the VL53L0X side by side where both are at hand, since the question the log
answers is which sensor to keep: the VL53L0X ranges about 0.8 m on white and 0.5 m on grey in daylight, an
ultrasonic is sun-proof but misses glass past a small angle of incidence by some accounts, and neither has been
measured here.

## Results

Not run yet: written 11-07, before the parts arrived; both builds compile. Open: which JSN-SR04T revision arrives and
whether it runs from 3.3 V; what the ultrasonic reads off glass at 15° and 30°; false pulses per 100 m walked with
the cane swinging; the ERM's inrush on the cell and whether a brown-out ever shows in the monitor.
