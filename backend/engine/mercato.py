"""Le mercato d'été des clubs IA : à l'intersaison, ils s'achètent des joueurs entre eux.

Après les fins de contrat et les retraites, avant de compléter leur effectif parmi les
agents libres (engine/free_agents.py), chaque club IA tente une recrue, au plus, à
son poste le plus faible : un joueur d'un autre club IA qui serait titulaire chez lui
et vaut nettement mieux que son titulaire le moins bon à ce poste. Les règles sont
celles du manager (engine/transfers.py) :

- le club vendeur fixe l'indemnité (`transfer_fee`), refuse de lâcher un titulaire s'il
  est un gros club, et garde de quoi jouer (`SELLER_MIN_SQUAD`, et au poste ses
  titulaires et une doublure) ;
- le joueur doit vouloir venir (`wage_demand`), sans que le club ne le surpaie ;
- l'acheteur paie avec une part de sa trésorerie (`BUDGET_SHARE`) et reste sous le
  plafond salarial (engine/regulations.py) ;
- on traite dans son hémisphère (le Super Rugby à part des championnats européens), et
  un international d'une fédération qui ne retient que les joueurs du pays y reste.

Le club dirigé par le joueur n'est ni acheteur ni vendeur : il recrute lui-même.
Aucune dépendance à FastAPI ni à la base.
"""

import random
from dataclasses import dataclass

from data.nations import NATIONS_BY_CODE, home_nation
from engine.economy import SQUAD_MAX
from engine.match_engine import FORMATION, RATING_FOR_POSITION
from engine.regulations import cap_breach
from engine.transfers import (
    TIME_STARTER,
    club_level,
    playing_time,
    preferred_years,
    transfer_fee,
    wage_demand,
)
from models import Club, Player, Position

# Une recrue vaut au moins le titulaire le moins bon du poste, plus ceci.
MIN_GAIN = 1.0
# Un club met au plus cette part de sa trésorerie dans une indemnité.
BUDGET_SHARE = 0.3
# Un club ne vend pas s'il tombe sous cet effectif.
SELLER_MIN_SQUAD = 28
# Ni au-delà de cette hausse de salaire pour convaincre le joueur.
MAX_RAISE = 1.3


@dataclass(frozen=True)
class Transfer:
    """Un transfert conclu : le joueur, ses clubs, l'indemnité, son nouveau contrat."""

    player: Player
    seller: Club
    buyer: Club
    fee: int
    wage: int
    years: int


# Le championnat de l'hémisphère sud ; tous les autres sont européens (l'URC compris).
SOUTH = "super_rugby"


def _may_move(player: Player, seller: Club, buyer: Club) -> bool:
    """Le joueur peut-il passer de `seller` à `buyer` : même hémisphère, et pas
    d'international d'une fédération stricte qui quitterait son pays."""
    if (seller.league == SOUTH) != (buyer.league == SOUTH):
        return False
    nation = NATIONS_BY_CODE.get(player.nationality)
    if nation is not None and nation.home_only and home_nation(seller.name) == nation.code:
        return home_nation(buyer.name) == nation.code
    return True


def _weakest_starter(club: Club, position: Position) -> float:
    """La note du titulaire le moins bon du club à ce poste (0 s'il en manque)."""
    rating = RATING_FOR_POSITION[position]
    ranked = sorted((rating(p) for p in club.players_at(position)), reverse=True)
    starters = FORMATION[position]
    return ranked[starters - 1] if len(ranked) >= starters else 0.0


def summer_market(
    clubs: list[Club],
    season_year: int,
    rng: random.Random,
    arrived: frozenset[int] = frozenset(),
) -> list[Transfer]:
    """Les transferts de l'été entre clubs IA (`clubs`, effectifs et trésoreries mis à
    jour) : chaque club, dans un ordre tiré au sort, tente une recrue. `arrived` : les
    joueurs qui viennent de changer de club (pré-contrat) et n'en repartent pas."""
    levels: dict[int, float] = {}

    def level(club: Club) -> float:
        if club.id not in levels:
            levels[club.id] = club_level(club)
        return levels[club.id]

    deals = []
    moved = set(arrived)  # joueurs qui ont déjà changé de club cet été
    buyers = list(clubs)
    rng.shuffle(buyers)
    for buyer in buyers:
        deal = _best_buy(buyer, clubs, season_year, level, moved, rng)
        if deal is None:
            continue
        player, seller = deal.player, deal.seller
        seller.players.remove(player)
        buyer.players.append(player)
        player.club_id, player.wage = buyer.id, deal.wage
        player.contract_until = season_year + deal.years - 1
        seller.balance += deal.fee
        buyer.balance -= deal.fee
        moved.add(player.id)
        levels.pop(buyer.id, None)
        levels.pop(seller.id, None)
        deals.append(deal)
    return deals


def _best_buy(
    buyer: Club,
    clubs: list[Club],
    season_year: int,
    level,
    moved: set[int],
    rng: random.Random,
) -> Transfer | None:
    """La meilleure recrue possible pour `buyer`, au poste où elle le renforce le plus."""
    if len(buyer.players) >= SQUAD_MAX or buyer.balance <= 0:
        return None
    budget = buyer.balance * BUDGET_SHARE
    weakest = {position: _weakest_starter(buyer, position) for position in Position}
    candidates = []
    for seller in clubs:
        if seller.id == buyer.id or len(seller.players) <= SELLER_MIN_SQUAD:
            continue
        if (seller.league == SOUTH) != (buyer.league == SOUTH):
            continue
        for player in seller.players:
            if player.id in moved or player.loaned_from is not None:
                continue
            if player.contract_until < season_year:
                continue
            gain = RATING_FOR_POSITION[player.position](player) - weakest[player.position]
            if gain >= MIN_GAIN:
                candidates.append((gain, seller, player))
    # Les plus belles recrues d'abord : la première qui passe toutes les étapes signe.
    candidates.sort(key=lambda c: (c[0], -c[2].id), reverse=True)
    for _gain, seller, player in candidates:
        position = player.position
        if not _may_move(player, seller, buyer):
            continue
        if len(seller.players_at(position)) <= FORMATION[position] + 1:
            continue  # le vendeur garde ses titulaires et une doublure au poste
        if playing_time(player, buyer) < TIME_STARTER:
            continue
        fee = transfer_fee(player, seller, season_year, level(seller))
        if fee is None or fee > budget:
            continue
        wage = wage_demand(player, seller, buyer, level)
        if wage is None or wage > player.wage * MAX_RAISE:
            continue
        if cap_breach(buyer, wage) is not None:
            continue
        years = rng.randint(*preferred_years(player))
        return Transfer(player, seller, buyer, fee, wage, years)
    return None
