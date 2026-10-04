"""Cohésion : à quel point le XV a l'habitude de jouer ensemble.

Elle se construit en alignant souvent les mêmes titulaires et se défait quand
le XV change (blessures, recrues, départs de l'intersaison). Elle court sur
toute la carrière, sans remise à zéro entre les saisons.

Après chaque match, la cohésion se rapproche d'une cible qui dépend de la
continuité : la part des titulaires qui avaient déjà commencé le match précédent.
"""

from collections.abc import Iterable

from engine.notes import Boost, Boosts, Note, club_matches, lineup_of, toward
from models.domain import Match

START = 10.0
# Cible quand aucun titulaire n'est reconduit, et quand tous le sont.
TARGET_NO_CONTINUITY, TARGET_FULL_CONTINUITY = 4.0, 20.0
# Part de l'écart à la cible comblée à chaque match : la cohésion se gagne lentement.
RATE = 0.12


def continuity(lineup: list[int], previous: list[int]) -> float:
    """Part des titulaires de `lineup` qui étaient déjà titulaires dans `previous`."""
    return len(set(lineup) & set(previous)) / len(lineup)


def team_cohesion(club_id: int, matches: list[Match], boosts: Iterable[Boost] = ()) -> Note:
    """Cohésion d'un club après tous ses matchs (`matches` dans l'ordre chronologique).

    `boosts` : décisions du manager (engine/affairs.py).
    """
    cohesion = Note(START)
    pending = Boosts(boosts)
    previous: list[int] = []
    for match in club_matches(club_id, matches):
        cohesion.nudge(pending.before(match.date))
        lineup = lineup_of(match, club_id)
        if not lineup:
            continue
        if previous:
            share = continuity(lineup, previous)
            target = TARGET_NO_CONTINUITY + (TARGET_FULL_CONTINUITY - TARGET_NO_CONTINUITY) * share
            cohesion.step(match, toward(cohesion.value, target, RATE))
        else:
            cohesion.step(match, cohesion.value)  # premier match connu : rien à comparer
        previous = lineup
    cohesion.nudge(pending.rest())
    return cohesion
