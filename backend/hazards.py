"""Durable metadata outbox. Never calls a network service in the actuation loop."""

import asyncio
import json
import sqlite3
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

from .adapters import HazardEvent


class HazardOutbox:
    def __init__(self, path="data/hazards.sqlite3"):
        self.path = str(path)
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS events (
                id TEXT PRIMARY KEY, fingerprint TEXT, created REAL, payload TEXT,
                attempts INTEGER DEFAULT 0, next_try REAL DEFAULT 0,
                delivered INTEGER DEFAULT 0)""")

    def connect(self):
        return sqlite3.connect(self.path, timeout=1)

    def observe(self, decision, simulated, location=None):
        scene = decision.scene or {}
        objects = [o for o in scene.get("objects", []) if o.get("confidence", 0) >= 0.5]
        blocked = scene.get("blocked", {})
        if not objects or max(blocked.values(), default=0) < 0.20:
            return None
        labels = sorted({o["label"] for o in objects})
        fingerprint = ",".join(labels) + ":" + ",".join(k for k, v in blocked.items() if v >= 0.20)
        now = time.time()
        with self.connect() as db:
            # Serialized transaction avoids duplicate insertion from concurrent requests.
            db.execute("BEGIN IMMEDIATE")
            if db.execute(
                "SELECT 1 FROM events WHERE fingerprint=? AND created>?", (fingerprint, now - 30)
            ).fetchone():
                return None
            event = HazardEvent(
                event_id=str(uuid.uuid4()),
                observed_at=datetime.now(timezone.utc).isoformat(),
                label=", ".join(labels)[:120],
                source="model_candidate",
                simulated=simulated,
                latitude=(location or {}).get("latitude"),
                longitude=(location or {}).get("longitude"),
                severity="review",
                confidence=scene.get("confidence", 0),
                reason=decision.reason,
                direction=decision.direction,
            )
            db.execute(
                "INSERT INTO events(id,fingerprint,created,payload) VALUES(?,?,?,?)",
                (event.event_id, fingerprint, now, event.model_dump_json()),
            )
            # Bounded retention: keep newest 5000 records, including pending candidates.
            db.execute(
                "DELETE FROM events WHERE id NOT IN "
                "(SELECT id FROM events ORDER BY created DESC LIMIT 5000)"
            )
        return event.event_id

    def list(self, limit=100):
        with self.connect() as db:
            rows = db.execute(
                "SELECT payload,delivered,attempts FROM events ORDER BY created DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [{**json.loads(p), "delivered": bool(d), "attempts": a} for p, d, a in rows]

    def pending(self):
        with self.connect() as db:
            return db.execute(
                "SELECT id,payload,attempts FROM events WHERE delivered=0 "
                "AND next_try<=? ORDER BY created LIMIT 1",
                (time.time(),),
            ).fetchone()

    def finish(self, event_id, attempts, success):
        with self.connect() as db:
            db.execute(
                "UPDATE events SET attempts=?,next_try=?,delivered=? WHERE id=?",
                (
                    attempts + 1,
                    time.time() + min(300, 2 ** min(attempts + 1, 8)),
                    int(success),
                    event_id,
                ),
            )

    async def deliver_one(self, sender):
        row = await asyncio.to_thread(self.pending)
        if row is None:
            return False
        event_id, payload, attempts = row
        try:
            success = await sender.send(HazardEvent.model_validate_json(payload))
        except Exception:
            success = False
        await asyncio.to_thread(self.finish, event_id, attempts, success)
        return success

    async def run(self, sender):
        while True:
            try:
                await self.deliver_one(sender)
            except Exception:
                pass  # Outbox failure cannot disable the hardware watchdog.
            await asyncio.sleep(1)
