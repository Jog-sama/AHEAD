"""Read-only live checks and actual local YOLO inference; never arms or steers."""
import argparse
import json
import time
from pathlib import Path

import cv2
import httpx
from dotenv import dotenv_values
from backend.scene_labels import SceneLabeler


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--image", default="tests/fixtures/bus.jpg")
    parser.add_argument("--model", default="models/yolo11n.pt")
    parser.add_argument("--device", default="auto")
    parser.add_argument("--screenshot", action="store_true")
    parser.add_argument("--live", action="store_true")
    args = parser.parse_args()
    image = cv2.imread(args.image)
    if image is None:
        raise SystemExit("Image could not be read")
    if args.screenshot:
        # Camera region of the supplied IMG_8125 screenshot, excluding app text.
        h, w = image.shape[:2]
        image = image[int(h*.155):int(h*.302), int(w*.05):int(w*.95)]
    labeler = SceneLabeler(model_path=args.model, device=args.device)
    runs = []
    for _ in range(4):
        start = time.monotonic()
        objects = labeler._infer(image)
        runs.append({"elapsed_ms": round((time.monotonic()-start)*1000, 1),
                     "objects": objects, "diagnostics": labeler.diagnostics})
    report = {"image": Path(args.image).name, "hardware_actuated": False, "runs": runs}
    if args.live:
        config = dotenv_values(".env")
        with httpx.Client(verify=False, timeout=3) as client:
            # Loopback only; no credentials leave the Mac.
            headers = {"X-API-Key": config.get("TV_API_KEY", "")}
            for route in ("/health", "/api/status", "/api/button"):
                response = client.get("https://127.0.0.1:8443"+route, headers=headers)
                data = response.json()
                if route == "/api/status":
                    data = {k: data.get(k) for k in ("armed", "direction", "commanded_angle", "ack_age_ms", "error")}
                report[route] = {"status": response.status_code, "data": data}
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
