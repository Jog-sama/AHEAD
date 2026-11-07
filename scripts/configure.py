"""Create ignored local settings without overwriting credentials."""

import os
import secrets
from pathlib import Path

root = Path(__file__).resolve().parent.parent
path = root / ".env"
if path.exists():
    raise SystemExit(".env already exists; edit it locally. Nothing overwritten.")
text = (root / ".env.example").read_text()
text = text.replace("TV_API_KEY=\n", f"TV_API_KEY={secrets.token_urlsafe(32)}\n")
text = text.replace("TV_DEVICE_TOKEN=\n", f"TV_DEVICE_TOKEN={secrets.token_hex(24)}\n")
fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
with os.fdopen(fd, "w") as f:
    f.write(text)
print("Created .env in MOCK mode. Open it locally to copy TV_API_KEY into the phone UI.")
