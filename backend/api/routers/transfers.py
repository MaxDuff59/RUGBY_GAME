"""Recrutement du club dirigé : approche, négociation, prêts, pré-contrats, ventes.

Trois voies pour recruter un joueur d'un autre club (règles : engine/transfers.py) :

- transfert en cours de contrat : on convient d'abord de l'indemnité avec le
  club, puis du salaire avec le joueur ; il arrive aussitôt ;
- pré-contrat : en dernière année de contrat, le joueur négocie librement son
  salaire ; il arrive à l'intersaison ;
- prêt : le club prête ses non-titulaires jusqu'à la fin de la saison, le
  joueur accepte s'il y gagne du temps de jeu ; son salaire est à ta charge.

Chaque offre refusée rapproche un peu l'autre partie de ton prix si l'offre
était sérieuse ; au bout de quelques refus, elle quitte la table.
"""

from fastapi import APIRouter, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from api.deps import SessionDep, load_my_club_row
from api.ledger import current_season, game_date, record
from api.schemas import (
    ClubRef,
    DealOption,
    ListingOut,
    NegotiationOut,
    OfferIn,
    OfferOut,
    OpenNegotiationIn,
    PlayerOut,
    TransfersOverview,
    TransferTargetOut,
)
from engine.economy import SQUAD_MAX, SQUAD_MIN, TransactionCategory, sale_price
from engine.transfers import (
    DealKind,
    accepts_loan,
    can_precontract,
    club_lends,
    club_level,
    playing_time,
    refusal_reason,
    time_label,
    transfer_fee,
    wage_demand,
)
from models import Club, Player
from models.orm import ClubRow, NegotiationRow, PlayerRow

router = APIRouter(prefix="/transfers", tags=["transferts"])

# Offres refusées avant que l'autre partie quitte la table, à chaque étape.
MAX_ROUNDS = 4
# Une offre à au moins 85 % de la demande fait baisser celle-ci de 5 %.
SERIOUS_OFFER_SHARE = 0.85
CONCESSION = 0.05

OPEN_STAGES = ("club", "player")


def _round_to(value: float, step: int) -> int:
    return int(round(value / step) * step)


# --- Lecture ---------------------------------------------------------------------------


def _season_year(session: Session) -> int:
    season = current_season(session)
    if season is None:
        raise HTTPException(status_code=404, detail="Aucune saison : commence une carrière")
    return season.year


def _negotiation_out(row: NegotiationRow) -> NegotiationOut:
    player = row.player
    return NegotiationOut(
        id=row.id,
        player_id=row.player_id,
        player_name=f"{player.first_name} {player.last_name}",
        club_name=player.club.name if player.club else "sans club",
        kind=DealKind(row.kind),
        stage=row.stage,
        opened_on=row.opened_on,
        rounds=row.rounds,
        fee_demand=row.fee_demand,
        fee=row.fee,
        wage_demand=row.wage_demand,
        wage=row.wage,
        years=row.years,
        message=row.message,
    )


def _active_negotiation(session: Session, club_id: int, player_id: int) -> NegotiationRow | None:
    return session.scalars(
        select(NegotiationRow).where(
            NegotiationRow.club_id == club_id,
            NegotiationRow.player_id == player_id,
            NegotiationRow.stage.in_([*OPEN_STAGES, "agreed"]),
        )
    ).first()


def _overview(session: Session, me: ClubRow) -> TransfersOverview:
    # Les effectifs viennent de changer (vente, arrivée) : on relit tout depuis la base.
    session.expire_all()
    year = _season_year(session)
    day = game_date(session)
    others = [row for row in session.scalars(select(ClubRow)) if row.id != me.id]
    names = {row.id: row.name for row in session.scalars(select(ClubRow))}
    listings = []
    for row in others:
        club = row.to_domain()
        level = round(club_level(club), 1)
        for player in club.players:
            if player.loaned_from is not None:
                continue  # un joueur prêté ne se négocie pas avec son club d'accueil
            listings.append(
                ListingOut(
                    player=PlayerOut.from_player(player, day, names),
                    club_id=club.id,
                    club_name=club.name,
                    club_level=level,
                    years_left=player.years_left(year),
                    playing_time=time_label(playing_time(player, club)),
                    transfer_fee=transfer_fee(player, club, year),
                    loanable=club_lends(player, club),
                    precontract=can_precontract(player, year),
                )
            )
    listings.sort(key=lambda listing: listing.player.value, reverse=True)

    negotiations = session.scalars(
        select(NegotiationRow)
        .where(NegotiationRow.club_id == me.id, NegotiationRow.stage.in_([*OPEN_STAGES, "agreed"]))
        .order_by(NegotiationRow.id.desc())
    )
    return TransfersOverview(
        balance=me.balance,
        season_year=year,
        squad_size=len(me.players),
        squad_min=SQUAD_MIN,
        squad_max=SQUAD_MAX,
        my_level=round(club_level(me.to_domain()), 1),
        listings=listings,
        negotiations=[_negotiation_out(row) for row in negotiations],
    )


def _options(player: Player, origin: Club, me: Club, year: int) -> list[DealOption]:
    """Les trois voies, avec les conditions du club et du joueur."""
    fee = transfer_fee(player, origin, year)
    wage = wage_demand(player, origin, me)
    refusal = refusal_reason(player, origin, me) if wage is None else ""
    options = []

    if fee is None:
        reason = "Le club refuse tout transfert : il est titulaire dans un grand club."
    elif wage is None:
        reason = refusal
    else:
        reason = "Le club demande une indemnité, puis le joueur négociera son salaire."
    options.append(
        DealOption(
            kind=DealKind.TRANSFER,
            available=fee is not None and wage is not None,
            reason=reason,
            fee_demand=fee,
            wage_demand=wage if fee is not None else None,
        )
    )

    if not can_precontract(player, year):
        reason = f"Sous contrat jusqu'en {player.contract_until + 1} : pas encore négociable."
    elif wage is None:
        reason = refusal
    else:
        reason = "Dernière année de contrat : il peut signer chez toi pour la saison prochaine."
    options.append(
        DealOption(
            kind=DealKind.PRECONTRACT,
            available=can_precontract(player, year) and wage is not None,
            reason=reason,
            wage_demand=wage if can_precontract(player, year) else None,
        )
    )

    if not club_lends(player, origin):
        reason = "Son club ne prête pas ses titulaires."
    elif not accepts_loan(player, origin, me):
        reason = "Il ne gagnerait pas de temps de jeu chez toi : un prêt ne l'intéresse pas."
    else:
        reason = "Son club le prête jusqu'à la fin de la saison, salaire à ta charge."
    options.append(
        DealOption(
            kind=DealKind.LOAN,
            available=club_lends(player, origin) and accepts_loan(player, origin, me),
            reason=reason,
            wage=player.wage,
        )
    )
    return options


def _load_target(session: Session, me: ClubRow, player_id: int) -> tuple[PlayerRow, Club, Player]:
    row = session.get(PlayerRow, player_id)
    if row is None or row.club_id is None or row.club_id == me.id or row.loaned_from is not None:
        raise HTTPException(status_code=404, detail="Joueur introuvable sur le marché")
    origin = row.club.to_domain()
    player = next(p for p in origin.players if p.id == player_id)
    return row, origin, player


@router.get("", response_model=TransfersOverview)
def get_market(session: SessionDep) -> TransfersOverview:
    """Joueurs des autres clubs, voies de recrutement, et négociations en cours."""
    return _overview(session, load_my_club_row(session))


@router.get("/{player_id}", response_model=TransferTargetOut)
def approach(player_id: int, session: SessionDep) -> TransferTargetOut:
    """Approche d'un joueur : sa situation, ce que demandent son club et lui-même."""
    me_row = load_my_club_row(session)
    _, origin, player = _load_target(session, me_row, player_id)
    me = me_row.to_domain()
    year = _season_year(session)
    active = _active_negotiation(session, me_row.id, player_id)
    return TransferTargetOut(
        player=PlayerOut.from_player(player, game_date(session)),
        club=ClubRef(id=origin.id, name=origin.name),
        club_level=round(club_level(origin), 1),
        my_level=round(club_level(me), 1),
        years_left=player.years_left(year),
        playing_time_now=time_label(playing_time(player, origin)),
        playing_time_here=time_label(playing_time(player, me)),
        options=_options(player, origin, me, year),
        negotiation=_negotiation_out(active) if active else None,
    )


# --- Négociation -------------------------------------------------------------------------


@router.post("/{player_id}/open", response_model=NegotiationOut, status_code=201)
def open_negotiation(
    player_id: int, payload: OpenNegotiationIn, session: SessionDep
) -> NegotiationOut:
    """Ouvre une négociation d'un type donné (une seule à la fois par joueur)."""
    me_row = load_my_club_row(session)
    _, origin, player = _load_target(session, me_row, player_id)
    if _active_negotiation(session, me_row.id, player_id) is not None:
        raise HTTPException(status_code=400, detail="Une négociation est déjà en cours avec lui")
    me = me_row.to_domain()
    year = _season_year(session)
    option = next(o for o in _options(player, origin, me, year) if o.kind == payload.kind)
    if not option.available:
        raise HTTPException(status_code=400, detail=option.reason)

    row = NegotiationRow(
        club_id=me_row.id,
        player_id=player_id,
        kind=payload.kind.value,
        opened_on=game_date(session),
        fee_demand=option.fee_demand,
        wage_demand=option.wage_demand if payload.kind != DealKind.LOAN else option.wage,
        fee=None,
        wage=None,
        years=None,
    )
    if payload.kind == DealKind.TRANSFER:
        row.stage = "club"
        row.message = f"{origin.name} demande une indemnité de {option.fee_demand:,} €.".replace(
            ",", " "
        )
    elif payload.kind == DealKind.PRECONTRACT:
        row.stage = "player"
        row.message = f"{player.name} demande {option.wage_demand:,} € par saison.".replace(
            ",", " "
        )
    else:
        row.stage = "player"
        row.message = (
            f"{origin.name} accepte de le prêter ; {player.name} est partant. "
            f"Son salaire ({player.wage:,} € par saison) sera à ta charge.".replace(",", " ")
        )
    session.add(row)
    session.commit()
    return _negotiation_out(row)


def _execute(session: Session, me: ClubRow, row: NegotiationRow, year: int) -> str:
    """Applique un accord complet (sauf le pré-contrat, qui attend l'intersaison)."""
    player = row.player
    name = f"{player.first_name} {player.last_name}"
    kind = DealKind(row.kind)
    if kind == DealKind.PRECONTRACT:
        return f"{name} a signé : il arrivera à l'intersaison pour {row.years} saisons."

    if len(me.players) >= SQUAD_MAX:
        raise HTTPException(status_code=400, detail=f"Effectif complet ({SQUAD_MAX} joueurs)")
    seller, day = player.club, game_date(session)
    if kind == DealKind.TRANSFER:
        if me.balance < row.fee:
            raise HTTPException(status_code=400, detail="Trésorerie insuffisante pour l'indemnité")
        record(
            session,
            me,
            TransactionCategory.TRANSFER,
            f"Achat · {name} ({seller.name})",
            -row.fee,
            day,
        )
        record(
            session,
            seller,
            TransactionCategory.TRANSFER,
            f"Vente · {name} ({me.name})",
            row.fee,
            day,
        )
        player.wage = row.wage
        player.contract_until = year + row.years - 1
        player.loaned_from = None
        player.club_id = me.id
        return f"{name} rejoint le club pour {row.years} saisons."

    player.loaned_from = seller.id
    player.club_id = me.id
    return f"{name} est prêté jusqu'à la fin de la saison."


def _counter(demand: int, offer: int, step: int) -> int:
    """La demande baisse un peu face à une offre sérieuse."""
    if offer >= SERIOUS_OFFER_SHARE * demand:
        return _round_to(demand * (1 - CONCESSION), step)
    return demand


@router.post("/negotiations/{negotiation_id}/offer", response_model=OfferOut)
def make_offer(negotiation_id: int, payload: OfferIn, session: SessionDep) -> OfferOut:
    """Fait une offre pour l'étape en cours : indemnité au club, ou salaire au joueur."""
    me = load_my_club_row(session)
    row = session.get(NegotiationRow, negotiation_id)
    if row is None or row.club_id != me.id:
        raise HTTPException(status_code=404, detail="Négociation introuvable")
    if row.stage not in OPEN_STAGES:
        raise HTTPException(status_code=400, detail="Cette négociation est terminée")
    year = _season_year(session)
    player = row.player
    name = f"{player.first_name} {player.last_name}"
    accepted = concluded = False

    if row.stage == "club":
        if payload.fee is None:
            raise HTTPException(status_code=400, detail="Indique l'indemnité proposée")
        if payload.fee >= row.fee_demand:
            row.fee, row.stage, row.rounds, accepted = payload.fee, "player", 0, True
            row.message = (
                f"{player.club.name} accepte {payload.fee:,} €. "
                f"{name} demande maintenant {row.wage_demand:,} € par saison."
            ).replace(",", " ")
        else:
            row.rounds += 1
            row.fee_demand = _counter(row.fee_demand, payload.fee, 5_000)
            if row.rounds >= MAX_ROUNDS:
                row.stage = "failed"
                row.message = f"{player.club.name} met fin aux discussions."
            else:
                row.message = f"{player.club.name} refuse et demande {row.fee_demand:,} €.".replace(
                    ",", " "
                )
    else:
        kind = DealKind(row.kind)
        wage = player.wage if kind == DealKind.LOAN else payload.wage
        if wage is None:
            raise HTTPException(status_code=400, detail="Indique le salaire proposé")
        if wage >= row.wage_demand:
            row.wage, row.years, row.rounds, accepted = wage, payload.years, 0, True
            row.stage = "agreed"
            row.message = _execute(session, me, row, year)
            concluded = True
            if kind != DealKind.PRECONTRACT:
                row.stage = "done"
        else:
            row.rounds += 1
            row.wage_demand = _counter(row.wage_demand, wage, 1_000)
            if row.rounds >= MAX_ROUNDS:
                row.stage = "failed"
                row.message = f"{name} ne veut plus discuter."
            else:
                row.message = f"{name} refuse et demande {row.wage_demand:,} € par saison.".replace(
                    ",", " "
                )

    session.commit()
    session.refresh(me)
    return OfferOut(
        accepted=accepted,
        concluded=concluded,
        message=row.message,
        negotiation=_negotiation_out(row),
        overview=_overview(session, me),
    )


@router.delete("/negotiations/{negotiation_id}", response_model=TransfersOverview)
def abandon(negotiation_id: int, session: SessionDep) -> TransfersOverview:
    """Rompt une négociation en cours (un pré-contrat signé ne se rompt pas)."""
    me = load_my_club_row(session)
    row = session.get(NegotiationRow, negotiation_id)
    if row is None or row.club_id != me.id:
        raise HTTPException(status_code=404, detail="Négociation introuvable")
    if row.stage not in OPEN_STAGES:
        raise HTTPException(status_code=400, detail="Cette négociation est terminée")
    row.stage = "failed"
    row.message = "Tu as quitté la table."
    session.commit()
    return _overview(session, me)


# --- Ventes ------------------------------------------------------------------------------


@router.post("/sell/{player_id}", response_model=TransfersOverview)
def sell(player_id: int, session: SessionDep) -> TransfersOverview:
    """Vend un de ses joueurs à sa valeur marchande, au club IA le moins fourni."""
    club = load_my_club_row(session)
    row = session.get(PlayerRow, player_id)
    if row is None or row.club_id != club.id:
        raise HTTPException(status_code=404, detail="Ce joueur n'est pas dans ton effectif")
    if row.loaned_from is not None:
        raise HTTPException(status_code=400, detail="Un joueur prêté ne se vend pas")
    if len(club.players) <= SQUAD_MIN:
        raise HTTPException(
            status_code=400, detail=f"Effectif minimum atteint ({SQUAD_MIN} joueurs)"
        )

    buyers = [
        c
        for c in session.scalars(select(ClubRow))
        if c.id != club.id and len(c.players) < SQUAD_MAX
    ]
    if not buyers:
        raise HTTPException(status_code=400, detail="Aucun club n'a de place dans son effectif")
    buyer = min(buyers, key=lambda c: len(c.players))

    price = sale_price(row.to_domain())
    day, name = game_date(session), f"{row.first_name} {row.last_name}"
    record(
        session, club, TransactionCategory.TRANSFER, f"Vente · {name} ({buyer.name})", price, day
    )
    record(
        session, buyer, TransactionCategory.TRANSFER, f"Achat · {name} ({club.name})", -price, day
    )
    row.club_id = buyer.id
    session.commit()
    session.refresh(club)
    return _overview(session, club)
