"""حسِ زنده‌بودنِ جارویس — واکنش به حرکاتِ دست، حرکتِ جلوی دوربین، و جمله‌های محیطیِ خودجوش."""

from __future__ import annotations

import datetime
import random
import time

from .logging_setup import get_logger
from .state import STATE

log = get_logger("persona")

_last_gesture = {"name": "", "at": 0.0}
_last_react = 0.0


def _title(cfg) -> str:
    return getattr(cfg, "user_title", "قربان")


def _speak(text: str) -> None:
    from . import tts
    tts.say(text)


def _allowed() -> bool:
    """آیا الان اجازه‌ی واکنشِ خودجوش هست؟"""
    with STATE.lock:
        if STATE.speaking or STATE.audio_muted or STATE.onboarding_active:
            return False
    try:
        from .proactive.notifications import autonomy_allows, in_quiet_hours
        return autonomy_allows("notify") and not in_quiet_hours()
    except Exception:
        return True


# ============================================================
# واکنش به حرکاتِ دست
# ============================================================

_GESTURE_LINES = {
    "Open_Palm": ["سلام {t}، در خدمتم.", "بله {t}؟ گوش می‌کنم.", "سلام، بفرمایید."],
    "Thumb_Up": ["خوشحالم که راضی هستید {t}.", "ممنون {t}.", "قربونِ شما."],
    "Thumb_Down": ["متأسفم {t}، سعی می‌کنم بهتر بشم.", "چشم، درستش می‌کنم."],
    "Victory": ["یه عکس از صفحه گرفتم {t}.", "ثبت شد {t}."],
    "Pointing_Up": ["بله {t}؟ می‌شنوم.", "در خدمتم {t}."],
    "ILoveYou": ["منم به شما ارادت دارم {t}.", "لطف دارید {t}."],
    "Closed_Fist": ["چشم {t}، ساکت می‌شم.", "باشه {t}."],
}


def on_gesture(name: str, cfg, engine) -> None:
    """یک حرکتِ دست تشخیص داده شد."""
    global _last_gesture, _last_react
    now = time.time()
    if name in ("", "None"):
        return
    # همان حرکت پشتِ سرِ هم = یک واکنش
    if name == _last_gesture["name"] and now - _last_gesture["at"] < 6:
        return
    if now - _last_react < 3:
        return
    _last_gesture = {"name": name, "at": now}
    if not _allowed():
        return
    _last_react = now
    t = _title(cfg)
    STATE.log(f"GESTURE {name}")

    if name == "Victory":
        try:
            from . import system_actions
            system_actions.screenshot(t)
            return
        except Exception:
            pass
    elif name == "Closed_Fist":
        try:
            if getattr(STATE, "now_playing", ""):
                engine.music.pause()
                return
        except Exception:
            pass
    elif name == "Pointing_Up":
        with STATE.lock:
            STATE.conversation_active = True
            STATE.awaiting_command = True

    lines = _GESTURE_LINES.get(name)
    if lines:
        _speak(random.choice(lines).replace("{t}", t))


# ============================================================
# واکنش به حرکتِ جلوی دوربین
# ============================================================

_last_motion_react = 0.0


def on_motion(cfg) -> None:
    global _last_motion_react
    now = time.time()
    if now - _last_motion_react < 90:
        return
    if not _allowed():
        return
    with STATE.lock:
        face = STATE.face_present
    _last_motion_react = now
    t = _title(cfg)
    if face:
        return
    _speak(random.choice([
        f"یه حرکتی جلوی دوربین حس کردم {t}.",
        f"{t}، کسی اونجاست؟",
        "حرکتی دیدم؛ همه‌چیز مرتبه؟",
    ]))


# ============================================================
# جمله‌های محیطیِ خودجوش
# ============================================================

def _time_bucket() -> str:
    h = datetime.datetime.now().hour
    if 5 <= h < 12:
        return "morning"
    if 12 <= h < 17:
        return "noon"
    if 17 <= h < 22:
        return "evening"
    return "late"


_AMBIENT = {
    "morning": ["صبحتون بخیر {t}. امیدوارم امروز روزِ خوبی داشته باشید.",
                "{t}، صبح شده. اگه برنامه‌ای دارید بگید یادداشت کنم."],
    "noon": ["ظهر شده {t}. یادتون نره یه چیزی بخورید.",
             "{t}، وسطِ روزه؛ اگه خسته‌اید چند دقیقه استراحت بد نیست."],
    "evening": ["عصر بخیر {t}.", "{t}، هوا داره تاریک می‌شه؛ چراغ‌ها رو روشن کنم براتون یادآوری کنم؟"],
    "late": ["دیر وقته {t}. اگه کاری ندارید بهتره استراحت کنید.",
             "{t}، نیمه‌شبه. من بیدارم اگه چیزی خواستید."],
}


def idle_worker(cfg, engine) -> None:
    """هر چند دقیقه سکوت، یک جمله‌ی محیطی می‌گوید (اگر autonomy اجازه بدهد)."""
    if not cfg.alive_enabled:
        return
    interval = max(3, cfg.idle_remark_minutes) * 60
    last_heard_seen = ""
    quiet_since = time.time()
    while STATE.running:
        if STATE.stop_event.wait(30):
            return
        with STATE.lock:
            lh = STATE.last_heard_text
            speaking = STATE.speaking
            present = STATE.owner_present or not STATE.owner_gate_active
        if lh != last_heard_seen or speaking:
            last_heard_seen = lh
            quiet_since = time.time()
            continue
        if time.time() - quiet_since < interval:
            continue
        quiet_since = time.time()
        if not (_allowed() and present):
            continue
        line = random.choice(_AMBIENT[_time_bucket()]).replace("{t}", _title(cfg))
        STATE.log("AMBIENT")
        _speak(line)


def greet_owner(cfg) -> None:
    """وقتی صاحب بعد از مدتی دوباره جلوی دوربین ظاهر می‌شود."""
    if not _allowed():
        return
    t = _title(cfg)
    _speak(random.choice([f"سلام {t}، خوش اومدید.", f"دوباره سلام {t}.",
                          f"{t}، برگشتید. در خدمتم."]))
