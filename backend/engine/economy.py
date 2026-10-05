"""Règles économiques : valeur des joueurs, salaires, staff, infrastructures.

Tous les montants sont en euros. Comme le reste du moteur, ce module ne dépend
ni de FastAPI ni de la base de données.
"""

import random
from dataclasses import dataclass
from enum import StrEnum

from engine.supporters import NEUTRAL as FANS_NEUTRAL
from models import AmenityKind, Club, Facilities, Player, StaffMember, Stage, StandSide

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


# Paliers de capacité du stade, et coût pour atteindre chacun. Un stade réel
# peut avoir une capacité entre deux paliers : on agrandit alors au suivant.
STADIUM_STEPS = [4_000, 6_000, 9_000, 12_000, 16_000, 20_000, 25_000, 30_000, 35_000]
STADIUM_UPGRADE_COSTS = {
    6_000: 1_500_000,
    9_000: 2_500_000,
    12_000: 3_500_000,
    16_000: 5_000_000,
    20_000: 7_000_000,
    25_000: 10_000_000,
    30_000: 14_000_000,
    35_000: 20_000_000,
}

FACILITY_LEVEL_MAX = 5
# Centre d'entraînement et de formation : coût = 800 k€ x niveau visé.
FACILITY_UPGRADE_COST_PER_LEVEL = 800_000


def next_stadium_step(capacity: int) -> int | None:
    """Palier de capacité suivant, ou None si le stade est déjà au maximum."""
    return next((step for step in STADIUM_STEPS if step > capacity), None)


def upgrade_cost(facilities: Facilities, kind: FacilityKind) -> int | None:
    """Coût de l'amélioration suivante, ou None si le maximum est atteint."""
    if kind == FacilityKind.STADIUM:
        step = next_stadium_step(facilities.stadium_capacity)
        return STADIUM_UPGRADE_COSTS[step] if step is not None else None

    level = facilities.training_level if kind == FacilityKind.TRAINING else facilities.academy_level
    if level >= FACILITY_LEVEL_MAX:
        return None
    return FACILITY_UPGRADE_COST_PER_LEVEL * (level + 1)


def apply_upgrade(facilities: Facilities, kind: FacilityKind) -> None:
    """Passe une infrastructure au palier suivant (le paiement est fait par l'appelant)."""
    if kind == FacilityKind.STADIUM:
        facilities.stadium_capacity = next_stadium_step(facilities.stadium_capacity)
    elif kind == FacilityKind.TRAINING:
        facilities.training_level += 1
    else:
        facilities.academy_level += 1


# --- Aménagements des tribunes -------------------------------------------------------

STAND_LABELS = {
    StandSide.NORTH: "Tribune nord",
    StandSide.SOUTH: "Tribune sud",
    StandSide.EAST: "Tribune est",
    StandSide.WEST: "Tribune ouest",
}

# Emplacements par tribune : 2 dans un petit stade, un de plus par tranche de 10 000 places.
STAND_SLOTS_BASE = 2
STAND_SLOTS_PER_SEATS = 10_000

# Taux de remplissage gagné grâce à l'écran géant.
SCREEN_ATTENDANCE_BONUS = 0.03


@dataclass(frozen=True)
class Amenity:
    """Un aménagement du catalogue : son prix et ce qu'il rapporte."""

    kind: AmenityKind
    label: str
    cost: int
    per_matchday: int = 0  # recette fixe à chaque match à domicile
    per_spectator: int = 0  # recette par spectateur à chaque match à domicile
    stadium_max: int | None = None  # nombre maximal dans tout le stade (None : un par emplacement)
    attendance_bonus: float = 0.0  # remplissage du stade

    def effect(self) -> str:
        if self.attendance_bonus:
            return f"+{round(self.attendance_bonus * 100)} % de remplissage"
        if self.per_spectator:
            return f"+{self.per_spectator} € par spectateur"
        when = "par journée" if self.kind == AmenityKind.SPONSOR else "par match à domicile"
        return f"+{self.per_matchday:,} € {when}".replace(",", " ")


AMENITIES = {
    amenity.kind: amenity
    for amenity in (
        Amenity(AmenityKind.SPONSOR, "Panneau sponsor", 200_000, per_matchday=6_000),
        Amenity(AmenityKind.BUVETTE, "Buvette", 120_000, per_spectator=2),
        Amenity(AmenityKind.SHOP, "Boutique du club", 350_000, per_spectator=3, stadium_max=1),
        Amenity(AmenityKind.BOXES, "Loges", 1_000_000, per_matchday=25_000, stadium_max=2),
        Amenity(
            AmenityKind.SCREEN,
            "Écran géant",
            500_000,
            stadium_max=1,
            attendance_bonus=SCREEN_ATTENDANCE_BONUS,
        ),
    )
}


def stand_slots(capacity: int) -> int:
    """Emplacements disponibles dans chaque tribune, selon la taille du stade."""
    return STAND_SLOTS_BASE + capacity // STAND_SLOTS_PER_SEATS


def amenity_count(facilities: Facilities, kind: AmenityKind) -> int:
    return sum(installed.count(kind) for installed in facilities.stands.values())


def amenity_refusal(facilities: Facilities, side: StandSide, kind: AmenityKind) -> str | None:
    """Pourquoi on ne peut pas installer cet aménagement dans cette tribune (None : on peut)."""
    amenity = AMENITIES[kind]
    if len(facilities.stands.get(side, [])) >= stand_slots(facilities.stadium_capacity):
        return "Tribune complète : agrandis le stade pour gagner des emplacements"
    if amenity.stadium_max is not None and amenity_count(facilities, kind) >= amenity.stadium_max:
        return "Déjà installé" if amenity.stadium_max == 1 else f"{amenity.stadium_max} au maximum"
    return None


def add_amenity(facilities: Facilities, side: StandSide, kind: AmenityKind) -> None:
    """Installe un aménagement (le paiement et la vérification sont faits par l'appelant)."""
    facilities.amenities(side).append(kind)


def _installed(facilities: Facilities) -> list[Amenity]:
    return [AMENITIES[kind] for installed in facilities.stands.values() for kind in installed]


def attendance_bonus(facilities: Facilities) -> float:
    """Remplissage gagné grâce aux aménagements (écran géant)."""
    return sum(a.attendance_bonus for a in _installed(facilities))


def hospitality_revenue(facilities: Facilities, spectators: int) -> int:
    """Buvettes, boutique et loges : ce qu'elles rapportent sur un match à domicile."""
    return sum(
        a.per_matchday + a.per_spectator * spectators
        for a in _installed(facilities)
        if a.kind != AmenityKind.SPONSOR
    )


# --- Club ----------------------------------------------------------------------------


def squad_value(club: Club) -> int:
    return sum(market_value(p) for p in club.players)


# --- Recettes et dépenses d'une journée ---------------------------------------------


class TransactionCategory(StrEnum):
    """Domaine d'une opération financière."""

    TICKETING = "ticketing"  # billetterie
    SPONSORS = "sponsors"
    WAGES = "wages"  # salaires joueurs + staff
    TRANSFER = "transfer"
    STAFF = "staff"  # embauches, indemnités
    FACILITIES = "facilities"
    PRIZE = "prize"  # primes de phases finales
    MEDICAL = "medical"  # soins (protocole accéléré)
    AFFAIRS = "affairs"  # vie du club : amendes, primes, séjours (engine/affairs.py)
    HOSPITALITY = "hospitality"  # buvettes, boutique et loges du stade


TICKET_PRICE = 30
# Taux de remplissage : 60 % pour le dernier, jusqu'à 90 % pour le premier, ± 5 % de hasard.
ATTENDANCE_BASE = 0.6
ATTENDANCE_RANK_BONUS = 0.3
ATTENDANCE_NOISE = 0.05
# Ferveur des supporters (engine/supporters.py) : +1,5 % de remplissage par point au-dessus
# de la note neutre, -1,5 % par point en dessous.
ATTENDANCE_PER_FERVOUR_POINT = 0.015

# Sponsors, par journée jouée : une part fixe et une part liée à la taille du stade.
SPONSOR_BASE = 30_000
SPONSOR_PER_SEAT = 4

# Primes des phases finales : par match disputé, et pour le champion.
PLAYOFF_PRIZES = {Stage.BARRAGE: 100_000, Stage.SEMI: 200_000, Stage.FINAL: 400_000}
CHAMPION_PRIZE = 600_000


def attendance(
    capacity: int,
    rank: int,
    club_count: int,
    playoff: bool = False,
    rng: random.Random | None = None,
    fervour: float = FANS_NEUTRAL,
    bonus: float = 0.0,
) -> int:
    """Spectateurs d'un match à domicile selon le classement, la ferveur des
    supporters et les aménagements du stade (`bonus`, voir `attendance_bonus`) ;
    stade plein en phase finale."""
    if playoff:
        return capacity
    rng = rng or random.Random()
    rank_share = 1 - (rank - 1) / max(club_count - 1, 1)  # 1 pour le premier, 0 pour le dernier
    rate = (
        ATTENDANCE_BASE
        + ATTENDANCE_RANK_BONUS * rank_share
        + ATTENDANCE_PER_FERVOUR_POINT * (fervour - FANS_NEUTRAL)
        + bonus
        + rng.uniform(-1, 1) * ATTENDANCE_NOISE
    )
    return int(capacity * min(max(rate, 0.0), 1.0))


def ticketing_revenue(spectators: int) -> int:
    return spectators * TICKET_PRICE


def sponsor_revenue(facilities: Facilities) -> int:
    """Part fixe, part liée au stade, et les panneaux installés dans les tribunes."""
    boards = amenity_count(facilities, AmenityKind.SPONSOR)
    return (
        SPONSOR_BASE
        + SPONSOR_PER_SEAT * facilities.stadium_capacity
        + boards * AMENITIES[AmenityKind.SPONSOR].per_matchday
    )


def matchday_wages(club: Club, regular_matchdays: int) -> int:
    """Part des salaires annuels (pros, espoirs, staff) versée à chaque journée régulière."""
    return (club.player_wages + club.youth_wages + club.staff_wages) // regular_matchdays
