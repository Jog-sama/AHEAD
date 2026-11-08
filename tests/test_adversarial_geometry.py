"""Independent geometric raycast tests. Simulated depth is NOT real-phone validation."""
from __future__ import annotations

import numpy as np
import pytest

from backend.arkit_depth import ARKitDepthVision
from scripts.adversarial_geometry import Box, packet


@pytest.mark.parametrize("height", (.07, .08, .10, .12, .18, .35))
@pytest.mark.parametrize("distance", (.6, .95, 1.45))
def test_low_and_mid_height_block_in_front(height, distance, monkeypatch):
    monkeypatch.setenv("TV_NAV_POLICY", "temporal")
    obstacle = Box((-.19, 0., -distance-.14), (.19, height, -distance))
    result = ARKitDepthVision().predict(packet([obstacle]))
    assert result.direction != "center", (height, distance, result.scene)


@pytest.mark.parametrize("obstacle", (
    Box((-1.15, .16, -1.6), (-.47, 1.9, -.62)),
    Box((.47, .16, -1.6), (1.15, 1.9, -.62)),
))
def test_side_obstacle_does_not_force_turn(obstacle, monkeypatch):
    monkeypatch.setenv("TV_NAV_POLICY", "temporal")
    nav = ARKitDepthVision()
    for yaw in (0., 2.5, -2.5, .6, -1.8):
        p = packet([obstacle], yaw=yaw, jitter=.025)
        assert nav.predict(p).direction == "center"


@pytest.mark.parametrize("noise", (0., .01, .03))
@pytest.mark.parametrize("dropout", (0., .15, .4))
def test_low_obstacle_stays_non_center_during_noise_and_dropout(noise, dropout, monkeypatch):
    monkeypatch.setenv("TV_NAV_POLICY", "temporal")
    nav = ARKitDepthVision()
    rng = np.random.default_rng(135)
    block = Box((-.18, 0., -1.23), (.18, .085, -1.1))
    for i in range(5):
        d = nav.predict(packet([block], yaw=(i%3-1)*2.0,
                               jitter=noise, dropout=dropout, rng=rng))
        assert d.direction != "center"


@pytest.mark.parametrize("noise", (0., .01, .03))
@pytest.mark.parametrize("dropout", (0., .15, .4))
def test_clean_corridor_does_not_swerve_due_to_lidar_noise(noise, dropout, monkeypatch):
    monkeypatch.setenv("TV_NAV_POLICY", "temporal")
    nav = ARKitDepthVision()
    rng = np.random.default_rng(246)
    for i in range(5):
        d = nav.predict(packet([], yaw=(-1)**i*3.0,
                               jitter=noise, dropout=dropout, rng=rng))
        assert d.direction in ("center", "unknown")


def test_missing_ground_returns_does_not_assert_route(monkeypatch):
    monkeypatch.setenv("TV_NAV_POLICY", "temporal")
    p = packet([], floor=False)
    d = ARKitDepthVision().predict(p)
    assert d.direction == "unknown"
    assert d.scene.get("valid_depth_fraction") == 0.0


def test_obstacle_close_to_sensor_triggers_emergency_stop(monkeypatch):
    monkeypatch.setenv("TV_NAV_POLICY", "temporal")
    p = packet([Box((-.43, .15, -.5), (.43, 1.4, -.35))])
    d = ARKitDepthVision().predict(p)
    assert d.direction == "unknown"
    assert d.scene["emergency_stop"]


def test_nearby_hazard_does_not_expire_after_one_missing_frame(monkeypatch):
    monkeypatch.setenv("TV_NAV_POLICY", "temporal")
    nav = ARKitDepthVision()
    b = Box((-.3, .12, -1.2), (.3, 1.45, -1.0))
    assert nav.predict(packet([b])).direction != "center"
    assert nav.predict(packet([])).direction != "center"
