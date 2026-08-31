"""پخش موزیک از پوشه‌ی محلی — روی کانال جدا از TTS، با داکینگ خودکار."""

from __future__ import annotations

import os
import random

from .logging_setup import get_logger
from .state import STATE
from . import tts

log = get_logger("music")

try:
    import pygame
except Exception:  # pragma: no cover
    pygame = None

_EXT = (".mp3", ".wav", ".ogg", ".flac", ".m4a")


class MusicPlayer:
    def __init__(self, music_dir: str, user_title: str = "قربان"):
        self.music_dir = music_dir
        self.title = user_title
        self.playlist: list[str] = []
        self.index = -1

    # --- داخلی ---
    def _scan(self) -> list[str]:
        if not os.path.isdir(self.music_dir):
            return []
        out = []
        for root, _dirs, files in os.walk(self.music_dir):
            for f in files:
                if f.lower().endswith(_EXT):
                    out.append(os.path.join(root, f))
        return out

    def _ensure(self) -> bool:
        if not self.playlist:
            self.playlist = self._scan()
            random.shuffle(self.playlist)
        return bool(self.playlist)

    def _play_current(self) -> None:
        if pygame is None or not (0 <= self.index < len(self.playlist)):
            return
        path = self.playlist[self.index]
        try:
            pygame.mixer.music.load(path)
            pygame.mixer.music.set_volume(0.8)
            pygame.mixer.music.play()
            name = os.path.splitext(os.path.basename(path))[0]
            STATE.log(f"MUSIC ▶ {name}")
            tts.say(f"در حال پخش {name} {self.title}.")
        except Exception as exc:
            log.warning("پخش آهنگ ناموفق بود: %s", exc)
            tts.say(f"نتونستم این آهنگ رو پخش کنم {self.title}.")

    def _no_music(self) -> None:
        tts.say(f"{self.title}، تو پوشه‌ی موزیک آهنگی پیدا نکردم.")

    # --- عمومی ---
    def play_random(self) -> None:
        if not self._ensure():
            return self._no_music()
        self.index = random.randrange(len(self.playlist))
        self._play_current()

    def next_track(self) -> None:
        if not self._ensure():
            return self._no_music()
        self.index = (self.index + 1) % len(self.playlist)
        self._play_current()

    def prev_track(self) -> None:
        if not self._ensure():
            return self._no_music()
        self.index = (self.index - 1) % len(self.playlist)
        self._play_current()

    def stop(self) -> None:
        if pygame:
            pygame.mixer.music.stop()
        tts.say(f"آهنگ رو متوقف کردم {self.title}.")

    def pause(self) -> None:
        if pygame:
            pygame.mixer.music.pause()
        tts.say(f"مکث کردم {self.title}.")

    def resume(self) -> None:
        if pygame:
            pygame.mixer.music.unpause()
        tts.say(f"ادامه می‌دم {self.title}.")
