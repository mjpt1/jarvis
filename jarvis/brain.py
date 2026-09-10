"""پاسخِ متنی مشترک — استفاده‌ی مشترکِ بات تلگرام و هر رابطِ متنیِ دیگر.

خروجی همیشه یک رشته است (برخلافِ CommandEngine که با صدا جواب می‌دهد).
"""

from __future__ import annotations

from .logging_setup import get_logger
from .text_fa import normalize

log = get_logger("brain")


def respond(text: str) -> str:
    text = (text or "").strip()
    if not text:
        return "بله؟"
    n = normalize(text)

    # --- حافظه ---
    if any(k in n for k in ("یادت باشه", "به خاطر بسپار", "یادداشت کن", "به یاد داشته باش")):
        from .memory.curator import remember
        content = text
        for p in ("این رو یادت باشه که", "یادت باشه که", "به خاطر بسپار که",
                  "یادداشت کن که", "به یاد داشته باش که", "یادت باشه", "به خاطر بسپار"):
            content = content.replace(p, "")
        content = content.strip(" ،.:")
        if len(content) < 3:
            return "چی رو یادم باشه؟"
        remember(content, source="telegram")
        return f"یادم می‌مونه: {content}"

    if any(k in n for k in ("چی یادته", "چی می‌دونی درباره", "درباره‌ش چی")):
        from .memory.store import get_store
        topic = n
        for p in ("چی یادته درباره", "چی یادته", "چی می‌دونی درباره", "درباره‌ش چی می‌دونی",
                  "درباره", "راجع به"):
            topic = topic.replace(p, " ")
        hits = get_store().search(topic.strip(), limit=5)
        if not hits:
            return "چیزی دربارهٔ این یادم نیست."
        return "این‌ها یادمه:\n" + "\n".join(f"• {f.text}" for f in hits)

    # --- وب ---
    if any(n.startswith(k) for k in ("سرچ کن", "بگرد", "جستجو کن", "تو وب بگرد", "گوگل کن")):
        from .integrations import web
        for p in ("سرچ کن", "بگرد", "جستجو کن", "تو وب بگرد", "گوگل کن", "درباره", "دنبال"):
            text = text.replace(p, "")
        return web.answer(text.strip(" ؟?،."))

    # --- گفت‌وگوی آزاد با Claude (+ حافظه) ---
    from . import claude_client
    reply = claude_client.ask(text)
    return reply or "الان نمی‌تونم جواب بدم (کلیدِ Claude تنظیم شده؟)."
