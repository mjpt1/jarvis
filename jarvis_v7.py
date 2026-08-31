# -*- coding: utf-8 -*-
"""
J.A.R.V.I.S. Companion v7 — «Stark HUD Pro+»

اضافه شده نسبت به v6:
  • باز کردن پوشه‌ها/درایوها (دانلود، دسکتاپ، اسناد، تصاویر، موزیک، درایوهای C/D/E)
    و برنامه‌ها (نوت‌پد، ماشین‌حساب، فایل‌اکسپلورر).
  • پخش موزیک از یک پوشه‌ی محلی: پخش تصادفی، بعدی/قبلی، مکث/ادامه، توقف.
    (موزیک روی یه کانال جدا از صدای جارویس پخش میشه و موقع حرف زدنش خودکار
    کم‌صدا [duck] میشه، نه قطع.)
  • اسکرین‌شات با دستور صوتی (نیاز به Pillow).
  • خاموش‌کردن/ری‌استارت/خواب سیستم — با یک مرحله‌ی تاییدِ صوتی («بله»/«نه»)
    برای جلوگیری از اجرای اشتباهی.
  • تایمر/یادآوری صوتی («جارویس ۱۰ دقیقه دیگه یادم بنداز آب بخورم»).
  • کنترل صدای سیستم (فقط ویندوز، نیاز به pycaw + comtypes).
  • خوندنِ چند تیتر خبر از یک فید RSS.
  • اسپارک‌لاین شبکه (آپلود/دانلود) کنار گیج‌های CPU/RAM/باتری.
  • (اختیاری) اگه متغیر محیطی ANTHROPIC_API_KEY رو تنظیم کنی، هر دستوری که با
    کلیدواژه‌های بالا مچ نشه، برای فهمیدن و جواب‌دادنِ طبیعی‌تر به Claude
    فرستاده میشه (با حافظه‌ی کوتاه‌مدتِ چند پیامِ آخر).

نصب پیش‌نیازها:
    pip install pygame edge-tts numpy opencv-python mediapipe sounddevice vosk psutil
    pip install pillow                     # برای اسکرین‌شات
    pip install pycaw comtypes             # فقط ویندوز، برای کنترل صدای سیستم (اختیاری)
    pip install arabic-reshaper python-bidi  # زیرنویس فارسی بهتر (اختیاری)

⚠️ قبل از اجرا این‌ها رو با مقادیر خودت عوض کن:
    USER_WEBSITE_URL   -> آدرس سایت خودت
    MUSIC_DIR           -> پوشه‌ی آهنگ‌هات (پیش‌فرض: ~/Music)
    NEWS_RSS_URL        -> فید خبری دلخواهت
    ANTHROPIC_API_KEY   -> (اختیاری) برای فهمِ دستورهای آزاد

کلیدها: ESC خروج | D دیباگ | 0-4 تست دستی رویدادها | M میوت رویدادهای خودکار
"""

import pygame
import asyncio
import edge_tts
import threading
import random
import math
import time
import os
import re
import sys
import json
import queue
import zipfile
import subprocess
import difflib
import datetime
import tempfile
import shutil
import urllib.request
import urllib.parse
import webbrowser

import cv2
import numpy as np
import mediapipe as mp
from mediapipe.tasks import python as mp_python
from mediapipe.tasks.python import vision as mp_vision

import sounddevice as sd
import vosk
vosk.SetLogLevel(-1)

import psutil

try:
    import arabic_reshaper
    from bidi.algorithm import get_display
    HAS_SHAPING = True
except ImportError:
    HAS_SHAPING = False

# ============================================================
# CONFIG کلی
# ============================================================

VOICE = "fa-IR-FaridNeural"

CAMERA_INDEX = 0
FULLSCREEN = True
FPS = 60

BG_COLOR = (2, 5, 9)
ORB_COLOR_IDLE = (0, 190, 255)
ORB_COLOR_SPEAK = (0, 255, 200)

USER_WEBSITE_URL = "https://mahsen81.ir"          # <-- آدرس سایت خودت
MUSIC_DIR = os.path.join(os.path.expanduser("~"), "Music")   # <-- پوشه‌ی آهنگ‌هات
MUSIC_EXTENSIONS = (".mp3", ".wav", ".ogg")
NEWS_RSS_URL = "https://feeds.bbci.co.uk/persian/rss.xml"    # <-- فید خبری دلخواه
WEATHER_UPDATE_INTERVAL = 600
SYSTEM_STATS_INTERVAL = 2.0
CONFIRM_TIMEOUT = 8.0

# (اختیاری) برای فهمِ دستورهای آزاد از طریق Claude — با env var ست کن:
#   export ANTHROPIC_API_KEY=...        (لینوکس/مک)
#   setx ANTHROPIC_API_KEY "..."        (ویندوز)
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
ANTHROPIC_MODEL = "claude-haiku-4-5-20251001"
CHAT_HISTORY_MAX_TURNS = 6

# ------------------------------------------------------------
# پالت رنگی «Stark HUD»
# ------------------------------------------------------------
HUD_CYAN = (0, 200, 255)
HUD_CYAN_DIM = (0, 150, 195)
HUD_CYAN_FAINT = (0, 90, 120)
HUD_WHITE = (220, 245, 255)
HUD_WARN = (255, 150, 60)
HUD_OK = (80, 255, 190)
GAUGE_BG = (14, 30, 42)

MODEL_DIR = os.path.join(tempfile.gettempdir(), "jarvis_models")
MODEL_PATH = os.path.join(MODEL_DIR, "face_landmarker.task")
MODEL_URL = (
    "https://storage.googleapis.com/mediapipe-models/face_landmarker/"
    "face_landmarker/float16/latest/face_landmarker.task"
)

# ------------------------------------------------------------
# CONFIG صدا / wake-word (Vosk، آفلاین، فارسی)
# ------------------------------------------------------------
VOSK_MODEL_NAME = "vosk-model-small-fa-0.42"
VOSK_MODEL_URL = f"https://alphacephei.com/vosk/models/{VOSK_MODEL_NAME}.zip"
VOSK_MODEL_DIR = os.path.join(MODEL_DIR, VOSK_MODEL_NAME)

SAMPLE_RATE = 16000
WAKE_WORDS = ["جارویس", "جارویز", "جاروی","جاروس","جارویش","جاریس",]
COMMAND_TIMEOUT = 6.0

WAKE_ACK_LINES = ["بله قربان؟", "گوش می‌کنم قربان.", "در خدمتم قربان."]
UNKNOWN_COMMAND_LINES = ["متوجه نشدم قربان، دوباره بگید.", "ببخشید قربان، دستور رو نفهمیدم."]
CONFIRM_YES_WORDS = ["بله", "آره", "تایید", "انجامش بده", "باشه انجامش بده"]
CONFIRM_NO_WORDS = ["نه", "لغو کن", "بی‌خیال", "نه قربان"]

# ------------------------------------------------------------
# آستانه‌های تشخیص (فقط برای گزارش وضعیت / فتیگ / اینترودر)
# ------------------------------------------------------------
GAZE_YAW_MAX = 8
GAZE_PITCH_MAX = 10
ROLL_TILT_THRESHOLD = 16
EAR_CLOSED_THRESHOLD = 0.19
FATIGUE_CLOSED_SECONDS = 2.0
TRACKING_LOST_SECONDS = 2.5

LEFT_EYE = [362, 385, 387, 263, 373, 380]
RIGHT_EYE = [33, 160, 158, 133, 153, 144]

# ------------------------------------------------------------
# رویدادهای خودکارِ دوربین — بدون نق‌زدن راجع به زاویه‌ی سر
# ------------------------------------------------------------
EVENTS = {
    "SYSTEM_READY": {"delay": 0.4, "cooldown": 10 ** 9, "lines": ["سیستم آماده‌ست قربان."]},
    "TRACKING_LOCKED": {"delay": 0.3, "cooldown": 10,
                         "lines": ["ردیابی برقراره قربان، ادامه بده.", "اتصال چهره برقرار شد قربان."]},
    "TRACKING_LOST": {"delay": 0.5, "cooldown": 20, "lines": ["قربان، از دیدم خارج شدید."]},
    "INTRUDER": {"delay": 0.3, "cooldown": 25, "lines": ["یه نفر دیگه وارد اتاق شد قربان."]},
    "FATIGUE": {"delay": 0.4, "cooldown": 60, "lines": ["پیشنهاد می‌کنم یکم استراحت کنی قربان."]},
    "TIMER_5MIN": {"delay": 0.0, "cooldown": 10 ** 9, "lines": ["پنج دقیقه از شروع کار گذشته قربان."]},
    "IDLE_STATUS": {"delay": 0.0, "cooldown": 180, "lines": ["همه چیز طبق برنامه پیش میره قربان."]},
}

MANUAL_TEST_KEYS = {
    pygame.K_0: "SYSTEM_READY",
    pygame.K_1: "TRACKING_LOCKED",
    pygame.K_2: "TRACKING_LOST",
    pygame.K_3: "INTRUDER",
    pygame.K_4: "FATIGUE",
}

# ------------------------------------------------------------
# پوشه‌ها/درایوهای قابل باز شدن با صدا — اسم‌ها رو با اسم پوشه‌های خودت هماهنگ کن
# ------------------------------------------------------------
FOLDER_ALIASES = {
    "دسکتاپ": os.path.join(os.path.expanduser("~"), "Desktop"),
    "دانلود": os.path.join(os.path.expanduser("~"), "Downloads"),
    "دانلودها": os.path.join(os.path.expanduser("~"), "Downloads"),
    "اسناد": os.path.join(os.path.expanduser("~"), "Documents"),
    "تصاویر": os.path.join(os.path.expanduser("~"), "Pictures"),
    "موزیک": MUSIC_DIR,
    "درایو سی": "C:\\",
    "درایو دی": "D:\\",
    "درایو ای": "E:\\",
}

# ============================================================
# وضعیت مشترک بین تردها (با لاک محافظت میشه)
# ============================================================

class SharedState:
    def __init__(self):
        self.lock = threading.Lock()
        self.running = True

        self.speaking = False
        self.current_subtitle = ""
        self.cache_ready = False
        self.cache_progress = (0, 1)

        self.face_present = False
        self.face_count = 0
        self.yaw = 0.0
        self.pitch = 0.0
        self.roll = 0.0
        self.face_area_ratio = 0.0
        self.ear = 1.0

        self.audio_muted = False
        self.awaiting_command = False
        self.last_heard_text = ""

        self.cpu_percent = 0.0
        self.ram_percent = 0.0
        self.battery_percent = None
        self.net_history = []   # KB/s دریافتی، برای اسپارک‌لاین

        self.weather_temp = None
        self.weather_desc = ""
        self.location_name = ""

        self.event_log = []

        # تاییدِ صوتیِ اقدامات حساس (خاموش‌کردن/ری‌استارت/خواب)
        self.pending_confirm_action = None
        self.pending_confirm_since = 0.0

        # حافظه‌ی کوتاه‌مدتِ مکالمه برای فال‌بکِ Claude
        self.chat_history = []


STATE = SharedState()
APP_START_TIME = time.time()

AUDIO_CACHE_DIR = tempfile.mkdtemp(prefix="jarvis_cache_")
audio_cache = {}

pygame.mixer.pre_init(44100, -16, 2, 512)


def log_event(text):
    ts = datetime.datetime.now().strftime("%H:%M:%S")
    with STATE.lock:
        STATE.event_log.append((ts, text))
        STATE.event_log = STATE.event_log[-8:]


# ============================================================
# پیش‌ساخت صداها
# ============================================================

async def _build_cache_async():
    all_lines = set()
    for cfg in EVENTS.values():
        for line in cfg["lines"]:
            all_lines.add(line)
    for line in STATIC_VOICE_LINES:
        all_lines.add(line)
    all_lines = list(all_lines)

    for i, line in enumerate(all_lines):
        path = os.path.join(AUDIO_CACHE_DIR, f"line_{i}.mp3")
        communicate = edge_tts.Communicate(line, VOICE)
        await communicate.save(path)
        audio_cache[line] = path
        with STATE.lock:
            STATE.cache_progress = (i + 1, len(all_lines))


def build_cache():
    try:
        asyncio.run(_build_cache_async())
    except Exception as e:
        print(f"[خطا در ساخت کش صدا] {e}")
    with STATE.lock:
        STATE.cache_ready = True


def reshape_farsi(text):
    if not HAS_SHAPING:
        return text
    try:
        return get_display(arabic_reshaper.reshape(text))
    except Exception:
        return text


# ============================================================
# صدا: TTS روی کانال جدا از موزیک (با «داکینگ» موزیک حین حرف‌زدن)
# ============================================================

TTS_CHANNEL_ID = 7


def _duck_music(duck):
    try:
        pygame.mixer.music.set_volume(0.15 if duck else 0.8)
    except Exception:
        pass


def _play_voice_file(path, subtitle_text):
    with STATE.lock:
        STATE.current_subtitle = subtitle_text
        STATE.speaking = True
    _duck_music(True)
    try:
        snd = pygame.mixer.Sound(path)
        ch = pygame.mixer.Channel(TTS_CHANNEL_ID)
        ch.play(snd)
        while ch.get_busy():
            time.sleep(0.03)
    except Exception as e:
        print(f"[خطا در پخش صدا] {e}")
    finally:
        _duck_music(False)
        with STATE.lock:
            STATE.speaking = False
            STATE.current_subtitle = ""


def play_cached(text):
    path = audio_cache.get(text)
    if not path or not os.path.exists(path):
        return
    _play_voice_file(path, text)


def handle_event(name):
    cfg = EVENTS.get(name)
    if not cfg:
        return
    with STATE.lock:
        ready = STATE.cache_ready
        muted = STATE.audio_muted
    if not ready or muted:
        return

    def worker():
        time.sleep(cfg["delay"])
        line = random.choice(cfg["lines"])
        log_event(name)
        play_cached(line)

    threading.Thread(target=worker, daemon=True).start()


def speak_dynamic(text):
    def worker():
        try:
            path = os.path.join(AUDIO_CACHE_DIR, f"dyn_{int(time.time() * 1000)}.mp3")
            asyncio.run(edge_tts.Communicate(text, VOICE).save(path))
            _play_voice_file(path, text)
            os.remove(path)
        except Exception as e:
            print(f"[خطا در تولید صدای زنده] {e}")

    threading.Thread(target=worker, daemon=True).start()


# ============================================================
# موزیک — پخش از پوشه‌ی محلی (کانال جدا از TTS)
# ============================================================

def _scan_music_folder():
    if not os.path.isdir(MUSIC_DIR):
        return []
    return [os.path.join(MUSIC_DIR, f) for f in os.listdir(MUSIC_DIR)
            if f.lower().endswith(MUSIC_EXTENSIONS)]


class MusicPlayer:
    def __init__(self):
        self.playlist = []
        self.index = -1

    def _ensure_playlist(self):
        if not self.playlist:
            self.playlist = _scan_music_folder()
            random.shuffle(self.playlist)

    def _play_current(self):
        if not (0 <= self.index < len(self.playlist)):
            return
        path = self.playlist[self.index]
        try:
            pygame.mixer.music.load(path)
            pygame.mixer.music.set_volume(0.8)
            pygame.mixer.music.play()
            name = os.path.splitext(os.path.basename(path))[0]
            log_event(f"MUSIC: {name}")
            speak_dynamic(f"در حال پخش {name} قربان.")
        except Exception as e:
            print(f"[خطا در پخش آهنگ] {e}")
            speak_dynamic("نتونستم این آهنگ رو پخش کنم قربان.")

    def play_random(self):
        self._ensure_playlist()
        if not self.playlist:
            speak_dynamic(f"قربان، تو پوشه‌ی موزیک آهنگی پیدا نکردم.")
            return
        self.index = random.randrange(len(self.playlist))
        self._play_current()

    def next_track(self):
        self._ensure_playlist()
        if not self.playlist:
            speak_dynamic("قربان، تو پوشه‌ی موزیک آهنگی پیدا نکردم.")
            return
        self.index = (self.index + 1) % len(self.playlist)
        self._play_current()

    def prev_track(self):
        self._ensure_playlist()
        if not self.playlist:
            return
        self.index = (self.index - 1) % len(self.playlist)
        self._play_current()

    def stop(self):
        pygame.mixer.music.stop()
        speak_dynamic("آهنگ رو متوقف کردم قربان.")

    def pause(self):
        pygame.mixer.music.pause()
        speak_dynamic("مکث کردم قربان.")

    def resume(self):
        pygame.mixer.music.unpause()
        speak_dynamic("ادامه میدم قربان.")


MUSIC_PLAYER = MusicPlayer()


# ============================================================
# باز کردن پوشه/درایو/برنامه‌های سیستم
# ============================================================

def _open_path(path):
    try:
        if os.name == "nt":
            os.startfile(path)
        elif sys.platform == "darwin":
            subprocess.run(["open", path])
        else:
            subprocess.run(["xdg-open", path])
        return True
    except Exception as e:
        print(f"[خطا در باز کردن مسیر] {e}")
        return False


def _make_folder_action(alias, path):
    def action():
        if os.path.isdir(path) or (os.name == "nt" and len(path) <= 3):
            if _open_path(path):
                speak_dynamic(f"{alias} رو باز کردم قربان.")
                log_event(f"OPEN_FOLDER: {alias}")
                return
        speak_dynamic("قربان، این مسیر رو پیدا نکردم.")
    return action


def _make_app_action(win_cmd, mac_cmd, linux_cmd, label):
    def action():
        cmd = win_cmd if os.name == "nt" else (mac_cmd if sys.platform == "darwin" else linux_cmd)
        try:
            subprocess.Popen(cmd)
            speak_dynamic(f"{label} رو باز کردم قربان.")
        except Exception as e:
            print(f"[خطا در باز کردن {label}] {e}")
            speak_dynamic(f"نتونستم {label} رو باز می کنم قربان.")
    return action


_open_notepad_action = _make_app_action(["notepad.exe"], ["open", "-a", "TextEdit"], ["gedit"], "نوت‌پد")
_open_calc_action = _make_app_action(["calc.exe"], ["open", "-a", "Calculator"], ["gnome-calculator"], "ماشین‌حساب")
_open_explorer_action = _make_folder_action("فایل اکسپلورر", os.path.expanduser("~"))


def _open_google_action():
    webbrowser.open("https://www.google.com")
    speak_dynamic("گوگل رو باز کردم قربان.")


def _open_mysite_action():
    webbrowser.open(USER_WEBSITE_URL)
    speak_dynamic("سایتتون رو باز کردم قربان.")


def _open_youtube_action():
    webbrowser.open("https://www.youtube.com")
    speak_dynamic("یوتیوب رو باز کردم قربان.")


def _open_gmail_action():
    webbrowser.open("https://mail.google.com")
    speak_dynamic("جیمیل رو باز کردم قربان.")


SEARCH_TRIGGER_PHRASES = [
    "رو تو گوگل سرچ کن", "رو تو گوگل جستجو کن",
    "را تو گوگل سرچ کن", "را تو گوگل جستجو کن",
    "رو سرچ کن", "را سرچ کن", "رو جستجو کن", "را جستجو کن",
]


def try_search_command(text):
    for phrase in SEARCH_TRIGGER_PHRASES:
        if phrase in text:
            query = text.split(phrase)[0].strip()
            if query:
                url = "https://www.google.com/search?q=" + urllib.parse.quote(query)
                webbrowser.open(url)
                log_event(f"SEARCH: {query}")
                speak_dynamic(f"در حال جستجوی {query} تو گوگل قربان.")
                return True
    return False


# ============================================================
# اسکرین‌شات
# ============================================================

def _screenshot_action():
    try:
        from PIL import ImageGrab
        shot_dir = os.path.join(os.path.expanduser("~"), "Pictures", "JarvisScreenshots")
        os.makedirs(shot_dir, exist_ok=True)
        path = os.path.join(shot_dir, f"shot_{int(time.time())}.png")
        img = ImageGrab.grab()
        img.save(path)
        log_event("SCREENSHOT")
        speak_dynamic("اسکرین‌شات رو گرفتم و ذخیره کردم قربان.")
    except ImportError:
        speak_dynamic("قربان، برای اسکرین‌شات باید کتابخونه‌ی Pillow نصب بشه.")
    except Exception as e:
        print(f"[خطا در اسکرین‌شات] {e}")
        speak_dynamic("نتونستم اسکرین‌شات بگیرم قربان.")


# ============================================================
# خاموش‌کردن / ری‌استارت / خواب — با تاییدِ صوتی
# ============================================================

def _request_confirmation(action_name, prompt_text):
    with STATE.lock:
        STATE.pending_confirm_action = action_name
        STATE.pending_confirm_since = time.time()
    speak_dynamic(prompt_text)


def _do_shutdown():
    speak_dynamic("در حال خاموش کردن سیستم قربان.")
    time.sleep(2)
    if os.name == "nt":
        os.system("shutdown /s /t 1")
    elif sys.platform == "darwin":
        os.system('osascript -e \'tell app "System Events" to shut down\'')
    else:
        os.system("shutdown now")


def _do_restart():
    speak_dynamic("در حال ری‌استارت سیستم قربان.")
    time.sleep(2)
    if os.name == "nt":
        os.system("shutdown /r /t 1")
    elif sys.platform == "darwin":
        os.system('osascript -e \'tell app "System Events" to restart\'')
    else:
        os.system("shutdown -r now")


def _do_sleep():
    speak_dynamic("سیستم رو اسلیپ میکنم قربان.")
    time.sleep(1.5)
    if os.name == "nt":
        os.system("rundll32.exe powrprof.dll,SetSuspendState 0,1,0")
    elif sys.platform == "darwin":
        os.system("pmset sleepnow")
    else:
        os.system("systemctl suspend")


PENDING_CONFIRM_ACTIONS = {"shutdown": _do_shutdown, "restart": _do_restart, "sleep": _do_sleep}


def _shutdown_action():
    _request_confirmation("shutdown", "قربان، مطمئنید می‌خواید سیستم خاموش بشه؟ بگید بله یا نه.")


def _restart_action():
    _request_confirmation("restart", "قربان، مطمئنید می‌خواید سیستم ری‌استارت بشه؟ بگید بله یا نه.")


def _sleep_action():
    _request_confirmation("sleep", "قربان، سیستم رو بخوابونم؟ بگید بله یا نه.")


# ============================================================
# کنترل صدای سیستم (فقط ویندوز — نیاز به pycaw + comtypes)
# ============================================================

def _set_system_volume(delta=None, absolute=None):
    if os.name != "nt":
        speak_dynamic("قربان، کنترل صدای سیستم فعلاً فقط تو ویندوز پشتیبانی میشه.")
        return
    try:
        from ctypes import cast, POINTER
        from comtypes import CLSCTX_ALL
        from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
        devices = AudioUtilities.GetSpeakers()
        interface = devices.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
        volume = cast(interface, POINTER(IAudioEndpointVolume))
        cur = volume.GetMasterVolumeLevelScalar()
        new = max(0.0, min(1.0, absolute if absolute is not None else cur + delta))
        volume.SetMasterVolumeLevelScalar(new, None)
        speak_dynamic(f"صدای سیستم رو روی {int(new * 100)} درصد گذاشتم قربان.")
    except ImportError:
        speak_dynamic("قربان، برای کنترل صدا باید pycaw و comtypes نصب بشه.")
    except Exception as e:
        print(f"[خطا در تنظیم صدا] {e}")
        speak_dynamic("نتونستم صدا رو تنظیم کنم قربان.")


def _volume_up_action():
    _set_system_volume(delta=0.1)


def _volume_down_action():
    _set_system_volume(delta=-0.1)


def _volume_mute_action():
    _set_system_volume(absolute=0.0)


# ============================================================
# تایمر / یادآوری صوتی
# ============================================================

PERSIAN_NUMBER_WORDS = {
    "یک": 1, "دو": 2, "سه": 3, "چهار": 4, "پنج": 5, "شش": 6, "هفت": 7, "هشت": 8,
    "نه": 9, "ده": 10, "پانزده": 15, "بیست": 20, "سی": 30, "چهل": 40, "پنجاه": 50, "شصت": 60,
}


def _parse_minutes(text):
    m = re.search(r"(\d+)", text)
    if m:
        return int(m.group(1))
    for word, val in PERSIAN_NUMBER_WORDS.items():
        if word in text:
            return val
    return None


def try_timer_command(text):
    if "دقیقه دیگه" not in text and "دقیقه بعد" not in text:
        return False
    minutes = _parse_minutes(text)
    if not minutes:
        return False
    msg = ""
    for kw in ["یادم بنداز", "یادآوری کن"]:
        if kw in text:
            msg = text.split(kw, 1)[1].strip()
            break

    def worker():
        time.sleep(minutes * 60)
        if msg:
            speak_dynamic(f"قربان، {minutes} دقیقه گذشت، یادت باشه {msg}.")
        else:
            speak_dynamic(f"قربان، {minutes} دقیقه‌ای که خواستید گذشت.")
        log_event(f"REMINDER fired ({minutes}min)")

    threading.Thread(target=worker, daemon=True).start()
    log_event(f"REMINDER set ({minutes}min)")
    speak_dynamic(f"باشه قربان، {minutes} دقیقه دیگه بهتون یادآوری می‌کنم.")
    return True


# ============================================================
# گزارش‌های زنده (وضعیت/ساعت/سیستم/آب‌وهوا/اخبار)
# ============================================================

def _status_report_text():
    with STATE.lock:
        face = STATE.face_present
        yaw, pitch, roll = STATE.yaw, STATE.pitch, STATE.roll
    if not face:
        return "قربان، در حال حاضر چهره‌ای رو ردیابی نمی‌کنم."
    tilt = "صاف" if abs(roll) < ROLL_TILT_THRESHOLD else "کج"
    if abs(yaw) < GAZE_YAW_MAX:
        direction = "مستقیم رو به دوربین"
    elif yaw > 0:
        direction = "چرخیده به سمت راست"
    else:
        direction = "چرخیده به سمت چپ"
    return f"قربان، در حال ردیابی چهره‌تونم. سرتون {tilt}ه و {direction}."


def _time_report_text():
    now = datetime.datetime.now()
    return f"ساعت الان {now.hour} و {now.minute} دقیقه‌ست قربان."


def _elapsed_report_text():
    elapsed_min = int((time.time() - APP_START_TIME) // 60)
    if elapsed_min <= 0:
        return "همین الان شروع کردیم قربان."
    return f"{elapsed_min} دقیقه از شروع کار می‌گذره قربان."


def _system_report_text():
    with STATE.lock:
        cpu = STATE.cpu_percent
        ram = STATE.ram_percent
        batt = STATE.battery_percent
    text = f"پردازنده {cpu:.0f} درصد در حال استفاده‌ست و رم {ram:.0f} درصد قربان."
    if batt is not None:
        text += f" باتری هم {batt:.0f} درصده."
    return text


def _weather_report_text():
    with STATE.lock:
        temp = STATE.weather_temp
        loc = STATE.location_name
    if temp is None:
        return "قربان، هنوز به اطلاعات آب‌وهوا دسترسی پیدا نکردم."
    loc_part = f" در {loc}" if loc else ""
    return f"دمای هوا{loc_part} الان {temp} درجه‌ست قربان."


def _news_report_text():
    try:
        with urllib.request.urlopen(NEWS_RSS_URL, timeout=6) as r:
            raw = r.read()
        import xml.etree.ElementTree as ET
        root = ET.fromstring(raw)
        titles = [item.findtext("title") for item in root.iter("item")]
        titles = [t.strip() for t in titles if t and t.strip()][:3]
        if not titles:
            return "قربان، الان خبری پیدا نکردم."
        return "چند تا از تیتر اخبار: " + "؛ ".join(titles)
    except Exception as e:
        print(f"[خطا در دریافت اخبار] {e}")
        return "قربان، الان به فید خبری دسترسی ندارم."


def _mute_action():
    with STATE.lock:
        STATE.audio_muted = True
    speak_dynamic("باشه قربان، رویدادهای خودکار رو ساکت می‌کنم.")


def _unmute_action():
    with STATE.lock:
        STATE.audio_muted = False
    speak_dynamic("باشه قربان، دوباره فعال شدم.")


def _quit_action():
    speak_dynamic("در حال خاموش شدن قربان.")
    time.sleep(1.5)
    STATE.running = False
    pygame.event.post(pygame.event.Event(pygame.QUIT))


# ============================================================
# (اختیاری) فال‌بک به Claude برای دستورهای آزاد
# ============================================================

def ask_claude(user_text):
    """اگه ANTHROPIC_API_KEY ست شده باشه، دستورهایی که کلیدواژه‌ی ثابت ندارن
    رو با حافظه‌ی چند پیامِ آخر به Claude میده تا طبیعی جواب بده."""
    if not ANTHROPIC_API_KEY:
        return None
    with STATE.lock:
        history = list(STATE.chat_history)
    messages = history + [{"role": "user", "content": user_text}]
    body = json.dumps({
        "model": ANTHROPIC_MODEL,
        "max_tokens": 300,
        "system": (
            "تو جارویس هستی، یک دستیار صوتی فارسی‌زبان که کاربر رو «قربان» صدا می‌زنه. "
            "خیلی مختصر و طبیعی جواب بده (حداکثر ۲-۳ جمله)، چون جوابت با صدا خونده میشه."
        ),
        "messages": messages,
    }).encode("utf-8")
    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages",
        data=body,
        headers={
            "content-type": "application/json",
            "x-api-key": ANTHROPIC_API_KEY,
            "anthropic-version": "2023-06-01",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            data = json.loads(r.read().decode())
        parts = [b.get("text", "") for b in data.get("content", []) if b.get("type") == "text"]
        reply = "".join(parts).strip()
        if not reply:
            return None
        with STATE.lock:
            STATE.chat_history.append({"role": "user", "content": user_text})
            STATE.chat_history.append({"role": "assistant", "content": reply})
            STATE.chat_history = STATE.chat_history[-(CHAT_HISTORY_MAX_TURNS * 2):]
        return reply
    except Exception as e:
        print(f"[خطا در تماس با Claude] {e}")
        return None


# ------------------------------------------------------------
# لیست کامل دستورهای صوتی
# ------------------------------------------------------------
VOICE_COMMANDS = [
    {"name": "GREETING", "keywords": ["سلام"],
     "lines": ["سلام قربان.", "در خدمتم قربان."]},
    {"name": "STATUS", "keywords": ["وضعیت", "گزارش"], "dynamic": _status_report_text},
    {"name": "TIME", "keywords": ["ساعت", "زمان چند"], "dynamic": _time_report_text},
    {"name": "ELAPSED", "keywords": ["چقدر گذشته", "چند دقیقه", "چقدره از"], "dynamic": _elapsed_report_text},
    {"name": "SYSTEM_REPORT", "keywords": ["سیستم چطوره", "وضعیت سیستم", "سی پی یو", "پردازنده"],
     "dynamic": _system_report_text},
    {"name": "WEATHER", "keywords": ["هوا چطوره", "آب و هوا", "آب‌وهوا", "دمای هوا"],
     "dynamic": _weather_report_text},
    {"name": "NEWS", "keywords": ["اخبار رو بگو", "خبر جدید", "اخبار چیه", "اخبار امروز"],
     "dynamic": _news_report_text},

    {"name": "OPEN_GOOGLE", "keywords": ["گوگل رو باز کن", "باز کن گوگل", "گوگل باز کن"],
     "action": _open_google_action},
    {"name": "OPEN_MYSITE", "keywords": ["سایت من رو باز کن", "سایت خودم رو باز کن",
                                          "سایتم رو باز کن", "باز کن سایتم"],
     "action": _open_mysite_action},
    {"name": "OPEN_YOUTUBE", "keywords": ["یوتیوب رو باز کن", "یوتیوب باز کن"],
     "action": _open_youtube_action},
    {"name": "OPEN_GMAIL", "keywords": ["جیمیل رو باز کن", "ایمیل رو باز کن"],
     "action": _open_gmail_action},
    {"name": "OPEN_NOTEPAD", "keywords": ["نوت‌پد رو باز کن", "نوت پد رو باز کن", "نوت پد باز کن"],
     "action": _open_notepad_action},
    {"name": "OPEN_CALC", "keywords": ["ماشین‌حساب رو باز کن", "ماشین حساب رو باز کن", "ماشین حساب باز کن"],
     "action": _open_calc_action},
    {"name": "OPEN_EXPLORER", "keywords": ["فایل اکسپلورر رو باز کن", "اکسپلورر رو باز کن"],
     "action": _open_explorer_action},

    {"name": "MUSIC_PLAY", "keywords": ["آهنگ پخش کن", "یه آهنگ بذار", "موزیک پخش کن"],
     "action": MUSIC_PLAYER.play_random},
    {"name": "MUSIC_NEXT", "keywords": ["آهنگ بعدی", "بعدی رو پخش کن"], "action": MUSIC_PLAYER.next_track},
    {"name": "MUSIC_PREV", "keywords": ["آهنگ قبلی"], "action": MUSIC_PLAYER.prev_track},
    {"name": "MUSIC_STOP", "keywords": ["آهنگ رو قطع کن", "موزیک رو قطع کن", "آهنگ رو متوقف کن"],
     "action": MUSIC_PLAYER.stop},
    {"name": "MUSIC_PAUSE", "keywords": ["آهنگ رو مکث کن", "آهنگ رو پاز کن"], "action": MUSIC_PLAYER.pause},
    {"name": "MUSIC_RESUME", "keywords": ["ادامه بده به آهنگ", "آهنگ رو ادامه بده"], "action": MUSIC_PLAYER.resume},

    {"name": "VOLUME_UP", "keywords": ["صدای سیستم رو زیاد کن", "صدا رو زیاد کن"], "action": _volume_up_action},
    {"name": "VOLUME_DOWN", "keywords": ["صدای سیستم رو کم کن", "صدا رو کم کن"], "action": _volume_down_action},
    {"name": "VOLUME_MUTE", "keywords": ["صدای سیستم رو قطع کن", "صدای سیستم رو ببند"],
     "action": _volume_mute_action},

    {"name": "SCREENSHOT", "keywords": ["اسکرین شات بگیر", "اسکرین‌شات بگیر", "یه عکس از صفحه بگیر"],
     "action": _screenshot_action},

    {"name": "SHUTDOWN", "keywords": ["خاموش کن سیستم رو", "سیستم رو خاموش کن", "کامپیوتر رو خاموش کن"],
     "action": _shutdown_action},
    {"name": "RESTART", "keywords": ["سیستم رو ری استارت کن", "کامپیوتر رو ری استارت کن", "ری استارت کن"],
     "action": _restart_action},
    {"name": "SLEEP", "keywords": ["سیستم رو بخوابون", "کامپیوتر رو بخوابون"], "action": _sleep_action},

    {"name": "MUTE", "keywords": ["ساکت شو", "ساکت باش", "بی‌صدا شو"], "action": _mute_action},
    {"name": "UNMUTE", "keywords": ["فعال شو", "صحبت کن", "صدا رو بیار"], "action": _unmute_action},
    {"name": "QUIT_APP", "keywords": ["برنامه رو ببند", "جارویس رو ببند", "خروج از برنامه"], "action": _quit_action},
]

# پوشه‌ها/درایوها هم به‌صورت خودکار به لیست دستورها اضافه میشن
for _alias, _path in FOLDER_ALIASES.items():
    VOICE_COMMANDS.append({
        "name": f"OPEN_FOLDER_{_alias}",
        "keywords": [f"{_alias} رو باز کن", f"{_alias} را باز کن"],
        "action": _make_folder_action(_alias, _path),
    })

STATIC_VOICE_LINES = list(WAKE_ACK_LINES) + list(UNKNOWN_COMMAND_LINES)
for _cmd in VOICE_COMMANDS:
    if "lines" in _cmd:
        STATIC_VOICE_LINES.extend(_cmd["lines"])


def match_voice_command(text):
    for cmd in VOICE_COMMANDS:
        for kw in cmd["keywords"]:
            if kw in text:
                return cmd
    return None


def dispatch_voice_command(cmd):
    log_event(cmd["name"])
    if "action" in cmd:
        cmd["action"]()
    elif "dynamic" in cmd:
        speak_dynamic(cmd["dynamic"]())
    elif "lines" in cmd:
        play_cached(random.choice(cmd["lines"]))


def handle_recognized_command_text(text):
    """ترتیب چک‌ها: سرچ گوگل -> تایمر -> کلیدواژه‌های ثابت -> (اختیاری) Claude."""
    if try_search_command(text):
        return True
    if try_timer_command(text):
        return True
    cmd = match_voice_command(text)
    if cmd:
        dispatch_voice_command(cmd)
        return True
    reply = ask_claude(text)
    if reply:
        log_event("CLAUDE_REPLY")
        speak_dynamic(reply)
        return True
    return False


class EventManager:
    """تشخیص لبه (edge-triggered) + کول‌داون؛ هیچ رویدادی راجع به زاویه‌ی سر نیست."""

    def __init__(self):
        self.last_fired = {name: 0.0 for name in EVENTS}
        self.system_ready_fired = False
        self.was_tracking = False
        self.face_lost_since = None
        self.eyes_closed_since = None

    def try_fire(self, name):
        now = time.time()
        cfg = EVENTS[name]
        if now - self.last_fired[name] < cfg["cooldown"]:
            return False
        self.last_fired[name] = now
        handle_event(name)
        return True

    def update(self, face_present, face_count, yaw, pitch, roll, area_ratio, ear):
        now = time.time()

        if face_present and not self.system_ready_fired:
            self.system_ready_fired = True
            self.try_fire("SYSTEM_READY")

        if face_present:
            if self.face_lost_since is not None and not self.was_tracking:
                self.try_fire("TRACKING_LOCKED")
            self.was_tracking = True
            self.face_lost_since = None
        else:
            if self.face_lost_since is None:
                self.face_lost_since = now
            elif (now - self.face_lost_since) > TRACKING_LOST_SECONDS and self.was_tracking:
                self.try_fire("TRACKING_LOST")
                self.was_tracking = False

        if not face_present:
            self.eyes_closed_since = None
            return

        if face_count >= 2:
            self.try_fire("INTRUDER")

        if ear < EAR_CLOSED_THRESHOLD:
            if self.eyes_closed_since is None:
                self.eyes_closed_since = now
            elif (now - self.eyes_closed_since) > FATIGUE_CLOSED_SECONDS:
                self.try_fire("FATIGUE")
        else:
            self.eyes_closed_since = None

        self.try_fire("IDLE_STATUS")


# ============================================================
# کمکی‌های هندسی: زاویه‌ی سر و EAR
# ============================================================

def rotation_matrix_to_euler(R):
    sy = math.sqrt(R[0, 0] ** 2 + R[1, 0] ** 2)
    singular = sy < 1e-6
    if not singular:
        pitch = math.atan2(-R[2, 0], sy)
        yaw = math.atan2(R[1, 0], R[0, 0])
        roll = math.atan2(R[2, 1], R[2, 2])
    else:
        pitch = math.atan2(-R[2, 0], sy)
        yaw = 0.0
        roll = math.atan2(-R[1, 2], R[1, 1])
    return math.degrees(yaw), math.degrees(pitch), math.degrees(roll)


def _euclid(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])


def eye_aspect_ratio(landmarks, indices, w, h):
    pts = [(landmarks[i].x * w, landmarks[i].y * h) for i in indices]
    p1, p2, p3, p4, p5, p6 = pts
    vert = _euclid(p2, p6) + _euclid(p3, p5)
    horiz = _euclid(p1, p4) * 2.0
    if horiz == 0:
        return 1.0
    return vert / horiz


# ============================================================
# ترد دوربین + MediaPipe FaceLandmarker
# ============================================================

def download_model_if_needed():
    if os.path.exists(MODEL_PATH):
        return True
    os.makedirs(MODEL_DIR, exist_ok=True)
    try:
        print("[در حال دانلود مدل FaceLandmarker، فقط یک بار...]")
        urllib.request.urlretrieve(MODEL_URL, MODEL_PATH)
        return True
    except Exception as e:
        print(f"[خطا در دانلود مدل — دوربین غیرفعال می‌مونه] {e}")
        return False


def camera_worker():
    if not download_model_if_needed():
        return

    base_options = mp_python.BaseOptions(model_asset_path=MODEL_PATH)
    options = mp_vision.FaceLandmarkerOptions(
        base_options=base_options,
        running_mode=mp_vision.RunningMode.VIDEO,
        num_faces=2,
        output_facial_transformation_matrixes=True,
        min_face_detection_confidence=0.5,
        min_tracking_confidence=0.5,
    )
    landmarker = mp_vision.FaceLandmarker.create_from_options(options)

    backend = cv2.CAP_DSHOW if os.name == "nt" else 0
    cap = cv2.VideoCapture(CAMERA_INDEX, backend)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)

    manager = EventManager()
    start = time.time()
    timer5_fired = False

    while STATE.running:
        ok, frame = cap.read()
        if not ok:
            time.sleep(0.05)
            continue

        frame = cv2.flip(frame, 1)
        h, w = frame.shape[:2]
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
        timestamp_ms = int((time.time() - start) * 1000)

        try:
            result = landmarker.detect_for_video(mp_image, timestamp_ms)
        except Exception:
            result = None

        face_present = bool(result and result.face_landmarks)
        face_count = len(result.face_landmarks) if result else 0
        yaw = pitch = roll = 0.0
        area_ratio = 0.0
        ear = 1.0

        if face_present:
            lm = result.face_landmarks[0]
            xs = [p.x for p in lm]
            ys = [p.y for p in lm]
            area_ratio = (max(xs) - min(xs)) * (max(ys) - min(ys))

            if result.facial_transformation_matrixes:
                mat = np.array(result.facial_transformation_matrixes[0]).reshape(4, 4)
                yaw, pitch, roll = rotation_matrix_to_euler(mat[:3, :3])

            left_ear = eye_aspect_ratio(lm, LEFT_EYE, w, h)
            right_ear = eye_aspect_ratio(lm, RIGHT_EYE, w, h)
            ear = (left_ear + right_ear) / 2.0

        with STATE.lock:
            STATE.face_present = face_present
            STATE.face_count = face_count
            STATE.yaw, STATE.pitch, STATE.roll = yaw, pitch, roll
            STATE.face_area_ratio = area_ratio
            STATE.ear = ear

        manager.update(face_present, face_count, yaw, pitch, roll, area_ratio, ear)

        if not timer5_fired and (time.time() - start) > 300:
            timer5_fired = True
            manager.try_fire("TIMER_5MIN")

        time.sleep(0.01)

    cap.release()
    landmarker.close()


# ============================================================
# ترد صدا — Vosk (آفلاین) + wake-word «جارویس» + تاییدهای صوتی
# ============================================================

def download_vosk_model_if_needed():
    if os.path.isdir(VOSK_MODEL_DIR) and os.listdir(VOSK_MODEL_DIR):
        return True
    os.makedirs(MODEL_DIR, exist_ok=True)
    zip_path = os.path.join(MODEL_DIR, f"{VOSK_MODEL_NAME}.zip")
    try:
        print("[در حال دانلود مدل فارسی Vosk، فقط یک بار...]")
        urllib.request.urlretrieve(VOSK_MODEL_URL, zip_path)
        with zipfile.ZipFile(zip_path, "r") as zf:
            zf.extractall(MODEL_DIR)
        os.remove(zip_path)
        return True
    except Exception as e:
        print(f"[خطا در دانلود مدل صوتی — ماژول صدا غیرفعال می‌مونه] {e}")
        return False


def _contains_wake_word(text):
    for w in WAKE_WORDS:
        if w in text:
            return text.split(w, 1)
    return None


def voice_worker():
    if not download_vosk_model_if_needed():
        return

    try:
        model = vosk.Model(VOSK_MODEL_DIR)
    except Exception as e:
        print(f"[خطا در بارگذاری مدل صوتی] {e}")
        return

    audio_q = queue.Queue()

    def _audio_callback(indata, frames, time_info, status):
        audio_q.put(bytes(indata))

    recognizer = vosk.KaldiRecognizer(model, SAMPLE_RATE)
    awaiting_since = None

    try:
        stream = sd.RawInputStream(
            samplerate=SAMPLE_RATE, blocksize=8000, dtype="int16",
            channels=1, callback=_audio_callback,
        )
    except Exception as e:
        print(f"[خطا در باز کردن میکروفون] {e}")
        return

    with stream:
        while STATE.running:
            with STATE.lock:
                currently_speaking = STATE.speaking

            if currently_speaking:
                while not audio_q.empty():
                    audio_q.get_nowait()
                time.sleep(0.1)
                continue

            try:
                data = audio_q.get(timeout=0.2)
            except queue.Empty:
                if awaiting_since and (time.time() - awaiting_since) > COMMAND_TIMEOUT:
                    awaiting_since = None
                    with STATE.lock:
                        STATE.awaiting_command = False
                with STATE.lock:
                    pending = STATE.pending_confirm_action
                    pending_since = STATE.pending_confirm_since
                if pending and (time.time() - pending_since) > CONFIRM_TIMEOUT:
                    with STATE.lock:
                        STATE.pending_confirm_action = None
                continue

            if not recognizer.AcceptWaveform(data):
                continue

            result = json.loads(recognizer.Result())
            text = (result.get("text") or "").strip()
            if not text:
                continue

            with STATE.lock:
                STATE.last_heard_text = text

            # ۱) اگه منتظر تاییدِ یه اقدام حساس (خاموش/ری‌استارت/خواب) بودیم
            with STATE.lock:
                pending = STATE.pending_confirm_action
                pending_since = STATE.pending_confirm_since
            if pending and (time.time() - pending_since) < CONFIRM_TIMEOUT:
                if any(w in text for w in CONFIRM_YES_WORDS):
                    with STATE.lock:
                        STATE.pending_confirm_action = None
                    action_fn = PENDING_CONFIRM_ACTIONS.get(pending)
                    if action_fn:
                        action_fn()
                    while not audio_q.empty():
                        audio_q.get_nowait()
                    continue
                if any(w in text for w in CONFIRM_NO_WORDS):
                    with STATE.lock:
                        STATE.pending_confirm_action = None
                    speak_dynamic("باشه قربان، انجامش نمیدم.")
                    while not audio_q.empty():
                        audio_q.get_nowait()
                    continue

            # ۲) روال عادی: wake-word یا ادامه‌ی دستور
            wake_split = _contains_wake_word(text)

            if wake_split is not None:
                _, after = wake_split
                after = after.strip()
                if after:
                    awaiting_since = None
                    with STATE.lock:
                        STATE.awaiting_command = False
                    if not handle_recognized_command_text(after):
                        play_cached(random.choice(WAKE_ACK_LINES))
                else:
                    play_cached(random.choice(WAKE_ACK_LINES))
                    awaiting_since = time.time()
                    with STATE.lock:
                        STATE.awaiting_command = True
                while not audio_q.empty():
                    audio_q.get_nowait()

            elif awaiting_since and (time.time() - awaiting_since) < COMMAND_TIMEOUT:
                awaiting_since = None
                with STATE.lock:
                    STATE.awaiting_command = False
                if not handle_recognized_command_text(text):
                    play_cached(random.choice(UNKNOWN_COMMAND_LINES))
                while not audio_q.empty():
                    audio_q.get_nowait()

            # نه ویک‌ورد بود نه منتظر دستور -> نادیده گرفته میشه


# ============================================================
# ترد آمار سیستم (CPU/RAM/باتری/شبکه)
# ============================================================

def system_stats_worker():
    last_net = None
    last_time = time.time()
    while STATE.running:
        try:
            cpu = psutil.cpu_percent(interval=SYSTEM_STATS_INTERVAL)
            ram = psutil.virtual_memory().percent
            batt = None
            try:
                b = psutil.sensors_battery()
                if b is not None:
                    batt = b.percent
            except Exception:
                pass

            now_net = psutil.net_io_counters()
            now_time = time.time()
            recv_kbps = 0.0
            if last_net is not None:
                dt = max(0.001, now_time - last_time)
                recv_kbps = max(0.0, (now_net.bytes_recv - last_net.bytes_recv) / 1024.0 / dt)
            last_net, last_time = now_net, now_time

            with STATE.lock:
                STATE.cpu_percent = cpu
                STATE.ram_percent = ram
                STATE.battery_percent = batt
                STATE.net_history.append(recv_kbps)
                STATE.net_history = STATE.net_history[-40:]
        except Exception:
            time.sleep(SYSTEM_STATS_INTERVAL)


# ============================================================
# ترد آب‌وهوا (open-meteo + ip-api، بدون کلید)
# ============================================================

def weather_worker():
    while STATE.running:
        try:
            with urllib.request.urlopen("http://ip-api.com/json/", timeout=5) as r:
                loc = json.loads(r.read().decode())
            lat, lon = loc.get("lat"), loc.get("lon")
            city = loc.get("city", "")
            if lat is not None and lon is not None:
                url = (f"https://api.open-meteo.com/v1/forecast?"
                       f"latitude={lat}&longitude={lon}&current_weather=true")
                with urllib.request.urlopen(url, timeout=5) as r2:
                    wdata = json.loads(r2.read().decode())
                cw = wdata.get("current_weather", {})
                temp = cw.get("temperature")
                with STATE.lock:
                    STATE.weather_temp = temp
                    STATE.location_name = city
        except Exception as e:
            print(f"[آب‌وهوا در دسترس نیست] {e}")
        for _ in range(int(WEATHER_UPDATE_INTERVAL)):
            if not STATE.running:
                break
            time.sleep(1)


# ============================================================
# رندر — کره‌ی ذرات هولوگرافیک
# ============================================================

def fibonacci_sphere(samples, radius):
    points = []
    phi = math.pi * (3.0 - math.sqrt(5.0))
    for i in range(samples):
        y = 1 - (i / float(samples - 1)) * 2
        r = math.sqrt(1 - y * y)
        theta = phi * i
        x = math.cos(theta) * r
        z = math.sin(theta) * r
        points.append((x * radius, y * radius, z * radius))
    return points


SPHERE_POINTS = fibonacci_sphere(160, 1.0)
_pulse_energy = 0.0


def rotate_point(p, ax, ay):
    x, y, z = p
    cosA, sinA = math.cos(ay), math.sin(ay)
    x, z = x * cosA - z * sinA, x * sinA + z * cosA
    cosB, sinB = math.cos(ax), math.sin(ax)
    y, z = y * cosB - z * sinB, y * sinB + z * cosB
    return x, y, z


def draw_orb(screen, t, cx, cy, base_scale, speaking):
    global _pulse_energy

    if speaking:
        _pulse_energy += random.uniform(-0.15, 0.2)
        _pulse_energy = max(0.2, min(1.5, _pulse_energy))
        color = ORB_COLOR_SPEAK
        rot_speed = 1.6
    else:
        _pulse_energy = 0.5 + 0.5 * math.sin(t * 1.1)
        color = ORB_COLOR_IDLE
        rot_speed = 0.5

    radius = base_scale * (0.75 + _pulse_energy * 0.25)
    ax = t * 0.3
    ay = t * rot_speed

    projected = []
    for p in SPHERE_POINTS:
        x, y, z = rotate_point(p, ax, ay)
        scale = radius
        factor = 260 / (260 - z * scale)
        px = cx + x * scale * factor
        py = cy + y * scale * factor
        projected.append((z, px, py, factor))

    projected.sort(key=lambda p: p[0])

    glow = pygame.Surface(screen.get_size(), pygame.SRCALPHA)
    for depth, px, py, factor in projected:
        brightness = (depth + 1) / 2
        size = max(1, int(2 + brightness * 4))
        alpha = int(60 + brightness * 195)
        c = (*color, alpha)
        pygame.draw.circle(glow, c, (int(px), int(py)), size)
    screen.blit(glow, (0, 0))

    core_glow = pygame.Surface(screen.get_size(), pygame.SRCALPHA)
    for i in range(8, 0, -1):
        a = int(10 * (9 - i))
        r = int(radius * 30 * (i / 8))
        pygame.draw.circle(core_glow, (*color, a), (cx, cy), r)
    screen.blit(core_glow, (0, 0))
    pygame.draw.circle(screen, (255, 255, 255), (cx, cy), int(radius * 12))

    for i, tilt in enumerate([0.25, -0.35, 0.15]):
        ring_w = int(radius * (280 + i * 40))
        ring_h = int(ring_w * abs(math.sin(t * 0.4 + i)) * 0.25 + ring_w * 0.08)
        rect = pygame.Rect(0, 0, ring_w, ring_h)
        rect.center = (cx, cy)
        ring_surf = pygame.Surface(screen.get_size(), pygame.SRCALPHA)
        pygame.draw.ellipse(ring_surf, (*color, 70), rect, width=1)
        screen.blit(ring_surf, (0, 0))


def draw_hud_ticks(screen, w, h, t):
    color = (0, 150, 200, 120)
    margin = 40
    length = 70
    surf = pygame.Surface((w, h), pygame.SRCALPHA)
    corners = [(margin, margin), (w - margin, margin), (margin, h - margin), (w - margin, h - margin)]
    for cxp, cyp in corners:
        pygame.draw.line(surf, color, (cxp - length, cyp), (cxp, cyp), 2)
        pygame.draw.line(surf, color, (cxp, cyp - length), (cxp, cyp), 2)
    screen.blit(surf, (0, 0))


def draw_subtitle(screen, w, h, font, subtitle):
    if not subtitle:
        return
    text = reshape_farsi(subtitle)
    label = font.render(text, True, (220, 245, 255))
    bar = pygame.Surface((w, 70), pygame.SRCALPHA)
    bar.fill((0, 20, 30, 160))
    screen.blit(bar, (0, h - 90))
    rect = label.get_rect(center=(w // 2, h - 55))
    screen.blit(label, rect)


def draw_loading(screen, w, h, font, cache_progress):
    done, total = cache_progress
    text = f"در حال آماده‌سازی صداها... {done}/{total}"
    label = font.render(reshape_farsi(text), True, (0, 200, 255))
    rect = label.get_rect(center=(w // 2, h // 2 + 120))
    screen.blit(label, rect)


def draw_ring_gauge(screen, cx, cy, radius, percent, color, font_val, font_label, label, value_text):
    pygame.draw.circle(screen, GAUGE_BG, (cx, cy), radius, width=6)
    percent = max(0.0, min(100.0, percent))
    start_deg = -90
    end_deg = -90 + (percent / 100.0) * 360
    rect = pygame.Rect(cx - radius, cy - radius, radius * 2, radius * 2)
    try:
        pygame.draw.arc(screen, color, rect, math.radians(-end_deg), math.radians(-start_deg), 6)
    except Exception:
        pass
    val_label = font_val.render(value_text, True, HUD_WHITE)
    screen.blit(val_label, val_label.get_rect(center=(cx, cy - 4)))
    name_label = font_label.render(reshape_farsi(label), True, HUD_CYAN_DIM)
    screen.blit(name_label, name_label.get_rect(center=(cx, cy + 22)))


def draw_system_gauges(screen, x, y, font_val, font_label):
    with STATE.lock:
        cpu = STATE.cpu_percent
        ram = STATE.ram_percent
        batt = STATE.battery_percent

    radius = 44
    gap = 110
    draw_ring_gauge(screen, x, y, radius, cpu, HUD_CYAN, font_val, font_label, "CPU", f"{cpu:.0f}%")
    draw_ring_gauge(screen, x + gap, y, radius, ram, HUD_OK, font_val, font_label, "RAM", f"{ram:.0f}%")
    if batt is not None:
        color = HUD_WARN if batt < 20 else HUD_CYAN
        draw_ring_gauge(screen, x + gap * 2, y, radius, batt, color, font_val, font_label, "BATT", f"{batt:.0f}%")


def draw_network_sparkline(screen, x, y, w_box, h_box, font_label):
    with STATE.lock:
        history = list(STATE.net_history)
    label = font_label.render("NET (KB/s)", True, HUD_CYAN_DIM)
    screen.blit(label, (x, y - 18))
    pygame.draw.rect(screen, GAUGE_BG, (x, y, w_box, h_box), width=1)
    if len(history) < 2:
        return
    maxv = max(history) or 1.0
    n = len(history)
    points = []
    for i, v in enumerate(history):
        px = x + int(i / (n - 1) * w_box)
        py = y + h_box - int(min(v / maxv, 1.0) * h_box)
        points.append((px, py))
    if len(points) >= 2:
        pygame.draw.lines(screen, HUD_CYAN, False, points, 2)


def draw_clock_panel(screen, x, y, font_big, font_small):
    now = datetime.datetime.now()
    time_str = now.strftime("%H:%M")
    date_str = now.strftime("%Y-%m-%d")
    t_label = font_big.render(time_str, True, HUD_CYAN)
    screen.blit(t_label, t_label.get_rect(midtop=(x, y)))
    d_label = font_small.render(date_str, True, HUD_CYAN_DIM)
    screen.blit(d_label, d_label.get_rect(midtop=(x, y + 42)))


def draw_weather_panel(screen, x, y, font, font_small):
    with STATE.lock:
        temp = STATE.weather_temp
        loc = STATE.location_name
    if temp is None:
        text = "آب‌وهوا: در حال دریافت..."
        label = font_small.render(reshape_farsi(text), True, HUD_CYAN_DIM)
        screen.blit(label, label.get_rect(topright=(x, y)))
        return
    temp_label = font.render(f"{temp:.0f}°C", True, HUD_CYAN)
    screen.blit(temp_label, temp_label.get_rect(topright=(x, y)))
    if loc:
        loc_label = font_small.render(reshape_farsi(loc), True, HUD_CYAN_DIM)
        screen.blit(loc_label, loc_label.get_rect(topright=(x, y + 30)))


def draw_log_panel(screen, x, y, font):
    with STATE.lock:
        entries = list(STATE.event_log)
    yy = y
    for ts, text in entries[-6:]:
        line = f"[{ts}] {text}"
        label = font.render(line, True, HUD_CYAN_FAINT)
        screen.blit(label, (x, yy))
        yy += 20


BUTTON_RADIUS = 22


def bottom_button_layout(w, h):
    keys = list(MANUAL_TEST_KEYS.items())
    n = len(keys)
    spacing = 60
    total_width = spacing * (n - 1)
    start_x = w // 2 - total_width // 2
    y = h - 50
    layout = []
    for i, (key, name) in enumerate(keys):
        x = start_x + i * spacing
        layout.append((x, y, name))
    return layout


def draw_bottom_buttons(screen, w, h, font):
    layout = bottom_button_layout(w, h)
    for x, y, name in layout:
        pygame.draw.circle(screen, GAUGE_BG, (x, y), BUTTON_RADIUS)
        pygame.draw.circle(screen, HUD_CYAN_DIM, (x, y), BUTTON_RADIUS, width=2)
        label = font.render(name[:1], True, HUD_CYAN)
        screen.blit(label, label.get_rect(center=(x, y)))
    return layout


def draw_debug_hud(screen, font, face_present, face_count, yaw, pitch, roll,
                    area_ratio, ear, audio_muted, awaiting_command, last_heard):
    lines = [
        f"face: {'YES' if face_present else 'NO'}   count={face_count}",
        f"yaw={yaw:6.1f}   pitch={pitch:6.1f}   roll={roll:6.1f}",
        f"area={area_ratio:5.3f}   ear={ear:5.3f}",
        f"mic: {'MUTED' if audio_muted else 'live'}   "
        f"{'listening for command...' if awaiting_command else 'waiting for wake-word'}",
        f"heard: {last_heard}",
        "[D] debug  [M] mute  [0-4] manual test  [ESC] exit",
    ]
    y = 20
    for line in lines:
        label = font.render(line, True, (0, 200, 255))
        screen.blit(label, (20, y))
        y += 22


# ============================================================
# حلقه‌ی اصلی
# ============================================================

def main():
    pygame.init()
    pygame.mixer.init()
    pygame.mixer.set_num_channels(16)

    if FULLSCREEN:
        info = pygame.display.Info()
        w, h = info.current_w, info.current_h
        screen = pygame.display.set_mode((w, h), pygame.FULLSCREEN)
    else:
        w, h = 900, 700
        screen = pygame.display.set_mode((w, h))

    pygame.display.set_caption("J.A.R.V.I.S.")
    clock = pygame.time.Clock()

    try:
        font = pygame.font.SysFont("arial", 26)
        debug_font = pygame.font.SysFont("consolas", 18)
        hud_font_small = pygame.font.SysFont("consolas", 16)
        hud_font_val = pygame.font.SysFont("consolas", 18)
        hud_font_big = pygame.font.SysFont("consolas", 40)
    except Exception:
        font = pygame.font.Font(None, 26)
        debug_font = pygame.font.Font(None, 18)
        hud_font_small = pygame.font.Font(None, 16)
        hud_font_val = pygame.font.Font(None, 18)
        hud_font_big = pygame.font.Font(None, 40)

    STATE.running = True
    threading.Thread(target=build_cache, daemon=True).start()
    threading.Thread(target=camera_worker, daemon=True).start()
    threading.Thread(target=voice_worker, daemon=True).start()
    threading.Thread(target=system_stats_worker, daemon=True).start()
    threading.Thread(target=weather_worker, daemon=True).start()

    cx, cy = w // 2, h // 2
    base_scale = min(w, h) / 900.0 * 4.0

    show_debug = True
    button_layout = []
    start_time = time.time()
    running = True
    while running:
        t = time.time() - start_time

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    running = False
                elif event.key == pygame.K_d:
                    show_debug = not show_debug
                elif event.key == pygame.K_m:
                    with STATE.lock:
                        STATE.audio_muted = not STATE.audio_muted
                elif event.key in MANUAL_TEST_KEYS:
                    handle_event(MANUAL_TEST_KEYS[event.key])
            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                mx, my = event.pos
                for bx, by, name in button_layout:
                    if (mx - bx) ** 2 + (my - by) ** 2 <= BUTTON_RADIUS ** 2:
                        handle_event(name)
                        break

        with STATE.lock:
            speaking = STATE.speaking
            subtitle = STATE.current_subtitle
            cache_ready = STATE.cache_ready
            cache_progress = STATE.cache_progress
            face_present = STATE.face_present
            face_count = STATE.face_count
            yaw, pitch, roll = STATE.yaw, STATE.pitch, STATE.roll
            area_ratio = STATE.face_area_ratio
            ear = STATE.ear
            audio_muted = STATE.audio_muted
            awaiting_command = STATE.awaiting_command
            last_heard = STATE.last_heard_text

        screen.fill(BG_COLOR)
        draw_hud_ticks(screen, w, h, t)
        draw_orb(screen, t, cx, cy, base_scale, speaking)

        draw_system_gauges(screen, 110, 100, hud_font_val, hud_font_small)
        draw_network_sparkline(screen, 20, 190, 220, 50, hud_font_small)
        draw_clock_panel(screen, w // 2, 30, hud_font_big, hud_font_small)
        draw_weather_panel(screen, w - 60, 30, hud_font_val, hud_font_small)
        draw_log_panel(screen, 20, h - 190, hud_font_small)

        draw_subtitle(screen, w, h, font, subtitle)
        if not cache_ready:
            draw_loading(screen, w, h, font, cache_progress)

        button_layout = draw_bottom_buttons(screen, w, h, hud_font_small)

        if show_debug:
            draw_debug_hud(screen, debug_font, face_present, face_count,
                            yaw, pitch, roll, area_ratio, ear,
                            audio_muted, awaiting_command, last_heard)

        pygame.display.flip()
        clock.tick(FPS)

    STATE.running = False
    pygame.quit()
    time.sleep(0.3)
    shutil.rmtree(AUDIO_CACHE_DIR, ignore_errors=True)


if __name__ == "__main__":
    main()
