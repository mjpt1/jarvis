import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient

from jarvis.config import Config
from jarvis.web import server


@pytest.fixture
def client(monkeypatch):
    server._cfg = Config()
    monkeypatch.setattr("jarvis.brain.respond", lambda t: f"echo:{t}")
    return TestClient(server._build_app())


def test_index_serves_command_center(client):
    r = client.get("/")
    assert r.status_code == 200
    assert "JARVIS" in r.text and "مرکز فرمان" in r.text


def test_dashboard_endpoint(client):
    r = client.get("/api/dashboard")
    assert r.status_code == 200
    b = r.json()
    for key in ("clock", "core", "feed", "agents", "timeline", "monitor",
                "memory", "llm", "voice", "bottom"):
        assert key in b
    assert isinstance(b["agents"], list) and len(b["agents"]) == 6
    assert "cpu" in b["monitor"]


def test_chat_endpoint(client):
    r = client.post("/api/chat", json={"text": "سلام"})
    assert r.json()["reply"] == "echo:سلام"


def test_autonomy_endpoint(client):
    r = client.post("/api/autonomy", json={"level": 2})
    assert r.json()["autonomy"] == 2


def test_memory_endpoint(client):
    assert client.get("/api/memory").status_code == 200
