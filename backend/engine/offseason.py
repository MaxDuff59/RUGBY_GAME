"""Intersaison : vieillissement, retraites et jeunes issus du centre de formation."""

import random
from collections.abc import Iterator

from data.generator import FIRST_SEASON_YEAR, generate_player
from models import Club, Player, Position

RETIREMENT_AGE = 36

# Âge des jeunes qui sortent du centre de formation.
YOUTH_AGES = (18, 20)
# Les jeunes arrivent sous le niveau moyen de l'effectif ; un bon centre réduit l'écart.
YOUTH_LEVEL_GAP = 3.0
YOUTH_LEVEL_PER_ACADEMY_LEVEL = 0.4
# Un jeune signe pour trois saisons.
YOUTH_CONTRACT_YEARS = 3


def age_players(club: Club) -> None:
    for player in club.players:
        player.age += 1


def retirees(club: Club) -> list[Player]:
    """Joueurs qui raccrochent (à appeler après `age_players`)."""
    return [p for p in club.players if p.age >= RETIREMENT_AGE]


def youth_intake_size(academy_level: int) -> int:
    """Nombre de jeunes formés par saison : un par niveau du centre."""
    return academy_level


def generate_youth(
    club: Club,
    player_ids: Iterator[int],
    rng: random.Random | None = None,
    season_year: int = FIRST_SEASON_YEAR,
) -> list[Player]:
    """Jeunes issus de la formation, aux postes les moins fournis de l'effectif."""
    rng = rng or random.Random()
    squad_level = sum(p.overall for p in club.players) / max(len(club.players), 1)
    level = (
        squad_level
        - YOUTH_LEVEL_GAP
        + YOUTH_LEVEL_PER_ACADEMY_LEVEL * club.facilities.academy_level
    )

    youths = []
    for _ in range(youth_intake_size(club.facilities.academy_level)):
        # Poste où le club a le moins de joueurs (jeunes déjà créés compris).
        counts = {position: len(club.players_at(position)) for position in Position}
        for youth in youths:
            counts[youth.position] += 1
        position = min(Position, key=lambda p: counts[p])
        youth = generate_player(next(player_ids), position, level, club.id, rng)
        youth.age = rng.randint(*YOUTH_AGES)
        youth.contract_until = season_year + YOUTH_CONTRACT_YEARS - 1
        youths.append(youth)
    return youths
