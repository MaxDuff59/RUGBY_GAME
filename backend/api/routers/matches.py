"""Matchs : simulation amicale et détail d'un match joué."""

import random

from fastapi import APIRouter, HTTPException
from sqlalchemy import select

from api.deps import SessionDep, load_club
from api.ledger import game_date
from api.schemas import MatchOut, MatchPlayerOut, PlayerMatchStatsOut, SimulateMatchIn
from engine.match_engine import SLOT_NUMBERS, simulate_match
from models import Match, Position
from models.orm import MatchRow, PlayerRow

router = APIRouter(prefix="/matches", tags=["matchs"])


@router.post("/simulate", response_model=MatchOut)
def simulate(payload: SimulateMatchIn, session: SessionDep) -> MatchOut:
    """Simule un match amical entre deux clubs (ni résultat ni blessure ne sont enregistrés)."""
    if payload.home_club_id == payload.away_club_id:
        raise HTTPException(status_code=400, detail="Un club ne peut pas jouer contre lui-même")

    home = load_club(session, payload.home_club_id)
    away = load_club(session, payload.away_club_id)
    rng = random.Random(payload.seed) if payload.seed is not None else None
    return MatchOut.from_match(simulate_match(home, away, rng=rng, day=game_date(session)))


def _players(session, match: Match) -> list[MatchPlayerOut]:
    """Les joueurs entrés en jeu, titulaires d'abord dans l'ordre de leurs numéros,
    puis les remplaçants."""
    ids = list(match.stats)
    rows = {
        player_id: (f"{first} {last}".strip(), position)
        for player_id, first, last, position in session.execute(
            select(
                PlayerRow.id, PlayerRow.first_name, PlayerRow.last_name, PlayerRow.position
            ).where(PlayerRow.id.in_(ids))
        )
    }
    numbers = {
        player_id: SLOT_NUMBERS[index]
        for lineup in (match.home_lineup, match.away_lineup)
        for index, player_id in enumerate(lineup)
        if index < len(SLOT_NUMBERS)
    }
    home = set(match.home_lineup)
    clubs = {e.player_id: e.club_id for e in match.events if e.player_id is not None}
    clubs |= {e.other_player_id: e.club_id for e in match.events if e.other_player_id}
    players = []
    for player_id, stats in match.stats.items():
        name, position = rows.get(player_id, (None, None))
        club_id = match.home_club_id if player_id in home else clubs.get(player_id)
        players.append(
            MatchPlayerOut(
                id=player_id,
                name=name,
                position=Position(position) if position else None,
                club_id=club_id if club_id is not None else match.away_club_id,
                number=numbers.get(player_id),
                stats=PlayerMatchStatsOut.model_validate(stats),
            )
        )
    return sorted(players, key=lambda p: (p.number is None, p.number or 0))


@router.get("/{match_id}", response_model=MatchOut)
def get_match(match_id: int, session: SessionDep) -> MatchOut:
    """Détail d'un match du calendrier déjà joué : score, événements, météo et
    statistiques de chaque joueur entré en jeu."""
    row = session.get(MatchRow, match_id)
    if row is None:
        raise HTTPException(status_code=404, detail=f"Match {match_id} introuvable")
    if not row.is_played:
        raise HTTPException(status_code=400, detail="Ce match n'a pas encore été joué")
    match = row.to_domain()
    return MatchOut.from_match(match, _players(session, match))
