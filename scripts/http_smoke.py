"""Launch two local processes and verify JPEG -> HTTP backend -> HTTP ESP32 simulator.
Run from repository root: python scripts/http_smoke.py
No actual device address is used, even if .env selects real hardware.
"""

import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from tests.conftest import DEVICE_KEY, KEY, frame  # noqa: E402


def free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def wait_ready(url):
    for _ in range(100):
        try:
            if httpx.get(url + "/health", timeout=0.3, trust_env=False).status_code == 200:
                return
        except httpx.HTTPError:
            pass
        time.sleep(0.05)
    raise RuntimeError("Local process failed to become ready")


def main():
    device_port, backend_port = free_port(), free_port()
    while device_port == backend_port:
        backend_port = free_port()
    device_url, backend_url = f"http://127.0.0.1:{device_port}", f"http://127.0.0.1:{backend_port}"
    env = {
        **os.environ,
        "TV_DEVICE_TOKEN": DEVICE_KEY,
        "TV_API_KEY": KEY,
        "TV_DEVICE": "esp32",
        "TV_ESP32_URL": device_url,
        "TV_LEFT": "80",
        "TV_RIGHT": "100",
        "TV_CENTER": "90",
        "TV_WHISPER_MODEL": "",
    }
    processes = []
    try:
        for module, port, factory in [
            ("scripts.sim_esp32:app", device_port, []),
            ("backend.app:create_app", backend_port, ["--factory"]),
        ]:
            processes.append(
                subprocess.Popen(
                    [
                        sys.executable,
                        "-m",
                        "uvicorn",
                        module,
                        *factory,
                        "--host",
                        "127.0.0.1",
                        "--port",
                        str(port),
                        "--log-level",
                        "error",
                    ],
                    env=env,
                    cwd=ROOT,
                )
            )
        wait_ready(device_url)
        wait_ready(backend_url)
        with httpx.Client(base_url=backend_url, headers={"X-API-Key": KEY}, trust_env=False) as c:
            gen = c.post("/api/arm", json={"mode": "cv"}).json()["generation"]
            observations = []
            for lane, angle in [("left", 80), ("center", 90), ("right", 100)]:
                for _ in range(2):
                    seq = len(observations)
                    r = c.post(
                        f"/api/frame?generation={gen}&sequence={seq}",
                        content=frame(lane),
                        headers={"Content-Type": "image/jpeg"},
                    )
                    r.raise_for_status()
                    observations.append(r.json())
                physical_sim = httpx.get(device_url + "/health", trust_env=False).json()
                assert physical_sim["angle"] == angle
            r = c.post("/api/stop")
            r.raise_for_status()
            assert r.json()["commanded_angle"] == 90
            assert httpx.get(device_url + "/health", trust_env=False).json()["angle"] == 90
            assert (
                c.post(
                    f"/api/frame?generation={gen}&sequence=99",
                    content=frame("right"),
                    headers={"Content-Type": "image/jpeg"},
                ).status_code
                == 409
            )
            print(
                "PASS: local TCP HTTP JPEG -> OpenCV -> backend -> ESP32 simulator; "
                "L/C/R, Stop, stale rejection"
            )
            print("Software-only backend elapsed ms:", [x["backend_ms"] for x in observations])
    finally:
        for p in processes:
            p.terminate()
        for p in processes:
            try:
                p.wait(timeout=5)
            except subprocess.TimeoutExpired:
                p.kill()
                p.wait()


if __name__ == "__main__":
    main()
