import json
from types import SimpleNamespace

import pytest

from backend.tinker_voice import TinkerVoice
from backend.vision import Decision
from scripts.train_spatial import load_split
from tests.conftest import frame


@pytest.mark.parametrize(
    "response,source",
    [
        ("Chair, 10 o'clock. Distance unknown.", "tinker"),
        ("Walk forward three meters.", "local_guard"),
        ("Door, 2 o'clock.", "local_guard"),
    ],
)
async def test_tinker_grounding_guard(response, source):
    voice = TinkerVoice()

    class Renderer:
        def build_generation_prompt(self, messages):
            assert messages[1]["content"][1]["image_url"]["url"].startswith("data:image/jpeg;")
            return "prompt"

        def get_stop_sequences(self):
            return ["stop"]

        def parse_response(self, tokens):
            return {"content": response}, None

    class Client:
        async def sample(self, **kwargs):
            return SimpleNamespace(sequences=[SimpleNamespace(tokens=[1])])

    voice.renderer = Renderer()
    voice.client = Client()
    voice.sdk = SimpleNamespace(SamplingParams=lambda **kwargs: kwargs)
    d = Decision(
        "unknown",
        "hold",
        "test",
        scene={"objects": [{"label": "chair", "confidence": 0.9, "box": [0.05, 0.2, 0.25, 0.8]}]},
    )
    result = await voice.describe(frame("left"), "where is the chair", d, "hold")
    assert result["source"] == source
    assert result["phrase"] == "Chair, 10 o'clock. Distance unknown."


def test_dataset_split_has_no_scene_overlap(tmp_path):
    (tmp_path / "scene.jpg").write_bytes(frame("left"))
    rows = [
        {
            "scene_id": str(i),
            "image": "scene.jpg",
            "question": "what is ahead",
            "answer": "Scene uncertain. Hold position.",
            "source_url": "https://example.test/source",
            "license": "CC0",
            "derivation": "test fixture",
        }
        for i in range(5)
    ]
    path = tmp_path / "dataset.jsonl"
    path.write_text("\n".join(map(json.dumps, rows)))
    train, held = load_split(path)
    assert not {r["scene_id"] for r in train} & {r["scene_id"] for r in held}
    rows[0]["answer"] = "one two three four five six seven eight nine"
    path.write_text("\n".join(map(json.dumps, rows)))
    with pytest.raises(ValueError):
        load_split(path)
