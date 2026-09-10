"""جمع‌کننده‌های سیگنال — هر کدام یک منبع را می‌پاید و در صورتِ تغییرِ مهم اعلان می‌دهد."""

from __future__ import annotations

import datetime

from ..config import Config
from ..logging_setup import get_logger
from ..state import STATE
from .notifications import push

log = get_logger("proactive")


class Collector:
    name = "base"
    interval = 900

    def __init__(self, cfg: Config):
        self.cfg = cfg
        self._state: dict = {}

    def poll(self) -> None:  # override
        raise NotImplementedError

    def run_forever(self) -> None:
        # کمی پخش‌شدگی تا همه با هم اجرا نشوند
        if STATE.stop_event.wait(5):
            return
        while STATE.running:
            try:
                self.poll()
            except Exception as exc:
                log.debug("%s: %s", self.name, exc)
            if STATE.stop_event.wait(self.interval):
                return


class WeatherCollector(Collector):
    name = "weather"

    def __init__(self, cfg):
        super().__init__(cfg)
        self.interval = cfg.collector_weather_interval

    def poll(self):
        with STATE.lock:
            temp = STATE.weather_temp
        if temp is None:
            return
        prev = self._state.get("temp")
        self._state["temp"] = temp
        if prev is None:
            return
        if temp <= 0 and prev > 0:
            push(f"دمای هوا به زیرِ صفر رسید ({temp:.0f} درجه)، مواظب باش قربان.",
                 source="weather", level="warn")
        elif abs(temp - prev) >= 6:
            push(f"دمای هوا از {prev:.0f} به {temp:.0f} درجه تغییر کرد قربان.",
                 source="weather")


class CalendarCollector(Collector):
    name = "calendar"

    def __init__(self, cfg):
        super().__init__(cfg)
        self.interval = cfg.collector_calendar_interval

    def poll(self):
        from ..integrations import google_ws
        if not google_ws.available():
            return
        try:
            svc = google_ws._svc("calendar", "v3")
            now = datetime.datetime.now(datetime.UTC)
            end = now + datetime.timedelta(minutes=self.cfg.calendar_alert_minutes)
            res = svc.events().list(
                calendarId="primary", timeMin=now.isoformat(), timeMax=end.isoformat(),
                singleEvents=True, orderBy="startTime", maxResults=5).execute()
        except Exception:
            return
        for ev in res.get("items", []):
            eid = ev.get("id")
            if eid in self._state:
                continue
            self._state[eid] = True
            start = ev["start"].get("dateTime", ev["start"].get("date", ""))
            push(f"یادآوری: «{ev.get('summary', 'رویداد')}» ساعتِ "
                 f"{start[11:16]} شروع می‌شه قربان.", source="calendar", level="warn")


class MailCollector(Collector):
    name = "mail"

    def __init__(self, cfg):
        super().__init__(cfg)
        self.interval = cfg.collector_mail_interval

    def poll(self):
        from ..integrations import google_ws
        if not google_ws.available():
            return
        try:
            svc = google_ws._svc("gmail", "v1")
            res = svc.users().messages().list(
                userId="me", q="is:unread in:inbox", maxResults=20).execute()
            ids = {m["id"] for m in res.get("messages", [])}
        except Exception:
            return
        seen = self._state.get("ids", set())
        new = ids - seen
        self._state["ids"] = ids
        if seen and new:
            push(f"{len(new)} ایمیلِ جدیدِ خوانده‌نشده داری قربان.",
                 source="mail", level="info")


class NewsCollector(Collector):
    name = "news"

    def __init__(self, cfg):
        super().__init__(cfg)
        self.interval = cfg.collector_news_interval

    def poll(self):
        if not self.cfg.news_interests:
            return
        try:
            import urllib.request
            import xml.etree.ElementTree as ET
            req = urllib.request.Request(self.cfg.news_rss_url,
                                         headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=8) as r:
                root = ET.fromstring(r.read())
        except Exception:
            return
        seen = self._state.setdefault("seen", set())
        for item in root.iter("item"):
            title = (item.findtext("title") or "").strip()
            if not title or title in seen:
                continue
            seen.add(title)
            if any(k in title for k in self.cfg.news_interests):
                push(f"خبرِ مرتبط: {title}", source="news", level="info")


ALL_COLLECTORS = [WeatherCollector, CalendarCollector, MailCollector, NewsCollector]
