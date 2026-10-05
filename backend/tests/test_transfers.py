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
    bargain,
    can_precontract,
    club_lends,
    club_level,
    opening_ask,
    playing_time,
    preferred_years,
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


def test_bargaining_converges_then_makes_a_last_effort():
    target, ask = 100_000, opening_ask(100_000, 1.3, 1_000)
    assert ask == 130_000
    assert bargain(ask, target, 130_000, None, 1_000) == ("accepted", ask)
    assert bargain(ask, target, 50_000, None, 1_000) == ("insulted", ask)  # sous 60 %
    # Il descend vers son objectif, jamais en dessous.
    verdict, lower = bargain(ask, target, 110_000, None, 1_000)
    assert verdict == "closer" and target < lower < ask
    assert bargain(ask, target, 70_000, None, 1_000)[1] == target
    # Une offre qui ne progresse pas l'agace sans le faire bouger.
    assert bargain(lower, target, 110_000, 110_000, 1_000) == ("stalled", lower)
    # À son objectif : il campe si l'offre est loin, coupe la poire en deux si elle est proche.
    assert bargain(target, target, 80_000, 70_000, 1_000) == ("last_word", target)
    verdict, effort = bargain(target, target, 92_000, 80_000, 1_000)
    assert verdict == "effort" and 90_000 <= effort < target
    assert bargain(effort, target, effort, 92_000, 1_000)[0] == "accepted"


def test_contract_length_wishes_follow_age():
    player = make_club(1, level=12).players[0]
    player.age = 22
    assert preferred_years(player) == (3, 5)
    player.age = 34
    assert preferred_years(player) == (1, 2)


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


def _find_target(manager, kind, keep=lambda listing: True):
    """Un joueur du marché pour lequel la voie `kind` est ouverte, avec son approche.

    `keep` : condition supplémentaire sur la fiche du marché.
    """
    market = manager.get("/transfers").json()
    flag = {"transfer": "transfer_fee", "loan": "loanable", "precontract": "precontract"}[kind]
    for listing in market["listings"]:
        if not listing[flag] or not keep(listing):
            continue
        target = manager.get(f"/transfers/{listing['player']['id']}").json()
        option = next(o for o in target["options"] if o["kind"] == kind)
        # Un transfert doit rester payable, sinon l'accord échouerait sur la trésorerie.
        affordable = kind != "transfer" or option["fee_demand"] <= market["balance"]
        if option["available"] and affordable:
            return listing, target, option
    pytest.fail(f"aucune cible pour un {kind}")


def test_market_describes_each_player_situation(manager):
    market = manager.get("/transfers").json()
    assert market["season_year"] == YEAR and market["negotiations"] == []
    listing = next(listing for listing in market["listings"] if not listing["free_agent"])
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
    years = target["preferred_years"][0]
    # Une durée hors de ses attentes ne se discute pas.
    low, high = target["preferred_years"]
    too_long = high + 1 if high < 5 else low - 1  # hors de ses attentes, mais entre 1 et 5
    answer = manager.post(
        f"/transfers/negotiations/{opened['id']}/offer", json={"wage": wage, "years": too_long}
    ).json()
    assert not answer["accepted"] and "saisons" in answer["message"]

    answer = manager.post(
        f"/transfers/negotiations/{opened['id']}/offer", json={"wage": wage, "years": years}
    ).json()
    assert answer["concluded"] and answer["negotiation"]["stage"] == "done"
    assert answer["overview"]["balance"] == balance - fee
    assert answer["overview"]["squad_size"] == 32

    player = next(p for p in manager.get("/clubs/3").json()["players"] if p["id"] == player_id)
    assert player["wage"] == wage and player["contract_until"] == YEAR + years - 1
    labels = [t["label"] for t in manager.get("/finances").json()["transactions"]]
    assert any(label.startswith("Achat · ") for label in labels)


def test_lowball_offers_end_the_talks(manager):
    listing, _, _ = _find_target(manager, "transfer")
    opened = manager.post(
        f"/transfers/{listing['player']['id']}/open", json={"kind": "transfer"}
    ).json()
    for _ in range(3):
        answer = manager.post(
            f"/transfers/negotiations/{opened['id']}/offer", json={"fee": 5_000}
        ).json()
        # Une offre dérisoire ne fait pas bouger le club, et use vite sa patience.
        assert answer["negotiation"]["fee_demand"] == opened["fee_demand"]
    assert answer["negotiation"]["stage"] == "failed"
    assert "ne veut plus discuter" in answer["message"]
    assert answer["negotiation"]["closed_by"] == "them"
    assert (
        manager.post(
            f"/transfers/negotiations/{opened['id']}/offer", json={"fee": 5_000}
        ).status_code
        == 400
    )
    # Il s'en souvient : pas de discussion avant la fin du délai, quelle que soit la voie.
    player_id = listing["player"]["id"]
    target = manager.get(f"/transfers/{player_id}").json()
    assert target["talks_closed_until"] == answer["negotiation"]["cooldown_until"]
    assert target["grudges"] == 1
    assert all(not option["available"] for option in target["options"])
    assert (
        manager.post(f"/transfers/{player_id}/open", json={"kind": "transfer"}).status_code == 400
    )
    market = manager.get("/transfers").json()
    row = next(item for item in market["listings"] if item["player"]["id"] == player_id)
    assert row["talks_closed_until"] is not None
    # Le délai passé, il revient plus exigeant et moins patient.
    until = answer["negotiation"]["cooldown_until"]
    for _ in range(21):
        if (
            manager.get("/transfers").json()["listings"]
            and manager.get(f"/transfers/{player_id}").json()["talks_closed_until"] is None
        ):
            break
        manager.post("/seasons/current/play")
    target = manager.get(f"/transfers/{player_id}").json()
    assert target["talks_closed_until"] is None and until is not None
    option = next(o for o in target["options"] if o["kind"] == "transfer")
    if option["available"]:
        reopened = manager.post(f"/transfers/{player_id}/open", json={"kind": "transfer"}).json()
        assert reopened["fee_demand"] > opened["fee_demand"]
        assert reopened["patience"] == 5
        assert "pas oublié" in reopened["message"]


def test_leaving_the_table_myself_is_forgiven_quickly(manager):
    listing, _, _ = _find_target(manager, "transfer")
    player_id = listing["player"]["id"]
    opened = manager.post(f"/transfers/{player_id}/open", json={"kind": "transfer"}).json()
    overview = manager.delete(f"/transfers/negotiations/{opened['id']}").json()
    assert overview["negotiations"] == []
    target = manager.get(f"/transfers/{player_id}").json()
    assert target["grudges"] == 0 and target["talks_closed_until"] is not None
    assert (
        manager.post(f"/transfers/{player_id}/open", json={"kind": "transfer"}).status_code == 400
    )
    # Deux semaines plus tard, tout est oublié.
    for _ in range(3):
        manager.post("/seasons/current/play")
    target = manager.get(f"/transfers/{player_id}").json()
    assert target["talks_closed_until"] is None
    reopened = manager.post(f"/transfers/{player_id}/open", json={"kind": "transfer"}).json()
    assert reopened["fee_demand"] == opened["fee_demand"] and reopened["patience"] == 6


def test_loan_returns_to_the_owner_at_the_end_of_the_season(manager):
    # Un prêté encore sous contrat la saison prochaine et loin de la retraite :
    # sinon il pourrait partir libre ou raccrocher au lieu de rentrer chez lui.
    listing, _, option = _find_target(
        manager, "loan", keep=lambda row: row["years_left"] >= 2 and row["player"]["age"] <= 32
    )
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
    listing, target, option = _find_target(manager, "precontract")
    player_id = listing["player"]["id"]
    opened = manager.post(f"/transfers/{player_id}/open", json={"kind": "precontract"}).json()
    assert opened["stage"] == "player" and opened["fee_demand"] is None

    years = target["preferred_years"][1]
    # Marchandage : le joueur ouvre haut, se rapproche à chaque offre sérieuse,
    # et finit par signer à son seuil (inférieur à sa demande d'ouverture).
    opening = option["wage_demand"]
    ask, wage = opening, int(opening * 0.8)
    for _ in range(5):
        answer = manager.post(
            f"/transfers/negotiations/{opened['id']}/offer", json={"wage": wage, "years": years}
        ).json()
        if answer["concluded"]:
            break
        assert answer["negotiation"]["wage_demand"] <= ask
        ask = answer["negotiation"]["wage_demand"]
        wage = int(wage * 1.05)
    assert answer["concluded"] and answer["negotiation"]["stage"] == "agreed"
    assert wage < opening
    # Il n'a pas encore bougé, mais l'accord est listé.
    assert all(p["id"] != player_id for p in manager.get("/clubs/3").json()["players"])
    assert any(n["id"] == opened["id"] for n in answer["overview"]["negotiations"])
    assert manager.delete(f"/transfers/negotiations/{opened['id']}").status_code == 400

    for _ in range(21):
        manager.post("/seasons/current/play")
    manager.post("/seasons/next")
    player = next(p for p in manager.get("/clubs/3").json()["players"] if p["id"] == player_id)
    assert player["wage"] == wage and player["contract_until"] == YEAR + 1 + years - 1
    assert manager.get("/transfers").json()["negotiations"] == []
