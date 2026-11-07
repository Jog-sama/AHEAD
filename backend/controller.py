import asyncio
import time

from .config import Settings
from .device import Device, DeviceError
from .vision import Decision, phrase_for


class ControlError(RuntimeError):
    pass


class Controller:
    """One operator, one process. Serialized actuator I/O and generation fencing."""

    def __init__(self, settings: Settings, device: Device):
        self.s, self.device = settings, device
        self.lock = asyncio.Lock()
        self.armed = False
        self.mode = "manual"
        self.generation = 0
        self.angle = 90
        self.direction = "unknown"
        self.phrase = "Disarmed. Hold position."
        self.error: str | None = None
        self.last_input = 0.0
        self.last_sequence = -1
        self.last_frame_at = 0.0
        self.last_decision: Decision | None = None
        self.candidate = "unknown"
        self.candidate_count = 0
        self.last_ack: dict | None = None
        self.last_ack_at = 0.0
        self.device_ms: float | None = None
        self.last_turn_at = 0.0

    def snapshot(self) -> dict:
        return dict(
            armed=self.armed,
            mode=self.mode,
            generation=self.generation,
            commanded_angle=self.angle,
            direction=self.direction,
            phrase=self.phrase,
            error=self.error,
            device=self.s.device,
            device_ack=self.last_ack,
            ack_age_ms=(
                round((time.monotonic() - self.last_ack_at) * 1000)
                if self.last_ack_at
                else None
            ),
            device_http_ms=self.device_ms,
            last_sequence=self.last_sequence,
            vision=self.last_decision.json() if self.last_decision else None,
        )

    async def _write(self, angle: int) -> None:
        start = time.monotonic()
        try:
            self.last_ack = await self.device.steer(angle)
            self.last_ack_at = time.monotonic()
            self.device_ms = round((self.last_ack_at - start) * 1000, 2)
            self.angle = angle
            self.error = None
        except DeviceError as exc:
            self.armed = False
            self.generation += 1
            self.direction = "unknown"
            self.phrase = "Device unavailable. Hold position."
            self.error = str(exc)
            # Physical angle is unknown; never report a successful neutral on failed I/O.
            raise

    def _reset_decision(self) -> None:
        self.candidate, self.candidate_count = "unknown", 0
        self.last_sequence = -1
        self.last_frame_at = 0
        self.last_decision = None
        self.direction = "unknown"

    async def arm(self, mode: str) -> dict:
        async with self.lock:
            self.armed = False
            self.generation += 1
            self.mode = mode
            self._reset_decision()
            try:
                await self.device.health()
            except DeviceError as exc:
                self.error = str(exc)
                self.phrase = "Device unavailable. Hold position."
                raise
            await self._write(self.s.center)
            self.armed = True
            self.last_input = time.monotonic()
            self.phrase = "Armed. Awaiting fresh input."
            return self.snapshot()

    async def stop(self, reason: str = "Stopped. Hold position.") -> dict:
        async with self.lock:
            self.armed = False
            self.generation += 1
            self._reset_decision()
            self.phrase = reason
            await self._write(self.s.center)
            return self.snapshot()

    def check(self, generation: int, mode: str) -> None:
        if not self.armed or generation != self.generation or self.mode != mode:
            raise ControlError("Disarmed, stale generation, or wrong mode; arm again")

    async def manual(self, direction: str, generation: int) -> dict:
        async with self.lock:
            self.check(generation, "manual")
            await self._write(getattr(self.s, direction))
            self.last_input = time.monotonic()
            self.direction = direction
            clock = {"left": "10", "center": "12", "right": "2"}[direction]
            self.phrase = f"Manual cue, {clock} o'clock."
            return self.snapshot()

    async def apply_frame(
        self, decision: Decision, generation: int, sequence: int, received_at: float
    ) -> dict:
        async with self.lock:
            if self.mode not in {"cv", "obstacle"}:
                raise ControlError("Camera mode is not armed")
            self.check(generation, self.mode)
            now = time.monotonic()
            max_age = 1.2 if self.mode == "obstacle" else 0.5
            if now - received_at > max_age or sequence <= self.last_sequence:
                raise ControlError("Stale frame discarded")
            self.last_sequence, self.last_frame_at = sequence, now
            self.last_decision = decision
            if decision.direction == self.candidate:
                self.candidate_count += 1
            else:
                self.candidate, self.candidate_count = decision.direction, 1
            # LiDAR's metric evidence permits a two-frame confirmation for a
            # faster stationary demo. RGB obstacle inference remains at one.
            # Unknown and direction changes always neutralize until stable.
            required = (
                (2 if decision.source == "arkit_lidar" else 1)
                if self.mode == "obstacle"
                else 2
            )
            stable = (
                decision.direction != "unknown" and self.candidate_count >= required
            )
            direction = decision.direction if stable else "unknown"
            if decision.source == "arkit_lidar":
                scene = decision.scene or {}
                free = scene.get("free_space", {})
                blocked = scene.get("near_obstacles", {})
                # Keep a previous cue only while CURRENT measurements still
                # support it. Missing evidence or a hazard overrides dwell.
                supported = (
                    self.direction in {"left", "center", "right"}
                    and free.get(self.direction, 0) >= 0.8
                    and not blocked.get(self.direction, True)
                    and not scene.get("emergency_stop", False)
                    and scene.get("tracking") == "normal"
                )
                if supported and (not stable or now - self.last_turn_at < 0.8):
                    direction = self.direction
                if direction != self.direction:
                    self.last_turn_at = now
                stable = direction != "unknown"
            angle = getattr(self.s, direction) if stable else self.s.center
            await self._write(angle)
            self.last_input = time.monotonic()
            self.direction = direction
            # A genuinely measured hazard must be announced even when no safe
            # turn can be proposed or the two-frame turn confirmation is pending.
            # Keep servo neutral; do NOT convert warning into a steering cue.
            hazard = (
                decision.source == "arkit_lidar"
                and decision.scene is not None
                and decision.scene.get("hazard_detected", False)
            )
            self.phrase = decision.phrase if stable or hazard else phrase_for("unknown")
            if stable and direction != decision.direction:
                self.phrase = f"Candidate sightline {direction} remains measured. Route not verified."
            return {**self.snapshot(), "vision": decision.json()}

    async def expire(self) -> None:
        async with self.lock:
            # Camera inference and transport can take longer than manual button events.
            # A missing camera stream still expires and commands neutral. The ESP32
            # retains its independent 800 ms servo-neutral watchdog.
            timeout = (
                max(self.s.input_timeout, 1.6)
                if self.mode == "obstacle"
                else self.s.input_timeout
            )
            if self.armed and time.monotonic() - self.last_input > timeout:
                self.armed = False
                self.generation += 1
                self._reset_decision()
                self.phrase = "Input expired. Hold position."
                try:
                    await self._write(self.s.center)
                except DeviceError:
                    pass  # Independent firmware timeout remains the final software backstop.

    async def watchdog(self) -> None:
        while True:
            await asyncio.sleep(0.05)
            await self.expire()

    def voice(self, question: str) -> dict:
        if self.mode == "obstacle":
            from .spatial_voice import local_answer

            fresh = self.armed and time.monotonic() - self.last_frame_at < 0.7
            return local_answer(
                question, self.last_decision if fresh else None, self.phrase
            )
        text = question.strip().lower().rstrip("?.!")
        if text not in {"status", "clear path", "what is ahead", "what's ahead"}:
            return {
                "phrase": "Object finding unavailable in baseline.",
                "source": "rules",
            }
        if not self.armed:
            return {"phrase": "Disarmed. Hold position.", "source": "rules"}
        if time.monotonic() - self.last_input > self.s.input_timeout:
            return {"phrase": "Input expired. Hold position.", "source": "rules"}
        return {
            "phrase": self.phrase,
            "source": "rules",
            "semantic_scene_understanding": False,
        }
