"""Run real perception on an image/video without connecting to any actuator."""

import argparse
import json
import time
from pathlib import Path

import cv2

from backend.obstacles import NeuralModels, ObstacleVision


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("input", help="JPEG/PNG or a local video")
    p.add_argument("--output", default="data/replay.json")
    p.add_argument("--frames", type=int, default=30)
    args = p.parse_args()
    models = NeuralModels("models/yolo11n.pt", "models/depth-anything-v2-small")
    vision = ObstacleVision(models)
    image = cv2.imread(args.input)
    cap = None if image is not None else cv2.VideoCapture(args.input)
    results = []
    for i in range(min(max(args.frames, 1), 500)):
        if cap is not None:
            ok, image = cap.read()
            if not ok:
                break
        h, w = image.shape[:2]
        scale = min(640 / w, 480 / h, 1)
        resized = cv2.resize(image, (round(w * scale), round(h * scale)))
        data = cv2.imencode(".jpg", resized)[1].tobytes()
        started = time.monotonic()
        decision = vision.predict(data)
        results.append(
            {
                "frame": i,
                "inference_ms": round((time.monotonic() - started) * 1000, 2),
                "decision": decision.json(),
            }
        )
        if cap is None:
            break
    if cap is not None:
        cap.release()
    if not results:
        raise SystemExit("No readable frames")
    target = Path(args.output)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps({"input": args.input, "hardware_tested": False, "frames": results}, indent=2)
    )
    print(f"{len(results)} frame(s) analyzed without hardware: {target}")


if __name__ == "__main__":
    main()
