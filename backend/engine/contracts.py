"""Fins de contrat : prolongations, et clubs concurrents qui signent les joueurs en fin de contrat.

Un contrat n'est plus renouvelé d'office : en dernière année, le club peut
prolonger son joueur, sinon il part libre à l'intersaison. Pendant la phase
retour, les clubs concurrents peuvent lui faire signer un pré-contrat : il est
alors perdu, quoi qu'on lui propose. Les meilleurs éléments de l'effectif sont
les plus convoités. Aucune dépendance à FastAPI ni à la base.
"""

import random

from data.generator import YOUTH_CONTRACT_YEARS, YOUTH_WAGE
from engine.economy import WAGE_MIN, wage_for
from engine.offseason import RETIREMENT_AGE
from engine.transfers import (
    TIME_BENCH,
    TIME_RESERVE,
    TIME_STARTER,
    club_level,
    move_appeal,
    playing_time,
    preferred_years,
    wage_demand,
)
from models import YOUTH_EXIT_AGE, Club, Player, Squad

# --- Situation en fin de saison ------------------------------------------------------


def retires_next_season(player: Player) -> bool:
    """Un pro qui aura l'âge de raccrocher à l'intersaison."""
    return player.squad == Squad.PRO and player.age + 1 >= RETIREMENT_AGE


def leaves_academy_next_season(player: Player) -> bool:
    """Un espoir trop âgé pour rester au centre la saison prochaine (sauf s'il passe pro)."""
    return player.squad == Squad.YOUTH and player.age + 1 >= YOUTH_EXIT_AGE


# --- Prolongation ----------------------------------------------------------------------

# Un titulaire sait ce qu'il vaut ; un réserviste se contente de moins.
RENEWAL_FACTOR = {TIME_STARTER: 1.1, TIME_BENCH: 1.0, TIME_RESERVE: 0.9}
# Il accepte une baisse de 10 % au plus, de 25 % passé 32 ans.
WAGE_CUT_FLOOR = 0.9
VETERAN_AGE = 32
VETERAN_CUT_FLOOR = 0.75


def renewal_wage(player: Player, club: Club) -> int:
    """Salaire annuel demandé pour prolonger (contrat espoir au tarif du centre)."""
    if player.squad == Squad.YOUTH:
        return YOUTH_WAGE
    fair = wage_for(player) * RENEWAL_FACTOR[playing_time(player, club)]
    floor = player.wage * (VETERAN_CUT_FLOOR if player.age > VETERAN_AGE else WAGE_CUT_FLOOR)
    return max(WAGE_MIN, int(round(max(fair, floor) / 1_000) * 1_000))


def renewal_years(player: Player) -> tuple[int, int]:
    """Durées acceptées : selon l'âge pour un pro, jusqu'à la sortie du centre pour un espoir."""
    if player.squad == Squad.YOUTH:
        return 1, max(1, min(YOUTH_CONTRACT_YEARS, YOUTH_EXIT_AGE - 1 - player.age))
    return preferred_years(player)


# --- Clubs concurrents ---------------------------------------------------------------------

# Chance, à chaque journée de la phase retour, qu'un concurrent signe un joueur
# en fin de contrat : une base, plus par point de note au-dessus de la moyenne
# de son groupe (pros ou espoirs). Sur une phase retour, un joueur moyen part
# environ une fois sur dix, un cadre (4 points au-dessus) une fois sur deux.
POACH_BASE = 0.01
POACH_PER_POINT = 0.012
POACH_MAX = 0.06
# Un espoir signe dans l'un des plus gros clubs.
YOUTH_SUITORS = 3


def poach_chance(player: Player, club: Club) -> float:
    group = club.youths if player.squad == Squad.YOUTH else club.players
    mean = sum(p.overall for p in group) / max(len(group), 1)
    return min(POACH_MAX, max(POACH_BASE, POACH_BASE + POACH_PER_POINT * (player.overall - mean)))


def pick_suitor(
    player: Player, origin: Club, rivals: list[Club], rng: random.Random
) -> tuple[Club, int] | None:
    """Le concurrent qui le signe et le salaire convenu, ou None si aucun ne lui plaît.

    `rivals` : les clubs qui ont encore de la place pour lui.
    """
    if not rivals:
        return None
    if player.squad == Squad.YOUTH:
        biggest = sorted(rivals, key=club_level, reverse=True)[:YOUTH_SUITORS]
        return rng.choice(biggest), YOUTH_WAGE
    offers = [(rival, wage_demand(player, origin, rival)) for rival in rivals]
    offers = [(rival, wage) for rival, wage in offers if wage is not None]
    if not offers:
        return None
    return max(offers, key=lambda offer: move_appeal(player, origin, offer[0]))
