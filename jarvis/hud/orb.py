"""کره‌ی ذرات هولوگرافیک — با سطوحِ از پیش تخصیص‌یافته برای FPS بهتر."""

from __future__ import annotations

import math
import random

import pygame

from . import theme


def _fibonacci_sphere(samples: int):
    pts = []
    phi = math.pi * (3.0 - math.sqrt(5.0))
    for i in range(samples):
        y = 1 - (i / float(samples - 1)) * 2
        r = math.sqrt(max(0.0, 1 - y * y))
        t = phi * i
        pts.append((math.cos(t) * r, y, math.sin(t) * r))
    return pts


class Orb:
    def __init__(self, size: tuple[int, int], points: int = 170):
        self.points = _fibonacci_sphere(points)
        self._layer = pygame.Surface(size, pygame.SRCALPHA)
        self._pulse = 0.5

    def resize(self, size):
        self._layer = pygame.Surface(size, pygame.SRCALPHA)

    def draw(self, screen, t: float, cx: int, cy: int, base_scale: float,
             *, speaking: bool, listening: bool):
        if speaking:
            self._pulse += random.uniform(-0.15, 0.2)
            self._pulse = max(0.2, min(1.5, self._pulse))
            color = theme.ORB_SPEAK
            rot_speed = 1.6
        elif listening:
            self._pulse = 0.7 + 0.3 * math.sin(t * 4.0)
            color = theme.ORB_LISTEN
            rot_speed = 0.9
        else:
            self._pulse = 0.5 + 0.5 * math.sin(t * 1.1)
            color = theme.ORB_IDLE
            rot_speed = 0.5

        radius = base_scale * (0.75 + self._pulse * 0.25)
        ax, ay = t * 0.3, t * rot_speed
        cosA, sinA = math.cos(ay), math.sin(ay)
        cosB, sinB = math.cos(ax), math.sin(ax)

        layer = self._layer
        layer.fill((0, 0, 0, 0))

        projected = []
        for x, y, z in self.points:
            x, z = x * cosA - z * sinA, x * sinA + z * cosA
            y, z = y * cosB - z * sinB, y * sinB + z * cosB
            factor = 260 / (260 - z * radius)
            projected.append((z, cx + x * radius * factor, cy + y * radius * factor))
        projected.sort(key=lambda p: p[0])

        for depth, px, py in projected:
            b = (depth + 1) / 2
            size = max(1, int(2 + b * 4))
            alpha = int(55 + b * 200)
            pygame.draw.circle(layer, (*color, alpha), (int(px), int(py)), size)

        # هاله‌ی مرکزی
        for i in range(7, 0, -1):
            a = int(9 * (8 - i))
            r = int(radius * 26 * (i / 7))
            pygame.draw.circle(layer, (*color, a), (cx, cy), r)

        # حلقه‌های مداری
        for i, _tilt in enumerate((0.25, -0.35, 0.15)):
            rw = int(radius * (150 + i * 26))
            rh = int(rw * (abs(math.sin(t * 0.4 + i)) * 0.25 + 0.08))
            rect = pygame.Rect(0, 0, rw, rh)
            rect.center = (cx, cy)
            pygame.draw.ellipse(layer, (*color, 70), rect, width=1)

        screen.blit(layer, (0, 0))
        pygame.draw.circle(screen, theme.WHITE, (cx, cy), max(2, int(radius * 10)))

        if listening:
            pulse_r = int(radius * (34 + 8 * math.sin(t * 6)))
            pygame.draw.circle(screen, theme.ORB_LISTEN, (cx, cy), pulse_r, width=2)
