"""Infrastructures du club dirigé par le joueur : stade, centre d'entraînement, formation."""

from fastapi import APIRouter, HTTPException

from api.deps import SessionDep, load_my_club_row
from api.ledger import game_date, record
from api.schemas import (
    AmenityIn,
    AmenityOut,
    DealOut,
    DealsIn,
    FacilitiesOut,
    FacilitiesOverview,
    Jersey,
    JerseyKind,
    JerseysOut,
    SponsorOut,
    SponsorsOut,
    StadiumOut,
    StandOut,
    UpgradeOut,
)
from engine.economy import (
    AMENITIES,
    STAND_LABELS,
    THIRD_KIT_COST,
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
from engine.sponsors import (
    CROWDED_MOOD,
    IMAGE_LABELS,
    IMAGE_MOOD,
    MAX_DEALS,
    PLACEMENT_LABELS,
    PLACEMENT_SHARE,
    SPONSORS,
    Deal,
    deal_refusal,
    deals_from,
    jersey_revenue,
    sponsor_mood,
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


def _sponsors(club: ClubRow) -> SponsorsOut:
    deals = deals_from(club.sponsors)
    return SponsorsOut(
        deals=[
            DealOut(sponsor=d.sponsor, placement=d.placement, revenue=d.revenue()) for d in deals
        ],
        library=[
            SponsorOut(
                id=s.id,
                name=s.name,
                sector=s.sector,
                budget=s.budget,
                image=s.image,
                image_label=IMAGE_LABELS[s.image],
                mood=IMAGE_MOOD[s.image],
                logo=s.logo,
            )
            for s in SPONSORS.values()
        ],
        placements=PLACEMENT_LABELS,
        shares=PLACEMENT_SHARE,
        max_deals=MAX_DEALS,
        revenue=jersey_revenue(deals),
        mood=sponsor_mood(deals),
        crowded_mood=CROWDED_MOOD,
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
        jerseys=JerseysOut(
            **{kind: Jersey(**data) for kind, data in (club.jerseys or {}).items()},
            third_kit=club.third_kit,
            third_kit_cost=THIRD_KIT_COST,
            third_kit_affordable=club.balance >= THIRD_KIT_COST,
        ),
        sponsors=_sponsors(club),
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


JERSEY_LABELS = {"home": "domicile", "away": "extérieur", "third": "third"}


def _check_kit(club: ClubRow, kind: JerseyKind) -> None:
    if kind == "third" and not club.third_kit:
        raise HTTPException(status_code=400, detail="Le maillot third n'est pas encore acheté")


@router.put("/jerseys/{kind}", response_model=FacilitiesOverview)
def save_jersey(kind: JerseyKind, body: Jersey, session: SessionDep) -> FacilitiesOverview:
    """Enregistre le maillot dessiné pour une tenue (gratuit, modifiable à volonté)."""
    club = load_my_club_row(session)
    _check_kit(club, kind)
    club.jerseys = {**(club.jerseys or {}), kind: body.model_dump()}
    session.commit()
    return _overview(club)


@router.delete("/jerseys/{kind}", response_model=FacilitiesOverview)
def reset_jersey(kind: JerseyKind, session: SessionDep) -> FacilitiesOverview:
    """Revient au maillot aux couleurs du club pour cette tenue."""
    club = load_my_club_row(session)
    _check_kit(club, kind)
    club.jerseys = {k: v for k, v in (club.jerseys or {}).items() if k != kind}
    session.commit()
    return _overview(club)


@router.post("/jerseys/third/buy", response_model=FacilitiesOverview)
def buy_third_kit(session: SessionDep) -> FacilitiesOverview:
    """Achète le maillot third, qu'on peut ensuite dessiner comme les autres."""
    club = load_my_club_row(session)
    if club.third_kit:
        raise HTTPException(status_code=400, detail="Maillot third déjà acheté")
    if club.balance < THIRD_KIT_COST:
        raise HTTPException(status_code=400, detail="Trésorerie insuffisante")
    club.third_kit = True
    record(
        session,
        club,
        TransactionCategory.FACILITIES,
        "Maillot third",
        -THIRD_KIT_COST,
        game_date(session),
    )
    session.commit()
    return _overview(club)


@router.put("/sponsors", response_model=FacilitiesOverview)
def set_sponsors(body: DealsIn, session: SessionDep) -> FacilitiesOverview:
    """Remplace les sponsors du maillot (au plus MAX_DEALS, un par emplacement). Les
    contrats sont sans engagement : ils se changent à tout moment."""
    club = load_my_club_row(session)
    deals = [Deal(d.sponsor, d.placement) for d in body.deals]
    refusal = deal_refusal(deals)
    if refusal is not None:
        raise HTTPException(status_code=400, detail=refusal)
    club.sponsors = [{"sponsor": d.sponsor, "placement": d.placement.value} for d in deals]
    session.commit()
    return _overview(club)
