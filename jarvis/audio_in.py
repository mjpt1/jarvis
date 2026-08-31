"""ترد ورودی صدا: Vosk آفلاین + کلمه‌ی بیدارباش + تاییدهای صوتی + مقیاس صدا.

از partial results برای واکنش سریع به «جارویس» استفاده می‌کند و هنگام صحبتِ جارویس
ورودی را نادیده می‌گیرد تا صدای خودش را دستور نگیرد.
"""

from __future__ import annotations

import json
import math
import queue
import time

from .config import Config
from .logging_setup import get_logger
from .state import STATE
from . import tts
from .commands import CommandEngine, CONFIRM_NO, CONFIRM_YES
from .text_fa import fuzzy_contains, normalize

log = get_logger("audio")


def _rms_level(pcm_bytes: bytes) -> float:
    if not pcm_bytes:
        return 0.0
    import array
    samples = array.array("h")
    samples.frombytes(pcm_bytes[: len(pcm_bytes) // 2 * 2])
    if not samples:
        return 0.0
    mean_sq = sum(s * s for s in samples) / len(samples)
    return min(1.0, math.sqrt(mean_sq) / 8000.0)


def _contains_wake(text: str, wake_words) -> tuple[bool, str]:
    norm = normalize(text)
    for w in wake_words:
        wn = normalize(w)
        idx = norm.find(wn)
        if idx != -1:
            return True, norm[idx + len(wn):].strip()
    # فازی برای تک‌کلمه
    if any(fuzzy_contains(norm, w, 0.8) for w in wake_words):
        return True, ""
    return False, ""


def voice_worker(cfg: Config, engine: CommandEngine) -> None:
    try:
        import sounddevice as sd
        import vosk
        from .models import ensure_vosk_model
    except Exception as exc:
        log.warning("ماژول‌های صوتی در دسترس نیستند: %s", exc)
        return

    vosk.SetLogLevel(-1)
    try:
        model_dir = ensure_vosk_model(cfg.vosk_model_name)
    except Exception as exc:
        log.warning("مدل صوتی دانلود نشد — تشخیص گفتار غیرفعال: %s", exc)
        return

    try:
        model = vosk.Model(str(model_dir))
    except Exception as exc:
        log.warning("بارگذاری مدل صوتی ناموفق بود: %s", exc)
        return

    audio_q: queue.Queue[bytes] = queue.Queue()

    def _cb(indata, frames, time_info, status):  # noqa: ARG001
        audio_q.put(bytes(indata))

    recognizer = vosk.KaldiRecognizer(model, cfg.sample_rate)
    recognizer.SetWords(False)

    try:
        stream = sd.RawInputStream(samplerate=cfg.sample_rate, blocksize=8000,
                                   dtype="int16", channels=1, callback=_cb)
    except Exception as exc:
        log.warning("باز کردن میکروفون ناموفق بود: %s", exc)
        return

    with STATE.lock:
        STATE.voice_enabled = True
    log.info("تشخیص گفتار فعال شد — کلمه‌ی بیدارباش: %s", cfg.wake_words[0])

    awaiting_since = None

    def _drain():
        while not audio_q.empty():
            try:
                audio_q.get_nowait()
            except queue.Empty:
                break

    with stream:
        while STATE.running:
            with STATE.lock:
                speaking = STATE.speaking
            if speaking:
                _drain()
                time.sleep(0.1)
                continue

            try:
                data = audio_q.get(timeout=0.2)
            except queue.Empty:
                _expire_confirm(cfg)
                if awaiting_since and time.time() - awaiting_since > cfg.command_timeout:
                    awaiting_since = None
                    with STATE.lock:
                        STATE.awaiting_command = False
                continue

            with STATE.lock:
                STATE.mic_level = _rms_level(data)

            if not recognizer.AcceptWaveform(data):
                partial = json.loads(recognizer.PartialResult()).get("partial", "")
                with STATE.lock:
                    STATE.partial_text = partial
                continue

            with STATE.lock:
                STATE.partial_text = ""
            text = json.loads(recognizer.Result()).get("text", "").strip()
            if not text:
                continue
            with STATE.lock:
                STATE.last_heard_text = text

            # ۱) تاییدِ اقدام حساس
            with STATE.lock:
                pending = STATE.pending_confirm_action
                pending_since = STATE.pending_confirm_since
            if pending and time.time() - pending_since < cfg.confirm_timeout:
                norm = normalize(text)
                if any(w in norm for w in CONFIRM_YES):
                    with STATE.lock:
                        STATE.pending_confirm_action = None
                    engine.run_confirmed(pending)
                    _drain()
                    continue
                if any(w in norm for w in CONFIRM_NO):
                    with STATE.lock:
                        STATE.pending_confirm_action = None
                    import random
                    tts.say(random.choice(engine.confirm_cancelled))
                    _drain()
                    continue

            # ۲) کلمه‌ی بیدارباش یا ادامه‌ی دستور
            has_wake, after = _contains_wake(text, cfg.wake_words)
            import random
            if has_wake:
                if after:
                    awaiting_since = None
                    with STATE.lock:
                        STATE.awaiting_command = False
                    if not engine.handle(after):
                        tts.say_cached_only(random.choice(engine.wake_ack))
                else:
                    tts.say_cached_only(random.choice(engine.wake_ack))
                    awaiting_since = time.time()
                    with STATE.lock:
                        STATE.awaiting_command = True
                _drain()
            elif awaiting_since and time.time() - awaiting_since < cfg.command_timeout:
                awaiting_since = None
                with STATE.lock:
                    STATE.awaiting_command = False
                if not engine.handle(text):
                    tts.say(random.choice(engine.unknown_lines))
                _drain()
            # وگرنه: نادیده گرفته می‌شود

    with STATE.lock:
        STATE.voice_enabled = False


def _expire_confirm(cfg: Config) -> None:
    with STATE.lock:
        pending = STATE.pending_confirm_action
        since = STATE.pending_confirm_since
    if pending and time.time() - since > cfg.confirm_timeout:
        with STATE.lock:
            STATE.pending_confirm_action = None
