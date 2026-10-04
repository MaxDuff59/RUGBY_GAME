"""Générateur de clubs et de joueurs fictifs.

Les noms sont fabriqués à partir de syllabes : aucun vrai joueur ni vrai club.
Chaque club reçoit un niveau de base ; ses joueurs sont tirés autour de ce
niveau, avec un profil d'attributs cohérent avec leur poste.
"""

import itertools
import random

from engine.economy import STADIUM_STEPS, staff_wage, wage_for
from models import (
    ATTRIBUTE_MAX,
    ATTRIBUTE_MIN,
    ATTRIBUTE_NAMES,
    STAFF_LEVEL_MAX,
    STAFF_LEVEL_MIN,
    Club,
    Facilities,
    Player,
    Position,
    StaffMember,
    StaffRole,
)

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
    player = Player(
        id=player_id,
        first_name=rng.choice(FIRST_NAMES),
        last_name=_make_last_name(rng),
        age=rng.randint(18, 35),
        position=position,
        club_id=club_id,
        **attributes,
    )
    # Salaire négocié autour de la valeur du joueur (de -10 % à +15 %).
    player.wage = wage_for(player, noise=rng.uniform(0.9, 1.15))
    return player


# --- Staff ---------------------------------------------------------------------------


def generate_staff_member(
    staff_id: int, role: StaffRole, level: int, club_id: int | None, rng: random.Random
) -> StaffMember:
    return StaffMember(
        id=staff_id,
        first_name=rng.choice(FIRST_NAMES),
        last_name=_make_last_name(rng),
        role=role,
        level=level,
        wage=staff_wage(level),
        club_id=club_id,
    )


def generate_staff_candidates(
    count_per_role: int, rng: random.Random | None = None, first_id: int = 1
) -> list[StaffMember]:
    """Membres de staff sans club, disponibles à l'embauche, de tous niveaux."""
    rng = rng or random.Random()
    ids = itertools.count(first_id)
    return [
        generate_staff_member(
            next(ids), role, rng.randint(STAFF_LEVEL_MIN, STAFF_LEVEL_MAX), None, rng
        )
        for role in StaffRole
        for _ in range(count_per_role)
    ]


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
    staff_ids = itertools.count(1)

    # Noms uniques : on retire tant qu'il y a un doublon.
    names: set[str] = set()
    while len(names) < count:
        names.add(_make_club_name(rng))

    clubs = []
    for club_id, name in enumerate(sorted(names), start=1):
        level = rng.uniform(min_level, max_level)
        # 0 = club modeste, 1 = gros club : sert à doser argent, staff et stade.
        wealth = (level - min_level) / (max_level - min_level)

        club = Club(
            id=club_id,
            name=name,
            balance=_round_to(rng.uniform(2_000_000, 3_000_000) + wealth * 6_000_000, 50_000),
            facilities=Facilities(
                stadium_capacity=STADIUM_STEPS[round(wealth * 3)],
                training_level=1 + round(wealth * 2),
                academy_level=1 + round(wealth * 2),
            ),
        )
        for position, size in SQUAD_COMPOSITION.items():
            for _ in range(size):
                club.players.append(
                    generate_player(next(player_ids), position, level, club_id, rng)
                )
        # Un membre de staff par poste, de niveau proche de celui du club.
        for role in StaffRole:
            staff_level = _clamp_level(round(1.5 + wealth * 2.5 + rng.uniform(-1, 1)))
            club.staff.append(
                generate_staff_member(next(staff_ids), role, staff_level, club_id, rng)
            )
        clubs.append(club)
    return clubs


def _round_to(value: float, step: int) -> int:
    return int(round(value / step) * step)


def _clamp_level(level: int) -> int:
    return max(STAFF_LEVEL_MIN, min(STAFF_LEVEL_MAX, level))
