"""Notes de vie d'un club : charge l'historique et appelle les calculs du moteur.

Morale et fraîcheur ne regardent que la saison en cours ; cohésion, direction et
supporters ont de la mémoire et parcourent toutes les saisons.

`History` charge les matchs une fois pour toutes ; la journée s'en sert pour la
forme de chaque club (engine/form.py), l'affluence et le jugement de la direction.
Elle charge aussi les décisions du manager entre deux matchs (engine/affairs.py),
qui s'ajoutent aux notes de son club.
"""

import bisect
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date
from functools import cached_property

from sqlalchemy import select
from sqlalchemy.orm import Session

from api.ledger import game_date
from api.schemas import ClubNotesOut, FormOut, NoteOut, ObjectiveOut
from data.leagues import league_config
from engine.board import (
    SACK_THRESHOLD,
    SACK_WARNING,
    BoardSeason,
    Objective,
    board_confidence,
    objective_for,
)
from engine.cohesion import team_cohesion
from engine.form import Form
from engine.freshness import appearances_by_player, squad_freshness, team_freshness
from engine.match_engine import team_strength
from engine.morale import team_morale
from engine.notes import Boost, Note
from engine.supporters import fan_fervour
from models import Club, Match, StaffRole
from models.orm import (
    AffairRow,
    ClubRow,
    MatchRow,
    PreseasonRankRow,
    SeasonRow,
    TransactionRow,
)


def ensure_preseason_ranks(session: Session, season: SeasonRow) -> dict[int, int]:
    """Rang attendu de chaque club dans son championnat pour la saison, calculé (et
    figé) au premier besoin."""
    rows = session.scalars(select(PreseasonRankRow).where(PreseasonRankRow.season_id == season.id))
    ranks = {row.club_id: row.rank for row in rows}
    if ranks:
        return ranks

    day = min((m.date for m in season.matches if m.date is not None), default=None)
    clubs_by_league: dict[str, dict[int, float]] = {}
    for club_id, league in season_leagues(season).items():
        team = team_strength(session.get(ClubRow, club_id).to_domain(), day)
        level = (team.set_piece + team.pack + team.attack + team.defense) / 4
        clubs_by_league.setdefault(league, {})[club_id] = level
    for levels in clubs_by_league.values():
        ordered = sorted(levels, key=levels.get, reverse=True)
        for rank, club_id in enumerate(ordered, start=1):
            session.add(PreseasonRankRow(season_id=season.id, club_id=club_id, rank=rank))
            ranks[club_id] = rank
    session.commit()
    return ranks


def season_leagues(season: SeasonRow) -> dict[int, str]:
    """Championnat de chaque club pendant la saison, d'après son calendrier."""
    leagues = {}
    for m in season.matches:
        leagues[m.home_club_id] = leagues[m.away_club_id] = m.league
    return leagues


def _played(rows: list[MatchRow]) -> list[Match]:
    return [
        m.to_domain() for m in sorted(rows, key=lambda m: (m.date, m.matchday, m.id)) if m.is_played
    ]


def _balance_lookup(session: Session, club_id: int) -> Callable[[date], int | None]:
    """Trésorerie du club à une date, d'après le grand livre (None avant la première opération)."""
    rows = list(
        session.scalars(
            select(TransactionRow)
            .where(TransactionRow.club_id == club_id)
            .order_by(TransactionRow.date, TransactionRow.id)
        )
    )
    dates = [row.date for row in rows]

    def balance_on(day: date) -> int | None:
        index = bisect.bisect_right(dates, day)
        return rows[index - 1].balance_after if index else None

    return balance_on


# club -> note -> [(saison, coup de pouce)]
AffairBoosts = dict[int, dict[str, list[tuple[int, Boost]]]]


def _affair_boosts(session: Session) -> AffairBoosts:
    """Effets des affaires réglées, par club et par note."""
    boosts: AffairBoosts = {}
    for row in session.scalars(select(AffairRow).where(AffairRow.anchor.is_not(None))):
        for key, delta in (row.effects or {}).items():
            notes = boosts.setdefault(row.club_id, {})
            notes.setdefault(key, []).append((row.season_id, Boost(row.anchor, delta)))
    return boosts


@dataclass
class History:
    """Tous les matchs pros joués, saison par saison, et les objectifs de la direction."""

    session: Session
    seasons: list[SeasonRow]
    by_season: list[list[Match]]
    leagues: list[dict[int, str]]  # championnat de chaque club, par saison
    ranks: list[dict[int, int]]  # rang attendu de chaque club dans son championnat, par saison
    affair_boosts: AffairBoosts = field(default_factory=dict)

    @classmethod
    def load(cls, session: Session) -> "History":
        # Les rangs d'avant-saison peuvent être calculés ici (et enregistrés) :
        # à charger avant de modifier quoi que ce soit dans la session.
        seasons = list(session.scalars(select(SeasonRow).order_by(SeasonRow.year)))
        return cls(
            session=session,
            seasons=seasons,
            by_season=[_played(season.matches) for season in seasons],
            leagues=[season_leagues(season) for season in seasons],
            ranks=[ensure_preseason_ranks(session, season) for season in seasons],
            affair_boosts=_affair_boosts(session),
        )

    @property
    def this_season(self) -> list[Match]:
        return self.by_season[-1] if self.by_season else []

    @cached_property
    def everything(self) -> list[Match]:
        return [m for matches in self.by_season for m in matches]

    @cached_property
    def appearances(self) -> dict[int, list[date]]:
        return appearances_by_player(self.everything)

    def boosts(self, club_id: int, key: str, this_season: bool = False) -> list[Boost]:
        """Décisions du manager sur une note (celles de la saison seulement, au besoin)."""
        items = self.affair_boosts.get(club_id, {}).get(key, [])
        if this_season:
            current = self.seasons[-1].id if self.seasons else None
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
        return fan_fervour(club_id, self.by_season, self.boosts(club_id, "supporters"))

    def board(self, club_id: int) -> Note:
        seasons = [
            BoardSeason(
                club_ids=self.league_clubs(club_id, i),
                matches=self.league_matches(club_id, i),
                objective=self.objective(club_id, i),
            )
            for i in range(len(self.seasons))
            if club_id in self.leagues[i]
        ]
        return board_confidence(
            club_id,
            seasons,
            _balance_lookup(self.session, club_id),
            self.boosts(club_id, "board"),
        )

    def form(self, club: Club, day: date) -> Form:
        """Forme du club avant de jouer le jour `day` (tout l'effectif, pour la fraîcheur)."""
        freshness = squad_freshness(
            self.appearances,
            [p.id for p in club.players],
            day,
            club.staff_level(StaffRole.FITNESS_COACH),
            self.boosts(club.id, "freshness"),
        )
        return Form(
            morale=self.morale(club.id).value,
            cohesion=self.cohesion(club.id).value,
            freshness=freshness,
        )


def club_notes(session: Session, club: Club) -> ClubNotesOut:
    history = History.load(session)
    names = {row.id: row.name for row in session.scalars(select(ClubRow))}
    season_ids = {m.id for m in history.this_season}
    day = game_date(session)
    lineup_now = [p.id for p in team_strength(club, day).lineup]

    def out(note: Note) -> NoteOut:
        return NoteOut.from_note(note, club.id, names, season_ids)

    objective = None
    if history.seasons:
        season_objective = history.objective(club.id)
        objective = ObjectiveOut(
            label=season_objective.label,
            target_rank=season_objective.target_rank,
            expected_rank=history.ranks[-1][club.id],
        )

    form = history.form(club, day)
    effects = form.effects(lineup_now)
    freshness = team_freshness(
        club.id,
        history.everything,
        lineup_now,
        day,
        club.staff_level(StaffRole.FITNESS_COACH),
        history.appearances,
        history.boosts(club.id, "freshness"),
    )
    return ClubNotesOut(
        morale=out(history.morale(club.id)),
        cohesion=out(history.cohesion(club.id)),
        freshness=out(freshness),
        board=out(history.board(club.id)),
        supporters=out(history.fervour(club.id)),
        objective=objective,
        form=FormOut(**effects, total=sum(effects.values())),
        sack_threshold=SACK_THRESHOLD,
        sack_warning=SACK_WARNING,
    )
