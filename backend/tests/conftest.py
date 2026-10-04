"""Fixtures pytest partagées : clubs du moteur, et client de l'API sur une base en mémoire."""

import random
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from api.main import app
from data.generator import SQUAD_COMPOSITION, generate_player
from database import get_session, seed_if_empty
from models import Club
from models.orm import Base


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


# --- API : base SQLite en mémoire (jamais sur rugby.db) ---------------------------------


@pytest.fixture
def client() -> Iterator[TestClient]:
    # StaticPool : une seule connexion partagée, sinon chaque session verrait
    # une base en mémoire différente (et vide).
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    TestSession = sessionmaker(bind=engine, expire_on_commit=False)
    with TestSession() as session:
        seed_if_empty(session, club_count=10, seed=0)

    def override_get_session() -> Iterator[Session]:
        with TestSession() as session:
            yield session

    app.dependency_overrides[get_session] = override_get_session
    # Pas de `with TestClient(...)` : on n'exécute pas le démarrage de l'app,
    # qui créerait le fichier rugby.db.
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture
def manager(client: TestClient) -> TestClient:
    """Client avec une carrière en cours (club 3)."""
    client.post("/career", json={"manager_name": "Maxence", "club_id": 3})
    return client
