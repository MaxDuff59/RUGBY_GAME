"""Finances du club dirigé par le joueur."""

from fastapi import APIRouter

from api.deps import SessionDep, load_my_club_row
from api.schemas import FinancesOut
from engine.economy import squad_value

router = APIRouter(prefix="/finances", tags=["finances"])


@router.get("", response_model=FinancesOut)
def get_finances(session: SessionDep) -> FinancesOut:
    club = load_my_club_row(session).to_domain()
    return FinancesOut(
        balance=club.balance,
        player_wages=club.player_wages,
        staff_wages=club.staff_wages,
        squad_value=squad_value(club),
        squad_size=len(club.players),
    )
