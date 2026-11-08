import asyncio
import base64
import binascii
import os
import secrets
import time
from contextlib import asynccontextmanager, suppress
from pathlib import Path
from typing import Literal

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field

from .adapters import InformerWebhook
from .arkit_depth import ARKitDepthVision, ARKitPacket, MAX_FRAME_BYTES, parse_packet
from .config import Settings
from .controller import ControlError, Controller
from .device import Device, DeviceError, HttpDevice, MockDevice
from .hazards import HazardOutbox
from .obstacles import ObstacleVision
from .speech import LocalWhisper, Transcriber
from .scene_labels import SceneLabeler
from .tinker_voice import TinkerVoice
from .vision import MarkerVision, VisionAdapter

WEB = Path(__file__).resolve().parent.parent / "web"


class ArmRequest(BaseModel):
    mode: Literal["manual", "cv", "obstacle"]


class SteerRequest(BaseModel):
    model_config = ConfigDict(strict=True)
    direction: Literal["left", "center", "right"]
    generation: int = Field(ge=0)


class VoiceRequest(BaseModel):
    text: str = Field(min_length=1, max_length=200)


class SceneImageRequest(BaseModel):
    # High-resolution RGB is sent ONLY when the user explicitly presses talk.
    # The fast LiDAR frame endpoint and existing Safari camera stay unchanged.
    jpeg_b64: str | None = Field(default=None, max_length=1_100_000)
    packet: ARKitPacket | None = None


class LocationRequest(BaseModel):
    latitude: float = Field(ge=-90, le=90, allow_inf_nan=False)
    longitude: float = Field(ge=-180, le=180, allow_inf_nan=False)
    accuracy: float = Field(ge=0, le=10000, allow_inf_nan=False)


async def limited_body(request: Request, limit: int) -> bytes:
    chunks, size = [], 0
    async for chunk in request.stream():
        size += len(chunk)
        if size > limit:
            raise HTTPException(413, f"Request exceeds {limit} bytes")
        chunks.append(chunk)
    return b"".join(chunks)


def create_app(
    settings: Settings | None = None,
    device: Device | None = None,
    vision: VisionAdapter | None = None,
    transcriber: Transcriber | None = None,
    obstacle_vision: VisionAdapter | None = None,
    hazard_outbox: HazardOutbox | None = None,
) -> FastAPI:
    s = settings or Settings.from_env()
    d = device or (
        MockDevice()
        if s.device == "mock"
        else HttpDevice(s.esp32_url, s.device_token, s.request_timeout)
    )
    controller = Controller(s, d)
    detector = vision or MarkerVision()
    obstacle_detector = obstacle_vision or ObstacleVision.from_env()
    arkit_detector = ARKitDepthVision(getattr(obstacle_detector, "models", None))
    frame_lock = asyncio.Lock()
    speech_lock = asyncio.Lock()
    outbox = hazard_outbox or HazardOutbox(os.getenv("TV_HAZARD_DB", "data/hazards.sqlite3"))
    location = {}
    latest = {}
    tinker_voice = TinkerVoice()
    scene_labeler = SceneLabeler()
    scene_voice_lock = asyncio.Lock()
    export_error = None
    sender = None
    if os.getenv("TV_INFORMER_AUTO_SEND") == "1":
        try:
            sender = InformerWebhook(
                os.getenv("TV_INFORMER_WEBHOOK_URL", ""),
                os.getenv("TV_INFORMER_WEBHOOK_SECRET", ""),
            )
        except ValueError:
            export_error = "Invalid Informer URL or secret; events kept locally"
    speech = transcriber
    if speech is None and os.getenv("TV_WHISPER_MODEL"):
        speech = LocalWhisper(os.environ["TV_WHISPER_MODEL"])

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        # Load and prime the object model before accepting camera input. A cold
        # GPU compilation must not compete with the first active servo stream.
        if settings is None and scene_labeler.model_path.is_file():
            import numpy as np
            try:
                await asyncio.to_thread(scene_labeler._infer, np.zeros((768, 768, 3), dtype=np.uint8))
            except Exception:
                pass  # Narration reports the actual error; LiDAR stays usable.
        task = asyncio.create_task(controller.watchdog())
        exporter = asyncio.create_task(outbox.run(sender)) if sender else None
        try:
            yield
        finally:
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task
            if exporter:
                exporter.cancel()
                with suppress(asyncio.CancelledError):
                    await exporter
            with suppress(DeviceError):
                await controller.stop("Server shutting down.")
            await d.close()

    app = FastAPI(
        title="TactileVector",
        version="0.1.0",
        lifespan=lifespan,
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )
    app.state.controller = controller

    async def authorize(x_api_key: str = Header(default="")) -> None:
        if not secrets.compare_digest(x_api_key, s.api_key):
            raise HTTPException(401, "Enter the local API key from .env")

    auth = [Depends(authorize)]

    @app.middleware("http")
    async def headers(request: Request, call_next):
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Permissions-Policy"] = (
            "camera=(self), microphone=(self), geolocation=(self)"
        )
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self'; style-src 'self'; "
            "img-src 'self' blob:; media-src 'self' blob:; connect-src 'self'; "
            "frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
        )
        return response

    @app.exception_handler(DeviceError)
    async def device_error(request: Request, exc: DeviceError):
        return JSONResponse(
            status_code=503, content={"detail": str(exc), "state": controller.snapshot()}
        )


    @app.exception_handler(ControlError)
    async def control_error(request: Request, exc: ControlError):
        print(
            f"[TACTILEVECTOR 409] {exc} | "
            f"armed={controller.armed} | "
            f"mode={controller.mode} | "
            f"generation={controller.generation}",
            flush=True,
        )
        return JSONResponse(
            status_code=409,
            content={"detail": str(exc)}
        )

    @app.get("/")
    async def index():
        return FileResponse(WEB / "index.html")

    @app.get("/health")
    async def health():
        return {
            "ok": True,
            "service": "tactilevector",
            "device": s.device,
            "scope": "stationary supervised demo",
        }

    @app.get("/api/status", dependencies=auth)
    async def status():
        return {
            **controller.snapshot(),
            "perception": {
                "engine": "neural"
                if getattr(obstacle_detector, "models", None)
                else "observation_only",
                "model_error": getattr(obstacle_detector, "unavailable_reason", None),
            },
            "informer": {"enabled": sender is not None, "error": export_error},
            "tinker": {
                "enabled": os.getenv("TV_TINKER_ENABLED") == "1",
                "checkpoint_configured": bool(os.getenv("TV_TINKER_CHECKPOINT")),
            },
        }

    @app.get("/api/hazards", dependencies=auth)
    async def hazards():
        return {
            "events": await asyncio.to_thread(outbox.list),
            "export_enabled": sender is not None,
            "error": export_error,
        }

    @app.post("/api/location", dependencies=auth)
    async def set_location(body: LocationRequest):
        location.update(body.model_dump(), received=time.monotonic())
        return {"ok": True, "expires_seconds": 60}

    @app.delete("/api/location", dependencies=auth)
    async def clear_location():
        location.clear()
        return {"ok": True}

    @app.post("/api/arm", dependencies=auth)
    async def arm(body: ArmRequest):
        return await controller.arm(body.mode)

    @app.post("/api/stop", dependencies=auth)
    async def stop():
        return await controller.stop()

    @app.post("/api/steer", dependencies=auth)
    async def steer(body: SteerRequest):
        return await controller.manual(body.direction, body.generation)

    @app.post("/api/frame", dependencies=auth)
    async def frame(request: Request, generation: int, sequence: int):
        if sequence < 0:
            raise HTTPException(422, "sequence must be nonnegative")
        if request.headers.get("content-type", "").split(";")[0] != "image/jpeg":
            raise HTTPException(415, "Send image/jpeg")
        if frame_lock.locked():
            raise HTTPException(429, "Frame busy; drop frame rather than queue")
        async with frame_lock:
            received_at = time.monotonic()
            mode = controller.mode
            if mode not in {"cv", "obstacle"}:
                raise ControlError("Arm a camera mode first")
            controller.check(generation, mode)
            try:
                data = await asyncio.wait_for(limited_body(request, 400_000), 1.0)
                selected = obstacle_detector if mode == "obstacle" else detector
                decision = await asyncio.to_thread(selected.predict, data)
            except TimeoutError as exc:
                raise HTTPException(408, "Frame upload timed out") from exc
            except ValueError as exc:
                raise HTTPException(422, str(exc)) from exc
            result = await controller.apply_frame(decision, generation, sequence, received_at)
            latest.update(jpeg=data, generation=generation, received=received_at)
            if mode == "obstacle" and controller.candidate_count >= 3:
                loc = location if time.monotonic() - location.get("received", 0) < 60 else None
                try:
                    await asyncio.to_thread(outbox.observe, decision, s.device == "mock", loc)
                except Exception:
                    result["hazard_warning"] = "Local hazard logging unavailable"
            result["backend_ms"] = round((time.monotonic() - received_at) * 1000, 2)
            return result

    @app.post("/api/arkit/frame", dependencies=auth)
    async def arkit_frame(request: Request, generation: int, sequence: int):
        """Aligned raw-camera JPEG, ARKit metric LiDAR, pose and floor-plane input.

        A separate opt-in path: never changes the working Safari /api/frame.
        Uses the SAME arming, generation fencing, neutral and stale-frame rules.
        """
        if sequence < 0:
            raise HTTPException(422, "sequence must be nonnegative")
        if request.headers.get("content-type", "").split(";")[0] != "application/json":
            raise HTTPException(415, "Send application/json")
        if frame_lock.locked():
            raise HTTPException(429, "Frame busy; drop frame rather than queue")
        async with frame_lock:
            received_at = time.monotonic()
            controller.check(generation, "obstacle")
            try:
                data = await asyncio.wait_for(limited_body(request, MAX_FRAME_BYTES), 1.0)
                packet = await asyncio.to_thread(parse_packet, data)
                decision = await asyncio.to_thread(arkit_detector.predict, packet)
            except TimeoutError as exc:
                raise HTTPException(408, "LiDAR frame upload timed out") from exc
            except ValueError as exc:
                raise HTTPException(422, str(exc)) from exc
            result = await controller.apply_frame(decision, generation, sequence, received_at)
            # Preserve the existing spatial voice/Tinker frame context for native frames.
            latest.update(
                jpeg=base64.b64decode(packet.jpeg_b64),
                generation=generation,
                received=received_at,
                packet=packet,
                decision=decision,
            )
            if controller.candidate_count >= 3:
                loc = location if time.monotonic() - location.get("received", 0) < 60 else None
                try:
                    await asyncio.to_thread(outbox.observe, decision, s.device == "mock", loc)
                except Exception:
                    result["hazard_warning"] = "Local hazard logging unavailable"
            result["backend_ms"] = round((time.monotonic() - received_at) * 1000, 2)
            result["sensor"] = "arkit_lidar"
            return result

    @app.get("/api/button", dependencies=auth)
    async def physical_button():
        # Separate from frame transport; a slow ESP HTTP request cannot delay
        # the servo/LiDAR loop. No command is issued by this endpoint.
        read = getattr(d, "button", None)
        if read is None:
            raise HTTPException(503, "Button endpoint unavailable on this device")
        return await read()

    @app.post("/api/voice/scene", dependencies=auth)
    async def describe_latest_scene(body: SceneImageRequest):
        # Speaking never changes navigation or re-arms a stopped controller.
        if (not controller.armed or controller.mode != "obstacle"
                or controller.last_decision is None):
            raise HTTPException(409, "Arm LiDAR obstacle mode before scene narration")
        snapshot = dict(latest)
        requested_at = time.monotonic()
        if (snapshot.get("generation") != controller.generation
                or time.monotonic() - snapshot.get("received", 0) > 1.5
                or "packet" not in snapshot):
            raise HTTPException(409, "Current LiDAR/RGB scene is stale")
        if scene_voice_lock.locked():
            raise HTTPException(429, "Scene narration already running")
        snapshot_jpeg = None
        if body.jpeg_b64 is not None:
            try:
                snapshot_jpeg = base64.b64decode(body.jpeg_b64, validate=True)
                if len(snapshot_jpeg) > 800_000:
                    raise ValueError("Oversized scene snapshot")
            except (binascii.Error, ValueError) as exc:
                raise HTTPException(422, "Invalid or oversized scene snapshot") from exc
        async with scene_voice_lock:
            decision = snapshot.get("decision", controller.last_decision)
            packet = body.packet or snapshot["packet"]
            if body.packet is not None:
                decision = await asyncio.to_thread(arkit_detector.predict, packet)
                if packet.tracking != "normal":
                    raise HTTPException(409, "Camera tracking unstable; capture again")
            # The image model is run ONLY on demand in a worker thread.
            # It never holds frame_lock or the servo controller lock.
            try:
                result = await asyncio.wait_for(
                    asyncio.to_thread(scene_labeler.describe, packet, decision, snapshot_jpeg),
                    timeout=12.0,
                )
            except TimeoutError as exc:
                raise HTTPException(503, "RGB recognition timed out; LiDAR navigation unaffected") from exc
            if (not controller.armed or controller.generation != snapshot["generation"]
                    or time.monotonic() - requested_at > 3.0
                    or time.monotonic() - latest.get("received", 0) > 1.5):
                raise HTTPException(409, "Scene changed or expired during analysis; capture again")
            import numpy as np
            current_packet = latest.get("packet")
            if current_packet is not None:
                pose = np.asarray(packet.camera_to_world).reshape(4, 4, order="F")
                current_pose = np.asarray(current_packet.camera_to_world).reshape(4, 4, order="F")
                displacement = np.linalg.norm(pose[:3, 3] - current_pose[:3, 3])
                rotation = np.arccos(np.clip((np.trace(pose[:3, :3].T @ current_pose[:3, :3])-1)/2, -1, 1))
                if displacement > .25 or rotation > .26:
                    raise HTTPException(409, "Phone moved during scene analysis; hold still and capture again")
            result["frame_age_ms_at_request"] = round(
                (requested_at - snapshot["received"]) * 1000
            )
            result["analysis_ms"] = round((time.monotonic() - requested_at) * 1000, 1)
            result["depth_alignment"] = "same_capture" if body.packet is not None or snapshot_jpeg is None else "legacy_unsynchronized"
            if snapshot_jpeg is not None and body.packet is None:
                # Old clients can still name objects, but their independent RGB
                # image cannot safely inherit metric distances from another frame.
                for obj in result["objects"]:
                    obj["distance_m"] = None
                result["phrase"] = "Objects: " + ", ".join(o["label"] for o in result["objects"]) + ". Object distances unverified; update the iPhone app for aligned depth."
            return result

    @app.post("/api/voice", dependencies=auth)
    async def voice(body: VoiceRequest):
        return controller.voice(body.text)

    @app.post("/api/voice/tinker", dependencies=auth)
    async def ask_tinker(body: VoiceRequest):
        if os.getenv("TV_TINKER_ENABLED") != "1":
            raise HTTPException(503, "Tinker disabled; use local scene voice")
        if controller.mode != "obstacle" or not controller.armed:
            raise HTTPException(409, "Arm obstacle mode and stream fresh frames first")
        snapshot = dict(latest)
        if time.monotonic() - snapshot.get("received", 0) > 0.7:
            raise HTTPException(409, "No fresh camera frame")
        try:
            result = await asyncio.wait_for(
                tinker_voice.describe(
                    snapshot["jpeg"], body.text, controller.last_decision, controller.phrase
                ),
                timeout=8,
            )
        except Exception:
            return {**controller.voice(body.text), "detail": "Tinker unavailable; local fallback"}
        if (
            snapshot["generation"] != controller.generation
            or not controller.armed
            or time.monotonic() - controller.last_frame_at > 0.7
            or time.monotonic() - snapshot["received"] > 3
        ):
            return {"phrase": "Scene changed. Ask again.", "source": "local_guard"}
        return result

    @app.post("/api/audio", dependencies=auth)
    async def audio(request: Request):
        mime = request.headers.get("content-type", "").split(";")[0]
        if mime not in {"audio/mp4", "audio/webm", "audio/ogg", "video/mp4"}:
            raise HTTPException(415, "Unsupported recording container")
        try:
            data = await asyncio.wait_for(limited_body(request, 1_000_000), 5.0)
        except TimeoutError as exc:
            raise HTTPException(408, "Audio upload timed out") from exc
        if not data:
            raise HTTPException(422, "Empty recording")
        if speech is not None:
            if speech_lock.locked():
                raise HTTPException(429, "Speech busy; try again after the current clip")
            async with speech_lock:
                try:
                    transcript = await asyncio.to_thread(speech.transcribe, data)
                except ValueError as exc:
                    raise HTTPException(422, str(exc)) from exc
                except Exception as exc:
                    raise HTTPException(503, "Local speech recognition failed") from exc
            answer = (
                controller.voice(transcript)
                if transcript
                else {"phrase": "No speech detected. Try again.", "source": "local_whisper"}
            )
            return {
                **answer,
                "received_bytes": len(data),
                "mime": mime,
                "stored": False,
                "transcription": transcript,
                "speech_source": "local_whisper",
            }
        # Transport capture only. No fake transcription or claim to have understood audio.
        return {
            "received_bytes": len(data),
            "mime": mime,
            "stored": False,
            "transcription": None,
            "source": "capture_only",
            "phrase": "Recording received. Use typed status.",
            "detail": "No speech recognizer configured. Audio discarded after this request.",
        }

    app.mount("/static", StaticFiles(directory=WEB), name="static")
    return app
