import json

import pytest

from jarvis.config import Config
from jarvis.commands import CommandEngine
from jarvis.missions.engine import MissionEngine, _parse_plan
from jarvis.missions.store import MissionStore
from jarvis.missions.tools import build_default_registry


@pytest.fixture
def engine(tmp_path):
    cfg = Config()
    cfg.music_dir = str(tmp_path)
    cfg.anthropic_api_key = ""
    return CommandEngine(cfg)


def test_tool_registry_has_core_tools(engine):
    reg = build_default_registry(engine)
    for name in ("say", "wait", "remember", "recall", "web_search", "run_command"):
        assert name in reg
    assert "say" in reg.catalog()


def test_parse_plan_extracts_json():
    raw = 'بله:\n{"steps": [{"tool": "say", "args": {"text": "سلام"}, "check": "گفته شد"}]}'
    plan = _parse_plan(raw)
    assert plan["steps"][0]["tool"] == "say"


def test_mission_runs_steps(engine, tmp_path, monkeypatch):
    said = []
    monkeypatch.setattr("jarvis.missions.engine.MissionEngine.plan",
                        lambda self, req: {"steps": [
                            {"tool": "wait", "args": {"seconds": "0"}, "check": "ok"},
                            {"tool": "say", "args": {"text": "تمام"}, "check": "ok"},
                        ]})
    monkeypatch.setattr("jarvis.tts.say", lambda *a, **k: said.append(a[0] if a else ""))
    me = MissionEngine(engine, store=MissionStore(tmp_path / "mis.db"))
    me.run("یه کاری بکن")
    rows = me.store.steps(1)
    assert [r["status"] for r in rows] == ["ok", "ok"]


def test_looks_like_mission():
    from jarvis.commands import _looks_like_mission
    assert _looks_like_mission("جارویس یه مأموریت برام انجام بده")
    assert not _looks_like_mission("ساعت چنده")
