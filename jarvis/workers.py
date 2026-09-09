"""تردهای پس‌زمینه: آمار سیستم و آب‌وهوا."""

from __future__ import annotations

import json
import time
import urllib.request

from .config import Config
from .logging_setup import get_logger
from .state import STATE

log = get_logger("workers")


def system_stats_worker(cfg: Config) -> None:
    try:
        import psutil
    except Exception as exc:
        log.warning("psutil در دسترس نیست — آمار سیستم غیرفعال: %s", exc)
        return

    last_net = None
    last_t = time.time()
    while STATE.running:
        try:
            cpu = psutil.cpu_percent(interval=cfg.system_stats_interval)
            ram = psutil.virtual_memory().percent
            batt = None
            try:
                b = psutil.sensors_battery()
                batt = b.percent if b is not None else None
            except Exception:
                pass

            now_net = psutil.net_io_counters()
            now_t = time.time()
            recv_kbps = 0.0
            if last_net is not None:
                dt = max(0.001, now_t - last_t)
                recv_kbps = max(0.0, (now_net.bytes_recv - last_net.bytes_recv) / 1024.0 / dt)
            last_net, last_t = now_net, now_t

            with STATE.lock:
                STATE.cpu_percent = cpu
                STATE.ram_percent = ram
                STATE.battery_percent = batt
                STATE.net_history.append(recv_kbps)
                del STATE.net_history[:-40]
        except Exception as exc:
            log.debug("خطای آمار سیستم: %s", exc)
            time.sleep(cfg.system_stats_interval)


def nightly_consolidation_worker(cfg: Config) -> None:
    """هر شب در ساعتِ تعیین‌شده، حقایقِ جامانده از مکالمه‌ها را استخراج و ذخیره می‌کند."""
    import datetime as _dt

    while STATE.running:
        now = _dt.datetime.now()
        target = now.replace(hour=cfg.nightly_consolidation_hour, minute=0,
                             second=0, microsecond=0)
        if target <= now:
            target += _dt.timedelta(days=1)
        wait_s = (target - now).total_seconds()
        if STATE.stop_event.wait(wait_s):
            return
        try:
            with STATE.lock:
                turns = list(STATE.chat_history)
            from .memory.curator import extract_from_turns
            from .memory import markdown_mirror
            from .memory.store import get_store
            n = extract_from_turns(turns)
            markdown_mirror.rebuild(get_store())
            log.info("نگهداریِ شبانه: %d حقیقتِ تازه.", n)
        except Exception as exc:
            log.warning("نگهداریِ شبانه ناموفق بود: %s", exc)


def _current_temp(lat, lon, ua) -> float | None:
    url = (f"https://api.open-meteo.com/v1/forecast?latitude={lat}"
           f"&longitude={lon}&current_weather=true")
    with urllib.request.urlopen(urllib.request.Request(url, headers=ua), timeout=5) as r:
        return json.loads(r.read().decode()).get("current_weather", {}).get("temperature")


def weather_worker(cfg: Config) -> None:
    ua = {"User-Agent": "Mozilla/5.0"}
    while STATE.running:
        try:
            req = urllib.request.Request("http://ip-api.com/json/", headers=ua)
            with urllib.request.urlopen(req, timeout=5) as r:
                loc = json.loads(r.read().decode())
            lat, lon, city = loc.get("lat"), loc.get("lon"), loc.get("city", "")
            if lat is not None and lon is not None:
                temp = _current_temp(lat, lon, ua)
                with STATE.lock:
                    STATE.weather_temp = temp
                    STATE.location_name = city
        except Exception as exc:
            log.debug("آب‌وهوا در دسترس نیست: %s", exc)

        try:
            temp2 = _current_temp(cfg.secondary_lat, cfg.secondary_lon, ua)
            with STATE.lock:
                STATE.secondary_temp = temp2
                STATE.secondary_name = cfg.secondary_city
        except Exception as exc:
            log.debug("آب‌وهوای مکان دوم در دسترس نیست: %s", exc)
        if STATE.stop_event.wait(cfg.weather_update_interval):
            break
