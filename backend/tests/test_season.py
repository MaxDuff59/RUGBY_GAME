"""Tests du calendrier et de la simulation de saison."""

import random
from collections import Counter

import pytest

from data.generator import generate_clubs
from engine.economy import SQUAD_MAX
from engine.season import generate_fixtures, rng_for
from engine.world import World
from models import Stage


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


def make_world(seed: int = 0, **options) -> World:
    return World(generate_clubs(10, random.Random(0)), seed=seed, **options)


def test_simulated_season_is_consistent():
    world = make_world()
    season = world.play_season()

    regular = [m for m in season.matches if m.stage == Stage.REGULAR]
    assert len(regular) == 90
    assert all(m.is_played for m in season.matches)
    table = world.table("top14")
    for row in table:
        assert row.played == 18
        assert row.won + row.drawn + row.lost == 18
    # Tous les points marqués sont encaissés par quelqu'un.
    assert sum(r.points_for for r in table) == sum(r.points_against for r in table)
    # Le classement est trié par points.
    points = [r.league_points for r in table]
    assert points == sorted(points, reverse=True)


def test_season_ends_with_playoffs_and_a_champion():
    world = make_world()
    assert world.champion("top14") is None
    season = world.play_season()

    # Formule du Top 14 : deux barrages, deux demi-finales, une finale.
    stages = Counter(m.stage for m in season.matches if m.stage != Stage.REGULAR)
    assert stages == {Stage.BARRAGE: 2, Stage.SEMI: 2, Stage.FINAL: 1}
    assert world.finished
    qualified = [row.club_id for row in world.table("top14")[:6]]
    assert world.champion("top14").id in qualified
    assert world.play_day() is None


def test_season_uses_the_whole_matchday():
    """La saison en mémoire joue la vraie journée : dates, blessures, argent."""
    world = make_world()
    balances = {club.id: club.balance for club in world.clubs.values()}
    report = world.play_day()

    assert len(report.played) == 5
    assert len({m.date for m in report.played}) == 1
    # Chaque club a touché ses sponsors et payé ses salaires.
    paid = {movement.club_id for movement in report.movements if movement.amount < 0}
    assert paid == set(world.clubs)
    for club in world.clubs.values():
        moves = [m.amount for m in report.movements if m.club_id == club.id]
        assert club.balance == balances[club.id] + sum(moves)
    world.play_season()
    injured = [p for club in world.clubs.values() for p in club.players if p.injury is not None]
    assert injured


def test_same_seed_replays_the_same_story():
    def story(seed: int) -> list:
        world = make_world(seed)
        world.play_season()
        world.offseason()
        world.play_season()
        return [
            [(m.home_club_id, m.away_club_id, m.home_score, m.away_score) for m in season.played]
            for season in world.seasons
        ] + [sorted(p.id for club in world.clubs.values() for p in club.players)]

    assert story(3) == story(3)
    assert story(3) != story(4)


def test_rng_for_depends_on_seed_and_moment():
    assert rng_for(1, "2026-09-05").random() == rng_for(1, "2026-09-05").random()
    assert rng_for(1, "2026-09-05").random() != rng_for(1, "2026-09-12").random()
    assert rng_for(1, "2026-09-05").random() != rng_for(2, "2026-09-05").random()


def test_offseason_starts_a_new_season():
    world = make_world()
    with pytest.raises(ValueError):
        world.offseason()
    ages = {p.id: p.age for club in world.clubs.values() for p in club.players}
    world.play_season()
    season = world.offseason()

    assert season.year == world.seasons[0].year + 1
    assert len(season.matches) == 90 and not season.played
    for club in world.clubs.values():
        assert len(club.players) <= SQUAD_MAX
        assert all(p.club_id == club.id for p in club.players)
        assert all(p.contract_until >= season.year for p in club.players)
        assert all(p.age == ages[p.id] + 1 for p in club.players if p.id in ages)
    assert all(p.club_id is None for p in world.free_agents)
    world.play_season()
    assert world.finished


def test_youth_leagues_are_played_on_request():
    world = make_world(youth_leagues=True)
    world.play_day()
    played = [m for m in world.season.youth_matches if m.is_played]
    assert len(played) == 5
