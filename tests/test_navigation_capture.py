"""Capture/replay tests validate what we can collect from the actual iPhone path.

All payloads here are SYNTHETIC; real sensor evaluation requires user recording.
"""
from __future__ import annotations

import gzip
import json

from fastapi.testclient import TestClient

from backend.app import create_app
from backend.device import MockDevice
from backend.navigation_recorder import NavigationRecorder, read_recording
from scripts.replay_navigation import replay
from tests.conftest import KEY
from tests.test_arkit_depth import make_packet


def test_records_no_images_and_replays_policies(tmp_path):
    r = NavigationRecorder(enabled=True, directory=str(tmp_path))
    assert r.path is not None
    packet = make_packet()
    from backend.arkit_depth import ARKitPacket
    r.capture(ARKitPacket.model_validate(packet), 12)
    r.capture(ARKitPacket.model_validate(packet), 13)
    r.close()
    rows = list(read_recording(r.path))
    assert len(rows) == 2
    assert [x["sequence"] for x in rows] == [12, 13]
    for row in rows:
        assert "jpeg_b64" not in row["packet"]
        assert "image" not in row
        assert "depth_m" in row["packet"]
        assert "camera_to_world" in row["packet"]
        assert "intrinsics" in row["packet"]
    result = replay(r.path)
    assert result["summary"]["frames"] == 2
    assert not result["summary"]["has_ground_truth"]
    assert result["summary"]["policies"]["temporal"]["counts"]["center"] == 2


def test_labels_measure_wrong_specific_without_claiming_safety(tmp_path):
    r = NavigationRecorder(enabled=True, directory=str(tmp_path))
    from backend.arkit_depth import ARKitPacket
    for seq in range(3):
        r.capture(ARKitPacket.model_validate(make_packet()), seq)
    r.close()
    labels = tmp_path / "labels.json"
    labels.write_text(json.dumps({"spans":[{"start":0, "end":2, "valid":["unknown"]}]}))
    result = replay(r.path, labels)
    assert result["summary"]["has_ground_truth"]
    assert result["summary"]["policies"]["temporal"]["labeled_frames"] == 3
    assert result["summary"]["policies"]["temporal"]["wrong_specific_when_labeled"] == 3


def test_native_api_opt_in_recording_preserves_endpoint(tmp_path, monkeypatch, settings):
    monkeypatch.setenv("TV_RECORD_ARKIT", "1")
    monkeypatch.setenv("TV_RECORD_DIR", str(tmp_path))
    body = json.dumps(make_packet()).encode()
    headers = {"X-API-Key": KEY, "content-type": "application/json"}
    with TestClient(create_app(settings, device=MockDevice())) as client:
        generation = client.post("/api/arm", json={"mode":"obstacle"},
                                 headers=headers).json()["generation"]
        for sequence in range(3):
            response = client.post(f"/api/arkit/frame?generation={generation}&sequence={sequence}",
                                   content=body, headers=headers)
            assert response.status_code == 200
    recordings = list(tmp_path.glob("*.jsonl.gz"))
    assert len(recordings) == 1
    rows = list(read_recording(recordings[0]))
    assert len(rows) == 3
    assert [r["sequence"] for r in rows] == [0, 1, 2]
    assert not any("jpeg_b64" in row["packet"] for row in rows)
