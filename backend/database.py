"""Connexion SQLite, création des tables et remplissage initial."""

import os
import random
from collections.abc import Iterator

from sqlalchemy import create_engine, func, inspect, select
from sqlalchemy.orm import Session, sessionmaker

from data.generator import generate_clubs, generate_staff_candidates, generate_top14
from models.orm import Base, ClubRow, StaffRow

# Surchargeable par variable d'environnement (ex. une autre base pour essayer).
DATABASE_URL = os.environ.get("RUGBY_DATABASE_URL", "sqlite:///./rugby.db")

# Nombre de clubs inventés quand on ne prend pas les vrais clubs du Top 14.
DEFAULT_CLUB_COUNT = 14

# check_same_thread=False : nécessaire pour utiliser SQLite depuis FastAPI (plusieurs threads).
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


def init_db() -> None:
    """Crée les tables si elles n'existent pas encore, et vérifie leur schéma."""
    Base.metadata.create_all(engine)
    # Pas de migrations pour l'instant : create_all ajoute les tables manquantes
    # mais pas les colonnes. Une base à l'ancien schéma doit être supprimée (le
    # monde est régénéré au démarrage suivant).
    inspector = inspect(engine)
    for table in Base.metadata.sorted_tables:
        actual = {column["name"] for column in inspector.get_columns(table.name)}
        expected = {column.name for column in table.columns}
        if not expected <= actual:
            raise RuntimeError(
                f"La base de données a un ancien schéma (table « {table.name} ») : "
                "supprime le fichier rugby.db (dans backend/) puis relance l'API."
            )


def seed_if_empty(
    session: Session,
    club_count: int = DEFAULT_CLUB_COUNT,
    seed: int | None = None,
    top14: bool = True,
) -> int:
    """Remplit la base si elle est vide : les vrais clubs du Top 14 (joueurs
    inventés), ou `club_count` clubs fictifs avec `top14=False`.

    Renvoie le nombre de clubs créés (0 si la base contenait déjà des clubs).
    """
    if session.scalar(select(func.count()).select_from(ClubRow)):
        return 0
    rng = random.Random(seed)
    clubs = generate_top14(rng) if top14 else generate_clubs(club_count, rng)
    session.add_all(ClubRow.from_domain(club) for club in clubs)
    # Staff disponible à l'embauche (3 candidats par poste), après ceux des clubs.
    first_id = sum(len(club.staff) for club in clubs) + 1
    candidates = generate_staff_candidates(3, rng, first_id=first_id)
    session.add_all(StaffRow.from_domain(member) for member in candidates)
    session.commit()
    return len(clubs)


def get_session() -> Iterator[Session]:
    """Fournit une session et la ferme après usage (dépendance FastAPI)."""
    with SessionLocal() as session:
        yield session
