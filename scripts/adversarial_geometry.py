"""Independent pinhole 3D raycaster for reproducible obstacle stress fixtures.

Synthetic geometry, NOT recorded sensor evidence or walking-safety validation.
AABB intersections, camera pitch/yaw, real metric depths, missing depth/noise.
"""
from __future__ import annotations

import base64
import io
from dataclasses import dataclass

import numpy as np
from PIL import Image

from backend.arkit_depth import ARKitPacket

W, H, IW, IH = 80, 60, 640, 480
INTR = (550., 550., 320., 240.)
buffer = io.BytesIO()
Image.fromarray(np.full((IH, IW, 3), 100, dtype=np.uint8)).save(buffer, "JPEG")
JPEG = base64.b64encode(buffer.getvalue()).decode()


@dataclass(frozen=True)
class Box:
    a: tuple[float, float, float]
    b: tuple[float, float, float]


def packet(boxes=(), *, yaw=0., x=0., z=0., height=1.15, tilt=-35.,
           floor=True, confidence=2, dropout=0., jitter=0., rng=None):
    """Render obstacle boxes and ground at y=0 to an ARKit-shaped packet."""
    rng = np.random.default_rng(44) if rng is None else rng
    fx, fy, cx, cy = INTR
    px, py = np.meshgrid((np.arange(W) + .5) * IW / W,
                         (np.arange(H) + .5) * IH / H)
    camera_ray = np.stack(((px-cx)/fx, -(py-cy)/fy, -np.ones((H, W))), axis=-1)
    tilt_r = np.deg2rad(tilt)
    c, s = np.cos(tilt_r), np.sin(tilt_r)
    pitch = np.array([[1,0,0], [0,c,-s], [0,s,c]])
    yaw_r = np.deg2rad(yaw)
    c, s = np.cos(yaw_r), np.sin(yaw_r)
    rotation = np.array([[c,0,s], [0,1,0], [-s,0,c]]) @ pitch
    ray = camera_ray @ rotation.T
    origin = np.array((x, height, z), dtype=float)
    distance = np.full((H, W), np.inf)

    if floor:
        ground = -origin[1] / np.where(np.abs(ray[..., 1]) < 1e-9,
                                      np.nan, ray[..., 1])
        distance = np.where((ground > .25) & (ground < 4.), ground, distance)
    for box in boxes:
        mn, mx = np.asarray(box.a), np.asarray(box.b)
        safe_ray = np.where(np.abs(ray) < 1e-9,
                            np.where(ray < 0, -1e-9, 1e-9), ray)
        start = (mn - origin) / safe_ray
        end = (mx - origin) / safe_ray
        near = np.max(np.minimum(start, end), axis=-1)
        far = np.min(np.maximum(start, end), axis=-1)
        hit = np.where((far >= near) & (far > 0) & (near > .18), near, np.inf)
        distance = np.minimum(distance, hit)
    distance = np.where(np.isfinite(distance) & (distance < 4.),
                        distance, 0.)
    if dropout:
        distance = np.where(rng.random(distance.shape) < dropout, 0., distance)
    if jitter:
        distance = np.where(distance > 0,
                            np.clip(distance + rng.normal(0, jitter, distance.shape),
                                    .25, 4.), 0.)
    pose = np.eye(4)
    pose[:3, :3] = rotation
    pose[:3, 3] = origin
    return ARKitPacket.model_validate({
        "jpeg_b64": JPEG, "image_width": IW, "image_height": IH,
        "depth_width": W, "depth_height": H,
        "depth_m": distance.ravel().tolist(),
        "confidence": [confidence] * (W*H),
        "intrinsics": list(INTR),
        "camera_to_world": pose.reshape(-1, order="F").tolist(),
        "tracking": "normal", "floor_y_world": 0. if floor else None,
    })
