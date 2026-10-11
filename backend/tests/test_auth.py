"""Comptes : inscription, connexion, session par cookie, déconnexion."""

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

import accounts
import database
from api import auth
from api.main import app


@pytest.fixture
def client(tmp_path, monkeypatch) -> Iterator[TestClient]:
    monkeypatch.setattr(database, "SAVES_DIR", tmp_path)
    monkeypatch.delenv("RUGBY_USERS_DB_URL", raising=False)
    accounts.reset()
    auth._attempts.clear()
    app.dependency_overrides.clear()
    yield TestClient(app)
    accounts.reset()


def test_register_then_login(client):
    assert client.get("/auth/me").status_code == 401
    created = client.post(
        "/auth/register", json={"email": " Maxence@Example.com ", "password": "ballon-ovale"}
    )
    assert created.status_code == 201
    assert created.json() == {"id": 1, "email": "maxence@example.com", "active_slot": None}
    assert auth.COOKIE in client.cookies
    assert client.get("/auth/me").json()["email"] == "maxence@example.com"

    assert client.post("/auth/logout").status_code == 204
    assert client.get("/auth/me").status_code == 401

    again = client.post(
        "/auth/login", json={"email": "maxence@example.com", "password": "ballon-ovale"}
    )
    assert again.status_code == 200
    assert client.get("/auth/me").json()["id"] == 1


def test_register_refuses_bad_input(client):
    def register(email, password):
        return client.post("/auth/register", json={"email": email, "password": password})

    assert register("pas-une-adresse", "ballon-ovale").status_code == 400
    assert register("maxence@example.com", "court").json()["detail"].startswith("Mot de passe")
    assert register("maxence@example.com", "ballon-ovale").status_code == 201
    taken = register("MAXENCE@example.com", "autre-mot-de-passe")
    assert taken.status_code == 400 and "existe déjà" in taken.json()["detail"]


def test_login_refuses_wrong_password_without_telling_which(client):
    client.post("/auth/register", json={"email": "maxence@example.com", "password": "ballon-ovale"})
    client.post("/auth/logout")
    wrong = client.post(
        "/auth/login", json={"email": "maxence@example.com", "password": "nope-nope"}
    )
    unknown = client.post(
        "/auth/login", json={"email": "inconnu@example.com", "password": "nope-nope"}
    )
    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json() == unknown.json()
    assert client.get("/auth/me").status_code == 401


def test_too_many_attempts_are_throttled(client):
    for _ in range(auth.LOGIN_ATTEMPTS):
        client.post("/auth/login", json={"email": "x@example.com", "password": "nope-nope"})
    blocked = client.post("/auth/login", json={"email": "x@example.com", "password": "nope-nope"})
    assert blocked.status_code == 429


def test_passwords_are_hashed():
    stored = accounts.hash_password("ballon-ovale")
    assert "ballon-ovale" not in stored and stored.startswith("scrypt$")
    assert accounts.check_password("ballon-ovale", stored)
    assert not accounts.check_password("ballon-rond", stored)
    assert not accounts.check_password("ballon-ovale", "n'importe quoi")


def test_forged_or_expired_cookie_is_ignored(client):
    client.cookies.set(auth.COOKIE, "jeton-invente")
    assert client.get("/auth/me").status_code == 401
    assert accounts.user_for_token(None) is None
