"""Moral de l'effectif : une note sur 20 qui suit les résultats.

Chaque saison repart d'un moral neutre. Après chaque match :
- le moral revient d'abord un peu vers la note neutre (les séries s'usent) ;
- puis le résultat le fait monter ou baisser, plus fort quand l'écart est net
  et en phases finales.
"""

from collections.abc import Iterable

from engine.notes import STAGE_WEIGHT, Boost, Boosts, Note, club_matches, scores, toward
from models.domain import Match, Stage

NEUTRAL = 12.0
# Part de l'écart à la note neutre effacée avant chaque match.
REVERSION = 0.25

WIN, DRAW, LOSS = 1.3, 0.0, -1.5
# Écart de points à partir duquel une victoire est large ou une défaite lourde.
CLEAR_MARGIN = 15
CLEAR_BONUS = 0.8
# Défaite de 7 points ou moins (bonus défensif) : on y croyait.
CLOSE_LOSS_MARGIN = 7
CLOSE_LOSS_RELIEF = 0.6


def result_change(scored: int, conceded: int, stage: Stage = Stage.REGULAR) -> float:
    """Variation de moral due à un résultat, avant le retour vers la note neutre."""
    margin = scored - conceded
    if margin > 0:
        change = WIN + (CLEAR_BONUS if margin >= CLEAR_MARGIN else 0.0)
    elif margin < 0:
        change = LOSS
        if -margin >= CLEAR_MARGIN:
            change -= CLEAR_BONUS
        elif -margin <= CLOSE_LOSS_MARGIN:
            change += CLOSE_LOSS_RELIEF
    else:
        change = DRAW
    return change * STAGE_WEIGHT[stage]


def team_morale(club_id: int, matches: list[Match], boosts: Iterable[Boost] = ()) -> Note:
    """Moral d'un club après les matchs d'une saison (`matches` dans l'ordre chronologique).

    `boosts` : décisions du manager de la saison (engine/affairs.py).
    """
    morale = Note(NEUTRAL)
    pending = Boosts(boosts)
    for match in club_matches(club_id, matches):
        morale.nudge(pending.before(match.date))
        scored, conceded = scores(match, club_id)
        reverted = toward(morale.value, NEUTRAL, REVERSION)
        morale.step(match, reverted + result_change(scored, conceded, match.stage))
    morale.nudge(pending.rest())
    return morale
