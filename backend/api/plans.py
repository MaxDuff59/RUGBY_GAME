"""Formule du compte : ce qu'un compte gratuit peut encore commencer (voir accounts.py).

Les refus répondent 402 (paiement requis) : l'interface propose alors le jeu complet,
payé une fois (api/billing.py).
"""

from fastapi import HTTPException

import accounts
from accounts import FREE_SAVES, FREE_SEASONS, User

PRICE_CENTS = 200
PRICE_LABEL = "2 €"
PAYMENT_REQUIRED = 402


def require_season(user: User) -> None:
    """Refuse de commencer une saison quand le compte gratuit les a toutes jouées."""
    if user.seasons_left == 0:
        raise HTTPException(
            status_code=PAYMENT_REQUIRED,
            detail=(
                f"Le compte gratuit s'arrête après {FREE_SEASONS} saisons, toutes carrières "
                f"confondues : passe au jeu complet ({PRICE_LABEL}) pour continuer."
            ),
        )


def require_new_save(user: User, saves: int) -> None:
    """Refuse une partie de plus au compte gratuit qui en a déjà `saves`."""
    require_season(user)
    if not user.premium and saves >= FREE_SAVES:
        raise HTTPException(
            status_code=PAYMENT_REQUIRED,
            detail=(
                "Le compte gratuit garde une seule partie : continue-la, ou passe au jeu "
                f"complet ({PRICE_LABEL}) pour en mener plusieurs."
            ),
        )


def count_season(user: User) -> None:
    """Une saison vient de commencer : elle compte, même si la partie est supprimée
    ensuite. Le jeu complet ne compte plus."""
    if not user.premium:
        accounts.count_season(user.id)
