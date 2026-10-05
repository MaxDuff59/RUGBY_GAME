"""Clubs et effectifs."""

from fastapi import APIRouter, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from api.deps import SessionDep, load_club, load_my_club_row
from api.ledger import game_date
from api.notes import club_notes
from api.schemas import (
    ClubDetail,
    ClubNotesOut,
    ClubSummary,
    FacilitiesOut,
    LineupIn,
    PlayerOut,
    StrengthOut,
)
from engine.match_engine import SLOT_POSITIONS, team_strength
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
                id=row.id,
                name=row.name,
                league=row.league,
                player_count=len(row.players),
                level=round(level, 1),
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
        lineup_custom=any(player_id is not None for player_id in club.lineup_choice),
    )


@router.put("/{club_id}/lineup", response_model=ClubDetail)
def set_lineup(club_id: int, lineup: LineupIn, session: SessionDep) -> ClubDetail:
    """Le manager compose son XV : chaque place reçoit le joueur voulu, même hors poste.
    Un joueur blessé plus tard est remplacé par le staff le temps de sa blessure."""
    row = _my_club_row(session, club_id)
    ids = lineup.player_ids
    if len(ids) != len(SLOT_POSITIONS):
        raise HTTPException(status_code=400, detail=f"Il faut {len(SLOT_POSITIONS)} places")
    chosen = [player_id for player_id in ids if player_id is not None]
    if len(set(chosen)) != len(chosen):
        raise HTTPException(status_code=400, detail="Un joueur ne peut occuper qu'une place")
    day = game_date(session)
    players = {p.id: p for p in row.to_domain().players}
    for player_id in chosen:
        player = players.get(player_id)
        if player is None:
            raise HTTPException(status_code=400, detail="Ce joueur n'est pas dans ton effectif")
        if player.is_injured(day):
            raise HTTPException(status_code=400, detail=f"{player.name} est blessé")
    row.lineup_choice = list(ids)
    session.commit()
    return get_club(club_id, session)


@router.delete("/{club_id}/lineup", response_model=ClubDetail)
def reset_lineup(club_id: int, session: SessionDep) -> ClubDetail:
    """Rend la composition du XV au staff."""
    _my_club_row(session, club_id).lineup_choice = []
    session.commit()
    return get_club(club_id, session)


def _my_club_row(session: Session, club_id: int) -> ClubRow:
    row = load_my_club_row(session)
    if row.id != club_id:
        raise HTTPException(status_code=403, detail="Tu ne composes que le XV de ton club")
    return row


@router.get("/{club_id}/notes", response_model=ClubNotesOut)
def get_club_notes(club_id: int, session: SessionDep) -> ClubNotesOut:
    """Notes de vie du club sur 20 : moral, cohésion, fraîcheur, confiance de la
    direction et ferveur des supporters, avec leur évolution sur la saison."""
    return club_notes(session, load_club(session, club_id))
