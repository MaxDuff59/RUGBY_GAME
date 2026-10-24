"""Entraînement du club dirigé : le rythme et le thème de la semaine (engine/training.py),
et qui progresse cette saison (engine/development.py)."""

from fastapi import APIRouter
from sqlalchemy.orm import Session

from api.deps import SessionDep, load_my_club_row
from api.ledger import game_date
from api.schemas import (
    IntensityOptionOut,
    PlayerOut,
    ThemeOptionOut,
    TrainingIn,
    TrainingOut,
)
from engine.development import OWN_UNCERTAINTY
from engine.training import FOCUS, RHYTHMS, plan_of
from models.orm import ClubRow

router = APIRouter(prefix="/training", tags=["entraînement"])


def _overview(session: Session, row: ClubRow) -> TrainingOut:
    day = game_date(session)
    club = row.to_domain()
    plan = plan_of(club)
    return TrainingOut(
        intensity=plan.intensity,
        theme=plan.theme,
        intensities=[
            IntensityOptionOut(
                key=key, pace=rhythm.pace, freshness=rhythm.freshness, injuries=rhythm.injuries
            )
            for key, rhythm in RHYTHMS.items()
        ],
        themes=[ThemeOptionOut(key=key, focus=list(focus)) for key, focus in FOCUS.items()],
        training_level=club.facilities.training_level,
        academy_level=club.facilities.academy_level,
        players=[
            PlayerOut.from_player(p, day, uncertainty=OWN_UNCERTAINTY)
            for p in [*club.players, *club.youths]
        ],
    )


@router.get("", response_model=TrainingOut)
def get_training(session: SessionDep) -> TrainingOut:
    """La semaine d'entraînement en cours, les choix possibles et la progression des joueurs."""
    return _overview(session, load_my_club_row(session))


@router.put("", response_model=TrainingOut)
def set_training(payload: TrainingIn, session: SessionDep) -> TrainingOut:
    """Change le rythme et (ou) le thème, valables chaque semaine jusqu'au prochain choix."""
    row = load_my_club_row(session)
    if payload.intensity is not None:
        row.training_intensity = payload.intensity.value
    if payload.theme is not None:
        row.training_theme = payload.theme.value
    session.commit()
    return _overview(session, row)
