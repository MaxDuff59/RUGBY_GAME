"""Fraîcheur : l'état physique du XV avant un match.

Chaque joueur a sa fraîcheur sur 20. Un match comme titulaire la fait baisser ;
chaque jour sans match en rattrape une part de l'écart à 20. Un titulaire qui
enchaîne toutes les semaines se stabilise autour de 13 (16 avec un excellent
préparateur physique) ; les trêves le remettent à neuf.

La fraîcheur du club est la moyenne de son XV : celui de chaque match pour
l'historique, le XV probable du prochain match pour la note actuelle.
"""

import datetime
from collections.abc import Iterable

from engine.notes import Boost, Note, club_matches, lineup_of
from models.domain import Match

FULL = 20.0
MATCH_COST = 9.0
# Part de l'écart à 20 rattrapée chaque jour, plus un bonus par étoile du préparateur physique.
BASE_RECOVERY = 0.11
RECOVERY_PER_FITNESS_LEVEL = 0.01


def daily_recovery(fitness_level: int) -> float:
    return BASE_RECOVERY + RECOVERY_PER_FITNESS_LEVEL * fitness_level


def recover(value: float, days: int, rate: float) -> float:
    return FULL - (FULL - value) * (1 - rate) ** days


def player_freshness(
    appearances: list[datetime.date],
    day: datetime.date,
    rate: float,
    boosts: Iterable[Boost] = (),
) -> float:
    """Fraîcheur d'un joueur le jour `day`, avant un éventuel match ce jour-là.

    `boosts` : repos ou charge en plus décidés par le manager (engine/affairs.py),
    appliqués après les matchs du même jour et récupérés ensuite comme le reste.
    """
    # (date, 0 = match / 1 = coup de pouce, variation) : le match d'un jour passe d'abord.
    timeline = sorted(
        [(played_on, 0, -MATCH_COST) for played_on in appearances]
        + [(boost.day, 1, boost.delta) for boost in boosts]
    )
    value, last = FULL, None
    for when, _, delta in timeline:
        if when >= day:
            break
        if last is not None:
            value = recover(value, (when - last).days, rate)
        value = min(FULL, max(0.0, value + delta))
        last = when
    if last is not None:
        value = recover(value, (day - last).days, rate)
    return value


def appearances_by_player(matches: list[Match]) -> dict[int, list[datetime.date]]:
    """Dates des matchs commencés par chaque joueur, tous clubs confondus."""
    dates: dict[int, list[datetime.date]] = {}
    for match in matches:
        if match.is_played and match.date is not None:
            for player_id in (*match.home_lineup, *match.away_lineup):
                dates.setdefault(player_id, []).append(match.date)
    return dates


def squad_freshness(
    appearances: dict[int, list[datetime.date]],
    player_ids: list[int],
    day: datetime.date,
    fitness_level: int = 0,
    boosts: Iterable[Boost] = (),
) -> dict[int, float]:
    """Fraîcheur de chaque joueur le jour `day`, avant le match (`boosts` : pour tous)."""
    rate = daily_recovery(fitness_level)
    boosts = list(boosts)
    return {p: player_freshness(appearances.get(p, []), day, rate, boosts) for p in player_ids}


def team_freshness(
    club_id: int,
    matches: list[Match],
    lineup_now: list[int],
    day: datetime.date,
    fitness_level: int = 0,
    appearances: dict[int, list[datetime.date]] | None = None,
    boosts: Iterable[Boost] = (),
) -> Note:
    """Fraîcheur du XV avant chacun des matchs du club, puis du XV probable au jour `day`.

    `matches` : tous les matchs joués (tous clubs, pour les joueurs arrivés en
    cours de route), dans l'ordre chronologique. `appearances` : leur index par
    joueur, s'il est déjà calculé. `boosts` : décisions du manager, pour tout le XV.
    """
    boosts = list(boosts)
    rate = daily_recovery(fitness_level)
    if appearances is None:
        appearances = appearances_by_player(matches)

    def average(lineup: list[int], on: datetime.date) -> float:
        if not lineup:
            return FULL
        total = sum(player_freshness(appearances.get(p, []), on, rate, boosts) for p in lineup)
        return total / len(lineup)

    freshness = Note(FULL)
    for match in club_matches(club_id, matches):
        lineup = lineup_of(match, club_id)
        if lineup and match.date is not None:
            freshness.step(match, average(lineup, match.date))
    freshness.value = average(lineup_now, day)
    return freshness
