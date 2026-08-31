"""مسیرهای دائمی برنامه (نه در پوشه‌ی موقت که با ری‌استارت پاک می‌شود)."""

from __future__ import annotations

import os
from pathlib import Path

# ریشه‌ی داده‌های کاربر: ~/.jarvis
HOME = Path(os.path.expanduser("~"))
APP_DIR = Path(os.environ.get("JARVIS_HOME", HOME / ".jarvis"))

MODELS_DIR = APP_DIR / "models"
CACHE_DIR = APP_DIR / "cache"          # کش صداهای ثابت (بین اجراها می‌ماند)
LOG_DIR = APP_DIR / "logs"
SCREENSHOT_DIR = HOME / "Pictures" / "JarvisScreenshots"

# ریشه‌ی سورس (برای دسترسی به assets)
PACKAGE_DIR = Path(__file__).resolve().parent
ASSETS_DIR = PACKAGE_DIR / "assets"
FONTS_DIR = ASSETS_DIR / "fonts"

CONFIG_FILE = APP_DIR / "config.json"
# اگر کاربر config.json کنار سورس گذاشت هم قبول می‌کنیم
LOCAL_CONFIG_FILE = PACKAGE_DIR.parent / "config.json"


def ensure_dirs() -> None:
    for d in (APP_DIR, MODELS_DIR, CACHE_DIR, LOG_DIR):
        d.mkdir(parents=True, exist_ok=True)
