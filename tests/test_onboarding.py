import json

from jarvis import onboarding
from jarvis.config import Config
from jarvis.onboarding import Onboarding, _clean_title
from jarvis.state import STATE


def _cfg(tmp_path, monkeypatch):
    monkeypatch.setattr(onboarding, "OWNER_FILE", tmp_path / "owner.json")
    monkeypatch.setattr(onboarding, "APP_DIR", tmp_path)
    monkeypatch.setattr("jarvis.onboarding.ensure_dirs", lambda: None)
    monkeypatch.setattr("jarvis.memory.curator.remember", lambda *a, **k: None)
    return Config()


def test_needs_onboarding(tmp_path, monkeypatch):
    monkeypatch.setattr(onboarding, "OWNER_FILE", tmp_path / "owner.json")
    assert onboarding.needs_onboarding()
    (tmp_path / "owner.json").write_text("{}", encoding="utf-8")
    assert not onboarding.needs_onboarding()


def test_clean_title():
    assert _clean_title("همون رئیس صدام کن") == "رئیس"
    assert _clean_title("علی") == "علی"
    assert _clean_title("نه اسم کوچیکم و صدا کن") == ""     # مبهم -> رد


def test_confirmed_flow(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path, monkeypatch)
    ob = Onboarding(cfg)
    ob.start()
    assert STATE.onboarding_active
    # name
    _, m = ob.submit("علی", conf=0.9)
    assert "درسته" in m
    _, m = ob.submit("بله")
    # title
    _, _ = ob.submit("رئیس", conf=0.9)
    _, _ = ob.submit("بله")
    # location
    _, _ = ob.submit("تهران", conf=0.9)
    _, _ = ob.submit("بله")
    # focus
    _, _ = ob.submit("مدیریت ایمیل و تقویم", conf=0.9)
    done, _ = ob.submit("بله")
    assert done and not STATE.onboarding_active
    assert cfg.user_title == "رئیس"
    data = json.loads((tmp_path / "owner.json").read_text(encoding="utf-8"))
    assert data["name"] == "علی" and data["location"] == "تهران"


def test_reject_and_reask(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path, monkeypatch)
    ob = Onboarding(cfg)
    ob.start()
    ob.submit("فلان", conf=0.9)
    _, m = ob.submit("نه")                # رد -> دوباره بپرس
    assert "دوباره" in m
    assert ob.phase == "ask" and ob.i == 0


def test_low_confidence_reasks(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path, monkeypatch)
    ob = Onboarding(cfg)
    ob.start()
    _, m = ob.submit("همهمه", conf=0.2)   # اطمینانِ پایین
    assert "نشنیدم" in m and ob.i == 0
