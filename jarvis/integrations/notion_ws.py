"""جست‌وجو و خواندنِ صفحه‌های Notion — فقط با urllib، نیاز به Integration Token.

صفحه‌ها باید با این Integration به اشتراک گذاشته شده باشند.
"""

from __future__ import annotations

import json
import urllib.request

from ..logging_setup import get_logger

log = get_logger("notion")

_TOKEN = ""
_VERSION = "2022-06-28"
_BASE = "https://api.notion.com/v1"


def configure(token: str) -> None:
    global _TOKEN
    _TOKEN = token


def available() -> bool:
    return bool(_TOKEN)


def _req(method: str, path: str, body: dict | None = None) -> dict:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(f"{_BASE}{path}", data=data, method=method, headers={
        "Authorization": f"Bearer {_TOKEN}",
        "Notion-Version": _VERSION,
        "Content-Type": "application/json",
    })
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read().decode())


def _title_of(page: dict) -> str:
    props = page.get("properties", {})
    for p in props.values():
        if p.get("type") == "title":
            parts = p.get("title", [])
            if parts:
                return "".join(t.get("plain_text", "") for t in parts)
    return "(بی‌عنوان)"


def search(query: str, limit: int = 5) -> list[dict]:
    try:
        res = _req("POST", "/search", {"query": query, "page_size": limit})
        out = []
        for r in res.get("results", []):
            if r.get("object") == "page":
                out.append({"id": r["id"], "title": _title_of(r),
                            "url": r.get("url", "")})
        return out
    except Exception as exc:
        log.warning("Notion search: %s", exc)
        return []


def _blocks_text(block_id: str, depth: int = 0) -> str:
    if depth > 3:
        return ""
    try:
        res = _req("GET", f"/blocks/{block_id}/children?page_size=100")
    except Exception:
        return ""
    lines = []
    for b in res.get("results", []):
        t = b.get("type", "")
        rich = b.get(t, {}).get("rich_text", []) if isinstance(b.get(t), dict) else []
        text = "".join(x.get("plain_text", "") for x in rich)
        if text:
            lines.append(text)
        if b.get("has_children"):
            child = _blocks_text(b["id"], depth + 1)
            if child:
                lines.append(child)
    return "\n".join(lines)


def read_page(page_id: str) -> str:
    txt = _blocks_text(page_id)
    return txt[:6000] or "(این صفحه متنی ندارد یا با Integration به اشتراک گذاشته نشده.)"


def search_and_read(query: str) -> str:
    hits = search(query, limit=3)
    if not hits:
        return "صفحه‌ای در Notion پیدا نشد (به اشتراک‌گذاری با Integration را بررسی کن)."
    top = hits[0]
    body = read_page(top["id"])
    others = "\n".join(f"- {h['title']}" for h in hits[1:])
    return f"«{top['title']}»:\n{body}" + (f"\n\nصفحه‌های دیگر:\n{others}" if others else "")
