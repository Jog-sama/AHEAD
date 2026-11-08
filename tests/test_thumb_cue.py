"""The Ahead page's thumb cue against the Mac's LiDAR decision, on synthetic scenes, not real sensing.

Each scene is rendered once as an ARKit depth map. backend/arkit_depth.py decides from the raw map; the page decides
from the corridor the Ahead app's shell would compute from the same map (Bridge/Depth.swift in phone-bridge,
re-implemented in `corridor` below), through tests/thumb_cue_eval.cjs. The page ports the single-frame (legacy)
policy, so that is the reference; the tests at the end fail when a constant the two share changes on one side only.
"""
import base64
import json
import math
import re
import shutil
import subprocess
from io import BytesIO
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from backend.arkit_depth import ARKitDepthVision, ARKitPacket
from backend.config import Settings
from backend.obstacles import choose_direction

EVAL = Path(__file__).with_name("thumb_cue_eval.cjs")
pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="node runs the page's cue")

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(autouse=True)
def legacy_policy(monkeypatch):
    # The page has no pose history, so it cannot follow a temporal policy; compare it with the one-frame planner.
    monkeypatch.setenv("TV_NAV_POLICY", "legacy")


DW, DH, IW, IH = 80, 60, 640, 480
FX = FY = 550.0
CX, CY = 320.0, 240.0


def scene(height=1.3, pitch_deg=-10, wall=3.0, boxes=()):
    """Floor, an optional wall `wall` m ahead, and boxes (ahead_m, x0, x1, y0, y1): faces toward the camera.

    Returns the depth map along the camera axis (0 where nothing is within 5 m) and the camera pose.
    """
    t = math.radians(pitch_deg)
    rot = np.array([[1, 0, 0], [0, math.cos(t), -math.sin(t)], [0, math.sin(t), math.cos(t)]])
    origin = np.array([0, height, 0])
    depth = np.zeros((DH, DW))
    for j in range(DH):
        for i in range(DW):
            ray = rot @ np.array([((i + .5) * IW / DW - CX) / FX, -((j + .5) * IH / DH - CY) / FY, -1])
            hits = []
            if ray[1] < -1e-3:
                hits.append(-height / ray[1])
            planes = [(wall, -10, 10, 0, 3)] if wall else []
            for ahead, x0, x1, y0, y1 in [*planes, *boxes]:
                if ray[2] < -1e-3:
                    d = ahead / -ray[2]
                    p = origin + ray * d
                    if x0 <= p[0] <= x1 and y0 <= p[1] <= y1:
                        hits.append(d)
            d = min(hits, default=0)
            depth[j, i] = d if 0.2 < d < 5 else 0
    pose = np.eye(4)
    pose[:3, :3], pose[:3, 3] = rot, origin
    return depth, pose


def reference(depth, pose):
    buf = BytesIO()
    Image.fromarray(np.full((IH, IW, 3), 130, np.uint8)).save(buf, "JPEG")
    pkt = dict(
        jpeg_b64=base64.b64encode(buf.getvalue()).decode(), image_width=IW, image_height=IH,
        depth_width=DW, depth_height=DH, depth_m=[round(float(d), 5) for d in depth.flat],
        confidence=[2] * depth.size, intrinsics=[FX, FY, CX, CY],
        camera_to_world=pose.flatten(order="F").tolist(), floor_y_world=None, tracking="normal",
    )
    return ARKitDepthVision().predict(ARKitPacket.model_validate(pkt)).direction


def corridor(depth, pose, mount):
    """Bridge/Depth.swift's corridor: bands 0.6–1.3 and 1.3–2.0 m above the ground, 9 columns over ±30°, each the
    5th-percentile horizontal distance of at least 4 pixels, else None."""
    r = pose[:3, :3]
    up = r[1] / np.linalg.norm(r[1])            # world up in camera coordinates
    fwd = np.array([0, 0, -1.0]) - np.dot([0, 0, -1.0], up) * up
    fwd /= np.linalg.norm(fwd)
    right = np.cross(fwd, up)
    sx, sy = DW / IW, DH / IH
    fx, fy, cx, cy = FX * sx, FY * sy, CX * sx, CY * sy
    tan_half = math.tan(math.radians(30))
    cells = [[[] for _ in range(9)] for _ in range(2)]
    for v in range(DH):
        for u in range(DW):
            z = depth[v, u]
            if not z > 0:
                continue
            p = np.array([(u - cx) * z / fx, -(v - cy) * z / fy, -z])
            h = float(np.dot(p, up)) + mount
            band = 0 if 0.6 <= h < 1.3 else 1 if 1.3 <= h < 2.0 else None
            ahead, side = float(np.dot(p, fwd)), float(np.dot(p, right))
            if band is None or ahead <= 0 or abs(side) >= ahead * tan_half:
                continue
            c = min(int((side / (ahead * tan_half) + 1) / 2 * 9), 8)
            cells[band][c].append(math.hypot(ahead, side))
    return [[round(sorted(d)[len(d) // 20], 3) if len(d) >= 4 else None for d in band] for band in cells]


def page(cases):
    out = subprocess.run(["node", str(EVAL)], input=json.dumps(cases), capture_output=True, text=True, check=True)
    return json.loads(out.stdout)


# (name, scene arguments): scenes with something standing at chest height beyond 1.65 m, where the two must agree.
AGREE = [
    ("open room", {}),
    ("box ahead", {"boxes": [(1.2, -0.3, 0.3, 0, 1.5)]}),
    ("box left", {"boxes": [(1.2, -1.0, -0.4, 0, 1.5)]}),
    ("box right", {"boxes": [(1.2, 0.4, 1.0, 0, 1.5)]}),
    ("boxes ahead and left", {"boxes": [(1.2, -0.15, 0.15, 0, 1.5), (1.2, -1.0, -0.4, 0, 1.5)]}),
    ("box close ahead", {"boxes": [(0.5, -0.3, 0.3, 0, 1.5)]}),
    ("overhang ahead", {"boxes": [(1.2, -0.3, 0.3, 1.4, 2.0)]}),
    ("low box ahead, seen by neither", {"boxes": [(1.2, -0.3, 0.3, 0, 0.45)]}),
    ("wall at 1.4 m", {"wall": 1.4}),
    # Near the 1.55 m and 1.65 m thresholds on a side lane, where range and distance straight ahead differ by up to 15%.
    *[(f"box right at {f} m, ahead and left blocked", {"boxes": [(1.2, -0.15, 0.15, 0, 1.5), (1.2, -1.0, -0.4, 0, 1.5),
                                                                  (f, 0.70, 0.95, 0, 1.5)]}) for f in (1.40, 1.50, 1.55)],
]
# The page bounds distance ahead from range with the cosine at a cell's outer edge, so just past 1.65 m on a side lane
# it holds neutral where the Mac already cues. The difference fails closed.
FAIL_CLOSED = [(f"box right at {f} m, ahead and left blocked",
                {"boxes": [(1.2, -0.15, 0.15, 0, 1.5), (1.2, -1.0, -0.4, 0, 1.5), (f, 0.70, 0.95, 0, 1.5)]}, "right")
               for f in (1.62, 1.70)]


@pytest.mark.parametrize(("name", "kw"), AGREE, ids=[a for a, _ in AGREE])
def test_page_decides_as_the_mac(name, kw):
    depth, pose = scene(**kw)
    want = reference(depth, pose)
    got = page([{"frames": [{"corridor": corridor(depth, pose, 1.3)}]}])[0][0]["decision"]
    assert got == want, name


EXPECTED = {"open room": "center", "box left": "right", "box right": "left", "boxes ahead and left": "right",
            "box close ahead": "unknown", "box ahead": "unknown"}


@pytest.mark.parametrize(("name", "want"), EXPECTED.items())
def test_scenes_mean_what_they_say(name, want):
    depth, pose = scene(**dict(AGREE)[name])
    assert reference(depth, pose) == want


@pytest.mark.parametrize(("name", "kw", "mac"), FAIL_CLOSED, ids=[a for a, _, _ in FAIL_CLOSED])
def test_near_the_open_threshold_the_page_holds_neutral(name, kw, mac):
    depth, pose = scene(**kw)
    assert reference(depth, pose) == mac
    assert page([{"frames": [{"corridor": corridor(depth, pose, 1.3)}]}])[0][0]["decision"] == "unknown"


def test_open_floor_with_nothing_behind_it_is_unsure_on_the_phone():
    # The Mac counts far floor returns as an opening; the corridor holds nothing below 0.6 m, so the page holds
    # neutral. The difference fails closed.
    depth, pose = scene(wall=None)
    assert reference(depth, pose) == "center"
    assert page([{"frames": [{"corridor": corridor(depth, pose, 1.3)}]}])[0][0]["decision"] == "unknown"


def lanes(left, center, right, head=None):
    chest = [left] * 3 + [center] * 3 + [right] * 3
    return [chest, head or [None] * 9]


OPEN, BLOCK = 3.0, 1.0
LEFT_BLOCKED = lanes(BLOCK, OPEN, OPEN)     # -> right
CENTER_BLOCKED = lanes(OPEN, BLOCK, OPEN)   # both sides open -> unknown, right lane still open
ALL_OPEN = lanes(OPEN, OPEN, OPEN)          # -> center
CLOSE = lanes(OPEN, 0.4, OPEN)              # within 0.55 m ahead


def run(*frames, step=100):
    return page([{"frames": [{"corridor": c, "t": i * step} for i, c in enumerate(frames)]}])[0]


def test_a_cue_waits_for_two_agreeing_frames():
    out = run(LEFT_BLOCKED, LEFT_BLOCKED)
    assert [f["angle"] for f in out] == [90, 100]


def test_a_cue_holds_through_a_disagreeing_frame_while_its_lane_stays_open():
    out = run(LEFT_BLOCKED, LEFT_BLOCKED, CENTER_BLOCKED)
    assert out[2]["decision"] == "unknown" and out[2]["cue"] == "right"


def test_an_obstacle_close_ahead_is_neutral_at_once():
    out = run(LEFT_BLOCKED, LEFT_BLOCKED, CLOSE)
    assert out[2]["stop"] and out[2]["angle"] == 90


def test_a_cue_whose_lane_closes_is_dropped_at_once():
    out = run(LEFT_BLOCKED, LEFT_BLOCKED, lanes(BLOCK, OPEN, BLOCK))
    assert out[2]["cue"] == "unknown" and out[2]["angle"] == 90


def test_a_turn_holds_for_800_ms():
    # Right, then a stable center: within 800 ms of the turn the right cue stays while its lane is open.
    out = run(LEFT_BLOCKED, LEFT_BLOCKED, ALL_OPEN, ALL_OPEN, ALL_OPEN, step=300)
    assert [f["cue"] for f in out] == ["unknown", "right", "right", "right", "center"]


def test_ahead_and_unknown_are_both_neutral_and_calibration_sets_the_sides():
    out = page([{"frames": [{"corridor": ALL_OPEN}, {"corridor": ALL_OPEN, "t": 100}]},
                {"frames": [{"corridor": LEFT_BLOCKED}, {"corridor": LEFT_BLOCKED, "t": 100}],
                 "cal": {"left": 95, "right": 85}},
                {"frames": [{"corridor": None}]}])
    assert out[0][1] == {"decision": "center", "stop": False, "cue": "center", "angle": 90}
    assert out[1][1]["angle"] == 85
    assert out[2][0]["angle"] == 90


def test_no_cue_unless_tracking_is_normal():
    # An absent tracking field is what a shell too old to report it sends.
    out = page([{"frames": [{"corridor": LEFT_BLOCKED, "tracking": "normal"},
                            {"corridor": LEFT_BLOCKED, "tracking": "normal", "t": 100},
                            {"corridor": LEFT_BLOCKED, "tracking": "limited", "t": 200},
                            {"corridor": LEFT_BLOCKED, "tracking": None, "t": 300}]}])[0]
    assert [f["angle"] for f in out] == [90, 100, 90, 90]


# A change to a shared constant on one side fails here; the fix is to change the other side too.
LEVELS = [0, .1, .12, .2, .5, .75, .8, .82, .9, 1]


def test_lane_choice_matches_the_macs_on_a_grid_of_evidence():
    pairs = [([fl, fc, fr], [bl, 0, br]) for fl in LEVELS[::3] for fc in LEVELS for fr in LEVELS[::3]
             for bl in (0, .2, .35) for br in (0, .2, .35)]
    pairs += [([1, 1, 1], [0, b, 0]) for b in LEVELS]
    got = page({"choose": pairs})["choose"]
    want = [choose_direction(f, b, 1.0)[0] for f, b in pairs]
    bad = [(p, g, w) for p, g, w in zip(pairs, got, want) if g != w]
    assert not bad, f"page thumbChoose differs from backend/obstacles.py choose_direction: {bad[:5]}"


def test_angles_match_the_firmware_and_the_macs_defaults():
    tv = ROOT / "firmware/TactileVector"
    safety = next(p for p in (tv / "Safety.h", tv / "include/Safety.h") if p.exists()).read_text()
    fw = {k: int(v) for k, v in re.findall(r"constexpr \w+ (\w+) = (\d+);", safety)}
    t = page({"choose": []})["THUMB"]
    assert (t["MIN"], t["NEUTRAL"], t["MAX"]) == (fw["MIN_ANGLE"], fw["NEUTRAL"], fw["MAX_ANGLE"])
    html = (ROOT / "ios/Ahead/index.html").read_text()
    s = Settings.__dataclass_fields__
    assert f"store.get('ahead.thumb.left'))||{s['left'].default}" in html
    assert f"store.get('ahead.thumb.right'))||{s['right'].default}" in html
