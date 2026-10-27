"""Comptes : inscription, connexion, session par cookie, déconnexion."""

import datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, update

import accounts
import database
from api import auth
from api.main import app


@pytest.fixture
def client(world) -> TestClient:
    auth._attempts.clear()
    return TestClient(app)


def test_register_then_login(client):
    assert client.get("/auth/me").status_code == 401
    created = client.post(
        "/auth/register", json={"email": " Maxence@Example.com ", "password": "ballon-ovale"}
    )
    assert created.status_code == 201
    assert created.json() == {
        "id": 1,
        "email": "maxence@example.com",
        "active_slot": None,
        "premium": False,
        "seasons_played": 0,
        "seasons_left": 2,
        "free_seasons": 2,
        "free_saves": 1,
        "paywall": False,
        "guest": False,
    }
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


def test_guest_plays_without_an_account(client):
    created = client.post("/auth/guest")
    assert created.status_code == 201
    me = client.get("/auth/me").json()
    assert me["guest"] is True and me["email"] == ""
    # Personne ne peut se connecter à un invité : il n'a pas de mot de passe.
    email = accounts.get(me["id"]).email
    assert client.post("/auth/login", json={"email": email, "password": ""}).status_code == 401

    assert client.post("/saves/1/new").status_code == 201
    second = client.post("/saves/2/new")
    assert second.status_code == 403 and "une seule partie" in second.json()["detail"]


def test_guest_who_registers_keeps_their_save(client):
    client.post("/auth/guest")
    guest_id = client.get("/auth/me").json()["id"]
    client.post("/saves/1/new")

    created = client.post(
        "/auth/register", json={"email": "maxence@example.com", "password": "ballon-ovale"}
    )
    assert created.status_code == 201
    assert created.json()["id"] == guest_id and created.json()["guest"] is False
    assert database.slot_exists(guest_id, 1)
    # Un vrai compte n'est plus effacé avec les invités.
    assert accounts.purge_guests() == []


def test_guest_logout_erases_their_save(client):
    client.post("/auth/guest")
    guest_id = client.get("/auth/me").json()["id"]
    client.post("/saves/1/new")
    assert client.post("/auth/logout").status_code == 204
    assert accounts.get(guest_id) is None
    assert not database.slot_exists(guest_id, 1)


def test_guests_who_stopped_coming_are_purged(client):
    client.post("/auth/guest")
    email = accounts.get(client.get("/auth/me").json()["id"]).email
    client.cookies.clear()
    # Sa session a expiré : le prochain invité le fait disparaître.
    with accounts._session() as session:
        session.execute(
            update(accounts.SessionRow).values(
                expires_at=accounts._now() - datetime.timedelta(minutes=1)
            )
        )
        session.commit()
    client.post("/auth/guest")
    with accounts._session() as session:
        emails = list(session.scalars(select(accounts.UserRow.email)))
    assert email not in emails and len(emails) == 1
