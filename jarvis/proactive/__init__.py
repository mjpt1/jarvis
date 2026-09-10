"""سیستمِ پیش‌کنشی و حاکمیت (فاز ۵).

- budget: ردیابیِ توکن/هزینه/تعدادِ تماسِ Claude با سقفِ روزانه.
- notifications: صفِ اعلان‌ها با تحویل از راهِ صدا/تلگرام/داشبورد و رعایتِ
  ساعتِ سکوت و سطحِ خودمختاری.
- collectors: جمع‌کننده‌های سیگنال (هوا، تقویم، ایمیل، اخبار).
- engine: هماهنگ‌کننده که همه را به هم وصل می‌کند.
"""

from .budget import BUDGET, Budget
from .engine import ProactiveEngine, proactive_worker
from .notifications import NOTIFY, Notification, autonomy_allows

__all__ = ["BUDGET", "Budget", "NOTIFY", "Notification", "autonomy_allows",
           "ProactiveEngine", "proactive_worker"]
