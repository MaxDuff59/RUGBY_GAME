"""Les règles côté API : celles des championnats (engine/regulations.py), qui bloquent
une signature, une prolongation ou une promotion, et le niveau de difficulté de la
carrière (engine/difficulty.py)."""

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from engine.difficulty import Rules, rules
from engine.regulations import cap_breach
from models import Club
from models.orm import CareerRow


def career_rules(session: Session) -> Rules:
    """Les règles du niveau de difficulté de la carrière (normal sans carrière de club)."""
    career = session.scalars(select(CareerRow)).first()
    return rules(career.difficulty if career is not None else None)


def _millions(euros: int) -> str:
    return f"{euros / 1_000_000:.2f}".replace(".", ",") + " M€"


def check_salary_cap(club: Club, extra: int) -> None:
    """Refuse (400) ce qui ferait dépasser le plafond salarial du championnat du club."""
    breach = cap_breach(club, extra)
    if breach is not None:
        after, cap = breach
        raise HTTPException(
            status_code=400,
            detail=(
                f"Plafond salarial : ta masse salariale passerait à {_millions(after)}, "
                f"pour un plafond de {_millions(cap)}."
            ),
        )
