"""Carrière : le club que dirige le joueur.

Une seule carrière à la fois pour l'instant : en créer une remplace la précédente.
La première saison (et son calendrier) est tirée au démarrage de la carrière.
Un manager limogé (voir seasons.py) reprend un autre club dans le même monde.
"""

from fastapi import APIRouter, HTTPException
from sqlalchemy import delete, select

from api.deps import SessionDep, load_club
from api.ledger import current_season
from api.routers.seasons import FIRST_SEASON_YEAR, create_season
from api.schemas import CareerIn, CareerOut, DismissalOut
from models.orm import CareerRow, DismissalRow

router = APIRouter(prefix="/career", tags=["carrière"])


@router.post("", response_model=CareerOut, status_code=201)
def start_career(payload: CareerIn, session: SessionDep) -> CareerOut:
    """Démarre une carrière à la tête d'un club."""
    club = load_club(session, payload.club_id)
    session.execute(delete(CareerRow))
    session.execute(delete(DismissalRow))
    row = CareerRow(manager_name=payload.manager_name, club_id=club.id)
    session.add(row)
    session.commit()

    if current_season(session) is None:
        create_season(session, FIRST_SEASON_YEAR)

    return CareerOut(id=row.id, manager_name=row.manager_name, club_id=club.id, club_name=club.name)


@router.get("", response_model=CareerOut)
def get_career(session: SessionDep) -> CareerOut:
    """Carrière en cours (404 tant qu'aucune n'a été démarrée)."""
    row = session.scalars(select(CareerRow)).first()
    if row is None:
        raise HTTPException(status_code=404, detail="Aucune carrière en cours")
    club = load_club(session, row.club_id)
    return CareerOut(id=row.id, manager_name=row.manager_name, club_id=club.id, club_name=club.name)


@router.get("/dismissal", response_model=DismissalOut | None)
def get_last_dismissal(session: SessionDep) -> DismissalOut | None:
    """Le dernier limogeage, tant qu'aucune nouvelle carrière n'a commencé (sinon null)."""
    row = session.scalars(select(DismissalRow).order_by(DismissalRow.id.desc())).first()
    return DismissalOut.model_validate(row) if row else None
