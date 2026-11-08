"""Palmarès : les champions de chaque championnat, l'histoire du club dirigé, les
trophées de chaque saison (engine/awards.py) et les records depuis la première saison.

Les champions, l'histoire et les records se relisent dans les matchs des saisons
passées, chargés une seule fois et sans les statistiques des joueurs (`_Matches`) ;
les trophées des saisons finies sont inscrits à l'intersaison (`AwardRow`), ceux de la
saison en cours se calculent dès que son championnat a joué sa finale.
"""

from collections import defaultdict

from fastapi import APIRouter, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from api import cup, internationals
from api import hero as heroes
from api.deps import SessionDep
from api.ledger import current_season
from api.notes import history_matches, light_match
from api.routers.seasons import _league_domain, _phase
from api.schemas import (
    AwardOut,
    ClubRef,
    ClubSeasonOut,
    HonoursOut,
    LeagueHonoursOut,
    MatchSummary,
    NationOut,
    RecordLineOut,
    RecordMatchOut,
    RecordsOut,
    SeasonHonoursOut,
    TitlesOut,
    WorldAwardOut,
    WorldAwardsOut,
    WorldNationAwardOut,
)
from data.leagues import league_config, sort_codes
from data.nations import NATIONS, NATIONS_BY_CODE
from engine import ranking
from engine.awards import AwardKind, season_awards
from engine.season import champion, league_table, phase
from engine.world_awards import world_awards
from models import EventType, Match, Player, Position, Stage
from models.orm import AwardRow, CareerRow, ClubRow, MoveRow, PlayerRow, SeasonRow

router = APIRouter(prefix="/honours", tags=["palmarès"])

RECORDS_SHOWN = 10
WINS_SHOWN = 5


class _Matches:
    """Les matchs pros de toutes les saisons, joués ou non, lus en une requête et sans
    les statistiques des joueurs, rangés par saison et par championnat."""

    def __init__(self, session: Session) -> None:
        self.by_league: dict[tuple[int, str], list[Match]] = defaultdict(list)
        for season_id, rows in history_matches(session).items():
            for row in rows:
                self.by_league[(season_id, row.league)].append(light_match(row))

    def leagues(self, season: SeasonRow) -> list[str]:
        """Les championnats de la saison, dans l'ordre de data/leagues.py."""
        return sort_codes(code for season_id, code in self.by_league if season_id == season.id)

    def of(self, season: SeasonRow, league: str) -> list[Match]:
        return self.by_league.get((season.id, league), [])

    def league_of(self, season: SeasonRow, club_id: int) -> str | None:
        """Le championnat que jouait le club cette saison-là (None s'il n'existait pas)."""
        for code in self.leagues(season):
            if any(club_id in (m.home_club_id, m.away_club_id) for m in self.of(season, code)):
                return code
        return None


class _Names:
    """Le nom de chaque joueur : sa fiche, ou à défaut son dernier mouvement (retraite)."""

    def __init__(self, session: Session) -> None:
        self.players = {
            pid: (f"{first} {last}", position)
            for pid, first, last, position in session.execute(
                select(PlayerRow.id, PlayerRow.first_name, PlayerRow.last_name, PlayerRow.position)
            )
        }
        self.moved = {
            pid: (name, position)
            for pid, name, position in session.execute(
                select(MoveRow.player_id, MoveRow.player_name, MoveRow.position).order_by(
                    MoveRow.id
                )
            )
        }

    def of(self, player_id: int) -> tuple[str, str] | None:
        return self.players.get(player_id) or self.moved.get(player_id)

    def active(self, player_id: int) -> bool:
        return player_id in self.players


def _award_out(row: AwardRow, clubs: dict[int, str], names: _Names) -> AwardOut:
    return AwardOut(
        kind=AwardKind(row.kind),
        slot=Position(row.slot) if row.slot else None,
        player_id=row.player_id,
        name=row.player_name,
        position=Position(row.position),
        club=ClubRef(id=row.club_id, name=clubs[row.club_id]),
        value=row.value,
        active=names.active(row.player_id),
    )


def _live_awards(
    season: SeasonRow, league: str, clubs: dict[int, str], players: dict[int, Player]
) -> list[AwardOut]:
    """Les trophées d'une saison finie mais pas encore close par l'intersaison."""
    return [
        AwardOut(
            kind=award.kind,
            slot=award.position,
            player_id=award.player_id,
            name=players[award.player_id].name,
            position=players[award.player_id].position,
            club=ClubRef(id=award.club_id, name=clubs[award.club_id]),
            value=award.value,
            active=True,
        )
        for award in season_awards(_league_domain(season, league, stats=True), players)
    ]


def _leagues(
    session: Session,
    seasons: list[SeasonRow],
    matches: _Matches,
    clubs: dict[int, str],
    names: _Names,
) -> list[LeagueHonoursOut]:
    stored = defaultdict(list)
    for row in session.scalars(select(AwardRow).order_by(AwardRow.id)):
        stored[(row.year, row.league)].append(_award_out(row, clubs, names))
    by_league: dict[str, list[SeasonHonoursOut]] = defaultdict(list)
    players: dict[int, Player] = {}  # chargés seulement s'il faut des trophées en direct
    for season in seasons:
        for league in matches.leagues(season):
            domain = matches.of(season, league)
            champion_id = champion(domain)
            final_match = next((m for m in domain if m.stage == Stage.FINAL), None)
            final = runner_up = None
            if final_match is not None and final_match.is_played:
                final = MatchSummary.from_match(final_match, clubs)
                loser = (
                    final_match.away_club_id
                    if champion_id == final_match.home_club_id
                    else final_match.home_club_id
                )
                runner_up = ClubRef(id=loser, name=clubs[loser])
            awards = stored.get((season.year, league))
            if awards is None:
                awards = []
                if phase(domain) == "finished":
                    if not players:
                        players.update(
                            (row.id, row.to_domain()) for row in session.scalars(select(PlayerRow))
                        )
                    awards = _live_awards(season, league, clubs, players)
            by_league[league].append(
                SeasonHonoursOut(
                    year=season.year,
                    champion=ClubRef(id=champion_id, name=clubs[champion_id])
                    if champion_id
                    else None,
                    runner_up=runner_up,
                    final=final,
                    awards=awards,
                )
            )
    # Les coupes d'Europe, à la suite des championnats (ni trophées individuels, ni poules).
    for season in seasons:
        for code in cup.codes(season):
            by_league[code].append(_cup_season(session, season, code, clubs))

    out = []
    championships = sort_codes(c for c in by_league if c not in cup.CUPS)
    for code in [*championships, *(c for c in cup.CUPS if c in by_league)]:
        history = sorted(by_league[code], key=lambda s: s.year, reverse=True)
        years: dict[int, list[int]] = defaultdict(list)
        for entry in history:
            if entry.champion is not None:
                years[entry.champion.id].append(entry.year)
        titles = [
            TitlesOut(club=ClubRef(id=cid, name=clubs[cid]), titles=len(ys), years=sorted(ys))
            for cid, ys in years.items()
        ]
        titles.sort(key=lambda t: (-t.titles, -max(t.years)))
        config = cup.CUPS[code] if code in cup.CUPS else league_config(code)
        out.append(
            LeagueHonoursOut(
                code=code,
                name=config.name,
                short_name=config.short_name,
                titles=titles,
                seasons=history,
            )
        )
    return out


def _cup_season(
    session: Session, season: SeasonRow, code: str, clubs: dict[int, str]
) -> SeasonHonoursOut:
    """Une saison d'une coupe d'Europe : son vainqueur et sa finale."""
    champion_id = cup.champion(session, season, code)
    final_row = next(
        (m for m in cup.rows(season, code) if m.stage == Stage.FINAL.value and m.is_played), None
    )
    final = runner_up = None
    if final_row is not None:
        final = MatchSummary.from_match(final_row.to_domain(stats=False), clubs)
        loser = (
            final_row.away_club_id
            if champion_id == final_row.home_club_id
            else final_row.home_club_id
        )
        runner_up = ClubRef(id=loser, name=clubs[loser])
    return SeasonHonoursOut(
        year=season.year,
        champion=ClubRef(id=champion_id, name=clubs[champion_id]) if champion_id else None,
        runner_up=runner_up,
        final=final,
        awards=[],
    )


def _club_history(seasons: list[SeasonRow], matches: _Matches, club_id: int) -> list[ClubSeasonOut]:
    history = []
    for season in seasons:
        league = matches.league_of(season, club_id)
        if league is None:
            continue
        domain = matches.of(season, league)
        table = league_table(domain).table()
        line = next(row for row in table if row.club_id == club_id)
        rank = [row.club_id for row in table].index(club_id) + 1 if line.played else None
        playoffs = "none"
        for match in sorted(domain, key=lambda m: m.matchday):
            if match.stage != Stage.REGULAR and club_id in (match.home_club_id, match.away_club_id):
                playoffs = match.stage.value
        if champion(domain) == club_id:
            playoffs = "champion"
        elif phase(domain) != "finished":
            playoffs = "running"
        history.append(
            ClubSeasonOut(
                year=season.year,
                league=league,
                league_name=league_config(league).short_name,
                rank=rank,
                club_count=len(table),
                playoffs=playoffs,
                played=line.played,
                won=line.won,
                points_for=line.points_for,
                points_against=line.points_against,
            )
        )
    return sorted(history, key=lambda s: s.year, reverse=True)


def _records(
    seasons: list[SeasonRow], matches: _Matches, clubs: dict[int, str], names: _Names
) -> RecordsOut:
    tries, points = defaultdict(int), defaultdict(int)
    season_tries, season_points = defaultdict(int), defaultdict(int)
    last_club: dict[int, int] = {}
    wins = []
    for season in seasons:
        played = [m for code in matches.leagues(season) for m in matches.of(season, code)]
        for match in sorted(played, key=lambda m: m.id):
            if not match.is_played:
                continue
            for event in match.events:
                if event.player_id is None or not event.points:
                    continue
                last_club[event.player_id] = event.club_id
                points[event.player_id] += event.points
                season_points[(event.player_id, season.year)] += event.points
                if event.type == EventType.TRY:
                    tries[event.player_id] += 1
                    season_tries[(event.player_id, season.year)] += 1
            wins.append(
                (abs(match.home_score - match.away_score), season.year, match.league, match)
            )

    def line(player_id: int, value: int, year: int | None = None) -> RecordLineOut | None:
        known = names.of(player_id)
        if known is None:
            return None
        club_id = last_club.get(player_id)
        return RecordLineOut(
            player_id=player_id,
            name=known[0],
            club=ClubRef(id=club_id, name=clubs[club_id]) if club_id in clubs else None,
            value=value,
            year=year,
            active=names.active(player_id),
        )

    def top(counts: dict, seasonal: bool = False) -> list[RecordLineOut]:
        best = sorted(counts.items(), key=lambda item: item[1], reverse=True)
        out = []
        for key, value in best:
            entry = line(key[0], value, key[1]) if seasonal else line(key, value)
            if entry is not None:
                out.append(entry)
            if len(out) == RECORDS_SHOWN:
                break
        return out

    wins.sort(key=lambda w: (w[0], w[3].home_score + w[3].away_score), reverse=True)
    return RecordsOut(
        tries=top(tries),
        points=top(points),
        season_tries=top(season_tries, seasonal=True),
        season_points=top(season_points, seasonal=True),
        biggest_wins=[
            RecordMatchOut(match=MatchSummary.from_match(match, clubs), year=year, league=league)
            for _, year, league, match in wins[:WINS_SHOWN]
        ],
        seasons=len(seasons),
    )


@router.get("", response_model=HonoursOut)
def get_honours(session: SessionDep) -> HonoursOut:
    """Le palmarès de tous les championnats, l'histoire du club dirigé, les records. En
    carrière de joueur, le championnat ouvert d'abord est celui de son club (son palmarès à
    lui se lit sur `GET /hero/career`)."""
    seasons = list(session.scalars(select(SeasonRow).order_by(SeasonRow.year)))
    clubs = {row.id: row.name for row in session.scalars(select(ClubRow))}
    names = _Names(session)
    matches = _Matches(session)
    career = session.scalars(select(CareerRow)).first()
    club = league = None
    history = []
    if career is not None:
        club = ClubRef(id=career.club_id, name=clubs[career.club_id])
        league = session.get(ClubRow, career.club_id).league
        history = _club_history(seasons, matches, career.club_id)
    elif (hero_club := heroes.hero_club_id(session)) is not None:
        club = ClubRef(id=hero_club, name=clubs[hero_club])
        league = session.get(ClubRow, hero_club).league
    return HonoursOut(
        club=club,
        league=league,
        leagues=_leagues(session, seasons, matches, clubs, names),
        club_history=history,
        records=_records(seasons, matches, clubs, names),
    )


# --- Les trophées mondiaux de la saison ------------------------------------------------------


@router.get("/world", response_model=WorldAwardsOut)
def get_world_awards(session: SessionDep) -> WorldAwardsOut:
    """Les trophées mondiaux de la saison en cours (engine/world_awards.py) : tous les
    championnats, les coupes d'Europe et les tests réunis ; puis la première sélection du
    classement mondial et celle qui y a gagné le plus de points. Ce que les bilans de fin
    de saison montrent, avant l'intersaison."""
    season = current_season(session)
    if season is None:
        raise HTTPException(status_code=404, detail="Aucune saison : commence une carrière")
    club_matches = [m.to_domain(True) for m in (*season.matches, *season.cup_matches)]
    tests = [row.to_domain() for row in internationals.test_rows(session, season)]
    rows = {row.id: row for row in session.scalars(select(PlayerRow))}
    players = {pid: row.to_domain() for pid, row in rows.items()}
    clubs = dict(session.execute(select(ClubRow.id, ClubRow.name)).all())
    with_nations = internationals.has_nations(session)

    def out(award) -> WorldAwardOut:
        player = players[award.player_id]
        nation = NATIONS_BY_CODE.get(player.nationality or "") if with_nations else None
        club = rows[award.player_id].club_id
        return WorldAwardOut(
            kind=award.kind,
            slot=award.position,
            player_id=player.id,
            name=player.name,
            position=player.position,
            age=player.age,
            photo=player.photo,
            club=ClubRef(id=club, name=clubs[club]) if club in clubs else None,
            nation=NationOut(id=nation.id, code=nation.code, name=nation.name) if nation else None,
            value=award.value,
            matches=award.matches,
            tests=award.tests,
        )

    best_nation = climber = None
    if with_nations:
        found = internationals.world_ranking(session)
        start = min((m.date for m in season.matches), default=None)
        before = [move.test for move in found.moves if start is None or move.test.date < start]
        initial = {n.code: n.points for n in NATIONS}
        points_before, _ = ranking.replay(initial, before)

        def nation_award(standing) -> WorldNationAwardOut:
            nation = NATIONS_BY_CODE[standing.code]
            return WorldNationAwardOut(
                nation=NationOut(id=nation.id, code=nation.code, name=nation.name),
                rank=standing.rank,
                points=standing.points,
                change=round(standing.points - points_before[standing.code], 2),
            )

        if found.standings:
            best_nation = nation_award(found.standings[0])
            if found.moves:
                climber = nation_award(
                    max(found.standings, key=lambda s: s.points - points_before[s.code])
                )
    leagues = {m.league for m in season.matches}
    return WorldAwardsOut(
        year=season.year,
        finished=all(_phase(season, league) == "finished" for league in leagues),
        awards=[out(award) for award in world_awards(club_matches, tests, players)],
        best_nation=best_nation,
        climber=climber,
    )
