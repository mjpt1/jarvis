"""دانلود و آماده‌سازی مدل‌ها (FaceLandmarker و Vosk فارسی).

نکته‌ی مهم: بعضی سرورها بدون هدر User-Agent خطای ۴۰۳ می‌دهند؛ این ماژول همیشه
User-Agent می‌فرستد، چند بار تلاش می‌کند و نتیجه را در مسیر دائمی نگه می‌دارد.
"""

from __future__ import annotations

import os
import time
import urllib.request
import zipfile

from .logging_setup import get_logger
from .paths import MODELS_DIR, ensure_dirs
from .state import STATE

log = get_logger("models")

_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")

FACE_LANDMARKER_URL = (
    "https://storage.googleapis.com/mediapipe-models/face_landmarker/"
    "face_landmarker/float16/latest/face_landmarker.task"
)
FACE_LANDMARKER_PATH = MODELS_DIR / "face_landmarker.task"

GESTURE_URL = (
    "https://storage.googleapis.com/mediapipe-models/gesture_recognizer/"
    "gesture_recognizer/float16/latest/gesture_recognizer.task"
)
GESTURE_PATH = MODELS_DIR / "gesture_recognizer.task"


class _Aborted(Exception):
    """دانلود به‌خاطرِ خاموش‌شدنِ برنامه قطع شد (نه خطای واقعی)."""


def _set_status(text: str) -> None:
    with STATE.lock:
        STATE.download_status = text


def _download(url: str, dest, attempts: int = 6, on_progress=None, label: str = "") -> None:
    """دانلودِ قابلِ‌ازسرگیری: اگر فایلِ .part از قبل باشد از همان‌جا ادامه می‌دهد."""
    ensure_dirs()
    dest_tmp = str(dest) + ".part"
    last_exc = None
    for i in range(1, attempts + 1):
        if not STATE.running:
            return
        try:
            have = os.path.getsize(dest_tmp) if os.path.exists(dest_tmp) else 0
            headers = {"User-Agent": _UA}
            if have:
                headers["Range"] = f"bytes={have}-"
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=30) as resp:
                resuming = resp.status == 206
                if have and not resuming:
                    have = 0                       # سرور ازسرگیری را قبول نکرد
                total = int(resp.headers.get("Content-Length", 0)) + (have if resuming else 0)
                got = have
                mode = "ab" if resuming else "wb"
                with open(dest_tmp, mode) as fh:
                    while STATE.running:
                        chunk = resp.read(1024 * 128)
                        if not chunk:
                            break
                        fh.write(chunk)
                        got += len(chunk)
                        if total:
                            pct = int(got * 100 / total)
                            _set_status(f"{label or 'دانلود مدل'}: {pct}٪ "
                                        f"({got // 1_000_000}/{total // 1_000_000} مگابایت)")
                            if on_progress:
                                on_progress(got, total)
            if not STATE.running:
                raise _Aborted()
            if not os.path.exists(dest_tmp) or os.path.getsize(dest_tmp) < 1024:
                raise OSError("فایلِ دانلود ناقص است")
            os.replace(dest_tmp, dest)
            _set_status("")
            return
        except _Aborted:
            _set_status("")
            raise
        except Exception as exc:  # pragma: no cover - شبکه
            last_exc = exc
            log.warning("دانلود ناموفق (تلاش %d/%d) — از سرگیری خودکار: %s", i, attempts, exc)
            _set_status(f"{label or 'دانلود مدل'}: قطع شد، تلاش دوباره…")
            time.sleep(min(20, 2.0 * i))
    _set_status("")
    raise RuntimeError(f"دانلود {url} ناموفق بود: {last_exc}")


def ensure_face_landmarker(on_progress=None):
    if FACE_LANDMARKER_PATH.exists() and FACE_LANDMARKER_PATH.stat().st_size > 0:
        return FACE_LANDMARKER_PATH
    log.info("در حال دانلود مدل FaceLandmarker (فقط یک بار)...")
    _download(FACE_LANDMARKER_URL, FACE_LANDMARKER_PATH, on_progress=on_progress,
              label="مدل چهره")
    log.info("مدل FaceLandmarker آماده شد.")
    return FACE_LANDMARKER_PATH


def ensure_gesture_recognizer(on_progress=None):
    if GESTURE_PATH.exists() and GESTURE_PATH.stat().st_size > 0:
        return GESTURE_PATH
    log.info("در حال دانلود مدل تشخیص حرکاتِ دست (فقط یک بار)...")
    _download(GESTURE_URL, GESTURE_PATH, on_progress=on_progress, label="مدل حرکات دست")
    return GESTURE_PATH


def ensure_vosk_model(model_name: str, on_progress=None):
    model_dir = MODELS_DIR / model_name
    if model_dir.is_dir() and any(model_dir.iterdir()):
        return model_dir

    url = f"https://alphacephei.com/vosk/models/{model_name}.zip"
    zip_path = MODELS_DIR / f"{model_name}.zip"
    big = "small" not in model_name
    log.info("در حال دانلود مدل صوتی Vosk «%s»...", model_name)
    _download(url, zip_path, on_progress=on_progress,
              label="مدل صوتیِ دقیق" if big else "مدل صوتی")

    log.info("در حال استخراج مدل صوتی...")
    with zipfile.ZipFile(zip_path, "r") as zf:
        zf.extractall(MODELS_DIR)
    zip_path.unlink(missing_ok=True)

    if not (model_dir.is_dir() and any(model_dir.iterdir())):
        # بعضی زیپ‌ها با نام متفاوت باز می‌شوند
        cands = [p for p in MODELS_DIR.iterdir() if p.is_dir() and p.name.startswith("vosk")]
        if cands:
            return cands[0]
        raise RuntimeError("استخراج مدل صوتی ناموفق بود.")
    log.info("مدل صوتی آماده شد.")
    return model_dir
