"""Carrière : le club que dirige le joueur, ou la sélection nationale.

Une seule carrière à la fois pour l'instant : en créer une remplace la précédente.
La première saison (et son calendrier) est tirée au démarrage de la carrière.
Un manager limogé (voir seasons.py), ou parti de lui-même, reprend un autre club
dans le même monde : un club à sa portée (engine/career.py).
Un sélectionneur (`SelectorRow`, voir selection.py) ne dirige aucun club : tous
sont alors menés par leur staff.

Le manager d'un club est sous contrat (engine/manager_contract.py) : deux saisons
pour commencer ; il demande à le prolonger, part de lui-même, ou accepte l'offre
d'un autre club ou d'une sélection.

Un manager qui prend un club une fois la saison de son championnat finie arrive au
début de la suivante : l'intersaison se joue aussitôt, réglée par le staff du club
(contrats, espoirs, mercato), sans repasser par le bilan d'une saison qu'il n'a pas
menée, ni par les offres qui l'accompagnent.
"""

from fastapi import APIRouter, HTTPException
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from api import careers, internationals, plans
from api.auth import UserDep
from api.deps import SessionDep, load_club
from api.ledger import current_season, game_date
from api.routers.seasons import FIRST_SEASON_YEAR, create_season, offseason
from api.schemas import (
    CareerHistoryOut,
    CareerIn,
    CareerOut,
    ClubRef,
    DismissalOut,
    ExtensionIn,
    ExtensionOut,
    JobOfferOut,
    ManagerContractOut,
    ManagerSeasonOut,
    SpellOut,
)
from data.leagues import league_config
from data.nations import NATIONS_BY_CODE
from engine import career as career_rules
from engine import manager_contract as terms
from models import Club
from models.orm import (
    CareerRow,
    ClubRow,
    DismissalRow,
    LiveInternationalRow,
    LiveMatchRow,
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
        contract_until=row.contract_until,
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
def start_career(payload: CareerIn, session: SessionDep, user: UserDep) -> CareerOut:
    """Démarre une carrière à la tête d'un club (`club_id`) ou d'une sélection (`nation`).

    Dans un monde neuf, elle ouvre la première saison, qui compte dans celles du
    compte (api/plans.py) ; reprendre un club dans le même monde n'en ouvre pas, sauf
    une fois la saison de son championnat finie : il arrive pour la suivante."""
    if (payload.club_id is None) == (payload.nation is None):
        raise HTTPException(status_code=400, detail="Choisis un club ou une sélection")
    season = current_season(session)
    first_season = season is None
    if first_season:
        plans.require_season(user)
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
    takeover = False
    if club is not None:
        # Un manager parti sans autre club ne reprend qu'un club à sa portée.
        reachable = careers.reachable(session, payload.manager_name)
        if reachable is not None and club.id not in reachable:
            raise HTTPException(
                status_code=400, detail=f"{club.name} est hors de ta portée pour l'instant"
            )
        takeover = not first_season and careers.league_over(season, club.league)
        if takeover:
            plans.require_season(user)
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

    if first_season:
        create_season(session, FIRST_SEASON_YEAR)
        plans.count_season(user)
    if club is not None:
        # Son passage dans le club commence aujourd'hui (engine/career.py), pour deux
        # saisons (engine/manager_contract.py).
        careers.open_spell(session, payload.manager_name, club.id, game_date(session))
        session.commit()
        if takeover:
            offseason(session, user, season, None)
        careers.sign(session, row, terms.FIRST_CONTRACT)
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


def _club_career_or_404(session: Session) -> CareerRow:
    row = session.scalars(select(CareerRow)).first()
    if row is None:
        raise HTTPException(status_code=404, detail="Aucune carrière de club en cours")
    return row


@router.get("/history", response_model=CareerHistoryOut)
def get_history(session: SessionDep) -> CareerHistoryOut:
    """Le parcours du manager : ses clubs, ses saisons, sa réputation, son contrat ; et,
    une fois la saison de son championnat finie, les clubs (et la sélection) qui
    veulent de lui."""
    row = _club_career_or_404(session)
    clubs = {club.id: club for club in session.scalars(select(ClubRow))}
    spells = careers.spells(session, row.manager_name)
    seasons = careers.manager_seasons(session, spells)
    value = careers.manager_reputation(seasons, spells)
    contract = careers.contract(session, row)
    length = terms.offer_length(value)

    def ref(club_id: int) -> ClubRef:
        return ClubRef(id=club_id, name=clubs[club_id].name)

    offers = []
    if careers.season_over(session):
        market = careers.market(session)
        offers = [
            JobOfferOut(
                club=ref(club_id),
                league=clubs[club_id].league,
                league_name=league_config(clubs[club_id].league).short_name,
                level=round(level, 1),
                balance=clubs[club_id].balance,
                seasons=length,
                indemnity=contract.indemnity,
            )
            for club_id, level in careers.offers(session, value, market).items()
        ]
        nation = careers.nation_offer(session, value, market)
        if nation is not None:
            code, level = nation
            offers.append(
                JobOfferOut(
                    kind="nation",
                    club=ClubRef(id=NATIONS_BY_CODE[code].id, name=NATIONS_BY_CODE[code].name),
                    nation=code,
                    league=SELECTOR_LEAGUE,
                    league_name=SELECTOR_LEAGUE_NAME,
                    level=round(level, 1),
                    balance=None,
                    seasons=None,
                    indemnity=contract.indemnity,
                )
            )

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
        offers=offers,
        contract_until=contract.until,
    )


@router.post("/offers/{club_id}", response_model=CareerOut)
def accept_offer(club_id: int, session: SessionDep, user: UserDep) -> CareerOut:
    """Le manager accepte l'offre d'un club : il le prend dès maintenant, et arrive au
    début de la saison prochaine, l'intersaison réglée par le staff. Ses négociations
    en cours tombent, et les affaires de son ancien club sont réglées par le staff.
    Encore sous contrat, il coûte à son nouveau club une indemnité, versée à l'ancien.
    La saison qui s'ouvre compte dans celles du compte (api/plans.py)."""
    row = _club_career_or_404(session)
    if club_id not in careers.offers(session):
        raise HTTPException(status_code=400, detail="Ce club ne t'a pas fait d'offre")
    plans.require_season(user)
    season = current_season(session)
    left = careers.contract(session, row).left
    seasons = terms.offer_length(careers.reputation_of(session, row.manager_name))
    old_club = session.get(ClubRow, row.club_id)
    careers.leave_club(
        session, row, "left", "Négociation interrompue : le manager est parti dans un autre club."
    )
    careers.pay_indemnity(session, old_club, left, session.get(ClubRow, club_id), row.manager_name)
    session.add(SpellRow(manager_name=row.manager_name, club_id=club_id, start=game_date(session)))
    row.club_id = club_id
    session.commit()
    offseason(session, user, season, None)
    careers.sign(session, row, seasons)
    session.commit()
    return _career_out(row, load_club(session, club_id))


@router.post("/offers/nation/{code}", response_model=CareerOut)
def accept_nation_offer(code: str, session: SessionDep) -> CareerOut:
    """Le manager accepte l'offre d'une sélection : il quitte son club (la fédération
    verse l'indemnité s'il était encore sous contrat) et devient sélectionneur."""
    row = _club_career_or_404(session)
    offer = careers.nation_offer(session)
    if offer is None or offer[0] != code.upper():
        raise HTTPException(status_code=400, detail="Cette sélection ne t'a pas fait d'offre")
    left = careers.contract(session, row).left
    old_club = session.get(ClubRow, row.club_id)
    careers.leave_club(
        session, row, "nation", "Négociation interrompue : le manager est parti en sélection."
    )
    careers.pay_indemnity(session, old_club, left, None, row.manager_name)
    selector = SelectorRow(manager_name=row.manager_name, nation=offer[0])
    session.delete(row)
    session.execute(delete(DismissalRow))
    session.add(selector)
    session.commit()
    return selector_out(selector)


def _contract_out(session: Session, row: CareerRow) -> ManagerContractOut:
    contract = careers.contract(session, row)
    return ManagerContractOut(
        club=ClubRef(id=row.club_id, name=session.get(ClubRow, row.club_id).name),
        until=contract.until,
        seasons_left=contract.left,
        expiring=contract.expiring,
        board=round(contract.board, 1),
        supporters=round(contract.supporters, 1),
        renewal=contract.granted if contract.expiring else None,
        max_ask=contract.max_ask,
        blocked=contract.blocked,
        matches_needed=contract.matches_needed,
        retry_on=contract.retry_on,
        indemnity=contract.indemnity,
        resign_cost=0.0 if contract.expiring else -career_rules.PER_RESIGNATION,
    )


@router.get("/contract", response_model=ManagerContractOut)
def get_contract(session: SessionDep) -> ManagerContractOut:
    """Le contrat du manager : son échéance, ce qu'en pense la direction, et en fin de
    contrat ce qu'elle propose."""
    return _contract_out(session, _club_career_or_404(session))


@router.post("/contract/extend", response_model=ExtensionOut)
def extend_contract(payload: ExtensionIn, session: SessionDep) -> ExtensionOut:
    """Demande à la direction de prolonger le contrat de `seasons` saisons : elle
    accepte, propose moins, ou refuse (engine/manager_contract.py)."""
    row = _club_career_or_404(session)
    contract = careers.contract(session, row)
    if contract.blocked is not None:
        raise HTTPException(status_code=400, detail=BLOCKED[contract.blocked])
    if payload.seasons > contract.max_ask:
        raise HTTPException(
            status_code=400,
            detail=f"Pas plus de {contract.max_ask} saison(s) de plus : contrat trop long",
        )
    reply = careers.extend(session, row, payload.seasons)
    return ExtensionOut(
        outcome=reply.outcome, seasons=reply.seasons, contract=_contract_out(session, row)
    )


# Pourquoi la direction n'entend pas de demande de prolongation (`Contract.blocked`).
BLOCKED = {
    "too_long": "Ton contrat court déjà sur le plus de saisons possible",
    "too_soon": "La direction veut d'abord te voir à l'œuvre",
    "refused": "La direction t'a déjà dit non : reviens à la charge plus tard",
}


@router.post("/leave", response_model=DismissalOut)
def leave_club(session: SessionDep) -> DismissalOut:
    """Le manager quitte son club sans autre club où aller : de lui-même (sa réputation
    en pâtit) ou au bout de son contrat. Il choisira ensuite un club à sa portée."""
    row = _club_career_or_404(session)
    departure = careers.go_free(session, row)
    return _departure_out(session, departure)


def _departure_out(session: Session, row: DismissalRow) -> DismissalOut:
    out = DismissalOut.model_validate(row)
    out.reachable = careers.reachable(session, row.manager_name)
    return out


@router.get("/dismissal", response_model=DismissalOut | None)
def get_last_dismissal(session: SessionDep) -> DismissalOut | None:
    """Le dernier départ (limogé, parti, contrat échu), tant qu'aucune nouvelle carrière
    n'a commencé (sinon null), et les clubs que le manager peut reprendre."""
    row = session.scalars(select(DismissalRow).order_by(DismissalRow.id.desc())).first()
    return _departure_out(session, row) if row else None
