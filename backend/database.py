"""Connexion SQLite et création des tables."""

from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from models.orm import Base

DATABASE_URL = "sqlite:///./rugby.db"

# check_same_thread=False : nécessaire pour utiliser SQLite depuis FastAPI (plusieurs threads).
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


def init_db() -> None:
    """Crée les tables si elles n'existent pas encore."""
    Base.metadata.create_all(engine)


def get_session() -> Iterator[Session]:
    """Fournit une session et la ferme après usage (servira de dépendance FastAPI)."""
    with SessionLocal() as session:
        yield session
