"""Progression des joueurs : un potentiel caché, et des progrès au fil de la saison.

Chaque joueur a un potentiel : le niveau (sa note générale moins un écart fixe, voir
models/domain.py) qu'il peut espérer atteindre. Il est tiré une fois, d'après son âge
à ce moment-là : un espoir de 17 ans peut avoir quatre ou cinq points devant lui, un
joueur de 28 ans est à peu près arrivé. Il reste caché : l'interface n'en montre qu'une
estimation, d'autant plus juste que le club connaît le joueur (voir `estimate`).

La progression se fait match après match (`develop`, à chaque jour où l'équipe
du joueur joue) : il comble chaque saison une part de l'écart qui le sépare de son
potentiel, d'autant plus vite qu'il est jeune, qu'il joue, qu'il joue bien, et que
son club s'entraîne dans de bonnes installations. Les points gagnés s'accumulent
(`Player.progress`) et deviennent, un à un, des points d'attributs, de préférence
dans ceux qui comptent à son poste. Le déclin des plus âgés, lui, se fait à
l'intersaison (engine/offseason.py).
"""

import random
from collections.abc import Iterable
from dataclasses import dataclass

from models import (
    ATTRIBUTE_MAX,
    ATTRIBUTE_NAMES,
    BEST_LEVEL,
    OVERALL_WEIGHTS,
    Club,
    Player,
    PlayerMatchStats,
    Position,
)

POTENTIAL_MAX = 19.5

# Marge de progression (en points de niveau) selon l'âge : (âge maximal, moyenne,
# écart-type) ; au-delà du dernier âge, le joueur est arrivé.
UPSIDE_BY_AGE = ((18, 5.5, 1.8), (20, 4.5, 1.5), (22, 3.0, 1.2), (24, 1.8, 0.9), (27, 0.7, 0.5))

# Part de l'écart au potentiel comblée en une saison, selon l'âge.
CATCH_UP_BY_AGE = ((20, 0.35), (23, 0.40), (26, 0.45), (29, 0.50), (99, 0.0))
# Jours de match d'une saison, sur lesquels la progression se répartit.
TICKS_PER_SEASON = 30

# Temps de jeu : un titulaire qui joue tout progresse plus qu'un joueur qui ne fait
# que s'entraîner.
MINUTES_FULL = 80
PLAYING_MIN, PLAYING_MAX = 0.6, 1.3
# Note du match sur 10 : chaque point au-dessus (ou en dessous) de 6 joue pour 10 %.
RATING_NEUTRAL, RATING_PER_POINT = 6.0, 0.10
# Installations : centre d'entraînement pour les pros, de formation pour les espoirs.
FACILITY_PER_LEVEL = 0.08  # niveau 5 : +32 %

# Attributs qui comptent à chaque poste : ils progressent deux fois plus souvent.
KEY_ATTRIBUTES = {
    Position.PROP: ("scrum", "power"),
    Position.HOOKER: ("scrum", "lineout"),
    Position.LOCK: ("lineout", "power"),
    Position.BACK_ROW: ("tackling", "power"),
    Position.SCRUM_HALF: ("passing", "handling"),
    Position.FLY_HALF: ("kicking", "passing"),
    Position.CENTRE: ("tackling", "handling"),
    Position.WING: ("pace", "handling"),
    Position.FULLBACK: ("pace", "kicking"),
}
KEY_WEIGHT = 2.0


def initial_potential(player: Player) -> float:
    """Le potentiel d'un joueur, d'après son âge et son niveau du moment ; le hasard est
    propre au joueur, si bien que le même joueur a toujours le même potentiel."""
    rng = random.Random(f"potential:{player.id}")
    upside = 0.0
    for max_age, mean, spread in UPSIDE_BY_AGE:
        if player.age <= max_age:
            upside = max(0.0, rng.gauss(mean, spread))
            break
    return round(min(max(player.level + upside, player.level), POTENTIAL_MAX), 1)


def ceiling(player: Player) -> float:
    """Le potentiel du joueur, tiré la première fois qu'on en a besoin, dans la limite du
    plus haut niveau possible (ce qui compte à son poste à 20)."""
    if player.potential is None:
        player.potential = initial_potential(player)
    return min(player.potential, BEST_LEVEL)


def catch_up(age: int) -> float:
    return next(rate for max_age, rate in CATCH_UP_BY_AGE if age <= max_age)


def playing_factor(line: PlayerMatchStats | None) -> float:
    """Ce que le match du jour apporte : temps de jeu et note."""
    if line is None:
        return PLAYING_MIN
    share = min(line.minutes / MINUTES_FULL, 1.0)
    factor = PLAYING_MIN + (PLAYING_MAX - PLAYING_MIN) * share
    if line.rating is not None and line.minutes > 0:
        factor *= 1 + RATING_PER_POINT * (line.rating - RATING_NEUTRAL) * share
    return max(factor, 0.0)


@dataclass(frozen=True)
class Training:
    """Ce que la semaine d'entraînement change à la progression (engine/training.py)."""

    pace: float = 1.0  # multiplicateur de la progression
    focus: tuple[str, ...] = ()  # attributs travaillés en priorité


NO_TRAINING = Training()


def tick(
    player: Player,
    facility_level: int,
    line: PlayerMatchStats | None,
    rng: random.Random,
    training: Training = NO_TRAINING,
) -> list[str]:
    """Un jour de match pour un joueur : il avance vers son potentiel. Renvoie les
    attributs qui ont gagné un point."""
    gap = ceiling(player) - player.level
    rate = catch_up(player.age)
    gain = _level_per_point(player, training.focus)
    if gap <= 0 or rate <= 0 or gain <= 0:
        return []
    facility = 1 + FACILITY_PER_LEVEL * (facility_level - 1)
    # Points d'attributs gagnés ce jour-là, assez pour combler la part prévue de l'écart.
    points = gap * rate / TICKS_PER_SEASON * playing_factor(line) * facility * training.pace / gain
    player.progress += points
    gained = []
    while player.progress >= 1 and player.level < ceiling(player):
        name = _pick_attribute(player, training.focus, rng)
        if name is None:
            break
        setattr(player, name, getattr(player, name) + 1)
        player.progress -= 1
        player.season_gain += 1
        gained.append(name)
    if player.level >= ceiling(player):
        player.progress = 0.0
    return gained


def _choices(player: Player, focus: Iterable[str]) -> tuple[list[str], list[float]]:
    """Les attributs qui peuvent encore gagner un point, et leurs chances."""
    names = [name for name in ATTRIBUTE_NAMES if getattr(player, name) < ATTRIBUTE_MAX]
    key, focus = KEY_ATTRIBUTES[player.position], set(focus)
    weights = [
        (KEY_WEIGHT if name in key else 1.0) * (KEY_WEIGHT if name in focus else 1.0)
        for name in names
    ]
    return names, weights


def _level_per_point(player: Player, focus: Iterable[str]) -> float:
    """Niveau gagné en moyenne par point d'attribut : un point dans un attribut qui ne
    compte pas au poste (la mêlée d'un ailier) n'en rapporte pas."""
    names, weights = _choices(player, focus)
    counted = OVERALL_WEIGHTS[player.position]
    share = sum(w * counted.get(n, 0.0) for n, w in zip(names, weights, strict=True))
    return share / max(sum(weights), 1.0)


def _pick_attribute(player: Player, focus: Iterable[str], rng: random.Random) -> str | None:
    names, weights = _choices(player, focus)
    if not names:
        return None
    return rng.choices(names, weights=weights)[0]


def develop(
    club: Club,
    stats: dict[int, PlayerMatchStats],
    rng: random.Random,
    youth: bool = False,
    training: Training = NO_TRAINING,
) -> dict[int, list[str]]:
    """Le club a joué : chacun de ses joueurs (pros, ou espoirs si `youth`) progresse
    selon ce qu'il a fait du match (`stats`). Renvoie les attributs gagnés par joueur."""
    squad = club.youths if youth else club.players
    level = club.facilities.academy_level if youth else club.facilities.training_level
    gains = {}
    for player in squad:
        gained = tick(player, level, stats.get(player.id), rng, training)
        if gained:
            gains[player.id] = gained
    return gains


def new_season(players: Iterable[Player]) -> None:
    """Intersaison : le compteur des progrès de la saison repart à zéro."""
    for player in players:
        player.season_gain = 0


# --- Ce que le club voit du potentiel --------------------------------------------------

# Écart (en points de niveau) entre l'estimation et la vérité, selon ce que le club sait
# du joueur : les siens, il les voit tous les jours ; les autres, il les devine.
OWN_UNCERTAINTY = 1.0
OTHER_UNCERTAINTY = 2.5


def estimate(player: Player, uncertainty: float) -> tuple[float, float]:
    """La fourchette de potentiel qu'un club donne à un joueur, de largeur
    2 x `uncertainty`, décalée d'un biais propre au joueur (le club peut se tromper)."""
    bias = random.Random(f"estimate:{player.id}").uniform(-0.5, 0.5) * uncertainty
    center = ceiling(player) + bias
    low = max(player.level, center - uncertainty)
    high = min(POTENTIAL_MAX + 0.5, max(center + uncertainty, low))
    return round(low, 1), round(high, 1)
