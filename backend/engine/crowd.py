"""Le public d'un match : combien ils sont, et combien ils poussent.

L'ambiance d'un match à domicile (de 0 à 1) tient à trois choses :
- le remplissage du stade : une enceinte à moitié vide ne fait pas peur ;
- la ferveur des supporters (engine/supporters.py), qui suit les résultats ;
- la tradition du stade (`STADIUM_TRADITION`, data/leagues.py) : à Aimé-Giral,
  Marcel-Michelin ou Thomond Park, le public pousse plus fort qu'ailleurs.

Elle fait l'avantage du terrain (engine/match_engine.py) : le territoire de
l'équipe qui reçoit est multiplié de 1,06 (stade clairsemé et froid) à 1,34
(chaudron plein), 1,25 en moyenne comme avant ; et les sifflets font manquer des
coups de pied au but au buteur adverse. Sur terrain neutre, pas de public à soi.
"""

import random
from dataclasses import dataclass

from data.leagues import STADIUM_TRADITION
from engine.economy import attendance, attendance_bonus
from engine.supporters import NEUTRAL as FANS_NEUTRAL
from models import Club

DEFAULT_TRADITION = 0.5

# Poids du remplissage, de la ferveur et de la tradition dans l'ambiance.
FILL_SHARE, FERVOUR_SHARE, TRADITION_SHARE = 0.5, 0.25, 0.25
# La ferveur (sur 20) compte de 4 (public las) à 16 (public en feu).
FERVOUR_LOW, FERVOUR_HIGH = 4.0, 16.0

# Avantage du terrain : multiplicateur du territoire de l'équipe qui reçoit.
ADVANTAGE_MIN, ADVANTAGE_SPAN = 1.06, 0.28
# Sifflets : réussite des coups de pied au but de l'adversaire, en points de pourcentage.
HOSTILE_KICKING = 0.06

# Paliers d'ambiance, du plus chaud au plus froid.
LEVELS = ((0.8, "Chaudron"), (0.65, "Bouillant"), (0.5, "Bonne ambiance"), (0.35, "Tiède"))
COLD = "Stade clairsemé"


@dataclass(frozen=True)
class Crowd:
    spectators: int
    capacity: int
    atmosphere: float  # de 0 à 1

    @property
    def advantage(self) -> float:
        """Multiplicateur du territoire de l'équipe qui reçoit."""
        return ADVANTAGE_MIN + ADVANTAGE_SPAN * self.atmosphere

    @property
    def hostility(self) -> float:
        """Réussite perdue par le buteur adverse sous les sifflets."""
        return HOSTILE_KICKING * self.atmosphere

    @property
    def label(self) -> str:
        return label_for(self.atmosphere)

    def to_dict(self) -> dict:
        return {
            "spectators": self.spectators,
            "capacity": self.capacity,
            "atmosphere": self.atmosphere,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Crowd":
        return cls(data["spectators"], data["capacity"], data["atmosphere"])


def label_for(value: float) -> str:
    """L'ambiance en mots : « Chaudron », « Bouillant »... « Stade clairsemé »."""
    return next((label for floor, label in LEVELS if value >= floor), COLD)


def tradition(club: Club) -> float:
    return STADIUM_TRADITION.get(club.name, DEFAULT_TRADITION)


def atmosphere(fill: float, fervour: float, stadium_tradition: float) -> float:
    """Ambiance de 0 à 1 : remplissage (0 à 1), ferveur (sur 20), tradition (0 à 1)."""
    heat = min(max((fervour - FERVOUR_LOW) / (FERVOUR_HIGH - FERVOUR_LOW), 0.0), 1.0)
    value = FILL_SHARE * fill + FERVOUR_SHARE * heat + TRADITION_SHARE * stadium_tradition
    return round(min(max(value, 0.0), 1.0), 3)


def gate(
    home: Club,
    rank: int,
    club_count: int,
    playoff: bool,
    rng: random.Random,
    fervour: float = FANS_NEUTRAL,
) -> Crowd:
    """Le public d'un match que `home` reçoit : l'affluence (engine/economy.py, selon le
    classement, la ferveur et les aménagements), puis l'ambiance qu'elle fait."""
    capacity = home.facilities.stadium_capacity
    spectators = attendance(
        capacity,
        rank,
        club_count,
        playoff,
        rng,
        fervour=fervour,
        bonus=attendance_bonus(home.facilities),
    )
    fill = spectators / capacity if capacity else 0.0
    return Crowd(spectators, capacity, atmosphere(fill, fervour, tradition(home)))
