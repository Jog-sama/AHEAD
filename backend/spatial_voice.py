"""Grounded, short object callouts. Voice never authorizes motor commands."""

import re


def local_answer(question, decision, cue):
    base = {
        "source": "local_scene_rules",
        "semantic_scene_understanding": True,
        "direction": "unknown",
        "metric_distance": None,
    }
    if decision is None:
        return {**base, "phrase": "Scene stale. Hold position."}
    text = question.lower().strip().rstrip("?.!")
    if text in {"status", "clear path", "is the path clear"}:
        return {**base, "phrase": cue}
    scene = decision.scene or {}
    objects = [o for o in scene.get("objects", []) if o.get("confidence", 0) >= 0.5]
    find = re.match(r"(?:where(?:'s| is)|find|locate)(?: the| a| an)? (.+)", text)
    if find:
        target = find.group(1).strip()
        objects = [o for o in objects if o["label"].lower() == target]
        if not objects:
            return {**base, "phrase": "Target not reliably detected."}
        if len(objects) > 1:
            return {**base, "phrase": "Multiple targets. Please check visually."}
    if not objects:
        return {**base, "phrase": "Scene uncertain. Hold position."}
    obj = max(objects, key=lambda o: o["confidence"])
    x = (obj["box"][0] + obj["box"][2]) / 2
    clock = "10" if x < 1 / 3 else "2" if x > 2 / 3 else "12"
    return {**base, "phrase": f"{obj['label'].capitalize()}, {clock} o'clock. Distance unknown."}
