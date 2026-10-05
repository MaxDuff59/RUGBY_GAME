"""Infrastructures du club dirigé par le joueur : stade, centre d'entraînement, formation."""

from fastapi import APIRouter, HTTPException

from api.deps import SessionDep, load_my_club_row
from api.ledger import game_date, record
from api.schemas import (
    AmenityIn,
    AmenityOut,
    FacilitiesOut,
    FacilitiesOverview,
    StadiumOut,
    StandOut,
    UpgradeOut,
)
from engine.economy import (
    AMENITIES,
    STAND_LABELS,
    FacilityKind,
    TransactionCategory,
    add_amenity,
    amenity_count,
    amenity_refusal,
    apply_upgrade,
    next_stadium_step,
    stand_slots,
    upgrade_cost,
)
from models import Facilities, StandSide
from models.orm import ClubRow

router = APIRouter(prefix="/facilities", tags=["infrastructures"])

FACILITY_LABELS = {
    FacilityKind.STADIUM: "Stade",
    FacilityKind.TRAINING: "Centre d'entraînement",
    FacilityKind.ACADEMY: "Centre de formation",
}


def _facilities(club: ClubRow) -> Facilities:
    return club.facilities()


def _stadium(facilities: Facilities) -> StadiumOut:
    slots = stand_slots(facilities.stadium_capacity)
    return StadiumOut(
        capacity=facilities.stadium_capacity,
        stands=[
            StandOut(
                side=side,
                label=STAND_LABELS[side],
                slots=slots,
                amenities=list(facilities.stands.get(side, [])),
            )
            for side in StandSide
        ],
        catalogue=[
            AmenityOut(
                kind=amenity.kind,
                label=amenity.label,
                cost=amenity.cost,
                effect=amenity.effect(),
                installed=amenity_count(facilities, amenity.kind),
                stadium_max=amenity.stadium_max,
            )
            for amenity in AMENITIES.values()
        ],
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
        stadium=_stadium(facilities),
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
    club.save_facilities(facilities)
    session.commit()
    return _overview(club)


@router.post("/stadium/stands/{side}/amenities", response_model=FacilitiesOverview)
def install_amenity(side: StandSide, body: AmenityIn, session: SessionDep) -> FacilitiesOverview:
    """Installe un aménagement (panneau sponsor, buvette, loges…) dans une tribune."""
    club = load_my_club_row(session)
    facilities = _facilities(club)
    amenity = AMENITIES[body.kind]
    refusal = amenity_refusal(facilities, side, body.kind)
    if refusal is not None:
        raise HTTPException(status_code=400, detail=refusal)
    if club.balance < amenity.cost:
        raise HTTPException(status_code=400, detail="Trésorerie insuffisante")

    add_amenity(facilities, side, body.kind)
    record(
        session,
        club,
        TransactionCategory.FACILITIES,
        f"Stade · {STAND_LABELS[side]} · {amenity.label}",
        -amenity.cost,
        game_date(session),
    )
    club.save_facilities(facilities)
    session.commit()
    return _overview(club)
