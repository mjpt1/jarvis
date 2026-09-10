"""مدیریتِ مهارت‌ها — ساخت از آخرین مأموریت، اجرا، فهرست."""

from __future__ import annotations

from ..logging_setup import get_logger
from ..state import STATE
from . import lab
from .store import Skill, get_store

log = get_logger("skills")


class SkillManager:
    def __init__(self, cmd_engine):
        self.engine = cmd_engine
        self.title = cmd_engine.title
        self.store = get_store()

    def _tools(self):
        from ..missions.tools import build_default_registry
        return build_default_registry(self.engine)

    # ------------------------------------------------------------------
    def save_from_last_mission(self, name: str, description: str = "") -> str:
        from ..missions.engine import engine as _me
        me = _me()
        steps = getattr(me, "last_plan_steps", None) if me else None
        if not steps:
            return f"{self.title}، مأموریتِ اخیری برای ذخیره ندارم."
        clean = [{"tool": s.get("tool"), "args": s.get("args", {})} for s in steps]
        ok, msg = lab.validate(clean, self._tools())
        if not ok:
            return msg
        self.store.save(Skill(name=name, description=description or name,
                              steps=clean, source="mission", verified=True))
        return f"مهارتِ «{name}» با {len(clean)} گام ذخیره شد {self.title}."

    def save_steps(self, name: str, steps: list[dict], description: str = "") -> str:
        ok, msg = lab.validate(steps, self._tools())
        if not ok:
            return msg
        self.store.save(Skill(name=name, description=description or name, steps=steps))
        return f"مهارتِ «{name}» ذخیره شد {self.title}."

    def list_spoken(self) -> str:
        sk = self.store.all()
        if not sk:
            return f"{self.title}، هنوز مهارتی ندارم."
        return f"{self.title}، {len(sk)} مهارت دارم: " + "، ".join(s.name for s in sk)

    def dry_run(self, name: str) -> str:
        s = self.store.find(name)
        if not s:
            return f"[JRV-SKL-002] مهارتِ «{name}» پیدا نشد."
        _ok, report = lab.dry_run(s.steps, self._tools())
        return report

    def run(self, name: str) -> str:
        s = self.store.find(name)
        if not s:
            return f"[JRV-SKL-002] مهارتِ «{name}» را نمی‌شناسم {self.title}."
        tools = self._tools()
        ok, msg = lab.validate(s.steps, tools)
        if not ok:
            return msg
        STATE.log(f"SKILL {s.name}")
        done = 0
        for st in s.steps:
            tool = tools.get(st["tool"])
            if tool is None:
                continue
            try:
                tool.run(**st.get("args", {}))
                done += 1
            except Exception as exc:
                log.warning("گامِ مهارت خطا داد: %s", exc)
                return f"{self.title}، مهارتِ «{s.name}» تو گامِ «{st['tool']}» متوقف شد."
        self.store.mark_run(s.name)
        return f"مهارتِ «{s.name}» اجرا شد ({done} گام) {self.title}."
