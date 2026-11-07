import asyncio
import time
from dataclasses import replace

import numpy as np
import pytest
from fastapi.testclient import TestClient

from backend.app import create_app
from backend.controller import ControlError, Controller
from backend.device import MockDevice
from backend.hazards import HazardOutbox
from backend.obstacles import ObstacleVision, choose_direction
from backend.spatial_voice import local_answer
from backend.vision import Decision
from tests.conftest import KEY, frame

H = {"X-API-Key": KEY}


@pytest.mark.parametrize(
    "free,blocked,confidence,expected",
    [
        ([0.1, 0.9, 0.95], [0.6, 0, 0], 0.9, "right"),
        ([0.95, 0.9, 0.1], [0, 0, 0.6], 0.9, "left"),
        ([0.95, 0.1, 0.3], [0, 0.8, 0.5], 0.9, "left"),
        ([0.3, 0.1, 0.95], [0.5, 0.8, 0], 0.9, "right"),
        ([0.95, 0.1, 0.95], [0, 0.8, 0], 0.9, "unknown"),
        ([0.1, 0.1, 0.1], [0.8, 0.8, 0.8], 0.9, "unknown"),
        ([0.95, 0.95, 0.95], [0, 0, 0], 0.3, "unknown"),
        ([0.95, 0.95, 0.95], [0, 0, 0], 0.9, "center"),
        ([float("nan"), 0.95, 0.95], [0, 0, 0], 0.9, "unknown"),
        ([1.1, 0.95, 0.95], [0, 0, 0], 0.9, "unknown"),
    ],
)
def test_direction_policy(free, blocked, confidence, expected):
    assert choose_direction(free, blocked, confidence)[0] == expected


def synthetic_scene(lane=None):
    image = np.full((240, 320, 3), 130, np.uint8)
    depth = np.repeat(np.linspace(0, 1, 240)[:, None], 320, axis=1).astype(np.float32)
    objects = []
    if lane is not None:
        x1, x2 = lane * 106 + 14, lane * 106 + 90
        image[112:220, x1:x2] = [30, 50, 200]
        depth[112:220, x1:x2] = 1.2
        objects = [
            {"label": "chair", "confidence": 0.9, "box": [x1 / 320, 112 / 240, x2 / 320, 220 / 240]}
        ]
    return image, objects, depth


@pytest.mark.parametrize(
    "lane,expected", [(None, "center"), (0, "right"), (1, "unknown"), (2, "left")]
)
def test_synthetic_floor_and_obstacle_geometry(lane, expected):
    decision = ObstacleVision().analyze(*synthetic_scene(lane))
    assert decision.direction == expected, decision.json()
    assert decision.scene["metric_distance"] is None


def test_wall_depth_drop_and_invalid_fail_closed():
    image, objs, depth = synthetic_scene()
    vision = ObstacleVision()
    assert vision.analyze(image, objs, np.ones_like(depth)).direction == "unknown"
    assert vision.analyze(image, objs, depth[::-1]).direction == "unknown"
    depth[170:190, :] = -1  # A drop/unsupported band blocks every route.
    assert vision.analyze(image, objs, depth).direction == "unknown"
    depth[0, 0] = float("nan")
    assert vision.analyze(image, objs, depth).direction == "unknown"


def test_no_models_never_follows_green_or_claims_depth():
    for side in [None, "left", "center", "right"]:
        d = ObstacleVision().predict(frame(side))
        assert d.direction == "unknown"


async def test_debounce_reverse_and_unknown(settings):
    d = MockDevice()
    c = Controller(settings, d)
    gen = (await c.arm("obstacle"))["generation"]
    decision = Decision("right", "Opening right.", "left blocked", source="test")
    for seq in range(3):
        r = await c.apply_frame(decision, gen, seq, time.monotonic())
        assert r["commanded_angle"] == (100 if seq == 2 else 90)
    for seq in range(3, 5):
        r = await c.apply_frame(replace(decision, direction="left"), gen, seq, time.monotonic())
        assert r["commanded_angle"] == 90
    r = await c.apply_frame(replace(decision, direction="unknown"), gen, 5, time.monotonic())
    assert r["commanded_angle"] == 90
    await c.stop()
    with pytest.raises(ControlError):
        await c.apply_frame(decision, gen, 6, time.monotonic())


async def test_stop_during_inference_keeps_neutral(settings):
    c = Controller(settings, MockDevice())
    gen = (await c.arm("obstacle"))["generation"]
    received = time.monotonic()

    async def inference():
        await asyncio.sleep(0.04)
        return await c.apply_frame(Decision("right", "right", "test"), gen, 0, received)

    task = asyncio.create_task(inference())
    await c.stop()
    with pytest.raises(ControlError):
        await task
    assert c.device.angle == 90


def test_obstacle_api_contract_and_voice(settings, tmp_path):
    class Perception:
        def predict(self, jpeg):
            return Decision(
                "right",
                "Opening right.",
                "left blocked",
                source="test",
                scene={
                    "objects": [
                        {"label": "chair", "confidence": 0.9, "box": [0.05, 0.4, 0.2, 0.9]}
                    ],
                    "blocked": {"left": 0.6},
                    "confidence": 0.9,
                },
            )

    d = MockDevice()
    box = HazardOutbox(tmp_path / "events.sqlite3")
    with TestClient(create_app(settings, d, obstacle_vision=Perception(), hazard_outbox=box)) as c:
        gen = c.post("/api/arm", json={"mode": "obstacle"}, headers=H).json()["generation"]
        for seq in range(3):
            r = c.post(
                f"/api/frame?generation={gen}&sequence={seq}",
                content=frame("left"),
                headers={**H, "Content-Type": "image/jpeg"},
            )
            assert r.status_code == 200
        assert r.json()["commanded_angle"] == 100
        assert (
            "10 o'clock"
            in c.post("/api/voice", json={"text": "where is the chair"}, headers=H).json()["phrase"]
        )
        assert c.get("/api/hazards", headers=H).json()["events"][0]["simulated"]
        assert c.post("/api/voice/tinker", json={"text": "status"}, headers=H).status_code == 503
        c.post("/api/stop", headers=H)
        assert "stale" in c.post("/api/voice", json={"text": "status"}, headers=H).json()["phrase"]


def test_voice_unknown_object_never_invents_distance():
    d = Decision("unknown", "uncertain", "test", scene={"objects": []})
    assert (
        local_answer("where is the door", d, "uncertain")["phrase"]
        == "Target not reliably detected."
    )
    assert (
        local_answer("what is ahead", None, "uncertain")["phrase"] == "Scene stale. Hold position."
    )


def test_location_validation(settings, tmp_path, monkeypatch):
    monkeypatch.setenv("TV_OBSTACLE_ENGINE", "opencv")
    with TestClient(create_app(settings, hazard_outbox=HazardOutbox(tmp_path / "events.db"))) as c:
        assert (
            c.post(
                "/api/location", json={"latitude": 91, "longitude": 0, "accuracy": 2}, headers=H
            ).status_code
            == 422
        )
        assert (
            c.post(
                "/api/location", json={"latitude": 36, "longitude": -78, "accuracy": 2}, headers=H
            ).status_code
            == 200
        )
        assert c.delete("/api/location", headers=H).status_code == 200


async def test_outbox_persistence_dedup_retry(tmp_path):
    box = HazardOutbox(tmp_path / "events.db")
    d = Decision(
        "unknown",
        "uncertain",
        "blocked",
        scene={
            "objects": [{"label": "chair", "confidence": 0.9}],
            "blocked": {"center": 0.6},
            "confidence": 0.8,
        },
    )
    assert box.observe(d, False)
    assert box.observe(d, False) is None
    assert len(HazardOutbox(tmp_path / "events.db").list()) == 1

    class Sender:
        calls = 0

        async def send(self, event):
            self.calls += 1
            return self.calls > 1

    sender = Sender()
    assert not await box.deliver_one(sender)
    assert box.list()[0]["attempts"] == 1
    with box.connect() as db:
        db.execute("UPDATE events SET next_try=0")
    assert await box.deliver_one(sender)
    assert box.list()[0]["delivered"]
