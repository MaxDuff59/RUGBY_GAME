"""Médical : infirmerie du club dirigé, protocoles de soins, dossier médical.

Quand un joueur du club se blesse, le protocole reste « à définir » : le manager
choisit entre prudence, protocole normal et retour anticipé (plus court, plus
risqué, payant). Le choix est définitif pour cette blessure. En attendant, le
protocole normal s'applique. Une absence de plus de trois mois autorise un
joker médical (api/jokers.py).
"""

import datetime

from fastapi import APIRouter, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from api.deps import SessionDep, load_my_club_row
from api.jokers import joker_of, joker_slots
from api.ledger import game_date, record
from api.schemas import InjuryCase, InjuryOut, MedicalOverview, PlayerRef, ProtocolOption
from engine.economy import TransactionCategory
from engine.medical import apply_protocol, planned_weeks, protocol_cost, relapse_risk
from models import FRAGILE_WEEKS, Club, Injury, Player, Protocol, StaffRole
from models.orm import ClubRow, InjuryRow, PlayerRow

router = APIRouter(prefix="/medical", tags=["médical"])

PROTOCOL_LABELS = {
    Protocol.CAUTIOUS: "protocole prudent",
    Protocol.STANDARD: "protocole normal",
    Protocol.ACCELERATED: "retour anticipé",
}


def _options(injury: Injury, club: Club, balance: int) -> list[ProtocolOption]:
    """Les trois protocoles possibles, tant que le manager n'a pas tranché."""
    if injury.protocol_chosen:
        return []
    physio = club.staff_level(StaffRole.PHYSIO)
    doctor = club.staff_level(StaffRole.DOCTOR)
    options = []
    for protocol in Protocol:
        weeks = planned_weeks(injury.base_weeks, protocol, physio)
        cost = protocol_cost(injury.severity, protocol)
        options.append(
            ProtocolOption(
                protocol=protocol,
                return_date=injury.occurred_on + datetime.timedelta(weeks=weeks),
                weeks=weeks,
                relapse_risk=relapse_risk(protocol, doctor),
                cost=cost,
                affordable=cost == 0 or balance >= cost,
            )
        )
    return options


def _ref(player: Player) -> PlayerRef:
    return PlayerRef(
        id=player.id,
        name=player.name,
        position=player.position,
        age=player.age,
        overall=player.overall,
    )


def injury_case(player: Player, injury: Injury, club: Club, day: datetime.date) -> InjuryCase:
    return InjuryCase(
        player=_ref(player),
        injury=InjuryOut.from_injury(injury, day),
        options=_options(injury, club, club.balance) if injury.is_active(day) else [],
    )


def _overview(session: Session, row: ClubRow) -> MedicalOverview:
    club = row.to_domain()
    day = game_date(session)
    players = {p.id: p for p in club.players}
    rows = session.scalars(
        select(InjuryRow)
        .join(PlayerRow)
        .where(PlayerRow.club_id == row.id)
        .order_by(InjuryRow.occurred_on.desc(), InjuryRow.id.desc())
    )

    slots = {slot.id for slot in joker_slots(session, row, day)}
    injured: list[InjuryCase] = []
    fragile: list[InjuryCase] = []
    history: list[InjuryCase] = []
    for injury_row in rows:
        injury = injury_row.to_domain()
        player = players[injury.player_id]
        case = injury_case(player, injury, club, day)
        case.joker_allowed = injury.id in slots
        joker = joker_of(session, injury.id)
        if joker is not None:
            case.joker = _ref(joker.player.to_domain())
        # Seule la blessure la plus récente d'un joueur décrit son état ;
        # les précédentes relèvent de l'historique.
        latest = player.injury is not None and player.injury.id == injury.id
        if latest and injury.is_active(day):
            injured.append(case)
        elif latest and injury.is_fragile(day):
            fragile.append(case)
        else:
            history.append(case)
    injured.sort(key=lambda c: c.injury.return_date)
    fragile.sort(key=lambda c: c.injury.fragile_until)

    return MedicalOverview(
        balance=club.balance,
        today=day,
        squad_size=len(club.players),
        available=len(club.available_players(day)),
        physio_level=club.staff_level(StaffRole.PHYSIO),
        doctor_level=club.staff_level(StaffRole.DOCTOR),
        fragile_weeks=FRAGILE_WEEKS,
        injured=injured,
        fragile=fragile,
        history=history,
    )


@router.get("", response_model=MedicalOverview)
def get_medical(session: SessionDep) -> MedicalOverview:
    """Blessés, joueurs sous surveillance et historique du club dirigé."""
    return _overview(session, load_my_club_row(session))


@router.post("/{injury_id}/protocol/{protocol}", response_model=MedicalOverview)
def choose_protocol(injury_id: int, protocol: Protocol, session: SessionDep) -> MedicalOverview:
    """Fixe le protocole de soins d'une blessure en cours (choix définitif)."""
    club_row = load_my_club_row(session)
    row = session.get(InjuryRow, injury_id)
    if row is None or row.player.club_id != club_row.id:
        raise HTTPException(status_code=404, detail="Blessure introuvable dans ton effectif")

    day = game_date(session)
    injury = row.to_domain()
    if not injury.is_active(day):
        raise HTTPException(status_code=400, detail="Le joueur est déjà revenu")
    if injury.protocol_chosen:
        raise HTTPException(status_code=400, detail="Le protocole de cette blessure est déjà fixé")
    cost = protocol_cost(injury.severity, protocol)
    if club_row.balance < cost:
        raise HTTPException(status_code=400, detail="Trésorerie insuffisante")

    club = club_row.to_domain()
    apply_protocol(injury, protocol, club)
    if cost:
        player = row.player
        record(
            session,
            club_row,
            TransactionCategory.MEDICAL,
            f"Soins · {player.first_name} {player.last_name} · {PROTOCOL_LABELS[protocol]}",
            -cost,
            day,
        )
    row.update_from(injury)
    session.commit()
    session.refresh(club_row)
    return _overview(session, club_row)
