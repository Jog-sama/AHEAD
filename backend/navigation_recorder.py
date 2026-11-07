"""Opt-in ARKit navigation recorder: no photographs, audio, GPS or API keys.

This captures raw metric depth, confidence, ARKit intrinsics and camera pose
as received by the backend. Indoor geometry is still sensitive: keep local.
"""
from __future__ import annotations

import gzip
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from queue import Empty, Full, Queue
from threading import Thread
from time import time
from typing import Any


class NavigationRecorder:
    def __init__(self, enabled: bool = False, directory: str = "data/navigation_recordings",
                 max_frames: int = 1500) -> None:
        self.enabled = enabled
        self.path: Path | None = None
        self.frames_queued = 0
        self.dropped = 0
        self._queue: Queue[Any] = Queue(maxsize=32)
        self._thread: Thread | None = None
        self._closed = False
        self.max_frames = max_frames
        if not enabled:
            return
        output = Path(directory).expanduser()
        output.mkdir(mode=0o700, parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        self.path = output / ("arkit_" + stamp + ".jsonl.gz")
        self._thread = Thread(target=self._write_loop, name="arkit-navigation-recorder", daemon=True)
        self._thread.start()

    @classmethod
    def from_env(cls) -> "NavigationRecorder":
        return cls(
            enabled=os.getenv("TV_RECORD_ARKIT", "0") == "1",
            directory=os.getenv("TV_RECORD_DIR", "data/navigation_recordings"),
        )

    def capture(self, packet: Any, sequence: int) -> None:
        """Nonblocking in the live navigation request; drop frames on overload."""
        if not self.enabled or self._closed or self.frames_queued >= self.max_frames:
            return
        try:
            self._queue.put_nowait((packet, int(sequence), int(time() * 1000)))
            self.frames_queued += 1
        except Full:
            self.dropped += 1

    def _write_loop(self) -> None:
        assert self.path is not None
        # Restricted permissions even if the caller has a permissive umask.
        fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        with os.fdopen(fd, "wb") as raw, gzip.GzipFile(fileobj=raw, mode="wb") as sink:
            while True:
                item = self._queue.get()
                if item is None:
                    break
                packet, sequence, timestamp_ms = item
                # Exclude the actual camera image, intentionally. The remaining
                # data is enough to reconstruct LiDAR rays and pose.
                body = packet.model_dump(exclude={"jpeg_b64"})
                row = {
                    "format": "ahead-depth-v1", "sequence": sequence,
                    "timestamp_ms": timestamp_ms, "packet": body,
                }
                sink.write((json.dumps(row, separators=(",", ":"), allow_nan=False) + "\n").encode())

    def close(self) -> None:
        if not self.enabled or self._closed:
            return
        self._closed = True
        try:
            self._queue.put_nowait(None)
        except Full:
            # Prefer ending cleanly over retaining the last queued sample.
            try:
                self._queue.get_nowait()
            except Empty:
                pass
            self._queue.put_nowait(None)
            self.dropped += 1
        if self._thread is not None:
            self._thread.join(timeout=15)
            if self._thread.is_alive():
                raise RuntimeError("Navigation recorder did not close cleanly")


def read_recording(path: str | Path):
    """Stream rows without loading the entire recording in memory."""
    with gzip.open(path, "rt", encoding="utf-8") as reader:
        for line in reader:
            if not line.strip():
                continue
            row = json.loads(line)
            if row.get("format") != "ahead-depth-v1":
                raise ValueError("Unsupported recording format")
            if "jpeg_b64" in row.get("packet", {}):
                raise ValueError("Unexpected stored camera image")
            yield row
