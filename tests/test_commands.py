import pytest

from jarvis.config import Config
from jarvis.commands import CommandEngine


@pytest.fixture
def engine(monkeypatch, tmp_path):
    cfg = Config()
    cfg.music_dir = str(tmp_path)
    cfg.anthropic_api_key = ""
    cfg.folder_aliases = {"دسکتاپ": str(tmp_path)}
    return CommandEngine(cfg)


def test_match_time_command(engine):
    cmd = engine.match("جارویس ساعت چنده")
    assert cmd is not None and cmd.name == "TIME"


def test_match_music_with_bad_spelling(engine):
    cmd = engine.match("یه اهنگ بزار برام")
    assert cmd is not None and cmd.name == "MUSIC_PLAY"


def test_match_folder_alias(engine):
    cmd = engine.match("دسکتاپ رو باز کن")
    assert cmd is not None and cmd.name == "OPEN::دسکتاپ"


def test_unknown_returns_none(engine):
    assert engine.match("قیمت دلار امروز چنده") is None


def test_handle_search(engine, monkeypatch):
    called = {}
    monkeypatch.setattr("jarvis.system_actions.google_search",
                        lambda q, t: called.setdefault("q", q))
    assert engine.handle("قیمت طلا رو سرچ کن")
    assert called["q"] == "قیمت طلا"


def test_handle_timer(engine, monkeypatch):
    said = []
    monkeypatch.setattr("jarvis.commands.tts.say", lambda *a, **k: said.append(a))
    assert engine.handle("ده دقیقه دیگه یادم بنداز اب بخورم")
    assert said
