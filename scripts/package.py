"""Create a clean source ZIP, excluding local credentials, caches, models and builds."""

import hashlib
import zipfile
from pathlib import Path

root = Path(__file__).resolve().parent.parent
out = root.parent / "TactileVector.zip"
excluded = {
    ".git",
    ".venv",
    "__pycache__",
    ".pytest_cache",
    ".ruff_cache",
    "certs",
    "node_modules",
    "models",
    "build",
    "data",
    "dist",
}
files = [
    p
    for p in root.rglob("*")
    if p.is_file()
    and not set(p.relative_to(root).parts) & excluded
    and not any(part.startswith(".venv") for part in p.relative_to(root).parts)
    and p.name not in {".env", "config.h"}
    and not (p.name.startswith(".env.") and p.name != ".env.example")
    and p.suffix not in {".pem", ".key", ".pyc", ".zip"}
]
with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
    for p in sorted(files):
        z.write(p, "tactilevector/" + str(p.relative_to(root)))
with zipfile.ZipFile(out) as z:
    assert z.testzip() is None
print(f"{out}: {len(files)} files; {out.stat().st_size} bytes")
print("SHA256", hashlib.sha256(out.read_bytes()).hexdigest())
