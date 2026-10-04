"""Intersaison : vieillissement, progression, retraites, et vie du centre de formation."""

import random
from collections.abc import Iterator

from data.generator import FIRST_SEASON_YEAR, generate_youth_player, youth_level
from models import (
    ATTRIBUTE_MAX,
    ATTRIBUTE_MIN,
    ATTRIBUTE_NAMES,
    YOUTH_EXIT_AGE,
    Club,
    Player,
    Position,
)

RETIREMENT_AGE = 36

# Jeunes qui entrent au centre chaque intersaison : une base, plus un par niveau du centre.
INTAKE_BASE = 2
INTAKE_PER_ACADEMY_LEVEL = 1
INTAKE_AGES = (16, 17)

# Progression annuelle (points d'attributs gagnés ou perdus) selon l'âge, puis
# bonus des infrastructures : centre de formation pour les espoirs, centre
# d'entraînement pour les pros (+1 point à partir du niveau 3, +2 au niveau 5).
GROWTH_BY_AGE = [(20, (2, 4)), (23, (1, 3)), (29, (0, 1)), (32, (0, 0)), (99, (-2, -1))]
FACILITY_BONUS = {1: 0, 2: 0, 3: 1, 4: 1, 5: 2}


def age_players(club: Club) -> None:
    for player in club.players + club.youths:
        player.age += 1


def retirees(club: Club) -> list[Player]:
    """Pros qui raccrochent (à appeler après `age_players`)."""
    return [p for p in club.players if p.age >= RETIREMENT_AGE]


def youth_exits(club: Club) -> list[Player]:
    """Espoirs trop âgés pour rester au centre (à appeler après `age_players`)."""
    return [p for p in club.youths if p.age >= YOUTH_EXIT_AGE]


def growth_points(player: Player, facility_level: int, rng: random.Random) -> int:
    low, high = next(points for max_age, points in GROWTH_BY_AGE if player.age <= max_age)
    points = rng.randint(low, high)
    return points + FACILITY_BONUS[facility_level] if points > 0 else points


def develop_player(player: Player, facility_level: int, rng: random.Random) -> int:
    """Fait progresser (ou décliner) un joueur ; renvoie les points gagnés."""
    points = growth_points(player, facility_level, rng)
    step = 1 if points > 0 else -1
    for _ in range(abs(points)):
        name = rng.choice(ATTRIBUTE_NAMES)
        value = getattr(player, name) + step
        setattr(player, name, max(ATTRIBUTE_MIN, min(ATTRIBUTE_MAX, value)))
    return points


def develop_players(club: Club, rng: random.Random | None = None) -> None:
    """Progression de tout le club (à appeler après `age_players`)."""
    rng = rng or random.Random()
    for player in club.players:
        develop_player(player, club.facilities.training_level, rng)
    for youth in club.youths:
        develop_player(youth, club.facilities.academy_level, rng)


def youth_intake_size(academy_level: int) -> int:
    return INTAKE_BASE + INTAKE_PER_ACADEMY_LEVEL * academy_level


def youth_intake(
    club: Club,
    player_ids: Iterator[int],
    rng: random.Random | None = None,
    season_year: int = FIRST_SEASON_YEAR,
) -> list[Player]:
    """Nouveaux espoirs du centre, aux postes les moins fournis chez les espoirs."""
    rng = rng or random.Random()
    squad_level = sum(p.overall for p in club.players) / max(len(club.players), 1)
    level = youth_level(squad_level, club.facilities.academy_level)

    newcomers = []
    for _ in range(youth_intake_size(club.facilities.academy_level)):
        counts = {position: 0 for position in Position}
        for youth in club.youths + newcomers:
            counts[youth.position] += 1
        position = min(Position, key=lambda p: counts[p])
        newcomers.append(
            generate_youth_player(
                next(player_ids),
                position,
                level,
                club.id,
                rng,
                season_year,
                age=rng.randint(*INTAKE_AGES),
            )
        )
    return newcomers
