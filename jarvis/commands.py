"""موتور دستورهای صوتی: ساخت فهرست دستورها، تطبیق فازی، و اجرا.

ترتیب پردازشِ یک عبارتِ شنیده‌شده:
    ۱) جستجوی گوگل   ۲) تایمر/یادآوری   ۳) دستورهای کلیدواژه‌ای (فازی)
    ۴) فال‌بک به Claude (اختیاری)
"""

from __future__ import annotations

import random
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass

from . import claude_client, reports, system_actions, tts
from .config import Config
from .logging_setup import get_logger
from .music import MusicPlayer
from .state import STATE
from .text_fa import (
    extract_reminder_message,
    fuzzy_contains,
    normalize,
    parse_duration_seconds,
    strip_phrase,
)

log = get_logger("commands")


@dataclass
class Command:
    name: str
    keywords: list[str]
    handler: Callable[..., None]
    wants_text: bool = False        # هندلر متنِ کاملِ شنیده‌شده را می‌گیرد


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

        if self.cfg.proactive_enabled:
            C(Command("BUDGET", ["چقدر خرج کردی", "بودجه چقدره", "امروز چقدر هزینه شد",
                                 "مصرفت چقدره"],
                      lambda: say(self._budget_line())))
            C(Command("AUTONOMY_SET", ["سطح خودمختاری", "خودمختاریت رو بذار",
                                       "استقلالت رو بذار", "آزادیت رو کم کن",
                                       "آزادیت رو زیاد کن"],
                      self._cmd_set_autonomy, wants_text=True))
            C(Command("COMMAND_CENTER", ["چه کارهایی داری", "مرکز فرمان",
                                         "چه خبر از کارها", "وضعیت کلی"],
                      lambda: say(self._command_center_line())))
            C(Command("QUIET_NIGHT", ["تا صبح ساکت باش", "شب‌بخیر", "دیگه چیزی نگو تا صبح"],
                      self._cmd_quiet))

        if self.cfg.mission_enabled:
            C(Command("SKILL_SAVE", ["این کار رو مهارت کن", "این رو به عنوان مهارت ذخیره کن",
                                     "این کارو یاد بگیر به اسم"],
                      self._cmd_skill_save, wants_text=True))
            C(Command("SKILL_RUN", ["مهارت رو اجرا کن", "مهارتِ", "کارِ", "اون مهارتو انجام بده"],
                      self._cmd_skill_run, wants_text=True))
            C(Command("SKILL_LIST", ["چه مهارت‌هایی داری", "مهارت‌هات چیه",
                                     "چه کارهایی بلدی"],
                      lambda: say(self._skills().list_spoken())))

        if self.cfg.memory_enabled:
            C(Command("REMEMBER", ["این رو یادت باشه", "یادت باشه که", "به خاطر بسپار",
                                   "یادداشت کن که", "به یاد داشته باش", "ذخیره کن که"],
                      self._cmd_remember, wants_text=True))
            C(Command("RECALL", ["چی یادته درباره", "درباره‌ش چی می‌دونی", "چی می‌دونی درباره",
                                 "راجع بهش چی یادته", "چی یادت مونده از"],
                      self._cmd_recall, wants_text=True))
            C(Command("MEMORY_STATS", ["حافظه‌ت رو نشون بده", "چند تا چیز یادته",
                                       "وضعیت حافظه", "حافظه‌ت چطوره"],
                      self._cmd_memory_stats))
            C(Command("MEMORY_FORGET", ["اون رو فراموش کن", "پاکش کن از حافظه",
                                        "یادت نباشه"],
                      lambda: say(f"{T}، برای فراموش کردن باید در فایلِ حافظه دستی "
                                  f"بایگانی‌اش کنید؛ من چیزی رو برای همیشه پاک نمی‌کنم.")))
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

        C(Command("CONVO_ON", ["همیشه گوش بده", "حالت مکالمه", "همش گوش بده",
                               "دیگه صدات نمی‌کنم", "گوش بده بهم"], self._convo_on))
        C(Command("CONVO_OFF", ["دیگه گوش نده", "از حالت مکالمه خارج شو",
                                "گوش نکن دیگه"], self._convo_off))
        C(Command("MUTE_EVENTS", ["ساکت شو", "ساکت باش", "بی صدا شو"], self._mute_events))
        C(Command("UNMUTE_EVENTS", ["فعال شو", "دوباره حرف بزن", "صدا رو بیار"], self._unmute_events))
        C(Command("QUIT", ["برنامه رو ببند", "جارویس رو ببند", "خروج از برنامه", "خودت رو ببند"],
                  self._quit))

        for alias, path in self.cfg.folder_aliases.items():
            C(Command(f"OPEN::{alias}",
                      [f"{alias} رو باز کن", f"{alias} باز کن"],
                      A.make_folder_action(alias, path, T)))

        self._build_integrations(C)

        # جملات ثابتِ وابسته به «خطاب کاربر»
        self.wake_ack = [f"بله {T}؟", f"گوش می‌کنم {T}.", f"در خدمتم {T}."]
        self.unknown_lines = [f"متوجه نشدم {T}، دوباره بگید.",
                              f"ببخشید {T}، دستور رو نفهمیدم."]
        self.confirm_cancelled = [f"باشه {T}، انجامش نمی‌دم."]

        # خطوط ثابت برای پیش‌ساختِ کش
        self.static_lines = (self.wake_ack + self.unknown_lines + self.confirm_cancelled
                             + [f"سلام {T}.", f"در خدمتم {T}."])

    # ------------------------------------------------------------------
    def _build_integrations(self, C) -> None:
        """دستورهای صوتیِ ادغام‌ها — فقط آن‌هایی که واقعاً در دسترس‌اند."""
        say = tts.say
        from .integrations import google_ws, notion_ws, spotify_ws, vision_tools, web

        if self.cfg.vision_enabled and vision_tools.available():
            C(Command("SCENE", ["چی می‌بینی", "صحنه رو توصیف کن", "رو صفحه چی هست",
                                "جلوت چی هست", "تو اتاق چی می‌بینی", "چی جلومه"],
                      lambda: say(vision_tools.describe_scene())))

        if self.cfg.face_id_enabled:
            C(Command("ENROLL_FACE", ["چهره‌ی من رو ثبت کن", "صورتم رو یاد بگیر",
                                      "چهره‌ام رو ذخیره کن"],
                      self._cmd_enroll_face))

        if self.cfg.web_enabled and web.available():
            C(Command("WEB_ANSWER",
                      ["تو اینترنت بگرد", "تو وب سرچ کن", "از اینترنت بپرس",
                       "تو گوگل بگرد و بگو", "جوابش رو از اینترنت پیدا کن"],
                      self._cmd_web_answer, wants_text=True))

        if self.cfg.google_enabled and google_ws.available():
            C(Command("GMAIL_UNREAD",
                      ["ایمیل جدید دارم", "ایمیل‌های نخونده", "میل چک کن",
                       "ایمیلام رو بخون"],
                      lambda: say(google_ws.unread_summary())))
            C(Command("CAL_UPCOMING",
                      ["برنامه‌ام چیه", "تقویمم چیه", "قرارهای این هفته",
                       "رویدادهای پیش رو", "امروز چه قراری دارم"],
                      lambda: say(google_ws.upcoming_events())))

        if self.cfg.spotify_enabled and spotify_ws.available():
            C(Command("SPOT_PLAY", ["اسپاتیفای پخش کن", "اسپاتیفای ادامه بده"],
                      lambda: say(spotify_ws.play())))
            C(Command("SPOT_PAUSE", ["اسپاتیفای رو نگه دار", "اسپاتیفای مکث"],
                      lambda: say(spotify_ws.pause())))
            C(Command("SPOT_NEXT", ["اسپاتیفای بعدی"], lambda: say(spotify_ws.next_track())))
            C(Command("SPOT_PREV", ["اسپاتیفای قبلی"], lambda: say(spotify_ws.prev_track())))
            C(Command("SPOT_NOW", ["چی داره پخش میشه", "الان چه آهنگیه"],
                      lambda: say(spotify_ws.current())))
            C(Command("SPOT_SEARCH", ["تو اسپاتیفای پخش کن", "از اسپاتیفای بذار"],
                      self._cmd_spotify_search, wants_text=True))

        if self.cfg.notion_enabled and notion_ws.available():
            C(Command("NOTION_SEARCH", ["تو نوشن بگرد", "تو نوشن پیدا کن",
                                        "از نوشن برام بیار"],
                      self._cmd_notion, wants_text=True))

    def _cmd_web_answer(self, text: str):
        from .integrations import web
        q = text
        for p in ("تو اینترنت بگرد", "تو وب سرچ کن", "از اینترنت بپرس",
                  "تو گوگل بگرد و بگو", "جوابش رو از اینترنت پیدا کن", "و بگو", "ببین"):
            q = strip_phrase(q, p)
        tts.say(f"{self.title}، بذارید ببینم…")
        tts.say(web.answer(q.strip(" ؟?،.")))

    def _cmd_spotify_search(self, text: str):
        from .integrations import spotify_ws
        q = text
        for p in ("تو اسپاتیفای پخش کن", "از اسپاتیفای بذار", "آهنگ", "رو"):
            q = strip_phrase(q, p)
        tts.say(spotify_ws.play_search(q.strip()))

    def _cmd_enroll_face(self):
        try:
            import cv2
        except Exception:
            tts.say(f"{self.title}، برای این کار به دوربین نیاز دارم.")
            return
        from .integrations import face_id
        from .paths import CREDENTIALS_DIR
        tts.say(f"{self.title}، لطفاً چند لحظه رو به دوربین نگاه کنید.")
        cap = cv2.VideoCapture(self.cfg.camera_index)
        ok, frame = cap.read()
        cap.release()
        if not ok:
            tts.say(f"{self.title}، دوربین در دسترس نبود.")
            return
        tmp = str(CREDENTIALS_DIR / "_enroll_tmp.jpg")
        cv2.imwrite(tmp, frame)
        tts.say(face_id.enroll(tmp))

    def _cmd_notion(self, text: str):
        from .integrations import notion_ws
        q = text
        for p in ("تو نوشن بگرد", "تو نوشن پیدا کن", "از نوشن برام بیار", "دنبال", "درباره"):
            q = strip_phrase(q, p)
        tts.say(notion_ws.search_and_read(q.strip()))

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
    # ---------------- مهارت‌ها ----------------
    def _skills(self):
        if not hasattr(self, "_skill_mgr"):
            from .skills.manager import SkillManager
            self._skill_mgr = SkillManager(self)
        return self._skill_mgr

    def _cmd_skill_save(self, text: str):
        name = text
        for p in ("این کار رو مهارت کن", "این رو به عنوان مهارت ذخیره کن",
                  "این کارو یاد بگیر به اسم", "به اسم", "به نام", "اسمش"):
            name = strip_phrase(name, p)
        name = name.strip(" ،.") or "مهارت بی‌نام"
        tts.say(self._skills().save_from_last_mission(name))

    def _cmd_skill_run(self, text: str):
        name = text
        for p in ("مهارت رو اجرا کن", "اون مهارتو انجام بده", "مهارتِ", "مهارت",
                  "کارِ", "رو اجرا کن", "رو انجام بده"):
            name = strip_phrase(name, p)
        name = name.strip(" ،.")
        if not name:
            tts.say(f"{self.title}، کدوم مهارت؟")
            return
        tts.say(self._skills().run(name))

    # ---------------- پیش‌کنشی / حاکمیت ----------------
    def _budget_line(self) -> str:
        from .proactive.budget import BUDGET
        return BUDGET.spoken(self.title)

    def _cmd_set_autonomy(self, text: str):
        from .proactive import notifications
        from .text_fa import normalize, words_to_number
        n = words_to_number(text)
        norm = normalize(text)
        if n is None:
            if "کم" in norm:
                n = max(0, notifications.autonomy() - 1)
            elif "زیاد" in norm or "بیشتر" in norm:
                n = min(5, notifications.autonomy() + 1)
            else:
                tts.say(f"{self.title}، یک عدد بین صفر تا پنج بگید.")
                return
        lvl = notifications.set_autonomy(int(n))
        self.cfg.autonomy_level = lvl
        desc = {0: "فقط وقتی بپرسید جواب می‌دم", 1: "اعلان‌های مهم رو می‌گم",
                2: "کارهای خواندنی رو خودم انجام می‌دم",
                3: "مأموریت پیشنهاد می‌دم و با تاییدتون اجرا می‌کنم",
                4: "کارهای امن رو بدون تایید انجام می‌دم", 5: "کاملاً مستقل عمل می‌کنم"}
        tts.say(f"باشه {self.title}، سطحِ خودمختاری روی {lvl} — {desc[lvl]}.")

    def _command_center_line(self) -> str:
        from .proactive.budget import BUDGET
        from .proactive.notifications import autonomy, recent
        parts = [f"سطحِ خودمختاری {autonomy()}"]
        s = BUDGET.summary()
        parts.append(f"امروز {s['calls']} تماس، {s['usd']:.3f} دلار")
        notes = recent(3)
        if notes:
            parts.append("آخرین اعلان‌ها: " + "؛ ".join(n["text"] for n in notes))
        else:
            parts.append("اعلانِ تازه‌ای نیست")
        return f"{self.title}، " + ". ".join(parts) + "."

    def _cmd_quiet(self):
        from .proactive import notifications
        notifications.quiet_until_morning()
        tts.say(f"شب‌بخیر {self.title}، تا صبح ساکت می‌مونم مگر چیزِ فوری باشه.")

    # ---------------- حافظه ----------------
    def _cmd_remember(self, text: str):
        content = text
        for p in ("این رو یادت باشه", "یادت باشه که", "به خاطر بسپار",
                  "یادداشت کن که", "به یاد داشته باش", "ذخیره کن که",
                  "این رو", "یادت باشه", "که"):
            content = strip_phrase(content, p)
        content = content.strip(" ،.")
        if len(content) < 3:
            tts.say(f"{self.title}، چی رو یادم باشه؟")
            return
        from .memory.curator import remember
        remember(content, source="user")
        tts.say(f"باشه {self.title}، یادم می‌مونه: {content}")

    def _cmd_recall(self, text: str):
        from .memory.store import get_store
        from .text_fa import normalize
        topic = normalize(text)
        for p in ("چی یادته درباره", "درباره‌ش چی می‌دونی", "چی می‌دونی درباره",
                  "راجع بهش چی یادته", "چی یادت مونده از", "درباره", "راجع به", "ی"):
            topic = topic.replace(p, " ")
        topic = topic.strip()
        store = get_store()
        hits = store.search(topic, limit=4) if topic else store.recent(4)
        if not hits:
            tts.say(f"{self.title}، چیزی دربارهٔ این یادم نیست.")
            return
        tts.say(f"{self.title}، این‌ها رو یادمه: " + "؛ ".join(f.text for f in hits))

    def _cmd_memory_stats(self):
        from .memory.store import get_store
        st = get_store().stats()
        if not st["active"]:
            tts.say(f"{self.title}، هنوز چیزی تو حافظه‌م نیست.")
            return
        top = sorted(st["by_category"].items(), key=lambda x: -x[1])[:3]
        parts = "، ".join(f"{n} مورد {c}" for c, n in top)
        tts.say(f"{self.title}، {st['active']} حقیقت یادمه؛ بیشترشون: {parts}.")

    def _convo_on(self):
        with STATE.lock:
            STATE.conversation_active = True
            STATE.awaiting_command = True
        tts.say(f"باشه {self.title}، تا وقتی نگید «بسه» منتظر دستورهاتون می‌مونم.")

    def _convo_off(self):
        with STATE.lock:
            STATE.conversation_active = False
            STATE.awaiting_command = False
        tts.say(f"باشه {self.title}، هر وقت کارم داشتید صدام کنید.")

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
                cmd.handler(text) if cmd.wants_text else cmd.handler()
            except Exception as exc:
                log.exception("اجرای دستور %s خطا داد: %s", cmd.name, exc)
                tts.say(f"{self.title}، در اجرای دستور مشکلی پیش اومد.")
            return True
        # مأموریتِ چندمرحله‌ای؟
        if self.cfg.mission_enabled and _looks_like_mission(text):
            from .missions.engine import run_mission_async
            run_mission_async(text, self)
            return True
        reply = claude_client.ask(text)
        if reply:
            STATE.log("CLAUDE")
            tts.say(reply)
            return True
        return False


CONFIRM_YES = ["بله", "اره", "تایید", "انجامش بده", "درسته", "حتما"]
CONFIRM_NO = ["نه", "لغو", "بی خیال", "نمی خواد", "کنسل"]

_MISSION_HINTS = [
    "یه کاری برام بکن", "این کارها رو انجام بده", "برام انجام بده", "مأموریت",
    "ماموریت", "چند تا کار", "اول ", "بعدش ", "سپس ", "قدم به قدم", "مرحله به مرحله",
    "و بعد ", "همه‌ی این", "ترتیب",
]


def _looks_like_mission(text: str) -> bool:
    n = normalize(text)
    if any(h in n for h in (normalize(x) for x in _MISSION_HINTS)):
        return True
    # جمله‌ی طولانی با چند فعلِ امری پشت‌سرهم
    return len(n.split()) >= 10 and n.count(" و ") >= 2


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
