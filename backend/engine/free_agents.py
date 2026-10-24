"""Agents libres : joueurs sans club ni contrat, que tout club peut signer sans indemnité.

D'où ils viennent : les joueurs du club dirigé qu'on n'a pas prolongés, ceux
que les clubs IA ne gardent pas, les espoirs qui quittent un centre sans
passer pro, et des joueurs de retour de l'étranger ou de divisions
inférieures (le vivier est complété à chaque intersaison). Un agent libre
négocie seul son salaire et arrive aussitôt. Il ne reste pas éternellement
sans club : après une saison sans contrat, il peut arrêter. Aucune dépendance
à FastAPI ni à la base.
"""

import random
from collections import Counter
from collections.abc import Iterable, Iterator
from dataclasses import dataclass

from data.generator import SQUAD_COMPOSITION, generate_player
from engine.economy import WAGE_MIN, wage_for
from engine.offseason import RETIREMENT_AGE, develop_player
from engine.regulations import cap_breach, cap_room, fit_under_cap
from engine.transfers import TIME_BENCH, TIME_STARTER, playing_time, preferred_years
from models import Club, Player, Position, Squad

# --- Ce que demande un agent libre -------------------------------------------------------

# Sans club, il vise son salaire de marché, moins s'il ne serait pas titulaire chez toi.
FREE_WAGE_FACTOR = {TIME_STARTER: 1.0, TIME_BENCH: 0.9}
FREE_WAGE_FACTOR_RESERVE = 0.8


def free_agent_wage(player: Player, club: Club) -> int:
    """Salaire annuel visé par l'agent libre pour signer dans ce club."""
    factor = FREE_WAGE_FACTOR.get(playing_time(player, club), FREE_WAGE_FACTOR_RESERVE)
    return max(WAGE_MIN, int(round(wage_for(player) * factor / 1_000) * 1_000))


def seasons_without_club(player: Player, season_year: int) -> int:
    """Saisons entières passées sans contrat (0 s'il est libre depuis l'intersaison)."""
    return max(0, season_year - 1 - player.contract_until)


# --- Le vivier, à l'intersaison ----------------------------------------------------------

# Après une saison entière sans club, un agent libre arrête une fois sur deux ;
# après deux, il arrête.
QUIT_CHANCE = {0: 0.0, 1: 0.5}
# Le vivier garde au moins ce nombre de joueurs (arrivées de l'étranger, de
# Pro D2...) et au plus ce nombre (les plus faibles quittent le rugby pro).
POOL_MIN = 25
POOL_MAX = 60
# Niveau et âge des joueurs qui arrivent dans le vivier de l'extérieur.
NEWCOMER_LEVEL = (8.0, 11.5)
NEWCOMER_AGES = (22, 33)


# Un agent libre ne s'entraîne nulle part : il progresse (ou décline) comme
# dans le plus petit centre d'entraînement.
FREE_TRAINING_LEVEL = 1


def release(player: Player, season_year: int) -> None:
    """Le joueur quitte son club sans contrat (un espoir sort du centre en pro)."""
    if player.squad == Squad.YOUTH:
        player.squad = Squad.PRO
        player.wage = wage_for(player)
    player.club_id = None
    player.loaned_from = None
    player.contract_until = min(player.contract_until, season_year - 1)


def quits(player: Player, season_year: int, rng: random.Random) -> bool:
    """À l'intersaison (après vieillissement) : l'agent libre raccroche-t-il ?"""
    if player.age >= RETIREMENT_AGE:
        return True
    chance = QUIT_CHANCE.get(seasons_without_club(player, season_year), 1.0)
    return rng.random() < chance


def age_free_agent(player: Player, season_year: int, rng: random.Random) -> bool:
    """Intersaison d'un agent libre : il vieillit, progresse ou décline. Renvoie
    False s'il arrête."""
    player.age += 1
    develop_player(player, FREE_TRAINING_LEVEL, rng)
    return not quits(player, season_year, rng)


def trim_pool(pool: list[Player]) -> list[Player]:
    """Les agents libres en trop (les plus faibles), qui quittent le rugby pro."""
    return sorted(pool, key=lambda p: p.overall)[: max(0, len(pool) - POOL_MAX)]


def newcomers(
    pool: list[Player], player_ids: Iterator[int], season_year: int, rng: random.Random
) -> list[Player]:
    """Joueurs qui arrivent dans le vivier pour le ramener à `POOL_MIN`, aux postes
    les moins fournis (sans contrat depuis l'intersaison)."""
    counts = Counter(p.position for p in pool)
    arrivals = []
    for _ in range(POOL_MIN - len(pool)):
        position = min(Position, key=lambda p: counts[p] / SQUAD_COMPOSITION[p])
        counts[position] += 1
        player = generate_player(
            next(player_ids), position, rng.uniform(*NEWCOMER_LEVEL), None, rng, season_year
        )
        player.age = rng.randint(*NEWCOMER_AGES)
        player.wage = wage_for(player, noise=rng.uniform(0.9, 1.15))
        player.contract_until = season_year - 1
        arrivals.append(player)
    return arrivals


# --- Les clubs IA -----------------------------------------------------------------------------

# En fin de contrat, un club IA ne garde pas tout le monde : un joueur sur
# cinq part, un trentenaire sur deux, tant que l'effectif reste fourni.
RELEASE_CHANCE = 0.2
VETERAN_RELEASE_CHANCE = 0.5
VETERAN_AGE = 31
RELEASE_FLOOR = 28  # pas de départ libre sous ce nombre de pros
# Un club IA complète son effectif dans le vivier jusqu'à cette taille.
SQUAD_TARGET = sum(SQUAD_COMPOSITION.values())


# Durée (en saisons) des contrats que les clubs IA renouvellent.
AI_RENEWAL_YEARS = (1, 3)


def ai_releases(player: Player, squad_size: int, rng: random.Random) -> bool:
    """Le club IA laisse-t-il partir ce joueur en fin de contrat ?"""
    if squad_size <= RELEASE_FLOOR:
        return False
    chance = VETERAN_RELEASE_CHANCE if player.age >= VETERAN_AGE else RELEASE_CHANCE
    return rng.random() < chance


def ai_pick(club: Club, pool: list[Player]) -> Player | None:
    """L'agent libre que signe un club IA à court d'effectif : le meilleur au poste
    le moins fourni (par rapport à un effectif type) dont le salaire tient sous le
    plafond, ou None s'il est complet."""
    if len(club.players) >= SQUAD_TARGET or not pool:
        return None
    counts = Counter(p.position for p in club.players)
    for position in sorted(Position, key=lambda p: counts[p] - SQUAD_COMPOSITION[p]):
        candidates = [
            p for p in pool if p.position == position and cap_breach(club, wage_for(p)) is None
        ]
        if candidates:
            return max(candidates, key=lambda p: p.overall)
    return None


def settle_contracts(club: Club, season_year: int, rng: random.Random) -> list[Player]:
    """Fins de contrat d'un club IA avant la saison `season_year` : il prolonge la
    plupart de ses joueurs (et tous ses espoirs) et laisse partir les autres ; au-dessus
    du plafond salarial, il laisse partir ses pros en fin de contrat tant qu'il le dépasse.

    Renvoie ceux qui partent, retirés de l'effectif : à l'appelant d'en faire des
    agents libres (`release`).
    """
    leaving = []
    squad_size = len(club.players)
    room = cap_room(club)
    for player in [*club.players, *club.youths]:
        if player.contract_until >= season_year:
            continue
        over_cap = room is not None and room < 0 and squad_size > RELEASE_FLOOR
        if player.squad == Squad.PRO and (ai_releases(player, squad_size, rng) or over_cap):
            squad_size -= 1
            room = None if room is None else room + player.wage
            leaving.append(player)
        else:
            player.contract_until = season_year + rng.randint(*AI_RENEWAL_YEARS) - 1
    gone = {player.id for player in leaving}
    club.players = [p for p in club.players if p.id not in gone]
    return leaving


@dataclass
class PoolRenewal:
    """Ce que l'intersaison a changé dans le vivier des agents libres."""

    signed: list[Player]  # recrutés par un club IA (club, salaire et contrat à jour)
    renegotiated: list[Player]  # pros d'un club IA au-dessus du plafond : salaire baissé
    dropped: list[Player]  # en trop : ils quittent le rugby pro
    arrivals: list[Player]  # arrivés de l'extérieur


def renew_pool(
    clubs: Iterable[Club],
    pool: list[Player],
    season_year: int,
    rng: random.Random,
    player_ids: Iterator[int],
) -> PoolRenewal:
    """Intersaison, après les départs : les clubs IA (`clubs`) au-dessus du plafond
    salarial renégocient leurs salaires, ceux à court d'effectif piochent dans le
    vivier, qui est ensuite ramené entre son minimum et son maximum. `pool` et les
    effectifs sont mis à jour."""
    signed, renegotiated = [], []
    for club in clubs:
        renegotiated += fit_under_cap(club)
        while (player := ai_pick(club, pool)) is not None:
            player.club_id = club.id
            player.wage = wage_for(player)
            player.contract_until = season_year + rng.randint(*preferred_years(player)) - 1
            club.players.append(player)
            pool.remove(player)
            signed.append(player)
    dropped = trim_pool(pool)
    for player in dropped:
        pool.remove(player)
    arrivals = newcomers(pool, player_ids, season_year, rng)
    pool.extend(arrivals)
    return PoolRenewal(signed, renegotiated, dropped, arrivals)
