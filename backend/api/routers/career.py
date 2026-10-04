"""Carrière : le club que dirige le joueur.

Une seule carrière à la fois pour l'instant : en créer une remplace la précédente.
"""

from fastapi import APIRouter, HTTPException
from sqlalchemy import delete, select

from api.deps import SessionDep, load_club
from api.schemas import CareerIn, CareerOut
from models.orm import CareerRow

router = APIRouter(prefix="/career", tags=["carrière"])


@router.post("", response_model=CareerOut, status_code=201)
def start_career(payload: CareerIn, session: SessionDep) -> CareerOut:
    """Démarre une carrière à la tête d'un club."""
    club = load_club(session, payload.club_id)
    session.execute(delete(CareerRow))
    row = CareerRow(manager_name=payload.manager_name, club_id=club.id)
    session.add(row)
    session.commit()
    return CareerOut(id=row.id, manager_name=row.manager_name, club_id=club.id, club_name=club.name)


@router.get("", response_model=CareerOut)
def get_career(session: SessionDep) -> CareerOut:
    """Carrière en cours (404 tant qu'aucune n'a été démarrée)."""
    row = session.scalars(select(CareerRow)).first()
    if row is None:
        raise HTTPException(status_code=404, detail="Aucune carrière en cours")
    club = load_club(session, row.club_id)
    return CareerOut(id=row.id, manager_name=row.manager_name, club_id=club.id, club_name=club.name)
