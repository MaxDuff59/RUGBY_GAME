"""Tests de la progression : potentiel caché, progrès au fil de la saison."""

import random

from engine.development import (
    OTHER_UNCERTAINTY,
    OWN_UNCERTAINTY,
    Training,
    ceiling,
    develop,
    estimate,
    initial_potential,
    playing_factor,
    tick,
)
from engine.offseason import develop_players
from models import PlayerMatchStats
from tests.conftest import make_club


def _player(age: int, seed: int = 0):
    player = make_club(1, 11, seed=seed).players[0]
    player.age = age
    player.potential = None
    return player


def test_young_players_have_more_upside():
    young = [initial_potential(_player(17, s)) - _player(17, s).overall for s in range(40)]
    old = [initial_potential(_player(30, s)) - _player(30, s).overall for s in range(40)]
    assert sum(young) / 40 > 3
    assert all(abs(gap) < 0.06 for gap in old)  # arrivé : le potentiel est sa note, arrondie


def test_potential_is_drawn_once_and_stays():
    player = _player(19)
    first = ceiling(player)
    player.age = 25  # plus tard, il reste celui tiré au départ
    assert ceiling(player) == first == initial_potential(_player(19))


def test_playing_well_helps():
    bench = playing_factor(None)
    full = PlayerMatchStats(minutes=80, rating=6.0)
    great = PlayerMatchStats(minutes=80, rating=8.0)
    poor = PlayerMatchStats(minutes=80, rating=4.5)
    assert bench < playing_factor(poor) < playing_factor(full) < playing_factor(great)


def test_a_young_starter_grows_over_a_season_up_to_his_potential():
    player = _player(18, seed=3)
    player.potential = player.overall + 4
    start = player.overall
    rng = random.Random(0)
    for _ in range(30):
        tick(player, 3, PlayerMatchStats(minutes=80, rating=6.5), rng)
    assert player.overall > start
    assert player.overall <= player.potential
    assert player.season_gain == round((player.overall - start) * 9)
    # Arrivé à son potentiel, il ne progresse plus.
    player.potential = player.overall
    assert tick(player, 5, PlayerMatchStats(minutes=80, rating=9), rng) == []


def test_playing_time_and_facilities_make_the_difference():
    def season(minutes: int, facility: int) -> float:
        player = _player(19, seed=5)
        player.potential = player.overall + 4
        start, rng = player.overall, random.Random(1)
        for _ in range(30):
            line = PlayerMatchStats(minutes=minutes, rating=6.0) if minutes else None
            tick(player, facility, line, rng)
        return player.overall - start

    assert season(80, 5) > season(80, 1) > season(0, 1)


def test_training_focus_steers_the_gains():
    def tackling_gains(training: Training) -> int:
        gained = []
        for seed in range(12):
            player = _player(18, seed=seed)
            player.potential = 19.5
            rng = random.Random(seed)
            for _ in range(60):
                gained += tick(player, 3, PlayerMatchStats(minutes=80, rating=6.0), rng, training)
        return gained.count("tackling")

    assert tackling_gains(Training(focus=("tackling",))) > tackling_gains(Training())


def test_develop_a_club_after_its_match():
    club = make_club(2, 11, seed=4)
    for player in club.players:
        player.age, player.potential = 19, player.overall + 3
    stats = {p.id: PlayerMatchStats(minutes=80, rating=7.0) for p in club.players[:15]}
    gains = {}
    rng = random.Random(3)
    for _ in range(10):
        for player_id, names in develop(club, stats, rng).items():
            gains.setdefault(player_id, []).extend(names)
    assert gains
    assert all(p.progress >= 0 for p in club.players)


def test_offseason_only_makes_veterans_decline():
    club = make_club(3, 12, seed=6)
    for player in club.players:
        player.age = 21
    before = [p.overall for p in club.players]
    develop_players(club, random.Random(0))
    assert [p.overall for p in club.players] == before  # la croissance est en saison
    for player in club.players:
        player.age = 34
    develop_players(club, random.Random(0))
    assert sum(p.overall for p in club.players) < sum(before)


def test_the_club_knows_its_own_players_better():
    player = _player(18, seed=8)
    low, high = estimate(player, OWN_UNCERTAINTY)
    far_low, far_high = estimate(player, OTHER_UNCERTAINTY)
    assert high - low < far_high - far_low
    assert low >= player.overall


# --- API -------------------------------------------------------------------------------


def test_players_progress_during_the_season_and_it_is_saved(manager):
    squad = manager.get("/clubs/3").json()["players"]
    assert all(p["potential_low"] <= p["potential_high"] for p in squad)
    for _ in range(4):
        manager.post("/seasons/current/play")
    squad = manager.get("/clubs/3").json()["players"]
    assert any(p["season_gain"] > 0 for p in squad)
