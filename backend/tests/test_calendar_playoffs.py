"""Calendrier daté, phases finales et intersaison."""

import itertools
import random
from datetime import date

import pytest

from engine.calendar import PLAYOFF_ROUNDS, season_dates
from engine.economy import attendance, matchday_wages
from engine.offseason import age_players, retirees, youth_intake
from engine.season import (
    PlayoffFormat,
    barrage_pairings,
    final_pairing,
    playoff_round,
    semi_pairings,
)
from models import EventType, Facilities, Match, MatchEvent, Stage
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


def test_each_league_has_its_own_start_and_breaks():
    # Super Rugby : saison de l'hémisphère Sud, à partir de février de l'année suivante.
    regular, _ = season_dates(2026, 22, start=(2, 1), breaks=())
    assert regular[0] == date(2027, 2, 6)
    assert all((b - a).days == 7 for a, b in zip(regular, regular[1:], strict=False))
    # Pro D2 : dès la fin août ; une trêve de janvier tombe dans l'année suivante.
    regular, _ = season_dates(2026, 30, start=(8, 22), breaks=(((1, 10), 2),))
    assert regular[0] == date(2026, 8, 22)
    gaps = [(b - a).days for a, b in zip(regular, regular[1:], strict=False)]
    assert sorted(gap for gap in gaps if gap > 7) == [21]


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


def test_shootout_decides_a_drawn_playoff():
    match = played(4, 5, 20, 20, Stage.BARRAGE)
    match.events = [
        MatchEvent(100, EventType.SHOOTOUT_GOAL, 4, None),
        MatchEvent(100, EventType.SHOOTOUT_GOAL, 5, None),
        MatchEvent(100, EventType.SHOOTOUT_MISSED, 4, None),
        MatchEvent(100, EventType.SHOOTOUT_GOAL, 5, None),
    ]
    # Le 5e passe aux tirs au but, même si le 4e était mieux classé.
    assert match.winner_id(SEEDING) == 5
    assert match.went_to_extra_time and match.went_to_shootout
    assert match.result_for(5) == 1 and match.result_for(4) == -1


def test_draw_without_shootout_goes_to_the_better_seed():
    # Match joué avant l'arrivée des prolongations : le mieux classé passe.
    match = played(4, 5, 20, 20, Stage.BARRAGE)
    assert match.winner_id(SEEDING) == 4
    reversed_hosting = played(5, 4, 20, 20, Stage.BARRAGE)
    assert reversed_hosting.winner_id(SEEDING) == 4


def test_barrages_need_six_clubs():
    with pytest.raises(ValueError):
        barrage_pairings([1, 2, 3])


def run_playoffs(fmt: PlayoffFormat, winner) -> list[tuple[Stage, list[tuple[int, int]]]]:
    """Déroule les phases finales ; `winner(home, away)` désigne le vainqueur de chaque match."""
    rounds, played_by_stage = [], {}
    while (next_round := playoff_round(fmt, SEEDING, played_by_stage)) is not None:
        stage, pairings = next_round
        rounds.append(next_round)
        played_by_stage[stage] = [
            played(home, away, 20, 10, stage)
            if winner(home, away) == home
            else played(home, away, 10, 20, stage)
            for home, away in pairings
        ]
    return rounds


def test_premiership_semis_are_first_against_fourth_and_second_against_third():
    rounds = run_playoffs(PlayoffFormat.TOP4, min)
    assert rounds == [(Stage.SEMI, [(1, 4), (2, 3)]), (Stage.FINAL, [(1, 2)])]


def test_urc_quarters_follow_the_bracket():
    # Le 8e et le 6e créent la surprise ; tableau 1-8 / 4-5 et 2-7 / 3-6.
    rounds = run_playoffs(PlayoffFormat.TOP8, lambda h, a: a if a in (6, 8) else min(h, a))
    assert rounds[0] == (Stage.QUARTER, [(1, 8), (2, 7), (3, 6), (4, 5)])
    assert rounds[1] == (Stage.SEMI, [(4, 8), (2, 6)])
    assert rounds[2] == (Stage.FINAL, [(6, 8)])


def test_super_rugby_brings_back_the_best_loser_as_fourth_seed():
    # 1-6, 2-5, 3-4 : le 5e bat le 2e, meilleur perdant, qui revient en 4e (à l'extérieur).
    rounds = run_playoffs(PlayoffFormat.SUPER6, lambda h, a: a if a == 5 else min(h, a))
    assert rounds[0] == (Stage.QUARTER, [(1, 6), (2, 5), (3, 4)])
    assert rounds[1] == (Stage.SEMI, [(1, 2), (3, 5)])
    assert rounds[2] == (Stage.FINAL, [(1, 5)])


def test_top14_format_matches_the_barrage_rules():
    rounds = run_playoffs(PlayoffFormat.TOP6, min)
    assert [stage for stage, _ in rounds] == [Stage.BARRAGE, Stage.SEMI, Stage.FINAL]
    assert rounds[1][1] == [(1, 4), (2, 3)]


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


def test_academy_produces_young_players_where_the_youth_squad_is_thin():
    club = make_club(1, level=12)
    club.facilities = Facilities(academy_level=3)
    # Des espoirs à tous les postes sauf talonneur.
    for player in club.players[:8]:
        if player.position.value != "HOOKER":
            club.youths.append(player)

    newcomers = youth_intake(club, itertools.count(1000), random.Random(0))
    assert len(newcomers) == 2 + 3
    assert all(16 <= y.age <= 17 and y.club_id == club.id for y in newcomers)
    assert all(y.squad.value == "youth" and y.wage == 15_000 for y in newcomers)
    assert newcomers[0].position.value == "HOOKER"
