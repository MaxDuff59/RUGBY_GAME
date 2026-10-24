"""La carrière du manager : sa réputation, et les clubs qui le veulent.

La réputation (de 0 à 100) se bâtit saison après saison, quel que soit le club :
un titre la fait grimper, une qualification pour les phases finales et un
classement meilleur qu'attendu l'entretiennent, un limogeage la ruine. Un manager
qui débute part de 30.

À la fin de la saison de son championnat, les clubs plus prestigieux que le sien
peuvent lui faire une offre, à la mesure de sa réputation : plus elle est haute,
plus les clubs qui l'appellent sont grands. Le prestige d'un club tient au niveau
de son XV et au rang de son championnat. Rien n'est tiré au hasard d'un appel à
l'autre : la même fin de saison donne les mêmes offres.
"""

import random
from dataclasses import dataclass

START, FLOOR, CEILING = 30.0, 0.0, 100.0
PER_SEASON, SEASONS_CAP = 4.0, 20.0
PER_TITLE = 12.0
PER_PLAYOFF = 3.0
PER_PLACE, PLACES_CAP = 2.0, 5  # places gagnées (ou perdues) sur le rang attendu
PER_DISMISSAL = -15.0

# Prestige d'un championnat, ajouté au niveau du XV (sur 20) de ses clubs.
LEAGUE_PRESTIGE = {"top14": 1.0, "premiership": 0.8, "urc": 0.6, "super_rugby": 0.5}
LOWER_LEAGUE = -1.5  # la Pro D2, et tout championnat inconnu
# Jusqu'où porte la réputation : 35 n'attire personne de plus grand, chaque tranche
# de 12 points ouvre les portes de clubs d'un point de prestige au-dessus.
REACH_FROM, REACH_PER_POINT = 35.0, 12.0
OFFER_CHANCE = 0.5
MAX_OFFERS = 3

LEVELS = (
    (80, "Star du banc"),
    (60, "Manager reconnu"),
    (40, "Manager confirmé"),
    (20, "Espoir du banc"),
)
UNKNOWN = "Inconnu"


@dataclass(frozen=True)
class Season:
    """Une saison du manager, dans le club qu'il dirigeait."""

    year: int
    club_id: int
    champion: bool
    playoffs: bool
    rank: int | None
    expected: int | None


def reputation(seasons: list[Season], dismissals: int) -> float:
    places = sum(
        max(-PLACES_CAP, min(PLACES_CAP, s.expected - s.rank))
        for s in seasons
        if s.rank is not None and s.expected is not None
    )
    value = (
        START
        + min(PER_SEASON * len(seasons), SEASONS_CAP)
        + PER_TITLE * sum(s.champion for s in seasons)
        + PER_PLAYOFF * sum(s.playoffs for s in seasons)
        + PER_PLACE * places
        + PER_DISMISSAL * dismissals
    )
    return round(min(max(value, FLOOR), CEILING), 1)


def label(value: float) -> str:
    return next((name for floor, name in LEVELS if value >= floor), UNKNOWN)


def prestige(level: float, league: str) -> float:
    return level + LEAGUE_PRESTIGE.get(league, LOWER_LEAGUE)


def reach(value: float) -> float:
    """Combien de points de prestige au-dessus de son club un manager peut viser."""
    return max(0.0, (value - REACH_FROM) / REACH_PER_POINT)


def offers(
    mine: float, candidates: dict[int, float], value: float, rng: random.Random
) -> list[int]:
    """Les clubs (identifiants) qui font une offre, du plus prestigieux au moins :
    `mine` est le prestige du club dirigé, `candidates` celui des autres."""
    ceiling = mine + reach(value)
    within = sorted(
        (cid for cid, p in candidates.items() if mine < p <= ceiling),
        key=lambda cid: (-candidates[cid], cid),
    )
    return [cid for cid in within if rng.random() < OFFER_CHANCE][:MAX_OFFERS]
