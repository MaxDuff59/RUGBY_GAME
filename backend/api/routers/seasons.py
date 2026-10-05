"""La saison en cours : calendrier, journée par journée, phases finales, saison suivante.

Le calendrier est tiré au début de la saison (matchs sans score). Chaque appel
à `play` joue la journée suivante : la semaine d'entraînement (qui peut blesser),
tous ses matchs (qui blessent aussi), puis les recettes et les salaires. Les
phases finales se créent au fil des résultats.
"""

import datetime
import itertools
import random

from fastapi import APIRouter, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from api.affairs import (
    affair_out,
    draw_affair,
    forced_starters,
    ignore_pending,
    settle_promises,
)
from api.deps import SessionDep, load_clubs
from api.free_agents import age_free_agents, release, renew_pool
from api.jokers import close_jokers, end_piges
from api.ledger import current_season, record
from api.live import load_live, run_training_week
from api.notes import History, ensure_preseason_ranks, season_leagues
from api.routers.contracts import contracts_overview, expire_contracts, rival_signings
from api.routers.leagues import league_out
from api.routers.medical import injury_case
from api.schemas import (
    ClubRef,
    DismissalOut,
    InjuryCase,
    LeagueOut,
    MatchdayOut,
    MatchSummary,
    ObjectiveOut,
    PlayOut,
    ScorerOut,
    SeasonOut,
    SeasonReviewOut,
    StandingOut,
)
from data.generator import FIRST_SEASON_YEAR
from data.leagues import DEFAULT_LEAGUE, PROMOTION, league_config, sort_codes
from engine.board import should_sack
from engine.calendar import season_dates
from engine.economy import (
    CHAMPION_PRIZE,
    PLAYOFF_PRIZES,
    SQUAD_MAX,
    SQUAD_MIN,
    TransactionCategory,
    attendance,
    attendance_bonus,
    hospitality_revenue,
    matchday_wages,
    sponsor_revenue,
    ticketing_revenue,
    wage_for,
)
from engine.match_engine import simulate_match
from engine.medical import new_injury
from engine.offseason import age_players, develop_players, retirees, youth_exits, youth_intake
from engine.season import generate_fixtures, playoff_round, record_result
from models import (
    ATTRIBUTE_NAMES,
    Club,
    EventType,
    Injury,
    InjurySource,
    Season,
    Squad,
    Stage,
    StandingRow,
)
from models.orm import (
    CareerRow,
    ClubRow,
    DismissalRow,
    InjuryRow,
    MatchRow,
    NegotiationRow,
    PlayerRow,
    SeasonRow,
    TransactionRow,
)

router = APIRouter(prefix="/seasons", tags=["saisons"])

__all__ = ["FIRST_SEASON_YEAR", "create_season", "focus_league", "router"]

STAGE_LABELS = {
    Stage.QUARTER: "quarts de finale",
    Stage.BARRAGE: "barrages",
    Stage.SEMI: "demi-finales",
    Stage.FINAL: "finale",
}


def _matchday_label(stage: Stage, matchday: int) -> str:
    return f"journée {matchday}" if stage == Stage.REGULAR else STAGE_LABELS[stage]


# --- Lecture de la saison ------------------------------------------------------------


def _club_rows(session: Session) -> list[ClubRow]:
    return list(session.scalars(select(ClubRow).order_by(ClubRow.id)))


def focus_league(session: Session) -> str:
    """Le championnat du club dirigé (le Top 14 sans carrière, ou le premier venu)."""
    career = session.scalars(select(CareerRow)).first()
    if career is not None:
        return session.get(ClubRow, career.club_id).league
    leagues = set(session.scalars(select(ClubRow.league)))
    return DEFAULT_LEAGUE if DEFAULT_LEAGUE in leagues or not leagues else min(leagues)


def _season_league_codes(season: SeasonRow) -> list[str]:
    """Championnats de la saison, dans l'ordre de data/leagues.py."""
    return sort_codes({m.league for m in season.matches})


def _league_matches(season: SeasonRow, league: str) -> list[MatchRow]:
    return [m for m in season.matches if m.league == league]


def _league_club_ids(season: SeasonRow, league: str) -> list[int]:
    return sorted(
        {c for m in _league_matches(season, league) for c in (m.home_club_id, m.away_club_id)}
    )


def _league_out(season: SeasonRow, league: str) -> LeagueOut:
    return league_out(league, len(_league_club_ids(season, league)))


def _regular_matchday_count(season: SeasonRow, league: str) -> int:
    return max(
        m.matchday for m in _league_matches(season, league) if m.stage == Stage.REGULAR.value
    )


def _table(season: SeasonRow, league: str) -> Season:
    """Classement vide des clubs d'un championnat."""
    table = Season(year=season.year, clubs=[])
    table.standings = {cid: StandingRow(club_id=cid) for cid in _league_club_ids(season, league)}
    return table


def _standings(season: SeasonRow, league: str) -> Season:
    """Classement de la saison régulière d'un championnat, recalculé à partir des matchs joués."""
    table = _table(season, league)
    for row in _league_matches(season, league):
        if row.stage == Stage.REGULAR.value and row.is_played:
            match = row.to_domain()
            table.matches.append(match)
            record_result(table, match)
    return table


def _seeding(season: SeasonRow, league: str) -> list[int]:
    """Identifiants des clubs du championnat, du 1er au dernier de la saison régulière."""
    return [row.club_id for row in _standings(season, league).table()]


def _phase(season: SeasonRow, league: str) -> str:
    matches = _league_matches(season, league)
    if any(m.stage == Stage.REGULAR.value and not m.is_played for m in matches):
        return "regular"
    finals = [m for m in matches if m.stage == Stage.FINAL.value]
    if finals and all(m.is_played for m in finals):
        return "finished"
    return "playoffs"


def _champion_id(season: SeasonRow, league: str) -> int | None:
    final = next((m for m in _league_matches(season, league) if m.stage == Stage.FINAL.value), None)
    if final is None or not final.is_played:
        return None
    return final.to_domain().winner_id(_seeding(season, league))


def _summary(row: MatchRow, names: dict[int, str]) -> MatchSummary:
    return MatchSummary.from_match(row.to_domain(), names)


def _matchday_out(rows: list[MatchRow], names: dict[int, str]) -> MatchdayOut:
    first = rows[0]
    return MatchdayOut(
        matchday=first.matchday,
        stage=Stage(first.stage),
        date=first.date,
        matches=[_summary(row, names) for row in rows],
    )


def _season_out(session: Session, season: SeasonRow, league: str | None = None) -> SeasonOut:
    league = league or focus_league(session)
    codes = _season_league_codes(season)
    if league not in codes:
        raise HTTPException(status_code=404, detail=f"Championnat « {league} » introuvable")
    names = {row.id: row.name for row in _club_rows(session)}

    standings = [
        StandingOut(
            rank=rank,
            club_id=row.club_id,
            club_name=names[row.club_id],
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
        for rank, row in enumerate(_standings(season, league).table(), start=1)
    ]

    matches = sorted(_league_matches(season, league), key=lambda m: (m.matchday, m.id))
    unplayed = [m for m in matches if not m.is_played]
    next_matchday = None
    if unplayed:
        first = unplayed[0].matchday
        next_matchday = _matchday_out([m for m in unplayed if m.matchday == first], names)

    champion_id = _champion_id(season, league)
    out = _league_out(season, league)
    return SeasonOut(
        year=season.year,
        league=out,
        leagues=[_league_out(season, code) for code in codes],
        phase=_phase(season, league),
        regular_matchdays=_regular_matchday_count(season, league),
        club_count=out.club_count,
        playoff_qualifiers=league_config(league).playoffs.qualifiers,
        next_matchday=next_matchday,
        standings=standings,
        matches=[_summary(m, names) for m in matches],
        champion=ClubRef(id=champion_id, name=names[champion_id]) if champion_id else None,
    )


# --- Création et avancement ----------------------------------------------------------


def create_season(session: Session, year: int) -> SeasonRow:
    """Tire le calendrier de la saison régulière de chaque championnat (matchs sans
    score) et l'enregistre."""
    by_league: dict[str, list[int]] = {}
    for row in _club_rows(session):
        by_league.setdefault(row.league, []).append(row.id)

    season = SeasonRow(year=year)
    pros, youths = [], []
    for league, club_ids in by_league.items():
        config = league_config(league)
        fixtures = generate_fixtures(club_ids)
        regular_dates, _ = season_dates(year, len(fixtures), config.start, config.breaks)
        # Les espoirs jouent les mêmes affiches, le même jour (saison régulière seulement).
        for squad, target in ((Squad.PRO, pros), (Squad.YOUTH, youths)):
            target.extend(
                MatchRow(
                    league=league,
                    matchday=number,
                    stage=Stage.REGULAR.value,
                    date=regular_dates[number - 1],
                    home_club_id=home,
                    away_club_id=away,
                    squad=squad.value,
                )
                for number, matchday in enumerate(fixtures, start=1)
                for home, away in matchday
            )
    season.matches, season.youth_matches = pros, youths
    session.add(season)
    session.commit()
    # Figé maintenant, avant que l'effectif ne bouge : l'objectif de la direction en dépend.
    ensure_preseason_ranks(session, season)
    return season


def _ensure_next_stage(session: Session, season: SeasonRow, league: str) -> None:
    """Crée les matchs du tour suivant d'un championnat quand tous ceux du tour en
    cours sont joués."""
    matches = _league_matches(season, league)
    if any(not m.is_played for m in matches):
        return

    config = league_config(league)
    seeding = _seeding(season, league)
    played = {
        stage: [m.to_domain() for m in matches if m.stage == stage.value]
        for stage in config.playoffs.stages
    }
    next_round = playoff_round(config.playoffs, seeding, played)
    if next_round is None:
        return  # finale jouée : la saison du championnat est terminée
    stage, pairings = next_round

    regular_count = _regular_matchday_count(season, league)
    stages = config.playoffs.stages
    _, playoff_dates = season_dates(
        season.year, regular_count, config.start, config.breaks, len(stages)
    )
    round_index = stages.index(stage)
    for home, away in pairings:
        season.matches.append(
            MatchRow(
                league=league,
                matchday=regular_count + round_index + 1,
                stage=stage.value,
                date=playoff_dates[round_index],
                home_club_id=home,
                away_club_id=away,
                neutral=stage == Stage.FINAL and config.neutral_final,
            )
        )
    session.commit()


def _prepare_day(session: Session, season: SeasonRow) -> datetime.date | None:
    """Ouvre les tours de phases finales prêts ; renvoie le prochain jour de match."""
    for league in _season_league_codes(season):
        _ensure_next_stage(session, season, league)
    return min((m.date for m in season.matches if not m.is_played), default=None)


def _play_day(
    session: Session, season: SeasonRow, day: datetime.date
) -> tuple[list[MatchRow], list[InjuryCase]]:
    """Joue tous les matchs du jour `day`, tous championnats confondus, et passe les
    écritures financières.

    Seuls les clubs qui jouent ce jour-là ont leur semaine d'entraînement. Si le
    match du club dirigé est en cours en direct (api/live.py), il est joué
    jusqu'au bout par le staff et compte tel quel ; la semaine d'entraînement a
    alors déjà eu lieu. Renvoie les matchs joués et les blessés du club dirigé
    (entraînement et matchs).
    """
    session.expire_all()  # blessures et effectifs des jours précédents
    todays = sorted(
        (m for m in season.matches if not m.is_played and m.date == day),
        key=lambda m: (m.league, m.id),
    )
    leagues = sorted({m.league for m in todays})
    career = session.scalars(select(CareerRow)).first()
    my_club_id = career.club_id if career is not None else None

    # Seuls les clubs des championnats du jour (et le club dirigé) sont chargés.
    club_rows = [row for row in _club_rows(session) if row.league in leagues]
    rows_by_id = {row.id: row for row in club_rows}
    wanted = set(rows_by_id) | ({my_club_id} if my_club_id is not None else set())
    clubs = load_clubs(session, wanted)
    playing = {club_id: clubs[club_id] for club_id in rows_by_id}
    players = {p.id: p for club in clubs.values() for p in club.players}
    if my_club_id is not None:
        # Titularisations promises au manager (api/affairs.py).
        clubs[my_club_id].forced_starters = forced_starters(session, my_club_id)

    # Match en direct du club dirigé : le staff finit ce qu'il reste à jouer.
    live = load_live(session, clubs)
    if live is not None and live.match_row not in todays:
        live = None

    # Classement avant la journée : il fixe l'affluence (et départage les phases finales).
    seeding = {league: _seeding(season, league) for league in leagues}
    rank_of = {
        club_id: rank for order in seeding.values() for rank, club_id in enumerate(order, start=1)
    }
    regular_count = {league: _regular_matchday_count(season, league) for league in leagues}
    rng = random.Random()

    # Forme du jour de chaque club (moral, cohésion, fraîcheur), avant toute écriture.
    history = History.load(session)
    forms = {club_id: history.form(club, day) for club_id, club in playing.items()}

    # Blessures de la journée : enregistrées en base, et renvoyées pour le club dirigé.
    my_injuries: list[tuple[InjuryRow, Injury]] = []

    def save_injury(injury: Injury, club: Club) -> None:
        injury_row = InjuryRow.from_domain(injury)
        session.add(injury_row)
        if club.id == my_club_id:
            my_injuries.append((injury_row, injury))

    # Semaine d'entraînement des clubs qui jouent (déjà faite si le match en direct
    # a commencé : ses blessés sont dans la sauvegarde).
    if live is None:
        my_injuries.extend(run_training_week(session, playing, forms, day, rng, my_club_id))
    else:
        for injury_row in session.scalars(
            select(InjuryRow).where(InjuryRow.id.in_(live.row.my_injuries))
        ):
            my_injuries.append((injury_row, injury_row.to_domain()))

    for row in todays:
        stage, matchday = Stage(row.stage), row.matchday
        label = _matchday_label(stage, matchday)
        config = league_config(row.league)
        home, away = clubs[row.home_club_id], clubs[row.away_club_id]
        if live is not None and row.id == live.match_row.id:
            live.match.auto = {home.id, away.id}
            result = live.match.play_to_end()
        else:
            result = simulate_match(
                home,
                away,
                rng=rng,
                matchday=matchday,
                neutral=row.neutral,
                day=day,
                home_form=forms[home.id],
                away_form=forms[away.id],
                knockout=stage.is_playoff,
            )
        row.home_score, row.away_score = result.home_score, result.away_score
        row.events = MatchRow.from_domain(result).events
        row.home_lineup, row.away_lineup = result.home_lineup, result.away_lineup
        for event in result.events:
            if event.type == EventType.INJURY:
                club = clubs[event.club_id]
                injury = new_injury(
                    players[event.player_id],
                    club,
                    InjurySource.MATCH,
                    day,
                    rng,
                    decided=club.id != my_club_id,
                )
                save_injury(injury, club)

        home_row, away_row = rows_by_id[home.id], rows_by_id[away.id]
        spectators = attendance(
            home_row.stadium_capacity,
            rank_of[home.id],
            len(seeding[row.league]),
            stage.is_playoff,
            rng,
            fervour=history.fervour(home.id).value,
            bonus=attendance_bonus(home.facilities),
        )
        record(
            session,
            home_row,
            TransactionCategory.TICKETING,
            f"Billetterie · {away.name} · {spectators:,} spectateurs".replace(",", " "),
            ticketing_revenue(spectators),
            day,
            matchday,
        )
        if hospitality := hospitality_revenue(home.facilities, spectators):
            record(
                session,
                home_row,
                TransactionCategory.HOSPITALITY,
                f"Buvettes, boutique et loges · {away.name}",
                hospitality,
                day,
                matchday,
            )
        for club_row, club in ((home_row, home), (away_row, away)):
            record(
                session,
                club_row,
                TransactionCategory.SPONSORS,
                f"Sponsors · {label}",
                sponsor_revenue(club.facilities),
                day,
                matchday,
            )
            if stage.is_playoff:
                record(
                    session,
                    club_row,
                    TransactionCategory.PRIZE,
                    f"Prime · {label}",
                    round(PLAYOFF_PRIZES[stage] * config.prize_factor),
                    day,
                    matchday,
                )
        if stage == Stage.FINAL:
            winner = rows_by_id[result.winner_id(seeding[row.league])]
            record(
                session,
                winner,
                TransactionCategory.PRIZE,
                "Prime · champion",
                round(CHAMPION_PRIZE * config.prize_factor),
                day,
                matchday,
            )

    # Les espoirs jouent leur journée en même temps que les pros (sans blessures).
    for row in season.youth_matches:
        if row.date == day and not row.is_played:
            result = simulate_match(
                clubs[row.home_club_id].youth_team(),
                clubs[row.away_club_id].youth_team(),
                rng=rng,
                matchday=row.matchday,
            )
            row.home_score, row.away_score = result.home_score, result.away_score
            row.events = MatchRow.from_domain(result).events
            row.home_lineup, row.away_lineup = result.home_lineup, result.away_lineup

    # Les salaires se versent à chaque journée de saison régulière du championnat,
    # à tous ses clubs.
    for league in leagues:
        regular = next(
            (m for m in todays if m.league == league and m.stage == Stage.REGULAR.value), None
        )
        if regular is None:
            continue
        label = _matchday_label(Stage.REGULAR, regular.matchday)
        for club_row in club_rows:
            if club_row.league == league:
                record(
                    session,
                    club_row,
                    TransactionCategory.WAGES,
                    f"Salaires · {label}",
                    -matchday_wages(clubs[club_row.id], regular_count[league]),
                    day,
                    regular.matchday,
                )

    if live is not None:
        session.delete(live.row)
    session.commit()

    cases = []
    if my_club_id is not None:
        my_club = clubs[my_club_id]
        for injury_row, injury in my_injuries:
            injury.id = injury_row.id  # attribué à l'enregistrement
            cases.append(injury_case(players[injury.player_id], injury, my_club, day))
    return todays, cases


def _play_matchday(session: Session, season: SeasonRow) -> tuple[MatchdayOut, list[InjuryCase]]:
    """Joue jusqu'à la prochaine journée du championnat du club dirigé.

    Les autres championnats ont leur propre calendrier : leurs matchs des jours
    d'avant (et du même jour) se jouent en chemin. Renvoie la journée jouée du
    championnat du club dirigé et ses blessés.
    """
    league = focus_league(session)
    if _phase(season, league) == "finished":
        raise HTTPException(status_code=400, detail="La saison est terminée")
    injuries: list[InjuryCase] = []
    while (day := _prepare_day(session, season)) is not None:
        todays, cases = _play_day(session, season, day)
        injuries += cases
        ours = [m for m in todays if m.league == league]
        if ours:
            break
    else:
        raise HTTPException(status_code=400, detail="La saison est terminée")
    _prepare_day(session, season)
    names = {row.id: row.name for row in _club_rows(session)}
    return _matchday_out(ours, names), injuries


def _finish_world(session: Session, season: SeasonRow) -> None:
    """Joue tout ce qui reste de la saison dans les autres championnats."""
    while (day := _prepare_day(session, season)) is not None:
        _play_day(session, season, day)


def _promotion(season: SeasonRow) -> tuple[int | None, int | None]:
    """(promu, relégué) : le champion de Pro D2 monte, le dernier du Top 14 descend."""
    lower, upper = PROMOTION
    codes = _season_league_codes(season)
    if lower not in codes or upper not in codes:
        return None, None
    if _phase(season, lower) != "finished" or _phase(season, upper) != "finished":
        return None, None
    return _champion_id(season, lower), _seeding(season, upper)[-1]


def _current_or_404(session: Session) -> SeasonRow:
    season = current_season(session)
    if season is None:
        raise HTTPException(status_code=404, detail="Aucune saison : commence une carrière")
    return season


# --- Routes --------------------------------------------------------------------------


@router.get("/current", response_model=SeasonOut)
def get_current_season(session: SessionDep, league: str | None = None) -> SeasonOut:
    """Calendrier complet, classement et prochaine journée de la saison en cours d'un
    championnat (par défaut celui du club dirigé)."""
    return _season_out(session, _current_or_404(session), league)


@router.get("/current/review", response_model=SeasonReviewOut)
def get_season_review(session: SessionDep) -> SeasonReviewOut:
    """Bilan sportif du club dirigé, une fois la finale jouée : classement, phases
    finales, objectif de la direction, espoirs, trésorerie, meilleurs marqueurs."""
    season = _current_or_404(session)
    career = session.scalars(select(CareerRow)).first()
    if career is None:
        raise HTTPException(status_code=404, detail="Aucune carrière en cours")
    club_id = career.club_id
    league = season_leagues(season)[club_id]
    if _phase(season, league) != "finished":
        raise HTTPException(status_code=400, detail="La saison n'est pas terminée")
    names = {row.id: row.name for row in _club_rows(session)}
    matches = _league_matches(season, league)

    table = _standings(season, league).table()
    seeding = [line.club_id for line in table]
    rank = seeding.index(club_id) + 1
    line = table[rank - 1]

    # Phases finales : le dernier tour joué, ou le titre.
    playoffs = "none"
    for row in sorted(matches, key=lambda m: m.matchday):
        if row.stage != Stage.REGULAR.value and club_id in (row.home_club_id, row.away_club_id):
            playoffs = row.stage
    champion_id = _champion_id(season, league)
    if champion_id == club_id:
        playoffs = "champion"
    promoted, relegated = _promotion(season)
    movement = "promoted" if promoted == club_id else "relegated" if relegated == club_id else None

    history = History.load(session)
    goal = history.objective(club_id)
    objective = ObjectiveOut(
        label=goal.label, target_rank=goal.target_rank, expected_rank=history.ranks[-1][club_id]
    )

    youth_table = _table(season, league)
    youth_rows = [m for m in season.youth_matches if m.league == league]
    for row in youth_rows:
        if row.is_played:
            record_result(youth_table, row.to_domain())
    youth_ids = [youth_line.club_id for youth_line in youth_table.table()]

    start = min(m.date for m in season.matches)
    season_total = session.scalar(
        select(func.coalesce(func.sum(TransactionRow.amount), 0)).where(
            TransactionRow.club_id == club_id, TransactionRow.date >= start
        )
    )
    balance = session.get(ClubRow, club_id).balance

    points: dict[int, int] = {}
    tries: dict[int, int] = {}
    for row in matches:
        if not row.is_played:
            continue
        for event in row.to_domain().events:
            if event.club_id == club_id and event.player_id is not None and event.points:
                points[event.player_id] = points.get(event.player_id, 0) + event.points
                if event.type == EventType.TRY:
                    tries[event.player_id] = tries.get(event.player_id, 0) + 1
    scorers = []
    for player_id in sorted(points, key=points.get, reverse=True)[:3]:
        player = session.get(PlayerRow, player_id)
        if player is not None:
            scorers.append(
                ScorerOut(
                    player_id=player_id,
                    name=f"{player.first_name} {player.last_name}",
                    points=points[player_id],
                    tries=tries.get(player_id, 0),
                )
            )

    return SeasonReviewOut(
        year=season.year,
        club=ClubRef(id=club_id, name=names[club_id]),
        champion=ClubRef(id=champion_id, name=names[champion_id]),
        league=_league_out(season, league),
        club_count=len(seeding),
        playoff_qualifiers=league_config(league).playoffs.qualifiers,
        rank=rank,
        played=line.played,
        won=line.won,
        drawn=line.drawn,
        lost=line.lost,
        points_for=line.points_for,
        points_against=line.points_against,
        tries_for=line.tries_for,
        league_points=line.league_points,
        playoffs=playoffs,
        movement=movement,
        objective=objective,
        objective_met=rank <= goal.target_rank,
        youth_rank=youth_ids.index(club_id) + 1 if youth_rows else None,
        balance_start=balance - season_total,
        balance_end=balance,
        scorers=scorers,
    )


@router.post("/current/play", response_model=PlayOut)
def play_next_matchday(session: SessionDep) -> PlayOut:
    """Joue la prochaine journée (tous ses matchs) et renvoie la saison mise à jour.

    Une affaire restée sans réponse est d'abord réglée d'office ; après la journée,
    les promesses sont tranchées et une nouvelle affaire peut tomber. Pendant la
    phase retour, des concurrents peuvent signer nos joueurs en fin de contrat.
    Les piges des jokers médicaux terminées donnent lieu à un avis.
    """
    season = _current_or_404(session)
    ignore_pending(session)
    played, injuries = _play_matchday(session, season)
    dismissal = _board_verdict(session, played)
    affairs, signings = [], []
    if dismissal is None:
        rng = random.Random()
        affairs = settle_promises(session, season, played.date)
        drawn = draw_affair(session, season, rng)
        affairs += [drawn] if drawn is not None else []
        league = focus_league(session)
        second_half = played.matchday > _regular_matchday_count(season, league) // 2
        if played.stage != Stage.REGULAR or second_half:
            signings = rival_signings(session, season, played.date, rng)
        affairs += end_piges(session, _phase(season, league) == "finished")
    return PlayOut(
        played=played,
        season=_season_out(session, season),
        injuries=injuries,
        dismissal=DismissalOut.model_validate(dismissal) if dismissal else None,
        affairs=[affair_out(row) for row in affairs],
        signings=signings,
    )


def _board_verdict(session: Session, played: MatchdayOut) -> DismissalRow | None:
    """Après une journée où le club dirigé a joué, la direction peut limoger le manager.

    La carrière est alors supprimée et les négociations en cours rompues ; le
    monde continue, et le manager peut reprendre un autre club.
    """
    career = session.scalars(select(CareerRow)).first()
    if career is None:
        return None
    club_id = career.club_id
    if not any(club_id in (m.home.id, m.away.id) for m in played.matches):
        return None

    history = History.load(session)
    confidence = history.board(club_id).value
    regular_played = sum(
        1
        for m in history.this_season
        if m.stage == Stage.REGULAR and club_id in (m.home_club_id, m.away_club_id)
    )
    if not should_sack(confidence, regular_played, 2 * (len(history.league_clubs(club_id)) - 1)):
        return None

    dismissal = DismissalRow(
        manager_name=career.manager_name,
        club_id=club_id,
        date=played.date,
        confidence=round(confidence, 1),
    )
    session.add(dismissal)
    for negotiation in session.scalars(
        select(NegotiationRow).where(
            NegotiationRow.club_id == club_id, NegotiationRow.stage.in_(("club", "player"))
        )
    ):
        negotiation.stage = "failed"
        negotiation.closed_by = "me"
        negotiation.message = "Négociation interrompue : le manager a été limogé."
    session.delete(career)
    session.commit()
    return dismissal


@router.post("/next", response_model=SeasonOut, status_code=201)
def start_next_season(session: SessionDep) -> SeasonOut:
    """Intersaison : fin des prêts, pré-contrats exécutés (les nôtres et ceux des
    concurrents), fins de contrat, puis les joueurs vieillissent, les plus âgés
    partent, les jeunes arrivent, les clubs IA complètent leur effectif parmi
    les agents libres, et un nouveau calendrier est tiré.

    Il suffit que le championnat du club dirigé soit terminé : les autres jouent
    d'abord ce qu'il leur reste. Puis le champion de Pro D2 monte en Top 14 et le
    dernier du Top 14 descend.

    Refusée si l'effectif pro du club dirigé passerait sous le minimum."""
    season = _current_or_404(session)
    if _phase(season, focus_league(session)) != "finished":
        raise HTTPException(status_code=400, detail="La saison n'est pas terminée")
    career = session.scalars(select(CareerRow)).first()
    my_club_id = career.club_id if career is not None else None
    if career is not None:
        contracts = contracts_overview(session, session.get(ClubRow, my_club_id))
        if contracts.squad_next < SQUAD_MIN:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Effectif pro insuffisant la saison prochaine : {contracts.squad_next} "
                    f"joueurs sous contrat (minimum {SQUAD_MIN}). Prolonge des joueurs, "
                    "fais passer des espoirs pros ou recrute."
                ),
            )

    _finish_world(session, season)
    session.expire_all()
    promoted, relegated = _promotion(season)
    if promoted is not None and relegated is not None:
        lower, upper = PROMOTION
        session.get(ClubRow, promoted).league = upper
        session.get(ClubRow, relegated).league = lower
        session.commit()

    rng = random.Random()
    year = season.year + 1
    close_jokers(session, year)
    _offseason_moves(session, year, rng, my_club_id)
    age_free_agents(session, year, rng)
    next_id = (session.scalar(select(func.max(PlayerRow.id))) or 0) + 1
    player_ids = itertools.count(next_id)

    for club_row in _club_rows(session):
        club = club_row.to_domain()
        rows = {row.id: row for row in [*club_row.players, *club_row.youths]}
        age_players(club)
        develop_players(club, rng)

        # Retraites, et espoirs trop âgés : les clubs IA promeuvent ceux qu'ils
        # peuvent garder, le manager a dû le faire lui-même avant l'intersaison ;
        # les autres quittent le centre et deviennent agents libres.
        retired = {player.id for player in retirees(club)}
        released = set()
        for youth in sorted(youth_exits(club), key=lambda p: p.overall, reverse=True):
            if club_row.id != my_club_id and len(club.players) - len(retired) < SQUAD_MAX:
                rows[youth.id].squad = Squad.PRO.value
                rows[youth.id].wage = wage_for(youth)
                club.players.append(youth)
            else:
                released.add(youth.id)
        for player in [*club.players, *club.youths]:
            if player.id in retired:
                session.delete(rows[player.id])
                continue
            row = rows[player.id]
            row.age = player.age
            for name in ATTRIBUTE_NAMES:
                setattr(row, name, getattr(player, name))
            if player.id in released:
                release(row, year)
        club.youths = [p for p in club.youths if p.id not in released]
        for youth in youth_intake(club, player_ids, rng, year):
            session.add(PlayerRow.from_domain(youth))
    renew_pool(session, year, rng, my_club_id, player_ids)
    session.commit()

    return _season_out(session, create_season(session, season.year + 1))


def _offseason_moves(
    session: Session, year: int, rng: random.Random, my_club_id: int | None
) -> None:
    """Mouvements de l'intersaison, avant le vieillissement : prêts, pré-contrats, contrats."""
    # Les prêtés rentrent chez leur club propriétaire.
    for row in session.scalars(select(PlayerRow).where(PlayerRow.loaned_from.is_not(None))):
        row.club_id, row.loaned_from = row.loaned_from, None

    # Les pré-contrats signés (par le manager ou par un concurrent) s'exécutent ;
    # les négociations inachevées tombent.
    for neg in session.scalars(select(NegotiationRow).where(NegotiationRow.stage != "done")):
        if neg.stage == "agreed":
            player = neg.player
            player.club_id = neg.club_id
            player.wage = neg.wage
            player.contract_until = year + neg.years - 1
            neg.stage = "done"
        elif neg.stage != "failed":
            neg.stage = "failed"
            neg.message = "La saison est terminée sans accord."

    session.flush()
    expire_contracts(session, year, my_club_id, rng)
    session.commit()
    session.expire_all()  # les effectifs ont changé : relationships à relire


@router.get("/{year}", response_model=SeasonOut)
def get_season(year: int, session: SessionDep, league: str | None = None) -> SeasonOut:
    """Une saison passée (ou en cours), par année et par championnat."""
    season = session.scalars(select(SeasonRow).where(SeasonRow.year == year)).first()
    if season is None:
        raise HTTPException(status_code=404, detail=f"Saison {year} introuvable")
    return _season_out(session, season, league)
