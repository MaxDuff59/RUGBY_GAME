"""Grand livre : chaque mouvement d'argent passe par `record`.

C'est le seul endroit où la trésorerie d'un club change, pour que le solde et
l'historique des opérations restent toujours cohérents.
"""

from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from engine.economy import TransactionCategory
from models.orm import ClubRow, MatchRow, SeasonRow, TransactionRow


def record(
    session: Session,
    club: ClubRow,
    category: TransactionCategory,
    label: str,
    amount: int,
    day: date,
    matchday: int | None = None,
) -> TransactionRow:
    """Applique un mouvement (positif = recette, négatif = dépense) et l'inscrit au livre."""
    club.balance += amount
    row = TransactionRow(
        club_id=club.id,
        date=day,
        matchday=matchday,
        category=category.value,
        label=label,
        amount=amount,
        balance_after=club.balance,
    )
    session.add(row)
    return row


def game_date(session: Session) -> date:
    """Date « du jour » dans le jeu : celle de la prochaine journée à jouer.

    Sans match à venir (saison terminée) : la date du dernier match ; sans
    saison du tout : la date réelle.
    """
    next_match = session.scalars(
        select(MatchRow).where(MatchRow.home_score.is_(None)).order_by(MatchRow.date)
    ).first()
    if next_match is not None:
        return next_match.date
    last_match = session.scalars(select(MatchRow).order_by(MatchRow.date.desc())).first()
    if last_match is not None:
        return last_match.date
    return date.today()


def current_season(session: Session) -> SeasonRow | None:
    """La saison la plus récente."""
    return session.scalars(select(SeasonRow).order_by(SeasonRow.year.desc())).first()
