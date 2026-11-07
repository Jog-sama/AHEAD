"""ARKit LiDAR depth/pose support for a stationary supervised demonstration.

Use measured 3D depth to detect nearby obstacles even when ARKit has no floor
anchor. Nearby measured sightlines can suggest a direction, but are NOT a safe
walking route: steps, glass, drop-offs and unobserved regions are not verified.
"""

import base64
import binascii
import json
import math
import os
import threading
from dataclasses import dataclass

import numpy as np
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

from .obstacles import LANES, choose_direction, unknown
from .vision import Decision, decode_frame
from .navigation_map import TemporalNavigationMap

# Depth maps are deliberately downsampled on the phone to bound CPU, JSON size and latency.
MAX_FRAME_BYTES = 900_000
MIN_Z = 0.40
MAX_Z = 2.10
BANDS = ((0.35, 0.90), (0.90, 1.45), (1.45, 2.10))
HALF_CORRIDOR_M = 0.30
TURN_TAN = 0.42   # side corridor diverges gradually, not a lateral teleport
MIN_FLOOR_POINTS = (5, 4, 3)
MIN_OCCUPIED_POINTS = 4


class ARKitPacket(BaseModel):
    """Sensor samples in native, unrotated camera-buffer coordinates.

    ARKit camera_to_world is a 4x4 COLUMN-MAJOR matrix, and its camera axes
    are +X right, +Y up, -Z forward. Depth is meters along the camera axis.
    """

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    jpeg_b64: str = Field(min_length=20, max_length=550_000)
    image_width: int = Field(ge=96, le=2560)
    image_height: int = Field(ge=96, le=1920)
    depth_width: int = Field(ge=32, le=160)
    depth_height: int = Field(ge=24, le=120)
    depth_m: list[float]
    confidence: list[int]
    intrinsics: list[float]  # [fx, fy, cx, cy], original capturedImage pixel units
    camera_to_world: list[float]  # ARKit simd_float4x4, column-major
    floor_y_world: float | None = None  # ARPlaneAnchor classified floor
    tracking: str = "not_available"

    @model_validator(mode="after")
    def check_shapes(self):
        n = self.depth_width * self.depth_height
        if n > 8000 or len(self.depth_m) != n or len(self.confidence) != n:
            raise ValueError("Depth/confidence grid dimension mismatch or oversized")
        if len(self.intrinsics) != 4 or len(self.camera_to_world) != 16:
            raise ValueError("Expected 4 camera intrinsics and 16 camera pose entries")
        if any(not math.isfinite(v) for v in self.intrinsics + self.camera_to_world):
            raise ValueError("Nonfinite camera calibration")
        if any(not math.isfinite(v) or v < 0 or v > 10 for v in self.depth_m):
            raise ValueError("Invalid depth reading")
        if any(c not in (0, 1, 2) for c in self.confidence):
            raise ValueError("ARKit confidence values must be 0, 1, or 2")
        fx, fy, cx, cy = self.intrinsics
        if not (fx > 1 and fy > 1 and 0 <= cx <= self.image_width and 0 <= cy <= self.image_height):
            raise ValueError("Invalid intrinsic matrix")
        t = np.array(self.camera_to_world, np.float64).reshape(4, 4, order="F")
        if np.max(np.abs(t[3] - [0, 0, 0, 1])) > 0.025:
            raise ValueError("Invalid homogeneous camera transform")
        if np.linalg.norm(t[:3, :3].T @ t[:3, :3] - np.eye(3)) > 0.20:
            raise ValueError("Camera rotation is not approximately orthonormal")
        if self.floor_y_world is not None and not math.isfinite(self.floor_y_world):
            raise ValueError("Invalid floor elevation")
        if self.tracking not in {"normal", "limited", "not_available"}:
            raise ValueError("Invalid tracking state")
        return self

    def decoded_jpeg(self):
        try:
            data = base64.b64decode(self.jpeg_b64, validate=True)
        except (ValueError, binascii.Error) as exc:
            raise ValueError("Invalid JPEG base64") from exc
        from .scene_labels import decode_scene_jpeg
        return decode_scene_jpeg(data)


def parse_packet(data: bytes) -> ARKitPacket:
    if not data or len(data) > MAX_FRAME_BYTES:
        raise ValueError("ARKit JSON body empty or too large")
    try:
        return ARKitPacket.model_validate_json(data)
    except ValidationError as exc:
        raise ValueError("Invalid ARKit frame metadata") from exc


def unproject_camera_relative(packet: ARKitPacket):
    """Gravity-aligned forward/right/camera-relative-height for every LiDAR ray.

    Critically this computation does NOT need an ARPlaneAnchor or floor geometry.
    Forward/right are horizontal in the ARKit world frame; relative height is
    measured from the camera origin. ARKit pose must be approximately valid.
    """
    h, w = packet.depth_height, packet.depth_width
    u, v = np.meshgrid(np.arange(w) + 0.5, np.arange(h) + 0.5)
    u *= packet.image_width / w
    v *= packet.image_height / h
    fx, fy, cx, cy = packet.intrinsics
    d = np.asarray(packet.depth_m, np.float64).reshape(h, w)
    good = (np.asarray(packet.confidence).reshape(h, w) >= 1) & (d >= 0.25) & (d <= 4.0)
    cam = np.stack(((u-cx)*d/fx, -(v-cy)*d/fy, -d), axis=-1)
    pose = np.asarray(packet.camera_to_world, np.float64).reshape(4, 4, order="F")
    origin = pose[:3, 3]
    world_delta = cam @ pose[:3, :3].T
    forward_axis = -pose[:3, 2].copy()
    forward_axis[1] = 0
    norm = np.linalg.norm(forward_axis)
    if norm < 0.45:
        raise ValueError("Camera pointed too steeply for horizontal direction planning")
    forward_axis /= norm
    right_axis = np.array((-forward_axis[2], 0, forward_axis[0]))
    forward = world_delta @ forward_axis
    lateral = world_delta @ right_axis
    relative_height = world_delta[..., 1]
    return forward, lateral, relative_height, good


def unproject_world(packet: ARKitPacket):
    """Compatibility API for the floor-supported path and older tests."""
    if packet.floor_y_world is None:
        raise ValueError("No floor anchor supplied")
    forward, lateral, relative_height, good = unproject_camera_relative(packet)
    camera_height = float(packet.camera_to_world[13] - packet.floor_y_world)
    return forward, lateral, relative_height + camera_height, good, camera_height


@dataclass
class LaneEvidence:
    free: float
    occupied: float
    bands: list[dict]
    supported: bool


def estimate_lanes(forward, lateral, height, good):
    """Evaluate *measured* nearby corridor evidence, not floor color.

    The first two distance bands need actual floor returns; the far band is
    diagnostic rather than mandatory because a hand-held down-tilted camera
    often cannot observe floor beyond ~1.5m. Occupancy is computed even when
    floor evidence is missing, so a visible obstacle is still reported.

    None of the scores is a traversability probability or a certified path.
    """
    floors = good & (np.abs(height) <= 0.20)
    solid = good & (height > 0.17) & (height < 1.85)
    out = {}
    for i, name in enumerate(LANES):
        slope = (-TURN_TAN, 0.0, TURN_TAN)[i]
        corridor = np.abs(lateral - slope * forward) <= HALF_CORRIDOR_M
        bands = []
        for k, (z0, z1) in enumerate(BANDS):
            region = corridor & (forward >= z0) & (forward < z1)
            floors_here = floors & region
            obstacles_here = solid & region
            floor_n = int(np.count_nonzero(floors_here))
            occupied_n = int(np.count_nonzero(obstacles_here))
            observations = int(np.count_nonzero(good & region))
            # A small noisy depth cluster must not masquerade as a wall.
            occupied = (occupied_n >= MIN_OCCUPIED_POINTS
                        and occupied_n >= max(4, int(observations * 0.09)))
            floor_supported = floor_n >= MIN_FLOOR_POINTS[k]
            bands.append({
                "range_m": [z0, z1], "floor_points": floor_n,
                "obstacle_points": occupied_n, "depth_points": observations,
                "obstacle_observed": occupied,
                "floor_supported": floor_supported,
                "supported": floor_supported and not occupied,
            })
        # Nearby corroborated floor measurements are enough to identify a
        # *candidate* gap; missing floor farther away does not assert blockage.
        near_and_mid = bands[0]["supported"] and bands[1]["supported"]
        any_blocked = any(b["obstacle_observed"] for b in bands)
        supported = near_and_mid and not any_blocked
        out[name] = LaneEvidence(
            free=1.0 if supported else 0.0,
            occupied=0.35 if any_blocked else 0.0,
            bands=bands,
            supported=supported,
        )
    return out


def estimate_depth_sightlines(forward, lateral, relative_height, good, camera_height=None):
    """Independent floorless LiDAR scan for nearby 3D obstructions.

    A sector receives *positive* line-of-sight evidence only when many measured
    rays reach beyond 1.65m, span both horizontal halves of the sector, and
    contain no corroborated near solid cluster. Never treat missing returns as
    empty space. This detects walls/chairs without demanding floor pixels.

    When a valid ARKit floor anchor exists we exclude floor-height returns;
    otherwise we use a bounded camera-relative vertical volume to avoid a
    down-pointed camera treating the ground beneath the user as an obstacle.
    That fallback can miss very low obstructions, which is surfaced to the UI.
    """
    import cv2

    denom = np.maximum(forward, 0.20)
    horizontal = lateral / denom
    vertical = relative_height / denom
    scan_height = (vertical >= -0.82) & (vertical <= 0.55)
    ray_ok = good & (forward > 0.25) & scan_height
    if camera_height is None:
        # Approximate torso-height volume, not an assertion of a visible floor.
        solid = ray_ok & (relative_height >= -0.80) & (relative_height <= 0.55)
    else:
        above_floor = relative_height + camera_height
        solid = ray_ok & (above_floor >= 0.16) & (above_floor <= 1.85)
    out = {}
    for i, name in enumerate(LANES):
        slope = (-TURN_TAN, 0.0, TURN_TAN)[i]
        angular = np.abs(horizontal - slope) <= 0.23
        sector = ray_ok & angular
        observations = int(np.count_nonzero(sector))
        near_mask = sector & solid & (forward <= 1.55)
        near_points = int(np.count_nonzero(near_mask))
        # Cluster corroboration prevents a few noisy pixels from acting as a wall.
        components, _, stats, _ = cv2.connectedComponentsWithStats(
            near_mask.astype(np.uint8), connectivity=8
        )
        largest = int(stats[1:, cv2.CC_STAT_AREA].max()) if components > 1 else 0
        obstacle = near_points >= 8 and largest >= 6
        far = sector & (forward >= 1.65)
        far_points = int(np.count_nonzero(far))
        half_a = int(np.count_nonzero(far & (horizontal < slope)))
        half_b = int(np.count_nonzero(far & (horizontal >= slope)))
        observed_open = (
            observations >= 45
            and far_points >= 35
            and far_points >= 0.55 * observations
            and half_a >= 10 and half_b >= 10
            and not obstacle
        )
        bands = []
        for z0, z1 in BANDS:
            patch = sector & (forward >= z0) & (forward < z1)
            points = int(np.count_nonzero(patch))
            obstacles = int(np.count_nonzero(patch & solid))
            bands.append({
                "range_m": [z0, z1], "floor_points": 0,
                "obstacle_points": obstacles, "depth_points": points,
                "obstacle_observed": obstacle and z0 < 1.55 and obstacles >= 6,
                "floor_supported": False, "supported": observed_open,
            })
        out[name] = LaneEvidence(
            free=1.0 if observed_open else 0.0,
            occupied=0.35 if obstacle else 0.0,
            bands=bands, supported=observed_open,
        )
    return out


class ARKitDepthVision:
    def __init__(self, models=None):
        self.models = models
        self.navigation = TemporalNavigationMap()
        self._navigation_lock = threading.Lock()

    def reset(self) -> None:
        with self._navigation_lock:
            self.navigation.reset()

    def predict(self, packet: ARKitPacket) -> Decision:
        # Validate image even when not running YOLO, and prevent disorientation
        # from accidental portrait JPEG / landscape sensor data mismatch.
        try:
            image = packet.decoded_jpeg()
        except ValueError as exc:
            return unknown(str(exc), {"sensor": "arkit_lidar"}, source="arkit_lidar")
        h, w = image.shape[:2]
        if abs(w / h - packet.image_width / packet.image_height) > 0.02:
            return unknown("Image/depth orientation mismatch", {"sensor": "arkit_lidar"}, "arkit_lidar")
        scene = {
            "sensor": "arkit_lidar", "depth_kind": "metric_lidar_depth_m",
            "metric_distance": "measured per-pixel, NOT certified obstacle clearance",
            "tracking": packet.tracking,
            "floor_source": "classified_ARPlaneAnchor" if packet.floor_y_world is not None else "not_required",
            "floor_y_world": packet.floor_y_world,
            "warning": "Depth sightlines are NOT verified walking routes; missing returns can hide hazards",
        }
        if packet.tracking != "normal":
            self.reset()
            return unknown("ARKit camera tracking not stable", scene, "arkit_lidar")
        try:
            forward, lateral, relative_height, good = unproject_camera_relative(packet)
        except ValueError as exc:
            return unknown(str(exc), scene, "arkit_lidar")
        scene["valid_depth_fraction"] = round(float(good.mean()), 3)
        if np.count_nonzero(good) < 40:
            self.reset()
            return unknown("Insufficient reliable LiDAR returns", scene, "arkit_lidar")

        camera_height = None
        if packet.floor_y_world is not None:
            h = float(packet.camera_to_world[13] - packet.floor_y_world)
            if 0.45 <= h <= 2.20:
                camera_height = h
                scene["camera_height_m"] = round(h, 3)
            else:
                scene["floor_anchor_warning"] = "Inconsistent floor elevation; using depth-only evidence"
        # Direct range obstacle detection ALWAYS runs, whether the floor exists
        # or not. It is never gated on a floor anchor or floor support count.
        ray_evidence = estimate_depth_sightlines(
            forward, lateral, relative_height, good, camera_height
        )
        floor_evidence = None
        if camera_height is not None:
            floor_evidence = estimate_lanes(
                forward, lateral, relative_height + camera_height, good
            )
        evidence = {}
        for lane in LANES:
            depth = ray_evidence[lane]
            floor = floor_evidence[lane] if floor_evidence is not None else None
            blocked = depth.occupied > 0 or (floor is not None and floor.occupied > 0)
            supported = not blocked and (depth.supported or (floor is not None and floor.supported))
            evidence[lane] = LaneEvidence(
                free=1.0 if supported else 0.0,
                occupied=0.35 if blocked else 0.0,
                bands=floor.bands if floor is not None else depth.bands,
                supported=supported,
            )
        free = [evidence[k].free for k in LANES]
        blocked = [evidence[k].occupied for k in LANES]
        scene["free_space"] = dict(zip(LANES, free, strict=True))
        scene["blocked"] = dict(zip(LANES, blocked, strict=True))
        scene["corridor_bands"] = {k: evidence[k].bands for k in LANES}
        scene["depth_only_bands"] = {k: ray_evidence[k].bands for k in LANES}
        scene["confidence_kind"] = "measured_depth_sightline_support_not_path_safety"
        scene["depth_only_fallback_active"] = not any(
            floor_evidence[k].supported for k in LANES
        ) if floor_evidence is not None else True
        scene["floor_required"] = False
        scene["confidence"] = 0.0
        # The LiDAR decision must never wait on heavy YOLO inference.
        # Opt-in labels only; defaults to metric LiDAR-only for responsiveness.
        scene["objects"] = []
        scene["object_labels_enabled"] = os.getenv("TV_ARKIT_YOLO_LABELS", "0") == "1"
        if self.models is not None and scene["object_labels_enabled"]:
            try:
                # RGB object classes are descriptive, never used to authorize motion.
                import cv2
                small = cv2.resize(image, (320, 240))
                model = self.models
                result = model.yolo.predict(
                    small, imgsz=320, conf=0.30, device=model.device, verbose=False
                )[0]
                scene["objects"] = [
                    f"{result.names[int(b.cls.item())]} ({int(b.conf.item()*100)}%)"
                    for b in result.boxes[:12]
                ]
            except Exception:
                scene["object_labels_warning"] = "YOLO labels unavailable"
        near_obstacles = {
            k: evidence[k].occupied > 0 for k in LANES
        }
        scene["near_obstacles"] = near_obstacles
        scene["nearest_obstacle_m"] = {}
        for lane, slope in zip(LANES, (-TURN_TAN, 0., TURN_TAN)):
            mask = good & (forward > .25) & (forward < 2.1)
            mask &= np.abs(lateral / np.maximum(forward, .2) - slope) <= .23
            if camera_height is not None:
                mask &= (relative_height + camera_height >= .16) & (relative_height + camera_height <= 1.85)
            else:
                mask &= (relative_height >= -.8) & (relative_height <= .55)
            scene["nearest_obstacle_m"][lane] = (
                round(float(np.quantile(forward[mask], .1)), 2)
                if near_obstacles[lane] and np.count_nonzero(mask) >= 6 else None)
        scene["hazard_detected"] = bool(any(near_obstacles.values()))
        scene["floor_coverage_warning"] = None if camera_height is not None else (
            "Floor not tracked; depth sees obstacles but cannot verify drop-offs or steps"
        )
        if os.getenv("TV_NAV_POLICY", "temporal") == "legacy":
            direction, reason = choose_direction(free, blocked, 1.0 if any(free) else 0.0, 0.82)
        else:
            # The recent depth history is held in world space and reprojected
            # against the current phone pose to avoid per-frame lane flicker.
            with self._navigation_lock:
                nav = self.navigation.update(
                    packet, forward, lateral, relative_height, good, camera_height
                )
            scene["navigation_map"] = {
                "frames": nav["frames"], "scores": nav["scores"],
                "evidence": nav["evidence"], "reason": nav["reason"],
                "warning": nav["warning"],
            }
            # Current hazards take precedence over historical evidence, while
            # previous obstacles remain visible through brief depth dropouts.
            near_obstacles = {
                k: near_obstacles[k] or nav["blocked"][k] for k in LANES
            }
            scene["near_obstacles"] = near_obstacles
            scene["hazard_detected"] = any(near_obstacles.values())
            existing_nearest = scene.get("nearest_obstacle_m", {})
            scene["nearest_obstacle_m"] = {
                k: min(v for v in (existing_nearest.get(k), nav["nearest_obstacle_m"].get(k))
                       if v is not None)
                if any(v is not None for v in
                       (existing_nearest.get(k), nav["nearest_obstacle_m"].get(k)))
                else None
                for k in LANES
            }
            scene["free_space"] = {
                k: float(nav["supported"][k] and not near_obstacles[k])
                for k in LANES
            }
            scene["blocked"] = {k: 0.35 if near_obstacles[k] else 0.0 for k in LANES}
            direction, reason = nav["direction"], nav["reason"]
            if direction != "unknown" and near_obstacles[direction]:
                direction, reason = "unknown", "Current obstacle disagrees with historical map"
            if near_obstacles["center"] and direction == "center":
                direction, reason = "unknown", "Current center obstruction; hold position"
            nearest_center = scene["nearest_obstacle_m"].get("center")
            scene["emergency_stop"] = (
                nearest_center is not None and nearest_center < 0.55
            )
            if scene["emergency_stop"]:
                direction, reason = "unknown", "Close obstacle ahead; stop"
        if direction == "unknown" and near_obstacles["center"]:
            reason = "Nearby obstacle directly ahead (LiDAR measured); no unambiguous side sightline"
        elif direction == "unknown" and any(near_obstacles.values()):
            reason = "Measured nearby obstacle; no unambiguous alternate sightline"
        elif direction != "unknown":
            reason = f"Measured depth sightline suggests {direction}; walking route NOT verified"
        scene["confidence"] = (round(sum(scene["free_space"].values()) / 3.0, 3)
                               if direction != "unknown" else 0.0)
        phrase = {
            "left": "Candidate opening left by LiDAR. Verify before moving.",
            "right": "Candidate opening right by LiDAR. Verify before moving.",
            "center": "Depth sightline ahead looks open. Verify before moving.",
            "unknown": (
                "OBSTACLE AHEAD. Stop. No verified turn."
                if near_obstacles["center"] else
                "OBSTACLE nearby. Stop and check."
                if any(near_obstacles.values()) else
                "Uncertain depth; hold position."
            ),
        }[direction]
        return Decision(direction, phrase, reason, tuple(free), "arkit_lidar", scene)
