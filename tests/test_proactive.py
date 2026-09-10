from jarvis.config import Config
from jarvis.proactive import notifications as N
from jarvis.proactive.budget import Budget
from jarvis.proactive.collectors import WeatherCollector


def test_budget_records_and_caps(tmp_path, monkeypatch):
    monkeypatch.setattr("jarvis.proactive.budget._FILE", tmp_path / "b.json")
    b = Budget()
    b.configure(daily_usd=0.0, daily_calls=2)
    assert b.allowed()
    b.record(1000, 500)
    b.record(1000, 500)
    assert not b.allowed()                      # به سقفِ تماس رسید
    s = b.summary()
    assert s["calls"] == 2 and s["usd"] > 0


def test_budget_usd_cap(tmp_path, monkeypatch):
    monkeypatch.setattr("jarvis.proactive.budget._FILE", tmp_path / "b2.json")
    b = Budget()
    b.configure(daily_usd=0.001, daily_calls=0)
    b.record(2_000_000, 0)                      # 2$ ورودی
    assert not b.allowed()


def test_autonomy_gating():
    N.set_autonomy(0)
    assert not N.autonomy_allows("notify")
    N.set_autonomy(1)
    assert N.autonomy_allows("notify")
    assert not N.autonomy_allows("propose_mission")
    N.set_autonomy(3)
    assert N.autonomy_allows("propose_mission")
    assert not N.autonomy_allows("auto_mission")


def test_quiet_hours():
    import datetime
    N.configure(1, [23, 8])
    assert N.in_quiet_hours(datetime.datetime(2026, 1, 1, 2, 0))
    assert not N.in_quiet_hours(datetime.datetime(2026, 1, 1, 14, 0))


def test_weather_collector_alerts(monkeypatch):
    pushed = []
    monkeypatch.setattr("jarvis.proactive.collectors.push",
                        lambda text, **k: pushed.append(text))
    from jarvis.state import STATE
    col = WeatherCollector(Config())
    with STATE.lock:
        STATE.weather_temp = 10.0
    col.poll()                                  # اولین بار: فقط ثبت
    with STATE.lock:
        STATE.weather_temp = 1.0
    col.poll()                                  # افتِ ۹ درجه‌ای -> اعلان
    assert pushed
