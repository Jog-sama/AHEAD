"""Depth-only obstacle evidence: synthetic scenes, not physical validation."""
import json

import numpy as np
import pytest
from fastapi.testclient import TestClient

from backend.app import create_app
from backend.arkit_depth import ARKitDepthVision, ARKitPacket, unproject_world
from backend.device import MockDevice
from tests.conftest import KEY
from tests.test_arkit_depth import make_packet


@pytest.mark.parametrize(("obstacle", "expected"), [
    (None, "center"),
    ((-1.15, -0.45), "center"),
    ((0.45, 1.15), "center"),
    ((-0.3, 0.3), "unknown"),
])
def test_floorless_direct_depth(obstacle, expected):
    pkt = ARKitPacket.model_validate(make_packet(obstacle=obstacle, floor=False))
    decision = ARKitDepthVision().predict(pkt)
    assert decision.direction == expected
    assert decision.scene["floor_required"] is False
    assert decision.scene["floor_source"] == "not_required"
    if obstacle:
        assert decision.scene["hazard_detected"]
    if obstacle == (-0.3, 0.3):
        assert decision.scene["near_obstacles"]["center"]
        assert "OBSTACLE AHEAD" in decision.phrase
        assert "Nearby obstacle" in decision.reason


def test_no_floor_does_not_elevate_missing_depth_to_clear():
    pkt = make_packet(floor=False)
    pkt["depth_m"] = [0.0] * len(pkt["depth_m"])
    result = ARKitDepthVision().predict(ARKitPacket.model_validate(pkt))
    assert result.direction == "unknown"
    assert not result.scene.get("hazard_detected", False)


def test_single_spurious_close_ray_is_not_an_obstacle():
    pkt = make_packet(floor=False)
    # One noisy LiDAR pixel cannot be corroborated by a spatial cluster.
    pkt["depth_m"][30*80 + 40] = 0.65
    result = ARKitDepthVision().predict(ARKitPacket.model_validate(pkt))
    assert not result.scene["hazard_detected"]


def test_floor_anchor_optional_even_if_far_ground_depth_missing():
    pkt = make_packet(floor=False)
    # Depth-only sensing with limited range still responds to a nearby obstacle.
    obstructed = make_packet(obstacle=(-0.3, 0.3), floor=False)
    result = ARKitDepthVision().predict(ARKitPacket.model_validate(obstructed))
    assert result.scene["near_obstacles"]["center"]


def test_floorless_hazard_phrase_reaches_controller_without_steering(settings):
    pkt = make_packet(obstacle=(-0.3, 0.3), floor=False)
    payload = json.dumps(pkt).encode()
    with TestClient(create_app(settings, device=MockDevice())) as client:
        headers = {"X-API-Key": KEY, "content-type": "application/json"}
        state = client.post("/api/arm", json={"mode":"obstacle"}, headers=headers)
        assert state.status_code == 200
        generation = state.json()["generation"]
        for seq in range(2):
            res = client.post(
                f"/api/arkit/frame?generation={generation}&sequence={seq}",
                content=payload, headers=headers,
            )
            assert res.status_code == 200
            assert res.json()["direction"] == "unknown"
            assert res.json()["commanded_angle"] == 90
            assert "OBSTACLE AHEAD" in res.json()["phrase"]
