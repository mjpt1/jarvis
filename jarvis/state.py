"""وضعیت مشترک بین تردها — با یک قفل محافظت می‌شود."""

from __future__ import annotations

import datetime
import threading
from dataclasses import dataclass, field


@dataclass
class SharedState:
    lock: threading.Lock = field(default_factory=threading.Lock)
    stop_event: threading.Event = field(default_factory=threading.Event)

    # صدا/گفتار
    speaking: bool = False
    current_subtitle: str = ""
    cache_ready: bool = False
    cache_progress: tuple[int, int] = (0, 1)
    audio_muted: bool = False
    awaiting_command: bool = False
    conversation_active: bool = False   # حالت مکالمه‌ی پیوسته فعال است
    last_heard_text: str = ""
    partial_text: str = ""
    mic_level: float = 0.0          # 0..1 دامنه‌ی صدای کاربر
    tts_level: float = 0.0          # 0..1 دامنه‌ی صدای جارویس هنگام صحبت
    voice_enabled: bool = False     # آیا ترد صدا واقعاً بالا آمد
    telegram_enabled: bool = False

    # دوربین/چهره
    camera_enabled: bool = False
    face_present: bool = False
    face_count: int = 0
    yaw: float = 0.0
    pitch: float = 0.0
    roll: float = 0.0
    face_area_ratio: float = 0.0
    ear: float = 1.0
    owner_present: bool = True      # چهره‌ی صاحب دیده می‌شود (اگر تشخیص چهره فعال باشد)
    owner_gate_active: bool = False # بیدارباش مشروط به دیدنِ صاحب است

    # سیستم
    cpu_percent: float = 0.0
    ram_percent: float = 0.0
    disk_percent: float = 0.0
    battery_percent: float | None = None
    net_history: list[float] = field(default_factory=list)
    tool_call_count: int = 0        # تعداد دستورهای اجراشده در این نشست

    # آب‌وهوا
    weather_temp: float | None = None
    weather_desc: str = ""
    location_name: str = ""

    # مکان دوم (مونکتون)
    secondary_temp: float | None = None
    secondary_name: str = ""

    # لاگ رویداد روی HUD
    event_log: list[tuple[str, str]] = field(default_factory=list)

    # تایید صوتی اقدامات حساس
    pending_confirm_action: str | None = None
    pending_confirm_since: float = 0.0

    # حافظه‌ی کوتاه‌مدت مکالمه (برای Claude)
    chat_history: list[dict] = field(default_factory=list)

    @property
    def running(self) -> bool:
        return not self.stop_event.is_set()

    def stop(self) -> None:
        self.stop_event.set()

    def audio_energy(self) -> float:
        """بیشینه‌ی دامنه‌ی صدای کاربر و جارویس — ورودیِ اکولایزر."""
        with self.lock:
            return max(self.mic_level, self.tts_level)

    def log(self, text: str) -> None:
        ts = datetime.datetime.now().strftime("%H:%M:%S")
        with self.lock:
            self.event_log.append((ts, text))
            del self.event_log[:-8]


STATE = SharedState()
