"""La carrière du manager : ses passages dans les clubs (`SpellRow`), ses saisons, sa
réputation et les offres des autres clubs (engine/career.py).

Un passage s'ouvre quand le manager prend un club (nouvelle carrière, ou offre
acceptée) et se ferme quand il le quitte : limogé, parti ailleurs, ou remplacé par
une nouvelle carrière. Une saison compte pour le club que le manager dirigeait le
jour de la dernière journée de son championnat (ou aujourd'hui pour la saison en cours).
"""

import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from api.deps import load_clubs
from api.ledger import game_date
from api.notes import History, season_leagues
from api.routers.seasons import (
    _champion_id,
    _league_matches,
    _phase,
    _standings,
    focus_league,
    season_rng,
)
from engine import career as rules
from engine.match_engine import team_strength
from models import Stage
from models.orm import CareerRow, ClubRow, SeasonRow, SpellRow


def open_spell(session: Session, manager: str, club_id: int, day: datetime.date) -> None:
    """Le manager prend `club_id` ; un passage resté ouvert (carrière abandonnée) se ferme."""
    close_spell(session, manager, day, "quit")
    session.add(SpellRow(manager_name=manager, club_id=club_id, start=day))


def close_spell(session: Session, manager: str, day: datetime.date, reason: str) -> None:
    for spell in session.scalars(
        select(SpellRow).where(SpellRow.manager_name == manager, SpellRow.end.is_(None))
    ):
        spell.end, spell.reason = day, reason


def spells(session: Session, manager: str) -> list[SpellRow]:
    """Les passages du manager, dans l'ordre ; une carrière d'avant les passages en
    reçoit un, ouvert depuis la première saison."""
    rows = list(
        session.scalars(
            select(SpellRow).where(SpellRow.manager_name == manager).order_by(SpellRow.id)
        )
    )
    career = session.scalars(select(CareerRow)).first()
    if not rows and career is not None and career.manager_name == manager:
        first = session.scalars(select(SeasonRow).order_by(SeasonRow.year)).first()
        start = min(m.date for m in first.matches) if first else game_date(session)
        open_spell(session, manager, career.club_id, start)
        session.commit()
        return spells(session, manager)
    return rows


def _club_on(rows: list[SpellRow], day: datetime.date) -> int | None:
    for spell in rows:
        if spell.start <= day and (spell.end is None or day <= spell.end):
            return spell.club_id
    return None


def manager_seasons(session: Session, rows: list[SpellRow]) -> list[rules.Season]:
    """Les saisons du manager (finies ou en cours), chacune dans le club qu'il dirigeait."""
    seasons = list(session.scalars(select(SeasonRow).order_by(SeasonRow.year)))
    history = History.load(session) if seasons else None
    out = []
    for index, season in enumerate(seasons):
        leagues = season_leagues(season)
        # Le club du manager le jour de la dernière journée de son championnat.
        for club_id in {spell.club_id for spell in rows}:
            league = leagues.get(club_id)
            if league is None:
                continue
            dates = [m.date for m in _league_matches(season, league)]
            finished = _phase(season, league) == "finished"
            day = max(dates) if finished else game_date(session)
            if _club_on(rows, day) != club_id:
                continue
            table = _standings(season, league).table()
            line = next((r for r in table if r.club_id == club_id), None)
            rank = [r.club_id for r in table].index(club_id) + 1 if line and line.played else None
            playoffs = any(
                m.stage != Stage.REGULAR.value and club_id in (m.home_club_id, m.away_club_id)
                for m in _league_matches(season, league)
            )
            expected = history.ranks[index].get(club_id) if index < len(history.ranks) else None
            out.append(
                rules.Season(
                    year=season.year,
                    club_id=club_id,
                    champion=finished and _champion_id(season, league) == club_id,
                    playoffs=playoffs,
                    rank=rank if finished else None,
                    expected=expected if finished else None,
                )
            )
    return out


def manager_reputation(seasons: list[rules.Season], rows: list[SpellRow]) -> float:
    """La réputation du manager d'après ses saisons finies et ses limogeages."""
    finished = [s for s in seasons if s.rank is not None]
    dismissals = sum(1 for spell in rows if spell.reason == "dismissed")
    return rules.reputation(finished, dismissals)


def offers(session: Session, reputation: float | None = None) -> dict[int, float]:
    """Les clubs qui veulent le manager (et le niveau de leur XV, sur 20), une fois la
    saison de son championnat finie (aucun avant, ni pour un sélectionneur)."""
    career = session.scalars(select(CareerRow)).first()
    season = session.scalars(select(SeasonRow).order_by(SeasonRow.year.desc())).first()
    if career is None or season is None:
        return {}
    if _phase(season, focus_league(session)) != "finished":
        return {}
    if reputation is None:
        rows = spells(session, career.manager_name)
        reputation = manager_reputation(manager_seasons(session, rows), rows)
    day = game_date(session)
    leagues = {row.id: row.league for row in session.scalars(select(ClubRow))}
    clubs = load_clubs(session, list(leagues))
    levels = {}
    for club_id, club in clubs.items():
        team = team_strength(club, day)
        levels[club_id] = (team.set_piece + team.pack + team.attack + team.defense) / 4
    prestige = {cid: rules.prestige(level, leagues[cid]) for cid, level in levels.items()}
    candidates = {cid: p for cid, p in prestige.items() if cid != career.club_id}
    rng = season_rng(season, "offers", career.manager_name)
    chosen = rules.offers(prestige[career.club_id], candidates, reputation, rng)
    return {club_id: levels[club_id] for club_id in chosen}
