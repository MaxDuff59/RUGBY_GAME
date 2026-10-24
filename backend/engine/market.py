"""Le marché des clubs IA en cours de saison : ce qu'ils font entre eux, semaine après semaine.

Les trois voies du manager (engine/transfers.py), avec les mêmes règles :

- pré-contrat : pendant la phase retour, un joueur en dernière année de contrat peut
  s'engager ailleurs pour la saison suivante. Les meilleurs éléments d'un effectif
  sont les plus convoités (`poach_chance`), et il ne signe que là où il jouerait ;
- prêt : un club à court de joueurs valides à un poste emprunte, jusqu'à la fin de la
  saison, un réserviste d'un club qui en a de reste et qui y gagne du temps de jeu ;
- agent libre : sur une longue blessure, il engage un joker médical ; et faute de
  prêt possible, un agent libre, jusqu'à la fin de la saison.

Chaque club respecte le plafond salarial de son championnat (engine/regulations.py) :
un agent libre ou un prêté ne signe que si son salaire y tient, un pré-contrat que si
celui de la saison suivante y tient, avec ceux déjà signés.

Le club dirigé par le joueur n'est pas de ce marché : il recrute lui-même, et ses
fins de contrat sont approchées à part (api/routers/contracts.py, `rival_signings`).
Aucune dépendance à FastAPI ni à la base.
"""

import datetime
import random
from collections import Counter
from dataclasses import dataclass, field

from data.nations import NATIONS_BY_CODE, home_nation
from engine.contracts import poach_chance, retires_next_season
from engine.economy import SQUAD_MAX, SQUAD_MIN
from engine.free_agents import free_agent_wage
from engine.match_engine import FORMATION, RATING_FOR_POSITION
from engine.medical import allows_joker
from engine.regulations import cap_breach, fits_next_season
from engine.transfers import (
    TIME_BENCH,
    TIME_RESERVE,
    DealKind,
    accepts_loan,
    can_precontract,
    club_level,
    move_appeal,
    playing_time,
    preferred_years,
    wage_demand,
)
from models import Club, Player, Position

# Entre clubs IA, un joueur en fin de contrat est approché deux fois moins souvent
# que ceux du club dirigé : sur une phase retour, un cadre part une fois sur quatre.
APPROACH_FACTOR = 0.5
# Qui s'intéresse à lui : les clubs de son championnat, et quelques-uns d'ailleurs.
FOREIGN_CLUBS = 4
# Un club ne va pas au-delà de cette hausse de salaire pour le convaincre.
MAX_RAISE = 1.3
# Pré-contrats qu'un même club signe au plus pour la saison suivante.
MAX_INCOMING = 4
# Le joueur choisit parmi ses meilleures offres, pas toujours la première.
SHORTLIST = 3

# Un absent de plus d'un mois dégarnit son poste.
LONG_ABSENCE = datetime.timedelta(weeks=4)
# Chaque semaine, un club à court de monde à un poste agit une fois sur deux.
ACT_CHANCE = 0.5
# Un agent libre fait l'affaire s'il vaut au moins la doublure du poste, à ce point près.
SIGNING_TOLERANCE = 1.0
# Un club ne prête pas s'il tombe sous cet effectif.
LENDER_MIN_SQUAD = SQUAD_MIN + 3


def cover(position: Position) -> int:
    """Joueurs valides qu'un club veut à un poste : ses titulaires et une doublure."""
    return FORMATION[position] + 1


@dataclass(frozen=True)
class Deal:
    """Un accord conclu entre clubs IA. `origin` : None pour un agent libre."""

    kind: DealKind
    player: Player
    origin: Club | None
    destination: Club
    wage: int
    years: int = 1  # durée du contrat (pré-contrat)


@dataclass
class Market:
    """Le marché un jour donné. Les prêts et les signatures d'agents libres modifient
    les effectifs de `clubs` et `pool` ; un pré-contrat ne change rien avant
    l'intersaison, il s'ajoute à `incoming` et sort le joueur du marché (`taken`)."""

    clubs: list[Club]  # les clubs IA, dans un ordre stable
    pool: list[Player]  # agents libres
    day: datetime.date
    season_year: int
    late: set[str]  # championnats en phase retour ou en phases finales
    active: set[str]  # championnats dont la saison régulière est en cours
    incoming: Counter[int] = field(default_factory=Counter)  # pré-contrats signés, par club
    # Salaires de ces pré-contrats, par club : pour le plafond de la saison suivante.
    incoming_wages: Counter[int] = field(default_factory=Counter)
    # Joueurs hors marché : déjà engagés ailleurs, ou en discussion avec le manager.
    taken: set[int] = field(default_factory=set)
    _levels: dict[int, float] = field(default_factory=dict, repr=False)

    def level(self, club: Club) -> float:
        """Niveau du club, calculé une fois (et recalculé quand son effectif change)."""
        if club.id not in self._levels:
            self._levels[club.id] = club_level(club)
        return self._levels[club.id]

    def _changed(self, *clubs: Club) -> None:
        for club in clubs:
            self._levels.pop(club.id, None)

    def _neighbours(self, club: Club, rng: random.Random) -> list[Club]:
        """Les clubs avec qui il traite : ceux de son championnat, quelques autres."""
        others = [c for c in self.clubs if c.id != club.id]
        home = [c for c in others if c.league == club.league]
        abroad = [c for c in others if c.league != club.league]
        return home + rng.sample(abroad, min(FOREIGN_CLUBS, len(abroad)))

    def _fit(self, club: Club, position: Position) -> list[Player]:
        """Ses joueurs à ce poste qui ne sont pas absents pour longtemps."""
        return [
            p
            for p in club.players_at(position)
            if not (p.is_injured(self.day) and p.injury.return_date - self.day > LONG_ABSENCE)
        ]

    # -- Pré-contrats ----------------------------------------------------------------------

    def approaches(self, rng: random.Random) -> list[Deal]:
        """Les pré-contrats signés ce jour-là dans les championnats en phase retour."""
        deals = []
        for club in self.clubs:
            if club.league not in self.late:
                continue
            for player in list(club.players):
                if (
                    player.loaned_from is not None
                    or player.id in self.taken
                    or not can_precontract(player, self.season_year)
                    or retires_next_season(player)
                    or rng.random() >= poach_chance(player, club) * APPROACH_FACTOR
                ):
                    continue
                offer = self._suitor(player, club, rng)
                if offer is None:
                    continue
                destination, wage = offer
                self.incoming[destination.id] += 1
                self.incoming_wages[destination.id] += wage
                self.taken.add(player.id)
                years = rng.randint(*preferred_years(player))
                deals.append(Deal(DealKind.PRECONTRACT, player, club, destination, wage, years))
        return deals

    def _suitor(self, player: Player, origin: Club, rng: random.Random) -> tuple[Club, int] | None:
        """Le club qui le signe et le salaire convenu : il y serait au moins remplaçant,
        le club ne le surpaie pas et reste sous le plafond salarial. Un international
        d'une fédération qui ne retient que les joueurs du pays y reste."""
        suitors = self._neighbours(origin, rng)
        nation = NATIONS_BY_CODE.get(player.nationality)
        if nation is not None and nation.home_only and home_nation(origin.name) == nation.code:
            suitors = [c for c in suitors if home_nation(c.name) == nation.code]
        offers = []
        for rival in suitors:
            signed = self.incoming[rival.id]
            if signed >= MAX_INCOMING or len(rival.players) + signed >= SQUAD_MAX:
                continue
            if playing_time(player, rival) < TIME_BENCH:
                continue
            wage = wage_demand(player, origin, rival, self.level)
            if wage is None or wage > player.wage * MAX_RAISE:
                continue
            if not fits_next_season(rival, self.season_year, wage, self.incoming_wages[rival.id]):
                continue
            offers.append((move_appeal(player, origin, rival, self.level), -rival.id, rival, wage))
        if not offers:
            return None
        offers.sort(key=lambda offer: offer[:2], reverse=True)
        *_, rival, wage = rng.choice(offers[:SHORTLIST])
        return rival, wage

    # -- Prêts et agents libres ------------------------------------------------------------

    def reinforcements(self, rng: random.Random) -> list[Deal]:
        """Les renforts du jour : un club à court de joueurs valides à un poste engage
        un joker médical (longue blessure), sinon emprunte, sinon signe un agent libre."""
        deals = []
        for club in self.clubs:
            if club.league not in self.active:
                continue
            for position in Position:
                if len(club.players) >= SQUAD_MAX:
                    break
                if len(self._fit(club, position)) >= cover(position):
                    continue
                if rng.random() >= ACT_CHANCE:
                    continue
                long = any(
                    p.injury is not None and allows_joker(p.injury, self.day)
                    for p in club.players_at(position)
                )
                deal = (
                    (self._sign(club, position, DealKind.JOKER) if long else None)
                    or self._borrow(club, position, rng)
                    or self._sign(club, position, DealKind.FREE)
                )
                if deal is not None:
                    deals.append(deal)
        return deals

    def _sign(self, club: Club, position: Position, kind: DealKind) -> Deal | None:
        """Le meilleur agent libre au poste, sous contrat jusqu'à la fin de la saison,
        s'il a le niveau du club : il vaut à peu près le moins bon de ses joueurs du poste,
        et son salaire tient sous le plafond."""
        rating = RATING_FOR_POSITION[position]
        candidates = [
            p
            for p in self.pool
            if p.position == position
            and p.id not in self.taken
            and cap_breach(club, free_agent_wage(p, club)) is None
        ]
        if not candidates:
            return None
        player = max(candidates, key=rating)
        floor = min((rating(p) for p in club.players_at(position)), default=0.0)
        if rating(player) < floor - SIGNING_TOLERANCE:
            return None
        wage = free_agent_wage(player, club)
        self.pool.remove(player)
        player.club_id, player.wage, player.contract_until = club.id, wage, self.season_year
        club.players.append(player)
        self._changed(club)
        return Deal(kind, player, None, club, wage)

    def _borrow(self, club: Club, position: Position, rng: random.Random) -> Deal | None:
        """Le meilleur réserviste qu'un autre club peut prêter à ce poste : son club garde
        de quoi jouer, lui serait au moins remplaçant ici, et son salaire tient sous le plafond."""
        offers = []
        for lender in self._neighbours(club, rng):
            if len(lender.players) <= LENDER_MIN_SQUAD:
                continue
            if len(self._fit(lender, position)) <= cover(position):
                continue
            for player in lender.players_at(position):
                if (
                    player.loaned_from is None
                    and player.id not in self.taken
                    and not player.is_injured(self.day)
                    and playing_time(player, lender) == TIME_RESERVE
                    and playing_time(player, club) >= TIME_BENCH
                    and accepts_loan(player, lender, club, self.level)
                    and cap_breach(club, player.wage) is None
                ):
                    offers.append(
                        (RATING_FOR_POSITION[position](player), -player.id, player, lender)
                    )
        if not offers:
            return None
        *_, player, lender = max(offers, key=lambda offer: offer[:2])
        lender.players.remove(player)
        player.club_id, player.loaned_from = club.id, lender.id
        club.players.append(player)
        self._changed(club, lender)
        return Deal(DealKind.LOAN, player, lender, club, player.wage)

    def play(self, rng: random.Random) -> list[Deal]:
        """Tout ce qui se conclut ce jour-là : renforts, puis pré-contrats."""
        return [*self.reinforcements(rng), *self.approaches(rng)]
