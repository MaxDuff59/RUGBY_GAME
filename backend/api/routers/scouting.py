"""Les recruteurs du club dirigé (engine/scouting.py) : superviser un joueur."""

from fastapi import APIRouter, HTTPException
from sqlalchemy import select

from api.deps import SessionDep, load_my_club_row
from api.ledger import game_date, record
from api.schemas import PlayerOut
from api.scouting import Knowledge
from engine.economy import TransactionCategory
from engine.scouting import REPORT_COST
from models.orm import ClubRow, PlayerRow, ScoutReportRow

router = APIRouter(prefix="/scouting", tags=["recrutement"])


@router.post("/{player_id}", response_model=PlayerOut, status_code=201)
def scout(player_id: int, session: SessionDep) -> PlayerOut:
    """Envoie un recruteur superviser un joueur : son rapport (ses vrais attributs, et un
    potentiel estimé de près) est rendu au soir de la journée suivante."""
    me = load_my_club_row(session)
    row = session.get(PlayerRow, player_id)
    if row is None:
        raise HTTPException(status_code=404, detail=f"Joueur {player_id} introuvable")
    knowledge = Knowledge(session)
    status = knowledge.status(row.to_domain())
    if status == "own":
        raise HTTPException(status_code=400, detail="Tu connais déjà tes propres joueurs")
    if status in ("report", "pending"):
        raise HTTPException(status_code=400, detail="Ce joueur est déjà supervisé")
    if me.balance < REPORT_COST:
        raise HTTPException(status_code=400, detail="Trésorerie insuffisante")
    day = game_date(session)
    record(
        session,
        me,
        TransactionCategory.TRANSFER,
        f"Rapport de recruteur · {row.first_name} {row.last_name}",
        -REPORT_COST,
        day,
    )
    session.add(ScoutReportRow(club_id=me.id, player_id=player_id, requested_on=day))
    session.commit()
    names = {club.id: club.name for club in session.scalars(select(ClubRow))}
    return Knowledge(session).player_out(row.to_domain(), day, names)
