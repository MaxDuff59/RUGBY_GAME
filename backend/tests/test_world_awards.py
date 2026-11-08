"""Les trophées mondiaux de la saison (engine/world_awards.py)."""

import random
from collections import Counter

from engine.match_engine import FORMATION, simulate_match
from engine.world_awards import (
    PLAYER_MATCHES,
    REVELATION_AGE,
    WorldAwardKind,
    world_awards,
)
from models import Club
from tests.conftest import make_club


def _season():
    """Six clubs en aller-retour (10 matchs chacun), puis deux sélections faites des
    meilleurs joueurs de deux clubs, qui se rencontrent trois fois."""
    clubs = [make_club(i, 11 + i % 3, seed=i) for i in range(1, 7)]
    rng = random.Random(0)
    club_matches = [
        simulate_match(home, away, rng=rng)
        for _ in range(2)
        for home in clubs
        for away in clubs
        if home is not away
    ]
    nations = [
        Club(id=9001, name="A", players=clubs[0].players),
        Club(id=9002, name="B", players=clubs[1].players),
    ]
    tests = [simulate_match(nations[i % 2], nations[1 - i % 2], rng=rng) for i in range(3)]
    players = {p.id: p for club in clubs for p in club.players}
    return club_matches, tests, players


def test_the_world_crowns_its_season():
    club_matches, tests, players = _season()
    awards = world_awards(club_matches, tests, players)
    kinds = Counter(a.kind for a in awards)
    for kind in (
        WorldAwardKind.PLAYER,
        WorldAwardKind.INTERNATIONAL,
        WorldAwardKind.TRIES,
        WorldAwardKind.POINTS,
        WorldAwardKind.TACKLES,
    ):
        assert kinds[kind] == 1, kind
    team = [a for a in awards if a.kind == WorldAwardKind.TEAM]
    assert len(team) == sum(FORMATION.values())
    assert all(players[a.player_id].position == a.position for a in team)
    best = next(a for a in awards if a.kind == WorldAwardKind.PLAYER)
    assert best.matches >= PLAYER_MATCHES and best.value == max(a.value for a in team)
    # Le meilleur joueur en sélection a joué les tests.
    international = next(a for a in awards if a.kind == WorldAwardKind.INTERNATIONAL)
    assert international.tests == 3


def test_the_best_prospect_is_young_and_retired_players_do_not_compete():
    club_matches, tests, players = _season()
    young = next(iter(players.values()))
    young.age = REVELATION_AGE
    for player in players.values():
        if player is not young:
            player.age = REVELATION_AGE + 5
    awards = world_awards(club_matches, tests, players)
    prospects = [a for a in awards if a.kind == WorldAwardKind.REVELATION]
    assert [a.player_id for a in prospects] in ([young.id], [])

    best = next(a for a in awards if a.kind == WorldAwardKind.PLAYER).player_id
    retired = {pid: p for pid, p in players.items() if pid != best}
    assert best not in {a.player_id for a in world_awards(club_matches, tests, retired)}
