"""La carrière du manager : ses passages dans les clubs (`SpellRow`), ses saisons, sa
réputation, les offres des autres clubs et des sélections (engine/career.py), et
son contrat (engine/manager_contract.py).

Un passage s'ouvre quand le manager prend un club (nouvelle carrière, ou offre
acceptée) et se ferme quand il le quitte : limogé, parti ailleurs, ou remplacé par
une nouvelle carrière. Une saison compte pour le club que le manager dirigeait le
jour de la dernière journée de son championnat (ou aujourd'hui pour la saison en cours).

Un manager qui quitte son club sans autre club où aller (parti de lui-même, ou au
bout de son contrat) laisse un `DismissalRow`, comme un manager limogé : il choisit
ensuite un club à sa portée.
"""

import datetime
from dataclasses import dataclass

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from api import internationals
from api.affairs import ignore_pending
from api.deps import load_clubs
from api.ledger import current_season, game_date, record
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
from engine import manager_contract as terms
from engine.board import SACK_THRESHOLD
from engine.difficulty import rules as difficulty_rules
from engine.economy import TransactionCategory
from engine.match_engine import team_strength
from models import Stage
from models.orm import (
    CareerRow,
    ClubRow,
    DismissalRow,
    LiveMatchRow,
    NegotiationRow,
    SeasonRow,
    SpellRow,
)


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
    resignations = sum(1 for spell in rows if spell.reason == "resigned")
    return rules.reputation(finished, dismissals, resignations)


def reputation_of(session: Session, manager: str) -> float:
    rows = spells(session, manager)
    return manager_reputation(manager_seasons(session, rows), rows)


@dataclass(frozen=True)
class Market:
    """Le niveau du XV (sur 20) et le prestige de chaque club, aujourd'hui."""

    levels: dict[int, float]
    prestige: dict[int, float]


def market(session: Session) -> Market:
    day = game_date(session)
    leagues = {row.id: row.league for row in session.scalars(select(ClubRow))}
    levels = {}
    for club_id, club in load_clubs(session, list(leagues)).items():
        team = team_strength(club, day)
        levels[club_id] = (team.set_piece + team.pack + team.attack + team.defense) / 4
    prestige = {cid: rules.prestige(level, leagues[cid]) for cid, level in levels.items()}
    return Market(levels, prestige)


def season_over(session: Session) -> tuple[CareerRow, SeasonRow] | None:
    """La carrière et la saison, une fois la saison du championnat du manager finie."""
    career = session.scalars(select(CareerRow)).first()
    season = session.scalars(select(SeasonRow).order_by(SeasonRow.year.desc())).first()
    if career is None or season is None:
        return None
    if _phase(season, focus_league(session)) != "finished":
        return None
    return career, season


def offers(
    session: Session, reputation: float | None = None, clubs: Market | None = None
) -> dict[int, float]:
    """Les clubs qui veulent le manager (et le niveau de leur XV, sur 20), une fois la
    saison de son championnat finie (aucun avant, ni pour un sélectionneur)."""
    over = season_over(session)
    if over is None:
        return {}
    career, season = over
    if reputation is None:
        reputation = reputation_of(session, career.manager_name)
    clubs = clubs or market(session)
    candidates = {cid: p for cid, p in clubs.prestige.items() if cid != career.club_id}
    rng = season_rng(season, "offers", career.manager_name)
    chosen = rules.offers(clubs.prestige[career.club_id], candidates, reputation, rng)
    return {club_id: clubs.levels[club_id] for club_id in chosen}


def nation_offer(
    session: Session, reputation: float | None = None, clubs: Market | None = None
) -> tuple[str, float] | None:
    """La sélection qui veut le manager (son code, le niveau de son XV), une fois la
    saison de son championnat finie ; None le plus souvent."""
    over = season_over(session)
    if over is None or not internationals.has_nations(session):
        return None
    career, season = over
    if reputation is None:
        reputation = reputation_of(session, career.manager_name)
    if reputation < rules.NATION_FROM:
        return None
    clubs = clubs or market(session)
    levels = {code: level for code, (_, level) in internationals.nation_levels(session).items()}
    rng = season_rng(season, "nation offer", career.manager_name)
    code = rules.nation_offer(clubs.prestige[career.club_id], levels, reputation, rng)
    return (code, levels[code]) if code is not None else None


def reachable(session: Session, manager: str) -> list[int] | None:
    """Les clubs que peut reprendre un manager parti sans autre club (None : aucun
    départ de ce manager, tous les clubs lui sont ouverts)."""
    last = session.scalars(select(DismissalRow).order_by(DismissalRow.id.desc())).first()
    if last is None or last.manager_name != manager:
        return None
    clubs = market(session)
    candidates = {cid: p for cid, p in clubs.prestige.items() if cid != last.club_id}
    return rules.reachable(
        clubs.prestige[last.club_id], candidates, reputation_of(session, manager)
    )


# --- Le contrat -------------------------------------------------------------------------


def _season_state(session: Session) -> tuple[int, bool]:
    """L'année de la saison en cours, et si celle du championnat du manager est finie."""
    season = current_season(session)
    return season.year, _phase(season, focus_league(session)) == "finished"


def sign(session: Session, career: CareerRow, seasons: int) -> None:
    """Le manager signe pour `seasons` saisons à jouer, la saison en cours comprise tant
    que son championnat n'est pas fini."""
    session.flush()  # le club du manager, pour son championnat
    year, finished = _season_state(session)
    career.contract_until = year + seasons - (0 if finished else 1)
    career.extension_refused_on = None


def contract_until(session: Session, career: CareerRow) -> int:
    """L'échéance du contrat ; une carrière d'avant les contrats en reçoit un, de deux
    saisons à partir de celle en cours."""
    if career.contract_until is None:
        career.contract_until = current_season(session).year + terms.FIRST_CONTRACT - 1
        session.commit()
    return career.contract_until


@dataclass(frozen=True)
class Contract:
    until: int
    left: int  # saisons encore à jouer sous contrat
    board: float  # confiance de la direction, sur 20
    supporters: float
    support: float  # appui de la direction (engine/manager_contract.py)
    granted: int  # saisons de prolongation que la direction accorderait
    # Pourquoi la demande n'est pas possible : too_long (contrat déjà au plus long),
    # too_soon (trop peu de matchs), refused (refus récent) ; None : elle l'est.
    blocked: str | None
    matches_needed: int  # matchs à jouer avant de pouvoir demander (too_soon)
    retry_on: datetime.date | None  # date d'une nouvelle demande (refused)

    @property
    def expiring(self) -> bool:
        """La saison est finie et le contrat aussi : prolonger, signer ailleurs ou partir."""
        return self.left == 0

    @property
    def max_ask(self) -> int:
        return max(0, min(terms.ASK_MAX, terms.MAX_SEASONS - self.left))

    @property
    def indemnity(self) -> int:
        """Ce que verserait à son club un club qui recruterait le manager maintenant."""
        return terms.indemnity(self.left)


def contract(session: Session, career: CareerRow) -> Contract:
    until = contract_until(session, career)
    year, finished = _season_state(session)
    left = terms.remaining(until, year, finished)
    history = History.load(session)
    board = history.board(career.club_id).value
    fervour = history.fervour(career.club_id).value
    demand = difficulty_rules(career.difficulty).sack_threshold - SACK_THRESHOLD
    support = terms.support(board, fervour, demand)

    start = next((s.start for s in spells(session, career.manager_name) if s.end is None), None)
    seen = sum(
        1
        for m in history.everything
        if career.club_id in (m.home_club_id, m.away_club_id) and (start is None or m.date >= start)
    )
    blocked, needed, retry_on = None, 0, None
    if left >= terms.MAX_SEASONS:
        blocked = "too_long"
    elif left > 0 and seen < terms.ASK_AFTER_MATCHES:
        blocked, needed = "too_soon", terms.ASK_AFTER_MATCHES - seen
    elif left > 0 and career.extension_refused_on is not None:
        retry_on = career.extension_refused_on + terms.REFUSAL_COOLDOWN
        if game_date(session) < retry_on:
            blocked = "refused"
        else:
            retry_on = None
    return Contract(
        until=until,
        left=left,
        board=board,
        supporters=fervour,
        support=support,
        granted=terms.grant(support, left),
        blocked=blocked,
        matches_needed=needed,
        retry_on=retry_on,
    )


def extend(session: Session, career: CareerRow, seasons: int) -> terms.Answer:
    """Le manager demande `seasons` saisons de plus ; un refus ferme la porte quelques
    semaines (sauf en fin de contrat, où la direction a déjà dit ce qu'elle voulait)."""
    current = contract(session, career)
    reply = terms.answer(seasons, current.granted)
    if reply.outcome == "accepted":
        career.contract_until = current.until + reply.seasons
        career.extension_refused_on = None
    elif reply.outcome == "refused" and not current.expiring:
        career.extension_refused_on = game_date(session)
    session.commit()
    return reply


def drop_negotiations(session: Session, club_id: int, message: str) -> None:
    for negotiation in session.scalars(
        select(NegotiationRow).where(
            NegotiationRow.club_id == club_id, NegotiationRow.stage.in_(("club", "player"))
        )
    ):
        negotiation.stage = "failed"
        negotiation.closed_by = "me"
        negotiation.message = message


def leave_club(session: Session, career: CareerRow, reason: str, message: str) -> None:
    """Le manager quitte son club (`reason`, celle de son passage) : ses affaires sont
    réglées par le staff, ses négociations tombent, le match en direct aussi."""
    ignore_pending(session)
    drop_negotiations(session, career.club_id, message)
    close_spell(session, career.manager_name, game_date(session), reason)
    session.execute(delete(LiveMatchRow))


def pay_indemnity(
    session: Session, left_club: ClubRow, left: int, payer: ClubRow | None, who: str
) -> None:
    """L'indemnité de départ d'un manager encore sous contrat : versée à son ancien club
    par celui qui le recrute (`payer`, None pour une fédération)."""
    amount = terms.indemnity(left)
    if amount <= 0:
        return
    day = game_date(session)
    record(
        session, left_club, TransactionCategory.STAFF, f"Indemnité de départ de {who}", amount, day
    )
    if payer is not None:
        record(
            session, payer, TransactionCategory.STAFF, f"Indemnité versée pour {who}", -amount, day
        )


def go_free(session: Session, career: CareerRow) -> DismissalRow:
    """Le manager part sans autre club : de lui-même, ou au bout de son contrat. Sa
    carrière s'arrête là, il choisira un club à sa portée."""
    current = contract(session, career)
    reason = "expired" if current.expiring else "resigned"
    leave_club(session, career, reason, "Négociation interrompue : le manager a quitté le club.")
    departure = DismissalRow(
        manager_name=career.manager_name,
        club_id=career.club_id,
        date=game_date(session),
        confidence=round(current.board, 1),
        reason=reason,
    )
    session.add(departure)
    session.delete(career)
    session.commit()
    return departure
