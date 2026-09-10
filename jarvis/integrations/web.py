"""جست‌وجو و خواندنِ صفحه‌ی وب — بدون کلید.

- search(query): چند نتیجه از DuckDuckGo HTML (بدون API).
- fetch(url): متنِ اصلیِ صفحه را برمی‌گرداند (BeautifulSoup اگر نصب باشد، وگرنه regex ساده).
- summarize(url|query): با Claude خلاصه می‌کند (اگر کلید باشد).
"""

from __future__ import annotations

import html
import json
import re
import urllib.parse
import urllib.request

from ..logging_setup import get_logger

log = get_logger("web")

_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")
_MAX_CHARS = 4000
_PROXY = ""
_opener = None


def configure(max_chars: int, proxy: str = "") -> None:
    global _MAX_CHARS, _PROXY, _opener
    _MAX_CHARS = max_chars
    _PROXY = (proxy or "").strip()
    _opener = (urllib.request.build_opener(
        urllib.request.ProxyHandler({"http": _PROXY, "https": _PROXY}))
        if _PROXY else urllib.request.build_opener())


def available() -> bool:
    return True


def _get(url: str, timeout: int = 12, tries: int = 2) -> str:
    op = _opener or urllib.request.build_opener()
    last = None
    for _ in range(tries):
        try:
            req = urllib.request.Request(url, headers={
                "User-Agent": _UA, "Accept-Language": "fa,en;q=0.8"})
            with op.open(req, timeout=timeout) as r:
                raw = r.read()
            for enc in ("utf-8", "cp1256", "latin-1"):
                try:
                    return raw.decode(enc)
                except UnicodeDecodeError:
                    continue
            return raw.decode("utf-8", "ignore")
        except Exception as exc:
            last = exc
    raise last  # type: ignore[misc]


def _get_json(url: str, timeout: int = 10) -> dict:
    return json.loads(_get(url, timeout=timeout, tries=2))


# ---------------- ویکی‌پدیا (قابل‌اعتمادترین برای سؤال‌های واقعی) ----------------

def wiki_summary(query: str, langs=("fa", "en")) -> dict | None:
    for lang in langs:
        try:
            api = (f"https://{lang}.wikipedia.org/w/api.php?action=query&list=search"
                   f"&srsearch={urllib.parse.quote(query)}&srlimit=1&format=json")
            hits = _get_json(api).get("query", {}).get("search", [])
            if not hits:
                continue
            title = hits[0]["title"]
            s = _get_json(f"https://{lang}.wikipedia.org/api/rest_v1/page/summary/"
                          f"{urllib.parse.quote(title.replace(' ', '_'))}")
            extract = s.get("extract", "")
            if extract:
                return {"title": title, "extract": extract, "lang": lang,
                        "url": s.get("content_urls", {}).get("desktop", {}).get("page", "")}
        except Exception as exc:
            log.debug("wiki %s: %s", lang, exc)
    return None


def _ddg_lite(query: str, limit: int) -> list[dict]:
    q = urllib.parse.quote(query)
    for base in ("https://lite.duckduckgo.com/lite/", "https://html.duckduckgo.com/html/"):
        try:
            page = _get(f"{base}?q={q}&kl=wt-wt")
        except Exception:
            continue
        results = []
        for m in re.finditer(r'<a[^>]*(?:class="result__a"|class="result-link")[^>]*'
                             r'href="([^"]+)"[^>]*>(.*?)</a>', page, re.S):
            url = html.unescape(m.group(1))
            mm = re.search(r"uddg=([^&]+)", url)
            if mm:
                url = urllib.parse.unquote(mm.group(1))
            title = re.sub(r"<[^>]+>", "", m.group(2)).strip()
            if url.startswith("http") and title:
                results.append({"title": html.unescape(title), "url": url, "snippet": ""})
            if len(results) >= limit:
                break
        if results:
            return results
    return []


def search(query: str, limit: int = 5) -> list[dict]:
    """نتایج جست‌وجو — ابتدا ویکی‌پدیا، بعد DuckDuckGo."""
    out: list[dict] = []
    w = wiki_summary(query)
    if w and w.get("url"):
        out.append({"title": w["title"], "url": w["url"], "snippet": w["extract"][:200]})
    try:
        out += _ddg_lite(query, limit)
    except Exception as exc:
        log.warning("جست‌وجوی DuckDuckGo ناموفق بود: %s", exc)
    # حذف تکراری‌ها
    seen, uniq = set(), []
    for r in out:
        if r["url"] not in seen:
            seen.add(r["url"])
            uniq.append(r)
    return uniq[:limit]


def _strip_html(page: str) -> str:
    try:
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(page, "html.parser")
        for tag in soup(["script", "style", "nav", "header", "footer", "aside", "form"]):
            tag.decompose()
        main = soup.find("article") or soup.find("main") or soup.body or soup
        text = main.get_text("\n", strip=True)
    except Exception:
        page = re.sub(r"(?is)<(script|style).*?</\1>", " ", page)
        text = re.sub(r"(?s)<[^>]+>", " ", page)
        text = html.unescape(text)
    text = re.sub(r"\n{3,}", "\n\n", re.sub(r"[ \t]+", " ", text))
    return text.strip()[:_MAX_CHARS]


def fetch(url: str) -> str:
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    try:
        return _strip_html(_get(url))
    except Exception as exc:
        log.warning("خواندن صفحه ناموفق بود: %s", exc)
        return ""


def answer(question: str) -> str:
    """پاسخِ یک سؤال: ویکی‌پدیا → (اگر کلید هست) خلاصه‌ی Claude از صفحه‌ها → فهرست نتایج."""
    from .. import claude_client

    wiki = wiki_summary(question)
    ddg = []
    try:
        ddg = _ddg_lite(question, 4)
    except Exception:
        pass

    if claude_client.available():
        context = ""
        if wiki:
            context += f"\n\n### ویکی‌پدیا: {wiki['title']}\n{wiki['extract']}"
        for h in ddg[:2]:
            body = fetch(h["url"])
            if body:
                context += f"\n\n### {h['title']}\n{h['url']}\n{body[:2000]}"
        if context:
            reply = claude_client.oneshot(
                "بر اساس متنِ زیر به سؤالِ کاربر کوتاه و دقیق به فارسی جواب بده. "
                "اگر جواب نبود، صادقانه بگو.",
                f"سؤال: {question}\n\nمنابع:{context}", max_tokens=500)
            if reply:
                return reply

    if wiki:
        first = wiki["extract"].split(". ")[0]
        return f"{first.strip('.')}. (ویکی‌پدیا: {wiki['title']})"
    if ddg:
        return "نتایج:\n" + "\n".join(f"• {h['title']} — {h['url']}" for h in ddg[:4])
    return "چیزی پیدا نکردم؛ ممکنه اتصالِ اینترنت مشکل داشته باشه."
