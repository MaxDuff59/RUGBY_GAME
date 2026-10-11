"""Générateur de clubs et de joueurs.

Les clubs inventés ont des noms fabriqués à partir de syllabes. Les vrais clubs
(data/leagues.py) reçoivent leur vrai effectif, pros et espoirs, quand
data/rosters.json le connaît (scripts/fetch_rosters.py, depuis Wikipédia), et des
joueurs inventés sinon, ou pour combler un poste vide.
Chaque club reçoit un niveau de base ; ses joueurs sont tirés autour de ce
niveau, avec un profil d'attributs cohérent avec leur poste. Un vrai joueur n'a
pas de note publique : son niveau suit celui de son club, plus haut s'il est
international, et selon son âge.
"""

import itertools
import json
import math
import random
import urllib.parse
from collections import Counter
from datetime import date
from pathlib import Path

from data.leagues import DEFAULT_LEAGUE, LEAGUES, League
from engine.economy import SQUAD_MAX, SQUAD_MIN, STADIUM_STEPS, staff_wage, wage_for
from models import (
    ATTRIBUTE_MAX,
    ATTRIBUTE_MIN,
    ATTRIBUTE_NAMES,
    STAFF_LEVEL_MAX,
    STAFF_LEVEL_MIN,
    YOUTH_EXIT_AGE,
    Club,
    Facilities,
    Player,
    Position,
    Squad,
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

# Centre de formation : effectif espoirs et niveau de départ des jeunes.
YOUTH_COMPOSITION = {
    Position.PROP: 4,
    Position.HOOKER: 2,
    Position.LOCK: 3,
    Position.BACK_ROW: 4,
    Position.SCRUM_HALF: 2,
    Position.FLY_HALF: 2,
    Position.CENTRE: 3,
    Position.WING: 3,
    Position.FULLBACK: 2,
}
YOUTH_AGES = (16, 21)
YOUTH_WAGE = 15_000
# Un espoir démarre loin du niveau pro ; un bon centre réduit l'écart.
YOUTH_LEVEL_GAP = 4.5
YOUTH_LEVEL_PER_ACADEMY_LEVEL = 0.4
YOUTH_CONTRACT_YEARS = 3

# Écart au niveau de base selon le poste : un pilier pousse en mêlée mais ne court
# pas vite, un ailier est rapide mais inutile en mêlée, etc.
# Ordre : pace, power, handling, passing, kicking, tackling, scrum, lineout, stamina
_PROFILE_TABLE = {
    Position.PROP:       (-4,  3, -2, -3, -6,  1,  4, -2, -3),
    Position.HOOKER:     (-2,  2,  0, -1, -5,  1,  3,  4, -1),
    Position.LOCK:       (-3,  3, -1, -2, -6,  1,  2,  4, -1),
    Position.BACK_ROW:   ( 0,  2,  1, -1, -4,  3,  0,  1,  3),
    Position.SCRUM_HALF: ( 1, -3,  2,  4,  1, -1, -6, -6,  2),
    Position.FLY_HALF:   ( 0, -2,  2,  3,  4, -1, -6, -6,  0),
    Position.CENTRE:     ( 1,  1,  2,  1, -1,  2, -5, -5,  1),
    Position.WING:       ( 4,  0,  1, -1, -1, -1, -6, -6,  1),
    Position.FULLBACK:   ( 3, -1,  2,  0,  2,  0, -6, -5,  2),
}  # fmt: skip
POSITION_PROFILES: dict[Position, dict[str, int]] = {
    position: dict(zip(ATTRIBUTE_NAMES, offsets, strict=True))
    for position, offsets in _PROFILE_TABLE.items()
}

# Dispersion des attributs autour du niveau visé (écart-type).
ATTRIBUTE_SPREAD = 2.0

# Saison de départ : les contrats générés se terminent entre cette saison et trois plus tard.
FIRST_SEASON_YEAR = 2026
CONTRACT_MAX_YEARS = 4


def _clamp(value: float) -> int:
    return max(ATTRIBUTE_MIN, min(ATTRIBUTE_MAX, round(value)))


def generate_player(
    player_id: int,
    position: Position,
    level: float,
    club_id: int | None,
    rng: random.Random,
    season_year: int = FIRST_SEASON_YEAR,
) -> Player:
    """Crée un joueur dont les attributs tournent autour de `level` (sur 20)."""
    # Chaque joueur a son propre niveau, un peu au-dessus ou en dessous de son club.
    player_level = rng.gauss(level, 1.5)
    attributes = _attributes(player_id, position, player_level, rng)
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
    # Contrat : de la dernière année (négociable par les autres clubs) à quatre saisons.
    player.contract_until = season_year + rng.randint(0, CONTRACT_MAX_YEARS - 1)
    return player


def _attributes(
    player_id: int, position: Position, player_level: float, rng: random.Random
) -> dict[str, int]:
    """Les 9 attributs d'un joueur de ce niveau, selon le profil de son poste."""
    profile = POSITION_PROFILES[position]
    skills = [name for name in ATTRIBUTE_NAMES if name != "stamina"]
    attributes = {
        name: _clamp(rng.gauss(player_level + profile[name], ATTRIBUTE_SPREAD)) for name in skills
    }
    # L'endurance, ajoutée après coup, se tire avec un hasard propre au joueur
    # (dérivé de ses autres attributs) : un monde généré à partir d'une graine
    # reste le même qu'avant son ajout.
    own = random.Random(f"{player_id}:{list(attributes.values())}")
    attributes["stamina"] = _clamp(own.gauss(player_level + profile["stamina"], ATTRIBUTE_SPREAD))
    return attributes


def youth_level(club_level: float, academy_level: int) -> float:
    """Niveau de départ d'un jeune du centre de formation."""
    return club_level - YOUTH_LEVEL_GAP + YOUTH_LEVEL_PER_ACADEMY_LEVEL * academy_level


def generate_youth_player(
    player_id: int,
    position: Position,
    level: float,
    club_id: int,
    rng: random.Random,
    season_year: int = FIRST_SEASON_YEAR,
    age: int | None = None,
) -> Player:
    """Un espoir : jeune, mal payé, sous contrat de formation."""
    youth = generate_player(player_id, position, level, club_id, rng, season_year)
    youth.age = age if age is not None else rng.randint(*YOUTH_AGES)
    youth.wage = YOUTH_WAGE
    youth.contract_until = season_year + YOUTH_CONTRACT_YEARS - 1
    youth.squad = Squad.YOUTH
    return youth


# --- Vrais effectifs ----------------------------------------------------------------

ROSTERS_PATH = Path(__file__).with_name("rosters.json")
# Âge des joueurs au début de la première saison.
SEASON_START = date(FIRST_SEASON_YEAR, 9, 1)
# Un vrai effectif compte souvent 40 joueurs : on en garde assez pour laisser de la
# place sous SQUAD_MAX ; les jeunes en trop rejoignent les espoirs, les autres le
# vivier des agents libres.
REAL_SQUAD_CAP = SQUAD_MAX - 2
REAL_YOUTH_CAP = 30
YOUTH_OVERFLOW_AGE = 21
# Postes à pourvoir au minimum chez les pros (sinon un joueur inventé comble).
POSITION_MINIMUM = {
    Position.PROP: 4,
    Position.HOOKER: 2,
    Position.LOCK: 3,
    Position.BACK_ROW: 4,
    Position.SCRUM_HALF: 2,
    Position.FLY_HALF: 2,
    Position.CENTRE: 3,
    Position.WING: 3,
    Position.FULLBACK: 1,
}
# Photo d'un vrai joueur : chemin dans l'API, qui la sert depuis sa propre copie
# (voir api/routers/photos.py). Le nom est celui du fichier sur Wikimedia Commons.
PHOTO_PATH = "/photos/{}"
# Niveau d'un vrai joueur par rapport à son club : international, puis âge.
INTERNATIONAL_BONUS = 1.6
REAL_PLAYER_SPREAD = 1.0


def load_rosters() -> dict:
    """Les vrais effectifs connus (data/rosters.json), par nom de club."""
    return json.loads(ROSTERS_PATH.read_text()) if ROSTERS_PATH.exists() else {}


def _age_offset(age: int) -> float:
    """Écart de niveau selon l'âge : on progresse jusqu'à 25 ans, on décline après 32."""
    if age <= 20:
        return -2.0
    if age <= 22:
        return -1.0
    if age <= 24:
        return -0.3
    if age <= 31:
        return 0.3
    if age <= 33:
        return 0.0
    return -0.6


def _real_age(entry: dict, ages: tuple[int, int], rng: random.Random) -> int:
    born = entry.get("born")
    if born:
        b = date.fromisoformat(born)
        return (
            SEASON_START.year - b.year - ((SEASON_START.month, SEASON_START.day) < (b.month, b.day))
        )
    return rng.randint(*ages)


def _split_name(name: str) -> tuple[str, str]:
    """'Juan Cruz Mallía' -> ('Juan', 'Cruz Mallía') ; un seul mot devient le nom."""
    first, _, last = name.strip().partition(" ")
    return (first, last) if last else ("", first)


def _trim(entries: list[dict], cap: int, composition: dict[Position, int]) -> tuple[list, list]:
    """Ramène la liste à `cap` joueurs en retirant au poste le plus fourni (rapporté
    à l'effectif type) : d'abord un jeune non international, puis le dernier listé."""
    kept, dropped = list(entries), []
    while len(kept) > cap:
        counts = Counter(e["position"] for e in kept)
        position = max(counts, key=lambda p: counts[p] / composition[p])
        candidates = [e for e in reversed(kept) if e["position"] == position]
        victim = min(candidates, key=lambda e: (e["international"], e["age"] > YOUTH_OVERFLOW_AGE))
        kept.remove(victim)
        dropped.append(victim)
    return kept, dropped


def _entries(raw: list[dict], ages: tuple[int, int], rng: random.Random) -> list[dict]:
    """Joueurs du fichier, avec leur poste du jeu et leur âge (tiré au hasard s'il est inconnu)."""
    return [
        {
            "name": e["name"],
            "position": Position(e["position"].upper()),
            "international": bool(e.get("international")),
            "age": _real_age(e, ages, rng),
            "photo": e.get("photo"),
        }
        for e in raw
    ]


def _real_player(
    entry: dict, player_id: int, player_level: float, club_id: int | None, rng: random.Random
) -> Player:
    first, last = _split_name(entry["name"])
    player = Player(
        id=player_id,
        first_name=first[:50],
        last_name=last[:50],
        age=entry["age"],
        position=entry["position"],
        club_id=club_id,
        **_attributes(player_id, entry["position"], player_level, rng),
    )
    player.wage = wage_for(player, noise=rng.uniform(0.9, 1.15))
    player.contract_until = FIRST_SEASON_YEAR + rng.randint(0, CONTRACT_MAX_YEARS - 1)
    if entry["photo"]:
        player.photo = PHOTO_PATH.format(urllib.parse.quote(entry["photo"].replace(" ", "_")))
    return player


def _fullbacks_from_wings(entries: list[dict]) -> None:
    """Certains effectifs rangent ailiers et arrières ensemble (« Outside backs ») : sans
    arrière, le dernier tiers de ces ailiers passe arrière."""
    if any(e["position"] == Position.FULLBACK for e in entries):
        return
    wings = [e for e in entries if e["position"] == Position.WING]
    for entry in wings[len(wings) - len(wings) // 3 :]:
        entry["position"] = Position.FULLBACK


def _real_squads(
    club: Club,
    roster: dict,
    level: float,
    player_ids: itertools.count,
    rng: random.Random,
    released: list[Player],
) -> None:
    """Remplit pros et espoirs d'un club depuis son vrai effectif, en comblant les manques."""
    entries = _entries(roster["pros"], (21, 32), rng)
    _fullbacks_from_wings(entries)
    pros, overflow = _trim(entries, REAL_SQUAD_CAP, SQUAD_COMPOSITION)
    # Espoirs : sans les trop âgés (une réserve compte aussi des pros confirmés).
    youths = _entries(roster.get("youths", []), YOUTH_AGES, rng)
    youths = [e for e in youths if e["age"] < YOUTH_EXIT_AGE]
    youths += [e for e in overflow if e["age"] <= YOUTH_OVERFLOW_AGE]
    youths, _ = _trim(youths, REAL_YOUTH_CAP, YOUTH_COMPOSITION)

    # Le niveau moyen des pros reste celui du club : les bonus se compensent.
    offsets = [INTERNATIONAL_BONUS * e["international"] + _age_offset(e["age"]) for e in pros]
    mean = sum(offsets) / len(offsets) if offsets else 0.0
    for entry, offset in zip(pros, offsets, strict=True):
        player_level = rng.gauss(level + offset - mean, REAL_PLAYER_SPREAD)
        club.players.append(_real_player(entry, next(player_ids), player_level, club.id, rng))
    for entry in overflow:
        if entry["age"] > YOUTH_OVERFLOW_AGE:
            player_level = rng.gauss(level - 1.0, REAL_PLAYER_SPREAD)
            free = _real_player(entry, next(player_ids), player_level, None, rng)
            free.contract_until = FIRST_SEASON_YEAR - 1
            released.append(free)

    junior_level = youth_level(level, club.facilities.academy_level)
    for entry in youths:
        bonus = INTERNATIONAL_BONUS * entry["international"] + 0.3 * (entry["age"] - 19)
        player_level = rng.gauss(junior_level + bonus, REAL_PLAYER_SPREAD)
        youth = _real_player(entry, next(player_ids), player_level, club.id, rng)
        youth.wage = YOUTH_WAGE
        youth.contract_until = FIRST_SEASON_YEAR + YOUTH_CONTRACT_YEARS - 1
        youth.squad = Squad.YOUTH
        club.youths.append(youth)

    # Postes vides ou trop peu fournis : des joueurs inventés comblent.
    counts = Counter(p.position for p in club.players)
    for position, minimum in POSITION_MINIMUM.items():
        for _ in range(minimum - counts[position]):
            club.players.append(generate_player(next(player_ids), position, level, club.id, rng))
    while len(club.players) < SQUAD_MIN:
        counts = Counter(p.position for p in club.players)
        position = min(Position, key=lambda p: counts[p] / SQUAD_COMPOSITION[p])
        club.players.append(generate_player(next(player_ids), position, level, club.id, rng))
    counts = Counter(p.position for p in club.youths)
    for position, size in YOUTH_COMPOSITION.items():
        for _ in range(math.ceil(size / 2) - counts[position]):
            club.youths.append(
                generate_youth_player(next(player_ids), position, junior_level, club.id, rng)
            )


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
        club = _make_club(
            club_id,
            name,
            level,
            wealth,
            STADIUM_STEPS[round(wealth * 3)],
            player_ids,
            staff_ids,
            rng,
        )
        clubs.append(club)
    return clubs


def generate_real_clubs(
    rng: random.Random | None = None,
    leagues: list[League] = LEAGUES,
    rosters: dict | None = None,
    released: list[Player] | None = None,
) -> list[Club]:
    """Les vrais clubs de chaque championnat, avec leur vrai effectif quand `rosters`
    le connaît (par défaut data/rosters.json) et des joueurs inventés sinon ; le staff
    est inventé. Les vrais joueurs en surnombre sans place chez les espoirs vont dans
    `released` (agents libres). Les plus grands stades sont ramenés au plus grand
    constructible."""
    rng = rng or random.Random()
    rosters = load_rosters() if rosters is None else rosters
    released = [] if released is None else released
    player_ids = itertools.count(1)
    staff_ids = itertools.count(1)
    reals = [(league.code, real) for league in leagues for real in league.clubs]
    return [
        _make_club(
            club_id,
            real.name,
            real.level,
            real.wealth,
            min(real.capacity, STADIUM_STEPS[-1]),
            player_ids,
            staff_ids,
            rng,
            league=code,
            roster=rosters.get(real.name),
            released=released,
        )
        for club_id, (code, real) in enumerate(reals, start=1)
    ]


def _make_club(
    club_id: int,
    name: str,
    level: float,
    wealth: float,
    stadium_capacity: int,
    player_ids: itertools.count,
    staff_ids: itertools.count,
    rng: random.Random,
    league: str = DEFAULT_LEAGUE,
    roster: dict | None = None,
    released: list[Player] | None = None,
) -> Club:
    """Un club complet : trésorerie et infrastructures selon `wealth`, effectif selon `level`
    (son vrai effectif si `roster` est donné)."""
    club = Club(
        id=club_id,
        name=name,
        league=league,
        balance=_round_to(rng.uniform(2_000_000, 3_000_000) + wealth * 6_000_000, 50_000),
        facilities=Facilities(
            stadium_capacity=stadium_capacity,
            training_level=1 + round(wealth * 2),
            academy_level=1 + round(wealth * 2),
        ),
    )
    if roster and roster.get("pros"):
        _real_squads(club, roster, level, player_ids, rng, [] if released is None else released)
    else:
        for position, size in SQUAD_COMPOSITION.items():
            for _ in range(size):
                club.players.append(
                    generate_player(next(player_ids), position, level, club_id, rng)
                )
        junior_level = youth_level(level, club.facilities.academy_level)
        for position, size in YOUTH_COMPOSITION.items():
            for _ in range(size):
                club.youths.append(
                    generate_youth_player(next(player_ids), position, junior_level, club_id, rng)
                )
    # Un membre de staff par poste, de niveau proche de celui du club.
    for role in StaffRole:
        staff_level = _clamp_level(round(1.5 + wealth * 2.5 + rng.uniform(-1, 1)))
        club.staff.append(generate_staff_member(next(staff_ids), role, staff_level, club_id, rng))
    return club


def _round_to(value: float, step: int) -> int:
    return int(round(value / step) * step)


def _clamp_level(level: int) -> int:
    return max(STAFF_LEVEL_MIN, min(STAFF_LEVEL_MAX, level))
