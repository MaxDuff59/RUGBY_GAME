"""Les règlements des championnats côté API (engine/regulations.py) : ce qui bloque
une signature, une prolongation ou une promotion."""

from fastapi import HTTPException

from engine.regulations import cap_breach
from models import Club


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
