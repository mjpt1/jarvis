"""هسته‌ی بصری جارویس — کره‌ای از هزاران نقطه‌ی چرخان که مثل اکولایزر با صدای
کاربر یا خودِ جارویس نبض می‌زند (الهام‌گرفته از هولوگرام طلاییِ آیرون‌من).

نقاط بر اساس طولِ جغرافیایی به «باند»های اکولایزر تقسیم می‌شوند؛ هر باند ارتفاع
مستقلِ خودش را دارد که با دامنه‌ی صدا و یک نوسانِ زمینه هدایت می‌شود و با
attack/decay نرم می‌شود تا حرکتش شبیه اکولایزر واقعی باشد.
"""

from __future__ import annotations

import math
import random

import pygame

from ..state import STATE
from . import theme


def _fibonacci_sphere(n: int):
    pts = []
    phi = math.pi * (3.0 - math.sqrt(5.0))
    for i in range(n):
        y = 1 - (i / float(n - 1)) * 2 if n > 1 else 0.0
        r = math.sqrt(max(0.0, 1 - y * y))
        th = phi * i
        pts.append((math.cos(th) * r, y, math.sin(th) * r))
    return pts


def _lerp_color(a, b, t):
    t = max(0.0, min(1.0, t))
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


class Orb:
    def __init__(self, size: tuple[int, int], points: int = 1400, bands: int = 48):
        self.bands = max(8, bands)
        self._make_points(points)
        self._layer = pygame.Surface(size, pygame.SRCALPHA)
        self.band_level = [0.0] * self.bands
        # هر باند رزونانس (سرعت نوسان) و فازِ خودش را دارد -> ظاهرِ «فرکانسی»
        rnd = random.Random(7)
        self.band_res = [1.6 + 3.4 * rnd.random() for _ in range(self.bands)]
        self.band_phase = [rnd.uniform(0, math.tau) for _ in range(self.bands)]

    def _make_points(self, n: int):
        raw = _fibonacci_sphere(n)
        self.px = []
        self.py = []
        self.pz = []
        self.pband = []
        self.plat = []          # 0 در قطب، 1 روی استوا (دامنه‌ی بیشتر)
        for x, y, z in raw:
            self.px.append(x)
            self.py.append(y)
            self.pz.append(z)
            azim = math.atan2(z, x)
            b = int((azim + math.pi) / math.tau * self.bands) % self.bands
            self.pband.append(b)
            self.plat.append(math.sqrt(max(0.0, 1.0 - y * y)))

    def resize(self, size):
        self._layer = pygame.Surface(size, pygame.SRCALPHA)

    # ------------------------------------------------------------------
    def _update_bands(self, t: float, energy: float, idle: float):
        n = self.bands
        for b in range(n):
            wave = 0.5 + 0.5 * math.sin(t * self.band_res[b] + self.band_phase[b])
            # هنگام سکوت یک موجِ ملایمِ «تنفس»؛ با صدا، برجستگیِ واقعی
            target = idle * (0.15 + 0.35 * wave) + energy * (0.35 + 0.9 * wave)
            target = min(1.6, target)
            cur = self.band_level[b]
            # attack سریع، decay آرام
            rate = 0.55 if target > cur else 0.12
            self.band_level[b] = cur + (target - cur) * rate

    def draw(self, screen, t: float, cx: int, cy: int, base_scale: float,
             *, speaking: bool, listening: bool):
        energy = STATE.audio_energy()

        if speaking:
            base_col = theme.GOLD
            hot_col = (255, 245, 210)
            idle = 0.25
        elif listening:
            base_col = theme.ORB_LISTEN
            hot_col = theme.WHITE
            idle = 0.22
        else:
            base_col = theme.CYAN
            hot_col = theme.WHITE
            idle = 0.16

        self._update_bands(t, energy, idle)

        radius = base_scale * 0.9
        persp = radius * 3.5
        ay = t * (0.5 + (0.9 if speaking else 0.35))
        ax = 0.35 * math.sin(t * 0.15)
        cosA, sinA = math.cos(ay), math.sin(ay)
        cosB, sinB = math.cos(ax), math.sin(ax)

        layer = self._layer
        layer.fill((0, 0, 0, 0))
        bl = self.band_level
        avg = sum(bl) / len(bl)

        # هاله‌ی مرکزی (پشتِ نقاط، نرم و کم‌رنگ)
        for k in range(5, 0, -1):
            a = max(0, min(26, int(4 * (6 - k) * (0.5 + avg))))
            rr = int(radius * (0.18 + 0.13 * k) * (0.85 + avg * 0.4))
            pygame.draw.circle(layer, (*base_col, a), (cx, cy), max(1, rr))

        projected = []
        for i in range(len(self.px)):
            x, y, z = self.px[i], self.py[i], self.pz[i]
            disp = bl[self.pband[i]] * (0.30 + 0.55 * self.plat[i])
            scale = 1.0 + disp
            x *= scale
            y *= scale
            z *= scale
            # چرخش
            x, z = x * cosA - z * sinA, x * sinA + z * cosA
            y, z = y * cosB - z * sinB, y * sinB + z * cosB
            factor = persp / max(60.0, persp - z * radius)
            projected.append((z, cx + x * radius * factor, cy + y * radius * factor,
                              factor, bl[self.pband[i]]))

        projected.sort(key=lambda p: p[0])
        for depth, sx, sy, factor, level in projected:
            b = max(0.0, min(1.0, (depth + 1) / 2))
            col = _lerp_color(base_col, hot_col, min(1.0, level * 0.8))
            alpha = max(0, min(255, int(40 + b * 175 + level * 40)))
            size = max(1, int((1.4 + b * 2.6 + level * 2.2) * max(0.3, min(2.5, factor))))
            pygame.draw.circle(layer, (*col, alpha), (int(sx), int(sy)), size)

        screen.blit(layer, (0, 0))

        core = max(2, int(radius * (0.05 + avg * 0.05)))
        pygame.draw.circle(screen, hot_col, (cx, cy), core)

        # حلقه‌های مداریِ نازک
        for j in range(3):
            rw = int(radius * (1.7 + j * 0.4) * (1 + avg * 0.2))
            rh = int(rw * (abs(math.sin(t * 0.4 + j)) * 0.22 + 0.06))
            rect = pygame.Rect(0, 0, max(2, rw), max(2, rh))
            rect.center = (cx, cy)
            pygame.draw.ellipse(screen, base_col, rect, width=1)

        if listening or speaking:
            pr = int(radius * (0.9 + 0.12 * math.sin(t * 6)) * (1 + energy * 0.4))
            pygame.draw.circle(screen, base_col, (cx, cy), max(2, pr), width=2)
