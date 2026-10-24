"""Le niveau de difficulté de la carrière, choisi au départ.

Il ne touche jamais aux matchs, seulement à ce qui entoure le manager :
- la patience de la direction : le seuil de confiance sous lequel elle limoge ;
- les recettes de son club (billetterie, buvettes, boutique, loges, sponsors) ;
- l'exigence des clubs et des joueurs qu'il veut recruter (indemnités, salaires).
"""

from dataclasses import dataclass
from enum import StrEnum

from engine.board import SACK_THRESHOLD


class Difficulty(StrEnum):
    EASY = "easy"
    NORMAL = "normal"
    HARD = "hard"


@dataclass(frozen=True)
class Rules:
    sack_threshold: float  # confiance (sur 20) sous laquelle la direction limoge
    revenue: float  # multiplicateur des recettes du club dirigé
    demands: float  # multiplicateur des indemnités et salaires demandés au recrutement


RULES = {
    Difficulty.EASY: Rules(sack_threshold=SACK_THRESHOLD - 1.5, revenue=1.2, demands=0.9),
    Difficulty.NORMAL: Rules(sack_threshold=SACK_THRESHOLD, revenue=1.0, demands=1.0),
    Difficulty.HARD: Rules(sack_threshold=SACK_THRESHOLD + 1.5, revenue=0.85, demands=1.12),
}


def rules(difficulty: str | None) -> Rules:
    """Les règles d'un niveau (normal par défaut, et pour une carrière d'avant les niveaux)."""
    return RULES[Difficulty(difficulty or Difficulty.NORMAL)]
