"""فال‌بک به Claude برای دستورهای آزاد — با حافظه‌ی کوتاه‌مدت و tool-use اختیاری.

اگر کلید API تنظیم نشده باشد، همه‌ی توابع None برمی‌گردانند و برنامه بدون آن کار می‌کند.
"""

from __future__ import annotations

import json
import urllib.request

from .logging_setup import get_logger
from .state import STATE

log = get_logger("claude")

_API_URL = "https://api.anthropic.com/v1/messages"

_KEY = ""
_MODEL = "claude-haiku-4-5-20251001"
_MAX_TURNS = 6
_TITLE = "قربان"
_ALLOW_ACTIONS = True

# name -> (توضیح فارسی، callable)
_ACTIONS: dict[str, tuple[str, callable]] = {}


def configure(*, api_key: str, model: str, max_turns: int, title: str,
              allow_actions: bool) -> None:
    global _KEY, _MODEL, _MAX_TURNS, _TITLE, _ALLOW_ACTIONS
    _KEY, _MODEL, _MAX_TURNS = api_key, model, max_turns
    _TITLE, _ALLOW_ACTIONS = title, allow_actions


def register_action(name: str, description: str, fn) -> None:
    _ACTIONS[name] = (description, fn)


def available() -> bool:
    return bool(_KEY)


def _system_prompt() -> str:
    return (
        f"تو «جارویس» هستی، یک دستیار صوتی فارسی‌زبان که کاربر را «{_TITLE}» صدا می‌زند. "
        "کوتاه، مؤدب و طبیعی جواب بده (حداکثر ۲ تا ۳ جمله)، چون پاسخت با صدا خوانده می‌شود. "
        "اگر کاربر خواست کاری روی کامپیوتر انجام شود و ابزار مناسبش را داری، از ابزار استفاده کن."
    )


def _tools_schema():
    if not (_ALLOW_ACTIONS and _ACTIONS):
        return None
    return [{
        "name": "perform_action",
        "description": "اجرای یک اقدام از پیش تعریف‌شده روی کامپیوتر کاربر.",
        "input_schema": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": list(_ACTIONS),
                    "description": " | ".join(f"{k}: {v[0]}" for k, v in _ACTIONS.items()),
                },
                "argument": {"type": "string", "description": "آرگومان اختیاری (مثلاً متن جستجو)"},
            },
            "required": ["action"],
        },
    }]


def _post(payload: dict) -> dict | None:
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(_API_URL, data=body, headers={
        "content-type": "application/json",
        "x-api-key": _KEY,
        "anthropic-version": "2023-06-01",
    })
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return json.loads(r.read().decode())
    except Exception as exc:  # pragma: no cover - شبکه
        log.warning("تماس با Claude ناموفق بود: %s", exc)
        return None


def ask(user_text: str) -> str | None:
    if not _KEY:
        return None

    with STATE.lock:
        history = list(STATE.chat_history)

    messages = history + [{"role": "user", "content": user_text}]
    payload = {
        "model": _MODEL,
        "max_tokens": 400,
        "system": _system_prompt(),
        "messages": messages,
    }
    tools = _tools_schema()
    if tools:
        payload["tools"] = tools

    data = _post(payload)
    if not data:
        return None

    # اجرای ابزار در صورت درخواست
    if data.get("stop_reason") == "tool_use":
        assistant_content = data.get("content", [])
        tool_results = []
        for block in assistant_content:
            if block.get("type") == "tool_use" and block.get("name") == "perform_action":
                inp = block.get("input", {})
                name = inp.get("action")
                arg = inp.get("argument", "")
                ok = _dispatch_action(name, arg)
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block.get("id"),
                    "content": "انجام شد" if ok else "این اقدام در دسترس نبود",
                })
        messages.append({"role": "assistant", "content": assistant_content})
        messages.append({"role": "user", "content": tool_results})
        payload["messages"] = messages
        data = _post(payload) or data

    reply = "".join(b.get("text", "") for b in data.get("content", [])
                    if b.get("type") == "text").strip()
    if not reply:
        return None

    with STATE.lock:
        STATE.chat_history.append({"role": "user", "content": user_text})
        STATE.chat_history.append({"role": "assistant", "content": reply})
        del STATE.chat_history[:-(_MAX_TURNS * 2)]
    return reply


def _dispatch_action(name: str | None, argument: str) -> bool:
    entry = _ACTIONS.get(name or "")
    if not entry:
        return False
    _desc, fn = entry
    try:
        if argument:
            try:
                fn(argument)
            except TypeError:
                fn()
        else:
            fn()
        STATE.log(f"CLAUDE→{name}")
        return True
    except Exception as exc:
        log.warning("اجرای اقدام %s ناموفق بود: %s", name, exc)
        return False
