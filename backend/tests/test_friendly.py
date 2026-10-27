"""Le match libre : deux équipes au choix, hors de toute partie."""

import pytest
from fastapi.testclient import TestClient

from api import auth, friendly
from api.main import app
from models.orm import PlayerRow


@pytest.fixture
def guest(world) -> TestClient:
    auth._attempts.clear()
    client = TestClient(app)
    client.post("/auth/guest")
    return client


def _team(groups: list[dict], name: str) -> int:
    return next(t["id"] for g in groups for t in g["teams"] if t["name"] == name)


def test_club_against_nation_without_any_save(guest):
    groups = guest.get("/friendly/teams").json()
    assert groups[-1]["code"] == "nations"
    assert {"top14", "premiership", "urc"} <= {g["code"] for g in groups}
    toulouse = _team(groups, "Stade Toulousain")
    france = _team(groups, "France")

    assert guest.get("/friendly").status_code == 404
    prepared = guest.post(
        "/friendly", json={"home_id": toulouse, "away_id": france, "my_id": toulouse}
    )
    assert prepared.status_code == 201
    setup = prepared.json()
    assert setup["home"]["name"] == "Stade Toulousain" and not setup["started"]
    assert not setup["team"]["lineup_custom"]
    # Pas encore de match : la composition d'abord.
    assert guest.get("/friendly").status_code == 404

    # Le joueur met un remplaçant du staff à l'ouverture (place 10, indice 9).
    bench = setup["team"]["strength"]["bench_ids"]
    chosen = [None] * 15
    chosen[9] = bench[-1]
    composed = guest.put("/friendly/lineup", json={"player_ids": chosen}).json()
    assert composed["team"]["lineup_custom"]
    assert composed["team"]["strength"]["lineup_ids"][9] == bench[-1]
    stranger = guest.put("/friendly/lineup", json={"player_ids": [10**6]})
    assert stranger.status_code == 400

    started = guest.post("/friendly/kickoff")
    assert started.status_code == 201
    live = started.json()
    home_ids = [p["id"] for p in live["home"]["players"]]
    # Le remplaçant choisi est titulaire au coup d'envoi.
    assert bench[-1] in home_ids[:15]
    assert guest.put("/friendly/lineup", json={"player_ids": []}).status_code == 400
    assert live["my_club_id"] == toulouse and live["minute"] == 0
    assert live["home"]["club"]["name"] == "Stade Toulousain"
    # Un Toulousain ne joue pas contre son club avec la France.
    with friendly.reference() as session:
        clubs = {
            p.id: p.club_id
            for p in session.query(PlayerRow).filter(
                PlayerRow.id.in_([p["id"] for p in live["away"]["players"]])
            )
        }
    assert toulouse not in clubs.values()

    played = guest.post("/friendly/advance", json={"minutes": 10}).json()
    assert played["minute"] == 10
    assert guest.get("/friendly").json()["minute"] == 10
    tactics = guest.post("/friendly/tactics", json={"game_plan": "hands"})
    assert tactics.status_code == 200

    done = guest.post("/friendly/finish").json()
    assert done["finished"] is True
    assert guest.post("/friendly/advance", json={}).status_code == 400
    assert guest.delete("/friendly").status_code == 204
    assert guest.get("/friendly").status_code == 404


def test_friendly_refuses_bad_choices(guest):
    groups = guest.get("/friendly/teams").json()
    toulouse = _team(groups, "Stade Toulousain")
    nz = _team(groups, "Nouvelle-Zélande")

    def start(home, away, mine):
        return guest.post("/friendly", json={"home_id": home, "away_id": away, "my_id": mine})

    assert start(toulouse, toulouse, toulouse).status_code == 400
    assert start(toulouse, nz, 12345).status_code == 400
    assert start(toulouse, 99999, toulouse).status_code == 400
    # Sélection contre sélection, en dirigeant celle qui se déplace.
    assert start(_team(groups, "France"), nz, nz).status_code == 201
    assert guest.post("/friendly/kickoff").json()["my_club_id"] == nz


def test_friendly_needs_an_account(world):
    assert TestClient(app).get("/friendly/teams").status_code == 401


def test_interrupted_reference_world_is_rebuilt(guest, monkeypatch):
    import catalog
    import database

    def unreachable():
        raise ConnectionError("catalogue injoignable")

    real = catalog.leagues
    monkeypatch.setattr(catalog, "leagues", unreachable)
    with pytest.raises(ConnectionError):
        guest.get("/friendly/teams")
    # Rien ne reste d'un monde à moitié fait : le prochain appel le refait.
    assert not database.slot_exists(*friendly.REFERENCE)
    monkeypatch.setattr(catalog, "leagues", real)
    assert len(guest.get("/friendly/teams").json()) > 1


def test_a_guest_who_leaves_takes_their_friendly_along(guest):
    groups = guest.get("/friendly/teams").json()
    toulouse, nz = _team(groups, "Stade Toulousain"), _team(groups, "Nouvelle-Zélande")
    guest.post("/friendly", json={"home_id": toulouse, "away_id": nz, "my_id": toulouse})
    guest.post("/auth/logout")
    # Le compte suivant (SQLite peut lui redonner le même identifiant) part de zéro.
    guest.post("/auth/guest")
    assert guest.get("/friendly/team").status_code == 404
