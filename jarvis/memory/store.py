"""ذخیره‌ی حقایق در SQLite با جست‌وجوی تمام‌متن، تقویت، جایگزینی و روابط."""

from __future__ import annotations

import json
import sqlite3
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from ..logging_setup import get_logger
from ..paths import MEMORY_DB, ensure_dirs

log = get_logger("memory")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS facts (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    text          TEXT NOT NULL,
    category      TEXT NOT NULL DEFAULT 'general',
    source        TEXT NOT NULL DEFAULT 'user',
    tags          TEXT NOT NULL DEFAULT '[]',
    confidence    REAL NOT NULL DEFAULT 0.8,
    reinforcement INTEGER NOT NULL DEFAULT 0,
    status        TEXT NOT NULL DEFAULT 'active',   -- active | superseded | archived
    superseded_by INTEGER,
    created_at    TEXT NOT NULL,
    updated_at    TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_facts_status   ON facts(status);
CREATE INDEX IF NOT EXISTS idx_facts_category ON facts(category);

CREATE TABLE IF NOT EXISTS relations (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    from_id    INTEGER NOT NULL,
    to_id      INTEGER NOT NULL,
    kind       TEXT NOT NULL,                       -- supports | contradicts | supersedes | relates
    created_at TEXT NOT NULL,
    UNIQUE(from_id, to_id, kind)
);

CREATE TABLE IF NOT EXISTS audit (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    fact_id    INTEGER,
    action     TEXT NOT NULL,
    detail     TEXT NOT NULL DEFAULT '',
    at         TEXT NOT NULL
);
"""

_FTS_SCHEMA = """
CREATE VIRTUAL TABLE IF NOT EXISTS facts_fts
USING fts5(text, content='facts', content_rowid='id', tokenize='unicode61');

CREATE TRIGGER IF NOT EXISTS facts_ai AFTER INSERT ON facts BEGIN
    INSERT INTO facts_fts(rowid, text) VALUES (new.id, new.text);
END;
CREATE TRIGGER IF NOT EXISTS facts_ad AFTER DELETE ON facts BEGIN
    INSERT INTO facts_fts(facts_fts, rowid, text) VALUES ('delete', old.id, old.text);
END;
CREATE TRIGGER IF NOT EXISTS facts_au AFTER UPDATE ON facts BEGIN
    INSERT INTO facts_fts(facts_fts, rowid, text) VALUES ('delete', old.id, old.text);
    INSERT INTO facts_fts(rowid, text) VALUES (new.id, new.text);
END;
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass
class Fact:
    id: int
    text: str
    category: str = "general"
    source: str = "user"
    tags: list[str] = field(default_factory=list)
    confidence: float = 0.8
    reinforcement: int = 0
    status: str = "active"
    superseded_by: int | None = None
    created_at: str = ""
    updated_at: str = ""

    @classmethod
    def _from_row(cls, row: sqlite3.Row) -> "Fact":
        return cls(
            id=row["id"], text=row["text"], category=row["category"],
            source=row["source"], tags=json.loads(row["tags"] or "[]"),
            confidence=row["confidence"], reinforcement=row["reinforcement"],
            status=row["status"], superseded_by=row["superseded_by"],
            created_at=row["created_at"], updated_at=row["updated_at"],
        )

    def short_date(self) -> str:
        return (self.created_at or "")[:10]


class MemoryStore:
    def __init__(self, db_path: Path | str = MEMORY_DB):
        ensure_dirs()
        self._path = str(db_path)
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(self._path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._has_fts = True
        with self._conn:
            self._conn.executescript(_SCHEMA)
            try:
                self._conn.executescript(_FTS_SCHEMA)
            except sqlite3.OperationalError as exc:      # FTS5 در دسترس نیست
                log.warning("FTS5 در دسترس نیست، جست‌وجوی ساده استفاده می‌شود: %s", exc)
                self._has_fts = False

    # ------------------------------------------------------------------
    def _audit(self, fact_id: int | None, action: str, detail: str = "") -> None:
        self._conn.execute(
            "INSERT INTO audit(fact_id, action, detail, at) VALUES (?,?,?,?)",
            (fact_id, action, detail, _now()),
        )

    def add_fact(self, text: str, *, category: str = "general", source: str = "user",
                 tags: list[str] | None = None, confidence: float = 0.8,
                 dedupe: bool = True) -> Fact:
        text = (text or "").strip()
        if not text:
            raise ValueError("متنِ حقیقت خالی است")
        with self._lock, self._conn:
            if dedupe:
                existing = self._find_similar(text)
                if existing is not None:
                    return self.reinforce(existing.id)
            now = _now()
            cur = self._conn.execute(
                "INSERT INTO facts(text, category, source, tags, confidence, "
                "created_at, updated_at) VALUES (?,?,?,?,?,?,?)",
                (text, category, source, json.dumps(tags or [], ensure_ascii=False),
                 confidence, now, now),
            )
            fid = int(cur.lastrowid)
            self._audit(fid, "create", text[:120])
            log.info("حقیقت جدید #%d [%s]: %s", fid, category, text[:80])
            return self.get(fid)  # type: ignore[return-value]

    def reinforce(self, fact_id: int, by: float = 0.05) -> Fact:
        with self._lock, self._conn:
            self._conn.execute(
                "UPDATE facts SET reinforcement = reinforcement + 1, "
                "confidence = MIN(1.0, confidence + ?), updated_at = ? "
                "WHERE id = ?",
                (by, _now(), fact_id),
            )
            self._audit(fact_id, "reinforce")
        return self.get(fact_id)  # type: ignore[return-value]

    def supersede(self, old_id: int, new_text: str, **kw) -> Fact:
        """حقیقتِ قدیمی را «جایگزین‌شده» علامت می‌زند و حقیقت تازه را می‌سازد."""
        with self._lock, self._conn:
            new = self.add_fact(new_text, dedupe=False, **kw)
            self._conn.execute(
                "UPDATE facts SET status='superseded', superseded_by=?, updated_at=? "
                "WHERE id=?", (new.id, _now(), old_id),
            )
            self.add_relation(new.id, old_id, "supersedes")
            self._audit(old_id, "supersede", f"-> #{new.id}")
        return new

    def archive(self, fact_id: int) -> None:
        with self._lock, self._conn:
            self._conn.execute(
                "UPDATE facts SET status='archived', updated_at=? WHERE id=?",
                (_now(), fact_id),
            )
            self._audit(fact_id, "archive")

    def add_relation(self, from_id: int, to_id: int, kind: str) -> None:
        with self._lock, self._conn:
            try:
                self._conn.execute(
                    "INSERT INTO relations(from_id, to_id, kind, created_at) "
                    "VALUES (?,?,?,?)", (from_id, to_id, kind, _now()),
                )
            except sqlite3.IntegrityError:
                pass

    # ------------------------------------------------------------------
    def get(self, fact_id: int) -> Fact | None:
        row = self._conn.execute("SELECT * FROM facts WHERE id=?", (fact_id,)).fetchone()
        return Fact._from_row(row) if row else None

    def _find_similar(self, text: str) -> Fact | None:
        import difflib
        norm = text.strip().lower()
        rows = self._conn.execute(
            "SELECT * FROM facts WHERE status='active' ORDER BY id DESC LIMIT 400"
        ).fetchall()
        for row in rows:
            if difflib.SequenceMatcher(None, norm, row["text"].strip().lower()).ratio() > 0.86:
                return Fact._from_row(row)
        return None

    def search(self, query: str, limit: int = 8) -> list[Fact]:
        query = (query or "").strip()
        if not query:
            return []
        with self._lock:
            if self._has_fts:
                try:
                    match = " OR ".join(
                        f'"{w}"' for w in query.split() if len(w) > 1) or f'"{query}"'
                    rows = self._conn.execute(
                        "SELECT f.* FROM facts_fts x JOIN facts f ON f.id = x.rowid "
                        "WHERE facts_fts MATCH ? AND f.status='active' "
                        "ORDER BY bm25(facts_fts), f.reinforcement DESC LIMIT ?",
                        (match, limit),
                    ).fetchall()
                    if rows:
                        return [Fact._from_row(r) for r in rows]
                except sqlite3.OperationalError:
                    pass
            like = f"%{query}%"
            rows = self._conn.execute(
                "SELECT * FROM facts WHERE status='active' AND text LIKE ? "
                "ORDER BY reinforcement DESC, id DESC LIMIT ?", (like, limit),
            ).fetchall()
            return [Fact._from_row(r) for r in rows]

    def recent(self, limit: int = 10) -> list[Fact]:
        rows = self._conn.execute(
            "SELECT * FROM facts WHERE status='active' ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [Fact._from_row(r) for r in rows]

    def all_active(self) -> list[Fact]:
        rows = self._conn.execute(
            "SELECT * FROM facts WHERE status='active' ORDER BY category, id"
        ).fetchall()
        return [Fact._from_row(r) for r in rows]

    def by_category(self, category: str) -> list[Fact]:
        rows = self._conn.execute(
            "SELECT * FROM facts WHERE status='active' AND category=? ORDER BY id",
            (category,),
        ).fetchall()
        return [Fact._from_row(r) for r in rows]

    def relations_of(self, fact_id: int) -> list[tuple[str, int]]:
        rows = self._conn.execute(
            "SELECT kind, to_id FROM relations WHERE from_id=? "
            "UNION SELECT kind, from_id FROM relations WHERE to_id=?",
            (fact_id, fact_id),
        ).fetchall()
        return [(r["kind"], r["to_id"]) for r in rows]

    def stats(self) -> dict:
        c = self._conn.execute
        total = c("SELECT COUNT(*) FROM facts WHERE status='active'").fetchone()[0]
        cats = dict(c("SELECT category, COUNT(*) FROM facts WHERE status='active' "
                      "GROUP BY category").fetchall())
        return {"active": total, "by_category": cats}

    def close(self) -> None:
        with self._lock:
            self._conn.close()


_STORE: MemoryStore | None = None
_STORE_LOCK = threading.Lock()


def get_store() -> MemoryStore:
    global _STORE
    with _STORE_LOCK:
        if _STORE is None:
            _STORE = MemoryStore()
        return _STORE
