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


def test_old_sightline_cannot_authorize_route_after_current_occlusion():
    """Old observations may veto a turn, never authorize a currently unseen one."""
    import time
    from backend.navigation_map import TemporalNavigationMap, _Frame

    packet = ARKitPacket.model_validate(make_packet())
    nav = TemporalNavigationMap()
    origin, forward, right = nav._basis(packet)
    now = time.monotonic()
    # Dense, three-dimensional world-space visibility sampled near and mid.
    center_points = np.array([
        origin + x * right + z * forward
        for z in (.50, .66, .79, 1.00, 1.16, 1.32)
        for x in (-.16, 0., .16)
    ])
    nav.frames.append(_Frame(now, origin.copy(), center_points,
                             np.full(len(center_points), 3, dtype=np.int8),
                             near_depth_points={"center": 12}))
    first = nav.evaluate(packet, now)
    assert first["direction"] == "center", first
    # Phone now sees a different region; the historical center ray evidence
    # still exists, but must not be treated as CURRENT permission to proceed.
    side_points = np.array([
        origin - 1.25 * right + z * forward for z in (.5, .7, 1.0, 1.2)
    ])
    nav.frames.append(_Frame(now + .1, origin.copy(), side_points,
                             np.full(len(side_points), 3, dtype=np.int8)))
    second = nav.evaluate(packet, now + .1)
    assert second["direction"] == "unknown", second
    assert second["evidence"]["center"]["current_support"] is False
    assert second["frames"] == 2



def test_distant_rays_cannot_authorize_unobserved_near_corridor(monkeypatch):
    """Reproduces real-phone log: high overall depth, zero near depth, false center."""
    from backend.arkit_depth import unproject_camera_relative

    monkeypatch.setenv("TV_NAV_POLICY", "temporal")
    original = ARKitPacket.model_validate(make_packet())
    forward, lateral, _, good = unproject_camera_relative(original)
    pkt = make_packet()
    # Remove only actual LiDAR endpoints inside 0.35-0.90m while retaining
    # far observations. Older code projected those distant rays into the near
    # lane and incorrectly returned 'center' with a confidence of 1.
    near = good & (forward >= .35) & (forward < .90)
    depth = np.asarray(pkt["depth_m"], dtype=float).reshape(forward.shape)
    depth[near] = 0.
    pkt["depth_m"] = depth.ravel().tolist()
    nav = ARKitDepthVision()
    decision = nav.predict(ARKitPacket.model_validate(pkt))
    assert decision.direction == "unknown", decision.scene
    info = decision.scene["navigation_map"]
    assert info["near_coverage"]["center"]["measured_depth_points"] == 0
    assert info["near_coverage"]["center"]["confirmed"] is False
    assert "Near walking corridor not directly observed" in info["reason"]
    assert decision.scene["free_space"]["center"] == 0.0


def test_direct_near_floor_evidence_is_reported(monkeypatch):
    monkeypatch.setenv("TV_NAV_POLICY", "temporal")
    result = predict(ARKitDepthVision())
    info = result.scene["navigation_map"]["near_coverage"]["center"]
    assert info["measured_depth_points"] >= 8
    assert info["confirmed"] is True
    assert result.direction == "center"
