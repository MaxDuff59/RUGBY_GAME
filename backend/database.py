"""Parties sauvegardées : création des tables, remplissage initial, et où elles vivent.

Deux rangements possibles, choisis par l'environnement :

- `RUGBY_DATABASE_URL` absent : une base SQLite par emplacement et par joueur
  (`saves/u<id>/partie-1.db` à `partie-3.db`, `<id>` étant le compte, voir accounts.py).
- `RUGBY_DATABASE_URL` présent (Postgres, par exemple Supabase) : un seul serveur,
  un schéma par partie (`save_u<id>_s<n>`) avec exactement les mêmes tables ; les
  comptes et le registre des parties (`saves`) sont dans le schéma `public`.

Dans les deux cas, chaque action est enregistrée aussitôt : la partie se sauvegarde
au fur et à mesure. La partie chargée est retenue sur le compte (`active_slot`).
"""

import datetime
import itertools
import os
import random
from collections import OrderedDict
from pathlib import Path

from sqlalchemy import Engine, create_engine, event, func, inspect, select, text, update
from sqlalchemy.orm import Session, sessionmaker

from data.generator import (
    ATTRIBUTE_SPREAD,
    FIRST_SEASON_YEAR,
    PHOTO_PATH,
    POSITION_PROFILES,
    generate_clubs,
    generate_real_clubs,
    generate_staff_candidates,
    roster_nationalities,
)
from data.leagues import LEAGUES
from data.nations import home_nation
from engine.development import ceiling, initial_potential
from engine.free_agents import newcomers
from models import (
    ATTRIBUTE_MAX,
    ATTRIBUTE_MIN,
    ATTRIBUTE_NAMES,
    Position,
    overall_at_level,
)
from models.orm import LEAGUE_CODE_LENGTH, Base, ClubRow, MoveRow, PlayerRow, StaffRow

# Dossier des parties SQLite et des photos (surchargeable : instance de test, volume en prod).
SAVES_DIR = Path(os.environ.get("RUGBY_SAVES_DIR", "./saves"))


def _postgres_url(url: str | None) -> str | None:
    """L'URL telle que SQLAlchemy la veut, avec le pilote psycopg : les hébergeurs
    (Railway, Supabase, Heroku) donnent `postgres://` ou `postgresql://` sans pilote."""
    if not url:
        return None
    for prefix in ("postgres://", "postgresql://"):
        if url.startswith(prefix):
            return "postgresql+psycopg://" + url[len(prefix) :]
    return url


# Serveur Postgres (ex. postgresql://... d'un hébergeur) ; None : SQLite par fichier.
DATABASE_URL = _postgres_url(os.environ.get("RUGBY_DATABASE_URL"))
SLOT_COUNT = 3
# Connexions SQLite gardées ouvertes : au-delà, la plus ancienne est fermée.
ENGINE_CACHE_SIZE = 64

# Nombre de clubs inventés (un seul championnat) quand on ne prend pas les vrais clubs.
DEFAULT_CLUB_COUNT = 14

SlotKey = tuple[int, int]  # (compte, emplacement)

_engines: OrderedDict[SlotKey, Engine] = OrderedDict()
# Parties dont le schéma a été vérifié (et migré) depuis le démarrage de l'API.
_checked: set[SlotKey] = set()
_shared: Engine | None = None


class NoSaveLoaded(Exception):
    """Aucune partie chargée : il faut en choisir une (ou en commencer une)."""


class OutdatedSave(Exception):
    """Une partie à un ancien format, que le jeu ne sait plus ouvrir."""


def uses_postgres() -> bool:
    return DATABASE_URL is not None


# --- Postgres : un serveur, un schéma par partie -----------------------------------------


def shared_engine() -> Engine:
    """La connexion au serveur Postgres, partagée par les parties et les comptes
    (créée au premier appel, avec le registre des parties)."""
    global _shared
    if _shared is None:
        _shared = create_engine(
            DATABASE_URL,
            pool_size=5,
            max_overflow=5,
            pool_pre_ping=True,
            pool_recycle=1800,
            # Pas de requêtes préparées côté serveur : le pooler de Supabase ne les suit pas.
            connect_args={"prepare_threshold": None},
        )
        with _shared.begin() as connection:
            connection.execute(
                text(
                    "CREATE TABLE IF NOT EXISTS saves ("
                    "user_id INTEGER NOT NULL, slot INTEGER NOT NULL, "
                    "updated_at TIMESTAMP NOT NULL, PRIMARY KEY (user_id, slot))"
                )
            )
    return _shared


def schema_name(user_id: int, slot: int) -> str:
    if not 1 <= slot <= SLOT_COUNT:
        raise ValueError(f"Emplacement {slot} : il y en a {SLOT_COUNT}")
    return f"save_u{user_id}_s{slot}"


def _schema_of(engine: Engine) -> str | None:
    """Le schéma Postgres vers lequel un moteur de partie est dirigé (None en SQLite)."""
    return engine.get_execution_options().get("schema_translate_map", {}).get(None)


def _touch_on_commit(session: Session, user_id: int, slot: int) -> None:
    """Bascule `saves.updated_at` à chaque commit qui a changé quelque chose."""

    @event.listens_for(session, "after_flush")
    def flushed(session: Session, _context) -> None:
        session.info["touched"] = True

    @event.listens_for(session, "before_commit")
    def committing(session: Session) -> None:
        session.flush()
        if session.info.pop("touched", False):
            session.execute(
                text("UPDATE saves SET updated_at = :now WHERE user_id = :u AND slot = :s"),
                {"now": datetime.datetime.now(), "u": user_id, "s": slot},
            )


# --- Une partie = un fichier SQLite, ou un schéma Postgres --------------------------------


def slot_path(user_id: int, slot: int) -> Path:
    if not 1 <= slot <= SLOT_COUNT:
        raise ValueError(f"Emplacement {slot} : il y en a {SLOT_COUNT}")
    return SAVES_DIR / f"u{user_id}" / f"partie-{slot}.db"


def slot_exists(user_id: int, slot: int) -> bool:
    if uses_postgres():
        with shared_engine().connect() as connection:
            found = connection.execute(
                text("SELECT 1 FROM saves WHERE user_id = :u AND slot = :s"),
                {"u": user_id, "s": slot},
            ).first()
        return found is not None
    return slot_path(user_id, slot).exists()


def saved_at(user_id: int, slot: int) -> datetime.datetime:
    """Dernière sauvegarde (automatique) d'une partie existante."""
    if uses_postgres():
        with shared_engine().connect() as connection:
            value = connection.execute(
                text("SELECT updated_at FROM saves WHERE user_id = :u AND slot = :s"),
                {"u": user_id, "s": slot},
            ).scalar_one()
        return value
    return datetime.datetime.fromtimestamp(slot_path(user_id, slot).stat().st_mtime)


def engine_for(user_id: int, slot: int) -> Engine:
    """Connexion à la base d'une partie (créée au premier appel, puis réutilisée)."""
    if uses_postgres():
        # Même serveur, même réservoir de connexions : seules les tables visées changent.
        return shared_engine().execution_options(
            schema_translate_map={None: schema_name(user_id, slot)}
        )
    key = (user_id, slot)
    if key in _engines:
        _engines.move_to_end(key)
        return _engines[key]
    while len(_engines) >= ENGINE_CACHE_SIZE:
        _, oldest = _engines.popitem(last=False)
        oldest.dispose()
    # check_same_thread=False : nécessaire pour utiliser SQLite depuis FastAPI
    # (plusieurs threads).
    _engines[key] = create_engine(
        f"sqlite:///{slot_path(user_id, slot)}", connect_args={"check_same_thread": False}
    )
    return _engines[key]


def session_for(user_id: int, slot: int) -> Session:
    session = sessionmaker(bind=engine_for(user_id, slot), expire_on_commit=False)()
    if uses_postgres():
        _touch_on_commit(session, user_id, slot)
    return session


def open_slot(user_id: int, slot: int) -> Session:
    """Session sur une partie existante, son schéma vérifié une fois par lancement
    (OutdatedSave s'il est trop ancien)."""
    key = (user_id, slot)
    if key not in _checked:
        init_db(engine_for(user_id, slot))
        _checked.add(key)
    return session_for(user_id, slot)


def load_slot(user_id: int, slot: int) -> None:
    """Vérifie qu'une partie existante s'ouvre (OutdatedSave si son format est trop ancien)."""
    init_db(engine_for(user_id, slot))
    _checked.add((user_id, slot))


def new_slot(user_id: int, slot: int, seed: int | None = None) -> None:
    """Remplace l'emplacement par un monde neuf (la carrière reste à choisir). Un monde
    qui n'a pas pu se remplir (catalogue injoignable...) est effacé : l'emplacement
    reste libre au lieu de garder une partie vide."""
    try:
        _fill_slot(user_id, slot, seed)
    except Exception:
        delete_slot(user_id, slot)
        raise


def _fill_slot(user_id: int, slot: int, seed: int | None) -> None:
    delete_slot(user_id, slot)
    if uses_postgres():
        schema = schema_name(user_id, slot)
        with shared_engine().begin() as connection:
            connection.execute(text(f'CREATE SCHEMA "{schema}"'))
            connection.execute(
                text("INSERT INTO saves (user_id, slot, updated_at) VALUES (:u, :s, :now)"),
                {"u": user_id, "s": slot, "now": datetime.datetime.now()},
            )
    else:
        slot_path(user_id, slot).parent.mkdir(parents=True, exist_ok=True)
    engine = engine_for(user_id, slot)
    init_db(engine)
    _checked.add((user_id, slot))
    with session_for(user_id, slot) as session:
        import catalog  # import tardif : la base des comptes sert aussi au catalogue

        seed_if_empty(session, seed=seed, leagues=catalog.leagues(), rosters=catalog.rosters())
    if uses_postgres():
        _resync_sequences(engine)


def _resync_sequences(engine: Engine) -> None:
    """Après un remplissage avec des identifiants choisis (clubs, joueurs, staff), les
    compteurs de Postgres repartent après le plus grand identifiant de chaque table."""
    schema = _schema_of(engine)
    with engine.begin() as connection:
        for table in Base.metadata.sorted_tables:
            if "id" not in table.columns:
                continue
            qualified = f'"{schema}"."{table.name}"'
            connection.execute(
                text(
                    f"SELECT setval(pg_get_serial_sequence('{qualified}', 'id'), "
                    f"COALESCE((SELECT MAX(id) FROM {qualified}), 0) + 1, false)"
                )
            )


def delete_slot(user_id: int, slot: int) -> None:
    """Efface une partie (son fichier, ou son schéma)."""
    key = (user_id, slot)
    _checked.discard(key)
    if uses_postgres():
        with shared_engine().begin() as connection:
            connection.execute(
                text(f'DROP SCHEMA IF EXISTS "{schema_name(user_id, slot)}" CASCADE')
            )
            connection.execute(
                text("DELETE FROM saves WHERE user_id = :u AND slot = :s"),
                {"u": user_id, "s": slot},
            )
        return
    engine = _engines.pop(key, None)
    if engine is not None:
        engine.dispose()
    slot_path(user_id, slot).unlink(missing_ok=True)


def forget_engines() -> None:
    """Ferme toutes les connexions ouvertes (tests : changer de base entre deux cas)."""
    global _shared
    for engine in _engines.values():
        engine.dispose()
    _engines.clear()
    _checked.clear()
    if _shared is not None:
        _shared.dispose()
        _shared = None


def init_db(engine: Engine) -> None:
    """Crée les tables si elles n'existent pas encore, et vérifie leur schéma."""
    Base.metadata.create_all(engine)
    _migrate(engine)
    # Pas de migrations générales : create_all ajoute les tables manquantes mais
    # pas les colonnes. Hors des cas traités par `_migrate`, une partie à l'ancien
    # schéma ne s'ouvre plus : il faut la supprimer.
    inspector = inspect(engine)
    schema = _schema_of(engine)
    for table in Base.metadata.sorted_tables:
        actual = {column["name"] for column in inspector.get_columns(table.name, schema=schema)}
        expected = {column.name for column in table.columns}
        if not expected <= actual:
            raise OutdatedSave(
                f"Cette partie a un ancien format (table « {table.name} ») : "
                "supprime-la pour en commencer une nouvelle."
            )


def _add_season_seed(engine: Engine) -> None:
    """Graine du hasard de la saison, ajoutée après coup (SQLite comme Postgres) :
    les saisons en cours en tirent une à leur prochaine journée."""
    inspector = inspect(engine)
    schema = _schema_of(engine)
    if not inspector.has_table("seasons", schema=schema):
        return
    if "seed" in {column["name"] for column in inspector.get_columns("seasons", schema=schema)}:
        return
    table = f'"{schema}"."seasons"' if schema else "seasons"
    with engine.begin() as connection:
        connection.execute(text(f"ALTER TABLE {table} ADD COLUMN seed INTEGER"))


def _add_nationality(engine: Engine) -> None:
    """Nationalité des joueurs, ajoutée après coup (SQLite comme Postgres) avec les
    sélections nationales : un vrai joueur retrouve la sienne dans data/rosters.json,
    un joueur inventé prend celle du pays de son club (aucune dans un monde inventé)."""
    inspector = inspect(engine)
    schema = _schema_of(engine)
    if not inspector.has_table("players", schema=schema):
        return
    if "nationality" in {c["name"] for c in inspector.get_columns("players", schema=schema)}:
        return
    table = f'"{schema}"."players"' if schema else "players"
    with engine.begin() as connection:
        connection.execute(text(f"ALTER TABLE {table} ADD COLUMN nationality VARCHAR(3)"))
    known = roster_nationalities()
    with sessionmaker(bind=engine)() as session:
        countries = {
            club_id: home_nation(name)
            for club_id, name in session.execute(select(ClubRow.id, ClubRow.name))
        }
        rows = session.execute(
            select(
                PlayerRow.id,
                PlayerRow.first_name,
                PlayerRow.last_name,
                PlayerRow.club_id,
                PlayerRow.loaned_from,
            )
        )
        found = []
        for player_id, first_name, last_name, club_id, loaned_from in rows:
            # Un joueur prêté est formé (ou payé) par son club propriétaire.
            code = known.get(f"{first_name} {last_name}".strip()) or countries.get(
                loaned_from or club_id
            )
            if code:
                found.append({"id": player_id, "nationality": code})
        if found:
            session.execute(update(PlayerRow), found)
            session.commit()


def _add_international_stage(engine: Engine) -> None:
    """Tour des matchs internationaux, ajouté après coup avec la Coupe du monde (SQLite
    comme Postgres) : ceux d'avant étaient tous des matchs de tournoi ou de tournée."""
    inspector = inspect(engine)
    schema = _schema_of(engine)
    if not inspector.has_table("internationals", schema=schema):
        return
    columns = {c["name"] for c in inspector.get_columns("internationals", schema=schema)}
    if "stage" in columns:
        return
    table = f'"{schema}"."internationals"' if schema else "internationals"
    with engine.begin() as connection:
        connection.execute(
            text(f"ALTER TABLE {table} ADD COLUMN stage VARCHAR(10) NOT NULL DEFAULT 'regular'")
        )


# Colonnes ajoutées après coup, SQLite comme Postgres, avec leur valeur pour les
# parties d'avant : la météo et les statistiques des matchs (les matchs déjà joués
# n'en ont pas), leur public et leur momentum, la discipline des joueurs et le capitaine
# choisi par le manager.
ADDED_COLUMNS = {
    "matches": {
        "weather": "VARCHAR(8)",
        "stats": "JSON NOT NULL DEFAULT '{}'",
        "spectators": "INTEGER",
        "atmosphere": "FLOAT",
        "momentum": "JSON NOT NULL DEFAULT '[]'",
    },
    "players": {
        "suspended_matches": "INTEGER NOT NULL DEFAULT 0",
        "yellow_cards": "INTEGER NOT NULL DEFAULT 0",
        "potential": "FLOAT",
        "progress": "FLOAT NOT NULL DEFAULT 0",
        "season_gain": "INTEGER NOT NULL DEFAULT 0",
        "potential_scale": "INTEGER NOT NULL DEFAULT 1",
    },
    "careers": {
        "difficulty": "VARCHAR(6) NOT NULL DEFAULT 'normal'",
        "contract_until": "INTEGER",
        "extension_refused_on": "DATE",
    },
    "dismissals": {"reason": "VARCHAR(10) NOT NULL DEFAULT 'dismissed'"},
    "cup_pools": {"competition": "VARCHAR(16) NOT NULL DEFAULT 'champions_cup'"},
    "clubs": {
        "captain_id": "INTEGER",
        "training_intensity": "VARCHAR(8) NOT NULL DEFAULT 'normal'",
        "training_theme": "VARCHAR(10) NOT NULL DEFAULT 'none'",
    },
}


def _add_columns(engine: Engine) -> None:
    inspector = inspect(engine)
    schema = _schema_of(engine)
    for table, columns in ADDED_COLUMNS.items():
        if not inspector.has_table(table, schema=schema):
            continue
        present = {c["name"] for c in inspector.get_columns(table, schema=schema)}
        name = f'"{schema}"."{table}"' if schema else table
        with engine.begin() as connection:
            for column, ddl in columns.items():
                if column not in present:
                    connection.execute(text(f"ALTER TABLE {name} ADD COLUMN {column} {ddl}"))


def _rescale_potential(engine: Engine) -> None:
    """La note générale ne fait plus la moyenne des 9 attributs mais compte ce qui sert au
    poste (models/domain.py). Le potentiel déjà tiré, sur l'ancienne note, bouge d'autant
    que le niveau du joueur, pour lui laisser la même marge ; les notes gardées par le
    journal des mouvements passent à la nouvelle note générale."""
    if not inspect(engine).has_table("players", schema=_schema_of(engine)):
        return
    with sessionmaker(bind=engine)() as session:
        rows = session.scalars(select(PlayerRow).where(PlayerRow.potential_scale == 1)).all()
        if not rows:
            return
        for row in rows:
            if row.potential is not None:
                mean = sum(getattr(row, name) for name in ATTRIBUTE_NAMES) / len(ATTRIBUTE_NAMES)
                row.potential = round(row.potential + row.level - mean, 1)
            row.potential_scale = 2
        for move in session.scalars(select(MoveRow)):
            move.overall = round(overall_at_level(move.overall), 2)
        session.commit()


def _fill_potential(engine: Engine) -> None:
    """Potentiel des joueurs qui n'en ont pas encore (parties d'avant la progression,
    et joueurs créés depuis le dernier lancement) : tiré d'après leur âge et leur note."""
    if not inspect(engine).has_table("players", schema=_schema_of(engine)):
        return
    with sessionmaker(bind=engine)() as session:
        rows = session.scalars(select(PlayerRow).where(PlayerRow.potential.is_(None))).all()
        for row in rows:
            row.potential = initial_potential(row.to_domain())
        if rows:
            session.commit()


def _widen_league_codes(engine: Engine) -> None:
    """Postgres : les colonnes de championnat créées à 12 caractères passent à
    `LEAGUE_CODE_LENGTH`, pour le code de la Coupe d'Europe (SQLite ne limite pas)."""
    schema = _schema_of(engine)
    if engine.dialect.name == "sqlite" or schema is None:
        return
    with engine.begin() as connection:
        short = connection.execute(
            text(
                "SELECT table_name FROM information_schema.columns WHERE table_schema = :schema"
                " AND column_name = 'league' AND character_maximum_length < :length"
            ),
            {"schema": schema, "length": LEAGUE_CODE_LENGTH},
        ).scalars()
        for table in list(short):
            connection.execute(
                text(
                    f'ALTER TABLE "{schema}"."{table}" ALTER COLUMN league '
                    f"TYPE VARCHAR({LEAGUE_CODE_LENGTH})"
                )
            )


def _migrate(engine: Engine) -> None:
    """Les quelques changements de schéma qu'on sait rattraper sans repartir de zéro
    (parties SQLite d'avant ces changements ; en Postgres les schémas naissent à jour,
    sauf pour la graine des saisons, la nationalité des joueurs, le tour des matchs
    internationaux, la longueur des codes de championnat et `ADDED_COLUMNS`)."""
    _add_season_seed(engine)
    _add_nationality(engine)
    _add_international_stage(engine)
    _add_columns(engine)
    _widen_league_codes(engine)
    if engine.dialect.name == "sqlite":
        _migrate_sqlite(engine)
    _rescale_potential(engine)
    _fill_potential(engine)


def _migrate_sqlite(engine: Engine) -> None:
    inspector = inspect(engine)
    if not inspector.has_table("players"):
        return
    if "lineup_choice" not in {column["name"] for column in inspector.get_columns("clubs")}:
        # Composition choisie par le manager, ajoutée après coup : le staff compose.
        with engine.begin() as connection:
            connection.execute(
                text("ALTER TABLE clubs ADD COLUMN lineup_choice JSON NOT NULL DEFAULT '[]'")
            )
    if "jerseys" not in {column["name"] for column in inspector.get_columns("clubs")}:
        # Maillots personnalisés, ajoutés après coup : chaque club garde ses couleurs.
        with engine.begin() as connection:
            connection.execute(
                text("ALTER TABLE clubs ADD COLUMN jerseys JSON NOT NULL DEFAULT '{}'")
            )
            connection.execute(
                text("ALTER TABLE clubs ADD COLUMN third_kit BOOLEAN NOT NULL DEFAULT 0")
            )
    if "sponsors" not in {column["name"] for column in inspector.get_columns("clubs")}:
        # Sponsors du maillot, ajoutés après coup : aucun contrat au départ.
        with engine.begin() as connection:
            connection.execute(
                text("ALTER TABLE clubs ADD COLUMN sponsors JSON NOT NULL DEFAULT '[]'")
            )
    columns = {column["name"] for column in inspector.get_columns("players")}
    if "photo" not in columns:
        # Photo des vrais joueurs, ajoutée après coup : les parties existantes n'en ont pas.
        with engine.begin() as connection:
            connection.execute(text("ALTER TABLE players ADD COLUMN photo VARCHAR(300)"))
    with sessionmaker(bind=engine)() as session:
        # Photos : les parties d'avant pointaient directement sur Wikimedia Commons ;
        # elles passent maintenant par l'API (voir api/routers/photos.py).
        legacy = session.scalars(
            select(PlayerRow).where(PlayerRow.photo.like("https://commons.wikimedia.org/%"))
        ).all()
        for row in legacy:
            name = row.photo.rsplit("/", 1)[-1].split("?", 1)[0]
            row.photo = PHOTO_PATH.format(name)
        if legacy:
            session.commit()
    if "stamina" not in columns:
        # Endurance ajoutée après coup : chaque joueur en tire une selon son poste
        # et son niveau, comme à la génération.
        with engine.begin() as connection:
            connection.execute(
                text("ALTER TABLE players ADD COLUMN stamina INTEGER NOT NULL DEFAULT 12")
            )
        rng = random.Random()
        with sessionmaker(bind=engine)() as session:
            for row in session.scalars(select(PlayerRow)):
                skills = (
                    row.pace + row.power + row.handling + row.passing
                    + row.kicking + row.tackling + row.scrum + row.lineout
                ) / 8  # fmt: skip
                offset = POSITION_PROFILES[Position(row.position)]["stamina"]
                value = round(rng.gauss(skills + offset, ATTRIBUTE_SPREAD))
                row.stamina = max(ATTRIBUTE_MIN, min(ATTRIBUTE_MAX, value))
            session.commit()


def seed_if_empty(
    session: Session,
    club_count: int = DEFAULT_CLUB_COUNT,
    seed: int | None = None,
    real: bool = True,
    leagues: list | None = None,
    rosters: dict | None = None,
) -> int:
    """Remplit la base si elle est vide : les vrais clubs des cinq championnats
    (avec leurs vrais joueurs quand data/rosters.json les connaît, voir
    data/generator.py), ou `club_count` clubs fictifs dans un seul championnat avec
    `real=False`, et un premier vivier d'agents libres.

    `leagues` et `rosters` remplacent data/leagues.py et data/rosters.json (clubs
    retouchés depuis le backoffice, voir catalog.py).

    Renvoie le nombre de clubs créés (0 si la base contenait déjà des clubs).
    """
    if session.scalar(select(func.count()).select_from(ClubRow)):
        return 0
    rng = random.Random(seed)
    released: list = []  # vrais joueurs en surnombre dans leur club : agents libres
    if real:
        clubs = generate_real_clubs(rng, leagues or LEAGUES, rosters, released)
    else:
        clubs = generate_clubs(club_count, rng)
    for player in (p for club in clubs for p in club.players + club.youths):
        ceiling(player)  # potentiel tiré d'après l'âge de départ (engine/development.py)
    session.add_all(ClubRow.from_domain(club) for club in clubs)
    # Staff disponible à l'embauche (3 candidats par poste), après ceux des clubs.
    first_id = sum(len(club.staff) for club in clubs) + 1
    candidates = generate_staff_candidates(3, rng, first_id=first_id)
    session.add_all(StaffRow.from_domain(member) for member in candidates)
    # Agents libres (joueurs sans club), après les joueurs des clubs.
    last_id = max((p.id for c in clubs for p in c.players + c.youths + released), default=0)
    player_ids = itertools.count(last_id + 1)
    free_agents = released + newcomers(released, player_ids, FIRST_SEASON_YEAR, rng)
    for player in free_agents:
        ceiling(player)
    session.add_all(PlayerRow.from_domain(player) for player in free_agents)
    session.commit()
    return len(clubs)
