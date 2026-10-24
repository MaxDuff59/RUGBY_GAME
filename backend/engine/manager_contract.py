"""Le contrat du manager : sa durée, les prolongations, et ce que coûte un départ.

Un manager signe pour deux saisons dans son premier club ; un club qui le recrute
lui en offre deux, trois s'il a déjà un nom. Le contrat court jusqu'à la fin de sa
dernière saison (`until`, l'année où elle commence, comme pour les joueurs).

Une prolongation se demande à la direction : elle accepte, propose moins, ou
refuse selon son appui, la confiance de la direction (sur 20) corrigée de
l'humeur des supporters et de la difficulté de la carrière. Après un refus, il
faut attendre quelques semaines pour revenir à la charge ; en fin de contrat, la
direction dit d'elle-même si elle veut le garder.

Un club qui recrute un manager encore sous contrat verse une indemnité à son
ancien club, par saison restante. Partir de soi-même avant la fin de son contrat
coûte de la réputation (engine/career.py) ; le laisser s'achever, non.
"""

import datetime
from dataclasses import dataclass

from engine import supporters

FIRST_CONTRACT = 2  # saisons, dans le club où l'on commence (ou rebondit)
OFFER_LENGTH, STAR_OFFER_LENGTH, STAR_REPUTATION = 2, 3, 60.0
MAX_SEASONS = 4  # saisons à jouer sous contrat au plus, prolongation comprise
ASK_MAX = 3  # saisons demandées d'un coup au plus

# Appui de la direction (sur 20) : confiance + part de l'écart des supporters à leur
# note neutre, moins le surcroît d'exigence de la difficulté.
SUPPORTERS_WEIGHT = 0.25
# Saisons de prolongation accordées au plus, selon l'appui.
GRANTS = ((15.0, 3), (12.5, 2), (10.0, 1))
# Matchs que la direction veut voir avant d'entendre parler de prolongation.
ASK_AFTER_MATCHES = 8
REFUSAL_COOLDOWN = datetime.timedelta(weeks=8)

INDEMNITY_PER_SEASON = 250_000


@dataclass(frozen=True)
class Answer:
    outcome: str  # accepted, countered ou refused
    seasons: int  # saisons accordées (accepted) ou proposées (countered)


def support(board: float, fervour: float, demand: float = 0.0) -> float:
    """Appui de la direction ; `demand` : son exigence en plus (difficile) ou en moins."""
    return board + SUPPORTERS_WEIGHT * (fervour - supporters.NEUTRAL) - demand


def remaining(until: int, year: int, finished: bool) -> int:
    """Saisons encore à jouer sous contrat, la saison `year` comprise tant qu'elle dure."""
    return max(0, until - year + (0 if finished else 1))


def grant(value: float, left: int) -> int:
    """Saisons de prolongation que la direction accorde au plus, d'après son appui
    et ce qu'il reste à jouer (`left`)."""
    best = next((seasons for floor, seasons in GRANTS if value >= floor), 0)
    return max(0, min(best, MAX_SEASONS - left))


def answer(asked: int, granted: int) -> Answer:
    if granted == 0:
        return Answer("refused", 0)
    if asked <= granted:
        return Answer("accepted", asked)
    return Answer("countered", granted)


def offer_length(reputation: float) -> int:
    return STAR_OFFER_LENGTH if reputation >= STAR_REPUTATION else OFFER_LENGTH


def indemnity(left: int) -> int:
    """Ce que verse un club pour recruter un manager à qui il reste `left` saisons."""
    return INDEMNITY_PER_SEASON * left
