"""Le mode compétition (api/competition.py) : choisir sa compétition, puis son équipe.

Dans un emplacement neuf, `POST /competition` choisit la Coupe d'Europe ou la Coupe du
monde et tire la saison (les qualifiés de la Coupe d'Europe en dépendent) ; puis
`POST /competition/team` prend un des participants, comme une carrière de club ou de
sélectionneur. `GET /competition` dit où en est l'équipe : en course, ou la partie
finie (titre ou élimination).
"""

import datetime

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select

from api import competition, cup, internationals, plans
from api.auth import UserDep
from api.deps import SessionDep
from api.ledger import current_season
from api.routers.career import selector_out, start_career
from api.routers.seasons import FIRST_SEASON_YEAR, create_season, next_fixture
from api.schemas import CareerIn, CareerOut, ClubRef
from data.nations import NATIONS_BY_ID
from engine.difficulty import Difficulty
from models.orm import CareerRow, CompetitionRow, SelectorRow

router = APIRouter(prefix="/competition", tags=["compétition"])


class CompetitionIn(BaseModel):
    code: str


class CompetitionTeamIn(BaseModel):
    manager_name: str = Field(min_length=1, max_length=100)
    team_id: int
    difficulty: Difficulty = Difficulty.NORMAL  # pour un club (engine/difficulty.py)


class CompetitionOut(BaseModel):
    code: str
    name: str
    teams: list[ClubRef]  # les participants, au choix tant que l'équipe n'est pas prise
    team: ClubRef | None
    over: bool
    result: str | None  # « Vainqueur », « Quart de finaliste »... une fois finie
    champion: ClubRef | None
    next_date: datetime.date | None
    # Coupe d'Europe : le prochain match du club est-il celui de la coupe ? Sinon,
    # l'interface enchaîne les journées de championnat d'ici là. (Une sélection a son
    # propre bouton pour aller au prochain rendez-vous, page Sélection.)
    ready: bool


def _out(session) -> CompetitionOut:
    season = current_season(session)
    found = competition.status(session, season)
    if found is None:
        raise HTTPException(status_code=404, detail="Cette partie n'est pas une compétition")
    teams = competition.participants(session, season, found.code) if season else []

    def ref(team_id: int | None) -> ClubRef | None:
        if team_id is None:
            return None
        return ClubRef(id=team_id, name=competition.team_name(session, team_id))

    return CompetitionOut(
        code=found.code,
        name=competition.NAMES[found.code],
        teams=[ClubRef(id=team_id, name=name) for team_id, name in teams],
        team=ref(found.team_id),
        over=found.over,
        result=found.result,
        champion=ref(found.champion_id),
        next_date=found.next_date,
        ready=_ready(session, season, found),
    )


def _ready(session, season, found: competition.Status) -> bool:
    if season is None or found.team_id is None or found.over:
        return False
    if found.code != competition.CHAMPIONS_CUP:
        return False
    fixture = next_fixture(session, season)
    return fixture is not None and fixture.squad == cup.CUP_SQUAD and fixture.league == found.code


@router.get("", response_model=CompetitionOut)
def get_competition(session: SessionDep) -> CompetitionOut:
    """La compétition de la partie et où en est l'équipe (404 : une carrière ordinaire)."""
    return _out(session)


@router.post("", response_model=CompetitionOut, status_code=201)
def choose_competition(
    payload: CompetitionIn, session: SessionDep, user: UserDep
) -> CompetitionOut:
    """Fait d'un monde neuf une partie en mode compétition et tire sa saison : elle
    compte dans celles du compte (api/plans.py)."""
    if payload.code not in competition.NAMES:
        raise HTTPException(status_code=404, detail=f"Compétition « {payload.code} » inconnue")
    started = current_season(session) is not None or any(
        session.scalars(select(table)).first() is not None
        for table in (CareerRow, SelectorRow, CompetitionRow)
    )
    if started:
        raise HTTPException(status_code=409, detail="Cette partie est déjà commencée")
    if payload.code == competition.CHAMPIONS_CUP and not cup.has_cup(session):
        raise HTTPException(status_code=400, detail="Ce monde n'a pas de Coupe d'Europe")
    if payload.code == competition.WORLD_CUP and not internationals.has_nations(session):
        raise HTTPException(status_code=400, detail="Ce monde n'a pas de sélections nationales")
    plans.require_season(user)
    session.add(CompetitionRow(code=payload.code))
    session.commit()
    create_season(session, FIRST_SEASON_YEAR)
    plans.count_season(user)
    return _out(session)


@router.post("/team", response_model=CareerOut, status_code=201)
def choose_team(payload: CompetitionTeamIn, session: SessionDep, user: UserDep) -> CareerOut:
    """Prend une équipe de la compétition : un club qualifié pour la Coupe d'Europe,
    ou une des seize nations de la Coupe du monde (invitées comprises)."""
    found = _out(session)
    if found.team is not None:
        raise HTTPException(status_code=409, detail=f"Tu diriges déjà {found.team.name}")
    if payload.team_id not in {team.id for team in found.teams}:
        raise HTTPException(status_code=400, detail=f"Cette équipe ne joue pas la {found.name}")
    if found.code == competition.CHAMPIONS_CUP:
        return start_career(
            CareerIn(
                manager_name=payload.manager_name,
                club_id=payload.team_id,
                difficulty=payload.difficulty,
            ),
            session,
            user,
        )
    row = SelectorRow(manager_name=payload.manager_name, nation=NATIONS_BY_ID[payload.team_id].code)
    session.add(row)
    session.commit()
    return selector_out(row)
