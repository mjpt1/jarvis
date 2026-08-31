"""موتور دستورهای صوتی: ساخت فهرست دستورها، تطبیق فازی، و اجرا.

ترتیب پردازشِ یک عبارتِ شنیده‌شده:
    ۱) جستجوی گوگل   ۲) تایمر/یادآوری   ۳) دستورهای کلیدواژه‌ای (فازی)
    ۴) فال‌بک به Claude (اختیاری)
"""

from __future__ import annotations

import random
import threading
import time
from dataclasses import dataclass
from typing import Callable

from .config import Config
from .logging_setup import get_logger
from .state import STATE
from . import claude_client, reports, system_actions, tts
from .music import MusicPlayer
from .text_fa import (
    extract_reminder_message, fuzzy_contains, normalize, parse_duration_seconds,
    strip_phrase,
)

log = get_logger("commands")


@dataclass
class Command:
    name: str
    keywords: list[str]
    handler: Callable[[], None]


class CommandEngine:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.title = cfg.user_title
        self.music = MusicPlayer(cfg.music_dir, self.title)
        self.commands: list[Command] = []
        self.static_lines: list[str] = []
        self._build()
        self._register_claude_actions()

    # ------------------------------------------------------------------
    def _t(self, s: str) -> str:
        return s.replace("{t}", self.title)

    def _build(self) -> None:
        T = self.title
        say = tts.say
        A = system_actions

        def greeting():
            say(random.choice([f"سلام {T}.", f"در خدمتم {T}."]))

        C = self.commands.append
        C(Command("GREETING", ["سلام", "درود"], greeting))
        C(Command("STATUS", ["وضعیت", "گزارش بده", "اوضاع چطوره"],
                  lambda: say(reports.status())))
        C(Command("TIME", ["ساعت چنده", "ساعت چند", "چه ساعتی", "زمان"],
                  lambda: say(reports.clock())))
        C(Command("ELAPSED", ["چقدر گذشته", "چند دقیقه گذشته", "چقدر از کارمون"],
                  lambda: say(reports.elapsed())))
        C(Command("SYSTEM", ["وضعیت سیستم", "سیستم چطوره", "سی پی یو", "پردازنده", "رم چقدره"],
                  lambda: say(reports.system())))
        C(Command("WEATHER", ["هوا چطوره", "اب و هوا", "دمای هوا", "چند درجه‌ست", "هوای اینجا"],
                  lambda: say(reports.weather())))
        C(Command("NEWS", ["اخبار", "خبر جدید", "چه خبر"],
                  lambda: say(reports.news())))
        C(Command("AUTHOR", ["کی تو رو ساخته", "برنامه نویست کیه", "سازنده‌ات کیه",
                             "کی برنامه نویسیت کرده", "توسعه دهنده"],
                  lambda: say(reports.author())))
        C(Command("SEC_TIME", ["ساعت مونکتون", "ساعت کانادا", "مونکتون ساعت چنده",
                               "اونجا ساعت چنده"],
                  lambda: say(reports.secondary_clock())))
        C(Command("SEC_WEATHER", ["هوای مونکتون", "دمای مونکتون", "هوای کانادا",
                                  "مونکتون چند درجه"],
                  lambda: say(reports.secondary_weather())))
        C(Command("DATE", ["امروز چندمه", "تاریخ امروز", "چه تاریخیه", "امروز چه روزیه"],
                  lambda: say(_date_line(T))))
        C(Command("BATTERY", ["باتری چقدره", "شارژ چقدره", "باتری چند درصده"],
                  lambda: say(reports.system())))
        C(Command("MUTE_TOGGLE", ["صدای خودت رو قطع کن", "حرف نزن دیگه"], self._mute_events))
        C(Command("THANKS", ["ممنون", "مرسی", "دستت درد نکنه", "خسته نباشی"],
                  lambda: say(random.choice([f"خواهش می‌کنم {T}.",
                                             f"کاری نکردم {T}.", f"همیشه در خدمتم {T}."]))))
        C(Command("WHO_AM_I", ["من کیم", "اسم من چیه", "من رو می‌شناسی"],
                  lambda: say(f"شما {T} هستید، کاربر اصلیِ من.")))
        C(Command("JOKE", ["یه جوک بگو", "یه چیز بامزه بگو", "بخندونم"],
                  lambda: say(random.choice(_JOKES))))
        C(Command("FLIP_COIN", ["شیر یا خط", "سکه بنداز", "پرتاب سکه"],
                  lambda: say(f"{random.choice(['شیر', 'خط'])} اومد {T}.")))
        C(Command("DICE", ["تاس بنداز", "یه عدد شانسی بگو"],
                  lambda: say(f"{random.randint(1, 6)} {T}.")))

        C(Command("OPEN_GOOGLE", ["گوگل رو باز کن", "گوگل باز کن"],
                  A.make_url_action("https://www.google.com", "گوگل", T)))
        C(Command("OPEN_YOUTUBE", ["یوتیوب رو باز کن", "یوتیوب باز کن"],
                  A.make_url_action("https://www.youtube.com", "یوتیوب", T)))
        C(Command("OPEN_GMAIL", ["جیمیل رو باز کن", "ایمیل رو باز کن"],
                  A.make_url_action("https://mail.google.com", "جیمیل", T)))
        C(Command("OPEN_MYSITE", ["سایت من رو باز کن", "سایتم رو باز کن", "سایت خودم"],
                  A.make_url_action(self.cfg.website_url, "سایتتون", T)))
        C(Command("OPEN_NOTEPAD", ["نوت پد رو باز کن", "نوت‌پد باز کن", "دفترچه یادداشت"],
                  A.make_app_action(["notepad.exe"], ["open", "-a", "TextEdit"],
                                    ["gedit"], "نوت‌پد", T)))
        C(Command("OPEN_CALC", ["ماشین حساب رو باز کن", "ماشین‌حساب باز کن"],
                  A.make_app_action(["calc.exe"], ["open", "-a", "Calculator"],
                                    ["gnome-calculator"], "ماشین‌حساب", T)))
        C(Command("OPEN_EXPLORER", ["فایل اکسپلورر", "اکسپلورر رو باز کن", "پنجره فایل"],
                  A.make_folder_action("فایل اکسپلورر",
                                       __import__("os").path.expanduser("~"), T)))

        C(Command("MUSIC_PLAY", ["اهنگ پخش کن", "یه اهنگ بذار", "موزیک پخش کن", "موزیک بذار"],
                  self.music.play_random))
        C(Command("MUSIC_NEXT", ["اهنگ بعدی", "بعدی رو بذار"], self.music.next_track))
        C(Command("MUSIC_PREV", ["اهنگ قبلی", "قبلی رو بذار"], self.music.prev_track))
        C(Command("MUSIC_STOP", ["اهنگ رو قطع کن", "موزیک رو قطع کن", "اهنگ رو ببند"],
                  self.music.stop))
        C(Command("MUSIC_PAUSE", ["اهنگ رو مکث کن", "اهنگ رو نگه دار", "پاز کن"],
                  self.music.pause))
        C(Command("MUSIC_RESUME", ["اهنگ رو ادامه بده", "ادامه بده اهنگ"], self.music.resume))

        C(Command("MEDIA_PLAYPAUSE", ["پخش یا مکث", "پلی پاز"],
                  lambda: A.media_key("playpause")))

        C(Command("VOL_UP", ["صدا رو زیاد کن", "صدای سیستم رو زیاد کن", "بلندتر"],
                  lambda: A.set_system_volume(T, delta=0.1)))
        C(Command("VOL_DOWN", ["صدا رو کم کن", "صدای سیستم رو کم کن", "اروم‌تر"],
                  lambda: A.set_system_volume(T, delta=-0.1)))
        C(Command("VOL_MUTE", ["صدای سیستم رو قطع کن", "صدای سیستم رو ببند"],
                  lambda: A.set_system_volume(T, absolute=0.0)))

        C(Command("SCREENSHOT", ["اسکرین شات بگیر", "از صفحه عکس بگیر", "عکس صفحه"],
                  lambda: A.screenshot(T)))
        C(Command("LOCK", ["سیستم رو قفل کن", "کامپیوتر رو قفل کن", "قفل کن"],
                  lambda: A.lock_screen(T)))

        C(Command("SHUTDOWN", ["سیستم رو خاموش کن", "کامپیوتر رو خاموش کن", "خاموش کن سیستم"],
                  lambda: self.request_confirm("shutdown",
                          f"{T}، مطمئنید سیستم خاموش بشه؟ بگید بله یا نه.")))
        C(Command("RESTART", ["سیستم رو ری استارت کن", "کامپیوتر رو ری استارت کن", "ری استارت کن"],
                  lambda: self.request_confirm("restart",
                          f"{T}، مطمئنید سیستم ری‌استارت بشه؟ بگید بله یا نه.")))
        C(Command("SLEEP_PC", ["سیستم رو بخوابون", "کامپیوتر رو بخوابون", "اسلیپ کن"],
                  lambda: self.request_confirm("sleep",
                          f"{T}، سیستم رو بخوابونم؟ بگید بله یا نه.")))

        C(Command("MUTE_EVENTS", ["ساکت شو", "ساکت باش", "بی صدا شو"], self._mute_events))
        C(Command("UNMUTE_EVENTS", ["فعال شو", "دوباره حرف بزن", "صدا رو بیار"], self._unmute_events))
        C(Command("QUIT", ["برنامه رو ببند", "جارویس رو ببند", "خروج از برنامه", "خودت رو ببند"],
                  self._quit))

        for alias, path in self.cfg.folder_aliases.items():
            C(Command(f"OPEN::{alias}",
                      [f"{alias} رو باز کن", f"{alias} باز کن"],
                      A.make_folder_action(alias, path, T)))

        # جملات ثابتِ وابسته به «خطاب کاربر»
        self.wake_ack = [f"بله {T}؟", f"گوش می‌کنم {T}.", f"در خدمتم {T}."]
        self.unknown_lines = [f"متوجه نشدم {T}، دوباره بگید.",
                              f"ببخشید {T}، دستور رو نفهمیدم."]
        self.confirm_cancelled = [f"باشه {T}، انجامش نمی‌دم."]

        # خطوط ثابت برای پیش‌ساختِ کش
        self.static_lines = (self.wake_ack + self.unknown_lines + self.confirm_cancelled
                             + [f"سلام {T}.", f"در خدمتم {T}."])

    # ------------------------------------------------------------------
    def _register_claude_actions(self) -> None:
        if not self.cfg.claude_can_run_actions:
            return
        for cmd in self.commands:
            if cmd.name in ("QUIT", "SHUTDOWN", "RESTART", "SLEEP_PC"):
                continue  # اقدامات پرخطر را به Claude نمی‌سپاریم
            claude_client.register_action(cmd.name, cmd.keywords[0], lambda c=cmd: c.handler())
        claude_client.register_action("GOOGLE_SEARCH", "جستجوی عبارت در گوگل",
                                      lambda q="": system_actions.google_search(q, self.title))

    # ------------------------------------------------------------------
    def _mute_events(self):
        with STATE.lock:
            STATE.audio_muted = True
        tts.say(f"باشه {self.title}، رویدادهای خودکار رو ساکت می‌کنم.")

    def _unmute_events(self):
        with STATE.lock:
            STATE.audio_muted = False
        tts.say(f"باشه {self.title}، دوباره فعال شدم.")

    def _quit(self):
        tts.say(f"در حال خاموش شدن {self.title}.", blocking=True)
        STATE.stop()

    # ------------------------------------------------------------------
    def request_confirm(self, action: str, prompt: str) -> None:
        with STATE.lock:
            STATE.pending_confirm_action = action
            STATE.pending_confirm_since = time.time()
        tts.say(prompt)

    def run_confirmed(self, action: str) -> None:
        fn = {
            "shutdown": system_actions.do_shutdown,
            "restart": system_actions.do_restart,
            "sleep": system_actions.do_sleep,
        }.get(action)
        if not fn:
            return
        tts.say({"shutdown": f"در حال خاموش کردن سیستم {self.title}.",
                 "restart": f"در حال ری‌استارت {self.title}.",
                 "sleep": f"سیستم رو می‌خوابونم {self.title}."}[action])
        threading.Thread(target=fn, daemon=True).start()

    # ------------------------------------------------------------------
    def _try_search(self, text: str) -> bool:
        norm = normalize(text)
        for phrase in ("رو تو گوگل سرچ کن", "رو تو گوگل جستجو کن", "تو گوگل سرچ کن",
                       "رو سرچ کن", "رو جستجو کن", "سرچ کن", "جستجو کن"):
            if phrase in norm:
                query = norm.split(phrase)[0].strip()
                if query:
                    system_actions.google_search(query, self.title)
                    return True
        return False

    def _try_timer(self, text: str) -> bool:
        norm = normalize(text)
        if not any(k in norm for k in ("دقیقه", "ثانیه", "ساعت")):
            return False
        if not any(k in norm for k in ("یادم بنداز", "یاداوری", "یادآوری", "تایمر", "بذار برای", "دیگه", "بعد")):
            return False
        seconds = parse_duration_seconds(norm)
        if not seconds or seconds <= 0:
            return False
        msg = extract_reminder_message(norm)
        mins = max(1, round(seconds / 60))

        def worker():
            if STATE.stop_event.wait(seconds):
                return
            if msg:
                tts.say(f"{self.title}، وقتش شد؛ یادت باشه {msg}.")
            else:
                tts.say(f"{self.title}، زمانی که خواستید تموم شد.")
            STATE.log(f"REMINDER fired ({seconds}s)")

        threading.Thread(target=worker, daemon=True).start()
        STATE.log(f"REMINDER set ({seconds}s)")
        if seconds >= 60:
            tts.say(f"باشه {self.title}، {mins} دقیقه‌ی دیگه یادآوری می‌کنم.")
        else:
            tts.say(f"باشه {self.title}، {seconds} ثانیه‌ی دیگه یادآوری می‌کنم.")
        return True

    def match(self, text: str) -> Command | None:
        best: tuple[float, Command] | None = None
        for cmd in self.commands:
            for kw in cmd.keywords:
                if fuzzy_contains(text, kw, self.cfg.fuzzy_threshold):
                    score = len(normalize(kw))
                    if best is None or score > best[0]:
                        best = (score, cmd)
        return best[1] if best else None

    def handle(self, text: str) -> bool:
        """True یعنی عبارت شناخته و اجرا شد."""
        text = (text or "").strip()
        if not text:
            return False
        if self._try_search(text):
            return True
        if self._try_timer(text):
            return True
        cmd = self.match(text)
        if cmd:
            STATE.log(cmd.name)
            try:
                cmd.handler()
            except Exception as exc:
                log.exception("اجرای دستور %s خطا داد: %s", cmd.name, exc)
                tts.say(f"{self.title}، در اجرای دستور مشکلی پیش اومد.")
            return True
        reply = claude_client.ask(text)
        if reply:
            STATE.log("CLAUDE")
            tts.say(reply)
            return True
        return False


CONFIRM_YES = ["بله", "اره", "تایید", "انجامش بده", "درسته", "حتما"]
CONFIRM_NO = ["نه", "لغو", "بی خیال", "نمی خواد", "کنسل"]

_WEEKDAYS = ["دوشنبه", "سه‌شنبه", "چهارشنبه", "پنجشنبه", "جمعه", "شنبه", "یکشنبه"]
_JOKES = [
    "چرا کامپیوتر سرما خورد؟ چون پنجره‌هاش باز مونده بود.",
    "به الگوریتم گفتن چرا ناراحتی؟ گفت همه‌ش دارن روم شرط می‌ذارن.",
    "یه بایت به یه بیت گفت خسته‌ای؟ گفت آره، یه کم بیت‌حالم.",
]


def _date_line(title: str) -> str:
    import datetime as _dt
    now = _dt.datetime.now()
    return f"امروز {_WEEKDAYS[now.weekday()]}، {now.day} {now.strftime('%B')} {now.year} است {title}."
