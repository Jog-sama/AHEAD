"""Validate/split real labeled image data, then explicitly run bounded Tinker SFT.

JSONL rows: scene_id, image (local JPEG path), question, answer (<=8 words).
No invented training examples, credentials, success logs, or trained checkpoint.
"""

import argparse
import asyncio
import json
import math
from pathlib import Path

from backend.tinker_voice import messages_for
from backend.vision import decode_frame


def load_split(path):
    rows = [json.loads(line) for line in Path(path).read_text().splitlines() if line.strip()]
    for row in rows:
        if not all(
            isinstance(row.get(k), str) and row[k].strip()
            for k in ("scene_id", "image", "question", "answer")
        ):
            raise ValueError("Each row requires scene_id, image, question and answer")
        if len(row["answer"].split()) > 8:
            raise ValueError("Answers must be at most eight words")
        image = Path(path).resolve().parent / row["image"]
        decode_frame(image.read_bytes())
        row["image"] = str(image)
    scenes = sorted({r["scene_id"] for r in rows})
    if len(scenes) < 2:
        raise ValueError("At least two independent scenes required for held-out evaluation")
    held = set(scenes[-max(1, math.ceil(len(scenes) * 0.2)) :])
    return (
        [r for r in rows if r["scene_id"] not in held],
        [r for r in rows if r["scene_id"] in held],
    )


async def train(args, rows, held):
    import tinker
    from tinker_cookbook import model_info
    from tinker_cookbook.renderers import get_renderer
    from tinker_cookbook.supervised.common import datum_from_model_input_weights
    from tinker_cookbook.tokenizer_utils import get_tokenizer

    renderer = get_renderer(
        model_info.get_recommended_renderer_name(args.model), get_tokenizer(args.model)
    )
    data = []
    for row in rows:
        messages = messages_for(Path(row["image"]).read_bytes(), row["question"])
        messages.append({"role": "assistant", "content": row["answer"]})
        model_input, weights = renderer.build_supervised_example(messages)
        data.append(datum_from_model_input_weights(model_input, weights))
    client = await tinker.ServiceClient().create_lora_training_client(
        base_model=args.model, rank=16
    )
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    (output / "heldout.json").write_text(json.dumps(held, indent=2))
    steps = 0
    with (output / "training.jsonl").open("w") as log:
        for _ in range(args.epochs):
            for i in range(0, len(data), 4):
                if steps >= args.max_steps:
                    break
                result = await client.forward_backward(data[i : i + 4], "cross_entropy")
                await client.optim_step(tinker.AdamParams(learning_rate=args.lr))
                log.write(json.dumps({"step": steps, "metrics": result.metrics}) + "\n")
                log.flush()
                steps += 1
    checkpoint = await client.save_weights_for_sampler(name="tactilevector-spatial")
    (output / "checkpoint.json").write_text(
        json.dumps(
            {
                "model": args.model,
                "checkpoint": checkpoint.path,
                "steps": steps,
                "evaluation": "not run",
                "training_scenes": sorted({r["scene_id"] for r in rows}),
            },
            indent=2,
        )
    )
    print("Saved checkpoint metadata. Evaluate on held-out scenes before using it in a demo.")


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("dataset")
    p.add_argument("--run", action="store_true", help="Start paid training with TINKER_API_KEY")
    p.add_argument("--model", default="thinkingmachines/Inkling-2-Small")
    p.add_argument("--output", default="data/tinker-training")
    p.add_argument("--epochs", type=int, choices=range(1, 6), default=1)
    p.add_argument("--max-steps", type=int, choices=range(1, 101), default=20)
    p.add_argument("--lr", type=float, default=1e-4)
    args = p.parse_args()
    rows, held = load_split(args.dataset)
    print(f"Validated {len(rows)} train / {len(held)} held-out examples, split by scene.")
    if args.run:
        asyncio.run(train(args, rows, held))
    else:
        print("Validation only. No API calls or charges. Add --run to train.")


if __name__ == "__main__":
    main()
