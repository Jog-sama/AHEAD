import time
import json
import numpy as np
import pytest
from fastapi.testclient import TestClient
from backend.controller import Controller
from backend.device import MockDevice
from backend.vision import Decision
from backend.scene_labels import SceneLabeler
from backend.app import create_app
from tests.test_arkit_depth import make_packet
from tests.test_scene_voice_button import HEADERS


def cue(direction, blocked=False, tracking="normal"):
    return Decision(direction, "Hold position" if blocked else "Candidate", "test",
                    source="arkit_lidar", scene={
                        "tracking": tracking, "free_space": {"left": 0 if blocked else 1, "right": 1},
                        "near_obstacles": {"left": blocked, "right": False},
                        "hazard_detected": blocked})


@pytest.mark.asyncio
async def test_alternation_dwell_and_immediate_hazard_override(settings):
    c = Controller(settings, MockDevice())
    await c.arm("obstacle")
    async def apply(d, seq):
        return await c.apply_frame(d, c.generation, seq, time.monotonic())
    await apply(cue("left"), 0)
    await apply(cue("left"), 1)
    assert c.direction == "left"
    for seq in range(2, 12):
        await apply(cue("right" if seq % 2 == 0 else "left"), seq)
        assert c.direction == "left"
    await apply(cue("unknown", blocked=True), 12)
    assert c.direction == "unknown" and c.angle == 90
    assert c.phrase == "Hold position"


@pytest.mark.asyncio
async def test_tracking_loss_cannot_keep_old_cue(settings):
    c = Controller(settings, MockDevice())
    await c.arm("obstacle")
    for seq in range(2):
        await c.apply_frame(cue("left"), c.generation, seq, time.monotonic())
    await c.apply_frame(cue("unknown", tracking="limited"), c.generation, 2, time.monotonic())
    assert c.direction == "unknown" and c.angle == 90


@pytest.mark.parametrize("turns", range(4))
def test_rotated_boxes_return_to_sensor_pixels(turns):
    image = np.zeros((100, 200), np.uint8)
    image[20:70, 40:120] = 1
    rotated = np.rot90(image, turns)
    y, x = np.where(rotated)
    h, w = rotated.shape
    box = [x.min()/w, y.min()/h, (x.max()+1)/w, (y.max()+1)/h]
    assert SceneLabeler.sensor_box(box, turns) == pytest.approx([.2, .2, .6, .7])


def test_synchronized_narration_does_not_actuate(settings, monkeypatch):
    monkeypatch.setattr(SceneLabeler, "_infer", lambda self, image: [])
    device = MockDevice()
    with TestClient(create_app(settings, device=device)) as c:
        gen = c.post("/api/arm", json={"mode":"obstacle"}, headers=HEADERS).json()["generation"]
        packet = make_packet()
        c.post(f"/api/arkit/frame?generation={gen}&sequence=0", content=json.dumps(packet), headers=HEADERS)
        count = len(device.calls)
        result = c.post("/api/voice/scene", json={"packet":packet}, headers=HEADERS)
        assert result.status_code == 200
        assert result.json()["depth_alignment"] == "same_capture"
        assert len(device.calls) == count
        packet["tracking"] = "limited"
        assert c.post("/api/voice/scene", json={"packet":packet}, headers=HEADERS).status_code == 409


@pytest.mark.asyncio
async def test_emergency_center_stop_overrides_supported_side(settings):
    c = Controller(settings, MockDevice())
    await c.arm("obstacle")
    for seq in range(2):
        await c.apply_frame(cue("left"), c.generation, seq, time.monotonic())
    emergency = cue("unknown")
    emergency.scene["emergency_stop"] = True
    await c.apply_frame(emergency, c.generation, 2, time.monotonic())
    assert c.angle == 90 and c.direction == "unknown"


def test_stop_during_recognition_discards_narration(settings, monkeypatch):
    with TestClient(create_app(settings, device=MockDevice())) as c:
        gen = c.post("/api/arm", json={"mode":"obstacle"}, headers=HEADERS).json()["generation"]
        packet = make_packet()
        c.post(f"/api/arkit/frame?generation={gen}&sequence=0", content=json.dumps(packet), headers=HEADERS)
        def describe(*args):
            c.post("/api/stop", headers=HEADERS)
            return {"phrase":"Old scene", "objects":[]}
        monkeypatch.setattr(SceneLabeler, "describe", describe)
        assert c.post("/api/voice/scene", json={"packet":packet}, headers=HEADERS).status_code == 409
