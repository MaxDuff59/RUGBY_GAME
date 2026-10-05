"""Règles économiques : valeur, salaires, infrastructures."""

import random

import pytest

from engine.economy import (
    STADIUM_STEPS,
    WAGE_MIN,
    FacilityKind,
    add_amenity,
    amenity_refusal,
    apply_upgrade,
    asking_price,
    attendance,
    attendance_bonus,
    hospitality_revenue,
    market_value,
    sale_price,
    severance,
    sponsor_revenue,
    stand_slots,
    upgrade_cost,
    wage_for,
)
from models import (
    ATTRIBUTE_NAMES,
    AmenityKind,
    Facilities,
    Player,
    Position,
    StaffMember,
    StaffRole,
    StandSide,
)


def make_player(level: int, age: int = 25) -> Player:
    attributes = dict.fromkeys(ATTRIBUTE_NAMES, level)
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


def test_stands_gain_slots_as_the_stadium_grows():
    assert stand_slots(4_000) == 2
    assert stand_slots(12_000) == 3
    assert stand_slots(35_000) == 5


def test_amenities_fill_a_stand_then_are_refused():
    facilities = Facilities(stadium_capacity=4_000)
    assert amenity_refusal(facilities, StandSide.NORTH, AmenityKind.BUVETTE) is None
    add_amenity(facilities, StandSide.NORTH, AmenityKind.BUVETTE)
    add_amenity(facilities, StandSide.NORTH, AmenityKind.SPONSOR)
    assert amenity_refusal(facilities, StandSide.NORTH, AmenityKind.BUVETTE) is not None
    # L'autre tribune reste libre.
    assert amenity_refusal(facilities, StandSide.SOUTH, AmenityKind.BUVETTE) is None


def test_some_amenities_are_unique_in_the_stadium():
    facilities = Facilities(stadium_capacity=35_000)
    add_amenity(facilities, StandSide.NORTH, AmenityKind.SHOP)
    assert amenity_refusal(facilities, StandSide.SOUTH, AmenityKind.SHOP) == "Déjà installé"
    add_amenity(facilities, StandSide.EAST, AmenityKind.BOXES)
    add_amenity(facilities, StandSide.WEST, AmenityKind.BOXES)
    assert amenity_refusal(facilities, StandSide.NORTH, AmenityKind.BOXES) is not None


def test_amenities_bring_money_and_fans():
    bare = Facilities(stadium_capacity=12_000)
    furnished = Facilities(stadium_capacity=12_000)
    add_amenity(furnished, StandSide.NORTH, AmenityKind.SPONSOR)
    add_amenity(furnished, StandSide.NORTH, AmenityKind.BUVETTE)
    add_amenity(furnished, StandSide.SOUTH, AmenityKind.BOXES)
    add_amenity(furnished, StandSide.EAST, AmenityKind.SCREEN)

    assert sponsor_revenue(furnished) == sponsor_revenue(bare) + 6_000
    assert hospitality_revenue(bare, 10_000) == 0
    assert hospitality_revenue(furnished, 10_000) == 2 * 10_000 + 25_000
    assert attendance_bonus(bare) == 0
    rng_a, rng_b = random.Random(1), random.Random(1)
    assert attendance(12_000, 5, 14, rng=rng_a, bonus=attendance_bonus(furnished)) > attendance(
        12_000, 5, 14, rng=rng_b
    )
