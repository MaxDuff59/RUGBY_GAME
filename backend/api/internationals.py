"""Les sélections nationales côté base : calendrier, listes, doublons et matchs.

Règles : engine/internationals.py. Les matchs internationaux ont leur table
(`InternationalRow`), les listes aussi (`CallUpRow`). Un monde de clubs inventés
n'a pas de pays, donc pas de sélections : tout ce module ne fait alors rien.

La journée (api/routers/seasons.py) s'en sert à chaque date : les listes dues
sont annoncées, les internationaux du jour retirés à leur club, puis les matchs
internationaux joués. Le sélectionneur, quand c'est le joueur, annonce sa liste
et compose son XV par api/routers/selection.py.
"""

import datetime
import itertools
import random
from dataclasses import dataclass

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from api.deps import load_club
from api.ledger import current_season, game_date
from api.moves import delete_player
from data.nations import (
    NATIONS_BY_CODE,
    NATIONS_BY_ID,
    WINDOWS_BY_CODE,
    Nation,
    Window,
    home_nation,
)
from engine import internationals as rules
from engine.form import Form
from engine.internationals import SquadKey
from engine.match_engine import team_strength
from engine.offseason import RETIREMENT_AGE, develop_player
from engine.season import rng_for
from models import ATTRIBUTE_NAMES, Club, Injury, Match, Player, Squad, Stage
from models.orm import (
    CallUpRow,
    ClubRow,
    InjuryRow,
    InternationalRow,
    MatchRow,
    PlayerRow,
    SeasonRow,
    SelectorRow,
)

PRO, AWAY = Squad.PRO.value, Squad.AWAY.value


def has_nations(session: Session) -> bool:
    """Le monde a de vrais clubs, donc des pays et des sélections."""
    return any(home_nation(name) for name in session.scalars(select(ClubRow.name)))


def selector(session: Session) -> SelectorRow | None:
    """La carrière de sélectionneur en cours (None : carrière de club, ou aucune)."""
    return session.scalars(select(SelectorRow)).first()


def nation_levels(session: Session) -> dict[str, tuple[int, float]]:
    """Les sélections que l'on peut diriger : leur vivier (nombre de joueurs) et le
    niveau de leur XV (sur 20) aujourd'hui, par code."""
    if not has_nations(session):
        return {}
    day = game_date(session)
    pool = eligible_players(session)
    levels = {}
    for nation in rules.selectable():
        players = pool[nation.code]
        team = team_strength(rules.national_team(nation, rules.pick_squad(players, day)), day)
        levels[nation.code] = (
            len(players),
            (team.set_piece + team.pack + team.attack + team.defense) / 4,
        )
    return levels


def test_rows(session: Session, season: SeasonRow) -> list[InternationalRow]:
    """Les matchs internationaux de la saison, dans l'ordre du calendrier."""
    return list(
        session.scalars(
            select(InternationalRow)
            .where(InternationalRow.season_id == season.id)
            .order_by(InternationalRow.date, InternationalRow.id)
        )
    )


def call_up_rows(session: Session, season: SeasonRow) -> list[CallUpRow]:
    return list(
        session.scalars(
            select(CallUpRow).where(CallUpRow.season_id == season.id).order_by(CallUpRow.id)
        )
    )


def squads(session: Session, season: SeasonRow) -> dict[SquadKey, list[int]]:
    """Les listes annoncées de la saison : (fenêtre, sélection) -> joueurs."""
    return {
        (row.competition, NATIONS_BY_CODE[row.nation].id): list(row.player_ids)
        for row in call_up_rows(session, season)
    }


def fixture(row: InternationalRow) -> Match:
    """Le match sans ses événements : ce qu'il faut pour lire le calendrier."""
    return Match(
        id=row.id,
        home_club_id=row.home_id,
        away_club_id=row.away_id,
        matchday=row.matchday,
        home_score=row.home_score,
        away_score=row.away_score,
        stage=Stage(row.stage),
        date=row.date,
        neutral=row.neutral,
        league=row.competition,
    )


def next_test_date(session: Session, season: SeasonRow) -> datetime.date | None:
    return session.scalar(
        select(func.min(InternationalRow.date)).where(
            InternationalRow.season_id == season.id, InternationalRow.home_score.is_(None)
        )
    )


# --- Les joueurs sélectionnables ------------------------------------------------------------


def club_names(session: Session) -> dict[int, str]:
    return dict(session.execute(select(ClubRow.id, ClubRow.name)).all())


def eligible_players(
    session: Session, codes: set[str] | None = None, names: dict[int, str] | None = None
) -> dict[str, list[Player]]:
    """Les joueurs sélectionnables de chaque nation (`codes`, toutes par défaut)."""
    codes = set(NATIONS_BY_CODE) if codes is None else codes
    names = club_names(session) if names is None else names
    rows = session.scalars(
        select(PlayerRow)
        .where(PlayerRow.nationality.in_(codes), PlayerRow.squad.in_((PRO, AWAY)))
        .order_by(PlayerRow.id)
    )
    pool: dict[str, list[Player]] = {code: [] for code in codes}
    for row in rows:
        player = row.to_domain()
        nation = NATIONS_BY_CODE[player.nationality]
        if rules.is_eligible(player, nation, names.get(player.club_id)):
            pool[nation.code].append(player)
    return pool


# --- Calendrier et listes -------------------------------------------------------------------


def ensure_calendar(session: Session, season: SeasonRow) -> None:
    """Tire le calendrier international de la saison au premier besoin, et complète
    les sélections à court de joueurs à un poste (`reinforcements`).

    Une saison déjà entamée (partie commencée avant les sélections) ne reçoit que
    les fenêtres pas encore commencées.
    """
    exists = session.scalar(
        select(func.count())
        .select_from(InternationalRow)
        .where(InternationalRow.season_id == season.id)
    )
    if exists or not has_nations(session):
        return
    matches = rules.schedule(season.year)
    played = [m.date for m in season.matches if m.is_played]
    if played:
        started = {m.league for m in matches if m.date <= max(played)}
        matches = [m for m in matches if m.league not in started]
    if not matches:
        return
    session.add_all(InternationalRow.from_domain(match, season.id) for match in matches)

    rng = rng_for(season.seed, "internationals")
    player_ids = itertools.count((session.scalar(select(func.max(PlayerRow.id))) or 0) + 1)
    pool = eligible_players(session)
    for nation in rules.participants():
        for player in rules.reinforcements(nation, pool[nation.code], player_ids, rng, season.year):
            session.add(PlayerRow.from_domain(player))
    session.commit()


def ensure_next_round(session: Session, season: SeasonRow) -> None:
    """Coupe du monde : crée les matchs du tour suivant quand tous ceux du tour en
    cours sont joués (quarts après les poules, puis demies, puis finale)."""
    rows = [row for row in test_rows(session, season) if row.competition == rules.WORLD_CUP.code]
    if not rows or any(not row.is_played for row in rows):
        return
    upcoming = rules.next_round([row.to_domain() for row in rows], season.year)
    if not upcoming:
        return
    session.add_all(InternationalRow.from_domain(match, season.id) for match in upcoming)
    session.commit()


def announce_due(
    session: Session, season: SeasonRow, day: datetime.date, everyone: bool = False
) -> list[CallUpRow]:
    """Annonce les listes dont la date limite est atteinte au jour `day`, composées
    par le staff de chaque sélection. Celle du sélectionneur est laissée au joueur,
    sauf avec `everyone` (le match arrive : le staff tranche à sa place)."""
    rows = test_rows(session, season)
    if not rows:
        return []
    matches = [fixture(row) for row in rows]
    due = rules.due_lists(matches, squads(session, season), day)
    human = selector(session)
    if human is not None and not everyone:
        due = [(code, team) for code, team in due if NATIONS_BY_ID[team].code != human.nation]
    if not due:
        return []
    pool = eligible_players(session, {NATIONS_BY_ID[team].code for _, team in due})
    new = []
    for code, team in due:
        nation = NATIONS_BY_ID[team]
        first = min(m.date for m in matches if m.league == code)
        squad = rules.pick_squad(pool[nation.code], first)
        new.append(
            CallUpRow(
                season_id=season.id,
                competition=code,
                nation=nation.code,
                player_ids=[p.id for p in squad],
                announced_on=day,
            )
        )
    session.add_all(new)
    session.commit()
    return new


def absentees_on(session: Session, season: SeasonRow, day: datetime.date) -> dict[int, int]:
    """Joueurs retenus par une sélection qui joue le jour `day` : joueur -> sélection."""
    rows = [row for row in test_rows(session, season) if row.date == day]
    if not rows:
        return {}
    return rules.absentees([fixture(row) for row in rows], squads(session, season), day)


@dataclass(frozen=True)
class Duty:
    """Un joueur d'un club retenu en sélection pour une fenêtre en cours."""

    nation: Nation
    window: Window
    # Doublons à venir : sa sélection joue le même jour que son club.
    dates: list[datetime.date]
    away: bool  # dont le prochain match du club


def club_duties(session: Session, club_id: int) -> dict[int, Duty]:
    """Les joueurs du club retenus en sélection, tant que leur fenêtre n'est pas finie."""
    season = current_season(session)
    if season is None:
        return {}
    upcoming = [row for row in test_rows(session, season) if not row.is_played]
    if not upcoming:
        return {}
    club_dates = sorted(
        session.scalars(
            select(MatchRow.date).where(
                MatchRow.season_id == season.id,
                MatchRow.squad == PRO,
                MatchRow.home_score.is_(None),
                or_(MatchRow.home_club_id == club_id, MatchRow.away_club_id == club_id),
            )
        )
    )
    mine = set(session.scalars(select(PlayerRow.id).where(PlayerRow.club_id == club_id)))
    duties: dict[int, Duty] = {}
    for call in call_up_rows(session, season):
        nation = NATIONS_BY_CODE[call.nation]
        playing = {
            row.date
            for row in upcoming
            if row.competition == call.competition and nation.id in (row.home_id, row.away_id)
        }
        if not playing:
            continue
        duty = Duty(
            nation=nation,
            window=WINDOWS_BY_CODE[call.competition],
            dates=[day for day in club_dates if day in playing],
            away=bool(club_dates) and club_dates[0] in playing,
        )
        for player_id in call.player_ids:
            if player_id in mine:
                duties[player_id] = duty
    return duties


def release_for_next_match(session: Session, club: Club) -> dict[int, Duty]:
    """Met le club dans l'état de son prochain match : sans ses joueurs retenus par une
    sélection qui joue ce jour-là, avec les espoirs qui les suppléent (`Club.cover`).
    Renvoie les joueurs du club retenus en sélection."""
    duties = club_duties(session, club.id)
    away = {player_id for player_id, duty in duties.items() if duty.away}
    rules.release(club, away, game_date(session))
    return duties


# --- Les matchs -----------------------------------------------------------------------------


def national_teams(
    session: Session,
    season: SeasonRow,
    rows: list[InternationalRow],
    appearances: dict[int, list[datetime.date]],
) -> tuple[dict[int, Club], dict[int, Form]]:
    """Les sélections des matchs `rows`, chacune avec sa liste pour effectif, et leur
    forme. Le XV du sélectionneur, s'il en a choisi un, est posé sur la sienne."""
    lists = squads(session, season)
    wanted = {
        player_id
        for row in rows
        for team in (row.home_id, row.away_id)
        for player_id in lists.get((row.competition, team), [])
    }
    players = {
        row.id: row.to_domain()
        for row in session.scalars(select(PlayerRow).where(PlayerRow.id.in_(wanted)))
    }
    human = selector(session)
    teams: dict[int, Club] = {}
    forms: dict[int, Form] = {}
    for row in rows:
        for team in (row.home_id, row.away_id):
            nation = NATIONS_BY_ID[team]
            squad = [players[i] for i in lists.get((row.competition, team), []) if i in players]
            choice = human.lineup_choice if human and human.nation == nation.code else []
            teams[team] = rules.national_team(nation, squad, choice or [])
            forms[team] = rules.national_form(teams[team], appearances, row.date)
    return teams, forms


@dataclass
class TestDay:
    """Les matchs internationaux joués un jour donné, et leurs blessés."""

    rows: list[InternationalRow]
    injuries: list[tuple[InjuryRow, Injury]]


def play_tests(
    session: Session,
    season: SeasonRow,
    day: datetime.date,
    rng: random.Random,
    appearances: dict[int, list[datetime.date]],
    clubs: dict[int, Club],
    my_club_id: int | None = None,
    live=None,
) -> TestDay:
    """Joue les matchs internationaux du jour `day` et enregistre résultats et blessures
    (à l'appelant de valider). `clubs` : ceux déjà chargés, pour leur staff médical.
    `live` : le match en direct du sélectionneur (api/live.py), compté tel quel."""
    rows = [row for row in test_rows(session, season) if row.date == day and not row.is_played]
    if not rows:
        return TestDay([], [])
    # Une liste manque encore (celle du sélectionneur) : son staff la compose.
    announce_due(session, season, day, everyone=True)
    teams, forms = national_teams(session, season, rows, appearances)
    if live is not None:
        # Le match en direct garde ses propres équipes, là où il en est.
        for side in live.match.sides:
            teams[side.club.id] = side.club

    def staff_of(player: Player) -> Club:
        if player.club_id is None:
            return rules.NO_CLUB
        if player.club_id not in clubs:
            clubs[player.club_id] = load_club(session, player.club_id)
        return clubs[player.club_id]

    def finish_live(match: Match) -> Match | None:
        if live is None or match.id != live.match_row.id:
            return None
        live.match.auto = {match.home_club_id, match.away_club_id}
        return live.match.play_to_end()

    matches = [row.to_domain() for row in rows]
    injuries = rules.play_tests(
        day, matches, teams, rng, forms, staff_of, my_club_id, finished=finish_live
    )
    for row, match in zip(rows, matches, strict=True):
        row.write_result(match)
    if live is not None:
        session.delete(live.row)
    recorded = []
    for injury in injuries:
        injury_row = InjuryRow.from_domain(injury)
        session.add(injury_row)
        recorded.append((injury_row, injury))
    return TestDay(rows, recorded)


def played_tests(session: Session) -> list[Match]:
    """Tous les matchs internationaux joués, toutes saisons confondues : ils comptent
    dans la fatigue des joueurs (engine/history.py)."""
    rows = session.scalars(
        select(InternationalRow)
        .where(InternationalRow.home_score.is_not(None))
        .order_by(InternationalRow.date, InternationalRow.id)
    )
    return [
        Match(
            id=row.id,
            home_club_id=row.home_id,
            away_club_id=row.away_id,
            home_score=row.home_score,
            away_score=row.away_score,
            date=row.date,
            home_lineup=list(row.home_lineup or []),
            away_lineup=list(row.away_lineup or []),
            league=row.competition,
        )
        for row in rows
    ]


# --- Intersaison ----------------------------------------------------------------------------


def offseason(session: Session, rng: random.Random) -> None:
    """Les joueurs hors des championnats du jeu vieillissent, progressent ou déclinent,
    et raccrochent à l'âge de la retraite. Les listes de la saison suivante en
    rappelleront d'autres au besoin (`ensure_calendar`)."""
    for row in session.scalars(select(PlayerRow).where(PlayerRow.squad == AWAY)):
        player = row.to_domain()
        player.age += 1
        if player.age >= RETIREMENT_AGE:
            delete_player(session, row)
            continue
        develop_player(player, rules.AWAY_TRAINING_LEVEL, rng)
        row.age = player.age
        for name in ATTRIBUTE_NAMES:
            setattr(row, name, getattr(player, name))
