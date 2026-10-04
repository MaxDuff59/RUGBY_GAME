"""Tests du moteur de match (sans FastAPI ni base de données)."""

import random

from engine.match_engine import MATCH_MINUTES, select_lineup, simulate_match
from models import EventType, Position
from tests.conftest import make_club


def test_score_is_plausible(even_clubs):
    home, away = even_clubs
    rng = random.Random(0)
    for _ in range(300):
        match = simulate_match(home, away, rng=rng)

        assert match.is_played
        for score in (match.home_score, match.away_score):
            assert 0 <= score <= 120
            # Un score de 1, 2 ou 4 points est impossible au rugby.
            assert score not in (1, 2, 4)
        # Le score est bien la somme des événements.
        assert match.home_score == match.points_for(home.id)
        assert match.away_score == match.points_for(away.id)
        # Les événements sont dans le temps réglementaire et dans l'ordre.
        minutes = [e.minute for e in match.events]
        assert minutes == sorted(minutes)
        assert all(1 <= m <= MATCH_MINUTES for m in minutes)


def test_every_try_is_followed_by_a_conversion_attempt(even_clubs):
    home, away = even_clubs
    match = simulate_match(home, away, rng=random.Random(3))
    conversions = {EventType.CONVERSION, EventType.CONVERSION_MISSED}
    tries = [i for i, e in enumerate(match.events) if e.type == EventType.TRY]
    assert tries, "ce match de test devrait contenir au moins un essai"
    for index in tries:
        assert match.events[index + 1].type in conversions


def test_same_seed_gives_same_match(even_clubs):
    home, away = even_clubs
    first = simulate_match(home, away, rng=random.Random(42))
    second = simulate_match(home, away, rng=random.Random(42))
    assert first == second


def test_stronger_team_wins_more_often(strong_and_weak):
    strong, weak = strong_and_weak
    rng = random.Random(0)
    strong_wins = weak_wins = 0
    # 1000 matchs, moitié à domicile, moitié à l'extérieur pour neutraliser l'avantage du terrain.
    for i in range(1000):
        home, away = (strong, weak) if i % 2 == 0 else (weak, strong)
        match = simulate_match(home, away, rng=rng)
        strong_score, weak_score = match.points_for(strong.id), match.points_for(weak.id)
        strong_wins += strong_score > weak_score
        weak_wins += weak_score > strong_score

    assert strong_wins > 700
    # ... mais le hasard laisse quelques surprises.
    assert weak_wins > 0


def test_lineup_has_fifteen_players_with_the_right_positions(even_clubs):
    lineup = select_lineup(even_clubs[0])
    assert len(lineup) == 15
    assert len({p.id for p in lineup}) == 15
    assert sum(p.position == Position.PROP for p in lineup) == 2
    assert sum(p.position.is_forward for p in lineup) == 8


def test_incomplete_squad_can_still_play():
    club = make_club(1, level=12)
    # Plus aucun talonneur : le moteur complète avec d'autres joueurs.
    club.players = [p for p in club.players if p.position != Position.HOOKER]
    assert len(select_lineup(club)) == 15
    match = simulate_match(club, make_club(2, level=12), rng=random.Random(0))
    assert match.is_played
