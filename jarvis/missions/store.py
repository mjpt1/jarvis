"""ذخیره‌ی مأموریت‌ها و گام‌هایشان در SQLite (برای ادامه بعد از کرش)."""

from __future__ import annotations

import json
import sqlite3
import threading
from datetime import UTC, datetime

from ..paths import MISSIONS_DB, ensure_dirs

_SCHEMA = """
CREATE TABLE IF NOT EXISTS missions (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    request    TEXT NOT NULL,
    status     TEXT NOT NULL DEFAULT 'planning',  -- planning|running|done|failed|cancelled
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS steps (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    mission_id INTEGER NOT NULL,
    idx        INTEGER NOT NULL,
    tool       TEXT NOT NULL,
    args       TEXT NOT NULL DEFAULT '{}',
    check_hint TEXT NOT NULL DEFAULT '',
    status     TEXT NOT NULL DEFAULT 'pending',   -- pending|running|ok|failed|skipped
    result     TEXT NOT NULL DEFAULT '',
    updated_at TEXT NOT NULL
);
"""


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


class MissionStore:
    def __init__(self, path=MISSIONS_DB):
        ensure_dirs()
        self._lock = threading.RLock()
        self._c = sqlite3.connect(str(path), check_same_thread=False)
        self._c.row_factory = sqlite3.Row
        with self._c:
            self._c.executescript(_SCHEMA)

    def create(self, request: str) -> int:
        with self._lock, self._c:
            cur = self._c.execute(
                "INSERT INTO missions(request, created_at, updated_at) VALUES (?,?,?)",
                (request, _now(), _now()),
            )
            return int(cur.lastrowid)

    def set_status(self, mission_id: int, status: str) -> None:
        with self._lock, self._c:
            self._c.execute("UPDATE missions SET status=?, updated_at=? WHERE id=?",
                            (status, _now(), mission_id))

    def add_steps(self, mission_id: int, steps: list[dict]) -> None:
        with self._lock, self._c:
            for i, s in enumerate(steps):
                self._c.execute(
                    "INSERT INTO steps(mission_id, idx, tool, args, check_hint, updated_at) "
                    "VALUES (?,?,?,?,?,?)",
                    (mission_id, i, s.get("tool", ""),
                     json.dumps(s.get("args", {}), ensure_ascii=False),
                     s.get("check", ""), _now()),
                )

    def steps(self, mission_id: int) -> list[sqlite3.Row]:
        return self._c.execute(
            "SELECT * FROM steps WHERE mission_id=? ORDER BY idx", (mission_id,)
        ).fetchall()

    def update_step(self, step_id: int, status: str, result: str = "") -> None:
        with self._lock, self._c:
            self._c.execute("UPDATE steps SET status=?, result=?, updated_at=? WHERE id=?",
                            (status, result[:2000], _now(), step_id))

    def unfinished(self) -> list[sqlite3.Row]:
        return self._c.execute(
            "SELECT * FROM missions WHERE status IN ('planning','running') "
            "ORDER BY id DESC"
        ).fetchall()

    def close(self) -> None:
        self._c.close()


_STORE: MissionStore | None = None
_LK = threading.Lock()


def get_store() -> MissionStore:
    global _STORE
    with _LK:
        if _STORE is None:
            _STORE = MissionStore()
        return _STORE
