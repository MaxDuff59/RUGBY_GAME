"""Carrière : le club que dirige le joueur, ou la sélection nationale.

Une seule carrière à la fois pour l'instant : en créer une remplace la précédente.
La première saison (et son calendrier) est tirée au démarrage de la carrière.
Un manager limogé (voir seasons.py) reprend un autre club dans le même monde.
Un sélectionneur (`SelectorRow`, voir selection.py) ne dirige aucun club : tous
sont alors menés par leur staff.
"""

from fastapi import APIRouter, HTTPException
from sqlalchemy import delete, select

from api import careers, internationals
from api.affairs import ignore_pending
from api.deps import SessionDep, load_club
from api.ledger import current_season, game_date
from api.routers.seasons import FIRST_SEASON_YEAR, create_season
from api.schemas import (
    CareerHistoryOut,
    CareerIn,
    CareerOut,
    ClubRef,
    DismissalOut,
    JobOfferOut,
    ManagerSeasonOut,
    SpellOut,
)
from data.leagues import league_config
from data.nations import NATIONS_BY_CODE
from engine import career as career_rules
from models import Club
from models.orm import (
    CareerRow,
    ClubRow,
    DismissalRow,
    LiveInternationalRow,
    LiveMatchRow,
    NegotiationRow,
    SelectorRow,
    SpellRow,
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
        difficulty=row.difficulty or "normal",
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
        row = CareerRow(
            manager_name=payload.manager_name,
            club_id=club.id,
            difficulty=payload.difficulty.value,
        )
    else:
        row = SelectorRow(manager_name=payload.manager_name, nation=nation.code)
    session.add(row)
    session.commit()

    if current_season(session) is None:
        create_season(session, FIRST_SEASON_YEAR)
    if club is not None:
        # Son passage dans le club commence aujourd'hui (engine/career.py).
        careers.open_spell(session, payload.manager_name, club.id, game_date(session))
        session.commit()

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


@router.get("/history", response_model=CareerHistoryOut)
def get_history(session: SessionDep) -> CareerHistoryOut:
    """Le parcours du manager : ses clubs, ses saisons, sa réputation ; et, une fois la
    saison de son championnat finie, les clubs qui veulent de lui."""
    row = session.scalars(select(CareerRow)).first()
    if row is None:
        raise HTTPException(status_code=404, detail="Aucune carrière de club en cours")
    clubs = {club.id: club for club in session.scalars(select(ClubRow))}
    spells = careers.spells(session, row.manager_name)
    seasons = careers.manager_seasons(session, spells)
    value = careers.manager_reputation(seasons, spells)

    def ref(club_id: int) -> ClubRef:
        return ClubRef(id=club_id, name=clubs[club_id].name)

    return CareerHistoryOut(
        manager_name=row.manager_name,
        reputation=value,
        label=career_rules.label(value),
        seasons=[
            ManagerSeasonOut(
                year=s.year,
                club=ref(s.club_id),
                rank=s.rank,
                expected=s.expected,
                playoffs=s.playoffs,
                champion=s.champion,
            )
            for s in reversed(seasons)
        ],
        spells=[
            SpellOut(club=ref(s.club_id), start=s.start, end=s.end, reason=s.reason) for s in spells
        ],
        offers=[
            JobOfferOut(
                club=ref(club_id),
                league=clubs[club_id].league,
                league_name=league_config(clubs[club_id].league).short_name,
                level=round(level, 1),
                balance=clubs[club_id].balance,
            )
            for club_id, level in careers.offers(session, value).items()
        ],
    )


@router.post("/offers/{club_id}", response_model=CareerOut)
def accept_offer(club_id: int, session: SessionDep) -> CareerOut:
    """Le manager accepte l'offre d'un club : il le prend dès maintenant, la saison
    prochaine se jouera avec lui. Ses négociations en cours tombent, et les affaires
    de son ancien club sont réglées par le staff."""
    row = session.scalars(select(CareerRow)).first()
    if row is None:
        raise HTTPException(status_code=404, detail="Aucune carrière de club en cours")
    if club_id not in careers.offers(session):
        raise HTTPException(status_code=400, detail="Ce club ne t'a pas fait d'offre")
    ignore_pending(session)
    for negotiation in session.scalars(
        select(NegotiationRow).where(
            NegotiationRow.club_id == row.club_id, NegotiationRow.stage.in_(("club", "player"))
        )
    ):
        negotiation.stage = "failed"
        negotiation.closed_by = "me"
        negotiation.message = "Négociation interrompue : le manager est parti dans un autre club."
    day = game_date(session)
    careers.close_spell(session, row.manager_name, day, "left")
    session.add(SpellRow(manager_name=row.manager_name, club_id=club_id, start=day))
    row.club_id = club_id
    session.execute(delete(LiveMatchRow))
    session.commit()
    return _career_out(row, load_club(session, club_id))


@router.get("/dismissal", response_model=DismissalOut | None)
def get_last_dismissal(session: SessionDep) -> DismissalOut | None:
    """Le dernier limogeage, tant qu'aucune nouvelle carrière n'a commencé (sinon null)."""
    row = session.scalars(select(DismissalRow).order_by(DismissalRow.id.desc())).first()
    return DismissalOut.model_validate(row) if row else None
