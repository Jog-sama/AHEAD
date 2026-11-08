import asyncio
import time

import httpx
import pytest

from backend.controller import ControlError, Controller
from backend.device import DeviceError, HttpDevice, MockDevice
from backend.vision import Decision
from scripts.sim_esp32 import create_sim
from tests.conftest import DEVICE_KEY


async def test_device_failure(settings):
    def fail(r):
        raise httpx.ConnectError("offline")

    d = HttpDevice("http://esp", DEVICE_KEY, transport=httpx.MockTransport(fail))
    c = Controller(settings, d)
    with pytest.raises(DeviceError):
        await c.arm("manual")
    assert not c.armed
    await d.close()


@pytest.mark.parametrize(
    "change",
    [
        {"angle": 80},
        {"neutral": 0},
        {"timeout_ms": 9000},
        {"configured": False},
        {"ok": "true"},
        {"failsafe": True},
    ],
)
async def test_bad_ack(change):
    ack = dict(
        ok=True,
        angle=90,
        neutral=90,
        min_angle=60,
        max_angle=120,
        timeout_ms=800,
        configured=True,
        wifi=True,
        failsafe=False,
    )
    ack.update(change)
    d = HttpDevice(
        "http://esp",
        DEVICE_KEY,
        transport=httpx.MockTransport(lambda r: httpx.Response(200, json=ack)),
    )
    with pytest.raises(DeviceError):
        await d.steer(90)
    await d.close()


async def test_pending_frame_after_stop(settings):
    d = MockDevice()
    c = Controller(settings, d)
    gen = (await c.arm("cv"))["generation"]
    received = time.monotonic()
    await c.stop()
    with pytest.raises(ControlError):
        await c.apply_frame(Decision("right", "test", "test"), gen, 0, received)
    assert not c.armed and d.angle == 90


async def test_slow_frame(settings):
    c = Controller(settings, MockDevice())
    gen = (await c.arm("cv"))["generation"]
    with pytest.raises(ControlError):
        await c.apply_frame(Decision("left", "test", "test"), gen, 0, time.monotonic() - 1)


async def test_sim_timeout_invalid():
    sim = create_sim(DEVICE_KEY)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=sim), base_url="http://esp"
    ) as c:
        assert (await c.get("/steer?angle=100")).status_code == 401
        for x in ["-1", "59", "121", "180", "90.5", "nan", "90&angle=100", "90&buzz=1"]:
            assert (
                await c.get(f"/steer?angle={x}", headers={"X-Device-Token": DEVICE_KEY})
            ).status_code == 400
        assert (await c.get("/steer?angle=100", headers={"X-Device-Token": DEVICE_KEY})).json()[
            "angle"
        ] == 100
        await asyncio.sleep(0.82)
        assert (await c.get("/health")).json()["angle"] == 90
        assert (await c.get("/health")).json()["failsafe"]
