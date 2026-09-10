"""ترد ورودی صدا: Vosk آفلاین + کلمه‌ی بیدارباش + تاییدهای صوتی + مقیاس صدا.

از partial results برای واکنش سریع به «جارویس» استفاده می‌کند و هنگام صحبتِ جارویس
ورودی را نادیده می‌گیرد تا صدای خودش را دستور نگیرد.
"""

from __future__ import annotations

import json
import math
import queue
import time

from . import tts
from .commands import CONFIRM_NO, CONFIRM_YES, CommandEngine
from .config import Config
from .logging_setup import get_logger
from .state import STATE
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


def _contains_wake(text: str, wake_words, fuzzy: float = 0.62) -> tuple[bool, str]:
    norm = normalize(text)
    if not norm:
        return False, ""
    for w in wake_words:
        wn = normalize(w)
        idx = norm.find(wn)
        if idx != -1:
            return True, norm[idx + len(wn):].strip()
    # تطبیقِ نرم روی هر توکن (مدل کوچک اسم را دقیق نمی‌شنود)
    toks = norm.split()
    wnorm = [normalize(w) for w in wake_words]
    for i, tok in enumerate(toks):
        if any(_ratio(tok, wn) >= fuzzy for wn in wnorm):
            return True, " ".join(toks[i + 1:]).strip()
    return False, ""


def _ratio(a: str, b: str) -> float:
    import difflib
    return difflib.SequenceMatcher(None, a, b).ratio()


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
        log.warning("[JRV-AUDIO-003] مدل صوتی دانلود نشد — تشخیص گفتار غیرفعال: %s", exc)
        return

    try:
        model = vosk.Model(str(model_dir))
    except Exception as exc:
        log.warning("[JRV-AUDIO-002] بارگذاری مدل صوتی ناموفق بود: %s", exc)
        return

    audio_q: queue.Queue[bytes] = queue.Queue()

    def _cb(indata, frames, time_info, status):  # noqa: ARG001
        audio_q.put(bytes(indata))

    recognizer = vosk.KaldiRecognizer(model, cfg.sample_rate)
    recognizer.SetWords(False)

    # شناسگرِ محدود فقط برای کلمه‌ی بیدارباش — دقتِ صدا زدن را بالا می‌برد
    wake_rec = None
    try:
        grammar = json.dumps(sorted(set(w for w in cfg.wake_grammar_words if w))
                             + ["[unk]"], ensure_ascii=False)
        wake_rec = vosk.KaldiRecognizer(model, cfg.sample_rate, grammar)
        wake_rec.SetWords(False)
        log.info("شناسگرِ بیدارباش با گرامر: %s", grammar)
    except Exception as exc:
        log.warning("شناسگرِ محدودِ بیدارباش ساخته نشد (از حالت عادی استفاده می‌شود): %s", exc)

    try:
        default_in = sd.query_devices(kind="input")
        log.info("میکروفون پیش‌فرض: %s", default_in.get("name", "?"))
    except Exception as exc:
        log.warning("میکروفونِ ورودی پیدا نشد: %s", exc)

    try:
        stream = sd.RawInputStream(samplerate=cfg.sample_rate, blocksize=8000,
                                   dtype="int16", channels=1, callback=_cb)
    except Exception as exc:
        log.warning("[JRV-AUDIO-001] باز کردن میکروفون ناموفق بود: %s", exc)
        return

    with STATE.lock:
        STATE.voice_enabled = True
    log.info("تشخیص گفتار فعال شد — کلمه‌ی بیدارباش: %s", cfg.wake_words[0])

    _last_dbg = [0.0, 0.0]   # [آخرین لاگِ partial, بیشینه‌ی سطح صدا از آخرین لاگ]
    peak = 0.0               # بیشینه‌ی نرمِ اخیرِ سطح صدا (برای فیلترِ نویزِ دور)

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

    _owner_warned = [0.0]

    def _owner_ok() -> bool:
        with STATE.lock:
            if not STATE.owner_gate_active:
                return True
            ok = STATE.owner_present
        if not ok and time.time() - _owner_warned[0] > 20:
            _owner_warned[0] = time.time()
            log.info("بیدارباش نادیده گرفته شد: چهره‌ی صاحب دیده نمی‌شود.")
        return ok

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

            lvl = _rms_level(data)
            peak = max(lvl, peak * 0.85)
            with STATE.lock:
                STATE.mic_level = lvl
            _last_dbg[1] = max(_last_dbg[1], lvl)

            # --- شناسگرِ محدودِ بیدارباش (فقط وقتی هنوز فعال نیستیم) ---
            if (wake_rec is not None and not convo and awaiting_since is None
                    and peak >= cfg.wake_min_level and _owner_ok()):
                if wake_rec.AcceptWaveform(data):
                    wtext = json.loads(wake_rec.Result()).get("text", "")
                else:
                    wtext = json.loads(wake_rec.PartialResult()).get("partial", "")
                wtext = wtext.replace("[unk]", "").strip()
                if wtext:
                    wk, _after = _contains_wake(
                        wtext, cfg.wake_words + cfg.wake_grammar_words, cfg.wake_fuzzy)
                    if wk:
                        log.info("بیدارباش (گرامر): %r  سطح≈%.2f", wtext, _last_dbg[1])
                        recognizer.Reset()
                        wake_rec.Reset()
                        _drain()
                        import random as _r
                        tts.say_cached_only(_r.choice(engine.wake_ack))
                        if cfg.conversation_mode:
                            _set_convo(True)
                            tts.say(f"در خدمتم {cfg.user_title}، تا وقتی نگید «بسه» "
                                    f"منتظر دستورهاتون می‌مونم.")
                        else:
                            awaiting_since = time.time()
                            _set_listen(True)
                        continue

            if not recognizer.AcceptWaveform(data):
                partial = json.loads(recognizer.PartialResult()).get("partial", "")
                with STATE.lock:
                    STATE.partial_text = partial
                now = time.time()
                if now - _last_dbg[0] > 3.0:
                    log.info("صدا: سطح≈%.2f  partial=%r", _last_dbg[1], partial)
                    _last_dbg[0], _last_dbg[1] = now, 0.0
                continue

            with STATE.lock:
                STATE.partial_text = ""
            text = json.loads(recognizer.Result()).get("text", "").strip()
            if not text:
                continue
            log.info("شنیده شد: %r  (convo=%s)", text, convo)
            with STATE.lock:
                STATE.last_heard_text = text
                onboarding_on = STATE.onboarding_active

            # ۰) پاسخ به سؤالِ آشناییِ اولیه
            ob = getattr(engine, "onboarding", None)
            if onboarding_on and ob is not None:
                done, nxt = ob.submit(text)
                tts.say(nxt)
                _drain()
                if done:
                    convo = False
                continue

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

            # ۲) عبارتِ «بسه/کافیه/تمام» -> خروج از حالت مکالمه
            norm = normalize(text)
            n_tokens = norm.split()
            exact_stop = any(tok in cfg.sleep_exact_tokens for tok in n_tokens)
            phrase_stop = any(fuzzy_contains(norm, p, 0.8) for p in cfg.sleep_phrases)
            if convo and (exact_stop or phrase_stop):
                log.info("خروج از حالت مکالمه با: %r", text)
                _set_convo(False)
                awaiting_since = None
                tts.say(f"باشه {cfg.user_title}، هر وقت کارم داشتید صدام کنید.")
                _drain()
                continue

            # ۳) کلمه‌ی بیدارباش یا ادامه‌ی دستور
            has_wake, after = _contains_wake(text, cfg.wake_words, cfg.wake_fuzzy)
            if has_wake and not convo and not _owner_ok():
                has_wake = False
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
                ok = engine.handle(text)
                log.info("  اجرا در حالت مکالمه: %r -> %s", text, ok)
                if not ok and cfg.nag_on_unknown:
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
