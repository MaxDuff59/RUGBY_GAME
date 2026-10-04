"""Fixtures pytest partagées."""

import random

import pytest

from data.generator import SQUAD_COMPOSITION, generate_player
from models import Club


def make_club(club_id: int, level: float, seed: int = 0) -> Club:
    """Club complet (31 joueurs) dont tous les joueurs tournent autour de `level`."""
    rng = random.Random(seed)
    club = Club(id=club_id, name=f"Club {club_id}")
    player_id = club_id * 100
    for position, size in SQUAD_COMPOSITION.items():
        for _ in range(size):
            player_id += 1
            club.players.append(generate_player(player_id, position, level, club_id, rng))
    return club


@pytest.fixture
def even_clubs() -> tuple[Club, Club]:
    """Deux clubs de même niveau."""
    return make_club(1, level=12, seed=1), make_club(2, level=12, seed=2)


@pytest.fixture
def strong_and_weak() -> tuple[Club, Club]:
    """Un club nettement plus fort que l'autre."""
    return make_club(1, level=15, seed=1), make_club(2, level=9, seed=2)
