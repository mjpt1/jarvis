"""اقدامات سیستمی: باز کردن مسیر/برنامه، اسکرین‌شات، خاموش/ری‌استارت/خواب،
قفل، کنترل صدای سیستم، و کلیدهای رسانه.

اقدامات حساس (خاموش/ری‌استارت/خواب) از طریق تاییدِ دوطرفه (صوتی + روی صفحه) در
ماژول commands اجرا می‌شوند؛ این‌جا فقط پیاده‌سازیِ خودِ کار است.
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
import webbrowser

from .logging_setup import get_logger
from .paths import SCREENSHOT_DIR
from .state import STATE
from . import tts

log = get_logger("actions")

IS_WIN = os.name == "nt"
IS_MAC = sys.platform == "darwin"


def _run(cmd: list[str]) -> bool:
    try:
        subprocess.Popen(cmd, shell=False)
        return True
    except Exception as exc:
        log.warning("اجرای %s ناموفق بود: %s", cmd, exc)
        return False


def open_path(path: str) -> bool:
    try:
        if IS_WIN:
            os.startfile(path)  # type: ignore[attr-defined]
        elif IS_MAC:
            subprocess.run(["open", path], check=False)
        else:
            subprocess.run(["xdg-open", path], check=False)
        return True
    except Exception as exc:
        log.warning("باز کردن مسیر %s ناموفق بود: %s", path, exc)
        return False


def make_folder_action(alias: str, path: str, title: str):
    def action():
        is_drive = IS_WIN and len(path) <= 3
        if os.path.isdir(path) or is_drive:
            if open_path(path):
                tts.say(f"{alias} رو باز کردم {title}.")
                STATE.log(f"OPEN {alias}")
                return
        tts.say(f"{title}، مسیر «{alias}» رو پیدا نکردم.")
    return action


def make_app_action(win_cmd, mac_cmd, linux_cmd, label: str, title: str):
    def action():
        cmd = win_cmd if IS_WIN else (mac_cmd if IS_MAC else linux_cmd)
        if _run(cmd):
            tts.say(f"{label} رو باز کردم {title}.")
        else:
            tts.say(f"نتونستم {label} رو باز کنم {title}.")
    return action


def make_url_action(url: str, label: str, title: str):
    def action():
        webbrowser.open(url)
        tts.say(f"{label} رو باز کردم {title}.")
        STATE.log(f"OPEN {label}")
    return action


def google_search(query: str, title: str) -> None:
    import urllib.parse
    webbrowser.open("https://www.google.com/search?q=" + urllib.parse.quote(query))
    STATE.log(f"SEARCH {query}")
    tts.say(f"در حال جستجوی «{query}» تو گوگل {title}.")


def screenshot(title: str) -> None:
    try:
        from PIL import ImageGrab
        SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
        path = SCREENSHOT_DIR / f"shot_{int(time.time())}.png"
        ImageGrab.grab().save(path)
        STATE.log("SCREENSHOT")
        tts.say(f"اسکرین‌شات رو گرفتم و ذخیره کردم {title}.")
    except ImportError:
        tts.say(f"{title}، برای اسکرین‌شات باید کتابخونه‌ی Pillow نصب بشه.")
    except Exception as exc:
        log.warning("اسکرین‌شات ناموفق: %s", exc)
        tts.say(f"نتونستم اسکرین‌شات بگیرم {title}.")


# ---------------- اقدامات حساس ----------------

def do_shutdown() -> None:
    time.sleep(2)
    if IS_WIN:
        _run(["shutdown", "/s", "/t", "1"])
    elif IS_MAC:
        _run(["osascript", "-e", 'tell app "System Events" to shut down'])
    else:
        _run(["systemctl", "poweroff"])


def do_restart() -> None:
    time.sleep(2)
    if IS_WIN:
        _run(["shutdown", "/r", "/t", "1"])
    elif IS_MAC:
        _run(["osascript", "-e", 'tell app "System Events" to restart'])
    else:
        _run(["systemctl", "reboot"])


def do_sleep() -> None:
    time.sleep(1.5)
    if IS_WIN:
        _run(["rundll32.exe", "powrprof.dll,SetSuspendState", "0,1,0"])
    elif IS_MAC:
        _run(["pmset", "sleepnow"])
    else:
        _run(["systemctl", "suspend"])


def lock_screen(title: str) -> None:
    if IS_WIN:
        _run(["rundll32.exe", "user32.dll,LockWorkStation"])
    elif IS_MAC:
        _run(["pmset", "displaysleepnow"])
    else:
        _run(["loginctl", "lock-session"])
    tts.say(f"سیستم رو قفل کردم {title}.")


# ---------------- صدای سیستم (ویندوز) ----------------

def _win_volume_iface():
    from ctypes import cast, POINTER
    from comtypes import CLSCTX_ALL
    from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
    devices = AudioUtilities.GetSpeakers()
    interface = devices.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
    return cast(interface, POINTER(IAudioEndpointVolume))


def set_system_volume(title: str, delta=None, absolute=None) -> None:
    if not IS_WIN:
        tts.say(f"{title}، کنترل صدای سیستم فعلاً فقط تو ویندوز کار می‌کنه.")
        return
    try:
        vol = _win_volume_iface()
        cur = vol.GetMasterVolumeLevelScalar()
        new = absolute if absolute is not None else cur + (delta or 0)
        new = max(0.0, min(1.0, new))
        vol.SetMasterVolumeLevelScalar(new, None)
        tts.say(f"صدای سیستم رو گذاشتم روی {int(new * 100)} درصد {title}.")
    except ImportError:
        tts.say(f"{title}، برای کنترل صدا باید pycaw و comtypes نصب بشه.")
    except Exception as exc:
        log.warning("تنظیم صدا ناموفق: %s", exc)
        tts.say(f"نتونستم صدا رو تنظیم کنم {title}.")


# ---------------- کلیدهای رسانه ----------------

def media_key(vk_name: str) -> None:
    """شبیه‌سازی کلید رسانه روی ویندوز (play/pause/next/prev)."""
    if not IS_WIN:
        return
    import ctypes
    codes = {"playpause": 0xB3, "next": 0xB0, "prev": 0xB1, "stop": 0xB2}
    code = codes.get(vk_name)
    if code is None:
        return
    ctypes.windll.user32.keybd_event(code, 0, 0, 0)
    ctypes.windll.user32.keybd_event(code, 0, 2, 0)
