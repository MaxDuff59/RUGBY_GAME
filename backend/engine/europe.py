"""La Coupe d'Europe : les meilleurs clubs du Top 14, de la Premiership et de l'URC.

Les huit premiers de la saison régulière précédente de chacun des trois championnats
(pour la première saison : les huit meilleurs effectifs) se qualifient. Ils sont
répartis en quatre poules de six, deux clubs de chaque championnat par poule : le
meilleur et le moins bien classé de chaque paire, pour équilibrer. Chaque club joue
quatre matchs de poule, deux week-ends de décembre et deux de janvier, que les trois
championnats laissent libres (data/leagues.py). Les poules se classent comme un
championnat (points, bonus, différence).

Les deux premiers de chaque poule vont en quarts de finale (début avril) : les quatre
vainqueurs de poule sont les têtes de série 1 à 4, les deuxièmes 5 à 8 ; 1 contre 8,
2 contre 7, 3 contre 6, 4 contre 5, chez la meilleure tête de série. Demi-finales
début mai (vainqueurs de 1-8 et 4-5, de 2-7 et 3-6), finale fin mai, sur terrain neutre.
Prolongation, puis tirs au but en cas d'égalité, comme dans les phases finales.

Le Challenge européen (`CHALLENGE`) réunit les autres clubs des trois championnats, du
9e au dernier : des poules de quatre (un club de chaque chapeau, les chapeaux suivant
le classement), trois journées de poule (les trois premiers week-ends de la Coupe
d'Europe), chacun recevant une ou deux fois. Puis des quarts à huit (les deux premiers
de chaque poule, et les meilleurs troisièmes s'il n'y a que trois poules), les mêmes
week-ends que la Coupe d'Europe.
"""

import datetime
import random
from dataclasses import dataclass
from itertools import product
from string import ascii_uppercase

from engine.calendar import first_saturday
from engine.season import league_table
from models import Match, Stage

CODE = "champions_cup"
NAME = "Champions Cup"
LEAGUES = ("top14", "premiership", "urc")
PER_LEAGUE = 8
POOLS = 4
POOL_ROUNDS = 4
QUALIFIERS_PER_POOL = 2

# Les samedis de la coupe (mois, jour) : à partir de ces dates, le premier samedi.
POOL_WEEKENDS = ((12, 6), (12, 13), (1, 10), (1, 17))
QUARTERS, SEMIS, FINAL = (4, 4), (5, 2), (5, 23)
KNOCKOUT = (Stage.QUARTER, Stage.SEMI, Stage.FINAL)
# Numéro de « journée » des tours à élimination directe, après les quatre de poule.
KNOCKOUT_MATCHDAY = {Stage.QUARTER: 5, Stage.SEMI: 6, Stage.FINAL: 7}

CHALLENGE = "challenge_cup"
CHALLENGE_NAME = "Challenge Cup"
CHALLENGE_FROM = PER_LEAGUE  # à partir du 9e de chaque championnat
CHALLENGE_POOL_SIZE = 4
# Les quarts de finale réunissent huit clubs : les deux premiers de chaque poule, et
# s'il en manque (trois poules), les meilleurs troisièmes.
KNOCKOUT_CLUBS = 8


@dataclass(frozen=True)
class Format:
    """Ce qui distingue les deux coupes : leurs week-ends de poule (une journée chacun)."""

    code: str
    weekends: tuple[tuple[int, int], ...]

    @property
    def pool_rounds(self) -> int:
        return len(self.weekends)


FORMATS = {
    CODE: Format(CODE, POOL_WEEKENDS),
    CHALLENGE: Format(CHALLENGE, POOL_WEEKENDS[:3]),
}


def saturday(year: int, month_day: tuple[int, int]) -> datetime.date:
    """Le samedi de la coupe à partir de (mois, jour) de la saison `year` (août à juillet)."""
    month, day = month_day
    return first_saturday(year if month >= 8 else year + 1, month, day)


def pool_dates(year: int, code: str = CODE) -> list[datetime.date]:
    return [saturday(year, weekend) for weekend in FORMATS[code].weekends]


def knockout_date(year: int, stage: Stage) -> datetime.date:
    return saturday(year, {Stage.QUARTER: QUARTERS, Stage.SEMI: SEMIS, Stage.FINAL: FINAL}[stage])


def draw_pools(ranked: dict[str, list[int]], rng: random.Random) -> dict[str, list[int]]:
    """Les poules : `ranked` donne les qualifiés de chaque championnat, du 1er au 8e. Chaque
    poule reçoit deux clubs de chaque championnat, un bien classé et un moins bien classé."""
    pools: dict[str, list[int]] = {letter: [] for letter in ascii_uppercase[:POOLS]}
    for league in LEAGUES:
        clubs = ranked[league][:PER_LEAGUE]
        pairs = [(clubs[i], clubs[PER_LEAGUE - 1 - i]) for i in range(POOLS)]
        rng.shuffle(pairs)
        for letter, pair in zip(pools, pairs, strict=True):
            pools[letter].extend(pair)
    return pools


def draw_challenge(ranked: dict[str, list[int]], rng: random.Random) -> dict[str, list[int]]:
    """Les poules du Challenge européen, de `CHALLENGE_POOL_SIZE` clubs : autant que le
    nombre de clubs le permet (trois dans le monde réel, quatre jusqu'à seize clubs).
    `ranked` donne ses clubs de chaque championnat, du mieux au moins bien classé. Rangés
    par place (tous les 9es, puis les 10es...), ils forment des chapeaux d'un club par
    poule ; chaque poule tire un club de chaque chapeau. Un nombre de clubs qui ne fait
    pas des poules pleines laisse de côté les derniers."""
    order = sorted(
        (
            (rank, LEAGUES.index(league), club)
            for league, clubs in ranked.items()
            for rank, club in enumerate(clubs)
        ),
    )
    clubs = [club for *_, club in order]
    count = min(POOLS, len(clubs) // CHALLENGE_POOL_SIZE)
    clubs = clubs[: count * CHALLENGE_POOL_SIZE]
    pools: dict[str, list[int]] = {letter: [] for letter in ascii_uppercase[:count]}
    for start in range(0, len(clubs), count):
        pot = clubs[start : start + count]
        rng.shuffle(pot)
        for letter, club in zip(pools, pot, strict=True):
            pools[letter].append(club)
    return pools


def pool_fixtures(
    pools: dict[str, list[int]], dates: list[datetime.date], code: str = CODE
) -> list[Match]:
    """Les journées de poule, une par date : quatre pour la Coupe d'Europe (poules de six,
    deux réceptions chacun), trois pour le Challenge (poules de quatre, une ou deux).

    Tableau à la ronde (méthode du cercle) dont on garde les premiers tours ; parmi les
    façons de répartir les réceptions, la première où chacun reçoit autant que possible
    la moitié de ses matchs."""
    rounds = len(dates)
    fair = {rounds // 2, (rounds + 1) // 2}
    fixtures = []
    for clubs in pools.values():
        ring, pairings = list(clubs), []
        for round_index in range(rounds):
            for i in range(len(ring) // 2):
                pairings.append((round_index, ring[i], ring[-1 - i]))
            ring = [ring[0], ring[-1], *ring[1:-1]]
        for home_first in product((True, False), repeat=len(pairings)):
            hosts = [a if keep else b for keep, (_, a, b) in zip(home_first, pairings, strict=True)]
            if all(hosts.count(club) in fair for club in clubs):
                break
        for keep, (round_index, a, b) in zip(home_first, pairings, strict=True):
            home, away = (a, b) if keep else (b, a)
            fixtures.append(
                Match(
                    home_club_id=home,
                    away_club_id=away,
                    matchday=round_index + 1,
                    date=dates[round_index],
                    league=code,
                )
            )
    return fixtures


def pool_tables(pools: dict[str, list[int]], matches: list[Match]) -> dict[str, list[int]]:
    """Le classement de chaque poule, du premier au dernier."""
    tables = {}
    for letter, clubs in pools.items():
        members = set(clubs)
        played = [
            m
            for m in matches
            if m.stage == Stage.REGULAR and m.home_club_id in members and m.is_played
        ]
        table = [row.club_id for row in league_table(played).table()] if played else []
        tables[letter] = table + [c for c in clubs if c not in table]
    return tables


def seeds(pools: dict[str, list[int]], matches: list[Match]) -> list[int]:
    """Les huit qualifiés, têtes de série 1 à 8 : les vainqueurs de poule d'abord, puis
    les deuxièmes, chacun rangé par points, différence et essais ; avec trois poules,
    les deux meilleurs troisièmes complètent."""
    played = [m for m in matches if m.stage == Stage.REGULAR and m.is_played]
    standings = league_table(played).standings if played else {}
    tables = pool_tables(pools, matches)

    def merit(club_id: int) -> tuple:
        row = standings.get(club_id)
        return (row.league_points, row.points_difference, row.tries_for) if row else (0, 0, 0)

    ordered = []
    for place in range(QUALIFIERS_PER_POOL):
        ordered += sorted((table[place] for table in tables.values()), key=merit, reverse=True)
    thirds = sorted(
        (table[QUALIFIERS_PER_POOL] for table in tables.values() if len(table) > 2),
        key=merit,
        reverse=True,
    )
    return ordered + thirds[: max(0, KNOCKOUT_CLUBS - len(ordered))]


def next_round(
    year: int, pools: dict[str, list[int]], matches: list[Match], code: str = CODE
) -> list[Match]:
    """Les matchs du tour suivant, quand tous ceux du tour en cours sont joués (aucun sinon,
    ou une fois la finale jouée)."""
    if not matches or any(not m.is_played for m in matches):
        return []
    played = {stage: [m for m in matches if m.stage == stage] for stage in KNOCKOUT}
    order = seeds(pools, matches)
    if not played[Stage.QUARTER]:
        pairs = [(order[i], order[7 - i]) for i in range(4)]
        return _ties(year, Stage.QUARTER, pairs, code)
    if not played[Stage.SEMI]:
        # Vainqueurs de 1-8 et 4-5, de 2-7 et 3-6 (les quarts sont rangés 1-8, 2-7, 3-6, 4-5).
        first, second, third, fourth = (m.winner_id(order) for m in played[Stage.QUARTER])
        pairs = [_seeded(first, fourth, order), _seeded(second, third, order)]
        return _ties(year, Stage.SEMI, pairs, code)
    if not played[Stage.FINAL]:
        finalists = [m.winner_id(order) for m in played[Stage.SEMI]]
        return _ties(year, Stage.FINAL, [_seeded(*finalists, order)], code, neutral=True)
    return []


def _seeded(a: int, b: int, order: list[int]) -> tuple[int, int]:
    """La paire, la meilleure tête de série d'abord (elle reçoit)."""
    return (a, b) if order.index(a) < order.index(b) else (b, a)


def _ties(
    year: int, stage: Stage, pairs: list[tuple[int, int]], code: str, neutral: bool = False
) -> list[Match]:
    day = knockout_date(year, stage)
    return [
        Match(
            home_club_id=home,
            away_club_id=away,
            matchday=KNOCKOUT_MATCHDAY[stage],
            stage=stage,
            date=day,
            neutral=neutral,
            league=code,
        )
        for home, away in pairs
    ]


def champion(pools: dict[str, list[int]], matches: list[Match]) -> int | None:
    final = next((m for m in matches if m.stage == Stage.FINAL and m.is_played), None)
    return final.winner_id(seeds(pools, matches)) if final else None
