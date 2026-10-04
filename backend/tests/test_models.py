"""Règles portées par les modèles : bornes des attributs et classement Top 14."""

import pytest

from models import Player, Position, StandingRow


def make_player(**overrides) -> Player:
    data = dict(
        id=1, first_name="Léo", last_name="Marant", age=24, position=Position.WING,
        pace=10, power=10, handling=10, passing=10, kicking=10, tackling=10, scrum=10, lineout=10,
    )  # fmt: skip
    data.update(overrides)
    return Player(**data)


@pytest.mark.parametrize("value", [0, 21])
def test_attribute_out_of_range_is_rejected(value):
    with pytest.raises(ValueError):
        make_player(pace=value)


def test_forwards_and_backs():
    assert Position.PROP.is_forward
    assert Position.BACK_ROW.is_forward
    assert not Position.SCRUM_HALF.is_forward
    assert not Position.FULLBACK.is_forward


def test_win_draw_loss_points():
    row = StandingRow(club_id=1)
    row.record(scored=20, conceded=10, tries=2, tries_conceded=1)  # victoire : 4
    row.record(scored=15, conceded=15, tries=1, tries_conceded=1)  # nul : 2
    row.record(scored=3, conceded=30, tries=0, tries_conceded=4)  # défaite lourde : 0
    assert (row.won, row.drawn, row.lost) == (1, 1, 1)
    assert row.league_points == 6
    assert row.points_difference == 20 + 15 + 3 - 10 - 15 - 30


def test_offensive_bonus_needs_three_more_tries_than_opponent():
    row = StandingRow(club_id=1)
    row.record(scored=40, conceded=20, tries=5, tries_conceded=3)  # +2 essais : pas de bonus
    assert row.offensive_bonus == 0
    row.record(scored=40, conceded=20, tries=5, tries_conceded=2)  # +3 essais : bonus
    assert row.offensive_bonus == 1
    assert row.league_points == 4 + 4 + 1


def test_no_offensive_bonus_without_a_win():
    row = StandingRow(club_id=1)
    row.record(scored=35, conceded=36, tries=5, tries_conceded=0)
    assert row.offensive_bonus == 0
    assert row.defensive_bonus == 1  # défaite d'un point


@pytest.mark.parametrize(("conceded", "bonus"), [(25, 1), (26, 0)])
def test_defensive_bonus_for_loss_by_five_or_less(conceded, bonus):
    row = StandingRow(club_id=1)
    row.record(scored=20, conceded=conceded, tries=2, tries_conceded=2)
    assert row.defensive_bonus == bonus
    assert row.league_points == bonus
