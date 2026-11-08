"""Download the attributed sources and make scene-grouped spatial voice examples."""

import argparse
import io
import json
import urllib.request
from pathlib import Path

from PIL import Image, ImageOps


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--sources", default="datasets/spatial_voice_sources.json")
    p.add_argument("--output", default="data/tinker-spatial")
    args = p.parse_args()
    output = Path(args.output)
    images = output / "images"
    images.mkdir(parents=True, exist_ok=True)
    rows = []
    for source in json.loads(Path(args.sources).read_text()):
        request = urllib.request.Request(source["url"], headers={"User-Agent": "AHEAD/1.0"})
        with urllib.request.urlopen(request, timeout=30) as response:
            original = Image.open(io.BytesIO(response.read())).convert("RGB")
        fitted = ImageOps.contain(original, (360, 420))
        for clock, x in (("10", 16), ("12", 140), ("2", 264)):
            canvas = Image.new("RGB", (640, 480), (38, 42, 47))
            canvas.paste(fitted, (x, (480 - fitted.height) // 2))
            name = f"{source['id']}-{clock}.jpg"
            canvas.save(images / name, quality=88, optimize=True)
            rows.append({
                "scene_id": source["id"],
                "image": f"images/{name}",
                "question": f"where is the {source['label']}",
                "answer": f"{source['label'].capitalize()}, {clock} o'clock. Distance unknown.",
                "source_url": source["source_url"],
                "license": source["license"],
                "author": source["author"],
                "derivation": (
                    "Source image letterboxed left/center/right; distance intentionally unknown"
                ),
            })
    dataset = output / "dataset.jsonl"
    dataset.write_text("\n".join(json.dumps(row) for row in rows) + "\n")
    (output / "ATTRIBUTION.json").write_text(Path(args.sources).read_text())
    print(f"Prepared {len(rows)} examples from {len(rows) // 3} licensed scenes at {dataset}")


if __name__ == "__main__":
    main()
