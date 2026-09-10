"""ذخیره‌ی مهارت‌ها در یک فایلِ JSON."""

from __future__ import annotations

import json
import threading
from dataclasses import asdict, dataclass, field
from datetime import datetime

from ..logging_setup import get_logger
from ..paths import DATA_DIR, ensure_dirs

log = get_logger("skills")

_FILE = DATA_DIR / "skills.json"


@dataclass
class Skill:
    name: str
    description: str = ""
    steps: list[dict] = field(default_factory=list)   # [{tool, args}]
    source: str = "user"
    verified: bool = False
    created_at: str = field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))
    runs: int = 0


class SkillStore:
    def __init__(self, path=_FILE):
        ensure_dirs()
        self._path = path
        self._lock = threading.Lock()
        self._skills: dict[str, Skill] = {}
        self._load()

    def _load(self):
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
            for d in data:
                self._skills[d["name"]] = Skill(**d)
        except Exception:
            pass

    def _save(self):
        try:
            self._path.write_text(
                json.dumps([asdict(s) for s in self._skills.values()],
                           ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception as exc:  # pragma: no cover
            log.warning("ذخیره‌ی مهارت‌ها ناموفق بود: %s", exc)

    def save(self, skill: Skill) -> None:
        with self._lock:
            self._skills[skill.name] = skill
            self._save()
        log.info("مهارت ذخیره شد: %s (%d گام)", skill.name, len(skill.steps))

    def get(self, name: str) -> Skill | None:
        return self._skills.get(name)

    def find(self, name: str) -> Skill | None:
        if name in self._skills:
            return self._skills[name]
        from ..text_fa import normalize
        n = normalize(name)
        for s in self._skills.values():
            if normalize(s.name) == n or n in normalize(s.name):
                return s
        return None

    def all(self) -> list[Skill]:
        return list(self._skills.values())

    def delete(self, name: str) -> bool:
        with self._lock:
            if name in self._skills:
                del self._skills[name]
                self._save()
                return True
        return False

    def mark_run(self, name: str) -> None:
        with self._lock:
            if name in self._skills:
                self._skills[name].runs += 1
                self._save()


_STORE: SkillStore | None = None
_LK = threading.Lock()


def get_store() -> SkillStore:
    global _STORE
    with _LK:
        if _STORE is None:
            _STORE = SkillStore()
        return _STORE
