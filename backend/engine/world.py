"""Un monde entier en mémoire, sans base de données ni manager : pour simuler des
saisons d'affilée et vérifier l'équilibre du jeu sur la durée.

`World` enchaîne ce que fait l'API, avec les mêmes règles : le calendrier et
les phases finales (engine/season.py), chaque jour de match (engine/matchday.py),
la forme des clubs tirée de l'historique (engine/history.py), puis l'intersaison
(fins de contrat, vieillissement, retraites, espoirs, agents libres, montée et
descente). Tous les clubs sont gérés par leur staff : il n'y a ni transferts
négociés, ni affaires, ni travaux, qui passent par les décisions du manager.
Un monde de vrais clubs a aussi ses sélections nationales (engine/internationals.py) :
leurs listes, leurs matchs, et les doublons qui privent les clubs de leurs internationaux.

Le hasard vient de la graine du monde : la même graine rejoue la même histoire.
"""

import datetime
import itertools
from collections.abc import Iterable
from dataclasses import dataclass, field

from data.generator import FIRST_SEASON_YEAR
from data.leagues import PROMOTION, league_config, sort_codes
from data.nations import NATIONS_BY_ID, Nation, home_nation
from engine import internationals
from engine.free_agents import age_free_agent, release, renew_pool, settle_contracts
from engine.history import History, expected_ranks
from engine.matchday import Day, DayReport, play_day
from engine.offseason import RETIREMENT_AGE, club_offseason, develop_player
from engine.season import (
    champion,
    league_table,
    next_date,
    next_playoff_matches,
    phase,
    regular_matchdays,
    rng_for,
    schedule,
    seeding,
)
from models import Club, Match, Player, StandingRow


@dataclass
class SeasonLog:
    """Une saison du monde : ses matchs, et ce qui a été figé à son départ."""

    year: int
    matches: list[Match]  # pros, tous championnats confondus, phases finales comprises
    youth_matches: list[Match]
    leagues: dict[int, str]  # championnat de chaque club cette saison-là
    ranks: dict[int, int]  # rang attendu de chaque club dans son championnat
    played: list[Match] = field(default_factory=list)  # matchs pros joués, dans l'ordre
    # Matchs internationaux (`Match.league` : le code de la fenêtre) et listes annoncées.
    tests: list[Match] = field(default_factory=list)
    squads: dict[internationals.SquadKey, list[int]] = field(default_factory=dict)

    def league_matches(self, league: str) -> list[Match]:
        return [m for m in self.matches if m.league == league]

    def window_matches(self, code: str) -> list[Match]:
        return internationals.window_matches(self.tests, code)


class World:
    def __init__(
        self,
        clubs: Iterable[Club],
        free_agents: Iterable[Player] = (),
        year: int = FIRST_SEASON_YEAR,
        seed: int = 0,
        youth_leagues: bool = False,
    ) -> None:
        """`youth_leagues` : jouer aussi le championnat des espoirs, comme dans le jeu
        (il ne change rien au reste du monde, et double le temps de calcul)."""
        self.clubs = {club.id: club for club in clubs}
        self.free_agents = list(free_agents)
        # Sélections nationales : seulement avec de vrais clubs, qui ont un pays. Leurs
        # joueurs qui évoluent hors des championnats du jeu sont dans `away`.
        self.has_nations = any(home_nation(club.name) for club in self.clubs.values())
        self.away: list[Player] = []
        self.seed = seed
        self.youth_leagues = youth_leagues
        self.seasons: list[SeasonLog] = []
        everyone = [p for c in self.clubs.values() for p in c.players + c.youths]
        last_id = max((p.id for p in [*everyone, *self.free_agents]), default=0)
        self._player_ids = itertools.count(last_id + 1)
        self._start_season(year)

    # -- Lecture ------------------------------------------------------------------------

    @property
    def season(self) -> SeasonLog:
        return self.seasons[-1]

    @property
    def leagues(self) -> list[str]:
        """Codes des championnats de la saison, dans l'ordre de data/leagues.py."""
        return sort_codes(set(self.season.leagues.values()))

    def league_clubs(self, league: str) -> list[Club]:
        return [club for club in self.clubs.values() if self.season.leagues[club.id] == league]

    def table(self, league: str) -> list[StandingRow]:
        """Classement de la saison régulière d'un championnat."""
        return league_table(self.season.league_matches(league)).table()

    def champion(self, league: str) -> Club | None:
        club_id = champion(self.season.league_matches(league))
        return self.clubs[club_id] if club_id is not None else None

    @property
    def finished(self) -> bool:
        """Toutes les finales de la saison sont jouées."""
        return all(phase(self.season.league_matches(code)) == "finished" for code in self.leagues)

    def history(self) -> History:
        return History(
            by_season=[season.played for season in self.seasons],
            leagues=[season.leagues for season in self.seasons],
            ranks=[season.ranks for season in self.seasons],
            season_ids=[season.year for season in self.seasons],
            internationals=[m for season in self.seasons for m in season.tests if m.is_played],
        )

    def eligible(self, nation: Nation) -> list[Player]:
        """Les joueurs que la sélection peut retenir."""
        in_clubs = [
            player
            for club in self.clubs.values()
            for player in club.players
            if internationals.is_eligible(player, nation, club.name)
        ]
        return in_clubs + [p for p in self.away if p.nationality == nation.code]

    # -- La saison ------------------------------------------------------------------------

    def _start_season(self, year: int) -> None:
        by_league: dict[str, list[Club]] = {}
        for club in sorted(self.clubs.values(), key=lambda club: club.id):
            by_league.setdefault(club.league, []).append(club)
        matches = [
            match
            for league, clubs in by_league.items()
            for match in schedule(league_config(league), [c.id for c in clubs], year, league)
        ]
        youth_matches = []
        if self.youth_leagues:
            # Les espoirs jouent les mêmes affiches, le même jour.
            youth_matches = [
                Match(m.home_club_id, m.away_club_id, m.matchday, date=m.date, league=m.league)
                for m in matches
            ]
        tests = []
        if self.has_nations:
            tests = internationals.schedule(year)
            rng = rng_for(self.seed, year, "internationals")
            for nation in internationals.participants():
                self.away += internationals.reinforcements(
                    nation, self.eligible(nation), self._player_ids, rng, year
                )
        self.seasons.append(
            SeasonLog(
                year=year,
                matches=matches,
                youth_matches=youth_matches,
                leagues={club.id: club.league for club in self.clubs.values()},
                # Figé maintenant : l'objectif de la direction en dépend.
                ranks=expected_ranks(by_league, min(m.date for m in matches)),
                tests=tests,
            )
        )

    def _next_day(self) -> datetime.date | None:
        """Ouvre les tours de phases finales prêts et annonce les listes des sélections
        dues ; renvoie le prochain jour de match, clubs et sélections confondus."""
        season = self.season
        for league in self.leagues:
            season.matches += next_playoff_matches(
                league_config(league), season.league_matches(league), season.year
            )
        season.tests += internationals.next_round(season.tests, season.year)
        day = next_date([*season.matches, *season.tests])
        if day is not None:
            for code, team in internationals.due_lists(season.tests, season.squads, day):
                first = min(m.date for m in season.window_matches(code))
                squad = internationals.pick_squad(self.eligible(NATIONS_BY_ID[team]), first)
                season.squads[(code, team)] = [p.id for p in squad]
        return day

    def play_day(self) -> DayReport | None:
        """Joue le prochain jour de match, tous championnats confondus (None si la
        saison est terminée)."""
        day = self._next_day()
        if day is None:
            return None
        season = self.season
        todays = [m for m in season.matches if not m.is_played and m.date == day]
        todays.sort(key=lambda m: m.league)  # tri stable : l'ordre du calendrier est gardé
        leagues = sorted({m.league for m in todays})
        history = self.history()
        playing = [club for club in self.clubs.values() if club.league in leagues]
        # Doublon : les joueurs retenus par une sélection qui joue aujourd'hui manquent.
        away = internationals.absentees(season.tests, season.squads, day)
        for club in playing:
            internationals.release(club, away, day)
        world = Day(
            date=day,
            clubs=self.clubs,
            forms={club.id: history.form(club, day) for club in playing},
            leagues={league: league_config(league) for league in leagues},
            seeding={league: seeding(season.league_matches(league)) for league in leagues},
            regular_matchdays={
                league: regular_matchdays(season.league_matches(league)) for league in leagues
            },
            fervour=lambda club_id: history.fervour(club_id).value,
        )
        youth = [m for m in season.youth_matches if not m.is_played and m.date == day]
        report = play_day(world, todays, rng_for(self.seed, day), youth_matches=youth)
        season.played += report.played
        for movement in report.movements:
            self.clubs[movement.club_id].balance += movement.amount
        for club in playing:
            internationals.release(club, (), day)  # les internationaux rentrent
        self._play_tests(day, history)
        return report

    def _play_tests(self, day: datetime.date, history: History) -> None:
        """Les matchs internationaux du jour, chaque sélection avec sa liste."""
        season = self.season
        tests = [m for m in season.tests if not m.is_played and m.date == day]
        if not tests:
            return
        everyone = {p.id: p for club in self.clubs.values() for p in club.players}
        everyone.update({p.id: p for p in self.away})
        teams, forms = {}, {}
        for match in tests:
            for team in (match.home_club_id, match.away_club_id):
                squad = [everyone[i] for i in season.squads[(match.league, team)] if i in everyone]
                teams[team] = internationals.national_team(NATIONS_BY_ID[team], squad)
                forms[team] = internationals.national_form(teams[team], history.appearances, day)
        internationals.play_tests(
            day,
            tests,
            teams,
            rng_for(self.seed, day, "internationals"),
            forms,
            staff_of=lambda player: self.clubs.get(player.club_id, internationals.NO_CLUB),
        )

    def play_season(self) -> SeasonLog:
        """Joue tout ce qu'il reste de la saison, phases finales comprises."""
        while self.play_day() is not None:
            pass
        return self.season

    # -- L'intersaison ---------------------------------------------------------------------

    def _promotion(self) -> None:
        """Le champion de la division du dessous monte, le dernier de celle du dessus descend."""
        lower, upper = PROMOTION
        if lower not in self.leagues or upper not in self.leagues:
            return
        promoted = self.champion(lower)
        relegated = self.clubs[seeding(self.season.league_matches(upper))[-1]]
        promoted.league, relegated.league = upper, lower

    def offseason(self) -> SeasonLog:
        """Passe à la saison suivante (à appeler une fois la saison terminée), dans
        l'ordre de l'API : montée et descente, fins de contrat, agents libres,
        vieillissement et retraites, espoirs, recrutement, nouveau calendrier."""
        if not self.finished:
            raise ValueError("La saison n'est pas terminée")
        self._promotion()
        year = self.season.year + 1
        rng = rng_for(self.seed, year, "offseason")
        clubs = sorted(self.clubs.values(), key=lambda club: club.id)

        leaving = [player for club in clubs for player in settle_contracts(club, year, rng)]
        for player in leaving:
            release(player, year)
        self.free_agents += leaving
        self.free_agents = [p for p in self.free_agents if age_free_agent(p, year, rng)]

        for club in clubs:
            moves = club_offseason(club, self._player_ids, rng, year)
            for youth in moves.released:
                release(youth, year)
            self.free_agents += moves.released
        renew_pool(clubs, self.free_agents, year, rng, self._player_ids)
        # Hors des championnats du jeu aussi, on vieillit et on raccroche.
        for player in self.away:
            player.age += 1
            develop_player(player, internationals.AWAY_TRAINING_LEVEL, rng)
        self.away = [p for p in self.away if p.age < RETIREMENT_AGE]

        self._start_season(year)
        return self.season
