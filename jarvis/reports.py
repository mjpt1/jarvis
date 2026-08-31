"""متنِ گزارش‌های زنده که جارویس با صدا می‌خواند."""

from __future__ import annotations

import datetime
import time
import urllib.request

from .logging_setup import get_logger
from .state import STATE

log = get_logger("reports")

APP_START = time.time()
ROLL_TILT = 16
YAW_MAX = 8

_T = "قربان"  # با configure جایگزین می‌شود
_NEWS_URL = "https://feeds.bbci.co.uk/persian/rss.xml"


def configure(title: str, news_url: str) -> None:
    global _T, _NEWS_URL
    _T, _NEWS_URL = title, news_url


def status() -> str:
    with STATE.lock:
        face, yaw, roll = STATE.face_present, STATE.yaw, STATE.roll
    if not face:
        return f"{_T}، الان چهره‌ای رو ردیابی نمی‌کنم."
    tilt = "صاف" if abs(roll) < ROLL_TILT else "کج"
    if abs(yaw) < YAW_MAX:
        direction = "مستقیم رو به دوربین"
    else:
        direction = "چرخیده به راست" if yaw > 0 else "چرخیده به چپ"
    return f"{_T}، در حال ردیابی چهره‌تونم. سرتون {tilt}ه و {direction}."


def clock() -> str:
    now = datetime.datetime.now()
    return f"ساعت {now.hour} و {now.minute} دقیقه‌ست {_T}."


def elapsed() -> str:
    mins = int((time.time() - APP_START) // 60)
    if mins <= 0:
        return f"همین الان شروع کردیم {_T}."
    return f"{mins} دقیقه از شروع کار می‌گذره {_T}."


def system() -> str:
    with STATE.lock:
        cpu, ram, batt = STATE.cpu_percent, STATE.ram_percent, STATE.battery_percent
    text = f"پردازنده {cpu:.0f} درصد و رم {ram:.0f} درصد در حال استفاده‌ست {_T}."
    if batt is not None:
        text += f" باتری {batt:.0f} درصده."
    return text


def weather() -> str:
    with STATE.lock:
        temp, loc = STATE.weather_temp, STATE.location_name
    if temp is None:
        return f"{_T}، هنوز به اطلاعات آب‌وهوا دسترسی پیدا نکردم."
    loc_part = f" در {loc}" if loc else ""
    return f"دمای هوا{loc_part} الان {temp:.0f} درجه‌ست {_T}."


def news() -> str:
    try:
        req = urllib.request.Request(_NEWS_URL, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=6) as r:
            raw = r.read()
        import xml.etree.ElementTree as ET
        root = ET.fromstring(raw)
        titles = [(it.findtext("title") or "").strip() for it in root.iter("item")]
        titles = [t for t in titles if t][:3]
        if not titles:
            return f"{_T}، الان خبری پیدا نکردم."
        return "چند تیتر خبر: " + "؛ ".join(titles)
    except Exception as exc:
        log.warning("دریافت اخبار ناموفق: %s", exc)
        return f"{_T}، الان به فید خبری دسترسی ندارم."
