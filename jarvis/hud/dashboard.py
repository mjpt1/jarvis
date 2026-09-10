"""چیدمانِ «مرکز فرمانِ» جارویس در pygame — هم‌شکلِ داشبوردِ وب.

سایدبار (راست) · نوار بالا · کره‌ی مرکزی · کارت‌های اطراف · نوار پایین.
"""

from __future__ import annotations

import datetime
import math
import time

import pygame

from ..state import STATE
from . import theme
from .text import blit

_FA = str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")


def fa(x) -> str:
    return str(x).translate(_FA)


_NAV = ["مرکز فرمان", "هستهٔ هوش", "عامل‌ها", "کارها", "حافظه",
        "گفت‌وگوها", "مأموریت‌ها", "ابزارها", "تنظیمات"]

_cache = {"t": 0.0, "ints": {}, "mem": {"active": 0}, "claude": False, "notes": []}


def _refresh(cfg):
    if time.time() - _cache["t"] < 3.5:
        return
    _cache["t"] = time.time()
    try:
        from ..integrations import registry
        _cache["ints"] = registry.status(cfg)
    except Exception:
        _cache["ints"] = {}
    try:
        from ..memory.store import get_store
        _cache["mem"] = get_store().stats()
    except Exception:
        pass
    try:
        from .. import claude_client
        _cache["claude"] = claude_client.available()
    except Exception:
        pass
    try:
        from ..proactive.notifications import recent
        _cache["notes"] = recent(5)
    except Exception:
        _cache["notes"] = []


def _card(screen, rect, title, fonts):
    x, y, w, h = rect
    surf = pygame.Surface((w, h), pygame.SRCALPHA)
    pygame.draw.rect(surf, (10, 24, 36, 235), (0, 0, w, h), border_radius=12)
    pygame.draw.rect(surf, (*theme.CYAN_FAINT, 200), (0, 0, w, h), width=1, border_radius=12)
    screen.blit(surf, (x, y))
    if title:
        blit(screen, fonts.fa_small, title, theme.CYAN_DIM, (x + w - 12, y + 10),
             anchor="topright")
    return pygame.Rect(x + 12, y + (34 if title else 12), w - 24, h - (44 if title else 20))


def _ring(screen, cx, cy, r, pct, label, val, fonts):
    pygame.draw.circle(screen, (15, 38, 54), (cx, cy), r, width=6)
    pct = max(0.0, min(100.0, pct))
    rect = pygame.Rect(cx - r, cy - r, r * 2, r * 2)
    end = -90 + pct / 100.0 * 360
    try:
        pygame.draw.arc(screen, theme.CYAN, rect, math.radians(-end), math.radians(90), 6)
    except Exception:
        pass
    blit(screen, fonts.fa, val, theme.CYAN, (cx, cy - 2), anchor="center")
    blit(screen, fonts.fa_small, label, theme.CYAN_DIM, (cx, cy + r + 12), anchor="center")


def _waveform(screen, cx, y, n, level, t, color):
    for i in range(n):
        ph = t * 6 + i * 0.7
        amp = (0.25 + 0.75 * abs(math.sin(ph))) * (0.3 + level * 1.6)
        bh = max(3, int(18 * min(1.0, amp)))
        bx = cx - (n * 5) // 2 + i * 5
        pygame.draw.rect(screen, color, (bx, y - bh // 2, 3, bh), border_radius=1)


class CommandCenter:
    def __init__(self):
        self._scanlines = None

    def draw(self, screen, t, orb, cfg, fonts, *, speaking, awaiting):
        w, h = screen.get_size()
        _refresh(cfg)
        sw = max(180, int(w * 0.15))         # عرض سایدبار
        topb, botb = 56, 40
        pad = 16
        content_w = w - sw

        with STATE.lock:
            s = STATE
            cpu, ram, disk = s.cpu_percent, s.ram_percent, s.disk_percent
            mic, tts_lvl = s.mic_level, s.tts_level
            convo = s.conversation_active
            voice_on, cam_on, tg_on = s.voice_enabled, s.camera_enabled, s.telegram_enabled
            subtitle, last_heard = s.current_subtitle, s.last_heard_text
            wtemp, wloc = s.weather_temp, s.location_name
            sec_temp, sec_name = s.secondary_temp, s.secondary_name
            events = list(s.event_log)[-6:]
            mem_turns = len(s.chat_history) // 2
            tool_calls = s.tool_call_count
            gate = s.owner_gate_active and not s.owner_present
        level = max(mic, tts_lvl)
        ints = _cache["ints"]
        mem_count = _cache["mem"].get("active", 0)
        claude_ok = _cache["claude"]

        # پس‌زمینه
        screen.fill(theme.BG)

        # ---------- کره‌ی مرکزی ----------
        cx = pad + (content_w - pad) // 2
        cy = topb + (h - topb - botb) // 2
        base_scale = min(content_w, h - topb - botb) * 0.26
        orb.draw(screen, t, cx, cy, base_scale, speaking=speaking, listening=awaiting)
        blit(screen, fonts.num_big, "J A R V I S", theme.WHITE, (cx, cy - 12),
             anchor="center", shaped=False)
        blit(screen, fonts.fa_small, "AI CORE · v8.0", theme.CYAN_DIM, (cx, cy + 22),
             anchor="center", shaped=False)

        # ---------- نوار بالا ----------
        pygame.draw.line(screen, theme.CYAN_FAINT, (0, topb), (content_w, topb), 1)
        ok = cpu < 85 and ram < 92
        pygame.draw.circle(screen, theme.OK if ok else theme.WARN, (24, topb // 2), 5)
        blit(screen, fonts.fa_small, f"وضعیت سیستم · {'بهینه' if ok else 'پرمصرف'}",
             theme.CYAN_DIM, (38, topb // 2), anchor="midleft")
        now = datetime.datetime.now()
        blit(screen, fonts.num, now.strftime("%H:%M:%S"), theme.CYAN,
             (content_w // 2, topb // 2 - 6), anchor="center", shaped=False)
        blit(screen, fonts.fa_small, "اپراتور · فرمانده", theme.CYAN_DIM,
             (content_w - 16, topb // 2), anchor="midright")

        # ---------- نوار پایین ----------
        by = h - botb
        pygame.draw.line(screen, theme.CYAN_FAINT, (0, by), (content_w, by), 1)
        wx = f"{wtemp:.0f}°" if wtemp is not None else "—"
        if sec_temp is not None:
            wx += f"  ·  {sec_name} {sec_temp:.0f}°"
        blit(screen, fonts.fa_small, f"◍ {wloc or '—'}", theme.CYAN_DIM, (16, by + botb // 2),
             anchor="midleft")
        blit(screen, fonts.fa_small, f"☀ {wx}", theme.CYAN_DIM, (170, by + botb // 2),
             anchor="midleft")
        talk = subtitle if speaking else (f"«{last_heard}»" if last_heard else "صحبت با جارویس")
        _waveform(screen, content_w // 2 - 90, by + botb // 2, 6, level, t, theme.CYAN)
        blit(screen, fonts.fa_small, talk, theme.CYAN, (content_w // 2, by + botb // 2),
             anchor="center")
        _waveform(screen, content_w // 2 + 90, by + botb // 2, 6, level, t, theme.CYAN)

        # ---------- سایدبار (راست) ----------
        sx = content_w
        pygame.draw.rect(screen, (7, 17, 27), (sx, 0, sw, h))
        pygame.draw.line(screen, theme.CYAN_FAINT, (sx, 0), (sx, h), 1)
        pygame.draw.circle(screen, theme.CYAN, (sx + sw - 24, 26), 12, width=2)
        pygame.draw.circle(screen, theme.CYAN, (sx + sw - 24, 26), 4)
        blit(screen, fonts.fa_small, "JARVIS", theme.WHITE, (sx + sw - 44, 20),
             anchor="topright", shaped=False)
        for i, item in enumerate(_NAV):
            yy = 62 + i * 30
            on = i == 0
            if on:
                hl = pygame.Surface((sw - 16, 26), pygame.SRCALPHA)
                hl.fill((*theme.CYAN, 34))
                screen.blit(hl, (sx + 8, yy - 4))
                pygame.draw.rect(screen, theme.CYAN, (sx + sw - 10, yy - 4, 2, 26))
            blit(screen, fonts.fa_small, item, theme.WHITE if on else theme.CYAN_DIM,
                 (sx + sw - 16, yy + 9), anchor="midright")

        # بلوکِ وضعیت صدا در سایدبار
        vy = h - 150
        vr = _card(screen, (sx + 10, vy, sw - 20, 130), "وضعیت صدا", fonts)
        _waveform(screen, sx + sw // 2, vr.y + 14, 7, level, t, theme.CYAN)
        vlbl = ("در حال صحبت…" if speaking else "منتظر دیدن چهره…" if gate
                else "حالت مکالمه" if convo else "گوش می‌کنم…" if awaiting else "در انتظار…")
        blit(screen, fonts.fa_small, vlbl, theme.CYAN, (sx + sw // 2, vr.y + 34),
             anchor="center")
        mcx, mcy = sx + sw // 2, vr.y + 74
        col = theme.GOLD if speaking else theme.CYAN
        pygame.draw.circle(screen, col, (mcx, mcy), 22, width=2)
        pygame.draw.circle(screen, col, (mcx, mcy), int(8 + level * 14))

        # ---------- کارت‌های ستونِ چپ ----------
        col_x = pad
        col_w = max(230, int(content_w * 0.26))
        # AI Core Overview
        r = _card(screen, (col_x, topb + pad, col_w, 176), "نمای هستهٔ هوش", fonts)
        core = [
            ("هستهٔ هوش", "فعال" if claude_ok else "محلی", claude_ok),
            ("حافظه", f"{fa(mem_count)} ذخیره", True),
            ("صدا", "آنلاین" if voice_on else "خاموش", voice_on),
            ("بینایی", "فعال" if cam_on else "خاموش", cam_on),
            ("تلگرام", "متصل" if tg_on else "خاموش", tg_on),
            ("سیستم", "بهینه" if ok else "پرمصرف", ok),
        ]
        for i, (nm, st, good) in enumerate(core):
            yy = r.y + i * 24
            blit(screen, fonts.fa_small, nm, theme.WHITE, (r.right, yy), anchor="topright")
            blit(screen, fonts.fa_small, st, theme.OK if good else theme.CYAN_FAINT,
                 (r.x, yy), anchor="topleft")

        # System Monitor rings
        r = _card(screen, (col_x, topb + pad + 192, col_w, 150), "پایشِ سیستم", fonts)
        third = r.w // 3
        _ring(screen, r.x + third // 2, r.y + 40, 34, cpu, "پردازنده", f"{fa(int(cpu))}٪", fonts)
        _ring(screen, r.x + third + third // 2, r.y + 40, 34, ram, "حافظه", f"{fa(int(ram))}٪", fonts)
        _ring(screen, r.x + 2 * third + third // 2, r.y + 40, 34, disk, "دیسک",
              f"{fa(int(disk))}٪", fonts)

        # Memory Insights
        r = _card(screen, (col_x, topb + pad + 358, col_w, 110), "بینشِ حافظه", fonts)
        for i, (v, nm) in enumerate([(mem_count, "حقیقت"), (mem_turns, "دور گفت‌وگو"),
                                     (tool_calls, "فرمان")]):
            xx = r.x + i * (r.w // 3) + (r.w // 6)
            blit(screen, fonts.fa, fa(v), theme.CYAN, (xx, r.y + 6), anchor="midtop")
            blit(screen, fonts.fa_small, nm, theme.CYAN_DIM, (xx, r.y + 34), anchor="midtop")

        # ---------- کارت‌های ستونِ راستِ مرکز ----------
        rc_w = max(240, int(content_w * 0.27))
        rc_x = content_w - rc_w - pad
        # Live Intelligence Feed
        r = _card(screen, (rc_x, topb + pad, rc_w, 176), "جریان اطلاعاتِ زنده", fonts)
        feed = [(n["text"], n["level"]) for n in _cache["notes"]]
        feed.append((f"پردازنده {fa(int(cpu))}٪ · رم {fa(int(ram))}٪", "info"))
        if claude_ok:
            feed.append(("هستهٔ Claude متصل است", "info"))
        for i, (txt, lvl) in enumerate(feed[:6]):
            yy = r.y + i * 24
            c = theme.WARN if lvl in ("warn", "urgent") else theme.CYAN_DIM
            blit(screen, fonts.fa_small, "• " + txt[:46], c, (r.right, yy), anchor="topright")

        # Active Agents
        r = _card(screen, (rc_x, topb + pad + 192, rc_w, 150), "عامل‌های فعال", fonts)
        agents = [("عامل صدا", voice_on), ("عامل بینایی", cam_on), ("عامل حافظه", True),
                  ("عامل وب", bool(ints.get("web"))), ("عامل مأموریت", True),
                  ("عامل تلگرام", tg_on)]
        for i, (nm, act) in enumerate(agents):
            col = i % 2
            row = i // 2
            ay = r.y + row * 30
            pygame.draw.circle(screen, theme.OK if act else theme.CYAN_FAINT,
                               (r.right - col * (r.w // 2) - 6, ay + 8), 4)
            blit(screen, fonts.fa_small, nm, theme.WHITE if act else theme.CYAN_FAINT,
                 (r.right - col * (r.w // 2) - 16, ay + 8), anchor="midright")

        # LLM / Integrations
        r = _card(screen, (rc_x, topb + pad + 358, rc_w, 150), "وضعیت LLM و ادغام‌ها", fonts)
        prov = [("Claude", claude_ok), ("جیمیل", ints.get("google")),
                ("اسپاتیفای", ints.get("spotify")), ("نوشن", ints.get("notion")),
                ("تلگرام", tg_on), ("وب", ints.get("web"))]
        for i, (nm, on) in enumerate(prov):
            col = i % 2
            row = i // 2
            ay = r.y + row * 30
            pygame.draw.circle(screen, theme.OK if on else theme.CYAN_FAINT,
                               (r.right - col * (r.w // 2) - 6, ay + 8), 4)
            blit(screen, fonts.fa_small, nm, theme.WHITE if on else theme.CYAN_FAINT,
                 (r.right - col * (r.w // 2) - 16, ay + 8), anchor="midright")

        # ---------- لاگ رویداد (پایینِ مرکز) ----------
        ly = h - botb - 20 - len(events) * 18
        for i, (ts, txt) in enumerate(events):
            blit(screen, fonts.mono, f"[{ts}] {txt}", theme.CYAN_FAINT,
                 (pad, ly + i * 18), shaped=False)

        # اسکن‌لاین سبک
        if self._scanlines is None or self._scanlines.get_size() != (content_w, h):
            sl = pygame.Surface((content_w, h), pygame.SRCALPHA)
            for yy in range(0, h, 3):
                pygame.draw.line(sl, (0, 0, 0, 16), (0, yy), (content_w, yy))
            self._scanlines = sl
        screen.blit(self._scanlines, (0, 0))

        if speaking and subtitle:
            bar = pygame.Surface((content_w, 44), pygame.SRCALPHA)
            bar.fill((0, 20, 30, 150))
            screen.blit(bar, (0, h - botb - 44))
            blit(screen, fonts.subtitle, subtitle, theme.WHITE,
                 (content_w // 2, h - botb - 22), anchor="center")
