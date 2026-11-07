# Collect actual iPhone navigation evidence (opt-in, no RGB recording)

The default recorder is **OFF**. This records LiDAR depth in meters,
80x60 confidence, original sensor intrinsics, ARKit camera-to-world pose,
floor reference when available, and an approximate capture timestamp.
It NEVER stores camera JPEG, microphone audio, API keys or GPS.
Indoor geometry and trajectories can still be sensitive; recordings stay
in `data/navigation_recordings/` (Git-ignored).

## First check out the draft branch

From your existing Mac clone where the working .env and certs already live:

```bash
cd ~/Code/tactilevector
git status --short
git fetch origin
git switch navigation-temporal-map-v1
```

If `git switch` reports local changes, **stop and preserve them**. Do not
discard/reset tracked files. An alternate Git worktree can be created while
leaving the running checkout untouched.

## Start a recording

Stop the currently running backend first, then start the same HTTPS server
with a one-time recording flag. Keep the original trusted certificates and
existing .env; do not share their contents.

```bash
cd ~/Code/tactilevector
source .venv-obstacle/bin/activate
TV_RECORD_ARKIT=1 TV_NAV_POLICY=temporal TV_SCENE_MODEL_DEVICE=mps \
python -m uvicorn backend.app:create_app --factory --host 0.0.0.0 --port 8443 \
  --ssl-certfile certs/server.pem --ssl-keyfile certs/server-key.pem
```

Use the iPhone app as normal. The recorder captures only successfully
accepted `/api/arkit/frame` requests. Stop the Mac server with Ctrl+C
after each scenario to close the file. Each backend run creates a separate
`arkit_*.jsonl.gz` recording under `data/navigation_recordings`.
Per run cap: 1500 accepted frames (~6 minutes at 4 FPS). No UI or
iOS/firmware change is required.

A separate camera video from a teammate, with permission from everyone
filmed, can be used to annotate physical obstacles and compare the cues.
The LiDAR recording does not include RGB photos.

## Scenes to record with eyes OPEN

At least three repeats of each: open corridor, obstacle only on left,
obstacle only on right, chair in the center, center blocked with one
wide side corridor, both sides blocked/narrow gap, 6–15 cm obstacle,
person crossing, slow phone yaw while stationary, intentional camera
occlusion, partial dark/reflective scene, and depth/tracking loss.
Include start and end still frames. Keep the phone position and tilt
like the final wearable. Do NOT depend on cues for locomotion.

For each trial write down:
- Test name, date, mounted phone height, phone angle, lighting.
- Physical obstacle locations and approximate width of each usable gap.
- At which frame/time the scene changes and which outputs should
  be allowed: center, left, right, or **unknown**.
- Known limitations, e.g. glass/dropoff/occlusion: only unknown is allowed.
- Whether the servo visibly flickered direction (optional separate video).

## Replay both algorithms on exactly the same measurements

```bash
python -m scripts.replay_navigation data/navigation_recordings/arkit_YYYYMMDDTHHMMSS.jsonl.gz \
    --output data/navigation_recordings/replay_report.json
```

This compares the legacy sector estimator with the new temporal map and
prints direction switches, unknown rates, and actual per-frame outputs.
Without labels those metrics are **not accuracy measurements**.

To supply independently checked route labels create a JSON file like:

```json
{
  "spans": [
    {"start": 0, "end": 49, "valid": ["center", "unknown"]},
    {"start": 50, "end": 110, "valid": ["unknown"]}
  ]
}
```

Indices are zero-based **recorded frame positions**, not network sequence
IDs. For a gap that you have measured as physically wide and connected,
include a side direction only if that direction is an acceptable candidate.
Include `unknown` whenever abstaining is reasonable; a specific cue
outside the valid set counts as a wrong-specific decision.

```bash
python -m scripts.replay_navigation data/navigation_recordings/arkit_YYYYMMDDTHHMMSS.jsonl.gz \
  --labels data/navigation_recordings/labels.json \
  --output data/navigation_recordings/labeled_report.json
```

## Sharing / privacy

Do NOT commit the recordings or upload them to a public repository.
The `data/` directory is excluded by `.gitignore`.
Share recordings privately only after reviewing them. They still reveal
dimensions and sensor trajectory of an indoor place. Collect consent for
any separate videos.

## Evidence limits

Playback of actual depth+pose is materially better than synthetic tests.
It does not certify safe mobility or establish universal robustness.
An evaluation needs labeled ground truth, difficult withheld scenes,
critical-hazard false-negative rates, temporal stability and supervision
by orientation-and-mobility/accessibility professionals. The system must
abstain rather than guess when geometry is missing.
