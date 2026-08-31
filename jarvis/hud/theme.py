"""پالت رنگ و بارگذاری فونت‌ها (Vazirmatn برای فارسی، Orbitron برای اعداد)."""

from __future__ import annotations

import pygame

from ..logging_setup import get_logger
from ..paths import FONTS_DIR

log = get_logger("hud")

# --- پالت Stark HUD ---
BG = (2, 5, 9)
CYAN = (0, 200, 255)
CYAN_DIM = (0, 150, 195)
CYAN_FAINT = (0, 90, 120)
WHITE = (220, 245, 255)
WARN = (255, 150, 60)
OK = (80, 255, 190)
GOLD = (255, 200, 90)          # accent «آرک‌ری‌اکتور» هنگام صحبت
GAUGE_BG = (14, 30, 42)

ORB_IDLE = (0, 190, 255)
ORB_SPEAK = (0, 255, 200)
ORB_LISTEN = (120, 200, 255)


class Fonts:
    def __init__(self, scale: float = 1.0):
        s = scale
        self.fa = self._fa(int(24 * s))
        self.fa_small = self._fa(int(17 * s))
        self.subtitle = self._fa(int(26 * s))
        self.num = self._num(int(18 * s))
        self.num_big = self._num(int(40 * s), bold=True)
        self.mono = self._mono(int(16 * s))

    def _fa(self, size: int, bold: bool = False):
        name = "Vazirmatn-Bold.ttf" if bold else "Vazirmatn-Regular.ttf"
        path = FONTS_DIR / name
        try:
            if path.exists():
                return pygame.font.Font(str(path), size)
        except Exception as exc:  # pragma: no cover
            log.debug("فونت %s بارگذاری نشد: %s", name, exc)
        return pygame.font.SysFont("tahoma,arial", size, bold=bold)

    def _num(self, size: int, bold: bool = False):
        path = FONTS_DIR / "Orbitron.ttf"
        try:
            if path.exists():
                return pygame.font.Font(str(path), size)
        except Exception:  # pragma: no cover
            pass
        return pygame.font.SysFont("consolas,arial", size, bold=bold)

    def _mono(self, size: int):
        try:
            return pygame.font.SysFont("consolas,menlo,monospace", size)
        except Exception:  # pragma: no cover
            return pygame.font.Font(None, size)
