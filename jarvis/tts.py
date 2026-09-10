"""تبدیل متن به گفتار (edge-tts) با کش دائمی و «داکینگ» موزیک هنگام صحبت.

- خطوط ثابت یک بار ساخته و در ~/.jarvis/cache نگه داشته می‌شوند (بین اجراها).
- خطوط پویا هم کش می‌شوند (هش متن) تا تکرارها فوری پخش شوند.
- اگر اینترنت نبود و متن در کش نبود، بی‌صدا رد می‌شود (خطا نمی‌دهد).
"""

from __future__ import annotations

import asyncio
import hashlib
import threading
import time

from .logging_setup import get_logger
from .paths import CACHE_DIR, ensure_dirs
from .state import STATE

log = get_logger("tts")

try:
    import pygame
except Exception:  # pragma: no cover
    pygame = None

TTS_CHANNEL_ID = 7
_VOICE = "fa-IR-FaridNeural"
_lock = threading.Lock()


def configure(voice: str) -> None:
    global _VOICE
    _VOICE = voice


def _key(text: str) -> str:
    h = hashlib.sha1(f"{_VOICE}|{text}".encode()).hexdigest()[:16]
    return h


def _cache_path(text: str):
    ensure_dirs()
    return CACHE_DIR / f"tts_{_key(text)}.mp3"


async def _synth(text: str, path) -> bool:
    import edge_tts
    try:
        await edge_tts.Communicate(text, _VOICE).save(str(path))
        return path.exists() and path.stat().st_size > 0
    except Exception as exc:  # pragma: no cover - شبکه
        log.warning("ساخت صدا ناموفق بود: %s", exc)
        return False


def synth_to_cache(text: str) -> bool:
    """صدا را می‌سازد و کش می‌کند (اگر نبود). True یعنی فایل آماده است."""
    path = _cache_path(text)
    if path.exists() and path.stat().st_size > 0:
        return True
    try:
        return asyncio.run(_synth(text, path))
    except RuntimeError:  # حلقه‌ی رویداد فعال
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(_synth(text, path))
        finally:
            loop.close()


def prebuild(lines, progress_cb=None) -> None:
    lines = list(dict.fromkeys(l for l in lines if l))
    for i, line in enumerate(lines, 1):
        synth_to_cache(line)
        if progress_cb:
            progress_cb(i, len(lines))
    with STATE.lock:
        STATE.cache_ready = True
    log.info("کش صدا آماده شد (%d خط).", len(lines))


def _duck_music(duck: bool) -> None:
    if pygame is None:
        return
    try:
        pygame.mixer.music.set_volume(0.15 if duck else 0.8)
    except Exception:
        pass


def _play_file(path, subtitle: str) -> None:
    if pygame is None or not path or not str(path):
        return
    with STATE.lock:
        STATE.current_subtitle = subtitle
        STATE.speaking = True
    _duck_music(True)
    try:
        snd = pygame.mixer.Sound(str(path))
        envelope = _amplitude_envelope(snd)
        ch = pygame.mixer.Channel(TTS_CHANNEL_ID)
        length = max(0.05, snd.get_length())
        ch.play(snd)
        t0 = time.time()
        while ch.get_busy() and STATE.running:
            frac = (time.time() - t0) / length
            with STATE.lock:
                STATE.tts_level = _sample_envelope(envelope, frac)
            time.sleep(0.03)
    except Exception as exc:
        log.warning("پخش صدا ناموفق بود: %s", exc)
    finally:
        _duck_music(False)
        with STATE.lock:
            STATE.speaking = False
            STATE.current_subtitle = ""
            STATE.tts_level = 0.0


def _amplitude_envelope(snd, buckets: int = 240):
    """پاکتِ دامنه‌ی صدا (۰..۱) برای هدایتِ اکولایزر هنگام صحبتِ جارویس."""
    try:
        import numpy as np
        import pygame
        arr = pygame.sndarray.array(snd).astype("float32")
        if arr.ndim > 1:
            arr = arr.mean(axis=1)
        if arr.size == 0:
            return None
        arr = np.abs(arr) / 32768.0
        pad = (-arr.size) % buckets
        if pad:
            arr = np.concatenate([arr, np.zeros(pad, dtype="float32")])
        env = arr.reshape(buckets, -1).mean(axis=1)
        peak = float(env.max()) or 1.0
        return (env / peak).tolist()
    except Exception:
        return None


def _sample_envelope(env, frac: float) -> float:
    if not env:
        return 0.6
    i = max(0, min(len(env) - 1, int(frac * len(env))))
    return float(env[i])


def say(text: str, *, blocking: bool = False) -> None:
    """گفتنِ یک جمله (کش اگر بود، وگرنه ساخت زنده)."""
    if not text:
        return

    def worker():
        with _lock:
            path = _cache_path(text)
            if not (path.exists() and path.stat().st_size > 0):
                synth_to_cache(text)
            if path.exists() and path.stat().st_size > 0:
                _play_file(path, text)

    if blocking:
        worker()
    else:
        threading.Thread(target=worker, daemon=True).start()


def say_cached_only(text: str) -> None:
    """فقط اگر در کش هست پخش کن (برای مسیرهای حساس به تأخیر مثل پاسخ ویک‌ورد)."""
    path = _cache_path(text)
    if path.exists() and path.stat().st_size > 0:
        threading.Thread(target=_play_file, args=(path, text), daemon=True).start()
    else:
        say(text)
