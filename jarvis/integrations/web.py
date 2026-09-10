"""جست‌وجو و خواندنِ صفحه‌ی وب — بدون کلید.

- search(query): چند نتیجه از DuckDuckGo HTML (بدون API).
- fetch(url): متنِ اصلیِ صفحه را برمی‌گرداند (BeautifulSoup اگر نصب باشد، وگرنه regex ساده).
- summarize(url|query): با Claude خلاصه می‌کند (اگر کلید باشد).
"""

from __future__ import annotations

import html
import re
import urllib.parse
import urllib.request

from ..logging_setup import get_logger

log = get_logger("web")

_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")
_MAX_CHARS = 4000


def configure(max_chars: int) -> None:
    global _MAX_CHARS
    _MAX_CHARS = max_chars


def available() -> bool:
    return True


def _get(url: str, timeout: int = 12) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": _UA,
                                               "Accept-Language": "fa,en;q=0.8"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        raw = r.read()
    for enc in ("utf-8", "cp1256", "latin-1"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", "ignore")


def search(query: str, limit: int = 5) -> list[dict]:
    """[{title, url, snippet}] از DuckDuckGo HTML."""
    q = urllib.parse.quote(query)
    try:
        page = _get(f"https://html.duckduckgo.com/html/?q={q}&kl=wt-wt")
    except Exception as exc:
        log.warning("جست‌وجوی وب ناموفق بود: %s", exc)
        return []
    results = []
    for m in re.finditer(
        r'<a[^>]*class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>', page, re.S):
        url = html.unescape(m.group(1))
        # DuckDuckGo لینک‌ها را از طریق ریدایرکت می‌دهد
        mm = re.search(r"uddg=([^&]+)", url)
        if mm:
            url = urllib.parse.unquote(mm.group(1))
        title = re.sub(r"<[^>]+>", "", m.group(2)).strip()
        results.append({"title": html.unescape(title), "url": url, "snippet": ""})
        if len(results) >= limit:
            break
    return results


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
    """یک سؤال را با جست‌وجو + خواندنِ صفحه‌ی اول + خلاصه‌ی Claude پاسخ می‌دهد."""
    from .. import claude_client
    hits = search(question, limit=4)
    if not hits:
        return "چیزی در وب پیدا نکردم."
    context = ""
    for h in hits[:2]:
        body = fetch(h["url"])
        if body:
            context += f"\n\n### {h['title']}\n{h['url']}\n{body[:2500]}"
    if not context:
        return "صفحه‌ها باز شدند ولی متنی برای خواندن نبود:\n" + \
               "\n".join(f"- {h['title']}: {h['url']}" for h in hits)
    if not claude_client.available():
        return "نتایج:\n" + "\n".join(f"- {h['title']}: {h['url']}" for h in hits)
    reply = claude_client.oneshot(
        "بر اساس متنِ صفحه‌های وبِ زیر، به سؤالِ کاربر کوتاه و دقیق به فارسی جواب بده. "
        "اگر جواب در متن نبود، صادقانه بگو.",
        f"سؤال: {question}\n\nمتنِ صفحه‌ها:{context}", max_tokens=500)
    return reply or "نتوانستم جمع‌بندی کنم."
