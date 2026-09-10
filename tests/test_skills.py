import pytest

from jarvis.config import Config
from jarvis.commands import CommandEngine
from jarvis.skills.lab import dry_run, validate
from jarvis.skills.store import Skill, SkillStore


class _Reg:
    def __init__(self, names):
        self._n = set(names)

    def __contains__(self, k):
        return k in self._n

    def get(self, k):
        class T:
            dangerous = k == "fs_write"

            def run(self, **kw):
                class R:
                    output = "ok"
                return R()
        return T() if k in self._n else None


def test_validate_rejects_unknown_tool():
    ok, msg = validate([{"tool": "nope"}], _Reg(["say"]))
    assert not ok and "JRV-SKL-001" in msg


def test_validate_ok():
    ok, _ = validate([{"tool": "say", "args": {"text": "x"}}], _Reg(["say"]))
    assert ok


def test_dry_run_simulates_writes():
    steps = [{"tool": "say", "args": {"text": "hi"}},
             {"tool": "fs_write", "args": {"path": "a", "content": "b"}}]
    ok, report = dry_run(steps, _Reg(["say", "fs_write"]))
    assert ok
    assert "say" in report and "در اجرای واقعی" in report


def test_skill_store_roundtrip(tmp_path):
    s = SkillStore(tmp_path / "sk.json")
    s.save(Skill(name="صبح", steps=[{"tool": "say", "args": {"text": "صبح بخیر"}}]))
    s2 = SkillStore(tmp_path / "sk.json")
    assert s2.find("صبح") is not None
    assert s2.get("صبح").steps[0]["tool"] == "say"


@pytest.fixture
def engine(tmp_path):
    cfg = Config()
    cfg.music_dir = str(tmp_path)
    cfg.anthropic_api_key = ""
    return CommandEngine(cfg)


def test_skill_manager_run(engine, tmp_path, monkeypatch):
    from jarvis.skills import store as sstore
    monkeypatch.setattr(sstore, "_STORE", SkillStore(tmp_path / "s.json"))
    said = []
    monkeypatch.setattr("jarvis.tts.say", lambda *a, **k: said.append(a[0] if a else ""))
    mgr = engine._skills()
    mgr.store.save(Skill(name="تست", steps=[{"tool": "say", "args": {"text": "سلام"}}]))
    out = mgr.run("تست")
    assert "اجرا شد" in out
