"""Carrière : le club que dirige le joueur, ou la sélection nationale.

Une seule carrière à la fois pour l'instant : en créer une remplace la précédente.
La première saison (et son calendrier) est tirée au démarrage de la carrière.
Un manager limogé (voir seasons.py) reprend un autre club dans le même monde.
Un sélectionneur (`SelectorRow`, voir selection.py) ne dirige aucun club : tous
sont alors menés par leur staff.
"""

from fastapi import APIRouter, HTTPException
from sqlalchemy import delete, select

from api import internationals
from api.deps import SessionDep, load_club
from api.ledger import current_season
from api.routers.seasons import FIRST_SEASON_YEAR, create_season
from api.schemas import CareerIn, CareerOut, DismissalOut
from data.leagues import league_config
from data.nations import NATIONS_BY_CODE
from models import Club
from models.orm import (
    CareerRow,
    DismissalRow,
    LiveInternationalRow,
    LiveMatchRow,
    SelectorRow,
)

# Ce que l'interface affiche à la place du championnat d'un club.
SELECTOR_LEAGUE = "internationals"
SELECTOR_LEAGUE_NAME = "Sélection nationale"

router = APIRouter(prefix="/career", tags=["carrière"])


def _career_out(row: CareerRow, club: Club) -> CareerOut:
    return CareerOut(
        id=row.id,
        manager_name=row.manager_name,
        club_id=club.id,
        club_name=club.name,
        league=club.league,
        league_name=league_config(club.league).name,
    )


def selector_out(row: SelectorRow) -> CareerOut:
    nation = NATIONS_BY_CODE[row.nation]
    return CareerOut(
        id=row.id,
        manager_name=row.manager_name,
        kind="nation",
        club_id=nation.id,
        club_name=nation.name,
        league=SELECTOR_LEAGUE,
        league_name=SELECTOR_LEAGUE_NAME,
        nation=nation.code,
    )


@router.post("", response_model=CareerOut, status_code=201)
def start_career(payload: CareerIn, session: SessionDep) -> CareerOut:
    """Démarre une carrière à la tête d'un club (`club_id`) ou d'une sélection (`nation`)."""
    if (payload.club_id is None) == (payload.nation is None):
        raise HTTPException(status_code=400, detail="Choisis un club ou une sélection")
    club = nation = None
    if payload.club_id is not None:
        club = load_club(session, payload.club_id)
    else:
        nation = NATIONS_BY_CODE.get(payload.nation.upper())
        selectable = {n.code for n in internationals.rules.selectable()}
        if nation is None or nation.code not in selectable:
            raise HTTPException(status_code=404, detail=f"Sélection « {payload.nation} » inconnue")
        if not internationals.has_nations(session):
            raise HTTPException(status_code=400, detail="Ce monde n'a pas de sélections nationales")
    for table in (CareerRow, SelectorRow, DismissalRow, LiveMatchRow, LiveInternationalRow):
        session.execute(delete(table))
    if club is not None:
        row = CareerRow(manager_name=payload.manager_name, club_id=club.id)
    else:
        row = SelectorRow(manager_name=payload.manager_name, nation=nation.code)
    session.add(row)
    session.commit()

    if current_season(session) is None:
        create_season(session, FIRST_SEASON_YEAR)

    return _career_out(row, club) if club is not None else selector_out(row)


@router.get("", response_model=CareerOut)
def get_career(session: SessionDep) -> CareerOut:
    """Carrière en cours (404 tant qu'aucune n'a été démarrée)."""
    row = session.scalars(select(CareerRow)).first()
    if row is not None:
        return _career_out(row, load_club(session, row.club_id))
    human = internationals.selector(session)
    if human is None:
        raise HTTPException(status_code=404, detail="Aucune carrière en cours")
    return selector_out(human)


@router.get("/dismissal", response_model=DismissalOut | None)
def get_last_dismissal(session: SessionDep) -> DismissalOut | None:
    """Le dernier limogeage, tant qu'aucune nouvelle carrière n'a commencé (sinon null)."""
    row = session.scalars(select(DismissalRow).order_by(DismissalRow.id.desc())).first()
    return DismissalOut.model_validate(row) if row else None
