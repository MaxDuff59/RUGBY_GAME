"""Le calendrier international de la saison : fenêtres, matchs, classements, listes.

Lisible depuis toute carrière. Un manager de club y suit ses joueurs retenus ;
un sélectionneur y lit ses adversaires (ses propres décisions passent par
api/routers/selection.py).
"""

import datetime

from fastapi import APIRouter, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from api import internationals
from api.deps import SessionDep
from api.ledger import current_season, game_date
from api.schemas import (
    CalledPlayer,
    ClubRef,
    InternationalsOut,
    MatchSummary,
    NationOut,
    NationSquadOut,
    NationSummary,
    PlayerOut,
    PlayerRef,
    PoolTableOut,
    SquadPlayerOut,
    StandingOut,
    WindowOut,
)
from data.nations import NATIONS_BY_CODE, NATIONS_BY_ID, WINDOWS, WINDOWS_BY_CODE, Nation, Window
from engine import internationals as rules
from engine.match_engine import team_strength
from engine.season import league_table
from models import Match, Player
from models.orm import CareerRow, InternationalRow, PlayerRow, SeasonRow

router = APIRouter(prefix="/internationals", tags=["sélections"])

NATION_NAMES = {nation.id: nation.name for nation in NATIONS_BY_ID.values()}


def nation_out(nation: Nation) -> NationOut:
    return NationOut(id=nation.id, code=nation.code, name=nation.name)


def summary(row: InternationalRow) -> MatchSummary:
    return MatchSummary.from_match(row.to_domain(), NATION_NAMES)


def player_ref(player: Player) -> PlayerRef:
    return PlayerRef(
        id=player.id,
        name=player.name,
        position=player.position,
        age=player.age,
        overall=player.overall,
    )


def _standings(matches: list[Match]) -> list[StandingOut]:
    return [
        StandingOut(
            rank=rank,
            club_id=row.club_id,
            club_name=NATION_NAMES[row.club_id],
            played=row.played,
            won=row.won,
            drawn=row.drawn,
            lost=row.lost,
            points_for=row.points_for,
            points_against=row.points_against,
            points_difference=row.points_difference,
            tries_for=row.tries_for,
            offensive_bonus=row.offensive_bonus,
            defensive_bonus=row.defensive_bonus,
            league_points=row.league_points,
        )
        for rank, row in enumerate(league_table(matches).table(), start=1)
    ]


def window_out(
    window: Window,
    rows: list[InternationalRow],
    lists: dict[rules.SquadKey, list[int]],
    year: int,
) -> WindowOut:
    """Une fenêtre de la saison `year` telle qu'on la lit : `rows` sont ses matchs,
    `lists` les listes de la saison."""
    matches = [row.to_domain() for row in rows]
    teams = sorted({team for m in matches for team in (m.home_club_id, m.away_club_id)})
    world_cup = window.format == "world_cup"
    pools = []
    if world_cup:
        pools = [
            PoolTableOut(
                name=f"Poule {letter}", standings=_standings(rules.pool_matches(matches, pool))
            )
            for letter, pool in zip("ABCD", rules.world_cup_pools(year), strict=True)
        ]
    winner = rules.champion(window, matches)
    return WindowOut(
        code=window.code,
        name=window.name,
        short_name=window.short_name,
        has_table=window.has_table,
        announce_by=rules.announce_by(matches),
        announced=any((window.code, team) in lists for team in teams),
        dates=sorted({*rules.window_dates(window, year), *(m.date for m in matches)}),
        nations=[nation_out(NATIONS_BY_ID[team]) for team in teams],
        matches=[MatchSummary.from_match(m, NATION_NAMES) for m in matches],
        standings=_standings(matches) if window.has_table and not world_cup else [],
        pools=pools,
        finished=rules.is_finished(window, matches),
        champion=ClubRef(id=winner, name=NATION_NAMES[winner]) if winner is not None else None,
    )


def windows_out(session: Session, season: SeasonRow) -> list[WindowOut]:
    rows = internationals.test_rows(session, season)
    lists = internationals.squads(session, season)
    out = []
    for window in WINDOWS:
        ours = [row for row in rows if row.competition == window.code]
        if ours:
            out.append(window_out(window, ours, lists, season.year))
    return out


def season_starts(season: SeasonRow, rows: list[InternationalRow]) -> dict[int, int]:
    """Titularisations de chaque joueur cette saison, club et sélection."""
    starts: dict[int, int] = {}
    for match in [*season.matches, *rows]:
        if match.is_played:
            for player_id in (*match.home_lineup, *match.away_lineup):
                starts[player_id] = starts.get(player_id, 0) + 1
    return starts


def squad_player_out(
    player: Player, day: datetime.date, names: dict[int, str], starts: dict[int, int]
) -> SquadPlayerOut:
    club = None
    if player.club_id is not None:
        club = ClubRef(id=player.club_id, name=names[player.club_id])
    return SquadPlayerOut(
        player=PlayerOut.from_player(player, day, names),
        club=club,
        position_rating=round(rules.position_rating(player), 1),
        starts=starts.get(player.id, 0),
    )


def _season_or_404(session: Session) -> SeasonRow:
    season = current_season(session)
    if season is None:
        raise HTTPException(status_code=404, detail="Aucune saison : commence une carrière")
    return season


@router.get("", response_model=InternationalsOut)
def get_internationals(session: SessionDep) -> InternationalsOut:
    """Les fenêtres internationales de la saison (aucune dans un monde de clubs inventés)."""
    season = _season_or_404(session)
    internationals.ensure_calendar(session, season)
    my_players = []
    career = session.scalars(select(CareerRow)).first()
    if career is not None:
        duties = internationals.club_duties(session, career.club_id)
        rows = session.scalars(select(PlayerRow).where(PlayerRow.id.in_(list(duties))))
        my_players = [
            CalledPlayer(
                player=player_ref(row.to_domain()),
                nation=nation_out(duties[row.id].nation),
                competition=duties[row.id].window.name,
                dates=duties[row.id].dates,
            )
            for row in rows
        ]
    return InternationalsOut(
        year=season.year,
        today=game_date(session),
        windows=windows_out(session, season),
        my_players=my_players,
    )


@router.get("/nations", response_model=list[NationSummary])
def list_nations(session: SessionDep) -> list[NationSummary]:
    """Les sélections que l'on peut diriger, avec leur vivier et le niveau de leur XV."""
    if not internationals.has_nations(session):
        return []
    day = game_date(session)
    pool = internationals.eligible_players(session)
    summaries = []
    for nation in rules.selectable():
        players = pool[nation.code]
        team = team_strength(rules.national_team(nation, rules.pick_squad(players, day)), day)
        level = (team.set_piece + team.pack + team.attack + team.defense) / 4
        summaries.append(
            NationSummary(
                id=nation.id,
                code=nation.code,
                name=nation.name,
                player_count=len(players),
                level=round(level, 1),
                # Ses rendez-vous de chaque saison (la Coupe du monde vient en plus).
                competitions=[
                    w.name for w in WINDOWS if w is not rules.WORLD_CUP and nation.code in w.teams
                ],
            )
        )
    return summaries


@router.get("/{competition}/{code}", response_model=NationSquadOut)
def get_squad(competition: str, code: str, session: SessionDep) -> NationSquadOut:
    """La liste d'une sélection pour une fenêtre (vide tant qu'elle n'est pas annoncée)."""
    season = _season_or_404(session)
    nation = NATIONS_BY_CODE.get(code.upper())
    if nation is None or competition not in WINDOWS_BY_CODE:
        raise HTTPException(status_code=404, detail="Sélection ou fenêtre introuvable")
    call = next(
        (
            row
            for row in internationals.call_up_rows(session, season)
            if row.competition == competition and row.nation == nation.code
        ),
        None,
    )
    day = game_date(session)
    names = internationals.club_names(session)
    players = []
    if call is not None:
        starts = season_starts(season, internationals.test_rows(session, season))
        rows = session.scalars(select(PlayerRow).where(PlayerRow.id.in_(call.player_ids)))
        players = [squad_player_out(row.to_domain(), day, names, starts) for row in rows]
    return NationSquadOut(
        nation=nation_out(nation),
        competition=WINDOWS_BY_CODE[competition].name,
        announced_on=call.announced_on if call is not None else None,
        players=players,
    )
