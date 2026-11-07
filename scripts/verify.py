"""Run reproducible hardware-independent checks, preserving stdout/stderr."""

import shutil
import subprocess
import sys
from pathlib import Path

root = Path(__file__).resolve().parent.parent
commands = {
    "pytest.txt": [sys.executable, "-m", "pytest", "-q"],
    "http-smoke.txt": [sys.executable, "scripts/http_smoke.py"],
    "ruff.txt": [sys.executable, "-m", "ruff", "check", "backend", "tests", "scripts"],
}
if shutil.which("node"):
    commands["javascript-check.txt"] = ["node", "--check", "web/app.js"]
for name, command in commands.items():
    result = subprocess.run(command, cwd=root, capture_output=True, text=True)
    (root / "evidence" / name).write_text(result.stdout + result.stderr)
    print(name, "PASS" if result.returncode == 0 else "FAIL")
    if result.returncode:
        print(result.stdout + result.stderr)
        raise SystemExit(result.returncode)
compiler = shutil.which("c++") or shutil.which("g++")
if compiler:
    target = "/tmp/tactilevector-policy"
    subprocess.run(
        [
            compiler,
            "-std=c++17",
            "-Wall",
            "-Wextra",
            "-Werror",
            "tests/firmware_policy.cpp",
            "-o",
            target,
        ],
        cwd=root,
        check=True,
    )
    result = subprocess.run([target], capture_output=True, text=True, check=True)
    (root / "evidence" / "firmware-policy.txt").write_text(result.stdout)
    print(result.stdout.strip())
else:
    print("C++ compiler unavailable: firmware policy test skipped")
