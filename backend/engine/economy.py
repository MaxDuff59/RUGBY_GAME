"""Règles économiques : valeur des joueurs, salaires, staff, infrastructures.

Tous les montants sont en euros. Comme le reste du moteur, ce module ne dépend
ni de FastAPI ni de la base de données.
"""

from enum import StrEnum

from models import Club, Facilities, Player, StaffMember

# --- Joueurs -------------------------------------------------------------------------

# Valeur marchande : 100 k€ pour une note de 10, multipliée par 1,6 à chaque point.
# Note 8 -> ~40 k€, 12 -> ~255 k€, 14 -> ~655 k€, 16 -> ~1,7 M€, 18 -> ~4,3 M€.
VALUE_AT_TEN = 100_000
VALUE_GROWTH_PER_POINT = 1.6

# Un jeune vaut plus (marge de progression), un trentenaire moins.
AGE_FACTORS = [(23, 1.3), (29, 1.0), (32, 0.7), (99, 0.45)]

# Salaire annuel : part de la valeur marchande, avec un plancher.
WAGE_SHARE_OF_VALUE = 0.3
WAGE_MIN = 40_000

# Un club vend au prix de la valeur et achète avec une marge pour le vendeur.
ASKING_PRICE_MARKUP = 1.25

# Taille d'effectif autorisée.
SQUAD_MIN = 25
SQUAD_MAX = 35


def _round_to(value: float, step: int) -> int:
    return int(round(value / step) * step)


def market_value(player: Player) -> int:
    """Valeur marchande d'un joueur, arrondie aux 5 k€."""
    base = VALUE_AT_TEN * VALUE_GROWTH_PER_POINT ** (player.overall - 10)
    factor = next(f for max_age, f in AGE_FACTORS if player.age <= max_age)
    return max(5_000, _round_to(base * factor, 5_000))


def wage_for(player: Player, noise: float = 1.0) -> int:
    """Salaire annuel cohérent avec la valeur (`noise` : écart négocié, ex. 0.9 à 1.15)."""
    return max(WAGE_MIN, _round_to(market_value(player) * WAGE_SHARE_OF_VALUE * noise, 1_000))


def asking_price(player: Player) -> int:
    """Prix demandé par le club vendeur."""
    return _round_to(market_value(player) * ASKING_PRICE_MARKUP, 5_000)


def sale_price(player: Player) -> int:
    """Ce que rapporte la vente d'un de ses joueurs."""
    return market_value(player)


# --- Staff ---------------------------------------------------------------------------

# Salaire annuel selon le niveau (1 à 5 étoiles).
STAFF_WAGE_BY_LEVEL = {1: 40_000, 2: 70_000, 3: 110_000, 4: 170_000, 5: 250_000}

# Licencier coûte une indemnité : la moitié du salaire annuel.
SEVERANCE_SHARE = 0.5


def staff_wage(level: int) -> int:
    return STAFF_WAGE_BY_LEVEL[level]


def severance(member: StaffMember) -> int:
    return int(member.wage * SEVERANCE_SHARE)


# --- Infrastructures -----------------------------------------------------------------


class FacilityKind(StrEnum):
    STADIUM = "stadium"
    TRAINING = "training"
    ACADEMY = "academy"


# Paliers de capacité du stade, et coût pour passer au palier suivant.
STADIUM_STEPS = [4_000, 6_000, 9_000, 12_000, 16_000, 20_000]
STADIUM_UPGRADE_COSTS = [1_500_000, 2_500_000, 3_500_000, 5_000_000, 7_000_000]

FACILITY_LEVEL_MAX = 5
# Centre d'entraînement et de formation : coût = 800 k€ x niveau visé.
FACILITY_UPGRADE_COST_PER_LEVEL = 800_000


def upgrade_cost(facilities: Facilities, kind: FacilityKind) -> int | None:
    """Coût de l'amélioration suivante, ou None si le maximum est atteint."""
    if kind == FacilityKind.STADIUM:
        step = STADIUM_STEPS.index(facilities.stadium_capacity)
        return STADIUM_UPGRADE_COSTS[step] if step < len(STADIUM_UPGRADE_COSTS) else None

    level = facilities.training_level if kind == FacilityKind.TRAINING else facilities.academy_level
    if level >= FACILITY_LEVEL_MAX:
        return None
    return FACILITY_UPGRADE_COST_PER_LEVEL * (level + 1)


def apply_upgrade(facilities: Facilities, kind: FacilityKind) -> None:
    """Passe une infrastructure au palier suivant (le paiement est fait par l'appelant)."""
    if kind == FacilityKind.STADIUM:
        step = STADIUM_STEPS.index(facilities.stadium_capacity)
        facilities.stadium_capacity = STADIUM_STEPS[step + 1]
    elif kind == FacilityKind.TRAINING:
        facilities.training_level += 1
    else:
        facilities.academy_level += 1


# --- Club ----------------------------------------------------------------------------


def squad_value(club: Club) -> int:
    return sum(market_value(p) for p in club.players)
