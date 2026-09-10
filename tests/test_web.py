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


def test_index_serves_html(client):
    r = client.get("/")
    assert r.status_code == 200 and "J.A.R.V.I.S." in r.text


def test_status_endpoint(client):
    r = client.get("/api/status")
    assert r.status_code == 200
    body = r.json()
    assert "cpu" in body and "memory" in body and "integrations" in body


def test_chat_endpoint(client):
    r = client.post("/api/chat", json={"text": "سلام"})
    assert r.json()["reply"] == "echo:سلام"


def test_memory_endpoint(client):
    r = client.get("/api/memory")
    assert r.status_code == 200
