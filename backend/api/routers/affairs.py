"""Affaires entre deux matchs : celles qui attendent une réponse, et la réponse."""

from fastapi import APIRouter, HTTPException

from api.affairs import affair_out, answer, pending_affairs, recent_affairs
from api.deps import SessionDep, load_my_club_row
from api.schemas import AffairOut, AffairsOverview, AnswerIn
from models.orm import AffairRow

router = APIRouter(prefix="/affairs", tags=["affaires"])


@router.get("", response_model=AffairsOverview)
def get_affairs(session: SessionDep) -> AffairsOverview:
    """Affaires en attente de réponse, et les dernières réglées."""
    club = load_my_club_row(session)
    return AffairsOverview(
        pending=[affair_out(row) for row in pending_affairs(session, club.id)],
        recent=[affair_out(row) for row in recent_affairs(session, club.id)],
    )


@router.post("/{affair_id}/answer", response_model=AffairOut)
def answer_affair(affair_id: int, body: AnswerIn, session: SessionDep) -> AffairOut:
    """Répond à une affaire : renvoie la réaction et les effets (cachés jusque-là)."""
    club = load_my_club_row(session)
    row = session.get(AffairRow, affair_id)
    if row is None or row.club_id != club.id:
        raise HTTPException(status_code=404, detail="Affaire introuvable")
    return affair_out(answer(session, club, row, body.choice))
