"""Règles du recrutement : qui est transférable, prêtable, et ce que veut le joueur.

Dans le rugby, les transferts en cours de contrat sont rares et chers : on
recrute surtout un joueur en dernière année de contrat, en négociant
directement avec lui pour la saison suivante. Le prêt sert à faire jouer un
joueur qui manque de temps de jeu. Aucune dépendance à FastAPI ni à la base.
"""

from enum import StrEnum

from engine.economy import market_value
from engine.match_engine import FORMATION, RATING_FOR_POSITION, team_strength
from models import Club, Player


class DealKind(StrEnum):
    TRANSFER = "transfer"  # en cours de contrat : indemnité au club, puis salaire au joueur
    PRECONTRACT = (
        "precontract"  # dernière année de contrat : salaire au joueur, arrivée à l'intersaison
    )
    LOAN = "loan"  # jusqu'à la fin de la saison, salaire à la charge de l'emprunteur


# --- Situation d'un joueur -------------------------------------------------------------

# Temps de jeu selon le rang à son poste : titulaire, remplaçant direct, réserviste.
TIME_STARTER = 1.0
TIME_BENCH = 0.5
TIME_RESERVE = 0.2


def club_level(club: Club) -> float:
    """Niveau sportif du club : moyenne des notes collectives du XV."""
    team = team_strength(club)
    return (team.set_piece + team.pack + team.attack + team.defense) / 4


def playing_time(player: Player, club: Club) -> float:
    """Temps de jeu attendu du joueur dans ce club (qu'il en fasse déjà partie ou non)."""
    rivals = [p for p in club.players_at(player.position) if p.id != player.id]
    rated = sorted([*rivals, player], key=RATING_FOR_POSITION[player.position], reverse=True)
    rank = rated.index(player)
    starters = FORMATION[player.position]
    if rank < starters:
        return TIME_STARTER
    if rank == starters:
        return TIME_BENCH
    return TIME_RESERVE


def time_label(time: float) -> str:
    return {TIME_STARTER: "titulaire", TIME_BENCH: "remplaçant"}.get(time, "réserviste")


# --- Position du club vendeur ------------------------------------------------------------

# Un gros club ne lâche pas ses titulaires en cours de contrat.
UNTRANSFERABLE_LEVEL = 15.0
# Indemnité : valeur × (1 + 0,5 par saison de contrat restante) × importance.
FEE_PER_CONTRACT_YEAR = 0.5
FEE_IMPORTANCE = {TIME_STARTER: 1.5, TIME_BENCH: 1.2, TIME_RESERVE: 1.0}


def _round_to(value: float, step: int) -> int:
    return int(round(value / step) * step)


def transfer_fee(player: Player, club: Club, season_year: int) -> int | None:
    """Indemnité demandée par le club, ou None s'il refuse tout transfert."""
    time = playing_time(player, club)
    if time == TIME_STARTER and club_level(club) >= UNTRANSFERABLE_LEVEL:
        return None
    years = player.years_left(season_year)
    fee = market_value(player) * (1 + FEE_PER_CONTRACT_YEAR * years) * FEE_IMPORTANCE[time]
    return _round_to(fee, 5_000)


def club_lends(player: Player, club: Club) -> bool:
    """Un club prête les joueurs qui ne sont pas titulaires chez lui."""
    return playing_time(player, club) < TIME_STARTER


def can_precontract(player: Player, season_year: int) -> bool:
    """En dernière année de contrat : libre de signer ailleurs pour la saison suivante."""
    return player.years_left(season_year) == 1


# --- Ce que veut le joueur -----------------------------------------------------------------

# Attrait d'un départ : prestige du club, temps de jeu, salaire. Le joueur
# signe si l'attrait dépasse le seuil ; le salaire demandé est celui qui
# permet de l'atteindre.
PRESTIGE_WEIGHT = 0.5
PRESTIGE_SCALE = 3.0  # un écart de 3 points de niveau compte pour 1
TIME_WEIGHT = 0.3
WAGE_WEIGHT = 0.3
ACCEPT_THRESHOLD = 0.05
# Au-delà de ce multiple de son salaire, le joueur ne veut pas venir, point.
WAGE_DEMAND_MAX = 3.0
# Pour un prêt, seul compte le temps de jeu (et un peu le niveau du club d'accueil).
LOAN_TIME_WEIGHT = 0.7
LOAN_PRESTIGE_WEIGHT = 0.1


def move_appeal(player: Player, origin: Club, destination: Club) -> float:
    """Attrait d'un transfert ou d'une signature libre, salaire mis à part."""
    prestige = (club_level(destination) - club_level(origin)) / PRESTIGE_SCALE
    time = playing_time(player, destination) - playing_time(player, origin)
    return PRESTIGE_WEIGHT * prestige + TIME_WEIGHT * time


def wage_demand(player: Player, origin: Club, destination: Club) -> int | None:
    """Salaire annuel exigé pour venir, ou None si le joueur refuse quoi qu'on lui offre."""
    appeal = move_appeal(player, origin, destination)
    factor = 1 + (ACCEPT_THRESHOLD - appeal) / WAGE_WEIGHT
    if factor > WAGE_DEMAND_MAX:
        return None
    return max(40_000, _round_to(player.wage * max(0.9, factor), 1_000))


def accepts_wage(player: Player, origin: Club, destination: Club, wage: int) -> bool:
    demand = wage_demand(player, origin, destination)
    return demand is not None and wage >= demand


def accepts_loan(player: Player, origin: Club, destination: Club) -> bool:
    """Le joueur accepte un prêt s'il y gagne du temps de jeu."""
    time = playing_time(player, destination) - playing_time(player, origin)
    prestige = (club_level(destination) - club_level(origin)) / PRESTIGE_SCALE
    return LOAN_TIME_WEIGHT * time + LOAN_PRESTIGE_WEIGHT * prestige >= ACCEPT_THRESHOLD


def refusal_reason(player: Player, origin: Club, destination: Club) -> str:
    """Pourquoi le joueur ne veut pas venir (quand `wage_demand` renvoie None)."""
    if club_level(destination) < club_level(origin):
        if playing_time(player, origin) < TIME_STARTER and accepts_loan(
            player, origin, destination
        ):
            return "Il ne quittera pas un si grand club, mais un prêt pour jouer l'intéresserait."
        return "Il ne veut pas rejoindre un club moins huppé que le sien."
    return "Il n'aurait pas plus de temps de jeu chez toi : il n'est pas intéressé."
