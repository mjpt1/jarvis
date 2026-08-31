"""دانلود و آماده‌سازی مدل‌ها (FaceLandmarker و Vosk فارسی).

نکته‌ی مهم: بعضی سرورها بدون هدر User-Agent خطای ۴۰۳ می‌دهند؛ این ماژول همیشه
User-Agent می‌فرستد، چند بار تلاش می‌کند و نتیجه را در مسیر دائمی نگه می‌دارد.
"""

from __future__ import annotations

import time
import urllib.request
import zipfile

from .logging_setup import get_logger
from .paths import MODELS_DIR, ensure_dirs

log = get_logger("models")

_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")

FACE_LANDMARKER_URL = (
    "https://storage.googleapis.com/mediapipe-models/face_landmarker/"
    "face_landmarker/float16/latest/face_landmarker.task"
)
FACE_LANDMARKER_PATH = MODELS_DIR / "face_landmarker.task"


def _download(url: str, dest, attempts: int = 3, on_progress=None) -> None:
    ensure_dirs()
    dest_tmp = str(dest) + ".part"
    last_exc = None
    for i in range(1, attempts + 1):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": _UA})
            with urllib.request.urlopen(req, timeout=30) as resp:
                total = int(resp.headers.get("Content-Length", 0))
                got = 0
                with open(dest_tmp, "wb") as fh:
                    while True:
                        chunk = resp.read(1024 * 64)
                        if not chunk:
                            break
                        fh.write(chunk)
                        got += len(chunk)
                        if on_progress and total:
                            on_progress(got, total)
            import os
            os.replace(dest_tmp, dest)
            return
        except Exception as exc:  # pragma: no cover - شبکه
            last_exc = exc
            log.warning("دانلود ناموفق (تلاش %d/%d): %s", i, attempts, exc)
            time.sleep(1.5 * i)
    raise RuntimeError(f"دانلود {url} ناموفق بود: {last_exc}")


def ensure_face_landmarker(on_progress=None):
    if FACE_LANDMARKER_PATH.exists() and FACE_LANDMARKER_PATH.stat().st_size > 0:
        return FACE_LANDMARKER_PATH
    log.info("در حال دانلود مدل FaceLandmarker (فقط یک بار)...")
    _download(FACE_LANDMARKER_URL, FACE_LANDMARKER_PATH, on_progress=on_progress)
    log.info("مدل FaceLandmarker آماده شد.")
    return FACE_LANDMARKER_PATH


def ensure_vosk_model(model_name: str, on_progress=None):
    model_dir = MODELS_DIR / model_name
    if model_dir.is_dir() and any(model_dir.iterdir()):
        return model_dir

    url = f"https://alphacephei.com/vosk/models/{model_name}.zip"
    zip_path = MODELS_DIR / f"{model_name}.zip"
    log.info("در حال دانلود مدل صوتی Vosk «%s» (فقط یک بار، ~۵۰ مگابایت)...", model_name)
    _download(url, zip_path, on_progress=on_progress)

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
