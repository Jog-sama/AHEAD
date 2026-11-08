"""Software-only ESP32 simulator. Token comes from local .env."""

import os
import re
import secrets
import time

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

load_dotenv()


def create_sim(token: str) -> FastAPI:
    app = FastAPI(title="SIMULATED ESP32", docs_url=None, openapi_url=None)
    app.state.angle, app.state.last, app.state.history = 90, 0.0, []

    def status():
        expired = time.monotonic() - app.state.last >= 0.8
        if expired:
            app.state.angle = 90
        return dict(
            ok=True,
            configured=True,
            wifi=True,
            angle=app.state.angle,
            neutral=90,
            min_angle=60,
            max_angle=120,
            timeout_ms=800,
            failsafe=expired,
            simulation=True,
        )

    @app.get("/health")
    async def health():
        return status()

    @app.get("/steer")
    async def steer(request: Request):
        if not token or not secrets.compare_digest(
            request.headers.get("x-device-token", ""), token
        ):
            return JSONResponse({"error": "unauthorized"}, status_code=401)
        args = list(request.query_params.multi_items())
        text = request.query_params.get("angle", "")
        if len(args) != 1 or not re.fullmatch(r"[0-9]{1,3}", text) or not 60 <= int(text) <= 120:
            return JSONResponse({"error": "angle must be 60..120"}, status_code=400)
        app.state.angle, app.state.last = int(text), time.monotonic()
        app.state.history.append(int(text))
        return status()

    return app


app = create_sim(os.getenv("TV_DEVICE_TOKEN", ""))
