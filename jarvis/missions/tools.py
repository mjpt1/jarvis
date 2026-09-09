"""رجیستریِ ابزارهایی که موتور مأموریت می‌تواند صدا بزند.

در فاز ۱ ابزارها همان اقدام‌های موجودِ جارویس‌اند به‌علاوه چند ابزارِ داخلی
(صحبت، مکث، یادسپاری، جست‌وجوی حافظه). فازهای بعدی ابزارهای وب/جیمیل/... را
همین‌جا اضافه می‌کنند.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Callable

from ..logging_setup import get_logger

log = get_logger("missions")


@dataclass
class ToolResult:
    ok: bool
    output: str = ""

    def __bool__(self) -> bool:
        return self.ok


@dataclass
class Tool:
    name: str
    description: str
    run: Callable[..., ToolResult]
    params: dict[str, str] = field(default_factory=dict)   # نام -> توضیح
    dangerous: bool = False


class ToolRegistry:
    def __init__(self):
        self._tools: dict[str, Tool] = {}

    def add(self, tool: Tool) -> None:
        self._tools[tool.name] = tool

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def __contains__(self, name: str) -> bool:
        return name in self._tools

    def names(self) -> list[str]:
        return list(self._tools)

    def catalog(self) -> str:
        rows = []
        for t in self._tools.values():
            p = ", ".join(f"{k}: {v}" for k, v in t.params.items()) or "بدون پارامتر"
            flag = "  ⚠️حساس" if t.dangerous else ""
            rows.append(f"- {t.name}({p}) — {t.description}{flag}")
        return "\n".join(rows)


def build_default_registry(engine) -> ToolRegistry:
    """engine = CommandEngine — برای دسترسی به اقدام‌های موجود و TTS."""
    from .. import tts, system_actions
    reg = ToolRegistry()

    def _say(text: str = "") -> ToolResult:
        tts.say(text, blocking=True)
        return ToolResult(True, "گفته شد")

    def _wait(seconds: str = "1") -> ToolResult:
        try:
            time.sleep(min(30.0, float(seconds)))
        except ValueError:
            time.sleep(1)
        return ToolResult(True, "مکث انجام شد")

    def _remember(text: str = "") -> ToolResult:
        from ..memory.curator import remember
        if not text.strip():
            return ToolResult(False, "متنی برای یادسپاری نبود")
        remember(text, source="mission")
        return ToolResult(True, "به حافظه اضافه شد")

    def _recall(query: str = "") -> ToolResult:
        from ..memory.store import get_store
        hits = get_store().search(query, limit=5)
        return ToolResult(True, "؛ ".join(f.text for f in hits) or "چیزی یافت نشد")

    def _web_search(query: str = "") -> ToolResult:
        system_actions.google_search(query, engine.title)
        return ToolResult(True, f"جست‌وجوی «{query}» در مرورگر باز شد")

    def _open_url(url: str = "") -> ToolResult:
        import webbrowser
        if not url:
            return ToolResult(False, "آدرسی داده نشد")
        webbrowser.open(url)
        return ToolResult(True, f"{url} باز شد")

    def _open_app(name: str = "") -> ToolResult:
        cmd = engine.match(f"{name} رو باز کن")
        if cmd:
            cmd.handler()
            return ToolResult(True, f"{name} باز شد")
        return ToolResult(False, f"برنامه‌ی «{name}» را نمی‌شناسم")

    def _run_command(phrase: str = "") -> ToolResult:
        """اجرای هر دستور صوتیِ موجودِ جارویس با یک عبارت."""
        cmd = engine.match(phrase)
        if not cmd:
            return ToolResult(False, f"دستوری برای «{phrase}» پیدا نشد")
        cmd.handler(phrase) if cmd.wants_text else cmd.handler()
        return ToolResult(True, f"دستور «{cmd.name}» اجرا شد")

    for t in [
        Tool("say", "گفتن یک جمله با صدای جارویس", _say, {"text": "متن"}),
        Tool("wait", "مکث چند ثانیه‌ای", _wait, {"seconds": "ثانیه"}),
        Tool("remember", "افزودن یک نکته به حافظه‌ی بلندمدت", _remember, {"text": "متن"}),
        Tool("recall", "جست‌وجو در حافظه", _recall, {"query": "موضوع"}),
        Tool("web_search", "جست‌وجوی وب در مرورگر", _web_search, {"query": "عبارت"}),
        Tool("open_url", "باز کردن یک آدرس در مرورگر", _open_url, {"url": "نشانی"}),
        Tool("open_app", "باز کردن یک برنامه/پوشه", _open_app, {"name": "نام فارسی"}),
        Tool("run_command", "اجرای هر دستور صوتیِ دیگرِ جارویس", _run_command,
             {"phrase": "عبارتِ دستور"}),
    ]:
        reg.add(t)
    return reg
