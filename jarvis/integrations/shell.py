"""اجرای دستورِ خط‌فرمان با فهرستِ سفید — فقط دستورهای مجاز، بدون shell=True."""

from __future__ import annotations

import shlex
import subprocess

from ..logging_setup import get_logger

log = get_logger("shell")

_ENABLED = False
_WHITELIST: set[str] = set()


def configure(enabled: bool, whitelist: list[str]) -> None:
    global _ENABLED, _WHITELIST
    _ENABLED = enabled
    _WHITELIST = {w.lower() for w in whitelist}


def available() -> bool:
    return _ENABLED


def run(command: str, timeout: int = 20) -> str:
    if not _ENABLED:
        return "اجرای دستورِ خط‌فرمان غیرفعال است (cli_enabled=false)."
    try:
        parts = shlex.split(command, posix=False)
    except ValueError:
        return "دستور نامعتبر."
    if not parts:
        return "دستوری داده نشد."
    prog = parts[0].lower().removesuffix(".exe")
    if prog not in _WHITELIST:
        return (f"[JRV-INT-004] دستور «{prog}» در فهرستِ مجاز نیست. "
                f"مجازها: {', '.join(sorted(_WHITELIST))}")
    try:
        proc = subprocess.run(parts, capture_output=True, text=True,
                              timeout=timeout, shell=False)
        out = (proc.stdout or "") + (proc.stderr or "")
        log.info("CLI: %s (rc=%d)", command, proc.returncode)
        return out.strip()[:4000] or f"(بدون خروجی، کد {proc.returncode})"
    except subprocess.TimeoutExpired:
        return "دستور بیش از حد طول کشید و متوقف شد."
    except Exception as exc:
        return f"خطا در اجرا: {exc}"
