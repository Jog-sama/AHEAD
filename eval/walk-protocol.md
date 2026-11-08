# Ahead: evaluation protocol

Blindfolded testing gives engineering metrics only. Nothing here measures usefulness to a blind pedestrian; say so on any slide that shows these numbers.

## Route
One fixed route, 300 to 500 m, walked the same way every time, with at least: 3 head-height obstacles the cane cannot find (a signpost arm, a low branch, an open window or truck mirror), 2 doorframes, 1 glass door approached head-on, 1 stretch of open sidewalk with nothing in the path (false-alarm stretch), and the same stretch in sun and in shade if possible. Mark each obstacle's position (metres from start) once; that is the ground truth.

## Conditions, in order
1. **Baseline: cane only.** Blindfolded tester, sighted guide walks one step behind, hand ready. Count contacts (cane tip or body touching an obstacle) and head-height contacts separately.
2. **Baseline: Apple Magnifier Detection Mode.** Magnifier app, Detection Mode, Door Detection and People Detection on, phone held at chest. Same route. Note what it announces and when.
3. **Ahead, phone only.** Chest mount, Start, same route.
4. **Ahead, phone + cane peripheral** (when the board is built).

Each condition at least twice; walking speed from the page's pedometer distance divided by time.

## Metrics and where they come from
| Metric | Definition | Source |
| --- | --- | --- |
| False alerts per 100 m | state changes to `slow` or `fast` with no marked obstacle within 3 m ahead, per 100 m walked | page CSV `state` rows + ground-truth positions; `analyze.py` |
| Missed obstacles | marked head/chest obstacles passed with no `slow` or `fast` within 3 m before them | same |
| Lead distance | distance at the first `slow` for each detected obstacle; want ≥ 2 m at 1.2 m/s (≈1.7 s) | `dist_m` on the first `slow` row before each obstacle |
| Latency | time from the obstacle entering 2.5 m to the first pulse; bench: walk toward a pole at known speed with a stopwatch, or video at 60 fps | bench, not the CSV |
| Head-height contacts | body contacts above the waist per route | observer tally |
| Depth losses | `lost` rows per route | CSV |
| Battery | percent at start and end, per hour of running | CSV `battery` column |
| Thermal | highest `thermal` state seen; note when it leaves `nominal` | CSV `thermal` column |
| Walking speed | metres walked / running time, per condition | page "This walk" |
| Workload | raw NASA-TLX after each condition | `nasa-tlx.md` |

## One-hour battery and thermal log
Start at 100 percent, Ahead running at 12 Hz, phone in the chest mount, screen on (keepAwake), walk or stand outdoors for 60 minutes. The page logs battery and thermal every minute. Report percent per hour and the minute the thermal state first left nominal. Repeat once indoors.

## Bench ranging (before the walks)
Use `bench-log.csv` (the esp32-labs `cane/` folder has the same header). For each sensor (phone LiDAR corridor, cane ultrasonic, VL53L0X if used), each condition (sun, shade, rain, dusk) and each surface (white wall, dark cloth, glass at 0°, 15°, 30°, foliage, a 5 cm pole, a signpost arm), place the target at 1, 2, 3 m measured with a tape, record the reading. Three readings per cell. Note the maximum range at which the reading is within 20 percent of truth.

## Rules during a walk
- The guide stops the tester before any real contact with the face.
- A session ends when the tester asks, or at the first stumble.
- No tester wears the blindfold for more than 20 minutes at a stretch.
