"""Synthetic navigation regressions. NOT proof of blind walking safety."""
from collections import deque

import numpy as np

from backend.arkit_depth import ARKitDepthVision, ARKitPacket
from tests.test_arkit_depth import make_packet


def predict(vision, obstacle=None, **kwargs):
    return vision.predict(ARKitPacket.model_validate(make_packet(obstacle, **kwargs)))


def test_center_priority_instead_of_side_swerves(monkeypatch):
    monkeypatch.setenv("TV_NAV_POLICY", "temporal")
    nav = ARKitDepthVision()
    directions = [predict(nav, obs).direction for obs in
                  [(-1.15, -.45), (.45, 1.15)] * 4]
    assert directions == ["center"] * 8
    monkeypatch.setenv("TV_NAV_POLICY", "legacy")
    legacy_nav = ARKitDepthVision()
    legacy = [predict(legacy_nav, obs).direction for obs in
              [(-1.15, -.45), (.45, 1.15)] * 4]
    assert legacy == ["right", "left"] * 4
    assert sum(legacy[i] != legacy[i - 1] for i in range(1, len(legacy))) == 7


def test_center_obstacle_not_guessed_side(monkeypatch):
    monkeypatch.setenv("TV_NAV_POLICY", "temporal")
    nav = ARKitDepthVision()
    for _ in range(5):
        result = predict(nav, (-.3, .3), floor=False)
        assert result.direction == "unknown"
        assert result.scene["near_obstacles"]["center"]
        assert "OBSTACLE AHEAD" in result.phrase
    assert result.scene["navigation_map"]["frames"] == 5


def test_obstacle_persists_over_one_clear_depth_frame(monkeypatch):
    monkeypatch.setenv("TV_NAV_POLICY", "temporal")
    nav = ARKitDepthVision()
    assert predict(nav, (-.3, .3)).direction == "unknown"
    result = predict(nav)
    assert result.direction == "unknown"
    assert result.scene["navigation_map"]["frames"] == 2
    nav.reset()
    recovered = predict(nav)
    assert recovered.direction == "center"
    assert recovered.scene["navigation_map"]["frames"] == 1


def test_floorless_depth_not_treated_as_verified_route(monkeypatch):
    monkeypatch.setenv("TV_NAV_POLICY", "temporal")
    result = predict(ARKitDepthVision(), floor=False)
    assert result.direction == "center"
    assert result.scene["floor_required"] is False
    assert "no verified walking path" in result.scene["navigation_map"]["warning"]


def test_tracking_loss_clears_history(monkeypatch):
    monkeypatch.setenv("TV_NAV_POLICY", "temporal")
    nav = ARKitDepthVision()
    predict(nav, (-.3, .3))
    assert predict(nav, tracking="limited").direction == "unknown"
    fresh = predict(nav)
    assert fresh.direction == "center"
    assert fresh.scene["navigation_map"]["frames"] == 1


def test_missing_confidence_abstains_and_resets(monkeypatch):
    monkeypatch.setenv("TV_NAV_POLICY", "temporal")
    nav = ARKitDepthVision()
    predict(nav)
    assert predict(nav, confidence=0).direction == "unknown"
    assert predict(nav).scene["navigation_map"]["frames"] == 1


def test_pose_rotation_reprojects_world_history(monkeypatch):
    monkeypatch.setenv("TV_NAV_POLICY", "temporal")
    nav = ARKitDepthVision()
    pkt = make_packet(obstacle=(-.3, .3))
    assert nav.predict(ARKitPacket.model_validate(pkt)).direction == "unknown"
    pose = np.array(pkt["camera_to_world"]).reshape(4, 4, order="F")
    yaw = np.deg2rad(3)
    rotation = np.array([[np.cos(yaw), 0, np.sin(yaw)],
                         [0, 1, 0], [-np.sin(yaw), 0, np.cos(yaw)]])
    pose[:3, :3] = rotation @ pose[:3, :3]
    pkt["camera_to_world"] = pose.flatten(order="F").tolist()
    result = nav.predict(ARKitPacket.model_validate(pkt))
    assert result.direction == "unknown"
    assert result.scene["navigation_map"]["frames"] == 2


def test_memory_bounded(monkeypatch):
    monkeypatch.setenv("TV_NAV_POLICY", "temporal")
    nav = ARKitDepthVision()
    for _ in range(25):
        result = predict(nav)
    assert result.scene["navigation_map"]["frames"] <= 9
    nav.reset()
    assert nav.navigation.frames == deque()
