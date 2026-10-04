"""Règles médicales : gravité, durée, protocoles de soins, rechutes, entraînement.

Le moteur de match signale seulement qu'un joueur s'est blessé (événement
`INJURY`) ; c'est ici qu'on tire la blessure elle-même. Comme le reste du
moteur, ce module ne dépend ni de FastAPI ni de la base de données.
"""

import random
from collections.abc import Callable
from datetime import date, timedelta

from models import Club, Injury, InjurySeverity, InjurySource, Player, Protocol, StaffRole

# --- Gravité et nature de la blessure --------------------------------------------------

# Répartition des gravités selon l'origine : l'entraînement blesse moins gravement.
SEVERITY_WEIGHTS = {
    InjurySource.MATCH: {
        InjurySeverity.LIGHT: 0.60,
        InjurySeverity.MODERATE: 0.30,
        InjurySeverity.SEVERE: 0.10,
    },
    InjurySource.TRAINING: {
        InjurySeverity.LIGHT: 0.75,
        InjurySeverity.MODERATE: 0.22,
        InjurySeverity.SEVERE: 0.03,
    },
}

# Nature de la blessure et fourchette de durée (en semaines) pour chaque gravité.
INJURY_KINDS: dict[InjurySeverity, list[tuple[str, int, int]]] = {
    InjurySeverity.LIGHT: [
        ("contusion à la cuisse", 1, 2),
        ("entorse légère de la cheville", 1, 3),
        ("élongation des ischio-jambiers", 2, 3),
        ("commotion cérébrale", 2, 3),
        ("doigt luxé", 1, 2),
        ("côtes contusionnées", 2, 3),
    ],
    InjurySeverity.MODERATE: [
        ("déchirure des ischio-jambiers", 4, 7),
        ("entorse du genou", 5, 8),
        ("luxation de l'épaule", 6, 8),
        ("fracture de la main", 4, 6),
        ("déchirure du mollet", 4, 6),
        ("entorse de la cheville", 4, 7),
    ],
    InjurySeverity.SEVERE: [
        ("rupture des ligaments croisés", 26, 36),
        ("fracture de la jambe", 16, 24),
        ("rupture du tendon d'Achille", 24, 32),
        ("opération de l'épaule", 14, 20),
        ("hernie discale", 12, 18),
    ],
}

# --- Protocoles de soins ---------------------------------------------------------------

# Facteur sur la durée et risque de rechute par match (pendant FRAGILE_WEEKS).
PROTOCOL_DURATION_FACTOR = {
    Protocol.CAUTIOUS: 1.3,
    Protocol.STANDARD: 1.0,
    Protocol.ACCELERATED: 0.65,
}
PROTOCOL_RELAPSE_RISK = {
    Protocol.CAUTIOUS: 0.01,
    Protocol.STANDARD: 0.04,
    Protocol.ACCELERATED: 0.12,
}
# Le protocole accéléré se paie (clinique, spécialistes), selon la gravité.
ACCELERATED_COST = {
    InjurySeverity.LIGHT: 15_000,
    InjurySeverity.MODERATE: 50_000,
    InjurySeverity.SEVERE: 150_000,
}

# Staff : chaque niveau de kiné au-delà du premier raccourcit la convalescence ;
# chaque niveau de médecin réduit le risque de rechute.
PHYSIO_DURATION_PER_LEVEL = 0.05  # niveau 5 : -20 %
DOCTOR_RELAPSE_PER_LEVEL = 0.10  # niveau 5 : -40 %

# --- Fréquence des blessures -----------------------------------------------------------

# Pendant un match, par équipe et par minute : ~0,6 blessé par équipe et par match.
MATCH_INJURY_CHANCE_PER_MINUTE = 0.0075
# À l'entraînement, par joueur et par semaine : ~0,12 blessé par club et par semaine.
TRAINING_INJURY_CHANCE_PER_WEEK = 0.004


def roll_severity(source: InjurySource, rng: random.Random) -> InjurySeverity:
    weights = SEVERITY_WEIGHTS[source]
    return rng.choices(list(weights), weights=list(weights.values()))[0]


def roll_kind(severity: InjurySeverity, rng: random.Random) -> tuple[str, int]:
    """Nature de la blessure et durée médicale de base, en semaines."""
    kind, low, high = rng.choice(INJURY_KINDS[severity])
    return kind, rng.randint(low, high)


def planned_weeks(base_weeks: int, protocol: Protocol, physio_level: int) -> int:
    """Durée réelle d'indisponibilité, après protocole et niveau du kiné (1 semaine au moins)."""
    physio = 1 - PHYSIO_DURATION_PER_LEVEL * max(physio_level - 1, 0)
    return max(1, round(base_weeks * PROTOCOL_DURATION_FACTOR[protocol] * physio))


def relapse_risk(protocol: Protocol, doctor_level: int) -> float:
    """Probabilité de rechute à chaque match joué pendant la période de fragilité."""
    doctor = 1 - DOCTOR_RELAPSE_PER_LEVEL * max(doctor_level - 1, 0)
    return round(PROTOCOL_RELAPSE_RISK[protocol] * doctor, 4)


def protocol_cost(severity: InjurySeverity, protocol: Protocol) -> int:
    return ACCELERATED_COST[severity] if protocol == Protocol.ACCELERATED else 0


def apply_protocol(injury: Injury, protocol: Protocol, club: Club) -> None:
    """Fixe le protocole (définitif) et recalcule la date de retour et le risque de rechute.

    Le paiement éventuel est à la charge de l'appelant.
    """
    if injury.protocol_chosen:
        raise ValueError("Le protocole de cette blessure est déjà fixé")
    weeks = planned_weeks(injury.base_weeks, protocol, club.staff_level(StaffRole.PHYSIO))
    injury.protocol = protocol
    injury.protocol_chosen = True
    injury.return_date = injury.occurred_on + timedelta(weeks=weeks)
    injury.relapse_risk = relapse_risk(protocol, club.staff_level(StaffRole.DOCTOR))


def new_injury(
    player: Player,
    club: Club,
    source: InjurySource,
    day: date,
    rng: random.Random,
    decided: bool = True,
) -> Injury:
    """Tire une nouvelle blessure pour un joueur et la lui attache.

    Un joueur encore fragile rechute : même blessure que la précédente. Avec
    `decided=False`, le protocole reste à choisir par le manager (le protocole
    normal s'applique en attendant).
    """
    relapse = player.is_fragile(day)
    if relapse and player.injury is not None:
        severity, kind = player.injury.severity, player.injury.kind
        _, low, high = next(k for k in INJURY_KINDS[severity] if k[0] == kind)
        base_weeks = rng.randint(low, high)
    else:
        relapse = False
        severity = roll_severity(source, rng)
        kind, base_weeks = roll_kind(severity, rng)

    injury = Injury(
        player_id=player.id,
        severity=severity,
        kind=kind,
        source=source,
        occurred_on=day,
        base_weeks=base_weeks,
        return_date=day,  # recalculée juste en dessous
        protocol=Protocol.STANDARD,
        protocol_chosen=False,
        relapse=relapse,
    )
    apply_protocol(injury, Protocol.STANDARD, club)
    injury.protocol_chosen = decided
    player.injury = injury
    return injury


def training_injuries(
    club: Club,
    day: date,
    rng: random.Random,
    decided: bool = True,
    risk: Callable[[Player], float] = lambda player: 1.0,
) -> list[Injury]:
    """Blessures de la semaine d'entraînement qui précède `day` (souvent aucune).

    `risk` multiplie le risque de chaque joueur (la fatigue, voir engine/form.py).
    """
    injuries = []
    for player in club.available_players(day):
        if rng.random() < TRAINING_INJURY_CHANCE_PER_WEEK * risk(player):
            # Blessé dans la semaine, entre deux et cinq jours avant le match.
            occurred = day - timedelta(days=rng.randint(2, 5))
            injuries.append(new_injury(player, club, InjurySource.TRAINING, occurred, rng, decided))
    return injuries
