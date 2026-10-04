"""Staff du club dirigé par le joueur : voir, embaucher, licencier.

Un seul membre par poste. Pour en changer, on licencie (avec indemnité) puis
on embauche parmi les candidats sans club.
"""

from fastapi import APIRouter, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from api.deps import SessionDep, load_my_club_row
from api.schemas import StaffMemberOut, StaffOverview, StaffSlotOut
from engine.economy import severance
from models import StaffRole
from models.orm import ClubRow, StaffRow

router = APIRouter(prefix="/staff", tags=["staff"])


def _overview(session: Session, club: ClubRow) -> StaffOverview:
    by_role = {StaffRole(row.role): row for row in club.staff}
    candidates = session.scalars(
        select(StaffRow)
        .where(StaffRow.club_id.is_(None))
        .order_by(StaffRow.role, StaffRow.level.desc())
    )
    return StaffOverview(
        balance=club.balance,
        slots=[_slot(role, by_role.get(role)) for role in StaffRole],
        candidates=[StaffMemberOut.model_validate(row.to_domain()) for row in candidates],
    )


def _slot(role: StaffRole, row: StaffRow | None) -> StaffSlotOut:
    """Emplacement d'un poste : son titulaire (ou personne) et l'indemnité de licenciement."""
    if row is None:
        return StaffSlotOut(role=role, member=None, severance=None)
    member = row.to_domain()
    return StaffSlotOut(
        role=role, member=StaffMemberOut.model_validate(member), severance=severance(member)
    )


@router.get("", response_model=StaffOverview)
def get_staff(session: SessionDep) -> StaffOverview:
    """Staff en place (un emplacement par poste) et candidats disponibles."""
    return _overview(session, load_my_club_row(session))


@router.post("/hire/{staff_id}", response_model=StaffOverview)
def hire(staff_id: int, session: SessionDep) -> StaffOverview:
    """Embauche un candidat sans club, si son poste est vacant."""
    club = load_my_club_row(session)
    candidate = session.get(StaffRow, staff_id)
    if candidate is None or candidate.club_id is not None:
        raise HTTPException(status_code=404, detail="Candidat introuvable ou déjà sous contrat")
    if any(row.role == candidate.role for row in club.staff):
        raise HTTPException(status_code=400, detail="Ce poste est déjà pourvu : licencie d'abord")

    candidate.club_id = club.id
    session.commit()
    session.refresh(club)
    return _overview(session, club)


@router.post("/{staff_id}/fire", response_model=StaffOverview)
def fire(staff_id: int, session: SessionDep) -> StaffOverview:
    """Licencie un membre de son staff, contre une indemnité."""
    club = load_my_club_row(session)
    member = session.get(StaffRow, staff_id)
    if member is None or member.club_id != club.id:
        raise HTTPException(status_code=404, detail="Ce membre ne fait pas partie de ton staff")

    cost = severance(member.to_domain())
    if club.balance < cost:
        raise HTTPException(status_code=400, detail="Trésorerie insuffisante pour l'indemnité")

    club.balance -= cost
    member.club_id = None  # il redevient disponible sur le marché
    session.commit()
    session.refresh(club)
    return _overview(session, club)
