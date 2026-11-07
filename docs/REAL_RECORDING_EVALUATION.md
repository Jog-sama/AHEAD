# AHEAD real-recording evaluation — 2026-11-07

Six user-supplied iPhone videos were reviewed locally. **The original recordings are not committed to this public repository.** Keep them in an ignored local folder such as `data/recordings/`.

## Evidence and limitations

- 6 portrait HLG/HEVC MOVs, ~30 FPS, **53.6 seconds / 1,608 frames** in total.
- All six carry a rotation transform. OpenCV's auto-oriented decode returns **1080 × 1920**, not the raw stored 1920 × 1080 raster.
- 110 frames were decoded and measured at ~2 samples per second, spanning each entire clip.
- Per-clip percentages below are fractions of OpenCV-decoded grayscale pixels above 245; these are **exposure indicators**, not detection or navigation scores.
- **No YOLO, monocular-depth, ARKit LiDAR, ESP32 or servo inference was executed in the inspection environment.** Model weights were unavailable. All obstacle outcomes and precision/recall remain **unverified**.
- MOVs have **no synchronized ARKit depth map or pose**. They cannot validate absolute obstacle distance, drop-offs, or traversability.
- HLG/HDR to BGR decoding may not reproduce the iPhone app's live JPEG colors exactly. Evaluate the actual ARKit streaming path separately.

| Clip | Duration | Frames sampled | Bright pixels >245 | Visually observed scene and evaluation target |
|---|---:|---:|---:|---|
| IMG_8137.MOV | 15.70 s | 32 | 8.7% | Reflective corridor, distant seating; assess floor reflections and premature “clear” |
| IMG_8138.MOV | 7.83 s | 16 | 44.5% | Very bright wall and diagonal shadows; should not hallucinate a verified route |
| IMG_8139.MOV | 7.40 s | 15 | 5.9% | Meeting table, people and chairs; compare detected classes with visible objects |
| IMG_8140.MOV | 6.23 s | 13 | 17.2% | Foreground chairs under harsh sunlight; assess near-field occlusion |
| IMG_8141.MOV | 7.87 s | 16 | 28.8% | Black backpack on carpet; inspect low-obstacle misses / erroneous center cues |
| IMG_8142.MOV | 8.57 s | 18 | 13.7% | Crowded rolling chairs; inspect clutter and free-space overconfidence |

These observations are **coarse scene descriptions, not ground-truth bounding-box annotations**. A true recall/precision score requires frame-by-frame reviewed labels and model predictions.

## Run the actual existing RGB inference on your Mac

1. Check out the feature branch `evaluation/real-video-recordings-2026-11-07`.
2. Copy the six MOVs to `data/recordings/` (do **not** `git add` or push private recordings).
3. Activate the existing project inference virtualenv; install project requirements if needed, and prepare local YOLO and depth weights using the documented setup. The replay **fails** if required weights are missing; never count this as a model pass.
4. From repository root, run:

```bash
source .venv-obstacle/bin/activate
mkdir -p data/replay-recordings

for n in 8137 8138 8139 8140 8141 8142; do
  python -m scripts.replay_perception "data/recordings/IMG_${n}.MOV" \
    --frames 100 --device mps --output "data/replay-recordings/IMG_${n}.json" || exit 1
done
```

The updated replay samples the **entire clip** (including the last frame) rather than only the opening second. Reports contain sampled timestamps, frame dimensions, execution times, decisions, and per-frame perception scene payloads.

The command above uses the RGB obstacle model, **not** the separate on-demand semantic scene-label model, which must be evaluated separately. Replays do not issue HTTP commands, arm the ESP32 or move the servo.

## What to count and inspect next

- Report per-scene **object class misses**, especially the backpack at floor height, chairs, and people. Inspect annotated boxes where possible; COCO class coverage alone cannot detect arbitrary hazards.
- Count inappropriate confident `center` or side cues in glare-only/wall-only frames, unstable rapid direction switches, and sequences with missing floor evidence.
- Report model inference latency (median/p95), model load errors, malformed frames, orientation errors, and quality-related `unknown` decisions, not just overall number of predictions.
- Compare object naming from `backend.scene_labels.SceneLabeler` against the same frames; its threshold, 768-pixel YOLO and device setting differ from the 320-pixel obstacle path.
- Obtain synchronized **RGB + ARKit depth + confidence + camera pose** recordings to validate physical hazard distance and directional occupancy, and supervised controlled obstacle trials before physical navigation use.

## Code change in this branch

`backend.obstacles.ObstacleVision.predict` now rescales along the **longest edge while preserving aspect ratio**. Previously all images were stretched to 320 × 240, even if their original shape was portrait.

`scripts.replay_perception` now samples the full video, honors rotation metadata through OpenCV, allows a Mac MPS device selection, and records timestamp/image dimensions. Regression tests are in `tests/test_recording_replay.py`.

**Validation status:** Metadata/frame decode measured locally; branch unit tests and real neural-model inference not yet executed in the target Mac environment. A successful synthetic unit test does not establish safe walking performance.
