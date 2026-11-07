"""Replay a real iPhone LiDAR/pose recording through legacy and temporal cues.

Usage:
    python -m scripts.replay_navigation data/navigation_recordings/arkit_*.jsonl.gz
    python -m scripts.replay_navigation file.jsonl.gz --labels labels.json

Image pixels are NEVER recorded: a neutral synthetic JPEG satisfies the
existing frame decoder but cannot support object-classification evaluation.
"""
from __future__ import annotations

import argparse
import base64
import io
import json
import os
from collections import Counter
from pathlib import Path

from PIL import Image

from backend.arkit_depth import ARKitDepthVision, ARKitPacket
from backend.navigation_recorder import read_recording


def placeholder_jpeg(width: int, height: int) -> str:
    image = Image.new("RGB", (width, height), (128, 128, 128))
    sink = io.BytesIO()
    image.save(sink, "JPEG", quality=50)
    return base64.b64encode(sink.getvalue()).decode("ascii")


def load_labels(path: str | Path | None) -> list[dict]:
    if not path:
        return []
    obj = json.loads(Path(path).read_text())
    spans = obj.get("spans", [])
    for s in spans:
        if (not isinstance(s.get("start"), int) or
            not isinstance(s.get("end"), int) or
            s["end"] < s["start"] or
            not isinstance(s.get("valid"), list) or
            not s["valid"] or
            any(x not in {"left", "center", "right", "unknown"} for x in s["valid"])):
            raise ValueError("Invalid ground truth annotation")
    return spans


def acceptable_for(i: int, spans: list[dict]) -> set[str] | None:
    for span in spans:
        if span["start"] <= i <= span["end"]:
            return set(span["valid"])
    return None


def replay(path: str | Path, labels: str | Path | None = None) -> dict:
    spans = load_labels(labels)
    previous_policy = os.environ.get("TV_NAV_POLICY")
    new, old = ARKitDepthVision(), ARKitDepthVision()
    records = []
    cache: dict[tuple[int, int], str] = {}
    try:
        for i, row in enumerate(read_recording(path)):
            values = dict(row["packet"])
            image_shape = (values["image_width"], values["image_height"])
            if image_shape not in cache:
                cache[image_shape] = placeholder_jpeg(*image_shape)
            values["jpeg_b64"] = cache[image_shape]
            packet = ARKitPacket.model_validate(values)
            os.environ["TV_NAV_POLICY"] = "legacy"
            before = old.predict(packet)
            os.environ["TV_NAV_POLICY"] = "temporal"
            after = new.predict(packet)
            expected = acceptable_for(i, spans)
            records.append({
                "i": i, "sequence": row["sequence"],
                "legacy": before.direction, "temporal": after.direction,
                "valid": sorted(expected) if expected is not None else None,
                "legacy_wrong_specific": expected is not None
                                         and before.direction != "unknown"
                                         and before.direction not in expected,
                "temporal_wrong_specific": expected is not None
                                           and after.direction != "unknown"
                                           and after.direction not in expected,
                "legacy_unknown": before.direction == "unknown",
                "temporal_unknown": after.direction == "unknown",
                "reason": after.reason,
                "map": after.scene.get("navigation_map", {}),
            })
    finally:
        if previous_policy is None:
            os.environ.pop("TV_NAV_POLICY", None)
        else:
            os.environ["TV_NAV_POLICY"] = previous_policy

    summary = {"recording": str(path), "frames": len(records),
               "has_ground_truth": bool(spans), "policies": {}}
    for name in ("legacy", "temporal"):
        choices = [r[name] for r in records]
        summary["policies"][name] = {
            "counts": dict(Counter(choices)),
            "direction_changes": sum(a != b for a, b in zip(choices[:-1], choices[1:])),
            "wrong_specific_when_labeled": sum(r[name + "_wrong_specific"] for r in records),
            "labeled_frames": sum(r["valid"] is not None for r in records),
        }
    summary["warning"] = (
        "Without externally verified traversability annotations, this measures "
        "stability/abstention only; it does NOT establish safe walking directions."
    )
    return {"summary": summary, "frames": records}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("recording", type=Path)
    parser.add_argument("--labels", type=Path, default=None)
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()
    result = replay(args.recording, args.labels)
    print(json.dumps(result["summary"], indent=2))
    if args.output:
        args.output.write_text(json.dumps(result, indent=2))
        print("Wrote per-frame comparison to", args.output)


if __name__ == "__main__":
    main()
