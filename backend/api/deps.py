"""Dépendances partagées par les routes."""

from typing import Annotated

from fastapi import Depends, HTTPException
from sqlalchemy.orm import Session

from database import get_session
from models import Club
from models.orm import ClubRow

# Raccourci : `session: SessionDep` dans une route injecte une session SQLAlchemy.
SessionDep = Annotated[Session, Depends(get_session)]


def load_club(session: Session, club_id: int) -> Club:
    """Charge un club (et son effectif) en objet du domaine, ou renvoie une 404."""
    row = session.get(ClubRow, club_id)
    if row is None:
        raise HTTPException(status_code=404, detail=f"Club {club_id} introuvable")
    return row.to_domain()
