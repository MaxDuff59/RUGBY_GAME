"""Clubs et effectifs."""

from fastapi import APIRouter
from sqlalchemy import select

from api.deps import SessionDep, load_club
from api.ledger import game_date
from api.schemas import ClubDetail, ClubSummary, FacilitiesOut, PlayerOut, StrengthOut
from engine.match_engine import team_strength
from models.orm import ClubRow

router = APIRouter(prefix="/clubs", tags=["clubs"])


@router.get("", response_model=list[ClubSummary])
def list_clubs(session: SessionDep) -> list[ClubSummary]:
    """Liste tous les clubs, triés par nom."""
    day = game_date(session)
    summaries = []
    for row in session.scalars(select(ClubRow).order_by(ClubRow.name)):
        team = team_strength(row.to_domain(), day)
        level = (team.set_piece + team.pack + team.attack + team.defense) / 4
        summaries.append(
            ClubSummary(
                id=row.id, name=row.name, player_count=len(row.players), level=round(level, 1)
            )
        )
    return summaries


@router.get("/{club_id}", response_model=ClubDetail)
def get_club(club_id: int, session: SessionDep) -> ClubDetail:
    """Effectif complet d'un club et ses notes collectives (XV de départ, blessés exclus)."""
    club = load_club(session, club_id)
    day = game_date(session)
    names = {row.id: row.name for row in session.scalars(select(ClubRow))}
    return ClubDetail(
        id=club.id,
        name=club.name,
        balance=club.balance,
        facilities=FacilitiesOut.model_validate(club.facilities),
        strength=StrengthOut.from_team(team_strength(club, day)),
        players=[PlayerOut.from_player(p, day, names) for p in club.players],
    )
