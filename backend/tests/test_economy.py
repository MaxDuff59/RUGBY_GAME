"""Règles économiques : valeur, salaires, infrastructures."""

import pytest

from engine.economy import (
    STADIUM_STEPS,
    WAGE_MIN,
    FacilityKind,
    apply_upgrade,
    asking_price,
    market_value,
    sale_price,
    severance,
    upgrade_cost,
    wage_for,
)
from models import Facilities, Player, Position, StaffMember, StaffRole


def make_player(level: int, age: int = 25) -> Player:
    attributes = dict.fromkeys(
        ["pace", "power", "handling", "passing", "kicking", "tackling", "scrum", "lineout"], level
    )
    return Player(1, "Léo", "Marant", age, Position.WING, **attributes)


def test_better_players_are_worth_more():
    values = [market_value(make_player(level)) for level in (8, 11, 14, 17, 20)]
    assert values == sorted(values)
    assert values[0] < values[-1] / 10


def test_young_players_are_worth_more_than_old_ones_at_equal_level():
    young, prime, old = (market_value(make_player(14, age)) for age in (21, 26, 34))
    assert young > prime > old


def test_wage_follows_value_with_a_floor():
    assert wage_for(make_player(5)) == WAGE_MIN
    assert wage_for(make_player(16)) > wage_for(make_player(12)) > WAGE_MIN


def test_buying_costs_more_than_selling():
    player = make_player(14)
    assert asking_price(player) > sale_price(player)


def test_severance_is_half_the_wage():
    member = StaffMember(1, "Paul", "Verchel", StaffRole.FORWARDS_COACH, level=3, wage=110_000)
    assert severance(member) == 55_000


@pytest.mark.parametrize("level", [0, 6])
def test_staff_level_out_of_range_is_rejected(level):
    with pytest.raises(ValueError):
        StaffMember(1, "Paul", "Verchel", StaffRole.DOCTOR, level=level, wage=1)


def test_stadium_upgrades_follow_the_steps_until_the_last_one():
    facilities = Facilities(stadium_capacity=STADIUM_STEPS[0])
    for expected in STADIUM_STEPS[1:]:
        assert upgrade_cost(facilities, FacilityKind.STADIUM) > 0
        apply_upgrade(facilities, FacilityKind.STADIUM)
        assert facilities.stadium_capacity == expected
    assert upgrade_cost(facilities, FacilityKind.STADIUM) is None


def test_training_centre_costs_more_at_each_level_and_stops_at_five():
    facilities = Facilities(training_level=1)
    costs = []
    while (cost := upgrade_cost(facilities, FacilityKind.TRAINING)) is not None:
        costs.append(cost)
        apply_upgrade(facilities, FacilityKind.TRAINING)
    assert facilities.training_level == 5
    assert costs == sorted(costs) and len(costs) == 4
