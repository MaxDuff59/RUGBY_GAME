"""Le classement mondial des sélections (engine/ranking.py)."""

import datetime

import pytest

from engine.ranking import Test, exchange, standings

DAY = datetime.date(2026, 11, 14)


def test_a_win_is_worth_one_point_between_equals_and_more_as_an_upset():
    # 76 à domicile (+3) contre 80 : écart de -1, la victoire vaut 1,1 et la défaite -0,9.
    assert exchange(76, 80, 20, 10) == pytest.approx(1.1)
    assert exchange(76, 80, 10, 20) == pytest.approx(-0.9)
    assert exchange(76, 80, 15, 15) == pytest.approx(0.1)
    # Sur terrain neutre, entre égaux : un point.
    assert exchange(80, 80, 20, 10, neutral=True) == pytest.approx(1.0)
    # L'écart est borné à dix points : une victoire attendue ne rapporte rien de plus.
    assert exchange(95, 50, 40, 0) == 0
    assert exchange(50, 95, 20, 10) == pytest.approx(2.0)


def test_big_wins_and_world_cup_matches_weigh_more():
    assert exchange(80, 80, 40, 10, neutral=True) == pytest.approx(1.5)
    assert exchange(80, 80, 20, 10, neutral=True, world_cup=True) == pytest.approx(2.0)
    assert exchange(80, 80, 40, 10, neutral=True, world_cup=True) == pytest.approx(3.0)


def test_points_change_hands_and_the_table_shows_the_last_moves():
    initial = {"AAA": 90.0, "BBB": 89.5, "CCC": 60.0}
    tests = [
        Test(DAY, "CCC", "AAA", 10, 40),  # victoire attendue : rien ne bouge
        Test(DAY + datetime.timedelta(days=7), "BBB", "AAA", 25, 20),
    ]
    table, moves = standings(initial, tests)
    assert [s.code for s in table] == ["BBB", "AAA", "CCC"]
    bbb, aaa, _ = table
    assert bbb.rank == 1 and bbb.previous_rank == 2
    assert aaa.rank == 2 and aaa.previous_rank == 1
    # Ce que l'un gagne, l'autre le perd : le total ne bouge pas.
    assert sum(s.points for s in table) == pytest.approx(sum(initial.values()))
    assert [move.change for move in moves][0] == 0
    assert bbb.points - bbb.previous_points == pytest.approx(moves[-1].change)


def test_without_tests_the_table_is_the_starting_one():
    table, moves = standings({"AAA": 80.0, "BBB": 85.0}, [])
    assert [(s.code, s.rank, s.previous_rank) for s in table] == [("BBB", 1, 1), ("AAA", 2, 2)]
    assert moves == []
