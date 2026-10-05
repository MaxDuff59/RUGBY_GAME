"""Tests du moteur de match (sans FastAPI ni base de données)."""

import random

from engine.match_engine import (
    MATCH_MINUTES,
    SHOOTOUT_KICKERS,
    select_lineup,
    simulate_match,
)
from models import EXTRA_TIME_MINUTES, EventType, Position
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


# --- Phases finales : prolongation et tirs au but -------------------------------------


def _knockouts(home, away, count=3000):
    rng = random.Random(0)
    return [simulate_match(home, away, rng=rng, knockout=True) for _ in range(count)]


def test_knockout_always_has_a_winner(even_clubs):
    home, away = even_clubs
    for match in _knockouts(home, away):
        assert match.result_for(home.id) == -match.result_for(away.id) != 0
        winner = match.winner_id([away.id, home.id])  # le classement ne départage plus
        assert match.result_for(winner) == 1


def test_extra_time_is_played_only_after_a_draw(even_clubs):
    home, away = even_clubs
    matches = _knockouts(home, away)
    extra = [m for m in matches if m.went_to_extra_time]
    assert extra, "3000 matchs serrés devraient bien donner quelques prolongations"
    for match in matches:
        last = MATCH_MINUTES + (EXTRA_TIME_MINUTES if match.went_to_extra_time else 0)
        assert all(1 <= e.minute <= last for e in match.events)
        regulation = [e for e in match.events if e.minute <= MATCH_MINUTES]
        home_80 = sum(e.points for e in regulation if e.club_id == home.id)
        away_80 = sum(e.points for e in regulation if e.club_id == away.id)
        assert match.went_to_extra_time == (home_80 == away_80)


def test_shootout_settles_a_draw_after_extra_time(even_clubs):
    home, away = even_clubs
    shootouts = [m for m in _knockouts(home, away) if m.went_to_shootout]
    assert shootouts, "3000 matchs serrés devraient bien donner quelques tirs au but"
    for match in shootouts:
        # Le score reste nul : seuls les tirs au but départagent.
        assert match.home_score == match.away_score
        assert match.shootout_for(home.id) != match.shootout_for(away.id)
        shootout = (EventType.SHOOTOUT_GOAL, EventType.SHOOTOUT_MISSED)
        kicks = [e for e in match.events if e.type in shootout]
        by_club = {club.id: [e for e in kicks if e.club_id == club.id] for club in (home, away)}
        # Les équipes tirent en alternance : jamais plus d'un tir d'écart.
        assert abs(len(by_club[home.id]) - len(by_club[away.id])) <= 1
        # Au-delà de 5 tirs chacun, mort subite : autant de tirs des deux côtés.
        if max(len(k) for k in by_club.values()) > SHOOTOUT_KICKERS:
            assert len(by_club[home.id]) == len(by_club[away.id])


def test_regular_season_match_can_end_in_a_draw(even_clubs):
    home, away = even_clubs
    rng = random.Random(0)
    matches = [simulate_match(home, away, rng=rng) for _ in range(1000)]
    assert any(m.home_score == m.away_score for m in matches)
    assert not any(m.went_to_extra_time for m in matches)
