"""Le match libre : deux équipes au choix, hors de toute partie."""

from collections import Counter

import pytest
from fastapi.testclient import TestClient

from api import auth, friendly
from api.main import app
from data import legends as legends_data
from engine import dilemmas
from engine.internationals import SQUAD_MINIMUM
from models.orm import PlayerRow


@pytest.fixture
def guest(world) -> TestClient:
    auth._attempts.clear()
    client = TestClient(app)
    client.post("/auth/guest")
    return client


def _team(groups: list[dict], name: str) -> int:
    return next(t["id"] for g in groups for t in g["teams"] if t["name"] == name)


def test_club_against_nation_without_any_save(guest, monkeypatch):
    # Les dilemmes du joueur arrêteraient le chrono avant dix minutes : testés plus bas.
    monkeypatch.setattr(dilemmas, "COACH_DILEMMA_CHANCE", 0.0)
    groups = guest.get("/friendly/teams").json()
    assert [g["code"] for g in groups[-3:]] == ["nations", "legends", "club_legends"]
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

    # Rejouer : mêmes équipes, même XV, de retour avant le coup d'envoi.
    replayed = guest.post("/friendly/replay")
    assert replayed.status_code == 200
    assert not replayed.json()["started"] and replayed.json()["team"]["lineup_custom"]
    assert guest.get("/friendly").status_code == 404
    again = guest.post("/friendly/kickoff").json()
    assert again["minute"] == 0 and not again["finished"]
    assert bench[-1] in [p["id"] for p in again["home"]["players"]][:15]
    assert guest.delete("/friendly").status_code == 204
    assert guest.get("/friendly").status_code == 404
    assert guest.post("/friendly/replay").status_code == 404


def test_legends_against_their_nation(guest):
    groups = guest.get("/friendly/teams").json()
    legends = _team(groups, "France de légende")
    france = _team(groups, "France")
    setup = guest.post(
        "/friendly", json={"home_id": legends, "away_id": france, "my_id": legends}
    ).json()
    assert setup["home"]["name"] == "France de légende"
    names = {f"{p['first_name']} {p['last_name']}" for p in setup["team"]["players"]}
    assert {"Antoine Dupont", "Serge Blanco", "Philippe Sella"} <= names
    # Les légendes sont un cran au-dessus de la sélection d'aujourd'hui.
    mine = setup["team"]["strength"]
    guest.delete("/friendly")
    today = guest.post(
        "/friendly", json={"home_id": legends, "away_id": france, "my_id": france}
    ).json()["team"]["strength"]
    assert mine["attack"] > today["attack"] and mine["defense"] > today["defense"]

    guest.post("/friendly", json={"home_id": legends, "away_id": france, "my_id": legends})
    live = guest.post("/friendly/kickoff").json()
    assert live["home"]["club"]["name"] == "France de légende"
    done = guest.post("/friendly/finish").json()
    assert done["finished"] is True


def test_club_legends_against_their_club(guest):
    groups = guest.get("/friendly/teams").json()
    clubs = next(g for g in groups if g["code"] == "club_legends")
    assert len(clubs["teams"]) == 11
    # Chaque équipe au choix a ses notes et son niveau, les légendes tout en haut.
    teams = [t for g in groups for t in g["teams"]]
    assert all(t["attack"] and t["forwards"] and t["defense"] for t in teams)
    assert {t["level"] for t in teams} <= {1 + n / 2 for n in range(9)}
    assert max(t["level"] for t in teams) == 5 and min(t["level"] for t in teams) == 1
    assert min(t["level"] for t in clubs["teams"]) >= 4
    legends = _team(groups, "Stade Français Paris de légende")
    paris = _team(groups, "Stade Français Paris")
    setup = guest.post(
        "/friendly", json={"home_id": paris, "away_id": legends, "my_id": legends}
    ).json()
    players = {f"{p['first_name']} {p['last_name']}": p for p in setup["team"]["players"]}
    assert {"Julien Arias", "Sergio Parisse", "Christophe Dominici"} <= set(players)
    # Chacun garde sa nationalité, le club donne la sienne aux autres.
    assert players["Sergio Parisse"]["nationality"] == "ITA"
    assert players["Julien Arias"]["nationality"] == "FRA"
    # Julien Arias, titulaire attitré, porte le 14 (13e place du XV) ; le joueur reste
    # libre de composer autrement.
    arias = players["Julien Arias"]["id"]
    assert setup["team"]["strength"]["lineup_ids"][13] == arias
    assert setup["team"]["lineup_custom"] is False
    camara = players["Djibril Camara"]["id"]
    xv = guest.put("/friendly/lineup", json={"player_ids": [None] * 13 + [camara]}).json()
    assert xv["team"]["strength"]["lineup_ids"][13] == camara and xv["team"]["lineup_custom"]
    xv = guest.delete("/friendly/lineup").json()
    assert xv["team"]["strength"]["lineup_ids"][13] == arias

    live = guest.post("/friendly/kickoff").json()
    assert live["away"]["club"]["name"] == "Stade Français Paris de légende"
    assert guest.post("/friendly/finish").json()["finished"] is True


def test_a_legend_keeps_his_rating_from_team_to_team():
    seen: dict[str, float] = {}
    for team in legends_data.LEGENDS:
        counts = Counter(legend.position for legend in team.legends)
        assert all(counts[position] >= n for position, n in SQUAD_MINIMUM.items()), team.name
        for legend in team.legends:
            name = f"{legend.first_name} {legend.last_name}"
            assert seen.setdefault(name, legend.rating) == legend.rating, name
    assert len({team.id for team in legends_data.LEGENDS}) == len(legends_data.LEGENDS)


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


def test_the_player_decides_dilemmas_in_a_friendly(guest, monkeypatch):
    """Au match libre aussi, le joueur tranche des dilemmes pour son XV (/friendly/choose)."""
    monkeypatch.setattr(dilemmas, "COACH_DILEMMA_CHANCE", 1.0)
    groups = guest.get("/friendly/teams").json()
    toulouse, france = _team(groups, "Stade Toulousain"), _team(groups, "France")
    guest.post("/friendly", json={"home_id": toulouse, "away_id": france, "my_id": toulouse})
    guest.post("/friendly/kickoff")
    live = guest.post("/friendly/advance", json={"minutes": 10}).json()
    dilemma = live["dilemma"]
    assert dilemma is not None and live["minute"] == 1
    mine = live["home"] if live["home"]["club"]["id"] == live["my_club_id"] else live["away"]
    assert dilemma["player_id"] in {p["id"] for p in mine["players"] if p["status"] == "field"}
    key = dilemma["options"][0]["key"]
    live = guest.post("/friendly/choose", json={"option": key}).json()
    assert [o["player_id"] for o in live["outcomes"]] == [dilemma["player_id"]]
    assert guest.post("/friendly/choose", json={"option": key}).status_code in (200, 400)
