"""عملیاتِ فایل با فهرستِ سفیدِ مسیرها — هیچ کاری بیرون از مسیرهای مجاز مجاز نیست."""

from __future__ import annotations

import os
from pathlib import Path

from ..logging_setup import get_logger
from ..paths import FILES_DIR

log = get_logger("fs")

_ROOTS: list[Path] = []
_ALLOW_WRITE = True
_MAX_READ = 20_000


def configure(whitelist: list[str], allow_write: bool = True) -> None:
    global _ROOTS, _ALLOW_WRITE
    roots = [FILES_DIR]
    for p in whitelist or []:
        try:
            roots.append(Path(os.path.expanduser(p)).resolve())
        except Exception:
            pass
    _ROOTS = roots
    _ALLOW_WRITE = allow_write
    FILES_DIR.mkdir(parents=True, exist_ok=True)


def available() -> bool:
    return True


def _resolve(path: str) -> Path | None:
    try:
        p = Path(os.path.expanduser(path))
        if not p.is_absolute():
            p = FILES_DIR / p
        p = p.resolve()
    except Exception:
        return None
    for root in _ROOTS:
        try:
            p.relative_to(root)
            return p
        except ValueError:
            continue
    return None


def roots_text() -> str:
    return "، ".join(str(r) for r in _ROOTS)


def list_dir(path: str = ".") -> str:
    p = _resolve(path)
    if p is None:
        return f"مسیر مجاز نیست. فقط این‌ها مجازند: {roots_text()}"
    if not p.is_dir():
        return "این یک پوشه نیست."
    items = sorted(p.iterdir(), key=lambda x: (x.is_file(), x.name.lower()))
    out = []
    for it in items[:200]:
        tag = "📁" if it.is_dir() else "📄"
        size = f" ({it.stat().st_size} B)" if it.is_file() else ""
        out.append(f"{tag} {it.name}{size}")
    return "\n".join(out) or "(خالی)"


def read_file(path: str) -> str:
    p = _resolve(path)
    if p is None:
        return f"مسیر مجاز نیست. مجاز: {roots_text()}"
    if not p.is_file():
        return "فایل پیدا نشد."
    try:
        return p.read_text(encoding="utf-8", errors="replace")[:_MAX_READ]
    except Exception as exc:
        return f"خطا در خواندن: {exc}"


def write_file(path: str, content: str) -> str:
    if not _ALLOW_WRITE:
        return "نوشتن در فایل غیرفعال است (fs_allow_write=false)."
    p = _resolve(path)
    if p is None:
        return f"مسیر مجاز نیست. مجاز: {roots_text()}"
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        log.info("فایل نوشته شد: %s (%d بایت)", p, len(content))
        return f"ذخیره شد: {p}"
    except Exception as exc:
        return f"خطا در نوشتن: {exc}"
