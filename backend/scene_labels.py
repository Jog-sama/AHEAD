"""On-demand RGB + ARKit metric-depth scene narration.

This module never changes navigation decisions or actuator commands. Object
recognition is optional: an absent weight file is reported, never guessed.
"""
from __future__ import annotations

import io
import os
import time
import threading
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, UnidentifiedImageError

from .arkit_depth import ARKitPacket, unproject_camera_relative


def decode_scene_jpeg(data: bytes):
    """Separate bounded decoder for high-quality on-demand RGB snapshots."""
    if not data or len(data) > 800_000:
        raise ValueError("Scene snapshot must be a JPEG under 800 KB")
    try:
        with Image.open(io.BytesIO(data)) as image:
            if image.format != "JPEG":
                raise ValueError("Scene snapshot is not JPEG")
            w, h = image.size
            if min(w, h) < 96 or max(w, h) > 1536 or w * h > 1_250_000:
                raise ValueError("Scene snapshot dimensions out of bounds")
            image.load()
            rgb = np.asarray(image.convert("RGB"))
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
        raise ValueError("Malformed RGB scene image") from exc
    return cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)


class SceneLabeler:
    def __init__(self, model=None, model_path=None, device=None):
        self.model = model
        root = Path(__file__).resolve().parents[1]
        default_model = "models/yolo11s.pt" if (root / "models/yolo11s.pt").is_file() else "models/yolo11n.pt"
        self.model_path = Path(model_path or os.getenv("TV_SCENE_YOLO_MODEL", default_model))
        self.device = device or os.getenv("TV_SCENE_MODEL_DEVICE", "auto")
        self._load_error = None
        self.diagnostics = {}
        self.inference_lock = threading.Lock()
        if not self.model_path.is_absolute():
            self.model_path = Path(__file__).resolve().parents[1] / self.model_path

    def _infer(self, bgr):
        if self.model is None:
            if not self.model_path.is_file():
                raise RuntimeError("Scene recognition weights missing; set TV_SCENE_YOLO_MODEL to a local .pt file")
            try:
                from ultralytics import YOLO
                self.model = YOLO(str(self.model_path))
            except (ImportError, OSError, ValueError) as exc:
                raise RuntimeError("Scene recognition model unavailable on Mac") from exc
        import torch
        requested = self.device
        if self.device == "auto":
            self.device = "mps" if torch.backends.mps.is_available() else "cpu"
        if self.device == "mps" and not torch.backends.mps.is_available():
            self.device = "cpu"
        start = time.monotonic()
        threshold = float(os.getenv("TV_SCENE_CONF", "0.25"))
        result = self.model.predict(
            bgr, imgsz=768, conf=0.10, iou=0.50, max_det=40,
            device=self.device, verbose=False,
        )[0]
        h, w = bgr.shape[:2]
        detected = []
        candidates = []
        for box in result.boxes:
            confidence = float(box.conf.item())
            coords = np.asarray(box.xyxy[0].cpu().numpy(), dtype=float)
            coords /= [w, h, w, h]
            coords = np.clip(coords, 0, 1)
            if coords[2] - coords[0] < 0.01 or coords[3] - coords[1] < 0.01:
                continue
            candidate = {
                "label": str(result.names[int(box.cls.item())]),
                "confidence": round(confidence, 3),
                "box": [float(x) for x in coords],
            }
            candidates.append(candidate)
            if confidence >= threshold:
                detected.append(candidate)
        self.diagnostics = {
            "model": self.model_path.name, "device": self.device,
            "requested_device": requested, "threshold": threshold,
            "inference_ms": round((time.monotonic() - start) * 1000, 1),
            "image_size": [w, h], "candidates": candidates,
            "accepted_count": len(detected),
            "zero_reason": None if detected else (
                "all_candidates_below_threshold" if candidates else "no_candidates_above_0.10"),
        }
        return detected

    @staticmethod
    def sensor_box(box, turns):
        x0, y0, x1, y1 = box
        for _ in range(turns % 4):
            x0, y0, x1, y1 = 1-y1, x0, 1-y0, x1
        return [x0, y0, x1, y1]

    @staticmethod
    def fuse_object(obj, packet, forward, lateral, good):
        """Use inner ROI + measured confidence, not guessed monocular depth."""
        x0, y0, x1, y1 = obj["box"]
        dw, dh = packet.depth_width, packet.depth_height
        # Inner ROI reduces background rays inside loose object boxes.
        xm, ym = (x0 + x1) / 2, (y0 + y1) / 2
        xr, yr = (x1 - x0) * .30, (y1 - y0) * .30
        xa, xb = max(0, int((xm - xr) * dw)), min(dw, int(np.ceil((xm + xr) * dw)))
        ya, yb = max(0, int((ym - yr) * dh)), min(dh, int(np.ceil((ym + yr) * dh)))
        measured = None
        lane = "direction unverified"
        if xb > xa and yb > ya:
            mask = good[ya:yb, xa:xb] & (forward[ya:yb, xa:xb] > 0.25)
            if int(np.count_nonzero(mask)) >= 6:
                fd = forward[ya:yb, xa:xb][mask]
                lr = lateral[ya:yb, xa:xb][mask]
                measured = round(float(np.quantile(fd, 0.30)), 1)
                bearing = float(np.median(lr / np.maximum(fd, .2)))
                lane = "left" if bearing < -.18 else "right" if bearing > .18 else "ahead"
        return {**obj, "distance_m": measured, "direction": lane}

    def describe(self, packet: ARKitPacket, decision, rgb_jpeg: bytes | None = None):
        if decision is None or decision.scene is None:
            return {"phrase": "No recent LiDAR scene. Hold position.", "objects": [], "source": "unavailable"}
        scene = decision.scene
        objects = []
        model_issue = None
        try:
            bgr = decode_scene_jpeg(rgb_jpeg) if rgb_jpeg else packet.decoded_jpeg()
            # Images and the 80x60 depth map retain the original sensor aspect
            # ratio. Never apply the SwiftUI display rotation to either.
            if abs(bgr.shape[1] / bgr.shape[0] - packet.image_width / packet.image_height) > .025:
                raise ValueError("RGB snapshot and LiDAR depth have different orientations")
            forward, lateral, _, good = unproject_camera_relative(packet)
            # Orient objects upright using measured gravity, then invert boxes
            # into the original sensor grid before associating metric depth.
            pose = np.asarray(packet.camera_to_world).reshape(4, 4, order="F")
            up_x, up_y = pose[1, 0], pose[1, 1]
            turns = (1 if up_x > 0 else 3) if abs(up_x) > abs(up_y) else (0 if up_y > 0 else 2)
            if not self.inference_lock.acquire(blocking=False):
                raise RuntimeError("Previous recognition is still running; try again shortly")
            try:
                raw = self._infer(np.ascontiguousarray(np.rot90(bgr, turns)))
                diagnostics = dict(self.diagnostics)
            finally:
                self.inference_lock.release()
            objects = [self.fuse_object({**o, "box": self.sensor_box(o["box"], turns)},
                                       packet, forward, lateral, good) for o in raw]
            diagnostics["upright_quarter_turns"] = turns
        except (RuntimeError, ValueError, ImportError) as exc:
            model_issue = str(exc)
        except Exception:
            model_issue = "RGB scene model failed; check local weights and Mac acceleration"
        # Prefer confidently detected nearby names; never fabricate labels.
        objects.sort(key=lambda x: (x["distance_m"] is None,
                                    x["distance_m"] if x["distance_m"] is not None else 10.0,
                                    -x["confidence"]))
        unique = []
        for obj in objects:
            if sum(1 for prev in unique if prev["label"] == obj["label"] and prev["direction"] == obj["direction"]) < 2:
                unique.append(obj)
            if len(unique) >= 4:
                break
        fragments = []
        for obj in unique:
            suffix = (f"about {obj['distance_m']:g} meters {obj['direction']}"
                      if obj["distance_m"] is not None else "distance unverified")
            qualifier = "possible " if obj["confidence"] < .65 else ""
            fragments.append(f"{qualifier}{obj['label']}, {suffix}")
        if fragments:
            text = "I detect " + "; ".join(fragments) + "."
        elif model_issue:
            text = "Object naming unavailable on the Mac."
        else:
            text = "No objects identified confidently in this image."
        center = scene.get("nearest_obstacle_m", {}).get("center")
        if scene.get("near_obstacles", {}).get("center"):
            text += (f" LiDAR reports an obstacle about {center:g} meters ahead."
                     if isinstance(center, (int, float)) and 0.2 <= center <= 4
                     else " LiDAR reports an obstacle ahead.")
        # A cue is a candidate sightline, not proof of a traversable path.
        if decision.direction in {"left", "right"}:
            text += f" The {decision.direction} sightline appears more open; route not verified."
        elif decision.direction == "unknown":
            text += " No verified turn. Hold position."
        else:
            text += " Sightline ahead appears open, but route not verified."
        return {"phrase": text, "objects": objects, "diagnostics": diagnostics if not model_issue else {"zero_reason": model_issue}, "source": "rgb_yolo_plus_arkit_lidar" if not model_issue else "lidar_only", "model_warning": model_issue}
