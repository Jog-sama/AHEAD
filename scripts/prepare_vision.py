"""Explicit one-time model download and warm-up. Never called by camera requests."""

import json
from pathlib import Path


def main():
    from transformers import AutoImageProcessor, AutoModelForDepthEstimation
    from ultralytics import YOLO

    root = Path("models")
    root.mkdir(exist_ok=True)
    YOLO(str(root / "yolo11n.pt"))
    model_id = "depth-anything/Depth-Anything-V2-Small-hf"
    target = root / "depth-anything-v2-small"
    AutoImageProcessor.from_pretrained(model_id).save_pretrained(target)
    AutoModelForDepthEstimation.from_pretrained(model_id).save_pretrained(target)
    (root / "sources.json").write_text(
        json.dumps(
            {
                "detector": "Ultralytics YOLO11n (COCO)",
                "depth": model_id,
                "depth_units": "relative inverse depth; not meters",
            },
            indent=2,
        )
    )
    from backend.obstacles import NeuralModels

    NeuralModels(root / "yolo11n.pt", target)
    print("Models downloaded and warm-up inference completed. Restart the backend.")


if __name__ == "__main__":
    main()
