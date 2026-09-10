"""دانلودِ پس‌زمینه‌ی مدل‌ها — قابلِ ازسرگیری، با نمایشِ درصد روی HUD.

جارویس با مدلِ کوچکِ صدا کار می‌کند و مدلِ بزرگِ دقیق‌تر را بی‌سروصدا در
پس‌زمینه می‌گیرد؛ اجرای بعدی خودکار از مدلِ بزرگ استفاده می‌کند.
"""

from __future__ import annotations

import json

from .config import Config
from .logging_setup import get_logger
from .paths import APP_DIR, LOCAL_CONFIG_FILE, MODELS_DIR
from .state import STATE

log = get_logger("models")


def _persist(key: str, value) -> None:
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


def background_worker(cfg: Config) -> None:
    """در یک تردِ daemon اجرا می‌شود. جارویس را بلاک نمی‌کند."""
    from .models import ensure_gesture_recognizer, ensure_vosk_model

    # مدل حرکاتِ دست (کوچک) — اگر نبود
    if cfg.gestures_enabled:
        try:
            ensure_gesture_recognizer()
        except Exception as exc:
            log.warning("مدل حرکاتِ دست دانلود نشد: %s", exc)

    # مدلِ بزرگِ صدا
    if not cfg.auto_upgrade_voice_model:
        return
    big = cfg.big_voice_model
    if (MODELS_DIR / big).is_dir() and any((MODELS_DIR / big).iterdir()):
        if cfg.vosk_model_name != big:
            _persist("vosk_model_name", big)
        return
    if cfg.vosk_model_name == big:
        return  # کاربر خودش خواسته؛ voice_worker می‌گیردش

    log.info("دانلودِ پس‌زمینه‌ی مدلِ بزرگِ فارسی آغاز شد (~۱.۴ گیگ، قابلِ ازسرگیری).")
    with STATE.lock:
        STATE.download_status = "مدل صوتیِ دقیق‌تر: در حال دانلود…"
    try:
        ensure_vosk_model(big)
        _persist("vosk_model_name", big)
        with STATE.lock:
            STATE.download_status = ""
        log.info("مدلِ بزرگِ صدا آماده شد؛ اجرای بعدی دقیق‌تر می‌شنود.")
        try:
            from . import tts
            tts.say("مدلِ صوتیِ بهتری دانلود شد؛ از دفعه‌ی بعد دقیق‌تر متوجه می‌شم.")
        except Exception:
            pass
    except Exception as exc:
        log.warning("دانلودِ مدلِ بزرگ کامل نشد (دفعه‌ی بعد ادامه می‌دهد): %s", exc)
        with STATE.lock:
            STATE.download_status = ""
