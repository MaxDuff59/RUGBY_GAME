"""Simulation de matchs."""

import random

from fastapi import APIRouter, HTTPException

from api.deps import SessionDep, load_club
from api.schemas import MatchOut, SimulateMatchIn
from engine.match_engine import simulate_match

router = APIRouter(prefix="/matches", tags=["matchs"])


@router.post("/simulate", response_model=MatchOut)
def simulate(payload: SimulateMatchIn, session: SessionDep) -> MatchOut:
    """Simule un match amical entre deux clubs (le résultat n'est pas enregistré)."""
    if payload.home_club_id == payload.away_club_id:
        raise HTTPException(status_code=400, detail="Un club ne peut pas jouer contre lui-même")

    home = load_club(session, payload.home_club_id)
    away = load_club(session, payload.away_club_id)
    rng = random.Random(payload.seed) if payload.seed is not None else None
    return MatchOut.from_match(simulate_match(home, away, rng=rng))
