"""Fixtures pytest partagées : clubs du moteur, et client de l'API sur une base en mémoire."""

import os
import random
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

import accounts
import database
from api.auth import current_user
from api.deps import get_session
from api.main import app
from data.generator import SQUAD_COMPOSITION, generate_player
from database import seed_if_empty
from models import Club
from models.orm import Base

# Le catalogue des tests reste dans leurs bases : jamais celui de la prod, même si le
# terminal a RUGBY_CATALOG_DB_URL (catalog.py la lit à chaque connexion).
os.environ.pop("RUGBY_CATALOG_DB_URL", None)

# Les tests tournent sur SQLite en mémoire ; avec RUGBY_TEST_DATABASE_URL (un Postgres
# jetable), ils tournent sur Postgres, vidé avant chaque cas.
TEST_DB_URL = os.environ.get("RUGBY_TEST_DATABASE_URL")


def wipe_postgres(engine: Engine) -> None:
    """Repart d'une base vide : schémas des parties et schéma public."""
    with engine.begin() as connection:
        schemas = connection.execute(
            text(
                "SELECT schema_name FROM information_schema.schemata "
                r"WHERE schema_name LIKE 'save\_%'"
            )
        ).scalars()
        for name in list(schemas):
            connection.execute(text(f'DROP SCHEMA "{name}" CASCADE'))
        connection.execute(text("DROP SCHEMA public CASCADE"))
        connection.execute(text("CREATE SCHEMA public"))


def test_engine() -> Engine:
    """Une base vide pour un test : SQLite en mémoire, ou le Postgres de test."""
    if TEST_DB_URL:
        engine = create_engine(TEST_DB_URL, connect_args={"prepare_threshold": None})
        wipe_postgres(engine)
        return engine
    # StaticPool : une seule connexion partagée, sinon chaque session verrait
    # une base en mémoire différente (et vide).
    return create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )


@pytest.fixture
def world(tmp_path, monkeypatch) -> Iterator[None]:
    """De vrais comptes et de vraies parties (fichiers dans un dossier temporaire, ou
    schémas du Postgres de test), au lieu de la base de test injectée."""
    monkeypatch.setattr(database, "SAVES_DIR", tmp_path)
    monkeypatch.setattr(database, "DATABASE_URL", TEST_DB_URL)
    monkeypatch.delenv("RUGBY_USERS_DB_URL", raising=False)
    if TEST_DB_URL:
        wipe_postgres(create_engine(TEST_DB_URL, connect_args={"prepare_threshold": None}))
    # Connexions neuves : le registre des parties et les tables des comptes se recréent.
    database.forget_engines()
    accounts.reset()
    app.dependency_overrides.clear()
    yield
    database.forget_engines()
    accounts.reset()


def make_club(club_id: int, level: float, seed: int = 0) -> Club:
    """Club complet (31 joueurs) dont tous les joueurs tournent autour de `level`."""
    rng = random.Random(seed)
    club = Club(id=club_id, name=f"Club {club_id}")
    player_id = club_id * 100
    for position, size in SQUAD_COMPOSITION.items():
        for _ in range(size):
            player_id += 1
            club.players.append(generate_player(player_id, position, level, club_id, rng))
    return club


@pytest.fixture
def even_clubs() -> tuple[Club, Club]:
    """Deux clubs de même niveau."""
    return make_club(1, level=12, seed=1), make_club(2, level=12, seed=2)


@pytest.fixture
def strong_and_weak() -> tuple[Club, Club]:
    """Un club nettement plus fort que l'autre."""
    return make_club(1, level=15, seed=1), make_club(2, level=9, seed=2)


# --- API : base SQLite en mémoire (jamais sur les parties sauvegardées) ---------------------


def full_account() -> accounts.User:
    """Le compte des tests de l'API sur base injectée : jeu complet, ses saisons ne se
    comptent pas (la formule gratuite a ses tests, tests/test_plans.py)."""
    return accounts.User(id=1, email="maxence@example.com", active_slot=1, premium=True)


@pytest.fixture
def client() -> Iterator[TestClient]:
    engine = test_engine()
    Base.metadata.create_all(engine)
    TestSession = sessionmaker(bind=engine, expire_on_commit=False)
    with TestSession() as session:
        seed_if_empty(session, club_count=10, seed=0, real=False)

    def override_get_session() -> Iterator[Session]:
        with TestSession() as session:
            yield session

    app.dependency_overrides[get_session] = override_get_session
    app.dependency_overrides[current_user] = full_account
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture
def manager(client: TestClient) -> TestClient:
    """Client avec une carrière en cours (club 3)."""
    client.post("/career", json={"manager_name": "Maxence", "club_id": 3})
    return client
