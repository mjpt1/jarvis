"""موتور مأموریت: برنامه‌ریزی با Claude → اجرای گام‌به‌گام → راستی‌آزمایی → ذخیره."""

from __future__ import annotations

import json
import re
import threading

from ..logging_setup import get_logger
from ..state import STATE
from .store import MissionStore, get_store
from .tools import ToolRegistry, build_default_registry

log = get_logger("missions")

_PLAN_SYS = """تو برنامه‌ریزِ مأموریتِ یک دستیارِ صوتی فارسی هستی.
درخواستِ کاربر را به مجموعه‌ای کوتاه از گام‌های اجرایی تبدیل کن.
فقط از این ابزارها استفاده کن:

{catalog}

خروجی فقط یک شیء JSON:
{{"steps": [{{"tool": "<نام ابزار>", "args": {{...}}, "check": "<چطور بفهمیم این گام موفق شد>"}}]}}
اگر درخواست مبهم یا خطرناک است، steps را خالی بگذار و کلید "reason" را توضیح بده.
حداکثر {max_steps} گام. جملهٔ پایانیِ جمع‌بندی را با یک گامِ say اضافه کن."""


def _parse_plan(raw: str) -> dict:
    m = re.search(r"\{.*\}", raw or "", re.S)
    if not m:
        return {"steps": []}
    try:
        data = json.loads(m.group(0))
        return data if isinstance(data, dict) else {"steps": []}
    except Exception:
        return {"steps": []}


class MissionEngine:
    def __init__(self, cmd_engine, store: MissionStore | None = None):
        self.cmd_engine = cmd_engine
        self.cfg = cmd_engine.cfg
        self.title = cmd_engine.title
        self.store = store or get_store()
        self.tools: ToolRegistry = build_default_registry(cmd_engine)
        self.last_plan_steps: list[dict] = []

    # ------------------------------------------------------------------
    def plan(self, request: str) -> dict:
        from .. import claude_client
        if not claude_client.available():
            return {"steps": [], "reason": "برای مأموریت به کلید Claude نیاز دارم"}
        sys = _PLAN_SYS.format(catalog=self.tools.catalog(),
                               max_steps=self.cfg.mission_max_steps)
        raw = claude_client.oneshot(sys, request, max_tokens=1200)
        plan = _parse_plan(raw or "")
        plan["steps"] = [s for s in plan.get("steps", [])
                         if s.get("tool") in self.tools][: self.cfg.mission_max_steps]
        return plan

    def verify(self, step_tool: str, check_hint: str, result: str) -> bool:
        """راستی‌آزماییِ سبک: ساختاری همیشه، معنایی فقط اگر check مبهم بود."""
        if not result:
            return False
        return True  # فاز ۱: نتیجه‌ی ok از ابزار کافی است

    def run(self, request: str) -> None:
        from .. import tts
        mid = self.store.create(request)
        STATE.log(f"MISSION #{mid}")
        plan = self.plan(request)
        steps = plan.get("steps", [])
        if not steps:
            reason = plan.get("reason") or "نتونستم این رو به گام‌های روشن تبدیل کنم"
            tts.say(f"{self.title}، {reason}.")
            self.store.set_status(mid, "failed")
            return

        self.last_plan_steps = [{"tool": s.get("tool"), "args": s.get("args", {})}
                                for s in steps]
        self.store.add_steps(mid, steps)
        self.store.set_status(mid, "running")
        tts.say(f"باشه {self.title}، {len(steps)} مرحله برای این کار دارم. شروع می‌کنم.")
        self._execute(mid)

    def _execute(self, mid: int) -> None:
        from .. import tts
        rows = self.store.steps(mid)
        done = 0
        for row in rows:
            if row["status"] in ("ok", "skipped"):
                done += 1
                continue
            if not STATE.running:
                return
            tool = self.tools.get(row["tool"])
            if tool is None:
                self.store.update_step(row["id"], "skipped", "ابزار ناموجود")
                continue
            try:
                args = json.loads(row["args"] or "{}")
            except Exception:
                args = {}
            self.store.update_step(row["id"], "running")
            log.info("مأموریت #%d گام %d: %s(%s)", mid, row["idx"], row["tool"], args)
            try:
                res = tool.run(**args)
            except TypeError:
                res = tool.run()
            except Exception as exc:
                res = None
                log.warning("گام خطا داد: %s", exc)

            ok = bool(res) and self.verify(row["tool"], row["check_hint"],
                                           getattr(res, "output", ""))
            self.store.update_step(row["id"], "ok" if ok else "failed",
                                   getattr(res, "output", "") if res else "خطا")
            if ok:
                done += 1
            else:
                tts.say(f"{self.title}، تو مرحلهٔ «{row['tool']}» گیر کردم. "
                        f"بقیهٔ کار رو ادامه بدم؟")
                self.store.set_status(mid, "failed")
                return

        self.store.set_status(mid, "done")
        STATE.log(f"MISSION #{mid} ✓")
        tts.say(f"{self.title}، مأموریت تموم شد؛ {done} مرحله انجام شد.")

    def resume_unfinished(self) -> None:
        from .. import tts
        rows = self.store.unfinished()
        if not rows:
            return
        log.info("%d مأموریتِ ناتمام پیدا شد.", len(rows))
        for row in rows[:1]:
            tts.say(f"{self.title}، یک مأموریتِ ناتمام از قبل دارم: «{row['request']}». "
                    f"ادامه‌اش می‌دم.")
            if row["status"] == "planning":
                self.store.set_status(row["id"], "failed")
            else:
                self._execute(row["id"])


_ENGINE: MissionEngine | None = None


def attach(cmd_engine) -> MissionEngine:
    global _ENGINE
    _ENGINE = MissionEngine(cmd_engine)
    return _ENGINE


def run_mission_async(request: str, cmd_engine) -> None:
    eng = _ENGINE or attach(cmd_engine)
    threading.Thread(target=eng.run, args=(request,), daemon=True).start()
