import json

from jarvis.config import Config
from jarvis import onboarding
from jarvis.onboarding import Onboarding
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


def test_full_flow_learns_owner(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path, monkeypatch)
    ob = Onboarding(cfg)
    ob.start()
    assert STATE.onboarding_active
    done, _ = ob.submit("علی")
    assert not done
    done, _ = ob.submit("رئیس")
    done, _ = ob.submit("تهران")
    done, msg = ob.submit("مدیریت ایمیل و تقویم")
    assert done
    assert not STATE.onboarding_active
    assert cfg.user_title == "رئیس"
    data = json.loads((tmp_path / "owner.json").read_text(encoding="utf-8"))
    assert data["name"] == "علی" and data["location"] == "تهران"
    assert data["onboarded"] is True


def test_skip_answer(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path, monkeypatch)
    ob = Onboarding(cfg)
    ob.start()
    ob.submit("رد کن")            # name skipped
    data_i = ob.i
    assert data_i == 1
    assert "name" not in ob.answers
