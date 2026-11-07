"""Optional RGB semantic floor mask; NOT proof of physical traversability.

This adapter is opt-in and offline at request time. The native ARKit route uses
actual metric depth and a tracked floor plane instead of this fallback.
"""

from pathlib import Path

import cv2
import numpy as np


class SegformerFloor:
    def __init__(self, path="models/segformer-ade20k-b0", device="cpu"):
        if device not in {"cpu", "mps"}:
            raise ValueError("TV_MODEL_DEVICE must be cpu or mps")
        if not Path(path).is_dir():
            raise ValueError("Run python -m scripts.prepare_semantic first")
        import torch
        from transformers import AutoImageProcessor, AutoModelForSemanticSegmentation

        self.torch, self.device = torch, device
        self.processor = AutoImageProcessor.from_pretrained(path, local_files_only=True)
        self.model = AutoModelForSemanticSegmentation.from_pretrained(
            path, local_files_only=True
        ).to(device).eval()
        # ADE20K label names depend on checkpoint/version. Do not use numeric IDs.
        labelmap = self.model.config.id2label
        self.floor_ids = {
            int(k) for k, label in labelmap.items()
            if label.lower().strip() in {"floor", "floor, flooring", "carpet", "rug"}
        }
        if not self.floor_ids:
            raise ValueError("No recognized floor label in semantic segmentation checkpoint")

    def floor_mask(self, image):
        from PIL import Image
        h, w = image.shape[:2]
        pil = Image.fromarray(cv2.cvtColor(image, cv2.COLOR_BGR2RGB))
        inputs = self.processor(
            images=pil, return_tensors="pt", size={"height": 256, "width": 256}
        ).to(self.device)
        with self.torch.inference_mode():
            logits = self.model(**inputs).logits
            logits = self.torch.nn.functional.interpolate(
                logits, size=(h, w), mode="bilinear", align_corners=False
            )
            classes = logits.argmax(dim=1)[0].cpu().numpy()
        return np.isin(classes, list(self.floor_ids))
