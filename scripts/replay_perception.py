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
    p.add_argument("--frames", type=int, default=30, help="Evenly spaced samples over the COMPLETE clip (max 500)")
    p.add_argument("--device", choices=["cpu", "mps"], default="cpu")
    args = p.parse_args()
    models = NeuralModels("models/yolo11n.pt", "models/depth-anything-v2-small", device=args.device)
    vision = ObstacleVision(models)
    is_video = Path(args.input).suffix.lower() in {".mov", ".mp4", ".m4v", ".avi", ".mkv"}
    cap = cv2.VideoCapture(args.input) if is_video else None
    image = None if is_video else cv2.imread(args.input)
    if cap is not None:
        if not cap.isOpened():
            raise SystemExit("Could not open input video")
        if hasattr(cv2, "CAP_PROP_ORIENTATION_AUTO"):
            cap.set(cv2.CAP_PROP_ORIENTATION_AUTO, 1)
        total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        fps = float(cap.get(cv2.CAP_PROP_FPS))
        if total <= 0 or fps <= 0:
            raise SystemExit("Video metadata has no usable frame count or FPS")
        count = min(max(args.frames, 1), 500, total)
        # Include early, middle, and FINAL frames; consecutive frames only cover ~1s.
        indices = [round((total - 1) * i / (count - 1)) for i in range(count)] if count > 1 else [0]
    else:
        indices = [0] if image is not None else []
        fps = 0.0
    results = []
    for i, frame_index in enumerate(indices):
        if cap is not None:
            cap.set(cv2.CAP_PROP_POS_FRAMES, frame_index)
            ok, image = cap.read()
            if not ok:
                raise SystemExit(f"Video frame decode failed at {frame_index}")
        h, w = image.shape[:2]
        scale = min(640 / w, 480 / h, 1)
        resized = cv2.resize(image, (round(w * scale), round(h * scale)))
        data = cv2.imencode(".jpg", resized)[1].tobytes()
        started = time.monotonic()
        decision = vision.predict(data)
        results.append(
            {
                "frame": i,
                "source_frame": frame_index,
                "time_s": round(frame_index / fps, 3) if fps else None,
                "decoded_size": [w, h],
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
        json.dumps({"input": args.input, "hardware_tested": False, "rgb_only_no_arkit_depth": True, "sampling": "full_video_evenly_spaced", "frames": results}, indent=2)
    )
    print(f"{len(results)} frame(s) analyzed without hardware: {target}")


if __name__ == "__main__":
    main()
