"""Les recruteurs : ce que le club sait vraiment des joueurs des autres.

Un joueur qu'aucun recruteur n'a supervisé ne se voit que de loin : chacun de ses
attributs est estimé, à deux points près (`estimate`). L'erreur est propre au joueur
et à l'attribut : la même d'un affichage à l'autre, si bien que tout ce qui s'en
déduit (note générale, valeur, comparaisons) reste cohérent, mais faux.

Superviser un joueur coûte `REPORT_COST` et prend jusqu'à la journée suivante ; le
rapport révèle alors ses vrais attributs, et le club estime son potentiel comme
celui de ses propres joueurs (engine/development.py).
"""

import random
from dataclasses import replace

from models import ATTRIBUTE_MAX, ATTRIBUTE_MIN, ATTRIBUTE_NAMES, Player

REPORT_COST = 15_000
# L'erreur d'un attribut estimé, tirée une fois pour toutes : de -2 à +2, souvent nulle.
ERRORS = (-2, -1, -1, 0, 0, 0, 1, 1, 2)


def estimate(player: Player) -> Player:
    """Le joueur tel que le club le voit sans rapport : ses attributs estimés."""
    errors = {
        name: random.Random(f"scout:{player.id}:{name}").choice(ERRORS) for name in ATTRIBUTE_NAMES
    }
    seen = {
        name: max(ATTRIBUTE_MIN, min(ATTRIBUTE_MAX, getattr(player, name) + errors[name]))
        for name in ATTRIBUTE_NAMES
    }
    return replace(player, **seen)
