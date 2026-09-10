"""حلقه‌ی اصلی برنامه و اتصال همه‌ی اجزا."""

from __future__ import annotations

import os
import threading
import time

import pygame

from . import claude_client, reports, tts
from .commands import CommandEngine
from .config import Config
from .hud import widgets
from .hud.orb import Orb
from .hud.theme import Fonts
from .logging_setup import get_logger, setup
from .state import STATE

log = get_logger("app")

MANUAL_TEST_KEYS = {
    pygame.K_0: "SYSTEM_READY", pygame.K_1: "TRACKING_LOCKED",
    pygame.K_2: "TRACKING_LOST", pygame.K_3: "INTRUDER", pygame.K_4: "FATIGUE",
}


def _enable_dpi_awareness() -> None:
    if os.name != "nt":
        return
    try:
        import ctypes
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass


def _emit_event_line(text: str) -> None:
    tts.say(text)


def run(cfg: Config, *, smoke_frames: int | None = None) -> None:
    setup()
    _enable_dpi_awareness()

    tts.configure(cfg.voice)
    reports.configure(cfg.user_title, cfg.news_rss_url, author=cfg.author,
                      secondary_city=cfg.secondary_city, secondary_tz=cfg.secondary_tz)
    claude_client.configure(api_key=cfg.anthropic_api_key, model=cfg.anthropic_model,
                            max_turns=cfg.chat_history_max_turns, title=cfg.user_title,
                            allow_actions=cfg.claude_can_run_actions)

    from .integrations import registry as _integrations
    _integrations.setup(cfg)

    from .proactive import engine as _proactive
    _proactive.configure(cfg)

    engine = CommandEngine(cfg)

    if cfg.mission_enabled:
        from .missions.engine import attach as _attach_missions
        _attach_missions(engine)

    pygame.init()
    pygame.mixer.pre_init(44100, -16, 2, 512)
    pygame.mixer.init()
    pygame.mixer.set_num_channels(16)

    fullscreen = cfg.fullscreen
    screen = _make_screen(fullscreen, cfg.windowed_size)
    w, h = screen.get_size()
    pygame.display.set_caption("J.A.R.V.I.S.")
    clock = pygame.time.Clock()

    scale = min(w / 1280, h / 800)
    fonts = Fonts(scale=max(0.75, scale))
    orb = Orb((w, h), points=cfg.orb_points, bands=cfg.orb_bands)
    from .hud.dashboard import CommandCenter
    cc = CommandCenter() if cfg.hud_command_center else None

    # --- تردهای پس‌زمینه ---
    from .audio_in import voice_worker
    from .vision import camera_worker, event_lines
    from .workers import system_stats_worker, weather_worker

    prebuild_lines = engine.static_lines + event_lines(cfg.user_title)
    threading.Thread(target=tts.prebuild, args=(prebuild_lines,),
                     kwargs={"progress_cb": _cache_progress}, daemon=True).start()

    if cfg.enable_camera:
        threading.Thread(target=camera_worker, args=(cfg, _emit_event_line), daemon=True).start()
    if cfg.enable_voice:
        threading.Thread(target=voice_worker, args=(cfg, engine), daemon=True).start()
    threading.Thread(target=system_stats_worker, args=(cfg,), daemon=True).start()
    threading.Thread(target=weather_worker, args=(cfg,), daemon=True).start()

    if cfg.memory_enabled and cfg.nightly_consolidation_hour:
        from .workers import nightly_consolidation_worker
        threading.Thread(target=nightly_consolidation_worker, args=(cfg,), daemon=True).start()

    if _integrations.status(cfg).get("telegram"):
        from .integrations.telegram_bot import worker as _tg_worker
        threading.Thread(target=_tg_worker, daemon=True).start()

    if cfg.web_dashboard_enabled:
        from .web import available as _web_ok
        from .web import run_server as _web_run
        if _web_ok():
            threading.Thread(target=_web_run, args=(cfg,), daemon=True).start()

    if cfg.proactive_enabled and cfg.autonomy_level > 0:
        from .proactive.engine import proactive_worker
        threading.Thread(target=proactive_worker, args=(cfg,), daemon=True).start()

    if cfg.mission_enabled:
        def _resume():
            time.sleep(6)
            try:
                from .missions.engine import _ENGINE
                if _ENGINE:
                    _ENGINE.resume_unfinished()
            except Exception as exc:      # pragma: no cover
                log.debug("ادامه‌ی مأموریت ناتمام ناموفق: %s", exc)
        threading.Thread(target=_resume, daemon=True).start()

    show_debug = cfg.show_debug_on_start
    start = time.time()
    frames = 0

    while STATE.running:
        t = time.time() - start
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                STATE.stop()
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    STATE.stop()
                elif event.key == pygame.K_d:
                    show_debug = not show_debug
                elif event.key == pygame.K_m:
                    with STATE.lock:
                        STATE.audio_muted = not STATE.audio_muted
                elif event.key == pygame.K_F11:
                    fullscreen = not fullscreen
                    screen = _make_screen(fullscreen, cfg.windowed_size)
                    w, h = screen.get_size()
                    scale = max(0.75, min(w / 1280, h / 800))
                    orb.resize((w, h))
                elif event.key in MANUAL_TEST_KEYS and cfg.enable_camera is not None:
                    _fire_manual(MANUAL_TEST_KEYS[event.key], cfg.user_title)

        with STATE.lock:
            speaking = STATE.speaking
            subtitle = STATE.current_subtitle
            cache_ready = STATE.cache_ready
            cache_progress = STATE.cache_progress
            awaiting = STATE.awaiting_command

        if cc is not None:
            cc.draw(screen, t, orb, cfg, fonts, speaking=speaking, awaiting=awaiting)
            widgets.author_credit(screen, w, h, fonts, cfg.author)
        else:
            cx, cy = w // 2, h // 2
            base_scale = min(w, h) * 0.30
            screen.fill(widgets.theme.BG)
            widgets.corner_ticks(screen, w, h, t)
            orb.draw(screen, t, cx, cy, base_scale, speaking=speaking, listening=awaiting)
            widgets.system_gauges(screen, int(120 * scale), int(110 * scale), fonts)
            widgets.network_sparkline(screen, 24, int(210 * scale), 220, 46, fonts)
            widgets.mic_meter(screen, 24, int(300 * scale), 220, 26, fonts)
            if cfg.memory_enabled:
                widgets.memory_panel(screen, 24, int(372 * scale), fonts)
            widgets.clock_panel(screen, w // 2, 26, fonts)
            widgets.weather_panel(screen, w - 40, 28, fonts)
            widgets.secondary_panel(screen, w - 40, int(96 * scale), fonts, cfg.secondary_tz)
            widgets.log_panel(screen, 24, h - 200, fonts)
            widgets.status_chips(screen, 28, h - 232, fonts)
            widgets.author_credit(screen, w, h, fonts, cfg.author)
            widgets.subtitle_bar(screen, w, h, fonts, subtitle)
            widgets.scanlines(screen, w, h)

        if not cache_ready:
            widgets.loading(screen, w, h, fonts, cache_progress)
        if show_debug:
            widgets.debug_hud(screen, fonts)

        pygame.display.flip()
        clock.tick(cfg.fps)

        frames += 1
        if smoke_frames is not None and frames >= smoke_frames:
            STATE.stop()

    STATE.stop()
    time.sleep(0.2)
    pygame.quit()
    log.info("خداحافظ.")


def _make_screen(fullscreen: bool, windowed_size):
    if fullscreen:
        info = pygame.display.Info()
        return pygame.display.set_mode((info.current_w, info.current_h), pygame.FULLSCREEN)
    return pygame.display.set_mode(windowed_size, pygame.RESIZABLE)


def _cache_progress(done: int, total: int) -> None:
    with STATE.lock:
        STATE.cache_progress = (done, total)


def _fire_manual(name: str, title: str) -> None:
    import random

    from .vision import EVENTS
    line = random.choice(EVENTS[name]["lines"]).replace("{t}", title)
    STATE.log(f"TEST:{name}")
    tts.say(line)
