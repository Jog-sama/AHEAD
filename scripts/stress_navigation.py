"""Randomized LiDAR geometry stress audit. Not real-world walking validation."""
from __future__ import annotations
import argparse
import json
import time
from collections import Counter
import numpy as np
from backend.arkit_depth import ARKitDepthVision
from scripts.adversarial_geometry import Box, packet

def audit(cases=180, seed=20261107):
    rng = np.random.default_rng(seed)
    counts, failures, timings = Counter(), [], []
    for i in range(cases):
        category = ("center_block", "side_block", "clear", "no_ground", "no_confidence")[i % 5]
        distance = float(rng.uniform(.55, 1.48))
        height = float(rng.uniform(.055, .40))
        width = float(rng.uniform(.27, .60))
        noise = float(rng.uniform(0, .03))
        dropout = float(rng.uniform(0, .43))
        yaw = float(rng.uniform(-3.5, 3.5))
        if category == "center_block":
            boxes = [Box((-width/2, 0., -distance-.17),
                         (width/2, height, -distance))]
        elif category == "side_block":
            side = -1 if rng.random() < .5 else 1
            a, b = (-1.3, -.52) if side < 0 else (.52, 1.3)
            boxes = [Box((a, .14, -distance-.6), (b, 1.8, -distance))]
        else:
            boxes = []
        nav = ARKitDepthVision()
        decisions = []
        for frame in range(4):
            kw = dict(yaw=yaw + float(rng.uniform(-2.0, 2.0)),
                      jitter=noise, dropout=dropout, rng=rng,
                      x=float(frame) * .015)
            if category == "no_ground":
                kw["floor"] = False
            if category == "no_confidence":
                kw["confidence"] = 0
            started = time.perf_counter()
            result = nav.predict(packet(boxes, **kw))
            timings.append((time.perf_counter() - started) * 1000)
            decisions.append(result.direction)
            counts[f"{category}:{result.direction}"] += 1
        failure = None
        if category == "center_block" and "center" in decisions:
            failure = "obstacle_false_center"
        elif category in ("clear", "side_block") and any(
            d in ("left", "right") for d in decisions
        ):
            failure = "unnecessary_side_turn"
        elif category in ("no_ground", "no_confidence") and "center" in decisions:
            failure = "missing_depth_false_center"
        if failure:
            failures.append(dict(case=i, kind=failure,
                                 distance_m=round(distance, 3),
                                 height_m=round(height, 3),
                                 width_m=round(width, 3),
                                 noise_m=round(noise, 3),
                                 dropout=round(dropout, 3),
                                 yaw_deg=round(yaw, 2), directions=decisions))
    return {
        "type": "synthetic_raycast_not_validated_walking",
        "seed": seed, "cases": cases, "frames": cases*4,
        "counts": dict(sorted(counts.items())),
        "failure_count": len(failures),
        "failure_examples": failures[:40],
        "latency_ms": {
            "median": round(float(np.median(timings)), 2),
            "p95": round(float(np.percentile(timings, 95)), 2)},
        "limitations": "Simplified axis-aligned boxes, approximate camera pose, no real ARKit noise, no glass/stairs/drop-offs, no pedestrian route labels.",
    }

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--cases", type=int, default=180)
    p.add_argument("--seed", type=int, default=20261107)
    p.add_argument("--fail-on-critical", action="store_true")
    a = p.parse_args()
    if not 5 <= a.cases <= 2000:
        p.error("cases must be 5..2000")
    result = audit(a.cases, a.seed)
    print("STRESS_NAVIGATION_JSON=" + json.dumps(result))
    if a.fail_on_critical and result["failure_count"]:
        raise SystemExit("Critical synthetic navigation failures reported")

if __name__ == "__main__":
    main()
