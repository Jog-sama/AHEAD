"""Software-only tests; do not claim real iPhone, Arduino or model inference."""
import json
from pathlib import Path

from fastapi.testclient import TestClient

from backend.app import create_app
from backend.arkit_depth import ARKitPacket
from backend.device import MockDevice
from backend.scene_labels import SceneLabeler
from backend.arkit_depth import ARKitDepthVision
from tests.conftest import KEY
from tests.test_arkit_depth import make_packet

HEADERS = {"X-API-Key": KEY, "content-type": "application/json"}


def test_fusion_uses_measured_depth_without_floor_anchor(monkeypatch):
    pkt = ARKitPacket.model_validate(make_packet(obstacle=(-0.3, 0.3), floor=False))
    labeler = SceneLabeler(model_path="/nonexistent/weights.pt")
    monkeypatch.setattr(labeler, "_infer", lambda img: [{
        "label": "chair", "confidence": .89, "box": [.3, .3, .7, .75],
    }])
    result = labeler.describe(pkt, ARKitDepthVision().predict(pkt))
    assert "chair" in result["phrase"]
    assert "No verified turn" in result["phrase"]
    assert result["objects"][0]["distance_m"] is None or result["objects"][0]["distance_m"] > 0
    assert result["objects"][0]["label"] == "chair"


def test_scene_uses_no_fabricated_classes_if_weights_missing():
    pkt = ARKitPacket.model_validate(make_packet(floor=False))
    answer = SceneLabeler(model_path="/nonexistent/weights.pt").describe(pkt, ARKitDepthVision().predict(pkt))
    assert not answer["objects"]
    assert answer["model_warning"]
    assert "Object naming unavailable" in answer["phrase"]


def test_button_read_auth_and_scene_narration_never_steers(settings, monkeypatch):
    from backend.scene_labels import SceneLabeler
    monkeypatch.setattr(SceneLabeler, "_infer", lambda self, img: [{
        "label": "chair", "confidence": .93, "box": [.25, .25, .75, .75]
    }])
    device = MockDevice()
    device.press_count = 3
    with TestClient(create_app(settings, device=device)) as client:
        assert client.get("/api/button").status_code == 401
        assert client.post("/api/voice/scene", json={}, headers=HEADERS).status_code == 409
        assert client.get("/api/button", headers=HEADERS).json()["press_count"] == 3
        generation = client.post("/api/arm", json={"mode": "obstacle"}, headers=HEADERS).json()["generation"]
        pkt = make_packet(floor=False)
        resp = client.post(f"/api/arkit/frame?generation={generation}&sequence=0",
                           content=json.dumps(pkt), headers=HEADERS)
        assert resp.status_code == 200, resp.text
        n = len(device.calls)
        response = client.post("/api/voice/scene", json={}, headers=HEADERS)
        assert response.status_code == 200, response.text
        assert "chair" in response.json()["phrase"]
        assert response.json()["source"] == "rgb_yolo_plus_arkit_lidar"
        assert len(device.calls) == n  # speaking can't steer or rearm
        client.post("/api/stop", headers=HEADERS)
        assert client.post("/api/voice/scene", json={}, headers=HEADERS).status_code == 409


def test_firmware_button_patch_idempotent():
    from scripts.firmware_button_patch import patch
    firmware = Path(__file__).resolve().parents[1] / "firmware/TactileVector/TactileVector.ino"
    modified = patch(firmware.read_text())
    assert 'server.on("/button"' in modified
    assert 'buttonPressCount++' in modified
    assert modified.count('server.on("/steer"') == 1
    assert patch(modified) == modified


def test_high_quality_rgb_override_and_invalid_payload(monkeypatch, settings):
    from io import BytesIO
    import base64
    import numpy as np
    from PIL import Image
    from backend.scene_labels import decode_scene_jpeg

    large = np.full((840, 1120, 3), 132, dtype=np.uint8)
    stream = BytesIO()
    Image.fromarray(large).save(stream, "JPEG", quality=85)
    jpeg = stream.getvalue()
    assert decode_scene_jpeg(jpeg).shape == (840, 1120, 3)
    assert len(jpeg) < 800000
    monkeypatch.setattr(SceneLabeler, "_infer", lambda self, img: [{
        "label": "laptop", "confidence": .97, "box": [.2, .2, .8, .8]
    }])
    with TestClient(create_app(settings, device=MockDevice())) as c:
        generation = c.post("/api/arm", json={"mode":"obstacle"}, headers=HEADERS).json()["generation"]
        pkt = make_packet(floor=False)
        r = c.post(f"/api/arkit/frame?generation={generation}&sequence=0", content=json.dumps(pkt), headers=HEADERS)
        assert r.status_code == 200
        r = c.post("/api/voice/scene", json={"jpeg_b64": base64.b64encode(jpeg).decode()}, headers=HEADERS)
        assert r.status_code == 200, r.text
        assert "laptop" in r.json()["phrase"]
        assert c.post("/api/voice/scene", json={"jpeg_b64":"not base64?"}, headers=HEADERS).status_code == 422
