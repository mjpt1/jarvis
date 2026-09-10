"""رجیستریِ کدهای خطا — هر خطای شناخته‌شده یک کدِ پایدارِ `JRV-<DOMAIN>-<NNN>` دارد.

هدف: خطاها قابل‌ردیابی، قابل‌جست‌وجو و مستند باشند. `scripts/check_registry.py`
بررسی می‌کند که هر کدی که در سورس استفاده شده این‌جا ثبت شده باشد.
"""

from __future__ import annotations

# کد -> توضیحِ کوتاه
REGISTRY: dict[str, str] = {
    # AUDIO
    "JRV-AUDIO-001": "باز کردن میکروفون ناموفق بود",
    "JRV-AUDIO-002": "بارگذاری مدل صوتی Vosk ناموفق بود",
    "JRV-AUDIO-003": "دانلود مدل صوتی ناموفق بود",
    # VISION
    "JRV-VISION-001": "باز نشدن دوربین",
    "JRV-VISION-002": "دانلود مدل FaceLandmarker ناموفق بود",
    "JRV-VISION-003": "تشخیص اشیا (YOLO) در دسترس نیست",
    # MEMORY
    "JRV-MEM-001": "متنِ حقیقت خالی است",
    "JRV-MEM-002": "خواندن/نوشتن پایگاه‌داده‌ی حافظه ناموفق بود",
    # MISSION
    "JRV-MIS-001": "برنامه‌ریزیِ مأموریت ناموفق بود (بدون کلید Claude)",
    "JRV-MIS-002": "گامِ مأموریت شکست خورد",
    # INTEGRATION
    "JRV-INT-001": "کلید/کتابخانه‌ی ادغام تنظیم نشده",
    "JRV-INT-002": "تماس با سرویسِ خارجی ناموفق بود",
    "JRV-INT-003": "مسیر خارج از فهرستِ سفیدِ فایل‌سیستم",
    "JRV-INT-004": "دستور خارج از فهرستِ سفیدِ خط‌فرمان",
    # BUDGET
    "JRV-BUD-001": "بودجه‌ی روزانه‌ی Claude تمام شده",
    # CONFIG
    "JRV-CFG-001": "خواندن فایل پیکربندی ناموفق بود",
    # SKILL
    "JRV-SKL-001": "مهارت به ابزارِ ناشناخته ارجاع می‌دهد",
    "JRV-SKL-002": "مهارت پیدا نشد",
}


class JarvisError(Exception):
    def __init__(self, code: str, detail: str = ""):
        self.code = code
        self.detail = detail
        desc = REGISTRY.get(code, "کدِ نامعلوم")
        super().__init__(f"[{code}] {desc}" + (f" — {detail}" if detail else ""))


def describe(code: str) -> str:
    return REGISTRY.get(code, "کدِ نامعلوم")


def is_registered(code: str) -> bool:
    return code in REGISTRY
