"""Infrastructures du club dirigé par le joueur : stade, centre d'entraînement, formation."""

from fastapi import APIRouter, HTTPException

from api.deps import SessionDep, load_my_club_row
from api.ledger import game_date, record
from api.schemas import FacilitiesOut, FacilitiesOverview, UpgradeOut
from engine.economy import (
    FacilityKind,
    TransactionCategory,
    apply_upgrade,
    next_stadium_step,
    upgrade_cost,
)
from models import Facilities
from models.orm import ClubRow

router = APIRouter(prefix="/facilities", tags=["infrastructures"])

FACILITY_LABELS = {
    FacilityKind.STADIUM: "Stade",
    FacilityKind.TRAINING: "Centre d'entraînement",
    FacilityKind.ACADEMY: "Centre de formation",
}


def _facilities(club: ClubRow) -> Facilities:
    return Facilities(
        stadium_capacity=club.stadium_capacity,
        training_level=club.training_level,
        academy_level=club.academy_level,
    )


def _overview(club: ClubRow) -> FacilitiesOverview:
    facilities = _facilities(club)
    upgrades = []
    for kind in FacilityKind:
        cost = upgrade_cost(facilities, kind)
        if kind == FacilityKind.STADIUM:
            current = facilities.stadium_capacity
            next_value = next_stadium_step(current)
        else:
            current = (
                facilities.training_level
                if kind == FacilityKind.TRAINING
                else facilities.academy_level
            )
            next_value = current + 1 if cost is not None else None
        upgrades.append(
            UpgradeOut(
                kind=kind,
                current=current,
                next=next_value,
                cost=cost,
                affordable=cost is not None and club.balance >= cost,
            )
        )
    return FacilitiesOverview(
        balance=club.balance,
        facilities=FacilitiesOut.model_validate(facilities),
        upgrades=upgrades,
    )


@router.get("", response_model=FacilitiesOverview)
def get_facilities(session: SessionDep) -> FacilitiesOverview:
    return _overview(load_my_club_row(session))


@router.post("/{kind}/upgrade", response_model=FacilitiesOverview)
def upgrade(kind: FacilityKind, session: SessionDep) -> FacilitiesOverview:
    """Passe une infrastructure au palier suivant, en payant son coût."""
    club = load_my_club_row(session)
    facilities = _facilities(club)
    cost = upgrade_cost(facilities, kind)
    if cost is None:
        raise HTTPException(status_code=400, detail="Niveau maximum déjà atteint")
    if club.balance < cost:
        raise HTTPException(status_code=400, detail="Trésorerie insuffisante")

    apply_upgrade(facilities, kind)
    if kind == FacilityKind.STADIUM:
        detail = f"{facilities.stadium_capacity:,} places".replace(",", " ")
    else:
        level = (
            facilities.training_level if kind == FacilityKind.TRAINING else facilities.academy_level
        )
        detail = f"niveau {level}"
    record(
        session,
        club,
        TransactionCategory.FACILITIES,
        f"{FACILITY_LABELS[kind]} · {detail}",
        -cost,
        game_date(session),
    )
    club.stadium_capacity = facilities.stadium_capacity
    club.training_level = facilities.training_level
    club.academy_level = facilities.academy_level
    session.commit()
    return _overview(club)
