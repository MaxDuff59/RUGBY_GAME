"""Ferveur des supporters : l'envie du public de suivre le club.

Elle bouge surtout avec les matchs à domicile : une défaite devant son public
déçoit plus qu'une défaite à l'extérieur, une victoire à l'extérieur ravit
moins qu'un succès à la maison. Les écarts nets et les phases finales comptent
plus ; une qualification pour les phases finales enflamme le public.

Les supporters ont la mémoire longue : la ferveur revient lentement vers la note
neutre, court sur toute la carrière, et ne s'efface qu'en partie à l'intersaison.
"""

from collections.abc import Iterable

from engine.notes import STAGE_WEIGHT, Boost, Boosts, Note, club_matches, scores, toward
from models.domain import Match, Stage

NEUTRAL = 10.0
REVERSION = 0.08  # par match
SEASON_RESET = 0.3  # à chaque nouvelle saison

# (victoire, nul, défaite), à domicile puis à l'extérieur.
HOME = (1.1, -0.2, -1.3)
AWAY = (0.7, 0.1, -0.4)
CLEAR_MARGIN = 15
CLEAR_BONUS = 0.5
QUALIFIED = 1.5  # premier match de phases finales de la saison


def result_change(
    scored: int, conceded: int, at_home: bool, stage: Stage = Stage.REGULAR, shootout: int = 0
) -> float:
    """`shootout` : 1 ou -1 si les tirs au but ont départagé un nul de phase finale."""
    win, draw, loss = HOME if at_home else AWAY
    margin = scored - conceded
    outcome = margin or shootout
    change = win if outcome > 0 else loss if outcome < 0 else draw
    if abs(margin) >= CLEAR_MARGIN:
        change += CLEAR_BONUS if margin > 0 else -CLEAR_BONUS
    return change * STAGE_WEIGHT[stage]


def fan_fervour(club_id: int, seasons: list[list[Match]], boosts: Iterable[Boost] = ()) -> Note:
    """Ferveur des supporters d'un club après toutes les saisons (matchs dans l'ordre).

    `boosts` : décisions du manager (engine/affairs.py).
    """
    fervour = Note(NEUTRAL)
    pending = Boosts(boosts)
    for index, matches in enumerate(seasons):
        if index > 0:
            fervour.value = toward(fervour.value, NEUTRAL, SEASON_RESET)
        qualified = False
        for match in club_matches(club_id, matches):
            fervour.nudge(pending.before(match.date))
            scored, conceded = scores(match, club_id)
            # Terrain neutre : personne n'est à domicile.
            at_home = match.home_club_id == club_id and not match.neutral
            value = toward(fervour.value, NEUTRAL, REVERSION)
            value += result_change(
                scored, conceded, at_home, match.stage, match.result_for(club_id)
            )
            if match.stage != Stage.REGULAR and not qualified:
                value += QUALIFIED
                qualified = True
            fervour.step(match, value)
    fervour.nudge(pending.rest())
    return fervour
