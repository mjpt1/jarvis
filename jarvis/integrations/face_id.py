"""تشخیصِ چهره‌ی صاحب برای بیدارباشِ بیومتریک.

نیاز: `pip install face_recognition` (که dlib می‌خواهد — روی ویندوز به Build Tools
نیاز دارد) و یک عکس مرجع در `~/.jarvis/credentials/owner_face.jpg`.
بدونِ این‌ها خاموش می‌ماند و بیدارباش مثل قبل فقط با صدا کار می‌کند.
"""

from __future__ import annotations

import threading

from ..logging_setup import get_logger
from ..paths import OWNER_FACE

log = get_logger("face")

_TOL = 0.5
_known = None
_lock = threading.Lock()


def configure(tolerance: float) -> None:
    global _TOL
    _TOL = tolerance


def available() -> bool:
    if not OWNER_FACE.is_file():
        return False
    try:
        import face_recognition  # noqa: F401
        return True
    except Exception:
        return False


def _load_known():
    global _known
    with _lock:
        if _known is None:
            import face_recognition
            img = face_recognition.load_image_file(str(OWNER_FACE))
            encs = face_recognition.face_encodings(img)
            _known = encs[0] if encs else False
        return _known


def enroll(image_path: str) -> str:
    """یک عکس را به‌عنوان چهره‌ی مرجعِ صاحب ذخیره می‌کند."""
    try:
        import shutil
        import face_recognition
        img = face_recognition.load_image_file(image_path)
        if not face_recognition.face_encodings(img):
            return "تو این عکس چهره‌ای پیدا نشد."
        OWNER_FACE.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(image_path, OWNER_FACE)
        global _known
        _known = None
        return "چهره‌ی مرجع ذخیره شد."
    except Exception as exc:
        log.warning("ثبتِ چهره ناموفق بود: %s", exc)
        return "ثبتِ چهره ناموفق بود."


def is_owner(rgb_frame) -> bool:
    """آیا در این فریم چهره‌ای هست که با صاحب بخواند؟"""
    known = _load_known()
    if known is False or known is None:
        return False
    try:
        import face_recognition
        locs = face_recognition.face_locations(rgb_frame)
        if not locs:
            return False
        for enc in face_recognition.face_encodings(rgb_frame, locs):
            if face_recognition.compare_faces([known], enc, tolerance=_TOL)[0]:
                return True
        return False
    except Exception as exc:
        log.debug("مقایسه‌ی چهره: %s", exc)
        return False
