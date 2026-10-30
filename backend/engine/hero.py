"""Carrière de joueur : le joueur que l'on crée, et comment il progresse.

Il démarre à 18 ans, bien en dessous du niveau d'un pro (`START_LEVEL`), avec le
profil de son poste. Il ne progresse pas tout seul comme les autres joueurs
(engine/development.py) : il gagne de l'expérience à chaque journée de son club, en
s'entraînant (`TRAINING_XP`) et surtout en jouant, d'autant plus qu'il joue longtemps
et bien (`match_xp`). Chaque tranche de `XP_PER_POINT` lui donne un point à placer
dans l'attribut de son choix ; un attribut coûte d'autant plus cher qu'il est haut
(`cost`).

Deux jauges suivent ses matchs. Sa confiance (`next_confidence`, de -1 à 1) monte avec
les bonnes notes et retombe avec les mauvaises (et les critiques qui vont avec) : elle
pèse sur ses chances en match (engine/dilemmas.py). La confiance de l'entraîneur
(`next_trust`, sur 100) décide de son temps de jeu : titulaire au-delà de
`TRUST_START`, remplaçant qui entre plus tard quand elle baisse (`entry_minute`) ; un
carton ou trop de prises de risque ratées la font chuter.

Blessé, il peut jouer diminué : ses attributs ne rendent pas tout, et la blessure
risque de s'aggraver (`AGGRAVATION_CHANCE`, de 1 à 3 semaines de plus).
"""

from models import ATTRIBUTE_MAX, ATTRIBUTE_MIN, ATTRIBUTE_NAMES, POSITION_PROFILES, Position

START_AGE = 18
START_LEVEL = 6.5  # base des attributs, avant le profil du poste
START_POINTS = 5  # à répartir dès la signature
START_CONTRACT_YEARS = 2  # le club le garde sous contrat au moins ce nombre de saisons

XP_PER_POINT = 40
TRAINING_XP = 8  # chaque journée où son club joue, qu'il joue ou non
FULL_MATCH_XP = 20  # 80 minutes jouées
XP_PER_RATING_POINT = 12  # par point de note au-dessus de RATING_NEUTRAL
RATING_NEUTRAL = 6.0
MINUTES_FULL = 80

# Confiance du joueur : ce qu'il garde de la précédente, ce que pèse un point de note
# autour de 6, et le poids des critiques (note sous CRITICS_BELOW) ; sans jouer, elle
# revient doucement vers 0.
CONFIDENCE_KEEP = 0.7
CONFIDENCE_PER_POINT = 0.25
CONFIDENCE_CRITICS = 0.1
CRITICS_BELOW = 5.0
CONFIDENCE_IDLE = 0.9

# Confiance de l'entraîneur, sur 100 : au départ, par point de note autour de 6, à
# chaque semaine d'entraînement, pour un carton, pour des prises de risque ratées.
TRUST_START_VALUE = 40.0
TRUST_PER_POINT = 6.0
TRUST_PER_WEEK = 1.0
TRUST_CARD = -12.0
TRUST_RISKS = -6.0
RISKY_FAILURES = 2  # prises de risque ratées dans un match qui fâchent l'entraîneur
PRAISE_FROM = 7.5  # note qui vaut des félicitations
# Au-delà, il est titulaire ; sinon il entre d'autant plus tard qu'elle est basse.
TRUST_START = 70.0
ENTRY_BY_TRUST = ((50.0, 52), (30.0, 60), (0.0, 68))

# Jouer blessé : risque d'aggraver la blessure, de 1 à 3 semaines.
AGGRAVATION_CHANCE = 0.4
AGGRAVATION_WEEKS = (1, 3)

# Prix d'un point d'attribut selon sa valeur actuelle : (jusqu'à, coût).
COSTS = ((9, 1), (13, 2), (16, 3), (ATTRIBUTE_MAX, 4))


def start_attributes(position: Position) -> dict[str, int]:
    """Les attributs d'un débutant : la base, plus le profil de son poste."""
    profile = POSITION_PROFILES[position]
    return {
        name: max(ATTRIBUTE_MIN, min(ATTRIBUTE_MAX, round(START_LEVEL + profile[name])))
        for name in ATTRIBUTE_NAMES
    }


def cost(value: int) -> int | None:
    """Points pour passer un attribut de `value` à `value + 1` (None : déjà au maximum)."""
    if value >= ATTRIBUTE_MAX:
        return None
    return next(price for ceiling, price in COSTS if value < ceiling or ceiling == ATTRIBUTE_MAX)


def match_xp(minutes: int, rating: float | None) -> int:
    """L'expérience d'un match joué : le temps de jeu, et la note au-dessus de 6."""
    if minutes <= 0:
        return 0
    played = FULL_MATCH_XP * min(minutes, MINUTES_FULL) / MINUTES_FULL
    bonus = XP_PER_RATING_POINT * max(0.0, (rating or RATING_NEUTRAL) - RATING_NEUTRAL)
    return round(played + bonus)


def clamp(value: float, low: float, high: float) -> float:
    return min(high, max(low, value))


def next_confidence(confidence: float, rating: float | None) -> float:
    """La confiance après une journée : son match (`rating`), ou rien s'il n'a pas joué."""
    if rating is None:
        return round(confidence * CONFIDENCE_IDLE, 3)
    change = CONFIDENCE_PER_POINT * (rating - RATING_NEUTRAL)
    if rating < CRITICS_BELOW:
        change -= CONFIDENCE_CRITICS
    return round(clamp(confidence * CONFIDENCE_KEEP + change, -1.0, 1.0), 3)


def next_trust(trust: float, rating: float | None, carded: bool, risky_failures: int) -> float:
    """La confiance de l'entraîneur après une journée."""
    value = trust + TRUST_PER_WEEK
    if rating is not None:
        value += TRUST_PER_POINT * (rating - RATING_NEUTRAL)
    if carded:
        value += TRUST_CARD
    if risky_failures >= RISKY_FAILURES:
        value += TRUST_RISKS
    return round(clamp(value, 0.0, 100.0), 1)


def entry_minute(trust: float) -> int:
    """La minute où l'entraîneur fait entrer le joueur resté sur le banc."""
    return next(minute for floor, minute in ENTRY_BY_TRUST if trust >= floor)
