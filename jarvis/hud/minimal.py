"""HUD مینیمالِ سینمایی — هم‌شکلِ رابطِ jarvis-OS.

پس‌زمینه‌ی تیره با وینیت · کره‌ی ذره‌ایِ آبیِ مرکزی با هاله‌ی نرم ·
نوارِ آیکونِ گوشه‌ی بالا-چپ · «JARVIS» + ساعتِ بزرگ بالا-راست ·
کارتِ «در حال پخش» پایین-چپ · آخرین پاسخِ جارویس پایین-راست.
"""

from __future__ import annotations

import datetime
import math

import pygame

from ..state import STATE
from .text import blit

_FA = str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")
_WD = ["دوشنبه", "سه‌شنبه", "چهارشنبه", "پنجشنبه", "جمعه", "شنبه", "یکشنبه"]
_MO = ["ژانویه", "فوریه", "مارس", "آوریل", "مه", "ژوئن", "ژوئیه", "اوت",
       "سپتامبر", "اکتبر", "نوامبر", "دسامبر"]

_BLUE = (70, 150, 230)
_BLUE_DIM = (40, 90, 150)
_BG = (6, 10, 18)


def _fa(x) -> str:
    return str(x).translate(_FA)


class MinimalHUD:
    def __init__(self, size):
        self._vignette = None
        self._glow = None
        self._resize(size)

    def _resize(self, size):
        w, h = size
        # وینیت — تیره در لبه‌ها، شفاف در مرکز (از بیرون به داخل رسم می‌شود)
        v = pygame.Surface((w, h), pygame.SRCALPHA)
        cx, cy = w // 2, h // 2
        maxr = math.hypot(cx, cy)
        steps = 30
        for i in range(steps):
            f = i / (steps - 1)                       # 0 لبه‌ی بیرونی → 1 مرکز
            a = int(165 * (1 - f) ** 1.7)
            pygame.draw.circle(v, (2, 5, 10, a), (cx, cy), int(maxr * (1 - f * 0.62)))
        self._vignette = v
        # هاله‌ی پشتِ کره — چند لایه‌ی نرمِ آبی
        g = pygame.Surface((w, h), pygame.SRCALPHA)
        R = int(min(w, h) * 0.46)
        for i in range(48, 0, -1):
            f = i / 48
            a = int(46 * (1 - f) ** 1.6)
            pygame.draw.circle(g, (36, 96, 190, a), (cx, cy), int(R * f))
        self._glow = g

    def resize(self, size):
        self._resize(size)

    # ------------------------------------------------------------------
    def _toolbar(self, screen, fonts, st):
        """نوارِ آیکونِ گوشه‌ی بالا-چپ — شش وضعیت."""
        x, y, gap, r = 26, 26, 42, 15
        pill_w = gap * 6 + 20
        surf = pygame.Surface((pill_w, 40), pygame.SRCALPHA)
        pygame.draw.rect(surf, (14, 22, 34, 230), (0, 0, pill_w, 40), border_radius=20)
        pygame.draw.rect(surf, (*_BLUE_DIM, 120), (0, 0, pill_w, 40), width=1, border_radius=20)
        screen.blit(surf, (x, y))
        cy = y + 20
        items = [
            ("mic", st["listening"] or st["speaking"]),
            ("screen", True),
            ("cam", st["cam"]),
            ("folder", True),
            ("music", st["music"]),
            ("chat", bool(st["reply"])),
        ]
        for i, (kind, on) in enumerate(items):
            ix = x + 18 + i * gap
            col = _BLUE if on else (60, 78, 100)
            if on:
                gs = pygame.Surface((r * 2, r * 2), pygame.SRCALPHA)
                pygame.draw.circle(gs, (*_BLUE, 40), (r, r), r)
                screen.blit(gs, (ix - r, cy - r))
            self._icon(screen, kind, ix, cy, col)

    def _icon(self, s, kind, x, y, c):
        if kind == "mic":
            pygame.draw.rect(s, c, (x - 3, y - 7, 6, 10), border_radius=3)
            pygame.draw.arc(s, c, (x - 6, y - 3, 12, 12), math.pi, 2 * math.pi, 2)
            pygame.draw.line(s, c, (x, y + 3), (x, y + 7), 2)
        elif kind == "screen":
            pygame.draw.rect(s, c, (x - 8, y - 6, 16, 11), width=2, border_radius=2)
            pygame.draw.line(s, c, (x - 3, y + 8), (x + 3, y + 8), 2)
        elif kind == "cam":
            pygame.draw.rect(s, c, (x - 8, y - 5, 16, 11), width=2, border_radius=2)
            pygame.draw.circle(s, c, (x, y), 3, width=2)
        elif kind == "folder":
            pygame.draw.rect(s, c, (x - 8, y - 4, 16, 10), width=2, border_radius=2)
            pygame.draw.line(s, c, (x - 8, y - 4), (x - 2, y - 4), 2)
        elif kind == "music":
            pygame.draw.circle(s, c, (x - 4, y + 5), 3)
            pygame.draw.circle(s, c, (x + 5, y + 3), 3)
            pygame.draw.line(s, c, (x - 1, y + 5), (x - 1, y - 6), 2)
            pygame.draw.line(s, c, (x + 8, y + 3), (x + 8, y - 8), 2)
            pygame.draw.line(s, c, (x - 1, y - 6), (x + 8, y - 8), 2)
        elif kind == "chat":
            pygame.draw.rect(s, c, (x - 8, y - 6, 16, 11), width=2, border_radius=3)
            pygame.draw.polygon(s, c, [(x - 3, y + 5), (x + 1, y + 5), (x - 3, y + 9)])

    # ------------------------------------------------------------------
    def draw(self, screen, t, orb, cfg, fonts, *, speaking, awaiting):
        w, h = screen.get_size()
        if self._vignette.get_size() != (w, h):
            self._resize((w, h))

        with STATE.lock:
            s = STATE
            convo, mic, tts_lvl = s.conversation_active, s.mic_level, s.tts_level
            cam_on = s.camera_enabled
            subtitle, last_heard = s.current_subtitle, s.last_heard_text
            reply = s.current_subtitle or getattr(s, "last_reply", "")
            gate = s.owner_gate_active and not s.owner_present
            music_np = getattr(s, "now_playing", "")
            ob_active = s.onboarding_active
            ob_q = s.onboarding_question
            dl = s.download_status
        level = max(mic, tts_lvl)
        title = getattr(cfg, "user_title", "قربان")

        screen.fill(_BG)
        screen.blit(self._glow, (0, 0))

        cx, cy = w // 2, h // 2
        base_scale = min(w, h) * 0.30
        orb.draw(screen, t, cx, cy, base_scale, speaking=speaking, listening=awaiting)

        screen.blit(self._vignette, (0, 0))

        # نوار آیکون
        self._toolbar(screen, fonts, {
            "listening": awaiting or convo, "speaking": speaking, "cam": cam_on,
            "music": bool(music_np), "reply": bool(reply),
        })

        # بالا-راست: JARVIS + ساعت + تاریخ
        now = datetime.datetime.now()
        blit(screen, fonts.num_big, "JARVIS", (210, 225, 240), (w - 30, 24),
             anchor="topright", shaped=False)
        clock_font = fonts.num_big
        blit(screen, clock_font, now.strftime("%H:%M"), _BLUE, (w - 30, 62),
             anchor="topright", shaped=False)
        date_s = f"{_WD[now.weekday()]} {_fa(now.day)} {_MO[now.month - 1]} {_fa(now.year)}"
        blit(screen, fonts.fa_small, date_s, _BLUE_DIM, (w - 30, 116), anchor="topright")

        # پایین-چپ: در حال پخش
        if music_np:
            cardw, cardh = 300, 66
            ox, oy = 26, h - 26 - cardh
            surf = pygame.Surface((cardw, cardh), pygame.SRCALPHA)
            pygame.draw.rect(surf, (12, 20, 32, 235), (0, 0, cardw, cardh), border_radius=12)
            pygame.draw.rect(surf, (*_BLUE_DIM, 120), (0, 0, cardw, cardh), width=1,
                             border_radius=12)
            screen.blit(surf, (ox, oy))
            pygame.draw.rect(screen, (*_BLUE, 55), (ox + 10, oy + 11, 44, 44), border_radius=8)
            pygame.draw.polygon(screen, _BLUE, [(ox + 26, oy + 22), (ox + 26, oy + 44),
                                                (ox + 42, oy + 33)])
            tw = cardw - 68
            name = music_np
            while name and fonts.fa_small.size(name)[0] > tw:
                name = name[:-2]
            blit(screen, fonts.fa_small, "در حال پخش", _BLUE_DIM, (ox + cardw - 12, oy + 8),
                 anchor="topright")
            blit(screen, fonts.fa_small, name or music_np[:20], (210, 225, 240),
                 (ox + cardw - 12, oy + 32), anchor="topright")

        # آشناییِ اولیه — پرسشِ فعلی وسطِ صفحه
        if ob_active and ob_q:
            box = pygame.Surface((min(w - 120, 900), 96), pygame.SRCALPHA)
            pygame.draw.rect(box, (10, 18, 30, 235), box.get_rect(), border_radius=14)
            pygame.draw.rect(box, (*_BLUE, 150), box.get_rect(), width=1, border_radius=14)
            bx = (w - box.get_width()) // 2
            screen.blit(box, (bx, h - 220))
            blit(screen, fonts.fa_small, "آشناییِ اولیه", _BLUE_DIM,
                 (w // 2, h - 210), anchor="midtop")
            blit(screen, fonts.fa, ob_q, (220, 235, 250), (w // 2, h - 186),
                 anchor="midtop")
            blit(screen, fonts.fa_small, "پاسخ‌تون رو بگید…", _BLUE,
                 (w // 2, h - 150), anchor="midtop")

        # نوارِ دانلودِ مدل (اگر در جریان است) — بالای نوارِ پایین
        if dl:
            blit(screen, fonts.fa_small, f"⬇ {dl}", _BLUE_DIM, (26, h - 118),
                 anchor="bottomleft")

        # پایین-راست: آخرین پاسخ / وضعیت
        status_line = (subtitle if speaking else
                       (f"«{last_heard}»" if last_heard else
                        ("منتظر دیدنِ چهره‌ی شما…" if gate else
                         "گوش می‌کنم…" if (awaiting or convo) else
                         f"در خدمتم {title}")))
        blit(screen, fonts.fa_small, status_line, (150, 190, 210), (w - 30, h - 40),
             anchor="bottomright")
        # موج کوچک زیر متن
        for i in range(9):
            ph = t * 5 + i * 0.6
            bh = max(2, int(10 * (0.3 + 0.7 * abs(math.sin(ph))) * (0.4 + level * 1.4)))
            bx = w - 30 - i * 7
            pygame.draw.rect(screen, _BLUE, (bx, h - 24 - bh // 2, 3, bh), border_radius=1)
