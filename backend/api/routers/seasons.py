"""La saison en cours : calendrier, journée par journée, phases finales, saison suivante.

Le calendrier est tiré au début de la saison (matchs sans score). Chaque appel
à `play` joue la journée suivante : la semaine d'entraînement (qui peut blesser),
tous ses matchs (qui blessent aussi), puis les recettes et les salaires. Les
phases finales se créent au fil des résultats.
"""

import itertools
import random

from fastapi import APIRouter, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from api.deps import SessionDep
from api.ledger import current_season, record
from api.routers.medical import injury_case
from api.schemas import (
    ClubRef,
    InjuryCase,
    MatchdayOut,
    MatchSummary,
    PlayOut,
    SeasonOut,
    StandingOut,
)
from data.generator import FIRST_SEASON_YEAR
from engine.calendar import season_dates
from engine.economy import (
    CHAMPION_PRIZE,
    PLAYOFF_PRIZES,
    SQUAD_MAX,
    TransactionCategory,
    attendance,
    matchday_wages,
    sponsor_revenue,
    ticketing_revenue,
    wage_for,
)
from engine.match_engine import simulate_match
from engine.medical import new_injury, training_injuries
from engine.offseason import age_players, develop_players, retirees, youth_exits, youth_intake
from engine.season import (
    PLAYOFF_QUALIFIERS,
    barrage_pairings,
    final_pairing,
    generate_fixtures,
    record_result,
    semi_pairings,
)
from models import ATTRIBUTE_NAMES, Club, EventType, Injury, InjurySource, Season, Squad, Stage
from models.orm import (
    CareerRow,
    ClubRow,
    InjuryRow,
    MatchRow,
    NegotiationRow,
    PlayerRow,
    SeasonRow,
)

router = APIRouter(prefix="/seasons", tags=["saisons"])

__all__ = ["FIRST_SEASON_YEAR", "create_season", "router"]

STAGE_LABELS = {
    Stage.BARRAGE: "barrages",
    Stage.SEMI: "demi-finales",
    Stage.FINAL: "finale",
}


def _matchday_label(stage: Stage, matchday: int) -> str:
    return f"journée {matchday}" if stage == Stage.REGULAR else STAGE_LABELS[stage]


# --- Lecture de la saison ------------------------------------------------------------


def _club_rows(session: Session) -> list[ClubRow]:
    return list(session.scalars(select(ClubRow).order_by(ClubRow.id)))


def _regular_matchday_count(season: SeasonRow) -> int:
    return max(m.matchday for m in season.matches if m.stage == Stage.REGULAR.value)


def _standings(season: SeasonRow, clubs: dict[int, Club]) -> Season:
    """Classement de la saison régulière, recalculé à partir des matchs joués."""
    table = Season(year=season.year, clubs=list(clubs.values()))
    for row in season.matches:
        if row.stage == Stage.REGULAR.value and row.is_played:
            match = row.to_domain()
            table.matches.append(match)
            record_result(table, match)
    return table


def _seeding(season: SeasonRow, clubs: dict[int, Club]) -> list[int]:
    """Identifiants des clubs du 1er au dernier de la saison régulière."""
    return [row.club_id for row in _standings(season, clubs).table()]


def _phase(season: SeasonRow) -> str:
    matches = season.matches
    if any(m.stage == Stage.REGULAR.value and not m.is_played for m in matches):
        return "regular"
    finals = [m for m in matches if m.stage == Stage.FINAL.value]
    if finals and all(m.is_played for m in finals):
        return "finished"
    return "playoffs"


def _summary(row: MatchRow, names: dict[int, str]) -> MatchSummary:
    return MatchSummary(
        id=row.id,
        matchday=row.matchday,
        stage=Stage(row.stage),
        date=row.date,
        neutral=row.neutral,
        home=ClubRef(id=row.home_club_id, name=names[row.home_club_id]),
        away=ClubRef(id=row.away_club_id, name=names[row.away_club_id]),
        home_score=row.home_score,
        away_score=row.away_score,
    )


def _matchday_out(rows: list[MatchRow], names: dict[int, str]) -> MatchdayOut:
    first = rows[0]
    return MatchdayOut(
        matchday=first.matchday,
        stage=Stage(first.stage),
        date=first.date,
        matches=[_summary(row, names) for row in rows],
    )


def _season_out(session: Session, season: SeasonRow) -> SeasonOut:
    club_rows = _club_rows(session)
    clubs = {row.id: row.to_domain() for row in club_rows}
    names = {row.id: row.name for row in club_rows}

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
        for rank, row in enumerate(_standings(season, clubs).table(), start=1)
    ]

    matches = sorted(season.matches, key=lambda m: (m.matchday, m.id))
    unplayed = [m for m in matches if not m.is_played]
    next_matchday = None
    if unplayed:
        first = unplayed[0].matchday
        next_matchday = _matchday_out([m for m in unplayed if m.matchday == first], names)

    phase = _phase(season)
    champion = None
    if phase == "finished":
        final = next(m for m in matches if m.stage == Stage.FINAL.value)
        winner_id = final.to_domain().winner_id(_seeding(season, clubs))
        champion = ClubRef(id=winner_id, name=names[winner_id])

    return SeasonOut(
        year=season.year,
        phase=phase,
        regular_matchdays=_regular_matchday_count(season),
        club_count=len(club_rows),
        playoff_qualifiers=PLAYOFF_QUALIFIERS,
        next_matchday=next_matchday,
        standings=standings,
        matches=[_summary(m, names) for m in matches],
        champion=champion,
    )


# --- Création et avancement ----------------------------------------------------------


def create_season(session: Session, year: int) -> SeasonRow:
    """Tire le calendrier de la saison régulière (matchs sans score) et l'enregistre."""
    club_ids = [row.id for row in _club_rows(session)]
    fixtures = generate_fixtures(club_ids)
    regular_dates, _ = season_dates(year, len(fixtures))

    season = SeasonRow(year=year)
    # Les espoirs jouent les mêmes affiches, le même jour (saison régulière seulement).
    for squad, target in ((Squad.PRO, "matches"), (Squad.YOUTH, "youth_matches")):
        setattr(
            season,
            target,
            [
                MatchRow(
                    matchday=number,
                    stage=Stage.REGULAR.value,
                    date=regular_dates[number - 1],
                    home_club_id=home,
                    away_club_id=away,
                    squad=squad.value,
                )
                for number, matchday in enumerate(fixtures, start=1)
                for home, away in matchday
            ],
        )
    session.add(season)
    session.commit()
    return season


def _ensure_next_stage(session: Session, season: SeasonRow, clubs: dict[int, Club]) -> None:
    """Crée les matchs de l'étape suivante quand tous ceux de l'étape en cours sont joués."""
    matches = season.matches
    if any(not m.is_played for m in matches):
        return

    def played_at(stage: Stage) -> list[MatchRow]:
        return [m for m in matches if m.stage == stage.value]

    seeding = _seeding(season, clubs)
    regular_count = _regular_matchday_count(season)
    _, playoff_dates = season_dates(season.year, regular_count)
    neutral = False

    if not played_at(Stage.BARRAGE):
        stage, pairings = Stage.BARRAGE, barrage_pairings(seeding)
    elif not played_at(Stage.SEMI):
        barrages = [m.to_domain() for m in played_at(Stage.BARRAGE)]
        stage, pairings = Stage.SEMI, semi_pairings(seeding, barrages)
    elif not played_at(Stage.FINAL):
        semis = [m.to_domain() for m in played_at(Stage.SEMI)]
        stage, pairings, neutral = Stage.FINAL, [final_pairing(seeding, semis)], True
    else:
        return  # finale jouée : la saison est terminée

    round_index = [Stage.BARRAGE, Stage.SEMI, Stage.FINAL].index(stage)
    for home, away in pairings:
        season.matches.append(
            MatchRow(
                matchday=regular_count + round_index + 1,
                stage=stage.value,
                date=playoff_dates[round_index],
                home_club_id=home,
                away_club_id=away,
                neutral=neutral,
            )
        )
    session.commit()


def _play_matchday(session: Session, season: SeasonRow) -> tuple[MatchdayOut, list[InjuryCase]]:
    """Joue la prochaine journée et passe les écritures financières.

    Renvoie la journée jouée et les blessés du club dirigé (entraînement et matchs).
    """
    club_rows = _club_rows(session)
    rows_by_id = {row.id: row for row in club_rows}
    clubs = {row.id: row.to_domain() for row in club_rows}
    names = {row.id: row.name for row in club_rows}
    players = {p.id: p for club in clubs.values() for p in club.players}
    career = session.scalars(select(CareerRow)).first()
    my_club_id = career.club_id if career is not None else None

    _ensure_next_stage(session, season, clubs)
    unplayed = [m for m in season.matches if not m.is_played]
    if not unplayed:
        raise HTTPException(status_code=400, detail="La saison est terminée")

    matchday = min(m.matchday for m in unplayed)
    todays = sorted((m for m in unplayed if m.matchday == matchday), key=lambda m: m.id)
    stage, day = Stage(todays[0].stage), todays[0].date
    label = _matchday_label(stage, matchday)

    # Classement avant la journée : il fixe l'affluence (et départage les phases finales).
    seeding = _seeding(season, clubs)
    rank_of = {club_id: rank for rank, club_id in enumerate(seeding, start=1)}
    regular_count = _regular_matchday_count(season)
    rng = random.Random()

    # Blessures de la journée : enregistrées en base, et renvoyées pour le club dirigé.
    my_injuries: list[tuple[InjuryRow, Injury]] = []

    def save_injury(injury: Injury, club: Club) -> None:
        injury_row = InjuryRow.from_domain(injury)
        session.add(injury_row)
        if club.id == my_club_id:
            my_injuries.append((injury_row, injury))

    # Semaine d'entraînement : tous les clubs, avant les matchs. Un blessé à
    # l'entraînement manque le match du jour.
    for club in clubs.values():
        for injury in training_injuries(club, day, rng, decided=club.id != my_club_id):
            save_injury(injury, club)

    for row in todays:
        home, away = clubs[row.home_club_id], clubs[row.away_club_id]
        result = simulate_match(
            home, away, rng=rng, matchday=matchday, neutral=row.neutral, day=day
        )
        row.home_score, row.away_score = result.home_score, result.away_score
        row.events = MatchRow.from_domain(result).events
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
            home_row.stadium_capacity, rank_of[home.id], len(clubs), stage.is_playoff, rng
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
                    PLAYOFF_PRIZES[stage],
                    day,
                    matchday,
                )
        if stage == Stage.FINAL:
            winner = rows_by_id[result.winner_id(seeding)]
            record(
                session,
                winner,
                TransactionCategory.PRIZE,
                "Prime · champion",
                CHAMPION_PRIZE,
                day,
                matchday,
            )

    # Les espoirs jouent leur journée en même temps que les pros (sans blessures).
    if stage == Stage.REGULAR:
        for row in season.youth_matches:
            if row.matchday == matchday and not row.is_played:
                result = simulate_match(
                    clubs[row.home_club_id].youth_team(),
                    clubs[row.away_club_id].youth_team(),
                    rng=rng,
                    matchday=matchday,
                )
                row.home_score, row.away_score = result.home_score, result.away_score
                row.events = MatchRow.from_domain(result).events

    # Les salaires se versent à chaque journée de saison régulière, pour tous les clubs.
    if stage == Stage.REGULAR:
        for club_row in club_rows:
            record(
                session,
                club_row,
                TransactionCategory.WAGES,
                f"Salaires · {label}",
                -matchday_wages(clubs[club_row.id], regular_count),
                day,
                matchday,
            )

    session.commit()
    _ensure_next_stage(session, season, clubs)

    cases = []
    if my_club_id is not None:
        my_club = clubs[my_club_id]
        for injury_row, injury in my_injuries:
            injury.id = injury_row.id  # attribué à l'enregistrement
            cases.append(injury_case(players[injury.player_id], injury, my_club, day))
    return _matchday_out(todays, names), cases


def _current_or_404(session: Session) -> SeasonRow:
    season = current_season(session)
    if season is None:
        raise HTTPException(status_code=404, detail="Aucune saison : commence une carrière")
    return season


# --- Routes --------------------------------------------------------------------------


@router.get("/current", response_model=SeasonOut)
def get_current_season(session: SessionDep) -> SeasonOut:
    """Calendrier complet, classement et prochaine journée de la saison en cours."""
    return _season_out(session, _current_or_404(session))


@router.post("/current/play", response_model=PlayOut)
def play_next_matchday(session: SessionDep) -> PlayOut:
    """Joue la prochaine journée (tous ses matchs) et renvoie la saison mise à jour."""
    season = _current_or_404(session)
    played, injuries = _play_matchday(session, season)
    return PlayOut(played=played, season=_season_out(session, season), injuries=injuries)


@router.post("/next", response_model=SeasonOut, status_code=201)
def start_next_season(session: SessionDep) -> SeasonOut:
    """Intersaison : fin des prêts, arrivée des joueurs sous pré-contrat, contrats
    renouvelés, puis les joueurs vieillissent, les plus âgés partent, les jeunes
    arrivent, et un nouveau calendrier est tiré."""
    season = _current_or_404(session)
    if _phase(season) != "finished":
        raise HTTPException(status_code=400, detail="La saison n'est pas terminée")

    rng = random.Random()
    year = season.year + 1
    _offseason_moves(session, year, rng)
    next_id = (session.scalar(select(func.max(PlayerRow.id))) or 0) + 1
    player_ids = itertools.count(next_id)
    career = session.scalars(select(CareerRow)).first()
    my_club_id = career.club_id if career is not None else None

    for club_row in _club_rows(session):
        club = club_row.to_domain()
        rows = {row.id: row for row in [*club_row.players, *club_row.youths]}
        age_players(club)
        develop_players(club, rng)

        # Retraites, et espoirs trop âgés : les clubs IA promeuvent ceux qu'ils
        # peuvent garder, le manager a dû le faire lui-même avant l'intersaison.
        gone = {player.id for player in retirees(club)}
        for youth in sorted(youth_exits(club), key=lambda p: p.overall, reverse=True):
            if club_row.id != my_club_id and len(club.players) - len(gone) < SQUAD_MAX:
                rows[youth.id].squad = Squad.PRO.value
                rows[youth.id].wage = wage_for(youth)
                club.players.append(youth)
            else:
                gone.add(youth.id)
        for player in [*club.players, *club.youths]:
            if player.id in gone:
                session.delete(rows[player.id])
            else:
                row = rows[player.id]
                row.age = player.age
                for name in ATTRIBUTE_NAMES:
                    setattr(row, name, getattr(player, name))
        club.youths = [p for p in club.youths if p.id not in gone]
        for youth in youth_intake(club, player_ids, rng, year):
            session.add(PlayerRow.from_domain(youth))
    session.commit()

    return _season_out(session, create_season(session, season.year + 1))


# Un contrat arrivé à terme est renouvelé d'une à trois saisons (pas encore de
# vraie gestion des contrats : les joueurs ne partent pas libres).
RENEWAL_YEARS = (1, 3)


def _offseason_moves(session: Session, year: int, rng: random.Random) -> None:
    """Mouvements de l'intersaison, avant le vieillissement : prêts, pré-contrats, contrats."""
    # Les prêtés rentrent chez leur club propriétaire.
    for row in session.scalars(select(PlayerRow).where(PlayerRow.loaned_from.is_not(None))):
        row.club_id, row.loaned_from = row.loaned_from, None

    # Les pré-contrats signés s'exécutent ; les négociations inachevées tombent.
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

    for row in session.scalars(select(PlayerRow).where(PlayerRow.contract_until < year)):
        row.contract_until = year + rng.randint(*RENEWAL_YEARS) - 1
    session.commit()


@router.get("/{year}", response_model=SeasonOut)
def get_season(year: int, session: SessionDep) -> SeasonOut:
    """Une saison passée (ou en cours), par année."""
    season = session.scalars(select(SeasonRow).where(SeasonRow.year == year)).first()
    if season is None:
        raise HTTPException(status_code=404, detail=f"Saison {year} introuvable")
    return _season_out(session, season)
