"""Fins de contrat : prolongations, signatures des concurrents, départs, bilan de saison."""

import pytest

from engine.contracts import (
    leaves_academy_next_season,
    poach_chance,
    renewal_wage,
    renewal_years,
    retires_next_season,
)
from engine.economy import SQUAD_MIN
from models import Squad
from tests.conftest import make_club

YEAR = 2026


def play_season(client):
    while client.get("/seasons/current").json()["phase"] != "finished":
        client.post("/seasons/current/play")


# --- Règles -------------------------------------------------------------------------


def test_renewal_terms_follow_age_and_squad():
    club = make_club(1, level=12)
    young, veteran = club.players[0], club.players[1]
    young.age, veteran.age = 22, 34
    assert renewal_years(young) == (3, 5)
    assert renewal_years(veteran) == (1, 2)
    # Un vétéran accepte une baisse, jamais au-delà de 25 %.
    assert renewal_wage(veteran, club) >= int(veteran.wage * 0.75) - 1_000

    youth = club.players[2]
    youth.squad, youth.age = Squad.YOUTH, 20
    assert renewal_wage(youth, club) == 15_000
    assert renewal_years(youth) == (1, 1)  # il sortira du centre à 22 ans
    youth.age = 21
    assert leaves_academy_next_season(youth)
    veteran.age = 35
    assert retires_next_season(veteran)


def test_the_best_players_are_the_most_coveted():
    club = make_club(1, level=12)
    ranked = sorted(club.players, key=lambda p: p.overall)
    assert poach_chance(ranked[-1], club) > poach_chance(ranked[0], club)
    assert all(0 < poach_chance(p, club) <= 0.06 for p in club.players)


# --- Routes -------------------------------------------------------------------------


def test_extend_a_player_in_his_last_year(manager):
    play_season(manager)
    contracts = manager.get("/contracts").json()
    open_ = [c for c in contracts["pros"] if c["status"] == "open"]
    assert open_ and all(c["player"]["contract_until"] == YEAR for c in open_)
    target = open_[0]
    player_id, years = target["player"]["id"], target["years_max"]

    # Durée hors de ses souhaits : refusée (au-delà de 5 saisons, par la validation).
    refused = manager.post(f"/contracts/{player_id}/extend", json={"years": years + 1})
    assert refused.status_code in (400, 422)

    after = manager.post(f"/contracts/{player_id}/extend", json={"years": years}).json()
    extended = next(c for c in after["pros"] if c["player"]["id"] == player_id)
    assert extended["status"] == "extended" and extended["new_years"] == years
    assert extended["player"]["contract_until"] == YEAR + years
    assert extended["player"]["wage"] == target["wage_demand"]
    assert after["squad_next"] == contracts["squad_next"] + 1
    # Plus en dernière année : on ne prolonge pas deux fois.
    again = manager.post(f"/contracts/{player_id}/extend", json={"years": 1})
    assert again.status_code == 400


def test_unextended_players_leave_and_extended_ones_stay(manager):
    play_season(manager)
    open_ = [c for c in manager.get("/contracts").json()["pros"] if c["status"] == "open"]
    for contract in open_[1:]:
        manager.post(
            f"/contracts/{contract['player']['id']}/extend",
            json={"years": contract["years_min"]},
        )
    assert manager.post("/seasons/next").status_code == 201

    mine = {p["id"] for p in manager.get("/clubs/3").json()["players"]}
    assert open_[0]["player"]["id"] not in mine  # parti libre
    assert all(c["player"]["id"] in mine for c in open_[1:])
    # Il est agent libre (sauf si un club IA l'a déjà repris), et les clubs IA
    # n'ont gardé que des joueurs sous contrat.
    gone = manager.get(f"/players/{open_[0]['player']['id']}").json()
    assert gone["club"] is None or gone["club"]["id"] != 3
    for club_id in (1, 2):
        players = manager.get(f"/clubs/{club_id}").json()["players"]
        assert all(p["contract_until"] >= YEAR + 1 for p in players)


def test_rivals_sign_players_in_their_last_year(manager, monkeypatch):
    monkeypatch.setattr("api.routers.contracts.poach_chance", lambda player, club: 1.0)
    first = manager.post("/seasons/current/play").json()
    assert first["signings"] == []  # pas avant la phase retour

    signings = []
    while not signings:
        signings = manager.post("/seasons/current/play").json()["signings"]
    signed = signings[0]
    assert signed["status"] == "signed_elsewhere" and signed["new_club"]["id"] != 3
    player_id = signed["player"]["id"]

    refused = manager.post(f"/contracts/{player_id}/extend", json={"years": 2})
    assert refused.status_code == 400
    assert signed["new_club"]["name"] in refused.json()["detail"]

    play_season(manager)
    listed = manager.get("/contracts").json()
    group = listed["youths"] if signed["player"]["squad"] == "YOUTH" else listed["pros"]
    assert any(c["player"]["id"] == player_id and c["status"] == "signed_elsewhere" for c in group)
    for contract in listed["pros"]:
        if contract["status"] == "open":
            manager.post(
                f"/contracts/{contract['player']['id']}/extend",
                json={"years": contract["years_min"]},
            )
    manager.post("/seasons/next")
    assert manager.get(f"/players/{player_id}").json()["club"]["id"] == signed["new_club"]["id"]


def test_next_season_needs_enough_players_under_contract(manager):
    play_season(manager)
    contracts = manager.get("/contracts").json()
    staying = [
        p
        for p in manager.get("/clubs/3").json()["players"]
        if p["contract_until"] > YEAR and p["age"] < 35
    ]
    # Vendre des joueurs sous contrat jusqu'à passer sous le minimum.
    while contracts["squad_next"] >= SQUAD_MIN:
        assert manager.post(f"/transfers/sell/{staying.pop()['id']}").status_code == 200
        contracts = manager.get("/contracts").json()
    refused = manager.post("/seasons/next")
    assert refused.status_code == 400 and "insuffisant" in refused.json()["detail"]

    for contract in contracts["pros"]:
        if contract["status"] == "open":
            manager.post(
                f"/contracts/{contract['player']['id']}/extend",
                json={"years": contract["years_min"]},
            )
    assert manager.get("/contracts").json()["squad_next"] >= SQUAD_MIN
    assert manager.post("/seasons/next").status_code == 201


def test_season_review(manager):
    assert manager.get("/seasons/current/review").status_code == 400
    play_season(manager)
    review = manager.get("/seasons/current/review").json()
    standings = manager.get("/seasons/current").json()["standings"]
    mine = next(row for row in standings if row["club_id"] == 3)
    assert review["club"]["id"] == 3 and review["rank"] == mine["rank"]
    assert review["won"] + review["drawn"] + review["lost"] == review["played"] == 18
    expected = "none" if mine["rank"] > 6 else review["playoffs"]
    assert review["playoffs"] == expected
    assert review["objective_met"] == (review["rank"] <= review["objective"]["target_rank"])
    assert 1 <= review["youth_rank"] <= 10
    assert len(review["scorers"]) <= 3
    assert review["scorers"] == sorted(review["scorers"], key=lambda s: -s["points"])


@pytest.mark.parametrize("path", ["/contracts"])
def test_contracts_need_a_career(client, path):
    assert client.get(path).status_code == 404
