#!/usr/bin/env python
"""بررسی: هر کدِ خطای `JRV-...` که در سورس ظاهر شده در errors.REGISTRY ثبت شده باشد."""

from __future__ import annotations

import re
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from jarvis.errors import REGISTRY  # noqa: E402

PATTERN = re.compile(r"JRV-[A-Z]+-\d{3}")


def main() -> int:
    used: set[str] = set()
    for py in (ROOT / "jarvis").rglob("*.py"):
        if py.name == "errors.py":
            continue
        used |= set(PATTERN.findall(py.read_text(encoding="utf-8")))

    missing = sorted(used - set(REGISTRY))
    if missing:
        print("کدهای خطای استفاده‌شده ولی ثبت‌نشده:")
        for m in missing:
            print(f"  - {m}")
        return 1
    print(f"OK — {len(REGISTRY)} کدِ ثبت‌شده، {len(used)} کدِ استفاده‌شده، همه معتبر.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
