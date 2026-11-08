"""Le classement mondial des sélections, à la manière de World Rugby.

Chaque nation a des points (autour de 50 à 95) ; un test en fait passer de l'une à
l'autre, comme un classement Elo : ce que gagne l'une, l'autre le perd. L'échange
dépend de l'écart entre les deux nations avant le match, celle qui reçoit comptant
HOME_ADVANTAGE points de plus (rien sur terrain neutre), l'écart borné à MAX_GAP :

- victoire : 1 - écart / 10 (une victoire attendue rapporte peu, un exploit jusqu'à 2) ;
- nul : - écart / 10 (le favori y perd) ;
- défaite : la victoire de l'autre.

Un écart au score de plus de BIG_WIN points multiplie l'échange par BIG_WIN_FACTOR,
un match de Coupe du monde par WORLD_CUP_FACTOR. Les points de départ de chaque nation
sont dans data/nations.py ; le classement d'une partie se refait à partir de tous ses
tests joués, dans l'ordre (api/internationals.py, `world_ranking`). Aucune dépendance à
FastAPI ni à la base.
"""

import datetime
from collections.abc import Iterable, Mapping
from dataclasses import dataclass

HOME_ADVANTAGE = 3.0
MAX_GAP = 10.0
BIG_WIN = 15
BIG_WIN_FACTOR = 1.5
WORLD_CUP_FACTOR = 2.0


@dataclass(frozen=True)
class Test:
    """Un test joué, vu du classement : les nations par leur code."""

    date: datetime.date
    home: str
    away: str
    home_score: int
    away_score: int
    neutral: bool = False
    world_cup: bool = False
    competition: str = ""  # code de la fenêtre, pour l'afficher


def exchange(
    home_points: float,
    away_points: float,
    home_score: int,
    away_score: int,
    neutral: bool = False,
    world_cup: bool = False,
) -> float:
    """Les points que gagne l'équipe qui reçoit (l'autre perd autant)."""
    gap = home_points - away_points + (0.0 if neutral else HOME_ADVANTAGE)
    gap = max(-MAX_GAP, min(MAX_GAP, gap)) / MAX_GAP
    if home_score > away_score:
        core = 1 - gap
    elif home_score < away_score:
        core = -(1 + gap)
    else:
        core = -gap
    if abs(home_score - away_score) > BIG_WIN:
        core *= BIG_WIN_FACTOR
    if world_cup:
        core *= WORLD_CUP_FACTOR
    return core


@dataclass(frozen=True)
class Move:
    """Ce qu'un test a fait au classement."""

    test: Test
    change: float  # gagné par l'équipe qui reçoit, perdu par l'autre


def replay(
    initial: Mapping[str, float], tests: Iterable[Test]
) -> tuple[dict[str, float], list[Move]]:
    """Les points de chaque nation après `tests` (dans l'ordre où ils se sont joués), et
    ce que chacun a échangé. Une nation inconnue de `initial` part de 50."""
    points = dict(initial)
    moves = []
    for test in tests:
        home, away = points.get(test.home, 50.0), points.get(test.away, 50.0)
        change = exchange(
            home, away, test.home_score, test.away_score, test.neutral, test.world_cup
        )
        points[test.home] = home + change
        points[test.away] = away - change
        moves.append(Move(test, change))
    return points, moves


def order(points: Mapping[str, float], tie_break: Iterable[str] = ()) -> list[str]:
    """Les nations de la première à la dernière ; à égalité, l'ordre de `tie_break`."""
    rank_of = {code: index for index, code in enumerate(tie_break)}
    return sorted(points, key=lambda code: (-round(points[code], 2), rank_of.get(code, 0), code))


@dataclass(frozen=True)
class Standing:
    code: str
    rank: int
    points: float
    # Avant la dernière journée de tests : son rang et ses points (None : pas de journée).
    previous_rank: int
    previous_points: float


def standings(
    initial: Mapping[str, float], tests: Iterable[Test]
) -> tuple[list[Standing], list[Move]]:
    """Le classement après `tests`, avec le mouvement de chaque nation depuis la veille
    de la dernière journée de tests (comme le classement que World Rugby publie chaque
    semaine), et tous les échanges dans l'ordre."""
    tests = sorted(tests, key=lambda test: test.date)
    last = tests[-1].date if tests else None
    before, _ = replay(initial, [t for t in tests if t.date != last])
    now, moves = replay(initial, tests)
    tie_break = list(initial)
    previous = {code: rank for rank, code in enumerate(order(before, tie_break), start=1)}
    return [
        Standing(
            code=code,
            rank=rank,
            points=round(now[code], 2),
            previous_rank=previous[code],
            previous_points=round(before[code], 2),
        )
        for rank, code in enumerate(order(now, tie_break), start=1)
    ], moves
