"""Experimental monocular scene estimates. No metric depth or safe-route claims.

Neural models provide object classes and relative inverse depth. OpenCV checks
appearance-connected floor support; a robust depth/row fit rejects flat walls.
The floor assumption is deliberately exposed and fails closed when unsupported.
"""

import os
from pathlib import Path

import cv2
import numpy as np

from .vision import Decision, decode_frame

LANES = ("left", "center", "right")


def choose_direction(free, blocked, confidence, threshold=0.75):
    """Scores are evidence fractions, NOT probabilities of traversability."""
    values = np.asarray([*free, *blocked, confidence], dtype=float)
    if not np.isfinite(values).all() or ((values < 0) | (values > 1)).any():
        return "unknown", "Invalid scene evidence"
    if confidence < 0.55:
        return "unknown", "Insufficient floor/depth evidence"
    usable = [free[i] >= threshold and blocked[i] < 0.12 for i in range(3)]
    if usable[1]:
        if blocked[0] >= 0.20 and usable[2]:
            return "right", "Left obstruction; right has estimated floor support"
        if blocked[2] >= 0.20 and usable[0]:
            return "left", "Right obstruction; left has estimated floor support"
        return "center", "Center has estimated floor support"
    candidates = [i for i in (0, 2) if usable[i]]
    if len(candidates) == 1:
        return LANES[candidates[0]], "Center uncertain/blocked; one supported side"
    if len(candidates) == 2 and abs(free[0] - free[2]) >= 0.15:
        return LANES[0 if free[0] > free[2] else 2], "Stronger side evidence"
    return "unknown", "No unambiguous supported route; hold position"


def unknown(reason, scene=None, source="obstacle_opencv"):
    if scene and scene.get("depth_kind") == "relative_inverse_depth":
        source = "yolo_depth_opencv"
    if scene is not None:
        scene.setdefault("confidence", 0.0)
    return Decision(
        "unknown", "Uncertain. Hold position.", reason, source=source, scene=scene
    )


class NeuralModels:
    """All weights must be prepared locally, never downloaded during a request."""

    def __init__(self, yolo_path, depth_path, device="cpu"):
        import torch
        from transformers import AutoImageProcessor, AutoModelForDepthEstimation
        from ultralytics import YOLO

        if not Path(yolo_path).is_file() or not Path(depth_path).is_dir():
            raise ValueError("Run python -m scripts.prepare_vision first")
        if device not in {"cpu", "mps"}:
            raise ValueError("TV_MODEL_DEVICE must be cpu or mps")
        self.torch, self.device = torch, device
        torch.set_num_threads(2)
        self.yolo = YOLO(str(yolo_path))
        self.processor = AutoImageProcessor.from_pretrained(
            depth_path, local_files_only=True
        )
        self.depth = (
            AutoModelForDepthEstimation.from_pretrained(
                depth_path, local_files_only=True
            )
            .to(device)
            .eval()
        )
        # Warm both models BEFORE arming; first-call overhead must not move a servo.
        self.infer(np.full((240, 320, 3), 120, np.uint8))

    def infer(self, image):
        from PIL import Image

        h, w = image.shape[:2]
        result = self.yolo.predict(
            image, imgsz=320, conf=0.30, device=self.device, verbose=False
        )[0]
        objects = []
        for box in result.boxes:
            xy = box.xyxy[0].cpu().numpy() / [w, h, w, h]
            objects.append(
                {
                    "label": result.names[int(box.cls.item())],
                    "confidence": round(float(box.conf.item()), 3),
                    "box": np.clip(xy, 0, 1).tolist(),
                }
            )
        inputs = self.processor(
            images=Image.fromarray(cv2.cvtColor(image, cv2.COLOR_BGR2RGB)),
            return_tensors="pt",
            size={"height": 252, "width": 252},
        ).to(self.device)
        with self.torch.inference_mode():
            depth = self.depth(**inputs).predicted_depth[0].cpu().numpy()
        return objects, cv2.resize(depth, (w, h), interpolation=cv2.INTER_LINEAR)


class ObstacleVision:
    def __init__(
        self, models=None, threshold=0.75, unavailable_reason=None, semantic=None
    ):
        self.models, self.threshold = models, threshold
        self.unavailable_reason = unavailable_reason
        self.semantic = semantic

    @classmethod
    def from_env(cls):
        yolo = os.getenv("TV_YOLO_MODEL", "models/yolo11n.pt")
        depth = os.getenv("TV_DEPTH_MODEL", "models/depth-anything-v2-small")
        threshold = {"conservative": 0.75, "strict": 0.90}.get(
            os.getenv("TV_SENSITIVITY", "conservative")
        )
        if threshold is None:
            raise ValueError("TV_SENSITIVITY must be conservative or strict")
        if os.getenv("TV_OBSTACLE_ENGINE", "neural") == "opencv":
            return cls(threshold=threshold)
        try:
            models = NeuralModels(yolo, depth, os.getenv("TV_MODEL_DEVICE", "cpu"))
            semantic = None
            if os.getenv("TV_RGB_SEGMENTER", "none") == "segformer":
                from .semantic_floor import SegformerFloor

                semantic = SegformerFloor(
                    os.getenv("TV_SEMANTIC_MODEL", "models/segformer-ade20k-b0"),
                    os.getenv("TV_MODEL_DEVICE", "cpu"),
                )
            return cls(models, threshold, semantic=semantic)
        except Exception as exc:
            # Keep known-working manual/marker paths available. Do not leak paths/tokens.
            return cls(threshold=threshold, unavailable_reason=type(exc).__name__)

    def predict(self, jpeg):
        image = decode_frame(jpeg)
        image = cv2.resize(image, (320, 240))
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        quality = {
            "brightness": round(float(gray.mean()), 1),
            "sharpness": round(float(cv2.Laplacian(gray, cv2.CV_64F).var()), 1),
        }
        if gray.mean() < 25 or gray.mean() > 235 or quality["sharpness"] < 12:
            return unknown(
                "Dark, overexposed, blank or blurred frame", {"quality": quality}
            )
        # Appearance baseline only: no semantic classes/depth, never authorizes movement.
        if self.models is None:
            edges = cv2.Canny(gray, 60, 140)
            contours, _ = cv2.findContours(
                edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
            )
            regions = []
            for c in contours:
                x, y, w, h = cv2.boundingRect(c)
                if w * h > 1200:
                    regions.append(
                        {
                            "label": "unclassified region",
                            "confidence": 0.0,
                            "box": [x / 320, y / 240, (x + w) / 320, (y + h) / 240],
                        }
                    )
            return unknown(
                "Neural perception unavailable; observation only",
                {
                    "objects": regions[:20],
                    "quality": quality,
                    "depth_kind": "unavailable",
                    "model_error": self.unavailable_reason,
                    "confidence": 0.0,
                    "warning": "Run scripts.prepare_vision; no route inferred from contours",
                },
            )
        try:
            objects, inverse_depth = self.models.infer(image)
            semantic_mask = (
                self.semantic.floor_mask(image) if self.semantic is not None else None
            )
            return self.analyze(image, objects, inverse_depth, quality, semantic_mask)
        except Exception as exc:
            return unknown(
                "Perception failed; hold position",
                {"model_error": type(exc).__name__, "confidence": 0.0},
            )

    def analyze(self, image, objects, inverse_depth, quality=None, semantic_mask=None):
        h, w = image.shape[:2]
        scene = {
            "objects": objects,
            "quality": quality or {},
            "depth_kind": "relative_inverse_depth",
            "metric_distance": None,
            "confidence_kind": "heuristic_evidence_not_probability",
            "warning": "Estimated floor support is not verified traversability",
        }
        depth = np.asarray(inverse_depth, dtype=np.float32)
        if depth.shape != (h, w) or not np.isfinite(depth).all():
            return unknown("Invalid depth output", scene)
        lo, hi = np.percentile(depth, [5, 95])
        if hi - lo < 1e-5:
            return unknown("Flat relative depth; geometry unknown", scene)
        depth = (depth - lo) / (hi - lo)
        obstacle = np.zeros((h, w), np.uint8)
        for obj in objects:
            if obj["confidence"] < 0.30:
                continue
            x1, y1, x2, y2 = np.asarray(obj["box"]) * [w, h, w, h]
            # Any confident object overlapping the corridor is exclusion evidence.
            # Do not depend on COCO containing every hazard class.
            if y2 >= h * 0.45:
                pad = int(w * 0.035)
                obstacle[
                    max(0, int(y1)) : min(h, int(y2) + 1),
                    max(0, int(x1) - pad) : min(w, int(x2) + pad + 1),
                ] = 1
            obj["clock"] = (
                "10"
                if (x1 + x2) / 2 < w / 3
                else "2" if (x1 + x2) / 2 > 2 * w / 3 else "12"
            )
        scene["blocked"] = {
            name: float(
                obstacle[
                    int(h * 0.5) : int(h * 0.92), int(w * i / 3) : int(w * (i + 1) / 3)
                ].mean()
            )
            for i, name in enumerate(LANES)
        }
        if semantic_mask is not None:
            appearance = np.asarray(semantic_mask, dtype=bool)
            if appearance.shape != (h, w):
                return unknown("Invalid semantic floor mask", scene)
            scene["floor_estimator"] = "segformer_ade20k_floor_class"
        else:
            lab = cv2.cvtColor(image, cv2.COLOR_BGR2LAB).astype(np.float32)
            seed = lab[int(h * 0.88) : int(h * 0.98), int(w * 0.12) : int(w * 0.88)]
            seed_ok = (
                obstacle[int(h * 0.88) : int(h * 0.98), int(w * 0.12) : int(w * 0.88)]
                == 0
            )
            if seed_ok.mean() < 0.45:
                return unknown("Foreground occludes floor reference", scene)
            color = np.median(seed[seed_ok], axis=0)
            appearance = np.linalg.norm(lab - color, axis=2) < 26
            scene["floor_estimator"] = "color_baseline"
        appearance[: int(h * 0.40)] = False
        appearance[obstacle > 0] = False
        # Only components actually touching the bottom of the frame are floor candidates.
        _, labels = cv2.connectedComponents(appearance.astype(np.uint8))
        bottom_labels = set(labels[int(h * 0.92) : int(h * 0.98)].ravel()) - {0}
        floor = np.isin(labels, list(bottom_labels))
        # Fit row-wise medians, robust against isolated objects and texture.
        rows, medians = [], []
        for y in range(int(h * 0.48), int(h * 0.95), 4):
            vals = depth[y, floor[y]]
            if len(vals) >= w * 0.15:
                rows.append(y / h)
                medians.append(float(np.median(vals)))
        if len(rows) < 12 or np.ptp(rows) < 0.3:
            return unknown("Insufficient connected floor support", scene)
        slope, intercept = np.polyfit(rows, medians, 1)
        residual = np.asarray(medians) - (slope * np.asarray(rows) + intercept)
        fit_error = float(np.median(np.abs(residual)))
        scene["floor_fit"] = {"slope": float(slope), "median_error": fit_error}
        if slope < 0.45 or fit_error > 0.12:
            return unknown(
                "Floor geometry uncertain; wall/tilt/uneven surface possible", scene
            )
        expected = slope * np.arange(h)[:, None] / h + intercept
        geometric = np.abs(depth - expected) < 0.18
        # Depth deviations detect unnamed obstacles; negative deviations also reject drops.
        supported = floor & geometric & (obstacle == 0)
        kernel = (5, 5) if semantic_mask is not None else (7, 9)
        supported = cv2.erode(supported.astype(np.uint8), np.ones(kernel, np.uint8)) > 0
        blocked_map = (obstacle > 0) | (np.abs(depth - expected) > 0.22)
        free, blocked, relative = [], [], []
        for i in range(3):
            xs = slice(int(w * (i / 3 + 0.025)), int(w * ((i + 1) / 3 - 0.025)))
            ys = slice(int(h * 0.50), int(h * 0.92))
            # Worst vertical segment prevents thin cross-lane barriers being averaged away.
            bands = np.array_split(supported[ys, xs], 3, axis=0)
            free.append(float(min(b.mean() for b in bands)))
            blocked.append(float(blocked_map[ys, xs].mean()))
            relative.append(float(np.median(depth[ys, xs])))
        confidence = float(np.clip(1 - fit_error / 0.18, 0, 1))
        scene.update(
            free_space=dict(zip(LANES, free, strict=True)),
            blocked=dict(zip(LANES, blocked, strict=True)),
            relative_closeness=dict(zip(LANES, relative, strict=True)),
            confidence=confidence,
        )
        # A semantic mask can be less dense than appearance-connected carpet.
        # Lowering a FRACTION here is not proof of safety: depth-fit, foreground,
        # region connectivity, and worst-band vetoes still apply.
        threshold = 0.55 if semantic_mask is not None else self.threshold
        direction, reason = choose_direction(free, blocked, confidence, threshold)
        phrase = {
            "left": "Estimated opening left. Check visually.",
            "right": "Estimated opening right. Check visually.",
            "center": "Center estimated open. Check visually.",
            "unknown": "Uncertain. Hold position.",
        }[direction]
        return Decision(
            direction, phrase, reason, tuple(free), "yolo_depth_opencv", scene
        )
