"""Synthetic regression tests for the robustness patch; not physical mobility validation."""
import asyncio
import time

import numpy as np
import pytest

from backend.arkit_depth import ARKitDepthVision, ARKitPacket, unproject_world
from backend.controller import Controller
from backend.device import MockDevice
from tests.test_arkit_depth import make_packet


def test_center_open_when_far_floor_unobserved():
    pkt = make_packet()
    fwd, _, _, _, _ = unproject_world(ARKitPacket.model_validate(pkt))
    depth = np.asarray(pkt["depth_m"])
    depth[(fwd > 1.45).ravel()] = 0.0
    pkt["depth_m"] = depth.tolist()
    result = ARKitDepthVision().predict(ARKitPacket.model_validate(pkt))
    assert result.direction == "center"
    assert result.scene["corridor_bands"]["center"][2]["floor_points"] == 0
    assert result.scene["confidence_kind"] != "traversability_probability"


@pytest.mark.parametrize(("obstacle", "expected"), [
    ((-1.15, -0.45), "right"), ((0.45, 1.15), "left"),
])
def test_offset_obstacle_steers_away_with_missing_far_floor(obstacle, expected):
    pkt = make_packet(obstacle)
    fwd, _, _, _, _ = unproject_world(ARKitPacket.model_validate(pkt))
    d = np.asarray(pkt["depth_m"])
    d[(fwd > 1.45).ravel()] = 0.0
    pkt["depth_m"] = d.tolist()
    result = ARKitDepthVision().predict(ARKitPacket.model_validate(pkt))
    assert result.direction == expected
    assert result.scene["hazard_detected"]


def test_center_obstacle_explicit_warning_even_if_no_supported_exit():
    decision = ARKitDepthVision().predict(ARKitPacket.model_validate(make_packet((-.3, .3))))
    assert decision.direction == "unknown"
    assert decision.scene["hazard_detected"]
    assert decision.scene["near_obstacles"]["center"]
    assert "Nearby obstacle" in decision.reason


def test_missing_ground_evidence_still_abstains():
    pkt = make_packet()
    pkt["depth_m"] = [0.0] * len(pkt["depth_m"])
    decision = ARKitDepthVision().predict(ARKitPacket.model_validate(pkt))
    assert decision.direction == "unknown"


@pytest.mark.asyncio
async def test_obstacle_watchdog_allows_processing_interval_but_still_expires(settings):
    c = Controller(settings, MockDevice())
    await c.arm("obstacle")
    c.last_input = time.monotonic() - 0.9
    await c.expire()
    assert c.armed, "0.9s LiDAR gap should not produce first-run 409"
    c.last_input = time.monotonic() - 2.0
    await c.expire()
    assert not c.armed
    assert c.angle == 90


@pytest.mark.asyncio
async def test_manual_watchdog_remains_short(settings):
    c = Controller(settings, MockDevice())
    await c.arm("manual")
    c.last_input = time.monotonic() - 0.9
    await c.expire()
    assert not c.armed
    assert c.angle == 90
