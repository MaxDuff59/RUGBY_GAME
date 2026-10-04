"""Finances du club dirigé par le joueur : situation et grand livre."""

from fastapi import APIRouter
from sqlalchemy import select

from api.deps import SessionDep, load_my_club_row
from api.schemas import FinancesOut, TransactionOut
from engine.economy import squad_value
from models.orm import TransactionRow

router = APIRouter(prefix="/finances", tags=["finances"])


@router.get("", response_model=FinancesOut)
def get_finances(session: SessionDep) -> FinancesOut:
    row = load_my_club_row(session)
    club = row.to_domain()
    transactions = session.scalars(
        select(TransactionRow)
        .where(TransactionRow.club_id == row.id)
        .order_by(TransactionRow.date.desc(), TransactionRow.id.desc())
    )
    return FinancesOut(
        balance=club.balance,
        player_wages=club.player_wages,
        staff_wages=club.staff_wages,
        squad_value=squad_value(club),
        squad_size=len(club.players),
        transactions=[TransactionOut.model_validate(t) for t in transactions],
    )
