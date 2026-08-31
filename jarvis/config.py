"""پیکربندی برنامه — از config.json و متغیرهای محیطی خوانده می‌شود.

هیچ مقداری داخل سورس هارد‌کد نمی‌شود؛ کاربر فقط config.json را ویرایش می‌کند.
برای ساختن فایل نمونه:  python -m jarvis --init-config
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, asdict, field, fields
from typing import Any

from .paths import CONFIG_FILE, LOCAL_CONFIG_FILE

# .env اختیاری
try:  # pragma: no cover - وابسته به محیط
    from dotenv import load_dotenv

    load_dotenv()
except Exception:  # pragma: no cover
    pass


@dataclass
class Config:
    # --- عمومی ---
    voice: str = "fa-IR-FaridNeural"
    user_title: str = "قربان"                       # نحوه‌ی خطاب کاربر
    website_url: str = "https://example.com"
    music_dir: str = os.path.join(os.path.expanduser("~"), "Music")
    news_rss_url: str = "https://feeds.bbci.co.uk/persian/rss.xml"

    # --- نمایش ---
    fullscreen: bool = True
    fps: int = 60
    show_debug_on_start: bool = False
    windowed_size: tuple[int, int] = (1100, 760)

    # --- دوربین ---
    camera_index: int = 0
    enable_camera: bool = True

    # --- صدا / تشخیص گفتار ---
    enable_voice: bool = True
    vosk_model_name: str = "vosk-model-small-fa-0.42"
    sample_rate: int = 16000
    wake_words: list[str] = field(default_factory=lambda: [
        "جارویس", "جارویز", "جاروی", "جاروس", "جارویش", "جاریس",
    ])
    fuzzy_threshold: float = 0.78          # آستانه‌ی تطبیق فازی دستورها

    # --- بازه‌ها ---
    weather_update_interval: int = 600
    system_stats_interval: float = 2.0
    confirm_timeout: float = 8.0
    command_timeout: float = 6.0

    # --- Claude (اختیاری) ---
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-haiku-4-5-20251001"
    chat_history_max_turns: int = 6
    claude_can_run_actions: bool = True    # اجازه‌ی اجرای دستور از طریق tool-use

    # --- پوشه‌های قابل باز شدن با صدا (نام فارسی -> مسیر) ---
    folder_aliases: dict[str, str] = field(default_factory=dict)

    # ------------------------------------------------------------------
    @classmethod
    def load(cls) -> "Config":
        data: dict[str, Any] = {}
        for path in (CONFIG_FILE, LOCAL_CONFIG_FILE):
            if path.is_file():
                try:
                    data = json.loads(path.read_text(encoding="utf-8"))
                    break
                except Exception as exc:  # pragma: no cover
                    print(f"[هشدار] خواندن {path} ناموفق بود: {exc}")

        known = {f.name for f in fields(cls)}
        clean = {k: v for k, v in data.items() if k in known}
        if "windowed_size" in clean and isinstance(clean["windowed_size"], list):
            clean["windowed_size"] = tuple(clean["windowed_size"])
        cfg = cls(**clean)

        # متغیر محیطی همیشه اولویت دارد
        env_key = os.environ.get("ANTHROPIC_API_KEY")
        if env_key:
            cfg.anthropic_api_key = env_key

        if not cfg.folder_aliases:
            cfg.folder_aliases = cfg._default_folder_aliases()
        return cfg

    @staticmethod
    def _default_folder_aliases() -> dict[str, str]:
        home = os.path.expanduser("~")
        aliases = {
            "دسکتاپ": os.path.join(home, "Desktop"),
            "دانلود": os.path.join(home, "Downloads"),
            "دانلودها": os.path.join(home, "Downloads"),
            "اسناد": os.path.join(home, "Documents"),
            "تصاویر": os.path.join(home, "Pictures"),
            "موزیک": os.path.join(home, "Music"),
        }
        if os.name == "nt":
            for letter in ("C", "D", "E"):
                if os.path.isdir(f"{letter}:\\"):
                    aliases[f"درایو {letter.lower()}"] = f"{letter}:\\"
        return aliases

    def write_example(self, path=None) -> str:
        path = path or LOCAL_CONFIG_FILE
        payload = asdict(self)
        payload["windowed_size"] = list(self.windowed_size)
        payload["anthropic_api_key"] = ""
        payload["folder_aliases"] = self._default_folder_aliases()
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, ensure_ascii=False, indent=2)
        return str(path)
