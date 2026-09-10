"""پیکربندی برنامه — از config.json و متغیرهای محیطی خوانده می‌شود.

هیچ مقداری داخل سورس هارد‌کد نمی‌شود؛ کاربر فقط config.json را ویرایش می‌کند.
برای ساختن فایل نمونه:  python -m jarvis --init-config
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field, fields
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
    author: str = "محسن جباره اصل"                   # برنامه‌نویس — روی HUD نمایش داده می‌شود
    website_url: str = "https://example.com"
    music_dir: str = os.path.join(os.path.expanduser("~"), "Music")
    news_rss_url: str = "https://feeds.bbci.co.uk/persian/rss.xml"

    # --- نمایش ---
    fullscreen: bool = True
    fps: int = 60
    show_debug_on_start: bool = False
    windowed_size: tuple[int, int] = (1100, 760)
    orb_points: int = 2400                          # تعداد نقاطِ کره‌ی ذره‌ای
    orb_bands: int = 48                             # تعداد باندهای اکولایزر
    hud_style: str = "minimal"                      # minimal | command | legacy

    # --- مکان دوم (مونکتون، نیوبرانزویک، کانادا) ---
    secondary_city: str = "مونکتون"
    secondary_lat: float = 46.0878
    secondary_lon: float = -64.7782
    secondary_tz: str = "America/Moncton"

    # --- دوربین ---
    camera_index: int = 0
    enable_camera: bool = True

    # --- صدا / تشخیص گفتار ---
    enable_voice: bool = True
    vosk_model_name: str = "vosk-model-small-fa-0.42"
    sample_rate: int = 16000
    wake_words: list[str] = field(default_factory=lambda: [
        "جارویس", "جارویز", "جاروی", "جاروس", "جارویش", "جاریس", "جادو",
        "جار", "چاره", "جاده", "شارژ", "جهاز",
    ])
    # واژه‌هایی که یک «شناسگرِ محدود» فقط دنبالشان می‌گردد تا صدا زدن قابل‌اعتماد شود.
    # مدل کوچک فارسیِ Vosk اسم «جارویس» را نمی‌شناسد؛ این لیست هرچه شنید را به
    # نزدیک‌ترین گزینه می‌چسباند. اگر واکنش نداد، اینجا هرچه واقعاً می‌شنود اضافه کن.
    wake_grammar_words: list[str] = field(default_factory=lambda: [
        "جارویس", "جارویز", "جاروس", "جادو", "جار", "چاره", "جاده", "شارژ",
    ])
    wake_fuzzy: float = 0.62               # آستانه‌ی نرم برای تطبیقِ کلمه‌ی بیدارباش
    wake_min_level: float = 0.16           # حداقل بلندیِ صدا برای پذیرشِ بیدارباش (فیلترِ تلویزیون/نویز)
    fuzzy_threshold: float = 0.78          # آستانه‌ی تطبیق فازی دستورها

    # حالت مکالمه‌ی پیوسته: یک بار «جارویس» بگو، بعد همیشه منتظر دستور بماند
    conversation_mode: bool = True
    conversation_idle_timeout: float = 0.0   # ثانیه سکوت تا خواب خودکار؛ 0 = هرگز
    nag_on_unknown: bool = False              # در حالت مکالمه، جمله‌ی نامفهوم را نادیده بگیر
    # عبارت‌های خروج از حالت مکالمه. چون مدلِ کوچک واژه‌های کوتاه را بد می‌شنود،
    # گونه‌های محتملِ اشتباه‌شنیده‌شده هم اضافه شده‌اند.
    sleep_phrases: list[str] = field(default_factory=lambda: [
        "بسه", "بس", "بسته", "دیگه بسه", "کافیه", "کافی",
        "تمام", "تمومه", "تموم", "تمامه", "دیگه تمومه",
        "دیگه گوش نده", "دیگه گوش نکن", "گوش نکن", "استراحت کن",
        "بخواب", "بگیر بخواب", "فعلا کاری ندارم", "مرخصی",
        "ساکت", "خاموش شو", "کنسل", "ولش کن",
    ])
    # اگر یکی از این توکن‌ها دقیقاً شنیده شود، بی‌درنگ از حالت مکالمه خارج می‌شود.
    sleep_exact_tokens: list[str] = field(default_factory=lambda: [
        "بسه", "بسته", "تمومه", "کافیه", "ساکت", "کنسل",
    ])

    # --- بازه‌ها ---
    weather_update_interval: int = 600
    system_stats_interval: float = 2.0
    confirm_timeout: float = 8.0
    command_timeout: float = 6.0

    # --- حافظه‌ی بلندمدت ---
    memory_enabled: bool = True
    memory_recall_limit: int = 6           # تعداد حقایقی که به Claude تزریق می‌شود
    nightly_consolidation_hour: int = 4    # ساعتِ استخراجِ شبانه‌ی حقایق (۰=خاموش)

    # --- موتور مأموریت (اجرای چندمرحله‌ای) ---
    mission_enabled: bool = True
    mission_max_steps: int = 8
    mission_autoconfirm: bool = False      # اجرای گام‌های حساس بدون تایید صوتی

    # --- ابزارها (فاز ۲) ---
    web_enabled: bool = True               # جست‌وجو و خواندنِ صفحه‌ی وب (بدون کلید)
    web_max_chars: int = 4000              # سقفِ متنِ استخراج‌شده از یک صفحه
    web_proxy: str = ""                    # پروکسیِ اختیاری برای جست‌وجوی وب (معمولاً لازم نیست)

    fs_enabled: bool = True
    fs_whitelist: list[str] = field(default_factory=list)   # مسیرهای مجاز؛ خالی = فقط ~/JarvisFiles
    fs_allow_write: bool = True

    cli_enabled: bool = False              # پیش‌فرض خاموش (پرخطر)
    cli_whitelist: list[str] = field(default_factory=lambda: [
        "echo", "dir", "ls", "type", "cat", "whoami", "hostname", "date", "ver",
        "ipconfig", "systeminfo", "git", "python", "pip",
    ])

    # --- بینایی پیشرفته (فاز ۳) ---
    vision_enabled: bool = True
    vision_source: str = "screen"         # screen | camera
    yolo_model: str = "yolov8n.pt"        # خودکار دانلود می‌شود (نیاز به ultralytics)
    vision_min_confidence: float = 0.4
    face_id_enabled: bool = True          # بیدارباشِ بیومتریک (نیاز به face_recognition + عکس مرجع)
    face_id_tolerance: float = 0.5

    # --- ادغام‌های خارجی (نیاز به کلید؛ تا تنظیم نشوند خاموش‌اند) ---
    google_enabled: bool = True            # Gmail + Calendar؛ به credentials نیاز دارد
    spotify_enabled: bool = True
    spotify_client_id: str = ""
    spotify_client_secret: str = ""
    spotify_redirect_uri: str = "http://localhost:8888/callback"
    notion_enabled: bool = True
    notion_token: str = ""
    telegram_enabled: bool = True
    telegram_bot_token: str = ""
    telegram_owner_id: int = 0             # فقط این کاربر می‌تواند با بات حرف بزند
    telegram_proxy: str = ""               # اگر api.telegram.org فیلتر است:
                                           #   "http://127.0.0.1:PORT" یا "socks5://127.0.0.1:PORT"

    # --- داشبورد وب (فاز ۴) ---
    web_dashboard_enabled: bool = True
    web_dashboard_host: str = "127.0.0.1"
    web_dashboard_port: int = 8730

    # --- سیستمِ پیش‌کنشی و حاکمیت (فاز ۵) ---
    proactive_enabled: bool = True
    autonomy_level: int = 1            # 0 خاموش · 1 فقط اعلان · 2 +ابزارِ خواندنی
                                       # 3 +مأموریتِ پیشنهادی با تایید · 4 +بدون تایید · 5 کامل
    quiet_hours: list[int] = field(default_factory=lambda: [23, 8])  # [شروع, پایان]
    news_interests: list[str] = field(default_factory=list)          # کلیدواژه‌های خبری
    collector_weather_interval: int = 1800
    collector_calendar_interval: int = 600
    collector_mail_interval: int = 900
    collector_news_interval: int = 3600
    calendar_alert_minutes: int = 30

    # بودجه‌ی روزانه (۰ = بی‌نهایت)
    budget_daily_usd: float = 1.0
    budget_daily_calls: int = 300

    # --- Claude (اختیاری) ---
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-haiku-4-5-20251001"
    chat_history_max_turns: int = 6
    claude_can_run_actions: bool = True    # اجازه‌ی اجرای دستور از طریق tool-use

    # --- پوشه‌های قابل باز شدن با صدا (نام فارسی -> مسیر) ---
    folder_aliases: dict[str, str] = field(default_factory=dict)

    # ------------------------------------------------------------------
    @classmethod
    def load(cls) -> Config:
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

        # متغیرهای محیطی همیشه اولویت دارند
        env_map = {
            "ANTHROPIC_API_KEY": "anthropic_api_key",
            "SPOTIFY_CLIENT_ID": "spotify_client_id",
            "SPOTIFY_CLIENT_SECRET": "spotify_client_secret",
            "NOTION_TOKEN": "notion_token",
            "TELEGRAM_BOT_TOKEN": "telegram_bot_token",
        }
        for env_name, attr in env_map.items():
            val = os.environ.get(env_name)
            if val:
                setattr(cfg, attr, val)
        owner = os.environ.get("TELEGRAM_OWNER_ID")
        if owner and owner.isdigit():
            cfg.telegram_owner_id = int(owner)

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
