"""Photos des joueurs : servies depuis notre copie, récupérées une fois chez Wikimedia."""

import pytest
from fastapi.testclient import TestClient

import database
from api.main import app
from api.routers import photos


@pytest.fixture
def client(tmp_path, monkeypatch) -> TestClient:
    monkeypatch.setattr(database, "SAVES_DIR", tmp_path)
    photos._failed.clear()
    return TestClient(app)


def test_photo_is_fetched_once_then_served_from_disk(client, monkeypatch):
    calls = []

    def fake_fetch(name):
        calls.append(name)
        return b"\xff\xd8fake-jpeg"

    monkeypatch.setattr(photos, "fetch", fake_fetch)
    first = client.get("/photos/Shahn%20Eru.jpg")
    assert first.status_code == 200 and first.content == b"\xff\xd8fake-jpeg"
    assert first.headers["content-type"] == "image/jpeg"
    assert "max-age" in first.headers["cache-control"]
    second = client.get("/photos/Shahn%20Eru.jpg")
    assert second.status_code == 200
    assert calls == ["Shahn Eru.jpg"]
    assert list(photos.cache_dir().iterdir())


def test_missing_photo_is_404_and_not_retried_at_once(client, monkeypatch):
    calls = []
    monkeypatch.setattr(photos, "fetch", lambda name: calls.append(name))
    assert client.get("/photos/Inconnu.jpg").status_code == 404
    assert client.get("/photos/Inconnu.jpg").status_code == 404
    assert calls == ["Inconnu.jpg"]


def test_path_tricks_are_refused(client, monkeypatch):
    monkeypatch.setattr(photos, "fetch", lambda name: b"x")
    assert client.get("/photos/..%2F..%2Fetc%2Fpasswd").status_code == 404
    assert client.get("/photos/..").status_code == 404
