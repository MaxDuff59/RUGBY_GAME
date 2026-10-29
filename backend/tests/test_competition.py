"""Le mode compétition : une partie qui ne joue que la Coupe d'Europe ou la Coupe du monde."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

import database
from api import auth
from api import cup as cups
from api.ledger import current_season
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
    assert client.post("/competition/restart").status_code == 409
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

    # Le parcours : chaque match de coupe joué ; en phase finale, le dernier est perdu
    # sauf au titre (éliminé en poules, il a pu gagner son dernier match).
    path = status["path"]
    assert len(path) >= 4 and all(m["stage"] == "regular" for m in path[:4])
    if path[-1]["stage"] != "regular":
        assert (path[-1]["result"] == "won") == (status["result"] == "Vainqueur")
    assert all(m["opponent"]["id"] != team["id"] for m in path)
    # Le bilan de saison lit le même parcours (api/cup.py).
    reached = {
        "Vainqueur": "champion",
        "Finaliste": "final",
        "Demi-finaliste": "semi",
        "Quart de finaliste": "quarter",
        "Éliminé en poules": "pools",
    }
    with database.open_slot(client.get("/auth/me").json()["id"], 1) as session:
        (run,) = [
            r
            for r in cups.runs(session, current_season(session), team["id"])
            if r.code == "champions_cup"
        ]
    assert run.result == reached[status["result"]]
    # La poule de l'équipe, classée : six clubs (quatre matchs chacun), elle comprise.
    pool = status["pool"]
    assert len(pool["table"]) == 6 and team["id"] in [r["club"]["id"] for r in pool["table"]]
    points = [r["league_points"] for r in pool["table"]]
    assert points == sorted(points, reverse=True)
    assert run.won + run.drawn + run.lost == len(path)

    # Recommencer : même compétition, même club, même manager, dans un monde neuf.
    again = client.post("/competition/restart")
    assert again.status_code == 201
    fresh = again.json()
    assert fresh["code"] == "champions_cup" and not fresh["over"] and fresh["path"] == []
    if fresh["team"] is not None:
        assert fresh["team"]["id"] == team["id"]
        assert client.get("/career").json()["manager_name"] == "Max"
    assert len([s for s in client.get("/saves").json() if not s["empty"]]) == 1


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
    assert status["path"] and status["path"][-1]["opponent"]["id"] != japan["id"]
    assert japan["id"] in [r["club"]["id"] for r in status["pool"]["table"]]

    again = client.post("/competition/restart").json()
    assert again["team"]["id"] == japan["id"] and not again["over"]


def test_a_started_game_is_not_a_competition(client):
    assert client.get("/competition").status_code == 404
    toulouse = next(c for c in client.get("/clubs").json() if c["name"] == "Stade Toulousain")
    client.post("/career", json={"manager_name": "Max", "club_id": toulouse["id"]})
    assert client.post("/competition", json={"code": "champions_cup"}).status_code == 409
