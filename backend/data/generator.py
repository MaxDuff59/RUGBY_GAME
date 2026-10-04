"""Générateur de clubs et de joueurs fictifs.

Les noms sont fabriqués à partir de syllabes : aucun vrai joueur ni vrai club.
Chaque club reçoit un niveau de base ; ses joueurs sont tirés autour de ce
niveau, avec un profil d'attributs cohérent avec leur poste.
"""

import itertools
import random

from models import ATTRIBUTE_MAX, ATTRIBUTE_MIN, ATTRIBUTE_NAMES, Club, Player, Position

# --- Noms inventés -------------------------------------------------------------------

FIRST_NAMES = [
    "Aurel", "Bastin", "Cyrian", "Dorian", "Elouan", "Fabio", "Gaspard", "Hugo",
    "Ilan", "Jory", "Kelian", "Lenny", "Malo", "Nolan", "Orso", "Paolo",
    "Quentin", "Rayan", "Sacha", "Timeo", "Ugo", "Valentin", "Wilson", "Yanis",
    "Tevita", "Sione", "Ioane", "Levan", "Rhys", "Callum", "Tomas", "Mateo",
]  # fmt: skip

LAST_NAME_SYLLABLES = [
    "bar", "ver", "lan", "dor", "mar", "tin", "ro", "chel", "gan", "bel",
    "four", "mon", "sa", "rel", "quet", "vi", "lo", "nier", "bou", "tel",
]  # fmt: skip

TOWN_PREFIXES = ["Port", "Saint", "Mont", "Val", "Bourg", "Pont", "Roche", "Clair"]
TOWN_SYLLABLES = ["vas", "or", "len", "mire", "bel", "cour", "fon", "gar", "ville", "brac"]
CLUB_PREFIXES = ["RC", "US", "Stade", "Union", "CA", "SC", "Racing", "Entente"]


def _make_last_name(rng: random.Random) -> str:
    syllables = rng.choices(LAST_NAME_SYLLABLES, k=rng.randint(2, 3))
    return "".join(syllables).capitalize()


def _make_club_name(rng: random.Random) -> str:
    town = "".join(rng.choices(TOWN_SYLLABLES, k=2)).capitalize()
    if rng.random() < 0.5:
        town = f"{rng.choice(TOWN_PREFIXES)}-{town}"
    return f"{rng.choice(CLUB_PREFIXES)} {town}"


# --- Joueurs -------------------------------------------------------------------------

# Composition d'un effectif professionnel : 31 joueurs (doublures à chaque poste).
SQUAD_COMPOSITION = {
    Position.PROP: 5,
    Position.HOOKER: 3,
    Position.LOCK: 4,
    Position.BACK_ROW: 5,
    Position.SCRUM_HALF: 2,
    Position.FLY_HALF: 2,
    Position.CENTRE: 4,
    Position.WING: 4,
    Position.FULLBACK: 2,
}

# Écart au niveau de base selon le poste : un pilier pousse en mêlée mais ne court
# pas vite, un ailier est rapide mais inutile en mêlée, etc.
# Ordre : pace, power, handling, passing, kicking, tackling, scrum, lineout
_PROFILE_TABLE = {
    Position.PROP:       (-4,  3, -2, -3, -6,  1,  4, -2),
    Position.HOOKER:     (-2,  2,  0, -1, -5,  1,  3,  4),
    Position.LOCK:       (-3,  3, -1, -2, -6,  1,  2,  4),
    Position.BACK_ROW:   ( 0,  2,  1, -1, -4,  3,  0,  1),
    Position.SCRUM_HALF: ( 1, -3,  2,  4,  1, -1, -6, -6),
    Position.FLY_HALF:   ( 0, -2,  2,  3,  4, -1, -6, -6),
    Position.CENTRE:     ( 1,  1,  2,  1, -1,  2, -5, -5),
    Position.WING:       ( 4,  0,  1, -1, -1, -1, -6, -6),
    Position.FULLBACK:   ( 3, -1,  2,  0,  2,  0, -6, -5),
}  # fmt: skip
POSITION_PROFILES: dict[Position, dict[str, int]] = {
    position: dict(zip(ATTRIBUTE_NAMES, offsets, strict=True))
    for position, offsets in _PROFILE_TABLE.items()
}

# Dispersion des attributs autour du niveau visé (écart-type).
ATTRIBUTE_SPREAD = 2.0


def _clamp(value: float) -> int:
    return max(ATTRIBUTE_MIN, min(ATTRIBUTE_MAX, round(value)))


def generate_player(
    player_id: int, position: Position, level: float, club_id: int, rng: random.Random
) -> Player:
    """Crée un joueur dont les attributs tournent autour de `level` (sur 20)."""
    # Chaque joueur a son propre niveau, un peu au-dessus ou en dessous de son club.
    player_level = rng.gauss(level, 1.5)
    profile = POSITION_PROFILES[position]
    attributes = {
        name: _clamp(rng.gauss(player_level + profile[name], ATTRIBUTE_SPREAD))
        for name in ATTRIBUTE_NAMES
    }
    return Player(
        id=player_id,
        first_name=rng.choice(FIRST_NAMES),
        last_name=_make_last_name(rng),
        age=rng.randint(18, 35),
        position=position,
        club_id=club_id,
        **attributes,
    )


# --- Clubs ---------------------------------------------------------------------------


def generate_clubs(
    count: int,
    rng: random.Random | None = None,
    min_level: float = 8.0,
    max_level: float = 14.0,
) -> list[Club]:
    """Génère `count` clubs aux noms uniques, de niveaux répartis entre min et max.

    Les identifiants commencent à 1 (clubs et joueurs).
    """
    rng = rng or random.Random()
    player_ids = itertools.count(1)

    # Noms uniques : on retire tant qu'il y a un doublon.
    names: set[str] = set()
    while len(names) < count:
        names.add(_make_club_name(rng))

    clubs = []
    for club_id, name in enumerate(sorted(names), start=1):
        level = rng.uniform(min_level, max_level)
        club = Club(id=club_id, name=name)
        for position, size in SQUAD_COMPOSITION.items():
            for _ in range(size):
                club.players.append(
                    generate_player(next(player_ids), position, level, club_id, rng)
                )
        clubs.append(club)
    return clubs
