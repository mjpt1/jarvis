"""آشناییِ اولیه — بارِ اول که جارویس روی یک سیستم اجرا می‌شود، چند سؤال می‌پرسد
و یاد می‌گیرد اربابش کیست و چه کارهایی باید برایش انجام دهد.

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
    ("name", "سلام. من جارویسم، دستیارِ شخصیِ شما. اسمِ شما چیه؟", "identity"),
    ("title", "از این به بعد چطور صداتون کنم؟ مثلاً «قربان»، «رئیس»، یا اسمِ کوچیکتون؟", "preference"),
    ("location", "کجا زندگی می‌کنید؟", "identity"),
    ("focus", "بیشتر چه کارهایی ازم می‌خواید براتون انجام بدم؟", "preference"),
]

_SKIP = {"رد کن", "بعدا", "بعداً", "نمیخوام بگم", "بی خیال", "هیچی"}


def needs_onboarding() -> bool:
    return not OWNER_FILE.is_file()


def load_owner() -> dict:
    try:
        return json.loads(OWNER_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


class Onboarding:
    def __init__(self, cfg):
        self.cfg = cfg
        self.i = 0
        self.answers: dict[str, str] = {}

    # ------------------------------------------------------------------
    def start(self) -> str:
        self.i = 0
        self.answers.clear()
        with STATE.lock:
            STATE.onboarding_active = True
        return self._ask()

    def _ask(self) -> str:
        q = _QUESTIONS[self.i][1]
        with STATE.lock:
            STATE.onboarding_question = q
        return q

    def is_done(self) -> bool:
        return self.i >= len(_QUESTIONS)

    def submit(self, answer: str) -> tuple[bool, str]:
        """پاسخِ کاربر را می‌گیرد. برمی‌گرداند: (تمام‌شد؟, جمله‌ی بعدیِ جارویس)."""
        answer = (answer or "").strip()
        key, _q, _cat = _QUESTIONS[self.i]
        if normalize(answer) not in _SKIP and len(answer) >= 1:
            self.answers[key] = answer
        self.i += 1
        if self.is_done():
            self._finish()
            name = self.answers.get("name", "")
            hi = f" {name}" if name else ""
            return True, (f"از آشنایی خوشحالم{hi}. همه‌چیز رو یادداشت کردم و "
                          f"از این به بعد در خدمتم. هر وقت کارم داشتید بگید «جارویس».")
        # تاییدِ کوتاه + سؤالِ بعدی
        ack = {"name": "خوشبختم.", "title": "چشم.", "location": "خوبه."}.get(key, "")
        return False, (ack + " " + self._ask()).strip()

    # ------------------------------------------------------------------
    def _finish(self) -> None:
        ensure_dirs()
        title = self.answers.get("title", "").strip()
        if title:
            # «آقای رضایی» / «رضا» → همان؛ «قربان»/«رئیس» → همان
            self.cfg.user_title = title
            self._persist_config("user_title", title)

        payload = dict(self.answers)
        payload["onboarded"] = True
        try:
            OWNER_FILE.write_text(json.dumps(payload, ensure_ascii=False, indent=2),
                                  encoding="utf-8")
        except Exception as exc:  # pragma: no cover
            log.warning("ذخیره‌ی owner.json ناموفق بود: %s", exc)

        # نوشتن در حافظه‌ی بلندمدت
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
                remember(f"کاربر در {loc} زندگی می‌کند", category="identity",
                         source="onboarding")
            foc = self.answers.get("focus")
            if foc:
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
    q = ob.start()
    while True:
        try:
            ans = input(f"\n{q}\n> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n(رد شد)")
            break
        done, nxt = ob.submit(ans)
        print(nxt)
        if done:
            break
        q = STATE.onboarding_question
    with STATE.lock:
        STATE.onboarding_active = False
