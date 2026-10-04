"""Tests de l'API, sur une base SQLite en mémoire (jamais sur rugby.db)."""

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from api.main import app
from database import get_session, seed_if_empty
from models.orm import Base


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


def test_list_clubs(client):
    response = client.get("/clubs")
    assert response.status_code == 200
    clubs = response.json()
    assert len(clubs) == 10
    assert all(club["player_count"] == 31 for club in clubs)
    assert all(1 <= club["level"] <= 20 for club in clubs)


def test_get_club_squad(client):
    response = client.get("/clubs/1")
    assert response.status_code == 200
    club = response.json()
    assert len(club["players"]) == 31
    assert len(club["strength"]["lineup_ids"]) == 15
    player_ids = {p["id"] for p in club["players"]}
    assert set(club["strength"]["lineup_ids"]) <= player_ids


def test_unknown_club_returns_404(client):
    assert client.get("/clubs/999").status_code == 404


def test_simulate_match(client):
    response = client.post(
        "/matches/simulate", json={"home_club_id": 1, "away_club_id": 2, "seed": 7}
    )
    assert response.status_code == 200
    match = response.json()
    home_points = sum(e["points"] for e in match["events"] if e["club_id"] == 1)
    assert match["home_score"] == home_points
    # Même graine, même match.
    again = client.post("/matches/simulate", json={"home_club_id": 1, "away_club_id": 2, "seed": 7})
    assert again.json() == match


def test_club_cannot_play_itself(client):
    response = client.post("/matches/simulate", json={"home_club_id": 1, "away_club_id": 1})
    assert response.status_code == 400


def test_career(client):
    assert client.get("/career").status_code == 404

    created = client.post("/career", json={"manager_name": "Maxence", "club_id": 3})
    assert created.status_code == 201
    assert client.get("/career").json() == created.json()

    # Une nouvelle carrière remplace la précédente.
    client.post("/career", json={"manager_name": "Maxence", "club_id": 4})
    assert client.get("/career").json()["club_id"] == 4


def test_career_needs_an_existing_club(client):
    assert (
        client.post("/career", json={"manager_name": "Maxence", "club_id": 999}).status_code == 404
    )


def test_simulate_and_reload_season(client):
    created = client.post("/seasons", json={"year": 2026, "seed": 1})
    assert created.status_code == 201
    season = created.json()
    assert season["matchdays"] == 18
    assert len(season["standings"]) == 10
    assert [row["rank"] for row in season["standings"]] == list(range(1, 11))

    # Le classement recalculé depuis la base est identique.
    assert client.get("/seasons/2026").json() == season
    # Pas deux fois la même saison.
    assert client.post("/seasons", json={"year": 2026}).status_code == 409
    assert client.get("/seasons/1999").status_code == 404
