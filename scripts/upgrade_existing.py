"""Apply this source update to an existing TactileVector folder with rollback.

Usage: python3 scripts/upgrade_existing.py /absolute/path/to/working/tactilevector
Stop the running server first. Firmware, .env, certificates, models and venv are preserved.
"""

import argparse
import json
import shutil
from datetime import datetime
from pathlib import Path

EXCLUDED = {
    "firmware",
    ".venv",
    ".git",
    "models",
    "data",
    "certs",
    "node_modules",
    "__pycache__",
    ".pytest_cache",
    ".ruff_cache",
    "dist",
    "build",
}


def upgrade(source, target):
    source, target = Path(source).resolve(), Path(target).resolve()
    if source == target or source in target.parents or target in source.parents:
        raise ValueError("Extract the update beside, not inside, the working project")
    for name in ("backend/app.py", "backend/device.py", "web/app.js"):
        if not (target / name).is_file():
            raise ValueError(f"Target does not look like Astra's project: missing {name}")
    files = [
        p
        for p in source.rglob("*")
        if p.is_file()
        and not set(p.relative_to(source).parts) & EXCLUDED
        and not any(part.startswith(".venv") for part in p.relative_to(source).parts)
        and p.name not in {".env", "config.h"}
        and not (p.name.startswith(".env.") and p.name != ".env.example")
        and p.suffix not in {".pyc", ".pem", ".key", ".sqlite3", ".zip"}
    ]
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    backup = target.parent / (target.name + "-pre-obstacle-" + stamp)
    backup.mkdir(mode=0o700)
    manifest = {"target": str(target), "replaced": [], "added": []}
    for p in files:
        rel = p.relative_to(source)
        destination = target / rel
        if destination.is_symlink():
            raise ValueError(f"Refusing to overwrite symlink: {rel}")
        if destination.exists():
            if destination.read_bytes() == p.read_bytes():
                continue
            old = backup / rel
            old.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(destination, old)
            manifest["replaced"].append(str(rel))
        else:
            manifest["added"].append(str(rel))
        # Record rollback before each mutation, including added files.
        (backup / "rollback.json").write_text(json.dumps(manifest, indent=2))
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(p, destination)
    (backup / "rollback.json").write_text(json.dumps(manifest, indent=2))
    return backup


def rollback(backup):
    backup = Path(backup).resolve()
    manifest = json.loads((backup / "rollback.json").read_text())
    target = Path(manifest["target"])
    for name in manifest["replaced"]:
        shutil.copy2(backup / name, target / name)
    for name in manifest["added"]:
        (target / name).unlink(missing_ok=True)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("target")
    p.add_argument("--rollback", action="store_true", help="Target is the backup directory")
    args = p.parse_args()
    if args.rollback:
        rollback(args.target)
        print("Restored backed-up code. Restart using the previous environment if needed.")
    else:
        backup = upgrade(Path(__file__).resolve().parent.parent, args.target)
        print(f"Updated existing source. Rollback backup: {backup}")
        print("Firmware and local configuration were not changed. Install dependencies next.")


if __name__ == "__main__":
    main()
