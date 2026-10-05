"""Parties sauvegardées : une base SQLite par emplacement, création des tables et
remplissage initial.

Chaque partie vit dans son propre fichier (`saves/partie-1.db` à `partie-3.db`).
Toutes les routes travaillent sur la partie chargée ; chaque action est
enregistrée aussitôt dans son fichier : la partie se sauvegarde au fur et à
mesure. La partie chargée est retenue dans `saves/active`, pour la retrouver
après un redémarrage de l'API.
"""

import itertools
import os
import random
from collections.abc import Iterator
from pathlib import Path

from sqlalchemy import Engine, create_engine, func, inspect, select, text
from sqlalchemy.orm import Session, sessionmaker

from data.generator import (
    ATTRIBUTE_SPREAD,
    FIRST_SEASON_YEAR,
    POSITION_PROFILES,
    generate_clubs,
    generate_real_clubs,
    generate_staff_candidates,
)
from engine.free_agents import newcomers
from models import ATTRIBUTE_MAX, ATTRIBUTE_MIN, Position
from models.orm import Base, ClubRow, PlayerRow, StaffRow

# Dossier des parties (surchargeable, ex. pour une instance de test).
SAVES_DIR = Path(os.environ.get("RUGBY_SAVES_DIR", "./saves"))
SLOT_COUNT = 3

# Nombre de clubs inventés (un seul championnat) quand on ne prend pas les vrais clubs.
DEFAULT_CLUB_COUNT = 14

_engines: dict[int, Engine] = {}


class NoSaveLoaded(Exception):
    """Aucune partie chargée : il faut en choisir une (ou en commencer une)."""


class OutdatedSave(Exception):
    """Une partie à un ancien format, que le jeu ne sait plus ouvrir."""


def slot_path(slot: int) -> Path:
    if not 1 <= slot <= SLOT_COUNT:
        raise ValueError(f"Emplacement {slot} : il y en a {SLOT_COUNT}")
    return SAVES_DIR / f"partie-{slot}.db"


def slot_exists(slot: int) -> bool:
    return slot_path(slot).exists()


def engine_for(slot: int) -> Engine:
    """Connexion à la base d'une partie (créée au premier appel, puis réutilisée)."""
    if slot not in _engines:
        # check_same_thread=False : nécessaire pour utiliser SQLite depuis FastAPI
        # (plusieurs threads).
        _engines[slot] = create_engine(
            f"sqlite:///{slot_path(slot)}", connect_args={"check_same_thread": False}
        )
    return _engines[slot]


def session_for(slot: int) -> Session:
    return sessionmaker(bind=engine_for(slot), expire_on_commit=False)()


def active_slot() -> int | None:
    """La partie chargée (None si aucune, ou si son fichier a disparu)."""
    try:
        slot = int((SAVES_DIR / "active").read_text())
    except (OSError, ValueError):
        return None
    return slot if 1 <= slot <= SLOT_COUNT and slot_exists(slot) else None


def set_active_slot(slot: int | None) -> None:
    marker = SAVES_DIR / "active"
    if slot is None:
        marker.unlink(missing_ok=True)
        return
    SAVES_DIR.mkdir(parents=True, exist_ok=True)
    marker.write_text(str(slot))


def load_slot(slot: int) -> None:
    """Charge une partie existante (OutdatedSave si son format est trop ancien)."""
    init_db(engine_for(slot))
    set_active_slot(slot)


def new_slot(slot: int, seed: int | None = None) -> None:
    """Remplace l'emplacement par un monde neuf et le charge (la carrière reste à choisir)."""
    delete_slot(slot)
    SAVES_DIR.mkdir(parents=True, exist_ok=True)
    engine = engine_for(slot)
    init_db(engine)
    with session_for(slot) as session:
        seed_if_empty(session, seed=seed)
    set_active_slot(slot)


def delete_slot(slot: int) -> None:
    """Efface une partie (son fichier) ; elle n'est plus chargée."""
    path = slot_path(slot)
    engine = _engines.pop(slot, None)
    if engine is not None:
        engine.dispose()
    path.unlink(missing_ok=True)
    if active_slot() is None:
        set_active_slot(None)


def init_db(engine: Engine) -> None:
    """Crée les tables si elles n'existent pas encore, et vérifie leur schéma."""
    Base.metadata.create_all(engine)
    _migrate(engine)
    # Pas de migrations générales : create_all ajoute les tables manquantes mais
    # pas les colonnes. Hors des cas traités par `_migrate`, une partie à l'ancien
    # schéma ne s'ouvre plus : il faut la supprimer.
    inspector = inspect(engine)
    for table in Base.metadata.sorted_tables:
        actual = {column["name"] for column in inspector.get_columns(table.name)}
        expected = {column.name for column in table.columns}
        if not expected <= actual:
            raise OutdatedSave(
                f"Cette partie a un ancien format (table « {table.name} ») : "
                "supprime-la pour en commencer une nouvelle."
            )


def _migrate(engine: Engine) -> None:
    """Les quelques changements de schéma qu'on sait rattraper sans repartir de zéro."""
    inspector = inspect(engine)
    if not inspector.has_table("players"):
        return
    columns = {column["name"] for column in inspector.get_columns("players")}
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
) -> int:
    """Remplit la base si elle est vide : les vrais clubs des cinq championnats
    (joueurs inventés, voir data/leagues.py), ou `club_count` clubs fictifs dans un
    seul championnat avec `real=False`, et un premier vivier d'agents libres.

    Renvoie le nombre de clubs créés (0 si la base contenait déjà des clubs).
    """
    if session.scalar(select(func.count()).select_from(ClubRow)):
        return 0
    rng = random.Random(seed)
    clubs = generate_real_clubs(rng) if real else generate_clubs(club_count, rng)
    session.add_all(ClubRow.from_domain(club) for club in clubs)
    # Staff disponible à l'embauche (3 candidats par poste), après ceux des clubs.
    first_id = sum(len(club.staff) for club in clubs) + 1
    candidates = generate_staff_candidates(3, rng, first_id=first_id)
    session.add_all(StaffRow.from_domain(member) for member in candidates)
    # Agents libres (joueurs sans club), après les joueurs des clubs.
    player_ids = itertools.count(sum(len(c.players) + len(c.youths) for c in clubs) + 1)
    free_agents = newcomers([], player_ids, FIRST_SEASON_YEAR, rng)
    session.add_all(PlayerRow.from_domain(player) for player in free_agents)
    session.commit()
    return len(clubs)


def get_session() -> Iterator[Session]:
    """Fournit une session sur la partie chargée et la ferme après usage (dépendance
    FastAPI). NoSaveLoaded si aucune partie n'est chargée."""
    slot = active_slot()
    if slot is None:
        raise NoSaveLoaded
    with session_for(slot) as session:
        yield session
