"""Les championnats du monde du jeu (data/leagues.py)."""

from fastapi import APIRouter
from sqlalchemy import func, select

from api.deps import SessionDep
from api.schemas import LeagueOut
from data.leagues import LEAGUES_BY_CODE, league_config, sort_codes
from models.orm import ClubRow

router = APIRouter(prefix="/leagues", tags=["championnats"])


def league_out(code: str, club_count: int) -> LeagueOut:
    known = code in LEAGUES_BY_CODE
    config = league_config(code)
    return LeagueOut(
        code=code,
        name=config.name if known else "Championnat",
        short_name=config.short_name if known else "Championnat",
        country=config.country if known else "",
        club_count=club_count,
        playoff_stages=config.playoffs.stages,
    )


@router.get("", response_model=list[LeagueOut])
def list_leagues(session: SessionDep) -> list[LeagueOut]:
    """Les championnats qui ont des clubs, dans l'ordre de data/leagues.py."""
    counts = dict(
        session.execute(select(ClubRow.league, func.count()).group_by(ClubRow.league)).all()
    )
    return [league_out(code, counts[code]) for code in sort_codes(counts)]
