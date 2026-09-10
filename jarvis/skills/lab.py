"""آزمایشگاهِ مهارت — اعتبارسنجی و اجرای آزمایشیِ امن پیش از فعال‌سازی."""

from __future__ import annotations

from ..logging_setup import get_logger

log = get_logger("skills")

# ابزارهایی که در «اجرای آزمایشی» بی‌خطرند (فقط می‌خوانند، چیزی را تغییر نمی‌دهند)
_READ_ONLY = {"say", "wait", "recall", "web_answer", "web_read", "fs_list",
              "fs_read", "gmail_unread", "calendar_upcoming", "notion_search",
              "describe_scene", "spotify_play"}


def validate(steps: list[dict], tool_registry) -> tuple[bool, str]:
    if not steps:
        return False, "مهارت هیچ گامی ندارد."
    for i, s in enumerate(steps):
        tool = s.get("tool")
        if tool not in tool_registry:
            return False, f"[JRV-SKL-001] گام {i + 1} به ابزارِ ناشناخته «{tool}» ارجاع می‌دهد."
    return True, "معتبر است."


def dry_run(steps: list[dict], tool_registry) -> tuple[bool, str]:
    """فقط گام‌های خواندنی را واقعاً اجرا می‌کند؛ بقیه را «شبیه‌سازی» می‌کند."""
    ok, msg = validate(steps, tool_registry)
    if not ok:
        return False, msg
    lines = []
    for i, s in enumerate(steps, 1):
        name = s["tool"]
        args = s.get("args", {})
        if name in _READ_ONLY:
            tool = tool_registry.get(name)
            try:
                res = tool.run(**args)
                lines.append(f"{i}. {name}: {getattr(res, 'output', '')[:80]}")
            except Exception as exc:
                lines.append(f"{i}. {name}: خطا — {exc}")
        else:
            flag = "  (⚠️حساس)" if tool_registry.get(name) and tool_registry.get(name).dangerous else ""
            lines.append(f"{i}. {name}{flag}: در اجرای واقعی انجام می‌شود")
    return True, "اجرای آزمایشی:\n" + "\n".join(lines)
