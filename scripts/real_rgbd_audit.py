"""Real RGB-D decoder / inference compatibility audit.

Not a directional accuracy benchmark. These samples use different depth cameras;
no calibrated mobile phone pose or pedestrian traversability labels are present.
"""
from __future__ import annotations

import base64
import io
import json
import sys
from pathlib import Path
from zipfile import ZipFile

import cv2
import numpy as np
from PIL import Image

from backend.arkit_depth import ARKitDepthVision, ARKitPacket

SOURCES = {
    "tum": ("TUM_depth.png", "TUM_color.png", 5000.0),
    "redwood": ("depth/", "color/", 1000.0),
    "sun": ("SUN_depth.png", "SUN_color.jpg", None),
    "nyu": ("NYU_depth.pgm", "NYU_color.ppm", None),
}


def decode(payload):
    with Image.open(io.BytesIO(payload)) as image:
        result = np.asarray(image)
    return result[..., 0] if result.ndim == 3 else result


def pack(rgb, depth):
    """An explicitly non-calibrated pitch/pose for software fault testing only."""
    depth = cv2.resize(depth.astype(np.float32), (80, 60),
                       interpolation=cv2.INTER_NEAREST)
    angle = np.deg2rad(-35)
    c, s = np.cos(angle), np.sin(angle)
    pose = np.eye(4)
    pose[:3, :3] = [[1., 0., 0.], [0., c, -s], [0., s, c]]
    pose[:3, 3] = [0., 1.15, 0.]
    im = Image.fromarray(cv2.resize(rgb, (640, 480)))
    buffer = io.BytesIO()
    im.save(buffer, "JPEG", quality=65)
    return ARKitPacket.model_validate({
        "jpeg_b64": base64.b64encode(buffer.getvalue()).decode(),
        "image_width": 640, "image_height": 480,
        "depth_width": 80, "depth_height": 60,
        "depth_m": depth.ravel().tolist(),
        "confidence": np.where(depth.ravel() > 0, 2, 0).tolist(),
        "intrinsics": [525., 525., 319.5, 239.5],
        "camera_to_world": pose.flatten(order="F").tolist(),
        "floor_y_world": None, "tracking": "normal",
    })


def analyze(folder):
    stats = []
    for source, (depth_match, color_match, scale) in SOURCES.items():
        with ZipFile(folder / (source + ".zip")) as archive:
            members = archive.namelist()
            if source == "redwood":
                depth_files = sorted(n for n in members
                                     if n.startswith(depth_match) and n.endswith(".png"))
                rgb_files = sorted(n for n in members
                                   if n.startswith(color_match) and n.endswith(".jpg"))
            else:
                depth_files, rgb_files = [depth_match], [color_match]
            assert len(depth_files) == len(rgb_files) > 0
            nav = ARKitDepthVision()
            choices = []
            for depth_name, rgb_name in zip(depth_files, rgb_files):
                raw = decode(archive.read(depth_name))
                with Image.open(io.BytesIO(archive.read(rgb_name))) as img:
                    rgb = np.asarray(img.convert("RGB"))
                assert raw.ndim == 2 and rgb.ndim == 3
                if scale is None:
                    # NYU/SUN use different raw encodings; verify real pixels,
                    # never treat those raw values as metric meters.
                    stats.append({
                        "dataset": source, "frame": depth_name,
                        "mode": "raw_format_only", "shape": list(raw.shape),
                        "dtype": str(raw.dtype), "nonzero": int(np.count_nonzero(raw)),
                        "median_raw": float(np.median(raw[raw > 0])) if np.any(raw) else None,
                    })
                    continue
                depth = raw.astype(float) / scale
                depth[(depth <= .25) | (depth > 4.0)] = 0.0
                result = nav.predict(pack(rgb, depth))
                choices.append(result.direction)
                stats.append({
                    "dataset": source, "frame": depth_name,
                    "mode": "noncalibrated_pose_smoke",
                    "valid_depth_fraction": result.scene.get("valid_depth_fraction"),
                    "direction": result.direction,
                    "median_depth_m": round(float(np.median(depth[depth > 0])), 3)
                        if np.any(depth > 0) else None,
                    "reason": result.reason,
                })
            print(source, "frames", len(depth_files), "directions", choices)
    summary = {
        "real_rgbd_frames": len(stats), "sources": list(SOURCES),
        "evidence": "Real depth decoding and crash/abstention smoke only, no route labels",
        "data": stats,
    }
    print("REAL_RGBD_AUDIT_JSON=" + json.dumps(summary))
    return summary


if __name__ == "__main__":
    analyze(Path(sys.argv[1] if len(sys.argv) > 1 else "/tmp/rgbd"))
