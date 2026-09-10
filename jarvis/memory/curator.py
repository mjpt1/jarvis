"""بازیابیِ حافظه برای Claude + استخراجِ خودکارِ حقایق («AutoDream»)."""

from __future__ import annotations

import json
import re

from ..logging_setup import get_logger
from . import markdown_mirror
from .store import MemoryStore, get_store

log = get_logger("memory")

_CATEGORIES = ["identity", "preference", "people", "work", "schedule",
               "home", "health", "finance", "general"]


def recall_context(text: str, limit: int = 6, store: MemoryStore | None = None) -> str:
    """رشته‌ای از حقایقِ مرتبط برای تزریق به system prompt جارویس."""
    store = store or get_store()
    hits = store.search(text, limit=limit)
    if not hits:
        # حقایقِ هویتی/ترجیحی همیشه مفیدند
        hits = store.by_category("identity")[:3] + store.by_category("preference")[:3]
    if not hits:
        return ""
    lines = [f"- ({f.short_date()}) {f.text}" for f in hits]
    return "چیزهایی که از قبل می‌دانی:\n" + "\n".join(lines)


def remember(text: str, *, category: str = "general", source: str = "user",
             tags: list[str] | None = None, store: MemoryStore | None = None):
    store = store or get_store()
    fact = store.add_fact(text, category=category, source=source, tags=tags or [])
    try:
        markdown_mirror.rebuild(store)
    except Exception as exc:  # pragma: no cover
        log.warning("بازسازی آینه‌ی Markdown ناموفق بود: %s", exc)
    return fact


_EXTRACT_SYS = (
    "تو دستیارِ استخراجِ حافظه‌ای. از گفت‌وگوی زیر فقط «حقایقِ ماندگار درباره‌ی کاربر "
    "یا زندگی‌اش» را دربیاور: ترجیح‌ها، اسم افراد، کارها، برنامه‌ها، عادت‌ها، "
    "تصمیم‌ها. چیزهای گذرا (سؤال‌های لحظه‌ای، خوش‌وبش) را نادیده بگیر. "
    "خروجی فقط یک آرایه‌ی JSON از اشیاء با کلیدهای \"text\" (جمله‌ی کوتاه و مستقل به فارسی) "
    f"و \"category\" (یکی از: {', '.join(_CATEGORIES)}). اگر چیزی نبود، []."
)


def _parse_json_array(raw: str):
    m = re.search(r"\[.*\]", raw, re.S)
    if not m:
        return []
    try:
        data = json.loads(m.group(0))
        return data if isinstance(data, list) else []
    except Exception:
        return []


def extract_from_turns(turns: list[dict], store: MemoryStore | None = None) -> int:
    """از چند پیامِ اخیرِ مکالمه حقایقِ تازه را می‌کِشد و ذخیره می‌کند."""
    from .. import claude_client
    if not claude_client.available() or not turns:
        return 0
    convo = "\n".join(f"{t['role']}: {t['content']}" for t in turns
                      if isinstance(t.get("content"), str))
    raw = claude_client.oneshot(_EXTRACT_SYS, convo, max_tokens=700)
    items = _parse_json_array(raw or "")
    store = store or get_store()
    added = 0
    for it in items:
        txt = (it.get("text") or "").strip()
        if not txt:
            continue
        cat = it.get("category") if it.get("category") in _CATEGORIES else "general"
        before = store.get(store.add_fact(txt, category=cat, source="auto").id)
        if before and before.reinforcement == 0:
            added += 1
    if added:
        try:
            markdown_mirror.rebuild(store)
        except Exception:  # pragma: no cover
            pass
        log.info("AutoDream: %d حقیقت تازه اضافه شد.", added)
    return added
