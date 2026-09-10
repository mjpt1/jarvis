"""ردیابیِ مصرفِ Claude — توکن، هزینه‌ی تخمینی، تعدادِ تماس — با سقفِ روزانه."""

from __future__ import annotations

import json
import threading
from datetime import date

from ..logging_setup import get_logger
from ..paths import DATA_DIR, ensure_dirs

log = get_logger("budget")

# قیمت‌های تقریبیِ هر میلیون توکن (دلار) — Haiku 4.5
_PRICE_IN = 1.0
_PRICE_OUT = 5.0

_FILE = DATA_DIR / "budget.json"


class Budget:
    def __init__(self):
        self._lock = threading.Lock()
        self.daily_usd = 0.0        # سقف؛ ۰ = بی‌نهایت
        self.daily_calls = 0
        self._day = str(date.today())
        self._calls = 0
        self._tok_in = 0
        self._tok_out = 0
        self._load()

    def configure(self, daily_usd: float, daily_calls: int) -> None:
        self.daily_usd = daily_usd
        self.daily_calls = daily_calls

    # ------------------------------------------------------------------
    def _load(self) -> None:
        try:
            d = json.loads(_FILE.read_text(encoding="utf-8"))
            if d.get("day") == self._day:
                self._calls = d.get("calls", 0)
                self._tok_in = d.get("tok_in", 0)
                self._tok_out = d.get("tok_out", 0)
        except Exception:
            pass

    def _save(self) -> None:
        try:
            ensure_dirs()
            _FILE.write_text(json.dumps({
                "day": self._day, "calls": self._calls,
                "tok_in": self._tok_in, "tok_out": self._tok_out,
            }), encoding="utf-8")
        except Exception:  # pragma: no cover
            pass

    def _rollover(self) -> None:
        today = str(date.today())
        if today != self._day:
            self._day = today
            self._calls = self._tok_in = self._tok_out = 0

    # ------------------------------------------------------------------
    def record(self, tok_in: int, tok_out: int) -> None:
        with self._lock:
            self._rollover()
            self._calls += 1
            self._tok_in += tok_in
            self._tok_out += tok_out
            self._save()

    def spent_usd(self) -> float:
        return (self._tok_in / 1e6) * _PRICE_IN + (self._tok_out / 1e6) * _PRICE_OUT

    def allowed(self) -> bool:
        """آیا هنوز اجازه‌ی یک تماسِ دیگر هست؟"""
        with self._lock:
            self._rollover()
            if self.daily_calls and self._calls >= self.daily_calls:
                return False
            if self.daily_usd and self.spent_usd() >= self.daily_usd:
                return False
            return True

    def summary(self) -> dict:
        with self._lock:
            self._rollover()
            return {
                "day": self._day,
                "calls": self._calls,
                "tokens_in": self._tok_in,
                "tokens_out": self._tok_out,
                "usd": round(self.spent_usd(), 4),
                "cap_usd": self.daily_usd,
                "cap_calls": self.daily_calls,
            }

    def spoken(self, title: str = "قربان") -> str:
        s = self.summary()
        cap = f" از سقفِ {s['cap_usd']:.2f} دلار" if s["cap_usd"] else ""
        return (f"امروز {s['calls']} بار از Claude پرسیدم؛ حدودِ "
                f"{s['usd']:.3f} دلار{cap} {title}.")


BUDGET = Budget()
