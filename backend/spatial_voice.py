"""Grounded, short object callouts. Voice never authorizes motor commands."""

import re


def grounded_candidates(question, decision, cue):
    """Return phrases derived only from current perception, never model invention."""
    if decision is None:
        return ["Scene stale. Hold position."]
    text = question.lower().strip().rstrip("?.!")
    if text in {"status", "clear path", "is the path clear"}:
        return [cue]
    scene = decision.scene or {}
    objects = [o for o in scene.get("objects", []) if o.get("confidence", 0) >= 0.5]
    find = re.match(r"(?:where(?:'s| is)|find|locate)(?: the| a| an)? (.+)", text)
    if find:
        target = find.group(1).strip()
        objects = [o for o in objects if o["label"].lower() == target]
        if not objects:
            return ["Target not reliably detected."]
        if len(objects) > 1:
            return ["Multiple targets. Please check visually."]
    phrases = []
    for obj in sorted(objects, key=lambda o: o["confidence"], reverse=True):
        x = (obj["box"][0] + obj["box"][2]) / 2
        clock = "10" if x < 1 / 3 else "2" if x > 2 / 3 else "12"
        phrase = f"{obj['label'].capitalize()}, {clock} o'clock. Distance unknown."
        if phrase not in phrases:
            phrases.append(phrase)
    return phrases[:6] or ["Scene uncertain. Hold position."]


def local_answer(question, decision, cue):
    base = {
        "source": "local_scene_rules",
        "semantic_scene_understanding": True,
        "direction": "unknown",
        "metric_distance": None,
    }
    return {**base, "phrase": grounded_candidates(question, decision, cue)[0]}
