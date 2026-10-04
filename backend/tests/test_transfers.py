"""Recrutement : règles de négociation, vrais clubs du Top 14, routes de transfert."""

import random

import pytest

from data.generator import generate_top14
from data.top14 import TOP14
from engine.economy import FacilityKind, next_stadium_step, upgrade_cost
from engine.match_engine import RATING_FOR_POSITION
from engine.transfers import (
    TIME_BENCH,
    TIME_RESERVE,
    TIME_STARTER,
    accepts_loan,
    can_precontract,
    club_lends,
    club_level,
    playing_time,
    transfer_fee,
    wage_demand,
)
from models import Facilities, Position
from tests.conftest import make_club

YEAR = 2026


def props_by_rating(club):
    return sorted(
        club.players_at(Position.PROP), key=RATING_FOR_POSITION[Position.PROP], reverse=True
    )


# --- Règles -------------------------------------------------------------------------


def test_playing_time_follows_the_rank_at_the_position():
    club = make_club(1, level=12)
    first, second, third, fourth, fifth = props_by_rating(club)
    assert playing_time(first, club) == playing_time(second, club) == TIME_STARTER
    assert playing_time(third, club) == TIME_BENCH
    assert playing_time(fourth, club) == playing_time(fifth, club) == TIME_RESERVE


def test_bench_player_of_a_big_club_prefers_a_loan():
    big, small = make_club(1, level=15, seed=1), make_club(2, level=9, seed=2)
    assert club_level(big) > club_level(small)
    bench = props_by_rating(big)[3]  # réserviste chez le grand club
    assert playing_time(bench, small) == TIME_STARTER  # titulaire chez le petit

    demand = wage_demand(bench, big, small)
    # Il ne descend que pour un salaire XXL, ou pas du tout.
    assert demand is None or demand >= 1.5 * bench.wage
    assert club_lends(bench, big)
    assert accepts_loan(bench, big, small)


def test_small_club_starter_jumps_at_a_big_club():
    big, small = make_club(1, level=15, seed=1), make_club(2, level=9, seed=2)
    starter = props_by_rating(small)[0]
    assert playing_time(starter, big) == TIME_RESERVE  # il jouerait peu là-haut
    demand = wage_demand(starter, small, big)
    assert demand is not None and demand <= starter.wage  # il vient même sans augmentation
    # L'inverse : un prêt chez un petit club n'intéresse pas un titulaire.
    assert not club_lends(starter, small)


def test_big_clubs_keep_their_starters_and_fees_grow_with_the_contract():
    big = make_club(1, level=15, seed=1)
    starter, _, bench, *_ = props_by_rating(big)
    assert transfer_fee(starter, big, YEAR) is None
    bench.contract_until = YEAR
    short = transfer_fee(bench, big, YEAR)
    bench.contract_until = YEAR + 2
    long = transfer_fee(bench, big, YEAR)
    assert short is not None and long > short

    small = make_club(2, level=9, seed=2)
    assert transfer_fee(props_by_rating(small)[0], small, YEAR) is not None


def test_precontract_only_in_the_last_contract_year():
    player = make_club(1, level=12).players[0]
    player.contract_until = YEAR
    assert can_precontract(player, YEAR)
    player.contract_until = YEAR + 1
    assert not can_precontract(player, YEAR)
    assert player.years_left(YEAR) == 2


# --- Top 14 --------------------------------------------------------------------------


def test_top14_clubs_are_generated_with_their_stadiums():
    clubs = generate_top14(random.Random(0))
    assert [c.name for c in clubs] == [real.name for real in TOP14]
    assert len(clubs) == 14 and all(len(c.players) == 31 for c in clubs)
    toulouse = next(c for c in clubs if c.name == "Stade Toulousain")
    montauban = next(c for c in clubs if c.name == "US Montauban")
    assert toulouse.facilities.stadium_capacity == 19_000
    assert club_level(toulouse) > club_level(montauban)
    assert toulouse.balance > montauban.balance
    assert all(c.players[0].contract_until >= YEAR for c in clubs)


def test_real_stadium_capacities_fit_between_the_steps():
    assert next_stadium_step(33_000) == 35_000
    assert next_stadium_step(35_000) is None
    assert upgrade_cost(Facilities(stadium_capacity=33_000), FacilityKind.STADIUM) > 0
    assert upgrade_cost(Facilities(stadium_capacity=35_000), FacilityKind.STADIUM) is None


# --- API -----------------------------------------------------------------------------


def _find_target(manager, kind):
    """Un joueur du marché pour lequel la voie `kind` est ouverte, avec son approche."""
    market = manager.get("/transfers").json()
    flag = {"transfer": "transfer_fee", "loan": "loanable", "precontract": "precontract"}[kind]
    for listing in market["listings"]:
        if not listing[flag]:
            continue
        target = manager.get(f"/transfers/{listing['player']['id']}").json()
        option = next(o for o in target["options"] if o["kind"] == kind)
        if option["available"]:
            return listing, target, option
    pytest.fail(f"aucune cible pour un {kind}")


def test_market_describes_each_player_situation(manager):
    market = manager.get("/transfers").json()
    assert market["season_year"] == YEAR and market["negotiations"] == []
    listing = market["listings"][0]
    assert listing["playing_time"] in ("titulaire", "remplaçant", "réserviste")
    assert listing["years_left"] >= 1
    assert any(listing["precontract"] for listing in market["listings"])
    assert any(listing["transfer_fee"] is None for listing in market["listings"])  # intransférables


def test_transfer_is_negotiated_with_the_club_then_the_player(manager):
    listing, target, option = _find_target(manager, "transfer")
    player_id = listing["player"]["id"]
    assert target["playing_time_now"] and target["playing_time_here"]

    opened = manager.post(f"/transfers/{player_id}/open", json={"kind": "transfer"}).json()
    assert opened["stage"] == "club" and opened["fee_demand"] == option["fee_demand"]
    # Une seule négociation à la fois avec le même joueur.
    assert manager.post(f"/transfers/{player_id}/open", json={"kind": "loan"}).status_code == 400

    # Offre sérieuse mais insuffisante : le club baisse un peu sa demande.
    low = int(opened["fee_demand"] * 0.9)
    answer = manager.post(f"/transfers/negotiations/{opened['id']}/offer", json={"fee": low}).json()
    assert not answer["accepted"] and answer["negotiation"]["stage"] == "club"
    assert answer["negotiation"]["fee_demand"] < opened["fee_demand"]

    fee = answer["negotiation"]["fee_demand"]
    answer = manager.post(f"/transfers/negotiations/{opened['id']}/offer", json={"fee": fee}).json()
    assert answer["accepted"] and not answer["concluded"]
    assert answer["negotiation"]["stage"] == "player" and answer["negotiation"]["fee"] == fee

    balance = answer["overview"]["balance"]
    wage = answer["negotiation"]["wage_demand"]
    answer = manager.post(
        f"/transfers/negotiations/{opened['id']}/offer", json={"wage": wage, "years": 3}
    ).json()
    assert answer["concluded"] and answer["negotiation"]["stage"] == "done"
    assert answer["overview"]["balance"] == balance - fee
    assert answer["overview"]["squad_size"] == 32

    player = next(p for p in manager.get("/clubs/3").json()["players"] if p["id"] == player_id)
    assert player["wage"] == wage and player["contract_until"] == YEAR + 2
    labels = [t["label"] for t in manager.get("/finances").json()["transactions"]]
    assert any(label.startswith("Achat · ") for label in labels)


def test_lowball_offers_end_the_talks(manager):
    listing, _, _ = _find_target(manager, "transfer")
    opened = manager.post(
        f"/transfers/{listing['player']['id']}/open", json={"kind": "transfer"}
    ).json()
    for _ in range(4):
        answer = manager.post(
            f"/transfers/negotiations/{opened['id']}/offer", json={"fee": 5_000}
        ).json()
    assert answer["negotiation"]["stage"] == "failed"
    assert (
        manager.post(
            f"/transfers/negotiations/{opened['id']}/offer", json={"fee": 5_000}
        ).status_code
        == 400
    )
    # On peut rouvrir ensuite.
    assert (
        manager.post(
            f"/transfers/{listing['player']['id']}/open", json={"kind": "transfer"}
        ).status_code
        == 201
    )


def test_loan_returns_to_the_owner_at_the_end_of_the_season(manager):
    listing, _, option = _find_target(manager, "loan")
    player_id, owner_id = listing["player"]["id"], listing["club_id"]
    opened = manager.post(f"/transfers/{player_id}/open", json={"kind": "loan"}).json()
    assert opened["stage"] == "player" and opened["wage_demand"] == option["wage"]

    answer = manager.post(f"/transfers/negotiations/{opened['id']}/offer", json={}).json()
    assert answer["concluded"]
    player = next(p for p in manager.get("/clubs/3").json()["players"] if p["id"] == player_id)
    assert player["loaned_from"] == owner_id and player["loaned_from_name"] == listing["club_name"]
    assert manager.post(f"/transfers/sell/{player_id}").status_code == 400  # pas à vendre
    # Un prêté n'apparaît pas sur le marché.
    market = manager.get("/transfers").json()
    assert all(row["player"]["id"] != player_id for row in market["listings"])

    for _ in range(21):
        manager.post("/seasons/current/play")
    manager.post("/seasons/next")
    assert all(p["id"] != player_id for p in manager.get("/clubs/3").json()["players"])
    assert any(p["id"] == player_id for p in manager.get(f"/clubs/{owner_id}").json()["players"])


def test_precontract_brings_the_player_at_the_next_season(manager):
    listing, _, option = _find_target(manager, "precontract")
    player_id = listing["player"]["id"]
    opened = manager.post(f"/transfers/{player_id}/open", json={"kind": "precontract"}).json()
    assert opened["stage"] == "player" and opened["fee_demand"] is None

    wage = option["wage_demand"]
    answer = manager.post(
        f"/transfers/negotiations/{opened['id']}/offer", json={"wage": wage, "years": 2}
    ).json()
    assert answer["concluded"] and answer["negotiation"]["stage"] == "agreed"
    # Il n'a pas encore bougé, mais l'accord est listé.
    assert all(p["id"] != player_id for p in manager.get("/clubs/3").json()["players"])
    assert any(n["id"] == opened["id"] for n in answer["overview"]["negotiations"])
    assert manager.delete(f"/transfers/negotiations/{opened['id']}").status_code == 400

    for _ in range(21):
        manager.post("/seasons/current/play")
    manager.post("/seasons/next")
    player = next(p for p in manager.get("/clubs/3").json()["players"] if p["id"] == player_id)
    assert player["wage"] == wage and player["contract_until"] == YEAR + 1 + 1
    assert manager.get("/transfers").json()["negotiations"] == []


def test_abandon_a_negotiation(manager):
    listing, _, _ = _find_target(manager, "transfer")
    opened = manager.post(
        f"/transfers/{listing['player']['id']}/open", json={"kind": "transfer"}
    ).json()
    overview = manager.delete(f"/transfers/negotiations/{opened['id']}").json()
    assert overview["negotiations"] == []


def test_contracts_are_renewed_when_they_expire(manager):
    for _ in range(21):
        manager.post("/seasons/current/play")
    manager.post("/seasons/next")
    players = manager.get("/clubs/3").json()["players"]
    assert all(p["contract_until"] >= YEAR + 1 for p in players)
