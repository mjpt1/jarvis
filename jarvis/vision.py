"""ترد دوربین + MediaPipe FaceLandmarker + تشخیص رویدادها (بدون نق‌زدن درباره‌ی زاویه‌ی سر)."""

from __future__ import annotations

import math
import time

from .config import Config
from .logging_setup import get_logger
from .state import STATE

log = get_logger("vision")

LEFT_EYE = [362, 385, 387, 263, 373, 380]
RIGHT_EYE = [33, 160, 158, 133, 153, 144]
EAR_CLOSED = 0.19
FATIGUE_SECONDS = 2.0
TRACKING_LOST_SECONDS = 2.5

EVENTS = {
    "SYSTEM_READY": {"cooldown": 10 ** 9, "lines": ["سیستم آماده‌ست {t}."]},
    "TRACKING_LOCKED": {"cooldown": 12,
                        "lines": ["اتصال چهره برقرار شد {t}.", "ردیابی برقراره {t}."]},
    "TRACKING_LOST": {"cooldown": 20, "lines": ["{t}، از دیدم خارج شدید."]},
    "INTRUDER": {"cooldown": 25, "lines": ["یه نفر دیگه وارد اتاق شد {t}."]},
    "FATIGUE": {"cooldown": 60, "lines": ["پیشنهاد می‌کنم یه کم استراحت کنید {t}."]},
    "IDLE_STATUS": {"cooldown": 240, "lines": ["همه چیز طبق برنامه پیش می‌ره {t}."]},
}


def event_lines(title: str) -> list[str]:
    out = []
    for cfg in EVENTS.values():
        out += [l.replace("{t}", title) for l in cfg["lines"]]
    return out


def rotation_matrix_to_euler(R):
    sy = math.sqrt(R[0, 0] ** 2 + R[1, 0] ** 2)
    if sy < 1e-6:
        pitch = math.atan2(-R[2, 0], sy)
        yaw = 0.0
        roll = math.atan2(-R[1, 2], R[1, 1])
    else:
        pitch = math.atan2(-R[2, 0], sy)
        yaw = math.atan2(R[1, 0], R[0, 0])
        roll = math.atan2(R[2, 1], R[2, 2])
    return math.degrees(yaw), math.degrees(pitch), math.degrees(roll)


def _euclid(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])


def eye_aspect_ratio(landmarks, indices, w, h):
    pts = [(landmarks[i].x * w, landmarks[i].y * h) for i in indices]
    p1, p2, p3, p4, p5, p6 = pts
    vert = _euclid(p2, p6) + _euclid(p3, p5)
    horiz = _euclid(p1, p4) * 2.0
    return vert / horiz if horiz else 1.0


class EventManager:
    def __init__(self, title: str, emit):
        self.title = title
        self.emit = emit                      # emit(text)
        self.last_fired = {name: 0.0 for name in EVENTS}
        self.system_ready_fired = False
        self.was_tracking = False
        self.face_lost_since = None
        self.eyes_closed_since = None

    def _fire(self, name: str):
        now = time.time()
        if now - self.last_fired[name] < EVENTS[name]["cooldown"]:
            return
        self.last_fired[name] = now
        with STATE.lock:
            muted, ready = STATE.audio_muted, STATE.cache_ready
        if muted or not ready:
            return
        import random
        line = random.choice(EVENTS[name]["lines"]).replace("{t}", self.title)
        STATE.log(name)
        self.emit(line)

    def update(self, face_present, face_count, ear):
        now = time.time()
        if face_present and not self.system_ready_fired:
            self.system_ready_fired = True
            self._fire("SYSTEM_READY")

        if face_present:
            if self.face_lost_since is not None and not self.was_tracking:
                self._fire("TRACKING_LOCKED")
            self.was_tracking = True
            self.face_lost_since = None
        else:
            if self.face_lost_since is None:
                self.face_lost_since = now
            elif now - self.face_lost_since > TRACKING_LOST_SECONDS and self.was_tracking:
                self._fire("TRACKING_LOST")
                self.was_tracking = False

        if not face_present:
            self.eyes_closed_since = None
            return

        if face_count >= 2:
            self._fire("INTRUDER")

        if ear < EAR_CLOSED:
            if self.eyes_closed_since is None:
                self.eyes_closed_since = now
            elif now - self.eyes_closed_since > FATIGUE_SECONDS:
                self._fire("FATIGUE")
        else:
            self.eyes_closed_since = None

        self._fire("IDLE_STATUS")


def camera_worker(cfg: Config, emit) -> None:
    try:
        import cv2
        import mediapipe as mp
        import numpy as np
        from mediapipe.tasks import python as mp_python
        from mediapipe.tasks.python import vision as mp_vision

        from .models import ensure_face_landmarker
    except Exception as exc:
        log.warning("ماژول‌های دوربین در دسترس نیستند: %s", exc)
        return

    try:
        model_path = ensure_face_landmarker()
    except Exception as exc:
        log.warning("[JRV-VISION-002] مدل چهره دانلود نشد — دوربین غیرفعال: %s", exc)
        return

    options = mp_vision.FaceLandmarkerOptions(
        base_options=mp_python.BaseOptions(model_asset_path=str(model_path)),
        running_mode=mp_vision.RunningMode.VIDEO,
        num_faces=2,
        output_facial_transformation_matrixes=True,
        min_face_detection_confidence=0.5,
        min_tracking_confidence=0.5,
    )
    landmarker = mp_vision.FaceLandmarker.create_from_options(options)

    backend = cv2.CAP_DSHOW if __import__("os").name == "nt" else 0
    cap = cv2.VideoCapture(cfg.camera_index, backend)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
    if not cap.isOpened():
        log.warning("[JRV-VISION-001] دوربین باز نشد (index=%s).", cfg.camera_index)
        landmarker.close()
        return

    # تشخیصِ چهره‌ی صاحب (اختیاری) برای بیدارباشِ بیومتریک
    face_id = None
    if cfg.face_id_enabled:
        try:
            from .integrations import face_id as _fid
            if _fid.available():
                face_id = _fid
                with STATE.lock:
                    STATE.owner_gate_active = True
                    STATE.owner_present = False
                log.info("بیدارباشِ بیومتریک فعال شد (تشخیص چهره‌ی صاحب).")
        except Exception as exc:
            log.debug("face_id: %s", exc)

    with STATE.lock:
        STATE.camera_enabled = True
    manager = EventManager(cfg.user_title, emit)
    start = time.time()
    _last_face_check = 0.0
    try:
        while STATE.running:
            ok, frame = cap.read()
            if not ok:
                time.sleep(0.05)
                continue
            frame = cv2.flip(frame, 1)
            h, w = frame.shape[:2]
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
            ts_ms = int((time.time() - start) * 1000)
            try:
                result = landmarker.detect_for_video(mp_image, ts_ms)
            except Exception:
                result = None

            present = bool(result and result.face_landmarks)
            count = len(result.face_landmarks) if result else 0
            yaw = pitch = roll = 0.0
            area = 0.0
            ear = 1.0
            if present:
                lm = result.face_landmarks[0]
                xs = [p.x for p in lm]
                ys = [p.y for p in lm]
                area = (max(xs) - min(xs)) * (max(ys) - min(ys))
                if result.facial_transformation_matrixes:
                    mat = np.array(result.facial_transformation_matrixes[0]).reshape(4, 4)
                    yaw, pitch, roll = rotation_matrix_to_euler(mat[:3, :3])
                ear = (eye_aspect_ratio(lm, LEFT_EYE, w, h)
                       + eye_aspect_ratio(lm, RIGHT_EYE, w, h)) / 2.0

            with STATE.lock:
                STATE.face_present = present
                STATE.face_count = count
                STATE.yaw, STATE.pitch, STATE.roll = yaw, pitch, roll
                STATE.face_area_ratio = area
                STATE.ear = ear

            # چهره‌ی صاحب را هر ~۱.۵ ثانیه بررسی کن (وقتی چهره‌ای هست)
            if face_id is not None and present and time.time() - _last_face_check > 1.5:
                _last_face_check = time.time()
                try:
                    is_owner = face_id.is_owner(rgb)
                except Exception:
                    is_owner = False
                with STATE.lock:
                    STATE.owner_present = is_owner
            elif face_id is not None and not present:
                with STATE.lock:
                    STATE.owner_present = False

            manager.update(present, count, ear)
            time.sleep(0.01)
    finally:
        cap.release()
        landmarker.close()
        with STATE.lock:
            STATE.camera_enabled = False
            STATE.owner_gate_active = False
