"""Short-horizon, pose-compensated LiDAR evidence for candidate tactile cues.

Not a traversability/safe-route planner. Projected rays support visibility, not
ground clearance; missing depth is never treated as free space.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass
import time

import numpy as np
import cv2

LANES = ("left", "center", "right")
SLOPES = {"left": -0.42, "center": 0.0, "right": 0.42}
CELL = 0.15
HALF_WIDTH = 0.34
BANDS = ((0.35, 0.90), (0.90, 1.45), (1.45, 2.10))


@dataclass
class _Frame:
    received: float
    position: np.ndarray
    points: np.ndarray  # World XYZ
    kinds: np.ndarray  # 1 obstacle, 2 measured floor, 3 ray visibility
    # Actual current sensor returns, never inferred by interpolated sightlines.
    near_depth_points: dict[str, int] | None = None
    floor_anchor_available: bool = False


class TemporalNavigationMap:
    """World-aligned recent geometry. One owner; serial inference calls."""

    def __init__(self, max_age_s: float = 1.8, max_frames: int = 9):
        self.max_age_s = max_age_s
        self.frames: deque[_Frame] = deque(maxlen=max_frames)
        self.previous_position: np.ndarray | None = None
        self.last_update: float | None = None
        self.previous_choice: str = "unknown"

    def reset(self) -> None:
        self.frames.clear()
        self.previous_position = None
        self.last_update = None
        self.previous_choice = "unknown"

    @staticmethod
    def _basis(packet):
        pose = np.asarray(packet.camera_to_world, dtype=np.float64).reshape(4, 4, order="F")
        origin = pose[:3, 3]
        forward = -pose[:3, 2].copy()
        forward[1] = 0
        magnitude = np.linalg.norm(forward)
        if magnitude < 0.45:
            raise ValueError("Phone camera too steep for stable horizontal cues")
        forward /= magnitude
        right = np.array((-forward[2], 0, forward[0]))
        return origin, forward, right

    @staticmethod
    def _cells(x, z, selection):
        if not np.any(selection):
            return set()
        indices = np.rint(np.column_stack((x[selection], z[selection])) / CELL).astype(np.int32)
        return set(map(tuple, indices))

    def _empty(self, reason):
        return {
            "direction": "unknown", "reason": reason,
            "supported": {name: False for name in LANES},
            "blocked": {name: False for name in LANES},
            "scores": {name: 0.0 for name in LANES},
            "near_obstacles": {name: False for name in LANES},
            "nearest_obstacle_m": {name: None for name in LANES},
            "evidence": {}, "frames": len(self.frames),
            "warning": "No candidate direction is a verified walking route",
        }

    def update(self, packet, forward, lateral, relative_height, good, camera_height, now=None):
        now = time.monotonic() if now is None else now
        origin, heading, right = self._basis(packet)
        if (self.last_update is not None and
            (now - self.last_update > self.max_age_s or
             np.linalg.norm(origin - self.previous_position) > 0.55)):
            self.reset()
        self.last_update = now
        self.previous_position = origin.copy()
        valid = good & (forward >= 0.30) & (forward <= 2.6) & (np.abs(lateral) < 1.8)
        if np.count_nonzero(valid) < 30:
            self.reset()
            return self._empty("No reliable near-range depth")

        # Gravity-aligned world 3D points from the camera pose.
        xyz = origin + forward[..., None] * heading + lateral[..., None] * right
        xyz[..., 1] = origin[1] + relative_height
        if camera_height is None:
            solid = valid & (relative_height >= -0.78) & (relative_height <= 0.55)
            floor = np.zeros_like(valid, dtype=bool)
        else:
            height = relative_height + camera_height
            # Ground-adjacent obstacles are detectable only if the depth
            # anomaly forms a connected image region. A raw 4-cm height
            # cutoff alone can accumulate phantom obstacles under 3-cm noise.
            tall = valid & (height >= 0.115) & (height <= 1.85)
            low_raw = valid & (height >= 0.040) & (height < 0.115)
            _, labels, stats, _ = cv2.connectedComponentsWithStats(
                low_raw.astype(np.uint8), connectivity=8
            )
            low = low_raw & (stats[labels, cv2.CC_STAT_AREA] >= 8) & (labels != 0)
            solid = tall | low
            floor = valid & (np.abs(height) <= 0.035)

        # Distant measurements imply rays were visible up to their endpoints,
        # NOT that ground, stairs, or low obstacles along the ray are traversable.
        angle = relative_height / np.maximum(forward, 0.2)
        long_ray = valid & (forward >= 1.65) & (angle >= -0.82) & (angle <= 0.55)
        chosen = solid | floor
        pos = xyz[chosen].reshape(-1, 3)
        kinds = np.where(solid[chosen], 1, 2).astype(np.int8)
        long_z = forward[long_ray]
        long_x = lateral[long_ray]
        long_h = relative_height[long_ray]
        if len(long_z) > 400:
            take = np.linspace(0, len(long_z)-1, 400, dtype=np.int32)
            long_z, long_x, long_h = long_z[take], long_x[take], long_h[take]
        if len(long_z):
            for fraction in (0.42, 0.67, 0.92):
                ray_points = (origin + (fraction*long_z)[:, None] * heading
                              + (fraction*long_x)[:, None] * right)
                ray_points[:, 1] = origin[1] + fraction*long_h
                pos = np.concatenate((pos, ray_points), axis=0)
                kinds = np.concatenate((kinds, np.full(len(ray_points), 3, dtype=np.int8)))

        near_depth_points = {}
        for lane, slope in SLOPES.items():
            near_corridor = (valid & (forward >= BANDS[0][0])
                             & (forward < BANDS[0][1])
                             & (np.abs(lateral - slope * forward) <= HALF_WIDTH))
            near_depth_points[lane] = int(np.count_nonzero(near_corridor))
        self.frames.append(_Frame(
            now, origin, pos, kinds, near_depth_points,
            floor_anchor_available=camera_height is not None,
        ))
        while self.frames and now - self.frames[0].received > self.max_age_s:
            self.frames.popleft()
        return self.evaluate(packet, now)

    def evaluate(self, packet, now=None):
        now = time.monotonic() if now is None else now
        if not self.frames:
            return self._empty("No spatial measurements")
        origin, heading, right = self._basis(packet)
        # Reproject WORLD-space history into current phone-relative coordinates.
        points = np.concatenate([f.points for f in self.frames], axis=0)
        kinds = np.concatenate([f.kinds for f in self.frames], axis=0)
        relative = points - origin
        z = relative @ heading
        x = relative @ right
        # History can veto a route, but must not AUTHORIZE a new route when the
        # latest frame no longer observes that corridor (e.g., sudden yaw,
        # occlusion, moving past an opening). Historical visibility alone is
        # particularly dangerous because it does not prove ground clearance.
        fresh = self.frames[-1]
        fresh_relative = fresh.points - origin
        fresh_z = fresh_relative @ heading
        fresh_x = fresh_relative @ right
        fresh_kinds = fresh.kinds
        details, blocked, supported, scores, nearest = {}, {}, {}, {}, {}

        for lane, slope in SLOPES.items():
            corridor = (z >= 0.35) & (z <= 2.1) & (np.abs(x - slope*z) <= HALF_WIDTH)
            occupied = corridor & (kinds == 1)
            occupied_cells = self._cells(x, z, occupied)
            # Require spatially distinct cells rather than repeated noisy pixels.
            obstacle = len(occupied_cells) >= 3
            blocked[lane] = obstacle
            nearest[lane] = round(float(np.quantile(z[occupied], 0.10)), 2) if obstacle else None
            band_stats = []
            for lo, hi in BANDS:
                subset = corridor & (z >= lo) & (z < hi)
                ground_cells = self._cells(x, z, subset & (kinds == 2))
                line_cells = self._cells(x, z, subset & (kinds == 3))
                band_stats.append({
                    "range_m": [lo, hi], "floor_cells": len(ground_cells),
                    "line_of_sight_cells": len(line_cells),
                    "occupied_cells": len(self._cells(x, z, subset & (kinds == 1))),
                })
            near, mid = band_stats[:2]
            a = max(near["floor_cells"] / 3.0, near["line_of_sight_cells"] / 5.0)
            b = max(mid["floor_cells"] / 3.0, mid["line_of_sight_cells"] / 5.0)
            score = round(min(1.0, a) * 0.45 + min(1.0, b) * 0.55, 3)
            scores[lane] = 0.0 if obstacle else score
            fresh_corridor = ((fresh_z >= 0.35) & (fresh_z <= 2.1)
                              & (np.abs(fresh_x - slope * fresh_z) <= HALF_WIDTH))
            fresh_bands = []
            for lo, hi in BANDS[:2]:
                current = fresh_corridor & (fresh_z >= lo) & (fresh_z < hi)
                ground = len(self._cells(fresh_x, fresh_z, current & (fresh_kinds == 2)))
                visible = len(self._cells(fresh_x, fresh_z, current & (fresh_kinds == 3)))
                fresh_bands.append({
                    "floor_cells": ground, "line_of_sight_cells": visible,
                    "supported": ground >= 2 or visible >= 2,
                })
            # A projected ray from 2m away is NOT a sensor observation of the
            # first 0.35-0.90m. Never grant an open cue when the current frame
            # provides no direct measurements in that near corridor.
            measured_near = (fresh.near_depth_points or {}).get(lane, 0)
            near_measured = measured_near >= 8
            # When ARKit supplies a plausible classified floor anchor, prefer
            # direct near-floor returns over rays passing above small hazards.
            near_floor = fresh_bands[0]["floor_cells"] >= 2
            near_coverage = near_measured and (
                near_floor if fresh.floor_anchor_available else True
            )
            # The old map may still VETO a route, never authorize unseen space.
            current_support = all(b["supported"] for b in fresh_bands) and near_coverage
            supported[lane] = score >= 0.68 and not obstacle and current_support
            details[lane] = {
                "bands": band_stats, "quality": score,
                "fresh_bands": fresh_bands, "current_support": current_support,
                "measured_near_depth_points": measured_near,
                "measured_near_floor_cells": fresh_bands[0]["floor_cells"],
                "near_coverage_confirmed": near_coverage,
                "candidate_sightline_only": not any(d["floor_cells"] for d in band_stats),
            }

        close_center = nearest["center"] is not None and nearest["center"] < 0.55
        if close_center:
            choice, reason = "unknown", "Close obstacle ahead; stop before evaluating a turn"
        elif supported["center"]:
            choice, reason = "center", "Measured forward sightline; forward preferred"
        elif blocked["center"]:
            sides = [i for i in ("left", "right") if supported[i]]
            if len(sides) == 1:
                choice, reason = sides[0], "Center obstruction; one corroborated side sightline"
            elif len(sides) == 2 and abs(scores["left"] - scores["right"]) >= 0.20:
                choice = max(sides, key=scores.__getitem__)
                reason = "Center obstruction; side evidence has a clear margin"
            else:
                choice, reason = "unknown", "Center blocked; no unambiguous side corridor"
        else:
            center_info = details["center"]
            if not center_info["near_coverage_confirmed"]:
                choice, reason = "unknown", "Near walking corridor not directly observed; hold position"
            else:
                choice, reason = "unknown", "Forward geometry unverified; do not guess a turn"

        # Avoid a side-to-side flip based on a weak new advantage.
        if (choice in ("left", "right") and self.previous_choice in ("left", "right")
            and choice != self.previous_choice and supported[self.previous_choice]
            and not close_center and scores[choice] - scores[self.previous_choice] < .32):
            choice, reason = self.previous_choice, "Hold previous side; no decisive advantage"
        self.previous_choice = choice
        return {
            "direction": choice, "reason": reason,
            "supported": supported, "blocked": blocked, "scores": scores,
            "near_obstacles": blocked, "nearest_obstacle_m": nearest,
            "evidence": details, "frames": len(self.frames),
            "map_age_ms": round((now - self.frames[-1].received) * 1000, 1),
            "warning": "LOS and floor are candidate evidence only; no verified walking path",
        }
