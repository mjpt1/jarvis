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

    awaiting_since = None          # مهلت کوتاهِ «یک دستور» (حالت غیرمکالمه)
    convo = False                  # حالت مکالمه‌ی پیوسته
    last_activity = time.time()

    def _set_listen(flag: bool):
        with STATE.lock:
            STATE.awaiting_command = flag

    def _set_convo(flag: bool):
        nonlocal convo
        convo = flag
        with STATE.lock:
            STATE.conversation_active = flag
            STATE.awaiting_command = flag

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
                convo_ext = STATE.conversation_active
            if convo_ext != convo:          # یک دستور، حالت مکالمه را عوض کرده
                convo = convo_ext
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
                    if not convo:
                        _set_listen(False)
                # خوابِ خودکارِ حالت مکالمه پس از سکوتِ طولانی (اگر تنظیم شده باشد)
                if (convo and cfg.conversation_idle_timeout > 0
                        and time.time() - last_activity > cfg.conversation_idle_timeout):
                    _set_convo(False)
                    tts.say(f"{cfg.user_title}، چون مدتی ساکت بودید می‌رم استراحت. "
                            f"هر وقت کارم داشتید صدام کنید.")
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

            # ۲) عبارتِ «بسه/کافیه» -> خروج از حالت مکالمه
            norm = normalize(text)
            if convo and any(fuzzy_contains(norm, p, 0.82) for p in cfg.sleep_phrases):
                _set_convo(False)
                awaiting_since = None
                tts.say(f"باشه {cfg.user_title}، هر وقت کارم داشتید صدام کنید.")
                _drain()
                continue

            # ۳) کلمه‌ی بیدارباش یا ادامه‌ی دستور
            has_wake, after = _contains_wake(text, cfg.wake_words)
            import random
            last_activity = time.time()

            if has_wake:
                if after:
                    if not engine.handle(after) and not convo:
                        tts.say_cached_only(random.choice(engine.wake_ack))
                else:
                    tts.say_cached_only(random.choice(engine.wake_ack))
                # پس از نخستین صدا زدن، وارد حالت مکالمه‌ی پیوسته می‌شویم
                if cfg.conversation_mode:
                    if not convo:
                        _set_convo(True)
                        if not after:
                            tts.say(f"در خدمتم {cfg.user_title}، تا وقتی نگید «بسه» "
                                    f"منتظر دستورهاتون می‌مونم.")
                else:
                    awaiting_since = time.time()
                    _set_listen(True)
                _drain()

            elif convo:
                # در حالت مکالمه هر جمله مستقیماً دستور تلقی می‌شود
                if not engine.handle(text) and cfg.nag_on_unknown:
                    tts.say(random.choice(engine.unknown_lines))
                _drain()

            elif awaiting_since and time.time() - awaiting_since < cfg.command_timeout:
                awaiting_since = None
                _set_listen(False)
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
