"""ابزارهای پردازش متن فارسی: نرمال‌سازی، تطبیق فازی، و تجزیه‌ی اعداد/زمان.

خروجی Vosk اغلب بدون نیم‌فاصله، با «ي/ك» عربی یا املای متفاوت است؛ این ماژول
همه را یک‌دست می‌کند تا تطبیق دستورها شکننده نباشد.
"""

from __future__ import annotations

import difflib
import re

# --- جدول تبدیل کاراکتر ---
_CHAR_MAP = {
    "ي": "ی", "ك": "ک", "ﻻ": "لا", "ۀ": "ه", "ة": "ه", "أ": "ا", "إ": "ا",
    "آ": "ا", "ؤ": "و", "ئ": "ی", "‌": " ", "‏": "", "‎": "",
    "ـ": "",
}
_DIGIT_MAP = {ord(a): ord(b) for a, b in zip("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩",
                                             "01234567890123456789")}

_TRANS = str.maketrans({**{ord(k): v for k, v in _CHAR_MAP.items()}, **_DIGIT_MAP})

# کلماتی که برای تطبیق بی‌اهمیت‌اند
_STOP = {"رو", "را", "به", "یه", "یک", "لطفا", "لطفاً", "کن", "بکن", "میشه",
         "می‌شه", "برام", "برایم", "الان", "خب", "دیگه"}


def normalize(text: str) -> str:
    """یک‌دست‌سازی: کاراکترها، ارقام، فاصله‌ها، حروف تکراری کشیده."""
    if not text:
        return ""
    text = text.translate(_TRANS)
    text = re.sub(r"(.)\1{2,}", r"\1\1", text)      # سلاااام -> سلاام
    text = re.sub(r"\s+", " ", text)
    return text.strip().lower()


def tokens(text: str) -> list[str]:
    return [w for w in normalize(text).split() if w]


def content_tokens(text: str) -> list[str]:
    return [w for w in tokens(text) if w not in _STOP]


def similarity(a: str, b: str) -> float:
    return difflib.SequenceMatcher(None, normalize(a), normalize(b)).ratio()


def contains_normalized(haystack: str, needle: str) -> bool:
    return normalize(needle) in normalize(haystack)


def fuzzy_contains(haystack: str, needle: str, threshold: float = 0.82) -> bool:
    """آیا عبارت needle (تقریباً) داخل haystack هست؟

    ابتدا زیررشته‌ی دقیقِ نرمال‌شده، بعد پنجره‌ی لغزان روی توکن‌ها با نسبت شباهت.
    """
    h_norm = normalize(haystack)
    n_norm = normalize(needle)
    if not n_norm:
        return False
    if n_norm in h_norm:
        return True

    h_tokens = h_norm.split()
    n_tokens = n_norm.split()
    if not h_tokens:
        return False
    span = len(n_tokens)
    windows = [" ".join(h_tokens[i:i + span]) for i in range(max(1, len(h_tokens) - span + 1))]
    windows.append(h_norm)
    return any(difflib.SequenceMatcher(None, w, n_norm).ratio() >= threshold for w in windows)


def strip_phrase(text: str, phrase: str) -> str:
    """حذف نخستین وقوعِ (تقریبیِ) phrase و برگرداندن باقی‌مانده."""
    norm = normalize(text)
    p = normalize(phrase)
    idx = norm.find(p)
    if idx != -1:
        return (norm[:idx] + " " + norm[idx + len(p):]).strip()
    return norm


# ============================================================
# اعداد فارسی — شامل اعداد ترکیبی («بیست و پنج»، «صد و ده»)
# ============================================================

_UNITS = {
    "صفر": 0, "یک": 1, "دو": 2, "سه": 3, "چهار": 4, "پنج": 5, "شش": 6, "شیش": 6,
    "هفت": 7, "هشت": 8, "نه": 9, "ده": 10, "یازده": 11, "دوازده": 12, "سیزده": 13,
    "چهارده": 14, "پانزده": 15, "پونزده": 15, "شانزده": 16, "شونزده": 16,
    "هفده": 17, "هیفده": 17, "هجده": 18, "هیجده": 18, "نوزده": 19,
}
_TENS = {"بیست": 20, "سی": 30, "چهل": 40, "پنجاه": 50, "شصت": 60, "هفتاد": 70,
         "هشتاد": 80, "نود": 90}
_HUNDREDS = {"صد": 100, "یکصد": 100, "دویست": 200, "سیصد": 300, "چهارصد": 400,
             "پانصد": 500, "ششصد": 600, "هفتصد": 700, "هشتصد": 800, "نهصد": 900}
_SCALES = {"هزار": 1000, "میلیون": 1_000_000}
_HALF = 0.5


def words_to_number(text: str):
    """رشته‌ی فارسیِ عدد را به int/float تبدیل می‌کند یا None."""
    text = normalize(text)
    m = re.search(r"\d+(?:[.,]\d+)?", text)
    if m:
        raw = m.group(0).replace(",", ".")
        return float(raw) if "." in raw else int(raw)

    words = [w for w in text.split() if w != "و"]
    if not words:
        return None

    total = 0
    current = 0
    matched = False
    for w in words:
        if w in _UNITS:
            current += _UNITS[w]
            matched = True
        elif w in _TENS:
            current += _TENS[w]
            matched = True
        elif w in _HUNDREDS:
            current += _HUNDREDS[w]
            matched = True
        elif w in _SCALES:
            current = max(1, current) * _SCALES[w]
            total += current
            current = 0
            matched = True
        elif w in ("نیم", "نیمه"):
            current += _HALF
            matched = True
        else:
            continue
    if not matched:
        return None
    result = total + current
    return int(result) if float(result).is_integer() else result


# ============================================================
# تجزیه‌ی مدت زمان -> ثانیه
# ============================================================

_UNIT_SECONDS = {
    "ثانیه": 1, "ثانیه‌ای": 1,
    "دقیقه": 60, "دقیقه‌ای": 60, "دیقه": 60,
    "ساعت": 3600, "ساعته": 3600,
}


def parse_duration_seconds(text: str):
    """«۱۰ دقیقه»، «یک ساعت و نیم»، «۹۰ ثانیه» -> ثانیه (int) یا None."""
    norm = normalize(text)
    total = 0.0
    found = False
    # الگو: <عدد یا کلمات> <واحد>
    unit_pat = "|".join(map(re.escape, _UNIT_SECONDS))
    for match in re.finditer(rf"([\w ]+?)\s*({unit_pat})", norm):
        qty_text = match.group(1).strip()
        # اجازه‌ی «یک ساعت و نیم» — عبارت قبل از واحد را کامل تجزیه کن
        qty = words_to_number(qty_text)
        if qty is None:
            # شاید فقط «نیم ساعت»
            if qty_text.split()[-1:] == ["نیم"] or qty_text.endswith("نیم"):
                qty = 0.5
            else:
                qty = 1
        total += float(qty) * _UNIT_SECONDS[match.group(2)]
        found = True

    if not found:
        return None
    # «و نیم» انتهایی بدون واحد صریح، به آخرین واحد نسبت داده شد؛ کافی است.
    return int(round(total))


def extract_reminder_message(text: str) -> str:
    norm = normalize(text)
    for kw in ("یادم بنداز", "یاد اوری کن", "یادآوری کن", "یادم بیار"):
        if kw in norm:
            return norm.split(kw, 1)[1].strip(" که،.")
    return ""
