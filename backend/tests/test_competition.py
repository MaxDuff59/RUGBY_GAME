"""Le mode compétition : une partie qui ne joue que la Coupe d'Europe ou la Coupe du monde."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

import database
from api import auth
from api.main import app
from models.orm import InternationalRow

# De quoi aller au bout d'une saison, jour par jour, sans boucler à l'infini.
MAX_DAYS = 120


@pytest.fixture
def client(world) -> TestClient:
    auth._attempts.clear()
    client = TestClient(app)
    client.post("/auth/guest")
    assert client.post("/saves/1/new").status_code == 201
    return client


def test_champions_cup_from_the_draw_to_the_end(client):
    unknown = client.post("/competition", json={"code": "six_nations"})
    assert unknown.status_code == 404
    chosen = client.post("/competition", json={"code": "champions_cup"})
    assert chosen.status_code == 201
    cup = chosen.json()
    assert cup["name"] == "Coupe d'Europe" and len(cup["teams"]) == 24
    assert cup["team"] is None and not cup["over"]
    assert client.post("/competition", json={"code": "world_cup"}).status_code == 409

    outsider = next(
        c for c in client.get("/clubs").json() if c["id"] not in {t["id"] for t in cup["teams"]}
    )
    refused = client.post(
        "/competition/team", json={"manager_name": "Max", "team_id": outsider["id"]}
    )
    assert refused.status_code == 400
    team = cup["teams"][0]
    taken = client.post("/competition/team", json={"manager_name": "Max", "team_id": team["id"]})
    assert taken.status_code == 201 and taken.json()["club_id"] == team["id"]
    saves = client.get("/saves").json()
    assert (
        saves[0]["competition"] == "champions_cup" and saves[0]["league_name"] == "Coupe d'Europe"
    )

    # Des journées de championnat d'abord : le premier match de coupe n'est qu'en décembre.
    assert not client.get("/competition").json()["ready"]
    while not client.get("/competition").json()["ready"]:
        assert client.post("/seasons/current/play").status_code == 200
    assert client.get("/seasons/current").json()["next_match"]["cup"]

    # La saison avance jusqu'au titre ou à l'élimination ; la direction ne limoge pas.
    for _ in range(MAX_DAYS):
        status = client.get("/competition").json()
        if status["over"]:
            break
        assert client.post("/seasons/current/play").status_code == 200
        assert client.get("/career").status_code == 200
    assert status["over"] and status["result"]
    assert client.get("/saves").json()[0]["competition_result"] == status["result"]
    ended = client.post("/seasons/current/play")
    assert ended.status_code == 400 and "terminée" in ended.json()["detail"]
    assert client.post("/live").status_code == 400
    assert client.post("/seasons/next").status_code == 400


def test_world_cup_only_with_an_invited_nation(client):
    cup = client.post("/competition", json={"code": "world_cup"}).json()
    assert len(cup["teams"]) == 16
    japan = next(t for t in cup["teams"] if t["name"] == "Japon")
    taken = client.post("/competition/team", json={"manager_name": "Max", "team_id": japan["id"]})
    assert taken.status_code == 201 and taken.json()["kind"] == "nation"

    # Rien d'autre que la Coupe du monde au calendrier international.
    client.get("/selection")
    with database.open_slot(client.get("/auth/me").json()["id"], 1) as session:
        windows = set(session.scalars(select(InternationalRow.competition)))
    assert windows == {"world_cup"}

    for _ in range(MAX_DAYS):
        status = client.get("/competition").json()
        if status["over"]:
            break
        if client.get("/selection").json()["phase"] == "list":
            suggested = client.get("/selection/pool").json()["suggested"]
            assert client.post("/selection/list", json={"player_ids": suggested}).status_code == 201
        assert client.post("/selection/advance").status_code == 200
    assert status["over"] and status["result"]
    assert client.post("/selection/advance").status_code == 400


def test_a_started_game_is_not_a_competition(client):
    assert client.get("/competition").status_code == 404
    toulouse = next(c for c in client.get("/clubs").json() if c["name"] == "Stade Toulousain")
    client.post("/career", json={"manager_name": "Max", "club_id": toulouse["id"]})
    assert client.post("/competition", json={"code": "champions_cup"}).status_code == 409
