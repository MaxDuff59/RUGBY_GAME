"""Calendrier daté, phases finales et intersaison."""

import itertools
import random
from datetime import date

import pytest

from engine.calendar import PLAYOFF_ROUNDS, season_dates
from engine.economy import attendance, matchday_wages
from engine.offseason import age_players, generate_youth, retirees
from engine.season import barrage_pairings, final_pairing, semi_pairings
from models import Facilities, Match, Stage
from tests.conftest import make_club

# --- Calendrier ----------------------------------------------------------------------


def test_matchdays_fall_on_saturdays_from_september():
    regular, playoffs = season_dates(2026, 26)
    assert len(regular) == 26 and len(playoffs) == PLAYOFF_ROUNDS
    assert regular[0] == date(2026, 9, 5)
    assert all(day.weekday() == 5 for day in regular + playoffs)
    # Les phases finales suivent la saison régulière.
    assert playoffs[0] > regular[-1]


def test_breaks_skip_exactly_eight_saturdays():
    regular, _ = season_dates(2026, 26)
    gaps = [(later - earlier).days for earlier, later in zip(regular, regular[1:], strict=False)]
    # 3 samedis en novembre, 2 à Noël, 3 pendant le Six Nations.
    assert sorted(gap for gap in gaps if gap > 7) == [21, 28, 28]
    assert regular[-1] < date(2027, 6, 1)


# --- Phases finales ------------------------------------------------------------------

SEEDING = list(range(1, 15))  # club 1 = 1er, club 14 = dernier


def played(home: int, away: int, home_score: int, away_score: int, stage: Stage) -> Match:
    return Match(home, away, home_score=home_score, away_score=away_score, stage=stage)


def test_barrages_pit_third_against_sixth_and_fourth_against_fifth():
    assert barrage_pairings(SEEDING) == [(3, 6), (4, 5)]


def test_semis_and_final_follow_the_winners():
    barrages = [played(3, 6, 20, 10, Stage.BARRAGE), played(4, 5, 10, 25, Stage.BARRAGE)]
    # Le 1er reçoit le vainqueur de 4e-5e (le 5e), le 2e reçoit le 3e.
    assert semi_pairings(SEEDING, barrages) == [(1, 5), (2, 3)]

    semis = [played(1, 5, 30, 12, Stage.SEMI), played(2, 3, 9, 15, Stage.SEMI)]
    assert final_pairing(SEEDING, semis) == (1, 3)


def test_draw_in_playoffs_goes_to_the_better_seed():
    match = played(4, 5, 20, 20, Stage.BARRAGE)
    assert match.winner_id(SEEDING) == 4
    reversed_hosting = played(5, 4, 20, 20, Stage.BARRAGE)
    assert reversed_hosting.winner_id(SEEDING) == 4


def test_barrages_need_six_clubs():
    with pytest.raises(ValueError):
        barrage_pairings([1, 2, 3])


# --- Économie d'une journée ----------------------------------------------------------


def test_attendance_grows_with_rank_and_fills_in_playoffs():
    rng = random.Random(0)
    first = attendance(10_000, rank=1, club_count=14, rng=rng)
    last = attendance(10_000, rank=14, club_count=14, rng=rng)
    assert 5_000 <= last < first <= 10_000
    assert attendance(10_000, rank=14, club_count=14, playoff=True) == 10_000


def test_matchday_wages_split_the_season_bill():
    club = make_club(1, level=12)
    club.players[0].wage = 260_000
    assert (
        matchday_wages(club, regular_matchdays=26) == (club.player_wages + club.staff_wages) // 26
    )


# --- Intersaison ---------------------------------------------------------------------


def test_players_age_and_the_oldest_retire():
    club = make_club(1, level=12)
    for player in club.players:
        player.age = 30
    club.players[0].age = 35
    age_players(club)
    assert club.players[0].age == 36
    assert retirees(club) == [club.players[0]]


def test_academy_produces_young_players_where_the_squad_is_thin():
    club = make_club(1, level=12)
    club.facilities = Facilities(academy_level=3)
    club.players = [p for p in club.players if p.position.value != "HOOKER"]  # plus de talonneur

    youths = generate_youth(club, itertools.count(1000), random.Random(0))
    assert len(youths) == 3
    assert all(18 <= y.age <= 20 and y.club_id == club.id for y in youths)
    assert youths[0].position.value == "HOOKER"
