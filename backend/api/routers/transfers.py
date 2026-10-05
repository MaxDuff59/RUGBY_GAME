"""Recrutement du club dirigé : approche, négociation, prêts, pré-contrats, ventes.

Trois voies pour recruter un joueur d'un autre club (règles : engine/transfers.py) :

- transfert en cours de contrat : on convient d'abord de l'indemnité avec le
  club, puis du salaire avec le joueur ; il arrive aussitôt ;
- pré-contrat : en dernière année de contrat, le joueur négocie librement son
  salaire ; il arrive à l'intersaison ;
- prêt : le club prête ses non-titulaires jusqu'à la fin de la saison, le
  joueur accepte s'il y gagne du temps de jeu ; son salaire est à ta charge.

Un agent libre (sans club ni contrat, voir engine/free_agents.py) négocie seul
son salaire et arrive aussitôt. Pendant une longue blessure, il peut aussi venir
en joker médical, en plus de l'effectif, jusqu'au retour du blessé (api/jokers.py).

Le club et le joueur ouvrent au-dessus de leur objectif (secret) et s'en
rapprochent à chaque offre refusée, puis consentent un dernier effort si l'offre
est proche. Leur patience s'use à chaque refus (plus vite si l'offre ne bouge
pas ou est dérisoire) ; à bout de patience, ils ne veulent plus discuter. Le
joueur a aussi une durée de contrat en tête. Et il a de la mémoire : après une
rupture, pas de discussion avant un moment, puis il revient plus exigeant.
"""

import datetime

from fastapi import APIRouter, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from api.deps import SessionDep, load_my_club_row
from api.jokers import joker_ids, joker_slots, live_jokers, squad_count, start_talks
from api.jokers import sign as sign_joker
from api.ledger import current_season, game_date, record
from api.schemas import (
    ClubRef,
    DealOption,
    JokerOut,
    JokerSlotOut,
    ListingOut,
    NegotiationOut,
    OfferIn,
    OfferOut,
    OpenNegotiationIn,
    PlayerOut,
    PlayerRef,
    TransfersOverview,
    TransferTargetOut,
)
from data.leagues import league_config, sort_codes
from engine.economy import SQUAD_MAX, SQUAD_MIN, TransactionCategory, sale_price
from engine.free_agents import free_agent_wage, seasons_without_club
from engine.transfers import (
    CLUB_OPENING_MARKUP,
    COOLDOWN_WEEKS_AFTER_MY_EXIT,
    COOLDOWN_WEEKS_AFTER_THEIR_EXIT,
    PATIENCE_COST,
    PLAYER_OPENING_MARKUP,
    DealKind,
    accepts_loan,
    bargain,
    can_precontract,
    club_lends,
    club_level,
    grudge_markup,
    grudge_patience,
    opening_ask,
    playing_time,
    preferred_years,
    refusal_reason,
    time_label,
    transfer_fee,
    wage_demand,
)
from models import Club, Player, Squad
from models.orm import ClubRow, InjuryRow, NegotiationRow, PlayerRow

router = APIRouter(prefix="/transfers", tags=["transferts"])

FEE_STEP = 5_000
WAGE_STEP = 1_000

OPEN_STAGES = ("club", "player")

FREE_AGENT = "Agent libre"


def _money(amount: int) -> str:
    return f"{amount:,} €".replace(",", " ")


def _fee_opening(player: Player, club: Club, year: int, grudges: int = 0) -> int | None:
    target = transfer_fee(player, club, year)
    if target is None:
        return None
    return opening_ask(target, grudge_markup(CLUB_OPENING_MARKUP, grudges), FEE_STEP)


def _wage_target(player: Player, origin: Club | None, me: Club) -> int | None:
    """Salaire visé par le joueur pour venir (None s'il refuse) ; `origin` None = agent libre."""
    return free_agent_wage(player, me) if origin is None else wage_demand(player, origin, me)


def _wage_opening(player: Player, origin: Club | None, me: Club, grudges: int = 0) -> int | None:
    target = _wage_target(player, origin, me)
    if target is None:
        return None
    return opening_ask(target, grudge_markup(PLAYER_OPENING_MARKUP, grudges), WAGE_STEP)


def _memory(
    session: Session, club_id: int, player_id: int, day: datetime.date
) -> tuple[int, datetime.date | None]:
    """Mémoire du joueur : (ruptures de son fait, date avant laquelle il ne discute pas)."""
    failed = session.scalars(
        select(NegotiationRow).where(
            NegotiationRow.club_id == club_id,
            NegotiationRow.player_id == player_id,
            NegotiationRow.stage == "failed",
        )
    ).all()
    grudges = sum(1 for row in failed if row.closed_by == "them")
    closed_until = max(
        (row.cooldown_until for row in failed if row.cooldown_until and row.cooldown_until > day),
        default=None,
    )
    return grudges, closed_until


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
        club_name=player.club.name if player.club else FREE_AGENT,
        kind=DealKind(row.kind),
        stage=row.stage,
        opened_on=row.opened_on,
        rounds=row.rounds,
        patience=row.patience,
        fee_demand=row.fee_demand,
        fee=row.fee,
        wage_demand=row.wage_demand,
        wage=row.wage,
        years=row.years,
        message=row.message,
        closed_by=row.closed_by,
        cooldown_until=row.cooldown_until,
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
    # Mémoire des ruptures, par joueur.
    memory: dict[int, tuple[int, datetime.date | None]] = {}
    for row in session.scalars(
        select(NegotiationRow).where(
            NegotiationRow.club_id == me.id, NegotiationRow.stage == "failed"
        )
    ):
        grudges, closed_until = memory.get(row.player_id, (0, None))
        if row.closed_by == "them":
            grudges += 1
        if row.cooldown_until and row.cooldown_until > day:
            closed_until = max(closed_until or row.cooldown_until, row.cooldown_until)
        memory[row.player_id] = (grudges, closed_until)
    listings = []
    for row in others:
        club = row.to_domain()
        level = round(club_level(club), 1)
        for player in club.players:
            if player.loaned_from is not None:
                continue  # un joueur prêté ne se négocie pas avec son club d'accueil
            grudges, closed_until = memory.get(player.id, (0, None))
            listings.append(
                ListingOut(
                    player=PlayerOut.from_player(player, day, names),
                    club_id=club.id,
                    club_name=club.name,
                    club_level=level,
                    league=league_config(club.league).short_name,
                    years_left=player.years_left(year),
                    playing_time=time_label(playing_time(player, club)),
                    transfer_fee=_fee_opening(player, club, year, grudges),
                    loanable=club_lends(player, club),
                    precontract=can_precontract(player, year),
                    talks_closed_until=closed_until,
                )
            )
    mine = me.to_domain()
    for row in session.scalars(
        select(PlayerRow).where(PlayerRow.club_id.is_(None), PlayerRow.squad == Squad.PRO.value)
    ):
        player = row.to_domain()
        grudges, closed_until = memory.get(player.id, (0, None))
        listings.append(
            ListingOut(
                player=PlayerOut.from_player(player, day, names),
                club_id=None,
                club_name=None,
                club_level=None,
                league=None,
                years_left=0,
                playing_time="sans club",
                transfer_fee=None,
                loanable=False,
                precontract=False,
                talks_closed_until=closed_until,
                free_agent=True,
                wage_demand=_wage_opening(player, None, mine, grudges),
            )
        )
    listings.sort(key=lambda listing: listing.player.value, reverse=True)

    negotiations = session.scalars(
        select(NegotiationRow)
        .where(NegotiationRow.club_id == me.id, NegotiationRow.stage.in_([*OPEN_STAGES, "agreed"]))
        .order_by(NegotiationRow.id.desc())
    )
    jokers = [
        JokerOut(
            player=_player_ref(joker.player),
            injured=_player_ref(joker.injury.player),
            until=joker.injury.return_date,
            status=joker.status,
        )
        for joker in live_jokers(session, me.id)
    ]
    return TransfersOverview(
        balance=me.balance,
        season_year=year,
        squad_size=squad_count(session, me),
        squad_min=SQUAD_MIN,
        squad_max=SQUAD_MAX,
        my_level=round(club_level(me.to_domain()), 1),
        leagues=[league_config(code).short_name for code in sort_codes({r.league for r in others})],
        listings=listings,
        negotiations=[_negotiation_out(row) for row in negotiations],
        joker_slots=[
            JokerSlotOut(
                injury_id=slot.id,
                player=_player_ref(slot.player),
                kind=slot.kind,
                return_date=slot.return_date,
            )
            for slot in joker_slots(session, me, day)
        ],
        jokers=jokers,
    )


def _player_ref(row: PlayerRow) -> PlayerRef:
    player = row.to_domain()
    return PlayerRef(
        id=player.id,
        name=player.name,
        position=player.position,
        age=player.age,
        overall=player.overall,
    )


def _options(
    player: Player,
    origin: Club | None,
    me: Club,
    year: int,
    grudges: int = 0,
    closed_until: datetime.date | None = None,
    slots: list[InjuryRow] = (),
) -> list[DealOption]:
    """Les voies, avec ce que demandent le club et le joueur à l'ouverture : les trois
    voies pour un joueur sous contrat ; pour un agent libre, la signature libre et
    un joker médical par longue blessure (`slots`)."""
    if origin is None:
        free = seasons_without_club(player, year)
        reason = (
            "Sans club depuis l'intersaison : pas d'indemnité, il arrive tout de suite."
            if free == 0
            else f"Sans club depuis {free + 1} intersaisons : il a hâte de rejouer."
        )
        wage = _wage_opening(player, None, me, grudges)
        options = [DealOption(kind=DealKind.FREE, available=True, reason=reason, wage_demand=wage)]
        for slot in slots:
            injured = f"{slot.player.first_name} {slot.player.last_name}"
            options.append(
                DealOption(
                    kind=DealKind.JOKER,
                    available=True,
                    reason=(
                        f"Pige jusqu'au retour de {injured}, prévu le "
                        f"{slot.return_date:%d/%m/%Y}, en plus de ton effectif."
                    ),
                    wage_demand=wage,
                    injury_id=slot.id,
                    injured_name=injured,
                    until=slot.return_date,
                )
            )
    else:
        options = None
    if closed_until is not None:
        reason = f"Il ne veut plus discuter avec vous avant le {closed_until:%d/%m/%Y}."
        kinds = (
            [o.kind for o in options]
            if options
            else [DealKind.TRANSFER, DealKind.PRECONTRACT, DealKind.LOAN]
        )
        return [DealOption(kind=kind, available=False, reason=reason) for kind in kinds]
    if options is not None:
        return options
    fee = _fee_opening(player, origin, year, grudges)
    wage = _wage_opening(player, origin, me, grudges)
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


def _load_target(
    session: Session, me: ClubRow, player_id: int
) -> tuple[PlayerRow, Club | None, Player]:
    """Le joueur visé et son club (None pour un agent libre)."""
    row = session.get(PlayerRow, player_id)
    if (
        row is None
        or row.squad != Squad.PRO.value
        or row.club_id == me.id
        or row.loaned_from is not None
    ):
        raise HTTPException(status_code=404, detail="Joueur introuvable sur le marché")
    if row.club_id is None:
        return row, None, row.to_domain()
    origin = row.club.to_domain()
    player = next(p for p in origin.players if p.id == player_id)
    return row, origin, player


@router.get("", response_model=TransfersOverview)
def get_market(session: SessionDep) -> TransfersOverview:
    """Joueurs des autres clubs et agents libres, voies de recrutement, négociations en cours."""
    return _overview(session, load_my_club_row(session))


@router.get("/{player_id}", response_model=TransferTargetOut)
def approach(player_id: int, session: SessionDep) -> TransferTargetOut:
    """Approche d'un joueur : sa situation, ce que demandent son club et lui-même."""
    me_row = load_my_club_row(session)
    _, origin, player = _load_target(session, me_row, player_id)
    me = me_row.to_domain()
    year = _season_year(session)
    active = _active_negotiation(session, me_row.id, player_id)
    grudges, closed_until = _memory(session, me_row.id, player_id, game_date(session))
    slots = joker_slots(session, me_row, game_date(session)) if origin is None else []
    return TransferTargetOut(
        player=PlayerOut.from_player(player, game_date(session)),
        club=ClubRef(id=origin.id, name=origin.name) if origin else None,
        club_level=round(club_level(origin), 1) if origin else None,
        my_level=round(club_level(me), 1),
        years_left=player.years_left(year) if origin else 0,
        playing_time_now=time_label(playing_time(player, origin)) if origin else "sans club",
        playing_time_here=time_label(playing_time(player, me)),
        preferred_years=preferred_years(player),
        talks_closed_until=closed_until,
        grudges=grudges,
        options=_options(player, origin, me, year, grudges, closed_until, slots),
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
    day = game_date(session)
    grudges, closed_until = _memory(session, me_row.id, player_id, day)
    slots = joker_slots(session, me_row, day) if origin is None else []
    options = _options(player, origin, me, year, grudges, closed_until, slots)
    option = next(
        (
            o
            for o in options
            if o.kind == payload.kind
            and (o.kind != DealKind.JOKER or o.injury_id == payload.injury_id)
        ),
        None,
    )
    if option is None and payload.kind == DealKind.JOKER and origin is None:
        raise HTTPException(
            status_code=400, detail="Pas de joker médical possible pour cette blessure"
        )
    if option is None:
        situation = "Il est sans club" if origin is None else "Il est sous contrat"
        detail = f"{situation} : cette voie n'est pas possible pour lui."
        raise HTTPException(status_code=400, detail=detail)
    if not option.available:
        raise HTTPException(status_code=400, detail=option.reason)

    low, high = preferred_years(player)
    row = NegotiationRow(
        club_id=me_row.id,
        player_id=player_id,
        kind=payload.kind.value,
        opened_on=day,
        patience=grudge_patience(grudges),
        last_offer=None,
        fee_demand=option.fee_demand,
        fee_floor=transfer_fee(player, origin, year) if origin else None,
        wage_demand=option.wage_demand if payload.kind != DealKind.LOAN else option.wage,
        wage_floor=_wage_target(player, origin, me) if payload.kind != DealKind.LOAN else None,
        fee=None,
        wage=None,
        years=None,
    )
    if payload.kind == DealKind.FREE:
        row.stage = "player"
        row.message = (
            f"{player.name}, libre de tout contrat, demande {_money(option.wage_demand)} "
            f"par saison, sur un contrat de {low} à {high} saisons."
        )
    elif payload.kind == DealKind.JOKER:
        row.stage = "player"
        row.message = (
            f"{player.name} est partant pour une pige jusqu'au retour de {option.injured_name}. "
            f"Il demande {_money(option.wage_demand)} par saison, au prorata de sa présence."
        )
    elif payload.kind == DealKind.TRANSFER:
        row.stage = "club"
        row.message = (
            f"{origin.name} ouvre les discussions à {_money(option.fee_demand)} d'indemnité."
        )
    elif payload.kind == DealKind.PRECONTRACT:
        row.stage = "player"
        row.message = (
            f"{player.name} demande {_money(option.wage_demand)} par saison, "
            f"sur un contrat de {low} à {high} saisons."
        )
    else:
        row.stage = "player"
        row.message = (
            f"{origin.name} accepte de le prêter ; {player.name} est partant. "
            f"Son salaire ({player.wage:,} € par saison) sera à ta charge.".replace(",", " ")
        )
    if grudges and payload.kind != DealKind.LOAN:
        row.message += " Il n'a pas oublié vos dernières discussions : il sera moins patient."
    session.add(row)
    if payload.kind == DealKind.JOKER:
        session.flush()
        start_talks(session, me_row.id, row, option.injury_id)
    session.commit()
    return _negotiation_out(row)


def _execute(session: Session, me: ClubRow, row: NegotiationRow, year: int) -> str:
    """Applique un accord complet (sauf le pré-contrat, qui attend l'intersaison)."""
    player = row.player
    name = f"{player.first_name} {player.last_name}"
    kind = DealKind(row.kind)
    if kind == DealKind.PRECONTRACT:
        return f"{name} a signé : il arrivera à l'intersaison pour {row.years} saisons."

    if kind == DealKind.JOKER:
        return sign_joker(session, row, year)  # en plus de l'effectif
    if squad_count(session, me) >= SQUAD_MAX:
        raise HTTPException(status_code=400, detail=f"Effectif complet ({SQUAD_MAX} joueurs)")
    if kind == DealKind.FREE:
        player.wage = row.wage
        player.contract_until = year + row.years - 1
        player.club_id = me.id
        return f"{name} s'engage avec le club pour {row.years} saisons."
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


def _walk_away(row: NegotiationRow, who: str) -> None:
    """L'autre partie quitte la table et s'en souviendra."""
    row.stage = "failed"
    row.closed_by = "them"
    row.cooldown_until = row.opened_on + datetime.timedelta(weeks=COOLDOWN_WEEKS_AFTER_THEIR_EXIT)
    row.message = (
        f"{who} ne veut plus discuter avec vous. "
        f"Inutile de revenir avant le {row.cooldown_until:%d/%m/%Y}."
    )


def _refuse(row: NegotiationRow, who: str, verdict: str, ask: int, unit: str) -> None:
    """Après une offre refusée : patience entamée, demande mise à jour, réponse formulée."""
    row.rounds += 1
    row.patience -= PATIENCE_COST[verdict]
    if row.patience <= 0:
        _walk_away(row, who)
        return
    amount = f"{_money(ask)}{unit}"
    if verdict == "insulted":
        row.message = f"{who} juge l'offre dérisoire. Encore une comme ça et c'est fini."
    elif verdict == "stalled":
        row.message = f"{who} s'impatiente : tu n'as pas bougé. La demande reste à {amount}."
    elif verdict == "last_word":
        row.message = (
            f"{who} campe sur {amount} : c'est un dernier mot, à moins que tu t'en approches."
        )
    elif verdict == "effort":
        row.message = f"{who} consent un dernier effort : {amount}, pas moins."
    else:
        row.message = f"{who} refuse, mais pourrait se contenter de {amount}."
    if row.patience <= 2:
        row.message += " La patience s'épuise."


@router.post("/negotiations/{negotiation_id}/offer", response_model=OfferOut)
def make_offer(negotiation_id: int, payload: OfferIn, session: SessionDep) -> OfferOut:
    """Fait une offre pour l'étape en cours : indemnité au club, ou salaire et durée au joueur."""
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
        verdict, ask = bargain(row.fee_demand, row.fee_floor, payload.fee, row.last_offer, FEE_STEP)
        row.last_offer = payload.fee
        if verdict == "accepted":
            row.fee, row.stage, accepted = payload.fee, "player", True
            grudges, _ = _memory(session, me.id, row.player_id, game_date(session))
            row.rounds, row.patience, row.last_offer = 0, grudge_patience(grudges), None
            low, high = preferred_years(player.to_domain())
            row.message = (
                f"{player.club.name} accepte {_money(payload.fee)}. À toi de convaincre {name} : "
                f"il demande {_money(row.wage_demand)} par saison, sur {low} à {high} saisons."
            )
        else:
            row.fee_demand = ask
            _refuse(row, player.club.name, verdict, ask, "")
    else:
        kind = DealKind(row.kind)
        if kind == DealKind.LOAN:
            verdict, ask, wage = "accepted", row.wage_demand, player.wage
        else:
            if payload.wage is None:
                raise HTTPException(status_code=400, detail="Indique le salaire proposé")
            wage = payload.wage
            low, high = preferred_years(player.to_domain())
            if kind != DealKind.JOKER and not low <= payload.years <= high:
                # La durée ne lui convient pas : il ne discute même pas le salaire.
                row.rounds += 1
                row.patience -= 1
                row.message = (
                    f"{payload.years} saison{'s' if payload.years > 1 else ''} ? {name} cherche "
                    f"un contrat de {low} à {high} saisons."
                )
                if row.patience <= 0:
                    _walk_away(row, name)
                session.commit()
                return OfferOut(
                    accepted=False,
                    concluded=False,
                    message=row.message,
                    negotiation=_negotiation_out(row),
                    overview=_overview(session, me),
                )
            verdict, ask = bargain(row.wage_demand, row.wage_floor, wage, row.last_offer, WAGE_STEP)
            row.last_offer = wage
        if verdict == "accepted":
            years = None if kind == DealKind.JOKER else payload.years
            row.wage, row.years, row.rounds, accepted = wage, years, 0, True
            row.stage = "agreed"
            row.message = _execute(session, me, row, year)
            concluded = True
            if kind != DealKind.PRECONTRACT:
                row.stage = "done"
        else:
            row.wage_demand = ask
            _refuse(row, name, verdict, ask, " par saison")

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
    row.closed_by = "me"
    row.cooldown_until = game_date(session) + datetime.timedelta(weeks=COOLDOWN_WEEKS_AFTER_MY_EXIT)
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
    if player_id in joker_ids(session, club.id):
        raise HTTPException(status_code=400, detail="Un joker médical ne se vend pas")
    if squad_count(session, club) <= SQUAD_MIN:
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
