"""Tests du staff technique : ce que chaque entraîneur change au jeu."""

import copy
import random

from engine.coaching import NEUTRAL, coaching, effect
from engine.match_engine import LiveMatch, kick_success_probability, simulate_match, team_strength
from models import StaffMember, StaffRole
from tests.conftest import make_club

TECHNICAL = (
    StaffRole.FORWARDS_COACH,
    StaffRole.ATTACK_COACH,
    StaffRole.DEFENCE_COACH,
    StaffRole.KICKING_COACH,
    StaffRole.ANALYST,
)


def staffed(club, level, roles=TECHNICAL):
    """Une copie du club avec un staff de ce niveau aux postes `roles` (0 : vacants)."""
    club = copy.deepcopy(club)
    # Le médecin reste en place : un club avec des postes vacants a quand même un staff.
    club.staff = [StaffMember(1, "Doc", "Teur", StaffRole.DOCTOR, 3, 0, club.id)]
    if level:
        club.staff += [
            StaffMember(10 + i, "Coach", role.value, role, level, 0, club.id)
            for i, role in enumerate(roles)
        ]
    return club


def test_a_team_without_staff_is_coached_at_the_reference_level():
    assert coaching(make_club(1, level=12)) == NEUTRAL
    average = coaching(staffed(make_club(1, level=12), 3))
    assert average == NEUTRAL


def test_better_coaches_lift_their_part_of_the_game():
    club = make_club(1, level=12)
    good, poor, vacant = (coaching(staffed(club, level)) for level in (5, 1, 0))
    assert good.forwards > 1 > poor.forwards > vacant.forwards
    assert good.attack > 1 > poor.attack
    assert good.defence > 1 > poor.defence
    assert good.analysis > 1 > poor.analysis
    assert good.kicking > 0 > poor.kicking > vacant.kicking


def test_one_coach_only_touches_his_own_lines():
    club = make_club(1, level=12)
    base = team_strength(staffed(club, 3))
    forwards = team_strength(staffed(club, 5, (StaffRole.FORWARDS_COACH,)))
    assert forwards.set_piece > base.set_piece and forwards.pack > base.pack
    assert forwards.attack < base.attack  # l'entraîneur de l'attaque est vacant


def test_the_kicking_coach_makes_the_kicker_more_reliable():
    home, away = make_club(1, level=12), make_club(2, level=12, seed=2)
    live = LiveMatch(staffed(home, 5), staffed(away, 1))
    kicker = max(home.players, key=lambda p: p.kicking)
    base = kick_success_probability(kicker.kicking)
    assert (
        live._kick_probability(live.home, kicker) > base > live._kick_probability(live.away, kicker)
    )


def test_a_top_staff_wins_more_matches():
    club = make_club(1, level=12, seed=1)
    good, poor = staffed(club, 5), staffed(club, 1)
    poor.id = 2
    rng = random.Random(3)
    wins = 0
    for i in range(600):
        home, away = (good, poor) if i % 2 == 0 else (poor, good)
        match = simulate_match(home, away, rng=rng)
        mine, theirs = (
            (match.home_score, match.away_score)
            if home is good
            else (match.away_score, match.home_score)
        )
        wins += mine > theirs
    assert wins / 600 > 0.55


def test_effect_shows_what_each_post_brings():
    assert effect(StaffRole.ATTACK_COACH, 3) == 0
    assert effect(StaffRole.ATTACK_COACH, 5) > 0 > effect(StaffRole.ATTACK_COACH, 0)
    assert effect(StaffRole.PHYSIO, 5) < effect(StaffRole.PHYSIO, 1) == 0
    assert effect(StaffRole.FITNESS_COACH, 5) > effect(StaffRole.FITNESS_COACH, 0) == 0
