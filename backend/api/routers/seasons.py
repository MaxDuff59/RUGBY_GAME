"""Saisons : simulation complète et classement.

Le classement n'est pas stocké : il est recalculé à partir des matchs enregistrés.
"""

import random

from fastapi import APIRouter, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from api.deps import SessionDep
from api.schemas import SeasonIn, SeasonOut, StandingOut
from engine.season import record_result, simulate_season
from models import Club, Season
from models.orm import ClubRow, MatchRow, SeasonRow

router = APIRouter(prefix="/seasons", tags=["saisons"])


def _load_clubs(session: Session) -> list[Club]:
    return [row.to_domain() for row in session.scalars(select(ClubRow).order_by(ClubRow.id))]


def _season_out(season: Season) -> SeasonOut:
    names = {club.id: club.name for club in season.clubs}
    standings = [
        StandingOut(
            rank=rank,
            club_id=row.club_id,
            club_name=names[row.club_id],
            played=row.played,
            won=row.won,
            drawn=row.drawn,
            lost=row.lost,
            points_for=row.points_for,
            points_against=row.points_against,
            points_difference=row.points_difference,
            tries_for=row.tries_for,
            offensive_bonus=row.offensive_bonus,
            defensive_bonus=row.defensive_bonus,
            league_points=row.league_points,
        )
        for rank, row in enumerate(season.table(), start=1)
    ]
    matchdays = max((m.matchday for m in season.matches), default=0)
    return SeasonOut(year=season.year, matchdays=matchdays, standings=standings)


@router.post("", response_model=SeasonOut, status_code=201)
def simulate_full_season(payload: SeasonIn, session: SessionDep) -> SeasonOut:
    """Simule une saison complète avec tous les clubs et l'enregistre."""
    if session.scalars(select(SeasonRow).where(SeasonRow.year == payload.year)).first():
        raise HTTPException(status_code=409, detail=f"La saison {payload.year} existe déjà")

    clubs = _load_clubs(session)
    rng = random.Random(payload.seed) if payload.seed is not None else None
    season = simulate_season(clubs, year=payload.year, rng=rng)

    row = SeasonRow(year=season.year)
    row.matches = [MatchRow.from_domain(match) for match in season.matches]
    session.add(row)
    session.commit()
    return _season_out(season)


@router.get("/{year}", response_model=SeasonOut)
def get_season(year: int, session: SessionDep) -> SeasonOut:
    """Classement d'une saison enregistrée, recalculé à partir de ses matchs."""
    row = session.scalars(select(SeasonRow).where(SeasonRow.year == year)).first()
    if row is None:
        raise HTTPException(status_code=404, detail=f"Saison {year} introuvable")

    season = Season(year=year, clubs=_load_clubs(session))
    for match_row in row.matches:
        match = match_row.to_domain()
        season.matches.append(match)
        record_result(season, match)
    return _season_out(season)
