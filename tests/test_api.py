import time

import httpx
import pytest
from fastapi.testclient import TestClient

from backend.app import create_app
from backend.device import HttpDevice, MockDevice
from scripts.sim_esp32 import create_sim
from tests.conftest import DEVICE_KEY, KEY, frame

HEADERS = {"X-API-Key": KEY}


def test_auth_and_static(settings):
    with TestClient(create_app(settings)) as c:
        assert c.get("/").status_code == 200
        assert c.get("/health").json()["device"] == "mock"
        assert c.post("/api/arm", json={"mode": "manual"}).status_code == 401
        assert not c.get("/api/status", headers=HEADERS).json()["armed"]
        assert "frame-ancestors 'none'" in c.get("/").headers["content-security-policy"]


def test_manual_stop_and_generation(settings):
    d = MockDevice()
    with TestClient(create_app(settings, d)) as c:
        gen = c.post("/api/arm", json={"mode": "manual"}, headers=HEADERS).json()["generation"]
        r = c.post("/api/steer", json={"direction": "left", "generation": gen}, headers=HEADERS)
        assert r.json()["commanded_angle"] == 80
        assert c.post("/api/stop", headers=HEADERS).json()["commanded_angle"] == 90
        assert (
            c.post(
                "/api/steer", json={"direction": "right", "generation": gen}, headers=HEADERS
            ).status_code
            == 409
        )
        assert d.angle == 90


def test_backend_idle_timeout(settings):
    d = MockDevice()
    with TestClient(create_app(settings, d)) as c:
        gen = c.post("/api/arm", json={"mode": "manual"}, headers=HEADERS).json()["generation"]
        c.post("/api/steer", json={"direction": "right", "generation": gen}, headers=HEADERS)
        time.sleep(0.85)
        state = c.get("/api/status", headers=HEADERS).json()
        assert not state["armed"] and d.angle == 90
        assert "expired" in state["phrase"]


@pytest.mark.parametrize("lane,angle", [("left", 80), ("center", 90), ("right", 100)])
def test_camera_backend_simulated_esp32(settings, lane, angle):
    sim = create_sim(DEVICE_KEY)
    device = HttpDevice("http://esp32", DEVICE_KEY, transport=httpx.ASGITransport(app=sim))
    with TestClient(create_app(settings, device)) as c:
        gen = c.post("/api/arm", json={"mode": "cv"}, headers=HEADERS).json()["generation"]
        for seq in range(2):
            r = c.post(
                f"/api/frame?generation={gen}&sequence={seq}",
                content=frame(lane),
                headers={**HEADERS, "Content-Type": "image/jpeg"},
            )
            assert r.status_code == 200
            assert r.json()["commanded_angle"] == (90 if seq == 0 else angle)
        assert sim.state.angle == angle
        assert r.json()["vision"]["direction"] == lane
        r = c.post(
            f"/api/frame?generation={gen}&sequence=2",
            content=frame(),
            headers={**HEADERS, "Content-Type": "image/jpeg"},
        )
        assert r.json()["commanded_angle"] == 90 and sim.state.angle == 90


def test_frame_replay_and_bounds(settings):
    with TestClient(create_app(settings)) as c:
        gen = c.post("/api/arm", json={"mode": "cv"}, headers=HEADERS).json()["generation"]
        path = f"/api/frame?generation={gen}&sequence=0"
        h = {**HEADERS, "Content-Type": "image/jpeg"}
        assert c.post(path, content=frame("left"), headers=h).status_code == 200
        assert c.post(path, content=frame("left"), headers=h).status_code == 409
        assert c.post(path, content=b"a" * 400001, headers=h).status_code == 413
        assert c.post(path, content=b"no", headers=h).status_code == 422
        assert c.post(path, content=frame(), headers=HEADERS).status_code == 415
        assert (
            c.post(
                "/api/steer", json={"direction": "banana", "generation": gen}, headers=HEADERS
            ).status_code
            == 422
        )
        assert (
            c.post(
                "/api/steer", json={"direction": "left", "generation": True}, headers=HEADERS
            ).status_code
            == 422
        )


def test_audio_and_voice_truthfulness(settings):
    with TestClient(create_app(settings)) as c:
        r = c.post(
            "/api/audio",
            content=b"transport-test",
            headers={**HEADERS, "Content-Type": "audio/mp4"},
        )
        assert r.json()["transcription"] is None and not r.json()["stored"]
        assert r.json()["received_bytes"] == 14
        assert (
            c.post(
                "/api/audio",
                content=b"x" * 1000001,
                headers={**HEADERS, "Content-Type": "audio/mp4"},
            ).status_code
            == 413
        )
        assert (
            c.post("/api/voice", json={"text": "where is the door"}, headers=HEADERS).json()[
                "phrase"
            ]
            == "Object finding unavailable in baseline."
        )
        assert (
            c.post("/api/voice", json={"text": "status"}, headers=HEADERS).json()["phrase"]
            == "Disarmed. Hold position."
        )
