"""L'historique d'un monde : ses matchs joués, saison par saison, et ce qu'on en tire.

Morale et fraîcheur ne regardent que la saison en cours ; cohésion, direction et
supporters ont de la mémoire et parcourent toutes les saisons. `History` ne fait
que rassembler les matchs et appeler les calculs de chaque note : l'API le
remplit depuis la base (api/notes.py), le monde en mémoire depuis ses propres
listes (engine/world.py).
"""

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date
from functools import cached_property

from data.leagues import league_config
from engine.board import BoardSeason, Objective, board_confidence, objective_for
from engine.cohesion import team_cohesion
from engine.form import Form
from engine.freshness import FULL, appearances_by_player, squad_freshness
from engine.match_engine import team_strength
from engine.morale import team_morale
from engine.notes import Boost, Note
from engine.supporters import fan_fervour
from engine.training import plan_of
from models import Club, Match, StaffRole

# club -> note -> [(saison, coup de pouce)]
AffairBoosts = dict[int, dict[str, list[tuple[int, Boost]]]]


def expected_ranks(clubs_by_league: dict[str, list[Club]], day: date | None) -> dict[int, int]:
    """Rang attendu de chaque club dans son championnat, d'après le niveau de son XV
    au jour `day` : il fixe l'objectif de la direction pour la saison."""
    ranks = {}
    for clubs in clubs_by_league.values():
        levels = {}
        for club in clubs:
            team = team_strength(club, day)
            levels[club.id] = (team.set_piece + team.pack + team.attack + team.defense) / 4
        for rank, club_id in enumerate(sorted(levels, key=levels.get, reverse=True), start=1):
            ranks[club_id] = rank
    return ranks


@dataclass
class History:
    """Tous les matchs pros joués, saison par saison, et les objectifs de la direction."""

    by_season: list[list[Match]]  # dans l'ordre chronologique
    leagues: list[dict[int, str]]  # championnat de chaque club, par saison
    ranks: list[dict[int, int]]  # rang attendu de chaque club dans son championnat, par saison
    season_ids: list[int] = field(default_factory=list)
    affair_boosts: AffairBoosts = field(default_factory=dict)
    # Ce que les supporters pensent des sponsors du maillot (engine/sponsors.py), par club.
    sponsor_moods: dict[int, float] = field(default_factory=dict)
    # Matchs internationaux joués (engine/internationals.py) : ils ne comptent que
    # dans la fatigue des joueurs, pas dans les notes des clubs.
    internationals: list[Match] = field(default_factory=list)

    @property
    def this_season(self) -> list[Match]:
        return self.by_season[-1] if self.by_season else []

    @cached_property
    def everything(self) -> list[Match]:
        return [m for matches in self.by_season for m in matches]

    @cached_property
    def appearances(self) -> dict[int, list[date]]:
        return appearances_by_player([*self.everything, *self.internationals])

    def boosts(self, club_id: int, key: str, this_season: bool = False) -> list[Boost]:
        """Décisions du manager sur une note (celles de la saison seulement, au besoin)."""
        items = self.affair_boosts.get(club_id, {}).get(key, [])
        if this_season:
            current = self.season_ids[-1] if self.season_ids else None
            items = [item for item in items if item[0] == current]
        return [boost for _, boost in items]

    def league_clubs(self, club_id: int, season_index: int = -1) -> list[int]:
        """Les clubs du championnat que jouait `club_id` cette saison-là (lui compris)."""
        leagues = self.leagues[season_index]
        return sorted(c for c, code in leagues.items() if code == leagues[club_id])

    def league_matches(self, club_id: int, season_index: int = -1) -> list[Match]:
        """Les matchs joués du championnat de `club_id` cette saison-là."""
        clubs = set(self.league_clubs(club_id, season_index))
        return [m for m in self.by_season[season_index] if m.home_club_id in clubs]

    def objective(self, club_id: int, season_index: int = -1) -> Objective:
        code = self.leagues[season_index][club_id]
        return objective_for(
            self.ranks[season_index][club_id],
            len(self.league_clubs(club_id, season_index)),
            league_config(code).playoffs.qualifiers,
        )

    def morale(self, club_id: int) -> Note:
        return team_morale(club_id, self.this_season, self.boosts(club_id, "morale", True))

    def cohesion(self, club_id: int) -> Note:
        return team_cohesion(club_id, self.everything, self.boosts(club_id, "cohesion"))

    def fervour(self, club_id: int) -> Note:
        fervour = fan_fervour(club_id, self.by_season, self.boosts(club_id, "supporters"))
        # Les sponsors du maillot pèsent tant qu'ils y sont : on retire le logo, ça passe.
        fervour.nudge(self.sponsor_moods.get(club_id, 0.0))
        return fervour

    def board(
        self, club_id: int, balance_on: Callable[[date], int | None] = lambda day: None
    ) -> Note:
        """Confiance de la direction ; `balance_on` : trésorerie du club à une date."""
        seasons = [
            BoardSeason(
                club_ids=self.league_clubs(club_id, i),
                matches=self.league_matches(club_id, i),
                objective=self.objective(club_id, i),
            )
            for i in range(len(self.by_season))
            if club_id in self.leagues[i]
        ]
        return board_confidence(club_id, seasons, balance_on, self.boosts(club_id, "board"))

    def form(self, club: Club, day: date) -> Form:
        """Forme du club avant de jouer le jour `day` (tout l'effectif, pour la fraîcheur) ;
        le rythme de la semaine d'entraînement (engine/training.py) joue sur la fraîcheur."""
        freshness = squad_freshness(
            self.appearances,
            [p.id for p in club.players],
            day,
            club.staff_level(StaffRole.FITNESS_COACH),
            self.boosts(club.id, "freshness"),
        )
        week = plan_of(club).rhythm.freshness
        if week:
            freshness = {
                player_id: min(FULL, max(0.0, value + week))
                for player_id, value in freshness.items()
            }
        return Form(
            morale=self.morale(club.id).value,
            cohesion=self.cohesion(club.id).value,
            freshness=freshness,
        )
