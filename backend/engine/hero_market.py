"""Carrière de joueur : le mercato du joueur incarné, à la fin de chaque saison.

Sa valeur (`value`) tient à sa note générale et, s'il a assez joué, à sa moyenne de la
saison. Les clubs dont le XV est à sa portée (`transfer_clubs`) peuvent lui faire une
offre : pas plus haut que sa valeur plus `REACH` (un débutant n'intéresse pas les
grands clubs), pas trop bas non plus. Un joueur qui a peu joué dans son club peut être
prêté une saison à un club plus modeste (`loan_clubs`) pour jouer davantage ; il
revient à l'intersaison suivante. Son club lui propose toujours de prolonger, à un
salaire qui suit sa valeur.

Un agent (`AGENTS`) lui obtient plus d'offres, de plus grands clubs et de meilleurs
salaires, contre une commission.

Rien n'est tiré au hasard d'un appel à l'autre : la même fin de saison donne les mêmes
offres.
"""

import random
from dataclasses import dataclass


@dataclass(frozen=True)
class Agent:
    offers: int  # offres de plus
    reach: float  # portée de plus (points de niveau)
    wage: float  # salaire obtenu, en multiple
    commission: float  # part du salaire qu'il prend


AGENTS = {
    "none": Agent(0, 0.0, 1.0, 0.0),
    "local": Agent(1, 0.5, 1.10, 0.05),
    "star": Agent(2, 1.0, 1.25, 0.10),
}

# Valeur : la note générale, plus VALUE_PER_RATING par point de moyenne au-dessus de 6,
# s'il a joué au moins VALUE_MIN_MATCHES matchs.
VALUE_PER_RATING = 0.6
VALUE_MIN_MATCHES = 5
# Clubs qui peuvent l'appeler : leur XV entre sa valeur moins FLOOR et plus REACH.
REACH = 1.0
FLOOR = 2.0
OFFER_CHANCE = 0.45
BASE_OFFERS = 2
# Prêt : s'il a joué moins de cette part des minutes de son club, vers un des LOAN_POOL
# clubs les plus modestes ; au plus LOAN_OFFERS.
LOAN_MINUTES_SHARE = 0.35
LOAN_POOL = 5
LOAN_OFFERS = 2
# Salaire : par point de prestige de plus (ou de moins) que son club, borné.
WAGE_PER_PRESTIGE = 0.08
WAGE_FACTOR_MIN, WAGE_FACTOR_MAX = 0.8, 1.6
EXTENSION_YEARS = 3
TRANSFER_YEARS = (2, 3)


def value(overall: float, average: float | None, matches: int) -> float:
    if average is None or matches < VALUE_MIN_MATCHES:
        return overall
    return overall + VALUE_PER_RATING * (average - 6.0)


def transfer_clubs(
    worth: float,
    current: int,
    levels: dict[int, float],
    prestige: dict[int, float],
    agent: Agent,
    rng: random.Random,
) -> list[int]:
    """Les clubs qui lui font une offre de transfert, du plus prestigieux au moins."""
    ceiling = worth + REACH + agent.reach
    within = sorted(
        (
            cid
            for cid, level in levels.items()
            if cid != current and worth - FLOOR <= level <= ceiling
        ),
        key=lambda cid: (-prestige[cid], cid),
    )
    chance = min(1.0, OFFER_CHANCE * (1 + 0.5 * agent.offers))
    return [cid for cid in within if rng.random() < chance][: BASE_OFFERS + agent.offers]


def loan_clubs(
    current: int,
    levels: dict[int, float],
    prestige: dict[int, float],
    minutes_share: float,
    rng: random.Random,
) -> list[int]:
    """Les clubs où son club peut le prêter pour qu'il joue, s'il a peu joué chez lui :
    parmi les plus modestes, moins prestigieux que le sien."""
    if minutes_share >= LOAN_MINUTES_SHARE:
        return []
    modest = sorted(
        (cid for cid in levels if cid != current and prestige[cid] < prestige[current]),
        key=lambda cid: (levels[cid], cid),
    )[:LOAN_POOL]
    return sorted(rng.sample(modest, min(LOAN_OFFERS, len(modest))), key=lambda c: -prestige[c])


def wage(base: int, prestige_gap: float, agent: Agent) -> int:
    """Le salaire offert : sa valeur sur le marché, le prestige du club, l'agent."""
    factor = min(WAGE_FACTOR_MAX, max(WAGE_FACTOR_MIN, 1 + WAGE_PER_PRESTIGE * prestige_gap))
    return round(base * factor * agent.wage / 1000) * 1000
