"""Agents libres : vivier, ce qu'ils demandent, signature, intersaison."""

import itertools
import random

from engine.economy import wage_for
from engine.free_agents import (
    POOL_MAX,
    POOL_MIN,
    ai_pick,
    free_agent_wage,
    newcomers,
    quits,
    seasons_without_club,
    trim_pool,
)
from engine.transfers import TIME_STARTER, playing_time
from models import ATTRIBUTE_NAMES
from tests.conftest import make_club

YEAR = 2026


def play_season(client):
    while client.get("/seasons/current").json()["phase"] != "finished":
        client.post("/seasons/current/play")


def free_listings(market):
    return [listing for listing in market["listings"] if listing["free_agent"]]


# --- Règles -------------------------------------------------------------------------


def test_newcomers_fill_the_pool_without_contract():
    rng = random.Random(0)
    pool = newcomers([], itertools.count(1), YEAR, rng)
    assert len(pool) == POOL_MIN
    assert all(p.club_id is None and p.contract_until == YEAR - 1 for p in pool)
    assert all(seasons_without_club(p, YEAR) == 0 for p in pool)
    assert newcomers(pool, itertools.count(100), YEAR, rng) == []
    # Trop plein : les plus faibles s'en vont.
    crowd = newcomers([], itertools.count(1), YEAR, rng) * 3
    gone = trim_pool(crowd)
    assert len(crowd) - len(gone) == POOL_MAX or len(crowd) <= POOL_MAX
    assert max(p.overall for p in gone) <= min(p.overall for p in crowd if p not in gone)


def test_a_free_agent_asks_less_where_he_would_not_start():
    player = newcomers([], itertools.count(1000), YEAR, random.Random(1))[0]
    for name in ATTRIBUTE_NAMES:
        setattr(player, name, 15)
    small, big = make_club(1, level=6), make_club(2, level=19)
    assert playing_time(player, small) == TIME_STARTER
    assert playing_time(player, big) < TIME_STARTER
    assert free_agent_wage(player, small) == wage_for(player)
    assert free_agent_wage(player, big) < wage_for(player)


def test_free_agents_quit_after_a_season_without_club():
    rng = random.Random(0)
    player = newcomers([], itertools.count(1), YEAR, rng)[0]
    player.age = 30
    assert not quits(player, YEAR, rng)  # libre depuis l'intersaison
    player.contract_until = YEAR - 3  # deux saisons sans club
    assert quits(player, YEAR, rng)
    player.contract_until, player.age = YEAR - 1, 36
    assert quits(player, YEAR, rng)


def test_short_ai_clubs_sign_from_the_pool():
    club = make_club(1, level=12)
    pool = newcomers([], itertools.count(1000), YEAR, random.Random(0))
    assert ai_pick(club, pool) is None  # effectif complet
    del club.players[:4]
    assert ai_pick(club, pool) in pool


# --- Routes -------------------------------------------------------------------------


def test_free_agents_are_on_the_market(manager):
    free = free_listings(manager.get("/transfers").json())
    assert len(free) == POOL_MIN
    assert all(
        f["club_id"] is None and f["transfer_fee"] is None and f["wage_demand"] for f in free
    )
    target = manager.get(f"/transfers/{free[0]['player']['id']}").json()
    assert target["club"] is None
    assert [o["kind"] for o in target["options"]] == ["free"]
    assert target["options"][0]["available"]


def test_sign_a_free_agent(manager):
    listing = free_listings(manager.get("/transfers").json())[0]
    player_id = listing["player"]["id"]
    # Ni prêt ni transfert pour un joueur sans club.
    assert manager.post(f"/transfers/{player_id}/open", json={"kind": "loan"}).status_code == 400

    opened = manager.post(f"/transfers/{player_id}/open", json={"kind": "free"}).json()
    assert opened["stage"] == "player" and opened["club_name"] == "Agent libre"
    assert opened["wage_demand"] == listing["wage_demand"]
    years = manager.get(f"/transfers/{player_id}").json()["preferred_years"][0]
    answer = manager.post(
        f"/transfers/negotiations/{opened['id']}/offer",
        json={"wage": opened["wage_demand"], "years": years},
    ).json()
    assert answer["concluded"] and answer["negotiation"]["stage"] == "done"
    assert answer["overview"]["squad_size"] == 32
    assert player_id not in {f["player"]["id"] for f in free_listings(answer["overview"])}

    player = next(p for p in manager.get("/clubs/3").json()["players"] if p["id"] == player_id)
    assert player["wage"] == opened["wage_demand"]
    assert player["contract_until"] == YEAR + years - 1


def test_unextended_players_join_the_pool(manager):
    play_season(manager)
    open_ = [c for c in manager.get("/contracts").json()["pros"] if c["status"] == "open"]
    assert open_
    assert manager.post("/seasons/next").status_code == 201

    market = manager.get("/transfers").json()
    free = {f["player"]["id"]: f for f in free_listings(market)}
    assert POOL_MIN <= len(free) <= POOL_MAX
    released = [c["player"]["id"] for c in open_]
    # Nos joueurs non prolongés sont agents libres, sauf ceux qu'un club IA a repris.
    for player_id in released:
        club = manager.get(f"/players/{player_id}").json()["club"]
        assert (club is None and player_id in free) or (club is not None and club["id"] != 3)
    for club_id in (1, 2, 4):
        assert len(manager.get(f"/clubs/{club_id}").json()["players"]) >= 25
