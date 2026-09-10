"""تشخیصِ اشیا با YOLOv8 و توصیفِ صحنه.

نیاز: `pip install ultralytics` (که torch را هم می‌آورد). بدونِ آن این ابزار
خودش را خاموش می‌کند. مدلِ کوچک (`yolov8n.pt`) بارِ اول خودکار دانلود می‌شود.
منبعِ تصویر: صفحه‌ی نمایش (پیش‌فرض) یا وب‌کم.
"""

from __future__ import annotations

import threading

from ..logging_setup import get_logger
from ..paths import MODELS_DIR

log = get_logger("vision")

_MODEL_NAME = "yolov8n.pt"
_SOURCE = "screen"
_MIN_CONF = 0.4
_model = None
_model_lock = threading.Lock()

# ترجمه‌ی کلاس‌های پرکاربردِ COCO به فارسی
_FA = {
    "person": "شخص", "chair": "صندلی", "laptop": "لپ‌تاپ", "cell phone": "موبایل",
    "book": "کتاب", "cup": "فنجان", "bottle": "بطری", "tv": "تلویزیون",
    "keyboard": "کیبورد", "mouse": "ماوس", "clock": "ساعت", "potted plant": "گلدان",
    "couch": "مبل", "bed": "تخت", "dining table": "میز", "remote": "کنترل",
    "backpack": "کوله", "handbag": "کیف", "cat": "گربه", "dog": "سگ",
    "car": "خودرو", "bicycle": "دوچرخه", "wine glass": "لیوان", "bowl": "کاسه",
}


def configure(model_name: str, source: str, min_conf: float) -> None:
    global _MODEL_NAME, _SOURCE, _MIN_CONF
    _MODEL_NAME, _SOURCE, _MIN_CONF = model_name, source, min_conf


def available() -> bool:
    try:
        import ultralytics  # noqa: F401
        return True
    except Exception:
        return False


def _load():
    global _model
    with _model_lock:
        if _model is None:
            from ultralytics import YOLO
            path = MODELS_DIR / _MODEL_NAME
            _model = YOLO(str(path) if path.exists() else _MODEL_NAME)
        return _model


def _grab_frame(source: str | None = None):
    src = source or _SOURCE
    import numpy as np
    if src == "camera":
        import cv2
        cap = cv2.VideoCapture(0)
        ok, frame = cap.read()
        cap.release()
        if not ok:
            return None
        return frame[:, :, ::-1]  # BGR->RGB
    from PIL import ImageGrab
    return np.array(ImageGrab.grab())


def detect(source: str | None = None) -> list[tuple[str, int]]:
    """[(نام فارسی, تعداد)] از اشیایی که با اطمینانِ کافی دیده شدند."""
    frame = _grab_frame(source)
    if frame is None:
        return []
    model = _load()
    res = model.predict(frame, conf=_MIN_CONF, verbose=False)
    counts: dict[str, int] = {}
    for r in res:
        for c in r.boxes.cls.tolist():
            name = r.names[int(c)]
            counts[_FA.get(name, name)] = counts.get(_FA.get(name, name), 0) + 1
    return sorted(counts.items(), key=lambda x: -x[1])


def describe_scene(source: str | None = None, narrate: bool = True) -> str:
    try:
        objs = detect(source)
    except Exception as exc:
        log.warning("تشخیص اشیا ناموفق بود: %s", exc)
        return "نتونستم صحنه رو تحلیل کنم."
    if not objs:
        return "چیزِ مشخصی نمی‌بینم."
    plain = "، ".join(f"{n} {name}" if n > 1 else name for name, n in objs)
    if not narrate:
        return plain
    from .. import claude_client
    if claude_client.available():
        r = claude_client.oneshot(
            "تو جارویسی. از فهرستِ اشیاءِ دیده‌شده یک توصیفِ کوتاه و طبیعیِ فارسی "
            "(یک جمله) از صحنه بساز.", f"اشیاء: {plain}", max_tokens=120)
        if r:
            return r
    return f"می‌بینم: {plain}."
