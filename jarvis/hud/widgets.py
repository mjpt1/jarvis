"""ویجت‌های HUD — همه توابع خالصِ رسم که از STATE می‌خوانند."""

from __future__ import annotations

import datetime
import math

import pygame

from ..state import STATE
from . import theme
from .text import blit, render


def corner_ticks(screen, w, h, t):
    surf = pygame.Surface((w, h), pygame.SRCALPHA)
    col = (0, 150, 200, 120)
    m, ln = 40, 70
    pull = int(6 * math.sin(t * 1.5))
    for cx, cy, sx, sy in ((m, m, 1, 1), (w - m, m, -1, 1),
                           (m, h - m, 1, -1), (w - m, h - m, -1, -1)):
        pygame.draw.line(surf, col, (cx, cy), (cx + sx * (ln + pull), cy), 2)
        pygame.draw.line(surf, col, (cx, cy), (cx, cy + sy * (ln + pull)), 2)
    screen.blit(surf, (0, 0))


def scanlines(screen, w, h):
    surf = pygame.Surface((w, h), pygame.SRCALPHA)
    for y in range(0, h, 3):
        pygame.draw.line(surf, (0, 0, 0, 22), (0, y), (w, y))
    screen.blit(surf, (0, 0))


def ring_gauge(screen, cx, cy, radius, percent, color, fonts, label, value):
    pygame.draw.circle(screen, theme.GAUGE_BG, (cx, cy), radius, width=6)
    percent = max(0.0, min(100.0, percent))
    rect = pygame.Rect(cx - radius, cy - radius, radius * 2, radius * 2)
    end = -90 + percent / 100.0 * 360
    try:
        pygame.draw.arc(screen, color, rect, math.radians(-end), math.radians(90), 6)
    except Exception:
        pass
    blit(screen, fonts.num, value, theme.WHITE, (cx, cy - 4), anchor="center", shaped=False)
    blit(screen, fonts.fa_small, label, theme.CYAN_DIM, (cx, cy + 20), anchor="center")


def system_gauges(screen, x, y, fonts):
    with STATE.lock:
        cpu, ram, batt = STATE.cpu_percent, STATE.ram_percent, STATE.battery_percent
    gap = 112
    ring_gauge(screen, x, y, 44, cpu, theme.CYAN, fonts, "CPU", f"{cpu:.0f}%")
    ring_gauge(screen, x + gap, y, 44, ram, theme.OK, fonts, "RAM", f"{ram:.0f}%")
    if batt is not None:
        c = theme.WARN if batt < 20 else theme.CYAN
        ring_gauge(screen, x + gap * 2, y, 44, batt, c, fonts, "BATT", f"{batt:.0f}%")


def network_sparkline(screen, x, y, w_box, h_box, fonts):
    with STATE.lock:
        history = list(STATE.net_history)
    blit(screen, fonts.fa_small, "شبکه (KB/s)", theme.CYAN_DIM, (x, y - 18))
    pygame.draw.rect(screen, theme.GAUGE_BG, (x, y, w_box, h_box), width=1)
    if len(history) < 2:
        return
    maxv = max(history) or 1.0
    n = len(history)
    pts = [(x + int(i / (n - 1) * w_box),
            y + h_box - int(min(v / maxv, 1.0) * h_box)) for i, v in enumerate(history)]
    pygame.draw.lines(screen, theme.CYAN, False, pts, 2)


def mic_meter(screen, x, y, w_box, h_box, fonts):
    with STATE.lock:
        level = STATE.mic_level
        voice_on = STATE.voice_enabled
        awaiting = STATE.awaiting_command
        convo = STATE.conversation_active
    blit(screen, fonts.fa_small, "میکروفون", theme.CYAN_DIM, (x, y - 18))
    pygame.draw.rect(screen, theme.GAUGE_BG, (x, y, w_box, h_box), width=1)
    if not voice_on:
        blit(screen, fonts.fa_small, "غیرفعال", theme.WARN, (x + 6, y + 4))
        return
    bars = 20
    lit = int(level * bars)
    bw = w_box / bars
    for i in range(bars):
        c = theme.OK if i < bars * 0.6 else theme.WARN
        col = c if i < lit else theme.GAUGE_BG
        pygame.draw.rect(screen, col, (x + i * bw + 1, y + 2, bw - 2, h_box - 4))
    if convo:
        blit(screen, fonts.fa_small, "حالت مکالمه — بگویید «بسه» تا تمام شود",
             theme.OK, (x, y + h_box + 4))
    elif awaiting:
        blit(screen, fonts.fa_small, "منتظر دستور…", theme.OK, (x, y + h_box + 4))


def clock_panel(screen, x, y, fonts):
    now = datetime.datetime.now()
    blit(screen, fonts.num_big, now.strftime("%H:%M"), theme.CYAN, (x, y),
         anchor="midtop", shaped=False)
    blit(screen, fonts.fa_small, now.strftime("%Y-%m-%d"), theme.CYAN_DIM, (x, y + 46),
         anchor="midtop", shaped=False)


def weather_panel(screen, x, y, fonts):
    with STATE.lock:
        temp, loc = STATE.weather_temp, STATE.location_name
    if temp is None:
        blit(screen, fonts.fa_small, "آب‌وهوا: در حال دریافت…", theme.CYAN_DIM, (x, y),
             anchor="topright")
        return
    blit(screen, fonts.num, f"{temp:.0f} C", theme.CYAN, (x, y), anchor="topright", shaped=False)
    if loc:
        blit(screen, fonts.fa_small, loc, theme.CYAN_DIM, (x, y + 26), anchor="topright")


def secondary_panel(screen, x, y, fonts, tz_name: str):
    """ساعت و دمای مکان دوم (مونکتون، نیوبرانزویک)."""
    with STATE.lock:
        temp, name = STATE.secondary_temp, STATE.secondary_name
    try:
        from zoneinfo import ZoneInfo
        now = datetime.datetime.now(ZoneInfo(tz_name))
        tstr = now.strftime("%H:%M")
    except Exception:
        tstr = "--:--"
    label = name or "مونکتون"
    blit(screen, fonts.fa_small, label, theme.CYAN_DIM, (x, y), anchor="topright")
    line = f"{tstr}" + (f"   {temp:.0f} C" if temp is not None else "")
    blit(screen, fonts.num, line, theme.CYAN, (x, y + 18), anchor="topright", shaped=False)


def author_credit(screen, w, h, fonts, author: str):
    if not author:
        return
    blit(screen, fonts.fa_small, f"طراحی و توسعه: {author}", theme.CYAN_FAINT,
         (w - 16, h - 20), anchor="bottomright")


def log_panel(screen, x, y, fonts):
    with STATE.lock:
        entries = list(STATE.event_log)[-6:]
    for i, (ts, text) in enumerate(entries):
        blit(screen, fonts.mono, f"[{ts}] {text}", theme.CYAN_FAINT, (x, y + i * 20),
             shaped=False)


def subtitle_bar(screen, w, h, fonts, subtitle):
    if not subtitle:
        return
    bar = pygame.Surface((w, 74), pygame.SRCALPHA)
    bar.fill((0, 20, 30, 170))
    screen.blit(bar, (0, h - 94))
    blit(screen, fonts.subtitle, subtitle, theme.WHITE, (w // 2, h - 57), anchor="center")


def status_chips(screen, x, y, fonts):
    """نشانگرهای کوچک وضعیت دوربین/صدا/Claude."""
    from .. import claude_client
    with STATE.lock:
        cam, voice = STATE.camera_enabled, STATE.voice_enabled
    items = [("دوربین", cam), ("صدا", voice), ("Claude", claude_client.available())]
    cx = x
    for label, on in items:
        col = theme.OK if on else theme.CYAN_FAINT
        pygame.draw.circle(screen, col, (cx, y), 5)
        r = blit(screen, fonts.fa_small, label, col, (cx + 12, y), anchor="midleft")
        cx = r.right + 20


def loading(screen, w, h, fonts, progress):
    done, total = progress
    blit(screen, fonts.fa, f"در حال آماده‌سازی صداها… {done}/{total}", theme.CYAN,
         (w // 2, h // 2 + 130), anchor="center")


def debug_hud(screen, fonts):
    with STATE.lock:
        s = STATE
        lines = [
            f"face: {'YES' if s.face_present else 'NO'}  count={s.face_count}",
            f"yaw={s.yaw:6.1f}  pitch={s.pitch:6.1f}  roll={s.roll:6.1f}",
            f"ear={s.ear:5.3f}  area={s.face_area_ratio:5.3f}",
            f"mic:{'MUTED' if s.audio_muted else 'live'}  "
            f"{'cmd?' if s.awaiting_command else 'wake?'}  lvl={s.mic_level:.2f}",
            f"partial: {s.partial_text}",
            f"heard: {s.last_heard_text}",
            "[D]debug [M]mute [F11]window [0-4]test [ESC]exit",
        ]
    for i, ln in enumerate(lines):
        blit(screen, fonts.mono, ln, theme.CYAN, (20, 20 + i * 22), shaped=False)
