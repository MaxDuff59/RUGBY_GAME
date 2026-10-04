"""Tests du calendrier et de la simulation de saison."""

import random
from collections import Counter

import pytest

from data.generator import generate_clubs
from engine.season import generate_fixtures, simulate_season


@pytest.mark.parametrize(
    ("club_count", "expected_matchdays"),
    [(2, 2), (3, 6), (4, 6), (9, 18), (10, 18), (14, 26)],
)
def test_fixture_count(club_count, expected_matchdays):
    # N pair : 2 x (N - 1) journées ; N impair : 2 x N (un club exempt par journée).
    fixtures = generate_fixtures(list(range(1, club_count + 1)))
    assert len(fixtures) == expected_matchdays


@pytest.mark.parametrize("club_count", [3, 4, 9, 10, 14])
def test_each_pair_meets_once_at_each_home(club_count):
    club_ids = list(range(1, club_count + 1))
    fixtures = generate_fixtures(club_ids)
    pairs = Counter(match for matchday in fixtures for match in matchday)

    # Chaque couple (domicile, extérieur) apparaît exactement une fois.
    assert len(pairs) == club_count * (club_count - 1)
    assert set(pairs.values()) == {1}
    # Tout le monde reçoit autant de fois.
    homes = Counter(home for matchday in fixtures for home, _ in matchday)
    assert set(homes.values()) == {club_count - 1}


@pytest.mark.parametrize("club_count", [4, 9, 10, 14])
def test_no_club_plays_twice_on_a_matchday(club_count):
    for matchday in generate_fixtures(list(range(1, club_count + 1))):
        clubs = [club for match in matchday for club in match]
        assert len(clubs) == len(set(clubs))


def test_home_and_away_alternate():
    fixtures = generate_fixtures(list(range(1, 15)))
    for club in range(1, 15):
        venues = "".join(
            "H" if home == club else "A"
            for matchday in fixtures
            for home, away in matchday
            if club in (home, away)
        )
        assert "HHHH" not in venues and "AAAA" not in venues


def test_needs_at_least_two_clubs():
    with pytest.raises(ValueError):
        generate_fixtures([1])


def test_simulated_season_is_consistent():
    clubs = generate_clubs(10, random.Random(0))
    season = simulate_season(clubs, year=2026, rng=random.Random(0))

    assert len(season.matches) == 90
    table = season.table()
    for row in table:
        assert row.played == 18
        assert row.won + row.drawn + row.lost == 18
    # Tous les points marqués sont encaissés par quelqu'un.
    assert sum(r.points_for for r in table) == sum(r.points_against for r in table)
    # Le classement est trié par points.
    points = [r.league_points for r in table]
    assert points == sorted(points, reverse=True)
