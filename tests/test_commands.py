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
    assert engine.match("قیمت دلار در بازار آزاد") is None


def test_author_command(engine):
    cmd = engine.match("جارویس سازنده‌ات کیه")
    assert cmd is not None and cmd.name == "AUTHOR"


def test_moncton_commands(engine):
    assert engine.match("ساعت مونکتون").name == "SEC_TIME"
    assert engine.match("هوای مونکتون چطوره").name == "SEC_WEATHER"


def test_conversation_toggle_commands(engine, monkeypatch):
    from jarvis.state import STATE
    monkeypatch.setattr("jarvis.commands.tts.say", lambda *a, **k: None)
    engine.match("حالت مکالمه").handler()
    assert STATE.conversation_active is True
    engine.match("از حالت مکالمه خارج شو").handler()
    assert STATE.conversation_active is False


def test_author_report_mentions_name():
    from jarvis import reports
    reports.configure("قربان", "http://x", author="محسن جباره اصل")
    assert "محسن جباره اصل" in reports.author()


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
