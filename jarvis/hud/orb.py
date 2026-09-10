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
            idle = 0.22
            spread = 0.42
        elif listening:
            base_col = (120, 190, 255)
            hot_col = theme.WHITE
            idle = 0.18
            spread = 0.30
        else:
            base_col = (96, 170, 255)          # آبیِ jarvis-OS
            hot_col = (215, 235, 255)
            idle = 0.12
            spread = 0.18

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
        breathe = 0.9 + 0.1 * math.sin(t * 1.4)      # تنفسِ ملایمِ سکوت

        # هاله‌ی مرکزیِ آبی (پشتِ نقاط)
        for k in range(9, 0, -1):
            a = max(0, min(60, int(7 * (10 - k) * (0.4 + avg) * breathe)))
            rr = int(radius * (0.12 + 0.11 * k) * (0.9 + avg * 0.4))
            pygame.draw.circle(layer, (*base_col, a), (cx, cy), max(1, rr))

        projected = []
        for i in range(len(self.px)):
            x, y, z = self.px[i], self.py[i], self.pz[i]
            disp = bl[self.pband[i]] * spread * (0.5 + 0.7 * self.plat[i])
            scale = 1.0 + disp
            x *= scale
            y *= scale
            z *= scale
            # چرخش
            x, z = x * cosA - z * sinA, x * sinA + z * cosA
            y, z = y * cosB - z * sinB, y * sinB + z * cosB
            factor = persp / max(60.0, persp - z * radius)
            limb = 1.0 - abs(z)          # نزدیکِ لبه‌ی دیداری روشن‌تر (فرنل)
            projected.append((z, cx + x * radius * factor, cy + y * radius * factor,
                              factor, bl[self.pband[i]], limb))

        projected.sort(key=lambda p: p[0])
        for depth, sx, sy, factor, level, limb in projected:
            b = max(0.0, min(1.0, (depth + 1) / 2))
            glowness = min(1.0, level * 0.55 + limb * 0.5 + b * 0.12)
            col = _lerp_color(base_col, hot_col, glowness)
            alpha = max(0, min(255, int(105 + b * 95 + level * 45 + limb * 55)))
            size = max(1, int((1.3 + b * 2.1 + level * 1.7 + limb * 1.6)
                              * max(0.3, min(2.4, factor))))
            pygame.draw.circle(layer, (*col, alpha), (int(sx), int(sy)), size)

        screen.blit(layer, (0, 0))

        # هستهٔ نورانی (روی خودِ صفحه، بدون سطحِ مربعی)
        core = max(3, int(radius * (0.05 + avg * 0.05)))
        glow_layer = self._layer
        glow_layer.fill((0, 0, 0, 0))
        for k in range(10, 0, -1):
            pygame.draw.circle(glow_layer, (*base_col, 10), (cx, cy), int(core * k * 0.9))
        screen.blit(glow_layer, (0, 0))
        pygame.draw.circle(screen, hot_col, (cx, cy), max(2, core))

        if listening or speaking:
            pr = int(radius * (0.98 + 0.06 * math.sin(t * 6)) * (1 + energy * 0.3))
            ring = pygame.Surface((pr * 2 + 4, pr * 2 + 4), pygame.SRCALPHA)
            pygame.draw.circle(ring, (*base_col, 90), (pr + 2, pr + 2), pr, width=2)
            screen.blit(ring, (cx - pr - 2, cy - pr - 2))
