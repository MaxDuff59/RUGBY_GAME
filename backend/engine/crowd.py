"""Le public d'un match : combien ils sont, et combien ils poussent.

L'ambiance d'un match à domicile (de 0 à 1) tient à trois choses :
- le remplissage du stade : une enceinte à moitié vide ne fait pas peur ;
- la ferveur des supporters (engine/supporters.py), qui suit les résultats ;
- la tradition du stade (`STADIUM_TRADITION`, data/leagues.py) : à Aimé-Giral,
  Marcel-Michelin ou Thomond Park, le public pousse plus fort qu'ailleurs.

Elle fait l'avantage du terrain (engine/match_engine.py) : le territoire de
l'équipe qui reçoit est multiplié de 1,05 (stade clairsemé et froid) à 1,33
(chaudron plein) au coup d'envoi, autour de 1,25 en moyenne sur le match, l'élan
du public compris ; et les sifflets font manquer des
coups de pied au but au buteur adverse. Sur terrain neutre, pas de public à soi.

Pendant le match, le public réagit au score (`Roar`) : un essai de son équipe
enflamme le stade, une pénalité ou un drop le réveille, un essai encaissé le
refroidit ; l'élan retombe au fil des minutes. Mené de loin, il se tait ; dans
les dix dernières minutes d'un match serré, il pousse plus fort. Un chaudron
s'enflamme plus qu'un stade tiède. L'avantage du terrain et les sifflets suivent
l'ambiance du moment.
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
ADVANTAGE_MIN, ADVANTAGE_SPAN = 1.05, 0.28
# Sifflets : réussite des coups de pied au but de l'adversaire, en points de pourcentage.
HOSTILE_KICKING = 0.06

# Réaction au score : élan donné par chaque fait de jeu de l'équipe qui reçoit (ou
# repris par un essai adverse), multiplié par (0,5 + ambiance) ; il retombe chaque minute.
ROAR_TRY, ROAR_KICK, ROAR_CONCEDED = 0.15, 0.05, -0.08
ROAR_FADE = 0.92
ROAR_LIMIT = 0.3
# Le score pèse aussi : mené de 15 points et plus, le public se tait ; de 8 à 14,
# il s'éteint un peu ; dans les dix dernières minutes à 7 points ou moins, il pousse.
SILENCE_MARGIN, SILENCE = 15, -0.25
SUBDUED_MARGIN, SUBDUED = 8, -0.1
TENSION_MINUTE, TENSION_MARGIN, TENSION = 70, 7, 0.1

# Ce que fait le stade, en mots (au-delà de ces seuils d'élan ou de score).
ROARING = 0.06

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
        """Multiplicateur du territoire de l'équipe qui reçoit, avant le coup d'envoi."""
        return advantage(self.atmosphere)

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


def advantage(value: float) -> float:
    """Multiplicateur du territoire de l'équipe qui reçoit, pour cette ambiance."""
    return ADVANTAGE_MIN + ADVANTAGE_SPAN * value


def hostility(value: float) -> float:
    """Réussite perdue par le buteur adverse sous les sifflets, pour cette ambiance."""
    return HOSTILE_KICKING * value


class Mood:
    """Ce que fait le stade à un moment du match."""

    ROARING = "roaring"  # il s'enflamme
    TENSE = "tense"  # il pousse, le match est serré et touche à sa fin
    SUBDUED = "subdued"  # il s'éteint
    SILENT = "silent"  # il se tait, son équipe est menée de loin


def score_effect(margin: int, minute: int) -> float:
    """Ce que le score fait à l'ambiance ; `margin` : points d'avance de l'équipe qui reçoit."""
    if margin <= -SILENCE_MARGIN:
        return SILENCE
    if margin <= -SUBDUED_MARGIN:
        return SUBDUED
    if minute >= TENSION_MINUTE and abs(margin) <= TENSION_MARGIN:
        return TENSION
    return 0.0


def roar_after(roar: float, base: float, scored: list[str], conceded_tries: int) -> float:
    """L'élan du public après une minute : il retombe, puis réagit aux faits de jeu
    (`scored` : « try » ou « kick » pour l'équipe qui reçoit, dans l'ordre)."""
    gain = sum(ROAR_TRY if kind == "try" else ROAR_KICK for kind in scored)
    gain += ROAR_CONCEDED * conceded_tries
    value = roar * ROAR_FADE + gain * (0.5 + base)
    return min(max(value, -ROAR_LIMIT), ROAR_LIMIT)


def live_atmosphere(base: float, roar: float, margin: int, minute: int) -> float:
    """L'ambiance du moment : celle du coup d'envoi, l'élan du public, le score."""
    return min(max(base + roar + score_effect(margin, minute), 0.0), 1.0)


def mood(roar: float, margin: int, minute: int) -> str | None:
    """Ce que fait le stade, en un mot (None : rien de particulier)."""
    effect = score_effect(margin, minute)
    if effect == SILENCE:
        return Mood.SILENT
    if roar >= ROARING:
        return Mood.ROARING
    if effect == TENSION:
        return Mood.TENSE
    if effect == SUBDUED or roar <= -ROARING:
        return Mood.SUBDUED
    return None


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
