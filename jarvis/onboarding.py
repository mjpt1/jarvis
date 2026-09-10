"""آشناییِ اولیه — بارِ اول که جارویس روی یک سیستم اجرا می‌شود، چند سؤال می‌پرسد،
هر پاسخ را تکرار و تأیید می‌گیرد، و یاد می‌گیرد اربابش کیست.

نتیجه در `~/.jarvis/owner.json` و در حافظه‌ی بلندمدت ذخیره می‌شود.
"""

from __future__ import annotations

import json

from .logging_setup import get_logger
from .paths import APP_DIR, ensure_dirs
from .state import STATE
from .text_fa import normalize

log = get_logger("onboarding")

OWNER_FILE = APP_DIR / "owner.json"

# (کلید, پرسش, دسته‌ی حافظه)
_QUESTIONS = [
    ("name", "سلام. من جارویسم، دستیارِ شخصیِ شما. اسمِ کوچیکتون چیه؟", "identity"),
    ("title", "از این به بعد چطور صداتون کنم؟ «قربان»، «رئیس»، یا اسمِ خودتون؟", "preference"),
    ("location", "کجا زندگی می‌کنید؟ فقط اسمِ شهر کافیه.", "identity"),
    ("focus", "بیشتر چه کارهایی ازم می‌خواید براتون انجام بدم؟", "preference"),
]

_YES = {"بله", "اره", "آره", "درسته", "همینه", "دقیقا", "بعله", "صحیح", "تایید", "اوهوم"}
_NO = {"نه", "نه‌خیر", "نخیر", "اشتباهه", "غلطه", "نبود", "دوباره", "عوضش کن"}
_SKIP = {"رد کن", "بعدا", "بعدا", "نمیخوام بگم", "بیخیال", "هیچی", "مهم نیست"}
_HONORIFICS = ["قربان", "رئیس", "ارباب", "استاد", "دکتر", "مهندس", "آقا", "خانم",
               "سرورم", "فرمانده", "کاپیتان", "جناب"]

_MIN_CONF = 0.55


def needs_onboarding() -> bool:
    return not OWNER_FILE.is_file()


def load_owner() -> dict:
    try:
        return json.loads(OWNER_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _clean_title(raw: str) -> str:
    n = normalize(raw)
    for h in _HONORIFICS:
        if normalize(h) in n:
            return h
    words = [w for w in n.split() if w not in
             {"من", "رو", "را", "به", "اسم", "اسمم", "کوچیکم", "صدا", "کن", "کنید",
              "بگو", "بگید", "می", "خوام", "خواهم", "همون", "فقط", "و", "نه", "با"}]
    if 1 <= len(words) <= 2:
        return " ".join(words)
    return ""


class Onboarding:
    def __init__(self, cfg):
        self.cfg = cfg
        self.i = 0
        self.phase = "ask"          # ask | confirm
        self.candidate = ""
        self.answers: dict[str, str] = {}
        self.retries = 0
        self.struggle = 0          # مجموعِ دفعاتِ نشنیدن/رد در کلِ نشست

    # ------------------------------------------------------------------
    def start(self) -> str:
        self.i = 0
        self.phase = "ask"
        self.candidate = ""
        self.retries = 0
        self.answers.clear()
        with STATE.lock:
            STATE.onboarding_active = True
        return self._ask()

    def _ask(self) -> str:
        self.phase = "ask"
        q = _QUESTIONS[self.i][1]
        with STATE.lock:
            STATE.onboarding_question = q
        return q

    def is_done(self) -> bool:
        return self.i >= len(_QUESTIONS)

    # ------------------------------------------------------------------
    def submit(self, answer: str, conf: float = 1.0) -> tuple[bool, str]:
        """(تمام‌شد؟, جمله‌ی بعدیِ جارویس)."""
        answer = (answer or "").strip()
        n = normalize(answer)
        key = _QUESTIONS[self.i][0]

        if n in _SKIP:
            self.i += 1
            self.retries = 0
            return self._after_advance()

        if self.phase == "confirm":
            if any(w in n for w in _YES):
                self.answers[key] = self.candidate
                self.i += 1
                self.retries = 0
                return self._after_advance()
            if any(w in n for w in _NO):
                self.struggle += 1
                if self.struggle >= 5:
                    return self._bail()
                self.retries += 1
                if self.retries >= 3:
                    self.i += 1
                    self.retries = 0
                    return self._after_advance("باشه، فعلاً ازش می‌گذریم. ")
                return False, "باشه، دوباره بگید. " + self._ask()
            # نه بله بود نه نه — همین را پاسخِ تازه بگیر
            answer, n = answer, n

        # phase == ask (یا پاسخِ تازه در confirm)
        if not answer or (conf < _MIN_CONF and len(answer.split()) <= 6):
            self.struggle += 1
            if self.struggle >= 5:
                return self._bail()
            self.retries += 1
            if self.retries >= 4:
                self.i += 1
                self.retries = 0
                return self._after_advance("مشکلی نیست، بعداً می‌پرسم. ")
            return False, "درست نشنیدم. " + _QUESTIONS[self.i][1]

        self.candidate = answer
        self.phase = "confirm"
        self.retries = 0
        with STATE.lock:
            STATE.onboarding_question = f"«{answer}» — درسته؟ بله یا نه"
        return False, f"شنیدم «{answer}». درسته {self._t()}؟ بله یا نه."

    def _t(self) -> str:
        return getattr(self.cfg, "user_title", "قربان")

    def _bail(self) -> tuple[bool, str]:
        """صدا هنوز خوب شنیده نمی‌شود؛ فعلاً بی‌خیالِ آشنایی می‌شویم."""
        self._finish()
        return True, (f"بذارید بعداً که مدلِ صوتیم بهتر شد این‌ها رو بپرسم {self._t()}. "
                      f"فعلاً «{self._t()}» صداتون می‌کنم؛ هر وقت خواستید بگید «تنظیمات اولیه».")

    def _after_advance(self, prefix: str = "") -> tuple[bool, str]:
        if self.is_done():
            self._finish()
            nm = self.answers.get("name", "")
            hi = f" {nm}" if nm else ""
            return True, (prefix + f"از آشنایی خوشحالم{hi}. همه‌چیز رو یادداشت کردم "
                          f"و از این به بعد در خدمتم. هر وقت کارم داشتید بگید «جارویس».")
        return False, (prefix + self._ask()).strip()

    # ------------------------------------------------------------------
    def _finish(self) -> None:
        ensure_dirs()
        raw_title = self.answers.get("title", "").strip()
        title = _clean_title(raw_title) or (self.answers.get("name", "").strip())
        if title:
            self.cfg.user_title = title
            self._persist_config("user_title", title)

        payload = dict(self.answers)
        payload["title_clean"] = title
        payload["onboarded"] = True
        try:
            OWNER_FILE.write_text(json.dumps(payload, ensure_ascii=False, indent=2),
                                  encoding="utf-8")
        except Exception as exc:  # pragma: no cover
            log.warning("[JRV-CFG-001] ذخیره‌ی owner.json ناموفق بود: %s", exc)

        try:
            from .memory.curator import remember
            nm = self.answers.get("name")
            if nm:
                remember(f"اسمِ کاربر {nm} است", category="identity", source="onboarding")
            if title:
                remember(f"کاربر دوست دارد «{title}» صدا زده شود",
                         category="preference", source="onboarding")
            loc = self.answers.get("location")
            if loc:
                remember(f"شهرِ کاربر {loc} است", category="identity", source="onboarding")
            foc = self.answers.get("focus")
            if foc and len(foc.split()) >= 2:
                remember(f"کاربر بیشتر این کارها را می‌خواهد: {foc}",
                         category="preference", source="onboarding")
        except Exception as exc:  # pragma: no cover
            log.warning("نوشتن در حافظه ناموفق بود: %s", exc)

        with STATE.lock:
            STATE.onboarding_active = False
            STATE.onboarding_question = ""
        log.info("آشناییِ اولیه کامل شد: %s", payload)

    def _persist_config(self, key: str, value) -> None:
        from .paths import LOCAL_CONFIG_FILE
        for path in (APP_DIR / "config.json", LOCAL_CONFIG_FILE):
            if path.is_file():
                try:
                    d = json.loads(path.read_text(encoding="utf-8"))
                    d[key] = value
                    path.write_text(json.dumps(d, ensure_ascii=False, indent=2),
                                    encoding="utf-8")
                    return
                except Exception:
                    continue


# ---------------- حالتِ متنی (وقتی صدا در دسترس نیست) ----------------

def run_text(cfg) -> None:
    import sys
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    ob = Onboarding(cfg)
    print("\n=== آشناییِ اولیه‌ی جارویس ===")
    msg = ob.start()
    while True:
        try:
            ans = input(f"\n{msg}\n> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n(رد شد)")
            break
        done, msg = ob.submit(ans)
        if done:
            print(msg)
            break
    with STATE.lock:
        STATE.onboarding_active = False
