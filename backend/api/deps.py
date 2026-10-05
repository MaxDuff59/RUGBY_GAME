"""Dépendances partagées par les routes."""

from collections.abc import Iterable
from typing import Annotated

from fastapi import Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from database import get_session
from models import Club
from models.orm import CareerRow, ClubRow, PlayerRow

# Raccourci : `session: SessionDep` dans une route injecte une session SQLAlchemy.
SessionDep = Annotated[Session, Depends(get_session)]


def load_club(session: Session, club_id: int) -> Club:
    """Charge un club (et son effectif) en objet du domaine, ou renvoie une 404."""
    row = session.get(ClubRow, club_id)
    if row is None:
        raise HTTPException(status_code=404, detail=f"Club {club_id} introuvable")
    return row.to_domain()


def load_clubs(session: Session, club_ids: Iterable[int]) -> dict[int, Club]:
    """Charge des clubs en objets du domaine, effectifs, blessures et staff en une fois
    (sans une requête par joueur)."""
    rows = session.scalars(
        select(ClubRow)
        .where(ClubRow.id.in_(list(club_ids)))
        .options(
            selectinload(ClubRow.players).selectinload(PlayerRow.injuries),
            selectinload(ClubRow.youths).selectinload(PlayerRow.injuries),
            selectinload(ClubRow.staff),
        )
    )
    return {row.id: row.to_domain() for row in rows}


def load_my_club_row(session: Session) -> ClubRow:
    """Ligne du club dirigé par le joueur (404 sans carrière en cours).

    On renvoie la ligne SQLAlchemy, pas l'objet du domaine : les routes de
    gestion (staff, transferts...) modifient directement la base.
    """
    career = session.scalars(select(CareerRow)).first()
    if career is None:
        raise HTTPException(status_code=404, detail="Aucune carrière en cours")
    return session.get(ClubRow, career.club_id)
