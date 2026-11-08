"""Validate sourced image data, run bounded Tinker SFT, and evaluate it.

JSONL rows require scene_id, image, question, answer (<=8 words), source_url,
license, and derivation. Scene IDs are kept wholly in train or held-out data.
"""

import argparse
import asyncio
import json
import math
import re
from pathlib import Path

from PIL import Image

from backend.tinker_voice import messages_for


def load_split(path):
    rows = [json.loads(line) for line in Path(path).read_text().splitlines() if line.strip()]
    required = ("scene_id", "image", "question", "answer", "source_url", "license", "derivation")
    for row in rows:
        if not all(isinstance(row.get(k), str) and row[k].strip() for k in required):
            raise ValueError("Each row requires content plus source_url, license and derivation")
        if len(row["answer"].split()) > 8:
            raise ValueError("Answers must be at most eight words")
        image = Path(path).resolve().parent / row["image"]
        with Image.open(image) as decoded:
            if decoded.format not in {"JPEG", "PNG"}:
                raise ValueError("Images must be JPEG or PNG")
            decoded.verify()
        row["image"] = str(image)
    scenes = sorted({r["scene_id"] for r in rows})
    if len(scenes) < 5:
        raise ValueError("At least five independent scenes are required")
    held = set(scenes[-max(1, math.ceil(len(scenes) * 0.2)) :])
    train = [r for r in rows if r["scene_id"] not in held]
    test = [r for r in rows if r["scene_id"] in held]
    return train, test


def response_text(message):
    content = (
        message.get("content")
        if isinstance(message, dict)
        else getattr(message, "content", None)
    )
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        return "".join(
            p.get("text", "") if isinstance(p, dict) else getattr(p, "text", "")
            for p in content
        ).strip()
    return ""


async def sample_row(client, renderer, tinker, row):
    prompt = renderer.build_generation_prompt(
        messages_for(Path(row["image"]).read_bytes(), row["question"])
    )
    result = await client.sample(
        prompt=prompt,
        num_samples=1,
        sampling_params=tinker.SamplingParams(
            max_tokens=48, temperature=0, stop=renderer.get_stop_sequences()
        ),
    )
    message, _ = renderer.parse_response(result.sequences[0].tokens)
    return response_text(message)


def score(rows):
    exact = sum(r["prediction"] == r["answer"] for r in rows)
    unsafe = re.compile(r"\b(walk|go|move|turn|meters?|feet|safe|clear path)\b", re.I)
    safe = sum(
        len(r["prediction"].split()) <= 8 and not unsafe.search(r["prediction"])
        for r in rows
    )
    return {
        "examples": len(rows),
        "exact_match": exact / len(rows),
        "safe_format": safe / len(rows),
    }


async def evaluate(service, renderer, tinker, model, checkpoint, held, output):
    base = await service.create_sampling_client(base_model=model)
    tuned = await service.create_sampling_client(model_path=checkpoint)
    details = []
    for row in held:
        base_text, tuned_text = await asyncio.gather(
            sample_row(base, renderer, tinker, row), sample_row(tuned, renderer, tinker, row)
        )
        details.append({
            "scene_id": row["scene_id"], "question": row["question"], "answer": row["answer"],
            "base_prediction": base_text, "tuned_prediction": tuned_text,
        })
    report = {
        "baseline": score([{**r, "prediction": r["base_prediction"]} for r in details]),
        "fine_tuned": score([{**r, "prediction": r["tuned_prediction"]} for r in details]),
        "rows": details,
    }
    (output / "evaluation.json").write_text(json.dumps(report, indent=2))
    return report


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
    service = tinker.ServiceClient(display_name="AHEAD spatial voice SFT")
    client = await service.create_lora_training_client(base_model=args.model, rank=16, seed=42)
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
                record = {"step": steps, "metrics": result.metrics}
                log.write(json.dumps(record, default=str) + "\n")
                log.flush()
                steps += 1
    checkpoint = await client.save_weights_for_sampler(name="ahead-spatial-voice")
    report = await evaluate(service, renderer, tinker, args.model, checkpoint.path, held, output)
    metadata = {
        "model": args.model, "checkpoint": checkpoint.path, "steps": steps,
        "training_scenes": sorted({r["scene_id"] for r in rows}),
        "heldout_scenes": sorted({r["scene_id"] for r in held}),
        "evaluation": {"baseline": report["baseline"], "fine_tuned": report["fine_tuned"]},
    }
    (output / "checkpoint.json").write_text(json.dumps(metadata, indent=2))
    print(json.dumps(metadata, indent=2))


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("dataset")
    p.add_argument("--run", action="store_true", help="Start paid training with Tinker credentials")
    p.add_argument("--model", default="thinkingmachines/Inkling-2-Small")
    p.add_argument("--output", default="data/tinker-training")
    p.add_argument("--epochs", type=int, choices=range(1, 6), default=2)
    p.add_argument("--max-steps", type=int, choices=range(1, 101), default=20)
    p.add_argument("--lr", type=float, default=1e-4)
    args = p.parse_args()
    rows, held = load_split(args.dataset)
    print(f"Validated {len(rows)} train / {len(held)} held-out examples, split by scene.")
    if args.run:
        asyncio.run(train(args, rows, held))
    else:
        print("Validation only. No API calls or charges. Add --run to train and evaluate.")


if __name__ == "__main__":
    main()
