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
from dataclasses import dataclass
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

import engine.history
from api.ledger import game_date
from api.schemas import ClubNotesOut, FormOut, NoteOut, ObjectiveOut
from engine.board import SACK_THRESHOLD, SACK_WARNING
from engine.freshness import team_freshness
from engine.history import AffairBoosts, expected_ranks
from engine.match_engine import team_strength
from engine.notes import Boost, Note
from engine.sponsors import deals_from, sponsor_mood
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
    clubs_by_league: dict[str, list[Club]] = {}
    for club_id, league in season_leagues(season).items():
        clubs_by_league.setdefault(league, []).append(session.get(ClubRow, club_id).to_domain())
    ranks = expected_ranks(clubs_by_league, day)
    for club_id, rank in ranks.items():
        session.add(PreseasonRankRow(season_id=season.id, club_id=club_id, rank=rank))
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


def _affair_boosts(session: Session) -> AffairBoosts:
    """Effets des affaires réglées, par club et par note."""
    boosts: AffairBoosts = {}
    for row in session.scalars(select(AffairRow).where(AffairRow.anchor.is_not(None))):
        for key, delta in (row.effects or {}).items():
            notes = boosts.setdefault(row.club_id, {})
            notes.setdefault(key, []).append((row.season_id, Boost(row.anchor, delta)))
    return boosts


@dataclass(kw_only=True)
class History(engine.history.History):
    """L'historique du monde (engine/history.py), chargé depuis la base."""

    session: Session
    seasons: list[SeasonRow]

    @classmethod
    def load(cls, session: Session) -> "History":
        # Les rangs d'avant-saison peuvent être calculés ici (et enregistrés) :
        # à charger avant de modifier quoi que ce soit dans la session.
        seasons = list(session.scalars(select(SeasonRow).order_by(SeasonRow.year)))
        return cls(
            session=session,
            seasons=seasons,
            season_ids=[season.id for season in seasons],
            by_season=[_played(season.matches) for season in seasons],
            leagues=[season_leagues(season) for season in seasons],
            ranks=[ensure_preseason_ranks(session, season) for season in seasons],
            affair_boosts=_affair_boosts(session),
            sponsor_moods={
                row.id: sponsor_mood(deals_from(row.sponsors))
                for row in session.scalars(select(ClubRow))
                if row.sponsors
            },
        )

    def board(self, club_id: int) -> Note:
        return super().board(club_id, _balance_lookup(self.session, club_id))


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
