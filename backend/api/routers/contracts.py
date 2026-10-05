"""Contrats du club dirigé : fins de contrat, prolongations, signatures des concurrents.

Règles : engine/contracts.py. En dernière année de contrat, un joueur peut être
prolongé ; sinon il part libre à l'intersaison. Pendant la phase retour, un
concurrent peut le signer : c'est un pré-contrat à son nom (`NegotiationRow`,
étape `agreed`), qui s'exécute à l'intersaison comme ceux du manager. Une
prolongation laisse une trace (`kind="extension"`, étape `done`) pour que le
bilan de fin de saison la montre.

Les clubs IA, eux, prolongent la plupart de leurs joueurs en fin de contrat ;
ceux qui partent, comme ceux du club dirigé non prolongés, deviennent agents libres.
"""

import datetime
import random
from collections import Counter

from fastapi import APIRouter, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from api.deps import SessionDep, load_my_club_row
from api.free_agents import release
from api.jokers import joker_ids
from api.ledger import current_season, game_date
from api.schemas import ClubRef, ContractOut, ContractsOverview, ExtendIn, PlayerOut
from engine.contracts import (
    leaves_academy_next_season,
    pick_suitor,
    poach_chance,
    renewal_wage,
    renewal_years,
    retires_next_season,
)
from engine.economy import SQUAD_MAX, SQUAD_MIN
from engine.free_agents import ai_releases
from engine.transfers import DealKind, playing_time, time_label
from models import Club, Player, Squad
from models.orm import CareerRow, ClubRow, NegotiationRow, PlayerRow, SeasonRow

router = APIRouter(prefix="/contracts", tags=["contrats"])

EXTENSION = "extension"

# Un club IA prolonge son joueur en fin de contrat d'une à trois saisons ; un
# joueur que le manager laisse partir signe aussi pour une à trois saisons.
AI_RENEWAL_YEARS = (1, 3)


def _season_or_404(session: Session) -> SeasonRow:
    season = current_season(session)
    if season is None:
        raise HTTPException(status_code=404, detail="Aucune saison : commence une carrière")
    return season


def _signed_elsewhere(session: Session, club_id: int) -> dict[int, NegotiationRow]:
    """Pré-contrats signés par des concurrents avec des joueurs du club, par joueur."""
    rows = session.scalars(
        select(NegotiationRow)
        .join(PlayerRow, NegotiationRow.player_id == PlayerRow.id)
        .where(
            NegotiationRow.stage == "agreed",
            NegotiationRow.club_id != club_id,
            PlayerRow.club_id == club_id,
        )
    )
    return {row.player_id: row for row in rows}


def _extensions(session: Session, club_id: int, season: SeasonRow) -> dict[int, NegotiationRow]:
    """Prolongations accordées par le club depuis le début de la saison, par joueur."""
    start = min(m.date for m in season.matches)
    rows = session.scalars(
        select(NegotiationRow).where(
            NegotiationRow.club_id == club_id,
            NegotiationRow.kind == EXTENSION,
            NegotiationRow.opened_on >= start,
        )
    )
    return {row.player_id: row for row in rows}


def _incoming(session: Session, club_id: int) -> int:
    """Joueurs qui arrivent au club à l'intersaison (pré-contrats signés)."""
    return session.scalar(
        select(func.count())
        .select_from(NegotiationRow)
        .where(NegotiationRow.club_id == club_id, NegotiationRow.stage == "agreed")
    )


def _situation(
    player: Player,
    club: Club,
    year: int,
    signed: dict[int, NegotiationRow],
    extended: dict[int, NegotiationRow],
    day: datetime.date,
    names: dict[int, str],
) -> ContractOut | None:
    """Ce qui attend le joueur à l'intersaison, ou None s'il est sous contrat et reste."""
    common = {
        "player": PlayerOut.from_player(player, day, names),
        "playing_time": (
            "espoir" if player.squad == Squad.YOUTH else time_label(playing_time(player, club))
        ),
    }

    def signed_with(row: NegotiationRow, status: str) -> ContractOut:
        return ContractOut(
            status=status,
            new_club=ClubRef(id=row.club_id, name=names[row.club_id]),
            new_wage=row.wage,
            new_years=row.years,
            signed_on=row.opened_on,
            **common,
        )

    if player.id in signed:
        return signed_with(signed[player.id], "signed_elsewhere")
    if retires_next_season(player):
        return ContractOut(status="retiring", **common)
    if leaves_academy_next_season(player):
        return ContractOut(status="leaving_academy", **common)
    if player.id in extended:
        return signed_with(extended[player.id], "extended")
    if player.contract_until <= year:
        low, high = renewal_years(player)
        return ContractOut(
            status="open",
            wage_demand=renewal_wage(player, club),
            years_min=low,
            years_max=high,
            **common,
        )
    return None


def contracts_overview(session: Session, me: ClubRow) -> ContractsOverview:
    session.expire_all()
    season = _season_or_404(session)
    year = season.year
    day = game_date(session)
    club = me.to_domain()
    names = {row.id: row.name for row in session.scalars(select(ClubRow))}
    signed = _signed_elsewhere(session, me.id)
    extended = _extensions(session, me.id, season)

    jokers = joker_ids(session, me.id)
    pros, youths = [], []
    for player in [*club.players, *club.youths]:
        if player.loaned_from is not None or player.id in jokers:
            continue  # contrat de son club propriétaire, ou pige d'un joker médical
        out = _situation(player, club, year, signed, extended, day, names)
        if out is not None:
            (youths if player.squad == Squad.YOUTH else pros).append(out)
    by_value = lambda out: out.player.value  # noqa: E731
    pros.sort(key=by_value, reverse=True)
    youths.sort(key=by_value, reverse=True)

    staying = [
        p
        for p in club.players
        if p.loaned_from is None
        and p.contract_until > year
        and p.id not in signed
        and not retires_next_season(p)
    ]
    return ContractsOverview(
        season_year=year,
        pros=pros,
        youths=youths,
        squad_next=len(staying) + _incoming(session, me.id),
        squad_min=SQUAD_MIN,
        squad_max=SQUAD_MAX,
    )


# --- Routes --------------------------------------------------------------------------


@router.get("", response_model=ContractsOverview)
def get_contracts(session: SessionDep) -> ContractsOverview:
    """Joueurs en fin de contrat (pros et espoirs), départs et prolongations de la saison."""
    return contracts_overview(session, load_my_club_row(session))


@router.post("/{player_id}/extend", response_model=ContractsOverview)
def extend(player_id: int, payload: ExtendIn, session: SessionDep) -> ContractsOverview:
    """Prolonge un joueur en dernière année de contrat, au salaire qu'il demande.

    Le nouveau salaire s'applique aussitôt ; les saisons s'ajoutent à la fin du contrat.
    """
    me = load_my_club_row(session)
    year = _season_or_404(session).year
    row = session.get(PlayerRow, player_id)
    if row is None or row.club_id != me.id or row.loaned_from is not None:
        raise HTTPException(status_code=404, detail="Ce joueur n'est pas sous contrat chez toi")
    club = me.to_domain()
    player = next(p for p in [*club.players, *club.youths] if p.id == player_id)

    if player_id in joker_ids(session, me.id):
        raise HTTPException(
            status_code=400,
            detail="Joker médical : tu pourras lui proposer un contrat à la fin de sa pige",
        )
    signed = _signed_elsewhere(session, me.id).get(player_id)
    if signed is not None:
        rival = session.get(ClubRow, signed.club_id)
        raise HTTPException(
            status_code=400, detail=f"{player.name} s'est déjà engagé avec {rival.name}"
        )
    if retires_next_season(player):
        raise HTTPException(status_code=400, detail=f"{player.name} raccroche en fin de saison")
    if leaves_academy_next_season(player):
        raise HTTPException(
            status_code=400, detail="Trop âgé pour rester au centre : fais-le passer pro"
        )
    if player.contract_until > year:
        raise HTTPException(
            status_code=400,
            detail=f"Déjà sous contrat jusqu'en {player.contract_until + 1}",
        )
    low, high = renewal_years(player)
    if not low <= payload.years <= high:
        seasons = f"{low} à {high} saisons" if high > low else f"{low} saison"
        raise HTTPException(status_code=400, detail=f"{player.name} veut un contrat de {seasons}")

    wage = renewal_wage(player, club)
    row.wage = wage
    row.contract_until = year + payload.years
    session.add(
        NegotiationRow(
            club_id=me.id,
            player_id=player_id,
            kind=EXTENSION,
            stage="done",
            opened_on=game_date(session),
            patience=0,
            last_offer=None,
            fee_demand=None,
            fee_floor=None,
            fee=None,
            wage_demand=wage,
            wage_floor=None,
            wage=wage,
            years=payload.years,
            message=f"{player.name} prolonge de {payload.years} saison(s).",
        )
    )
    session.commit()
    return contracts_overview(session, me)


# --- Au fil de la saison et à l'intersaison ----------------------------------------------


def rival_signings(
    session: Session, season: SeasonRow, day: datetime.date, rng: random.Random
) -> list[ContractOut]:
    """Après une journée de la phase retour : des concurrents signent des joueurs du
    club dirigé en dernière année de contrat. Renvoie les signatures du jour."""
    career = session.scalars(select(CareerRow)).first()
    if career is None:
        return []
    club_rows = list(session.scalars(select(ClubRow)))
    names = {row.id: row.name for row in club_rows}
    me = next(row for row in club_rows if row.id == career.club_id).to_domain()
    rivals = [row.to_domain() for row in club_rows if row.id != me.id]
    signed = _signed_elsewhere(session, me.id)
    jokers = joker_ids(session, me.id)
    # Place chez chaque concurrent, en comptant les joueurs qui doivent déjà le rejoindre.
    incoming = Counter(
        session.scalars(select(NegotiationRow.club_id).where(NegotiationRow.stage == "agreed"))
    )

    signings = []
    for player in [*me.players, *me.youths]:
        if (
            player.loaned_from is not None
            or player.id in jokers
            or player.contract_until != season.year
            or player.id in signed
            or retires_next_season(player)
            or leaves_academy_next_season(player)
            or rng.random() >= poach_chance(player, me)
        ):
            continue
        room = [
            club
            for club in rivals
            if player.squad == Squad.YOUTH or len(club.players) + incoming[club.id] < SQUAD_MAX
        ]
        suitor = pick_suitor(player, me, room, rng)
        if suitor is None:
            continue
        rival, wage = suitor
        years = rng.randint(*renewal_years(player))
        row = NegotiationRow(
            club_id=rival.id,
            player_id=player.id,
            kind=DealKind.PRECONTRACT.value,
            stage="agreed",
            opened_on=day,
            patience=0,
            last_offer=None,
            fee_demand=None,
            fee_floor=None,
            fee=None,
            wage_demand=wage,
            wage_floor=None,
            wage=wage,
            years=years,
            message=f"{player.name} s'engage avec {rival.name} pour {years} saison(s).",
        )
        session.add(row)
        incoming[rival.id] += 1
        signings.append(
            ContractOut(
                player=PlayerOut.from_player(player, day, names),
                status="signed_elsewhere",
                playing_time="espoir"
                if player.squad == Squad.YOUTH
                else time_label(playing_time(player, me)),
                new_club=ClubRef(id=rival.id, name=rival.name),
                new_wage=wage,
                new_years=years,
                signed_on=day,
            )
        )
    session.commit()
    return signings


def expire_contracts(
    session: Session, year: int, my_club_id: int | None, rng: random.Random
) -> None:
    """Intersaison (après les pré-contrats) : contrats arrivés à terme avant `year`.

    Les clubs IA prolongent la plupart de leurs joueurs et laissent partir les
    autres. Ceux du club dirigé qui n'ont pas été prolongés partent : tous
    deviennent agents libres (un espoir sort du centre en pro).
    """
    pros_by_club = Counter(
        session.scalars(select(PlayerRow.club_id).where(PlayerRow.squad == Squad.PRO.value))
    )
    expired = session.scalars(
        select(PlayerRow).where(PlayerRow.contract_until < year, PlayerRow.club_id.is_not(None))
    )
    for row in expired:
        mine = row.club_id == my_club_id
        is_pro = row.squad == Squad.PRO.value
        if not mine and not (
            is_pro and ai_releases(row.to_domain(), pros_by_club[row.club_id], rng)
        ):
            row.contract_until = year + rng.randint(*AI_RENEWAL_YEARS) - 1
            continue
        if is_pro:
            pros_by_club[row.club_id] -= 1
        release(row, year)
