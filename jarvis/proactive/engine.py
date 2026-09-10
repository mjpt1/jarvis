"""هماهنگ‌کننده‌ی پیش‌کنشی — جمع‌کننده‌ها را اجرا می‌کند و «مرکز فرمان» را نگه می‌دارد."""

from __future__ import annotations

import threading

from ..config import Config
from ..logging_setup import get_logger
from .budget import BUDGET
from .collectors import ALL_COLLECTORS
from .notifications import configure as _cfg_notify

log = get_logger("proactive")


class ProactiveEngine:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.collectors = [C(cfg) for C in ALL_COLLECTORS]

    def start(self) -> None:
        _cfg_notify(self.cfg.autonomy_level, self.cfg.quiet_hours)
        BUDGET.configure(self.cfg.budget_daily_usd, self.cfg.budget_daily_calls)
        for col in self.collectors:
            threading.Thread(target=col.run_forever, daemon=True,
                             name=f"collector-{col.name}").start()
        log.info("سیستمِ پیش‌کنشی فعال شد (سطحِ خودمختاری %d، %d جمع‌کننده).",
                 self.cfg.autonomy_level, len(self.collectors))

    def command_center(self) -> dict:
        from .notifications import recent
        return {
            "autonomy": self.cfg.autonomy_level,
            "budget": BUDGET.summary(),
            "notifications": recent(15),
            "collectors": [c.name for c in self.collectors],
        }


_ENGINE: ProactiveEngine | None = None


def configure(cfg: Config) -> None:
    """تنظیمِ خودمختاری و بودجه — حتی وقتی جمع‌کننده‌ها خاموش‌اند."""
    _cfg_notify(cfg.autonomy_level, cfg.quiet_hours)
    BUDGET.configure(cfg.budget_daily_usd, cfg.budget_daily_calls)


def proactive_worker(cfg: Config) -> None:
    global _ENGINE
    _ENGINE = ProactiveEngine(cfg)
    _ENGINE.start()


def engine() -> ProactiveEngine | None:
    return _ENGINE
