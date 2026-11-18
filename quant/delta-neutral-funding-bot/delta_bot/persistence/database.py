"""Async SQLite persistence."""
from __future__ import annotations
import json, os
from datetime import datetime, timezone
from typing import Optional
from dataclasses import asdict
import aiosqlite, structlog
from delta_bot.core.types import DeltaNeutralPosition, SkipEvent, PortfolioSnapshot

logger = structlog.get_logger(__name__)

SCHEMA = """
CREATE TABLE IF NOT EXISTS positions (
    id TEXT PRIMARY KEY, data TEXT NOT NULL, status TEXT NOT NULL,
    opened_at TEXT NOT NULL, closed_at TEXT, updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS skip_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT, reason TEXT NOT NULL,
    details TEXT, timestamp TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT, data TEXT NOT NULL, timestamp TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_pos_status ON positions(status);
"""


def _now(): return datetime.now(timezone.utc).isoformat()


class Database:
    def __init__(self, db_path: str = "data/bot.db"):
        self.db_path = db_path
        self._conn: Optional[aiosqlite.Connection] = None

    async def initialize(self):
        os.makedirs(os.path.dirname(self.db_path) or ".", exist_ok=True)
        self._conn = await aiosqlite.connect(self.db_path)
        await self._conn.executescript(SCHEMA)
        await self._conn.commit()
        logger.info("database.initialized", path=self.db_path)

    async def close(self):
        if self._conn:
            try:
                await self._conn.commit()
            except Exception:
                pass
            await self._conn.close()
            self._conn = None

    async def save_position(self, pos: DeltaNeutralPosition):
        d = asdict(pos)
        await self._conn.execute(
            "INSERT INTO positions (id,data,status,opened_at,closed_at,updated_at) "
            "VALUES (?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET data=excluded.data,"
            "status=excluded.status,closed_at=excluded.closed_at,updated_at=excluded.updated_at",
            (pos.id, json.dumps(d, default=str), pos.status.value,
             pos.opened_at.isoformat() if pos.opened_at else _now(),
             pos.closed_at.isoformat() if pos.closed_at else None, _now()))
        await self._conn.commit()

    async def load_positions(self, status: Optional[str] = None) -> list[dict]:
        if status:
            cur = await self._conn.execute(
                "SELECT data FROM positions WHERE status = ?", (status,)
            )
        else:
            cur = await self._conn.execute("SELECT data FROM positions")
        return [json.loads(r[0]) for r in await cur.fetchall()]

    async def load_closed_positions(self, limit: int = 1000) -> list[dict]:
        cur = await self._conn.execute(
            "SELECT data FROM positions WHERE status = 'closed' "
            "ORDER BY closed_at DESC LIMIT ?",
            (limit,),
        )
        return [json.loads(r[0]) for r in await cur.fetchall()]

    async def log_skip(self, event: SkipEvent):
        await self._conn.execute(
            "INSERT INTO skip_events (reason,details,timestamp) VALUES (?,?,?)",
            (event.reason.value, event.details, event.timestamp.isoformat()))
        await self._conn.commit()

    async def get_skip_events(self, limit=50) -> list[dict]:
        cur = await self._conn.execute(
            "SELECT reason,details,timestamp FROM skip_events ORDER BY timestamp DESC LIMIT ?", (limit,))
        return [{"reason": r[0], "details": r[1], "timestamp": r[2]} for r in await cur.fetchall()]

    async def save_snapshot(self, snap: PortfolioSnapshot):
        await self._conn.execute("INSERT INTO snapshots (data,timestamp) VALUES (?,?)",
                                  (json.dumps(asdict(snap), default=str), _now()))
        await self._conn.commit()
