"""Tests du momentum : une barre par minute, en raccord avec ce qui s'est passé."""

import random

from engine.match_engine import LiveMatch
from engine.momentum import CHANCE_MAX, PLAY_MAX, SCORED, minute_bar
from models import EventType, MatchEvent
from tests.conftest import make_club


def _played(seed: int = 5) -> LiveMatch:
    live = LiveMatch(make_club(1, 13, seed=1), make_club(2, 11, seed=2), rng=random.Random(seed))
    live.play_to_end()
    return live


def test_one_bar_per_minute_matching_the_scoring():
    live = _played()
    assert len(live.momentum) == live.minute == 80
    assert all(-100 <= bar <= 100 for bar in live.momentum)
    # Un essai : la barre entière, du côté de l'équipe qui marque.
    for event in live.events:
        if event.type == EventType.TRY:
            sign = 1 if event.club_id == 1 else -1
            assert live.momentum[event.minute - 1] == sign * SCORED[EventType.TRY]
    # Le plus fort domine plus souvent, mais l'autre a ses minutes.
    home = sum(bar > 0 for bar in live.momentum)
    assert 40 < home < 80


def test_the_graph_draws_no_randomness():
    """Le même match, au même hasard, donne le même score qu'avant le graphique : le
    calcul ne fait que lire la minute jouée."""
    first, second = _played(7), _played(7)
    assert first.momentum == second.momentum
    assert first.result().home_score == second.result().home_score


def test_a_minute_goes_to_the_most_threatening_side():
    calm = minute_bar(1, {1: 3, 2: 0}, None, [])
    assert 0 < calm <= PLAY_MAX
    assert minute_bar(1, {1: 1, 2: 2}, None, []) < 0  # l'adversaire a eu le jeu
    chance = minute_bar(1, {1: 3, 2: 0}, (2, 0.4), [])
    assert -CHANCE_MAX <= chance < -calm  # une action dangereuse pèse plus que le jeu courant
    scored = minute_bar(1, {1: 0, 2: 3}, None, [MatchEvent(30, EventType.PENALTY_GOAL, 1, 9)])
    assert scored == SCORED[EventType.PENALTY_GOAL]


def test_the_momentum_survives_a_saved_live_match():
    home, away = make_club(1, 12, seed=1), make_club(2, 12, seed=2)
    live = LiveMatch(home, away, rng=random.Random(3))
    live.advance(30)
    resumed = LiveMatch.from_state(home, away, live.to_state())
    assert resumed.momentum == live.momentum
    resumed.advance(10)
    live.advance(10)
    assert resumed.momentum == live.momentum and len(live.momentum) == 40
    # Un match commencé avant le graphique : ses minutes jouées restent vides.
    state = live.to_state()
    del state["momentum"]
    assert LiveMatch.from_state(home, away, state).momentum == [0] * 40
