"""صفِ اعلان‌ها و تحویلشان با رعایتِ سطحِ خودمختاری و ساعتِ سکوت."""

from __future__ import annotations

import datetime
import threading
from dataclasses import dataclass, field

from ..logging_setup import get_logger
from ..state import STATE

log = get_logger("proactive")

# سطحِ خودمختاری:
#   0 هیچ کارِ خودجوشی · 1 فقط اعلانِ صوتی/متنی · 2 +ابزارِ خواندنیِ خودجوش
#   3 +مأموریتِ پیشنهادی با تاییدِ صوتی · 4 +بدون تایید (امن) · 5 کامل
_AUTONOMY = 1
_QUIET = (23, 8)


def configure(autonomy_level: int, quiet_hours: list[int]) -> None:
    global _AUTONOMY, _QUIET
    _AUTONOMY = max(0, min(5, autonomy_level))
    if quiet_hours and len(quiet_hours) == 2:
        _QUIET = (quiet_hours[0], quiet_hours[1])


def autonomy() -> int:
    return _AUTONOMY


def set_autonomy(level: int) -> int:
    global _AUTONOMY
    _AUTONOMY = max(0, min(5, level))
    return _AUTONOMY


def autonomy_allows(action: str) -> bool:
    need = {"notify": 1, "read_tool": 2, "propose_mission": 3,
            "auto_mission": 4, "anything": 5}.get(action, 5)
    return _AUTONOMY >= need


def quiet_until_morning() -> None:
    global _QUIET
    _QUIET = (datetime.datetime.now().hour, 8)


def in_quiet_hours(now: datetime.datetime | None = None) -> bool:
    h = (now or datetime.datetime.now()).hour
    a, b = _QUIET
    return a <= h or h < b if a > b else a <= h < b


@dataclass
class Notification:
    text: str
    source: str = "system"
    level: str = "info"                 # info | warn | urgent
    at: str = field(default_factory=lambda: datetime.datetime.now().strftime("%H:%M"))
    delivered_voice: bool = False


_LOCK = threading.Lock()
_ITEMS: list[Notification] = []


def push(text: str, *, source: str = "system", level: str = "info",
         speak: bool = True, telegram: bool = True) -> Notification:
    n = Notification(text=text, source=source, level=level)
    with _LOCK:
        _ITEMS.append(n)
        del _ITEMS[:-40]
    STATE.log(f"PROACTIVE: {text[:50]}")
    log.info("اعلان [%s/%s]: %s", source, level, text)

    quiet = in_quiet_hours() and level != "urgent"

    if speak and autonomy_allows("notify") and not quiet:
        with STATE.lock:
            present = STATE.owner_present or not STATE.owner_gate_active
        if present:
            try:
                from .. import tts
                tts.say(text)
                n.delivered_voice = True
            except Exception:
                pass

    if telegram:
        try:
            from ..integrations.telegram_bot import notify_owner
            notify_owner(f"🔔 {text}")
        except Exception:
            pass
    return n


def recent(limit: int = 20) -> list[dict]:
    with _LOCK:
        return [{"text": n.text, "source": n.source, "level": n.level, "at": n.at}
                for n in _ITEMS[-limit:]][::-1]


class _Notify:
    push = staticmethod(push)
    recent = staticmethod(recent)


NOTIFY = _Notify()
