"""پیکربندیِ متمرکزِ همه‌ی ادغام‌ها از روی Config."""

from __future__ import annotations

from ..config import Config
from ..logging_setup import get_logger
from . import (
    face_id,
    filesystem,
    google_ws,
    notion_ws,
    shell,
    spotify_ws,
    telegram_bot,
    vision_tools,
    web,
)

log = get_logger("integrations")


def setup(cfg: Config) -> None:
    if cfg.web_enabled:
        web.configure(cfg.web_max_chars, cfg.web_proxy)
    if cfg.fs_enabled:
        filesystem.configure(cfg.fs_whitelist, cfg.fs_allow_write)
    shell.configure(cfg.cli_enabled, cfg.cli_whitelist)
    if cfg.vision_enabled:
        vision_tools.configure(cfg.yolo_model, cfg.vision_source, cfg.vision_min_confidence)
    if cfg.face_id_enabled:
        face_id.configure(cfg.face_id_tolerance)
    if cfg.spotify_enabled:
        spotify_ws.configure(cfg.spotify_client_id, cfg.spotify_client_secret,
                             cfg.spotify_redirect_uri)
    if cfg.notion_enabled:
        notion_ws.configure(cfg.notion_token)
    if cfg.telegram_enabled:
        telegram_bot.configure(cfg.telegram_bot_token, cfg.telegram_owner_id,
                               cfg.telegram_proxy)

    active = status(cfg)
    log.info("ادغام‌های فعال: %s", "، ".join(k for k, v in active.items() if v) or "هیچ‌کدام")


def status(cfg: Config) -> dict[str, bool]:
    return {
        "web": cfg.web_enabled and web.available(),
        "filesystem": cfg.fs_enabled and filesystem.available(),
        "cli": shell.available(),
        "google": cfg.google_enabled and google_ws.available(),
        "spotify": cfg.spotify_enabled and spotify_ws.available(),
        "notion": cfg.notion_enabled and notion_ws.available(),
        "telegram": cfg.telegram_enabled and telegram_bot.available(),
        "vision": cfg.vision_enabled and vision_tools.available(),
        "face_id": cfg.face_id_enabled and face_id.available(),
    }
