"""Forme du jour : moral, cohésion et fraîcheur pèsent sur le match.

Les notes collectives d'un XV (conquête, paquet, attaque, défense) sont
multipliées par un facteur de forme, neutre (1,0) aux notes de référence :
- un point de moral au-dessus de 12 vaut +0,6 % ;
- un point de cohésion au-dessus de 16 vaut +0,4 % ;
- un point de fraîcheur moyenne du XV au-dessus de 16 vaut +0,8 %.
Entre un club euphorique, soudé et frais et un club au plus bas, éclaté et
épuisé, l'écart dépasse 20 %.

La fraîcheur pèse aussi sur les blessures : un joueur à 8 se blesse deux fois
plus qu'un joueur à 16, un joueur à 20 deux fois moins.
"""

from dataclasses import dataclass, field

from models import Player

MORALE_REF, COHESION_REF, FRESHNESS_REF = 12.0, 16.0, 16.0
MORALE_WEIGHT = 0.006
COHESION_WEIGHT = 0.004
FRESHNESS_WEIGHT = 0.008

# Risque de blessure : +1/8 par point de fraîcheur sous la référence, au moins la moitié.
INJURY_PER_POINT = 1 / 8
INJURY_MIN_WEIGHT = 0.5


@dataclass(frozen=True)
class Form:
    """État d'un club avant un match. Un joueur absent de `freshness` est à la référence."""

    morale: float = MORALE_REF
    cohesion: float = COHESION_REF
    freshness: dict[int, float] = field(default_factory=dict)

    def player_freshness(self, player_id: int) -> float:
        return self.freshness.get(player_id, FRESHNESS_REF)

    def lineup_freshness(self, lineup: list[int]) -> float:
        if not lineup:
            return FRESHNESS_REF
        return sum(self.player_freshness(p) for p in lineup) / len(lineup)

    def effects(self, lineup: list[int]) -> dict[str, float]:
        """Part de chaque note dans le facteur de forme (0,03 = +3 %)."""
        return {
            "morale": MORALE_WEIGHT * (self.morale - MORALE_REF),
            "cohesion": COHESION_WEIGHT * (self.cohesion - COHESION_REF),
            "freshness": FRESHNESS_WEIGHT * (self.lineup_freshness(lineup) - FRESHNESS_REF),
        }

    def factor(self, lineup: list[int]) -> float:
        return 1 + sum(self.effects(lineup).values())

    def injury_weight(self, player: Player) -> float:
        """Multiplicateur du risque de blessure d'un joueur selon sa fraîcheur."""
        gap = FRESHNESS_REF - self.player_freshness(player.id)
        return max(INJURY_MIN_WEIGHT, 1 + INJURY_PER_POINT * gap)


NEUTRAL_FORM = Form()
