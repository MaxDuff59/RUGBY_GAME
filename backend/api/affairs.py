"""Affaires entre deux matchs : décrit le club au moteur, enregistre et règle les affaires.

Le cycle, autour de chaque journée (api/routers/seasons.py) :
1. avant de jouer, une affaire restée sans réponse est réglée d'office (`ignore_pending`) ;
2. après, les promesses sont tranchées sur le match du jour (`settle_promises`),
   puis une nouvelle affaire est peut-être tirée (`draw_affair`) ;
3. entre deux journées, le manager répond (`answer`, api/routers/affairs.py).
"""

import random
from datetime import date, timedelta

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from api.ledger import game_date, record
from api.notes import History
from api.schemas import AffairOptionOut, AffairOut
from engine.affairs import (
    CATALOGUE,
    CATEGORY_LABELS,
    EXTENSION_RAISE,
    EXTENSION_YEARS,
    IGNORED,
    RAISE_SHARE,
    STAFF_RAISE_SHARE,
    Action,
    Draft,
    Fixture,
    PastChoice,
    PlayerInfo,
    PromiseKind,
    Result,
    Situation,
    StaffInfo,
    draw,
    follow_up,
    promise_kept,
    render,
)
from engine.economy import TransactionCategory
from engine.match_engine import team_strength
from engine.notes import scores
from engine.season import record_result
from models import Club, Match, Player, Season, Squad, Stage, StandingRow
from models.orm import AffairRow, CareerRow, ClubRow, MatchRow, PlayerRow, SeasonRow, StaffRow

RECENT_COUNT = 8


# --- Lecture -----------------------------------------------------------------------------


def pending_affairs(session: Session, club_id: int) -> list[AffairRow]:
    return list(
        session.scalars(
            select(AffairRow)
            .where(AffairRow.club_id == club_id, AffairRow.answered_on.is_(None))
            .order_by(AffairRow.id)
        )
    )


def recent_affairs(session: Session, club_id: int) -> list[AffairRow]:
    return list(
        session.scalars(
            select(AffairRow)
            .where(AffairRow.club_id == club_id, AffairRow.answered_on.is_not(None))
            .order_by(AffairRow.id.desc())
            .limit(RECENT_COUNT)
        )
    )


def affair_out(row: AffairRow) -> AffairOut:
    scenario = CATALOGUE[row.scenario]
    ctx = row.context
    chosen = next((o for o in scenario.options if o.key == row.choice), None)
    return AffairOut(
        id=row.id,
        scenario=row.scenario,
        category=scenario.category.value,
        category_label=CATEGORY_LABELS[scenario.category],
        title=scenario.title,
        text=render(scenario.text, ctx),
        date=row.created_on,
        player_id=ctx.get("player_id"),
        options=[AffairOptionOut(key=o.key, label=render(o.label, ctx)) for o in scenario.options],
        answered=row.answered_on is not None,
        choice=row.choice,
        choice_label=render(chosen.label, ctx) if chosen else None,
        outcome=row.outcome,
        effects={key: round(value, 1) for key, value in (row.effects or {}).items()},
        money=row.money,
        promise=row.promise,
    )


def forced_starters(session: Session, club_id: int) -> set[int]:
    """Joueurs à qui une titularisation a été promise pour le prochain match."""
    rows = session.scalars(
        select(AffairRow).where(
            AffairRow.club_id == club_id,
            AffairRow.promise == PromiseKind.START.value,
            AffairRow.promise_settled.is_(False),
        )
    )
    return {row.context["player_id"] for row in rows if row.context.get("player_id")}


def _last_played_day(session: Session) -> date:
    """Date du dernier match pro joué : les décisions comptent à partir de là."""
    last = session.scalars(
        select(MatchRow)
        .where(MatchRow.home_score.is_not(None), MatchRow.squad == "pro")
        .order_by(MatchRow.date.desc())
    ).first()
    return last.date if last is not None else game_date(session) - timedelta(days=1)


# --- Situation du club -----------------------------------------------------------------


def _player_info(player: Player, starts: dict[int, int], year: int, day: date) -> PlayerInfo:
    injured = player.injury.weeks_left(day) if player.is_injured(day) else 0
    return PlayerInfo(
        id=player.id,
        name=player.name,
        position=player.position,
        age=player.age,
        overall=player.overall,
        starts=starts.get(player.id, 0),
        years_left=player.years_left(year),
        injured_weeks=injured,
        youth=player.squad == Squad.YOUTH,
    )


def _standings(history: History) -> list[int]:
    """Clubs du 1er au dernier de la saison régulière en cours."""
    table = Season(year=0, clubs=[])
    table.standings = {cid: StandingRow(club_id=cid) for cid in history.club_ids}
    for match in history.this_season:
        if match.stage == Stage.REGULAR:
            record_result(table, match)
    return [row.club_id for row in table.table()]


def _streak(club_id: int, matches: list[Match]) -> int:
    """+n victoires de suite, −n défaites de suite (0 après un nul)."""
    streak = 0
    for match in reversed(matches):
        scored, conceded = scores(match, club_id)
        sign = 1 if scored > conceded else -1 if scored < conceded else 0
        if sign == 0 or (streak and (streak > 0) != (sign > 0)):
            break
        streak += sign
    return streak


def build_situation(session: Session, club_row: ClubRow, season: SeasonRow) -> Situation:
    history = History.load(session)
    club: Club = club_row.to_domain()
    day = game_date(session)
    names = {row.id: row.name for row in session.scalars(select(ClubRow))}

    mine = [m for m in history.this_season if club.id in (m.home_club_id, m.away_club_id)]
    starts: dict[int, int] = {}
    for match in mine:
        if match.stage == Stage.REGULAR:
            lineup = match.home_lineup if match.home_club_id == club.id else match.away_lineup
            for player_id in lineup:
                starts[player_id] = starts.get(player_id, 0) + 1

    seeding = _standings(history)
    rank_of = {club_id: rank for rank, club_id in enumerate(seeding, start=1)}

    last = None
    if mine:
        match = mine[-1]
        scored, conceded = scores(match, club.id)
        opponent = match.away_club_id if match.home_club_id == club.id else match.home_club_id
        last = Result(
            opponent=names[opponent],
            scored=scored,
            conceded=conceded,
            at_home=match.home_club_id == club.id and not match.neutral,
            stage=match.stage,
        )

    upcoming = sorted(
        (
            m
            for m in season.matches
            if not m.is_played and club.id in (m.home_club_id, m.away_club_id)
        ),
        key=lambda m: m.date,
    )
    fixture = None
    if upcoming:
        match = upcoming[0]
        opponent = match.away_club_id if match.home_club_id == club.id else match.home_club_id
        fixture = Fixture(
            opponent=names[opponent],
            opponent_rank=rank_of.get(opponent),
            at_home=match.home_club_id == club.id and not match.neutral,
            stage=Stage(match.stage),
        )

    lineup = [p.id for p in team_strength(club, day).lineup]
    notes = {
        "morale": history.morale(club.id).value,
        "cohesion": history.cohesion(club.id).value,
        "freshness": history.form(club, day).lineup_freshness(lineup),
        "board": history.board(club.id).value,
        "supporters": history.fervour(club.id).value,
    }

    past = [
        PastChoice(
            scenario=row.scenario,
            choice=row.choice,
            player_id=row.context.get("player_id"),
            day=row.created_on,
            player_name=row.context.get("player"),
            this_season=row.season_id == season.id,
        )
        for row in session.scalars(select(AffairRow).where(AffairRow.club_id == club.id))
    ]
    # Matchs joués depuis la dernière affaire de la saison (datée du jour du match suivant).
    last_affair = max((p.day for p in past if p.this_season), default=None)
    since = sum(1 for m in mine if last_affair is None or m.date >= last_affair)

    return Situation(
        club=club.name,
        day=day,
        rank=rank_of.get(club.id),
        club_count=len(history.club_ids),
        target_rank=history.objective(club.id).target_rank if history.seasons else None,
        played=sum(1 for m in mine if m.stage == Stage.REGULAR),
        regular_rounds=2 * (len(history.club_ids) - 1),
        last=last,
        streak=_streak(club.id, mine),
        next=fixture,
        notes=notes,
        balance=club.balance,
        academy_level=club.facilities.academy_level,
        players=[_player_info(p, starts, season.year, day) for p in club.players],
        youths=[_player_info(p, starts, season.year, day) for p in club.youths],
        staff=[StaffInfo(s.id, s.name, s.role, s.level) for s in club.staff],
        past=past,
        matches_since_affair=since,
    )


# --- Cycle autour de la journée ---------------------------------------------------------


def _save(session: Session, club_id: int, season: SeasonRow, draft: Draft) -> AffairRow:
    row = AffairRow(
        club_id=club_id,
        season_id=season.id,
        scenario=draft.scenario.key,
        created_on=game_date(session),
        context=draft.context,
    )
    session.add(row)
    return row


def _settle(
    session: Session, club_row: ClubRow, row: AffairRow, effects: dict, money: int, outcome: str
) -> None:
    row.answered_on = game_date(session)
    row.anchor = _last_played_day(session)
    row.effects = {key: value for key, value in effects.items() if value}
    row.money = money
    row.outcome = outcome
    if money:
        title = CATALOGUE[row.scenario].title
        record(
            session,
            club_row,
            TransactionCategory.AFFAIRS,
            f"Vie du club · {title}",
            money,
            row.answered_on,
        )


def ignore_pending(session: Session) -> None:
    """Avant de jouer : les affaires sans réponse sont réglées d'office.

    Une affaire à une seule réponse (une suite de promesse) la prend ; les autres
    prennent la réaction « sans réponse » de leur catégorie.
    """
    career = session.scalars(select(CareerRow)).first()
    if career is None:
        return
    club_row = session.get(ClubRow, career.club_id)
    for row in pending_affairs(session, career.club_id):
        scenario = CATALOGUE[row.scenario]
        if len(scenario.options) == 1:
            option = scenario.options[0]
            _settle(
                session,
                club_row,
                row,
                option.effects,
                option.money,
                render(option.outcome, row.context),
            )
            row.choice = option.key
        else:
            effects, outcome = IGNORED[scenario.category]
            _settle(session, club_row, row, effects, 0, outcome)
    session.commit()


def settle_promises(session: Session, season: SeasonRow, day: date) -> list[AffairRow]:
    """Tranche les promesses sur le match du jour du club dirigé ; renvoie les suites."""
    career = session.scalars(select(CareerRow)).first()
    if career is None:
        return []
    club_id = career.club_id
    match = next(
        (
            m
            for m in season.matches
            if m.date == day and m.is_played and club_id in (m.home_club_id, m.away_club_id)
        ),
        None,
    )
    if match is None:
        return []

    domain = match.to_domain()
    scored, conceded = scores(domain, club_id)
    lineup = domain.home_lineup if domain.home_club_id == club_id else domain.away_lineup
    opponent_id = domain.away_club_id if domain.home_club_id == club_id else domain.home_club_id
    result = Result(
        opponent=session.get(ClubRow, opponent_id).name,
        scored=scored,
        conceded=conceded,
        at_home=domain.home_club_id == club_id,
        stage=domain.stage,
    )

    follow_ups = []
    rows = session.scalars(
        select(AffairRow).where(
            AffairRow.club_id == club_id,
            AffairRow.promise.is_not(None),
            AffairRow.promise_settled.is_(False),
        )
    )
    for row in list(rows):
        row.promise_settled = True
        option = next(o for o in CATALOGUE[row.scenario].options if o.key == row.choice)
        kept = promise_kept(
            PromiseKind(row.promise), row.context.get("player_id"), lineup, scored > conceded
        )
        key = option.promise.kept if kept else option.promise.broken
        if key is not None:
            follow_ups.append(_save(session, club_id, season, follow_up(key, row.context, result)))
    session.commit()
    return follow_ups


def draw_affair(session: Session, season: SeasonRow, rng: random.Random) -> AffairRow | None:
    """Après une journée : peut-être une nouvelle affaire pour le club dirigé."""
    career = session.scalars(select(CareerRow)).first()
    if career is None or pending_affairs(session, career.club_id):
        return None
    club_row = session.get(ClubRow, career.club_id)
    draft = draw(build_situation(session, club_row, season), rng)
    if draft is None:
        return None
    row = _save(session, club_row.id, season, draft)
    session.commit()
    return row


# --- Réponse ----------------------------------------------------------------------------


def _my_player(session: Session, club_row: ClubRow, player_id: int | None) -> PlayerRow:
    row = session.get(PlayerRow, player_id) if player_id is not None else None
    if row is None or row.club_id != club_row.id:
        raise HTTPException(status_code=400, detail="Ce joueur n'est plus au club")
    return row


def _act(session: Session, club_row: ClubRow, action: Action, ctx: dict) -> None:
    """Exécute l'action d'une réponse (lève une HTTPException si elle est impossible)."""
    # Imports locaux : ces routeurs importent eux-mêmes beaucoup de modules de l'API.
    from api.routers.academy import promote
    from api.routers.transfers import sell

    player_id = ctx.get("player_id")
    if action == Action.RAISE_WAGE:
        row = _my_player(session, club_row, player_id)
        row.wage = round(row.wage * (1 + RAISE_SHARE))
    elif action == Action.EXTEND:
        row = _my_player(session, club_row, player_id)
        row.contract_until += EXTENSION_YEARS
        row.wage = round(row.wage * (1 + EXTENSION_RAISE))
    elif action == Action.SELL:
        _my_player(session, club_row, player_id)
        sell(player_id, session)
    elif action == Action.PROMOTE:
        _my_player(session, club_row, player_id)
        promote(player_id, session)
    elif action in (Action.STAFF_RAISE, Action.STAFF_LEAVE):
        member = session.get(StaffRow, ctx.get("staff_id"))
        if member is None or member.club_id != club_row.id:
            raise HTTPException(status_code=400, detail="Ce membre du staff n'est plus au club")
        if action == Action.STAFF_RAISE:
            member.wage = round(member.wage * (1 + STAFF_RAISE_SHARE))
        else:
            member.club_id = None


def answer(session: Session, club_row: ClubRow, row: AffairRow, choice: str) -> AffairRow:
    if row.answered_on is not None:
        raise HTTPException(status_code=400, detail="Cette affaire est déjà réglée")
    scenario = CATALOGUE[row.scenario]
    option = next((o for o in scenario.options if o.key == choice), None)
    if option is None:
        raise HTTPException(status_code=400, detail=f"Réponse inconnue : {choice}")

    if option.action is not None:
        _act(session, club_row, option.action, row.context)

    notes = {}
    if option.gamble is not None:
        history = History.load(session)
        notes = {"board": history.board(club_row.id).value}
    effects, outcome = option.resolve(notes, random.Random())
    _settle(session, club_row, row, effects, option.money, render(outcome, row.context))
    row.choice = option.key
    if option.promise is not None:
        row.promise = option.promise.kind.value
    session.commit()
    return row
