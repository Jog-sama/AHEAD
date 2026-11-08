import time
from typing import Protocol

import httpx
from pydantic import BaseModel, ConfigDict, StrictBool, StrictInt


class DeviceError(RuntimeError):
    pass


class Ack(BaseModel):
    model_config = ConfigDict(extra="ignore")
    ok: StrictBool
    angle: StrictInt
    neutral: StrictInt
    min_angle: StrictInt
    max_angle: StrictInt
    timeout_ms: StrictInt
    configured: StrictBool
    wifi: StrictBool
    failsafe: StrictBool


class Device(Protocol):
    async def steer(self, angle: int) -> dict: ...
    async def health(self) -> dict: ...
    async def close(self) -> None: ...


class HttpDevice:
    def __init__(
        self,
        url: str,
        token: str,
        timeout: float = 0.35,
        transport: httpx.AsyncBaseTransport | None = None,
    ):
        self.client = httpx.AsyncClient(
            base_url=url.rstrip("/"),
            headers={"X-Device-Token": token},
            timeout=timeout,
            transport=transport,
            follow_redirects=False,
            trust_env=False,
        )

    async def _get(self, path: str, angle: int | None = None) -> dict:
        try:
            r = await self.client.get(path, params={"angle": angle} if angle is not None else None)
            r.raise_for_status()
            ack = Ack.model_validate(r.json())
            if not ack.ok or not ack.configured or not ack.wifi:
                raise ValueError("Device not ready")
            if (
                ack.neutral != 90
                or ack.min_angle != 60
                or ack.max_angle != 120
                or not 100 <= ack.timeout_ms <= 800
            ):
                raise ValueError("Firmware safety contract differs")
            if angle is not None and (ack.angle != angle or ack.failsafe):
                raise ValueError("Device did not acknowledge requested command")
            return ack.model_dump()
        except (httpx.HTTPError, ValueError, TypeError) as exc:
            # Do not leak URLs, auth headers, or response bodies into UI errors.
            raise DeviceError(
                "ESP32 unavailable or unsafe acknowledgement; check power/network"
            ) from exc

    async def steer(self, angle: int) -> dict:
        if not 60 <= angle <= 120:
            raise DeviceError("Angle outside 60..120")
        return await self._get("/steer", angle)

    async def health(self) -> dict:
        return await self._get("/health")

    async def button(self) -> dict:
        """Authenticated, read-only physical button event counter."""
        try:
            response = await self.client.get("/button", timeout=0.6)
            response.raise_for_status()
            obj = response.json()
            count = obj.get("press_count")
            if isinstance(count, bool) or not isinstance(count, int) or not 0 <= count <= 4294967295:
                raise ValueError("Invalid press counter")
            return {"press_count": count, "pressed": obj.get("pressed") is True}
        except (httpx.HTTPError, ValueError, TypeError, AttributeError) as exc:
            raise DeviceError("ESP32 button endpoint unreachable or invalid; check device power and Wi-Fi") from exc

    async def close(self) -> None:
        await self.client.aclose()


class MockDevice:
    """Software-only timeout model; no physical servo."""

    def __init__(self):
        self.angle = 90
        self.last = time.monotonic()
        self.calls: list[int] = []

    async def steer(self, angle: int) -> dict:
        if not 60 <= angle <= 120:
            raise DeviceError("Angle outside 60..120")
        self.angle, self.last = angle, time.monotonic()
        self.calls.append(angle)
        self.calls = self.calls[-100:]
        return await self.health()

    async def health(self) -> dict:
        expired = time.monotonic() - self.last > 0.8
        if expired:
            self.angle = 90
        return dict(
            ok=True,
            angle=self.angle,
            neutral=90,
            min_angle=75,
            max_angle=105,
            timeout_ms=800,
            configured=True,
            wifi=True,
            failsafe=expired,
            mock=True,
        )

    async def button(self) -> dict:
        return {"press_count": getattr(self, "press_count", 0), "pressed": False}

    async def close(self) -> None:
        pass
