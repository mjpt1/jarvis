"""بات تلگرام — long-polling با urllib، بدون وابستگی.

فقط `telegram_owner_id` می‌تواند با بات حرف بزند. پیام‌ها به jarvis.brain.respond
می‌روند (همان حافظه و Claude). به‌صورت یک تردِ پس‌زمینه اجرا می‌شود.
"""

from __future__ import annotations

import json
import time
import urllib.parse
import urllib.request

from ..logging_setup import get_logger
from ..state import STATE

log = get_logger("telegram")

_TOKEN = ""
_OWNER = 0
_PROXY = ""
_opener = None


def configure(token: str, owner_id: int, proxy: str = "") -> None:
    global _TOKEN, _OWNER, _PROXY, _opener
    _TOKEN, _OWNER, _PROXY = token, owner_id, (proxy or "").strip()
    _opener = _build_opener(_PROXY)


def _build_opener(proxy: str):
    if not proxy:
        return urllib.request.build_opener()
    if proxy.startswith(("socks5://", "socks4://", "socks://", "socks5h://")):
        try:
            import socks  # PySocks
            from sockshandler import SocksiPyHandler
        except Exception:
            log.warning("برای پروکسیِ SOCKS باید PySocks نصب شود: pip install pysocks")
            return urllib.request.build_opener()
        kind = socks.SOCKS4 if proxy.startswith("socks4") else socks.SOCKS5
        rest = proxy.split("://", 1)[1]
        host, _, port = rest.partition(":")
        return urllib.request.build_opener(
            SocksiPyHandler(kind, host, int(port or 1080), rdns=True))
    # پروکسیِ HTTP
    return urllib.request.build_opener(
        urllib.request.ProxyHandler({"http": proxy, "https": proxy}))


def available() -> bool:
    return bool(_TOKEN)


def _api(method: str, **params) -> dict:
    url = f"https://api.telegram.org/bot{_TOKEN}/{method}"
    data = urllib.parse.urlencode(params).encode()
    req = urllib.request.Request(url, data=data)
    opener = _opener or urllib.request.build_opener()
    with opener.open(req, timeout=40) as r:
        return json.loads(r.read().decode())


def send(chat_id: int, text: str) -> None:
    try:
        for chunk in (text[i:i + 3800] for i in range(0, len(text), 3800)):
            _api("sendMessage", chat_id=chat_id, text=chunk)
    except Exception as exc:
        log.warning("ارسال پیام تلگرام ناموفق بود: %s", exc)


def notify_owner(text: str) -> None:
    """اعلانِ پیش‌کنشی به صاحب (برای فازهای بعدی: هشدارها)."""
    if _TOKEN and _OWNER:
        send(_OWNER, text)


def _handle(chat_id: int, user_id: int, text: str) -> None:
    if _OWNER and user_id != _OWNER:
        send(chat_id, "این بات خصوصی است.")
        log.warning("پیام از کاربرِ غیرمجاز: %s", user_id)
        return
    if text.strip() in ("/start", "/help"):
        send(chat_id, "سلام قربان. من جارویسم — هر چی بپرسید همین‌جا جواب می‌دم؛ "
                      "«یادت باشه که…»، «چی یادته درباره…»، «سرچ کن…» هم کار می‌کنه.")
        return
    from ..brain import respond
    log.info("تلگرام: %r", text)
    try:
        reply = respond(text)
    except Exception as exc:
        log.warning("brain.respond خطا داد: %s", exc)
        reply = "خطایی پیش اومد."
    send(chat_id, reply or "…")


def worker() -> None:
    if not available():
        return
    try:
        me = _api("getMe")
        log.info("بات تلگرام فعال شد: @%s", me.get("result", {}).get("username", "?"))
    except Exception as exc:
        log.warning("اتصال به تلگرام ناموفق بود: %s", exc)
        return

    with STATE.lock:
        STATE.telegram_enabled = True
    offset = 0
    while STATE.running:
        try:
            res = _api("getUpdates", offset=offset, timeout=30)
        except Exception as exc:
            log.debug("getUpdates: %s", exc)
            time.sleep(3)
            continue
        for upd in res.get("result", []):
            offset = upd["update_id"] + 1
            msg = upd.get("message") or upd.get("edited_message")
            if not msg or "text" not in msg:
                continue
            _handle(msg["chat"]["id"], msg["from"]["id"], msg["text"])

    with STATE.lock:
        STATE.telegram_enabled = False
