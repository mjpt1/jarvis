"""راه‌اندازی logging — هم روی کنسول هم فایل چرخشی."""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler

from .paths import LOG_DIR, ensure_dirs

_CONFIGURED = False


def setup(level: int = logging.INFO) -> logging.Logger:
    global _CONFIGURED
    logger = logging.getLogger("jarvis")
    if _CONFIGURED:
        return logger

    ensure_dirs()
    logger.setLevel(level)
    fmt = logging.Formatter("%(asctime)s  %(levelname)-7s  %(name)s: %(message)s",
                            datefmt="%H:%M:%S")

    console = logging.StreamHandler()
    console.setFormatter(fmt)
    logger.addHandler(console)

    try:
        fileh = RotatingFileHandler(LOG_DIR / "jarvis.log", maxBytes=1_000_000,
                                    backupCount=3, encoding="utf-8")
        fileh.setFormatter(fmt)
        logger.addHandler(fileh)
    except Exception:  # pragma: no cover
        pass

    logger.propagate = False
    _CONFIGURED = True
    return logger


def get_logger(name: str = "jarvis") -> logging.Logger:
    if not _CONFIGURED:
        setup()
    return logging.getLogger(name if name.startswith("jarvis") else f"jarvis.{name}")
