"""La saison en cours : calendrier, journée par journée, phases finales, saison suivante.

Le calendrier est tiré au début de la saison (matchs sans score). Chaque appel
à `play` joue la journée suivante : la semaine d'entraînement (qui peut blesser),
tous ses matchs (qui blessent aussi), puis les recettes et les salaires. Les
phases finales se créent au fil des résultats.

Les matchs internationaux (api/internationals.py) suivent le même calendrier :
à chaque date, les listes dues sont annoncées, les joueurs retenus par une
sélection qui joue ce jour-là manquent à leur club (doublon), puis les matchs
internationaux se jouent.

Les règles sont dans le moteur (engine/season.py, engine/matchday.py,
engine/offseason.py) : ici on charge le monde depuis la base, on appelle le
moteur et on enregistre ce qu'il rend. Le hasard vient de la graine de la
saison (`season_rng`).
"""

import datetime
import itertools
import random
from dataclasses import dataclass, field

from fastapi import APIRouter, HTTPException
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from accounts import User
from api import competition, cup, internationals, plans
from api.affairs import (
    affair_out,
    draw_affair,
    forced_starters,
    ignore_pending,
    settle_promises,
)
from api.auth import UserDep
from api.deps import SessionDep, load_clubs
from api.free_agents import age_free_agents, release, renew_pool
from api.jokers import close_jokers, end_piges
from api.ledger import current_season, record
from api.live import live_match_row, load_live, load_live_test
from api.market import market_day, summer_market
from api.moves import delete_player, log_move
from api.notes import History, ensure_preseason_ranks, season_leagues
from api.routers.contracts import contracts_overview, expire_contracts, rival_signings
from api.routers.leagues import league_out
from api.routers.medical import injury_case
from api.schemas import (
    CalledPlayer,
    CallUpNotice,
    ClubRef,
    CupOut,
    CupPoolOut,
    CupRowOut,
    CupRunOut,
    DismissalOut,
    InjuryCase,
    LeagueOut,
    MatchdayOut,
    MatchSummary,
    NationOut,
    ObjectiveOut,
    PlayerRef,
    PlayOut,
    ScorerOut,
    SeasonOut,
    SeasonReviewOut,
    StandingOut,
)
from data.generator import FIRST_SEASON_YEAR
from data.leagues import DEFAULT_LEAGUE, PROMOTION, league_config, sort_codes
from data.nations import NATIONS_BY_CODE, WINDOWS_BY_CODE
from engine import europe
from engine.awards import season_awards
from engine.board import should_sack
from engine.difficulty import rules
from engine.economy import SQUAD_MIN, TransactionCategory
from engine.journal import MoveKind
from engine.matchday import Day, play_day
from engine.offseason import club_offseason
from engine.season import (
    champion,
    league_table,
    next_playoff_matches,
    phase,
    record_result,
    rng_for,
    schedule,
    seeding,
)
from engine.sponsors import deals_from, jersey_revenue
from models import (
    ATTRIBUTE_NAMES,
    EventType,
    Injury,
    Match,
    Season,
    Squad,
    Stage,
    StandingRow,
)
from models.orm import (
    AwardRow,
    CareerRow,
    ClubRow,
    DismissalRow,
    InjuryRow,
    InternationalRow,
    MatchRow,
    NegotiationRow,
    PlayerRow,
    SeasonRow,
    SpellRow,
    SuspensionRow,
    TransactionRow,
)

router = APIRouter(prefix="/seasons", tags=["saisons"])

__all__ = ["FIRST_SEASON_YEAR", "create_season", "focus_league", "router", "season_rng"]

# Les graines tiennent dans un entier de la base (32 bits signés).
SEED_RANGE = 2**31


def season_rng(season: SeasonRow, *labels: object) -> random.Random:
    """Le hasard d'un moment de la saison (une date, « offseason »...), tiré de sa
    graine : rejoué dans le même état, ce moment donne le même résultat."""
    if season.seed is None:
        season.seed = random.randrange(SEED_RANGE)  # saison d'avant les graines
    return rng_for(season.seed, *labels)


# --- Lecture de la saison ------------------------------------------------------------


def _club_rows(session: Session) -> list[ClubRow]:
    """Les clubs, effectifs compris (chargés avec eux) : coûteux, seulement s'il les faut."""
    return list(session.scalars(select(ClubRow).order_by(ClubRow.id)))


def club_names(session: Session) -> dict[int, str]:
    """Le nom de chaque club, sans charger les effectifs."""
    return dict(session.execute(select(ClubRow.id, ClubRow.name)).all())


def _club_leagues(session: Session) -> dict[int, str]:
    """Le championnat de chaque club, dans l'ordre des identifiants, sans les effectifs."""
    return dict(session.execute(select(ClubRow.id, ClubRow.league).order_by(ClubRow.id)).all())


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


def _league_domain(season: SeasonRow, league: str, stats: bool = False) -> list[Match]:
    """Les matchs d'un championnat pour le moteur ; les statistiques des joueurs
    (`stats`) seulement pour qui en a besoin, les trophées."""
    return [m.to_domain(stats) for m in _league_matches(season, league)]


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
    return league_table(_league_domain(season, league))


def _seeding(season: SeasonRow, league: str) -> list[int]:
    """Identifiants des clubs du championnat, du 1er au dernier de la saison régulière."""
    return seeding(_league_domain(season, league))


def _phase(season: SeasonRow, league: str) -> str:
    return phase(_league_domain(season, league))


def _champion_id(season: SeasonRow, league: str) -> int | None:
    return champion(_league_domain(season, league))


def _summary(row: MatchRow, names: dict[int, str]) -> MatchSummary:
    return MatchSummary.from_match(row.to_domain(), names)


def _matchday_out(rows: list[MatchRow], names: dict[int, str]) -> MatchdayOut:
    first = rows[0]
    in_cup = first.squad == cup.CUP_SQUAD
    return MatchdayOut(
        matchday=first.matchday,
        stage=Stage(first.stage),
        date=first.date,
        matches=[_summary(row, names) for row in rows],
        cup=in_cup,
        competition=cup.CUPS[first.league].short_name if in_cup else None,
        pool_rounds=europe.FORMATS[first.league].pool_rounds if in_cup else None,
    )


def next_fixture(session: Session, season: SeasonRow) -> MatchRow | None:
    """Le prochain match du club dirigé, celui où s'arrête la prochaine journée jouée :
    la journée de son championnat, ou un match de Coupe d'Europe qui tombe avant.
    None s'il ne joue pas la prochaine journée de son championnat (phases finales).

    Les tours de phases finales prêts sont déjà ouverts (`_prepare_day`, après chaque
    journée)."""
    career = session.scalars(select(CareerRow)).first()
    if career is None:
        return None
    league = focus_league(session)
    club_id = career.club_id
    unplayed = [m for m in season.matches if not m.is_played and m.league == league]
    league_day = min((m.date for m in unplayed), default=None)
    mine = [
        m
        for m in [*unplayed, *season.cup_matches]
        if not m.is_played
        and club_id in (m.home_club_id, m.away_club_id)
        and (league_day is None or m.date <= league_day)
    ]
    return min(mine, key=lambda m: (m.date, m.id), default=None)


def _next_match_out(
    session: Session, season: SeasonRow, names: dict[int, str]
) -> MatchdayOut | None:
    """Le prochain match du club dirigé et les autres affiches du jour de sa compétition."""
    row = next_fixture(session, season)
    if row is None:
        return None
    pool = season.cup_matches if row.squad == cup.CUP_SQUAD else season.matches
    todays = sorted(
        (m for m in pool if not m.is_played and m.date == row.date and m.league == row.league),
        key=lambda m: m.id,
    )
    return _matchday_out(todays, names)


def _season_out(session: Session, season: SeasonRow, league: str | None = None) -> SeasonOut:
    league = league or focus_league(session)
    codes = _season_league_codes(season)
    if league not in codes:
        raise HTTPException(status_code=404, detail=f"Championnat « {league} » introuvable")
    names = club_names(session)

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
        next_match=_next_match_out(session, season, names),
        standings=standings,
        matches=[_summary(m, names) for m in matches],
        champion=ClubRef(id=champion_id, name=names[champion_id]) if champion_id else None,
        cups=[_cup_out(session, season, code, names) for code in cup.codes(season)],
    )


def _cup_out(session: Session, season: SeasonRow, code: str, names: dict[int, str]) -> CupOut:
    """Une coupe d'Europe de la saison : poules, matchs, phase et champion."""
    pool_map = cup.pools(session, season, code)
    domain = cup.matches(season, code)
    tables = europe.pool_tables(pool_map, domain)
    played = [m for m in domain if m.stage == Stage.REGULAR and m.is_played]
    standings = league_table(played).standings if played else {}
    pools = []
    for letter, order in tables.items():
        rows = []
        for club_id in order:
            line = standings.get(club_id)
            rows.append(
                CupRowOut(
                    club=ClubRef(id=club_id, name=names[club_id]),
                    played=line.played if line else 0,
                    won=line.won if line else 0,
                    points_difference=line.points_difference if line else 0,
                    league_points=line.league_points if line else 0,
                )
            )
        pools.append(CupPoolOut(pool=letter, table=rows))
    champion_id = europe.champion(pool_map, domain)
    knockout = any(m.stage != Stage.REGULAR for m in domain)
    rows = sorted(cup.rows(season, code), key=lambda m: (m.date, m.id))
    return CupOut(
        code=code,
        name=cup.CUPS[code].short_name,
        pool_rounds=europe.FORMATS[code].pool_rounds,
        pools=pools,
        matches=[_summary(row, names) for row in rows],
        phase="finished" if champion_id else "knockout" if knockout else "pools",
        champion=ClubRef(id=champion_id, name=names[champion_id]) if champion_id else None,
    )


# --- Création et avancement ----------------------------------------------------------


def create_season(session: Session, year: int, seed: int | None = None) -> SeasonRow:
    """Tire le calendrier de la saison régulière de chaque championnat (matchs sans
    score) et l'enregistre, avec la graine du hasard de la saison (au hasard sans `seed`)."""
    by_league: dict[str, list[int]] = {}
    for club_id, league in _club_leagues(session).items():
        by_league.setdefault(league, []).append(club_id)

    season = SeasonRow(year=year, seed=random.randrange(SEED_RANGE) if seed is None else seed)
    pros, youths = [], []
    for league, club_ids in by_league.items():
        fixtures = schedule(league_config(league), club_ids, year, code=league)
        # Les espoirs jouent les mêmes affiches, le même jour (saison régulière seulement).
        for squad, target in ((Squad.PRO, pros), (Squad.YOUTH, youths)):
            for match in fixtures:
                row = MatchRow.from_domain(match)
                row.squad = squad.value
                target.append(row)
    season.matches, season.youth_matches = pros, youths
    session.add(season)
    session.commit()
    # Figé maintenant, avant que l'effectif ne bouge : l'objectif de la direction en dépend.
    preseason = ensure_preseason_ranks(session, season)
    if cup.has_cup(session):
        _draw_cup(session, season, preseason)
    # Calendrier international, et les listes déjà dues au premier jour de la saison.
    _prepare_day(session, season)
    return season


def _draw_cup(session: Session, season: SeasonRow, preseason: dict[int, int]) -> None:
    """Les coupes d'Europe de la saison : les clubs de chaque championnat qualificatif dans
    l'ordre de la saison régulière précédente, ou, la première saison, de leur effectif ;
    les huit premiers en Coupe d'Europe, les autres au Challenge européen."""
    previous = session.scalars(select(SeasonRow).where(SeasonRow.year == season.year - 1)).first()
    leagues = _club_leagues(session)
    ranked = {}
    for league in europe.LEAGUES:
        members = [club_id for club_id, code in leagues.items() if code == league]
        if previous is not None and league in _season_league_codes(previous):
            order = [c for c in _seeding(previous, league) if c in members]
            ranked[league] = order + [c for c in members if c not in order]
        else:
            ranked[league] = sorted(members, key=lambda c: preseason.get(c, len(members)))
    cup.create_cup(session, season, ranked, season_rng(season, "cup"))
    rest = {league: clubs[europe.CHALLENGE_FROM :] for league, clubs in ranked.items()}
    cup.create_cup(session, season, rest, season_rng(season, "challenge"), europe.CHALLENGE)


def _ensure_next_stage(session: Session, season: SeasonRow, league: str) -> None:
    """Crée les matchs du tour suivant d'un championnat quand tous ceux du tour en
    cours sont joués."""
    upcoming = next_playoff_matches(
        league_config(league), _league_domain(season, league), season.year
    )
    if not upcoming:
        return  # tour en cours, ou finale jouée : la saison du championnat est terminée
    season.matches.extend(MatchRow.from_domain(match) for match in upcoming)
    session.commit()


def _prepare_day(session: Session, season: SeasonRow) -> datetime.date | None:
    """Ouvre les tours de phases finales prêts et annonce les listes des sélections
    dues ; renvoie le prochain jour de match, clubs et sélections confondus."""
    for league in _season_league_codes(season):
        _ensure_next_stage(session, season, league)
    cup.ensure_next_round(session, season)
    internationals.ensure_calendar(session, season)
    internationals.ensure_next_round(session, season)
    dates = [m.date for m in [*season.matches, *season.cup_matches] if not m.is_played]
    next_test = internationals.next_test_date(session, season)
    if next_test is not None:
        dates.append(next_test)
    day = min(dates, default=None)
    if day is not None:
        internationals.announce_due(session, season, day)
    return day


def _write_result(row: MatchRow, match: Match) -> None:
    row.home_score, row.away_score = match.home_score, match.away_score
    row.events = MatchRow.from_domain(match).events
    row.home_lineup, row.away_lineup = list(match.home_lineup), list(match.away_lineup)
    saved = MatchRow.from_domain(match)
    row.weather, row.stats = saved.weather, saved.stats
    row.spectators, row.atmosphere = saved.spectators, saved.atmosphere
    row.momentum = saved.momentum


@dataclass
class DayResult:
    """Ce qu'un jour de match a donné : les matchs de clubs, les matchs internationaux,
    et les blessés du club dirigé (ou, pour un sélectionneur, de sa liste)."""

    matches: list[MatchRow] = field(default_factory=list)
    tests: list[InternationalRow] = field(default_factory=list)
    cases: list[InjuryCase] = field(default_factory=list)


# Ce que la progression d'un joueur change (engine/development.py).
PROGRESSION_COLUMNS = (*ATTRIBUTE_NAMES, "potential", "progress", "season_gain")

# Les recettes d'un jour de match (billetterie, buvettes et boutique, sponsors).
REVENUES = {
    TransactionCategory.TICKETING,
    TransactionCategory.HOSPITALITY,
    TransactionCategory.SPONSORS,
}


def _play_day(session: Session, season: SeasonRow, day: datetime.date) -> DayResult:
    """Joue tous les matchs du jour `day`, tous championnats confondus, et passe les
    écritures financières : charge le monde, laisse le moteur jouer la journée
    (engine/matchday.py), puis enregistre ce qu'il rend. Les matchs internationaux
    du jour se jouent ensuite (api/internationals.py).

    Le marché des clubs IA (api/market.py) se joue ensuite, une fois par jour de match.

    Seuls les clubs qui jouent ce jour-là ont leur semaine d'entraînement, sans leurs
    joueurs retenus par une sélection qui joue le même jour. Si le match du club
    dirigé est en cours en direct (api/live.py), il est joué jusqu'au bout par le
    staff et compte tel quel ; la semaine d'entraînement a alors déjà eu lieu.
    """
    session.expire_all()  # blessures et effectifs des jours précédents
    league_rows = sorted(
        (m for m in season.matches if not m.is_played and m.date == day),
        key=lambda m: (m.league, m.id),
    )
    # La Coupe d'Europe joue ses week-ends à part, que les championnats laissent libres.
    cup_rows = [m for m in season.cup_matches if not m.is_played and m.date == day]
    todays = league_rows + cup_rows
    youth_rows = [m for m in season.youth_matches if m.date == day and not m.is_played]
    leagues = sorted({m.league for m in league_rows})
    cup_clubs = {club for m in cup_rows for club in (m.home_club_id, m.away_club_id)}
    cups_today = sorted({m.league for m in cup_rows})
    career = session.scalars(select(CareerRow)).first()
    my_club_id = career.club_id if career is not None else None

    # Seuls les clubs des championnats du jour, ceux de la coupe (et le club dirigé)
    # sont chargés.
    rows_by_id = {
        row.id: row
        for row in session.scalars(
            select(ClubRow)
            .where(or_(ClubRow.league.in_(leagues), ClubRow.id.in_(cup_clubs)))
            .order_by(ClubRow.id)
        )
    }
    wanted = set(rows_by_id) | ({my_club_id} if my_club_id is not None else set())
    clubs = load_clubs(session, wanted)
    players = {p.id: p for club in clubs.values() for p in [*club.players, *club.youths]}
    if my_club_id is not None:
        # Titularisations promises au manager (api/affairs.py).
        clubs[my_club_id].forced_starters = forced_starters(session, my_club_id)
    # Doublon : les joueurs retenus par une sélection qui joue aujourd'hui manquent
    # à leur club, qui fait monter des espoirs aux postes dégarnis.
    away = internationals.absentees_on(session, season, day)
    for club in clubs.values():
        internationals.rules.release(club, away, day)
    human = internationals.selector(session)
    watched = _selector_list(session, season, human) if human is not None else set()

    # Match en direct du club dirigé : le staff finit ce qu'il reste à jouer. Un jour
    # où seul un autre championnat joue, il attend le sien (ses clubs ne sont pas chargés).
    live = load_live(session, clubs) if live_match_row(session) in todays else None

    def finish_live(match: Match) -> Match | None:
        if live is None or match.id != live.match_row.id:
            return None
        live.match.auto = {match.home_club_id, match.away_club_id}
        return live.match.play_to_end()

    # Forme du jour de chaque club (moral, cohésion, fraîcheur), avant toute écriture.
    history = History.load(session)
    world = Day(
        date=day,
        clubs=clubs,
        forms={club_id: history.form(clubs[club_id], day) for club_id in rows_by_id},
        leagues={league: league_config(league) for league in leagues}
        | {code: cup.CUPS[code] for code in cups_today},
        seeding={league: _seeding(season, league) for league in leagues}
        | {code: cup.seeding(session, season, code) for code in cups_today},
        regular_matchdays={league: _regular_matchday_count(season, league) for league in leagues}
        | {code: europe.FORMATS[code].pool_rounds for code in cups_today},
        managed_club_id=my_club_id,
        fervour=lambda club_id: history.fervour(club_id).value,
        shirt_revenue=lambda club_id: jersey_revenue(deals_from(rows_by_id[club_id].sponsors)),
    )
    matches = [row.to_domain() for row in todays]
    youth_matches = [row.to_domain() for row in youth_rows]
    report = play_day(
        world,
        matches,
        season_rng(season, day),
        youth_matches=youth_matches,
        # Déjà faite si le match en direct a commencé : ses blessés sont dans la sauvegarde.
        trained=live is not None,
        finished=finish_live,
    )

    for row, match in zip([*todays, *youth_rows], [*matches, *youth_matches], strict=True):
        _write_result(row, match)

    # Blessures de la journée : enregistrées en base, et renvoyées pour le club dirigé
    # (ou, pour un sélectionneur, pour les joueurs de sa liste).
    my_injuries: list[tuple[InjuryRow, Injury]] = []
    if live is not None:
        for injury_row in session.scalars(
            select(InjuryRow).where(InjuryRow.id.in_(live.row.my_injuries))
        ):
            my_injuries.append((injury_row, injury_row.to_domain()))
    for club_id, injury in report.injuries:
        injury_row = InjuryRow.from_domain(injury)
        session.add(injury_row)
        if club_id == my_club_id or injury.player_id in watched:
            my_injuries.append((injury_row, injury))

    # Discipline : les peines prononcées, puis ce que chacun a encore à purger.
    for suspension in report.suspensions:
        session.add(
            SuspensionRow(
                player_id=suspension.player_id,
                club_id=suspension.club_id,
                date=day,
                matches=suspension.matches,
                reason=suspension.reason.value,
            )
        )
    for player_id in report.disciplined:
        player, player_row = players[player_id], session.get(PlayerRow, player_id)
        player_row.suspended_matches = player.suspended_matches
        player_row.yellow_cards = player.yellow_cards
    # Progression : chacun a avancé vers son potentiel (engine/development.py). Toutes
    # les colonnes de progression sont écrites pour chacun, même inchangées : les lignes
    # ont alors la même forme et partent en une requête groupée, pas une par joueur.
    for player_id in report.developed:
        player, player_row = players[player_id], session.get(PlayerRow, player_id)
        for name in PROGRESSION_COLUMNS:
            setattr(player_row, name, getattr(player, name))
            flag_modified(player_row, name)

    # Les matchs internationaux du jour, avec leur propre hasard : les clubs jouent
    # la même journée qu'il y en ait ou non.
    test_day = internationals.play_tests(
        session,
        season,
        day,
        season_rng(season, day, "internationals"),
        history.appearances,
        clubs,
        my_club_id,
        live=load_live_test(session) if human is not None else None,
    )
    for injury_row, injury in test_day.injuries:
        in_my_club = injury.player_id in players and (
            players[injury.player_id].club_id == my_club_id
        )
        if (my_club_id is not None and in_my_club) or injury.player_id in watched:
            my_injuries.append((injury_row, injury))

    # Les recettes du club dirigé suivent la difficulté de la carrière (engine/difficulty.py).
    revenue = rules(career.difficulty).revenue if career is not None else 1.0
    for movement in report.movements:
        amount = movement.amount
        if movement.club_id == my_club_id and amount > 0 and movement.category in REVENUES:
            amount = round(amount * revenue)
        record(
            session,
            rows_by_id[movement.club_id],
            movement.category,
            movement.label,
            amount,
            day,
            movement.matchday,
        )

    if live is not None:
        session.delete(live.row)
    session.commit()
    # Une finale jouée : les trophées de son championnat s'inscrivent au palmarès.
    finals = {row.league for row in league_rows if row.stage == Stage.FINAL.value}
    if finals:
        record_awards(session, season, finals)

    cases = []
    if my_club_id is not None:
        my_club = clubs[my_club_id]
        for injury_row, injury in my_injuries:
            injury.id = injury_row.id  # attribué à l'enregistrement
            cases.append(injury_case(players[injury.player_id], injury, my_club, day))
    elif my_injuries:
        listed = {
            row.id: row.to_domain()
            for row in session.scalars(
                select(PlayerRow).where(PlayerRow.id.in_([i.player_id for _, i in my_injuries]))
            )
        }
        for injury_row, injury in my_injuries:
            injury.id = injury_row.id
            cases.append(
                injury_case(listed[injury.player_id], injury, internationals.rules.NO_CLUB, day)
            )
    # Le soir des matchs, les clubs IA traitent entre eux : pré-contrats, prêts, agents libres.
    market_day(session, season, day, season_rng(season, day, "market"))
    return DayResult(matches=todays, tests=test_day.rows, cases=cases)


def _selector_list(session: Session, season: SeasonRow, human) -> set[int]:
    """Les joueurs de la liste du sélectionneur, tant que sa fenêtre n'est pas finie :
    leurs blessures, en club comme en sélection, lui sont signalées."""
    nation = NATIONS_BY_CODE[human.nation]
    open_windows = {
        row.competition
        for row in internationals.test_rows(session, season)
        if not row.is_played and nation.id in (row.home_id, row.away_id)
    }
    return {
        player_id
        for row in internationals.call_up_rows(session, season)
        if row.nation == nation.code and row.competition in open_windows
        for player_id in row.player_ids
    }


def _play_matchday(session: Session, season: SeasonRow) -> tuple[MatchdayOut, list[InjuryCase]]:
    """Joue jusqu'à la prochaine journée du championnat du club dirigé, ou jusqu'à son
    prochain match de Coupe d'Europe s'il tombe avant.

    Les autres championnats ont leur propre calendrier : leurs matchs des jours
    d'avant (et du même jour) se jouent en chemin. Renvoie la journée jouée (du
    championnat du club dirigé, ou de la coupe) et ses blessés.
    """
    league = focus_league(session)
    if _phase(season, league) == "finished":
        raise HTTPException(status_code=400, detail="La saison est terminée")
    career = session.scalars(select(CareerRow)).first()
    my_club_id = career.club_id if career is not None else None
    injuries: list[InjuryCase] = []
    while (day := _prepare_day(session, season)) is not None:
        result = _play_day(session, season, day)
        injuries += result.cases
        ours = [m for m in result.matches if m.league == league]
        if ours:
            break
        mine = next(
            (
                m
                for m in result.matches
                if m.squad == cup.CUP_SQUAD and my_club_id in (m.home_club_id, m.away_club_id)
            ),
            None,
        )
        if mine is not None:
            # Les affiches du jour de sa coupe (l'autre coupe joue peut-être le même jour).
            ours = [
                m for m in result.matches if m.squad == cup.CUP_SQUAD and m.league == mine.league
            ]
            break
    else:
        raise HTTPException(status_code=400, detail="La saison est terminée")
    _prepare_day(session, season)
    names = club_names(session)
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
    names = club_names(session)
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

    # Les marqueurs comptent aussi les matchs de coupe d'Europe.
    cup_rows = [row for code in cup.codes(season) for row in cup.rows(season, code)]
    points: dict[int, int] = {}
    tries: dict[int, int] = {}
    for row in [*matches, *cup_rows]:
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
        # Le titre vaut tous les objectifs, quel que soit le rang de saison régulière.
        objective_met=rank <= goal.target_rank or playoffs == "champion",
        youth_rank=youth_ids.index(club_id) + 1 if youth_rows else None,
        balance_start=balance - season_total,
        balance_end=balance,
        scorers=scorers,
        cups=[
            CupRunOut(
                code=run.code,
                name=run.name,
                result=run.result,
                won=run.won,
                drawn=run.drawn,
                lost=run.lost,
                champion=ClubRef(id=run.champion_id, name=names[run.champion_id])
                if run.champion_id is not None
                else None,
            )
            for run in cup.runs(session, season, club_id)
        ],
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
    if internationals.selector(session) is not None:
        raise HTTPException(
            status_code=400, detail="Un sélectionneur avance jour par jour (/selection/advance)"
        )
    competition.require_running(session, season)
    ignore_pending(session)
    known_lists = {row.id for row in internationals.call_up_rows(session, season)}
    played, injuries = _play_matchday(session, season)
    dismissal = _board_verdict(session, played)
    affairs, signings, call_ups = [], [], []
    if dismissal is None:
        call_ups = _call_up_notices(session, season, known_lists)
        rng = season_rng(season, played.date, "affairs")
        affairs = settle_promises(
            session, season, played.date, internationals.absentees_on(session, season, played.date)
        )
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
        call_ups=call_ups,
    )


def _call_up_notices(session: Session, season: SeasonRow, known: set[int]) -> list[CallUpNotice]:
    """Les joueurs du club dirigé retenus dans les listes annoncées depuis `known`
    (celles d'avant la journée), fenêtre par fenêtre, avec les doublons à prévoir."""
    career = session.scalars(select(CareerRow)).first()
    new = [row for row in internationals.call_up_rows(session, season) if row.id not in known]
    if career is None or not new:
        return []
    duties = internationals.club_duties(session, career.club_id)
    squad = {row.id: row for row in session.get(ClubRow, career.club_id).players}
    notices: dict[str, CallUpNotice] = {}
    for call in new:
        nation = NATIONS_BY_CODE[call.nation]
        for player_id in call.player_ids:
            if player_id not in squad:
                continue
            player = squad[player_id].to_domain()
            notice = notices.setdefault(
                call.competition,
                CallUpNotice(
                    competition=WINDOWS_BY_CODE[call.competition].name, players=[], doublons=[]
                ),
            )
            notice.players.append(
                CalledPlayer(
                    player=PlayerRef(
                        id=player.id,
                        name=player.name,
                        position=player.position,
                        age=player.age,
                        overall=player.overall,
                    ),
                    nation=NationOut.model_validate(nation),
                )
            )
            duty = duties.get(player_id)
            if duty is not None:
                notice.doublons = sorted({*notice.doublons, *duty.dates})
    return list(notices.values())


def _board_verdict(session: Session, played: MatchdayOut) -> DismissalRow | None:
    """Après une journée où le club dirigé a joué, la direction peut limoger le manager.

    La carrière est alors supprimée et les négociations en cours rompues ; le
    monde continue, et le manager peut reprendre un autre club.
    """
    career = session.scalars(select(CareerRow)).first()
    # En mode compétition, le manager mène son club jusqu'au bout de la coupe.
    if career is None or competition.current(session) is not None:
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
    rounds = 2 * (len(history.league_clubs(club_id)) - 1)
    if not should_sack(confidence, regular_played, rounds, rules(career.difficulty).sack_threshold):
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
    for spell in session.scalars(
        select(SpellRow).where(SpellRow.manager_name == career.manager_name, SpellRow.end.is_(None))
    ):
        spell.end, spell.reason = played.date, "dismissed"
    session.delete(career)
    session.commit()
    return dismissal


@router.post("/next", response_model=SeasonOut, status_code=201)
def start_next_season(session: SessionDep, user: UserDep) -> SeasonOut:
    """Intersaison : fin des prêts, pré-contrats exécutés (les nôtres et ceux des
    concurrents), fins de contrat, puis les joueurs vieillissent, les plus âgés
    partent, les jeunes arrivent, les clubs IA complètent leur effectif parmi
    les agents libres, et un nouveau calendrier est tiré.

    Il suffit que le championnat du club dirigé soit terminé : les autres jouent
    d'abord ce qu'il leur reste. Puis le champion de Pro D2 monte en Top 14 et le
    dernier du Top 14 descend.

    Refusée si l'effectif pro du club dirigé passerait sous le minimum, ou si le
    contrat du manager s'achève sans qu'il ait prolongé, signé ailleurs ou quitté
    le club (api/routers/career.py), ou si le compte gratuit a joué toutes ses
    saisons (api/plans.py) : la nouvelle compte dans les siennes."""
    if competition.current(session) is not None:
        raise HTTPException(status_code=400, detail="Une compétition se joue sur une saison")
    plans.require_season(user)
    season = _current_or_404(session)
    if internationals.selector(session) is not None:
        # Un sélectionneur suit toute la saison du monde, jour par jour.
        if _prepare_day(session, season) is not None:
            raise HTTPException(status_code=400, detail="La saison n'est pas terminée")
    elif _phase(season, focus_league(session)) != "finished":
        raise HTTPException(status_code=400, detail="La saison n'est pas terminée")
    career = session.scalars(select(CareerRow)).first()
    my_club_id = career.club_id if career is not None else None
    if career is not None and (career.contract_until or season.year + 1) <= season.year:
        raise HTTPException(
            status_code=400,
            detail=(
                "Ton contrat s'achève avec la saison : prolonge-le, signe ailleurs "
                "ou quitte le club."
            ),
        )
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
    return _season_out(session, offseason(session, user, season, my_club_id))


def offseason(session: Session, user: User, season: SeasonRow, my_club_id: int | None) -> SeasonRow:
    """L'intersaison de `season` (voir `start_next_season`), et la saison suivante.
    `my_club_id` : le club que le manager gère lui-même ; les autres le sont par leur
    staff, comme celui qu'un manager rejoint à la fin de la saison (api/routers/career.py)."""
    _finish_world(session, season)
    session.expire_all()
    record_awards(session, season)
    promoted, relegated = _promotion(season)
    if promoted is not None and relegated is not None:
        lower, upper = PROMOTION
        session.get(ClubRow, promoted).league = upper
        session.get(ClubRow, relegated).league = lower
        session.commit()

    rng = season_rng(season, "offseason")
    year = season.year + 1
    # Date des mouvements de l'intersaison (api/moves.py) : au lendemain du dernier match.
    day = max(m.date for m in season.matches) + datetime.timedelta(days=1)
    close_jokers(session, year)
    _offseason_moves(session, year, rng, my_club_id, day)
    age_free_agents(session, year, rng)
    next_id = (session.scalar(select(func.max(PlayerRow.id))) or 0) + 1
    player_ids = itertools.count(next_id)

    for club_row in _club_rows(session):
        club = club_row.to_domain()
        rows = {row.id: row for row in [*club_row.players, *club_row.youths]}
        squad = [*club.players, *club.youths]
        # Retraites, et espoirs trop âgés : les clubs IA promeuvent ceux qu'ils
        # peuvent garder, le manager a dû le faire lui-même avant l'intersaison ;
        # les autres quittent le centre et deviennent agents libres.
        moves = club_offseason(
            club, player_ids, rng, year, promotes_youths=club_row.id != my_club_id
        )
        retired = {player.id for player in moves.retired}
        for player in squad:
            row = rows[player.id]
            if player.id in retired:
                row.age = player.age
                log_move(session, MoveKind.RETIREMENT, row, day, origin=club_row.id)
                delete_player(session, row)
                continue
            row.age = player.age
            row.yellow_cards = player.yellow_cards
            row.season_gain = player.season_gain
            for name in ATTRIBUTE_NAMES:
                setattr(row, name, getattr(player, name))
        for youth in moves.promoted:
            rows[youth.id].squad, rows[youth.id].wage = Squad.PRO.value, youth.wage
        for youth in moves.released:
            release(rows[youth.id], year)
        for youth in moves.newcomers:
            session.add(PlayerRow.from_domain(youth))
    # Le mercato d'été entre clubs IA, avant qu'ils ne complètent leur effectif.
    summer_market(session, year, season_rng(season, "mercato"), my_club_id, day)
    renew_pool(session, year, rng, my_club_id, player_ids, day)
    internationals.offseason(session, rng)
    session.commit()

    created = create_season(session, year, rng.randrange(SEED_RANGE))
    plans.count_season(user)
    return created


def record_awards(session: Session, season: SeasonRow, finals: set[str] | None = None) -> None:
    """Les trophées de chaque championnat de la saison (engine/awards.py), avec le nom des
    joueurs : inscrits le jour de sa finale (`finals` : les championnats qui l'ont jouée),
    sinon à l'intersaison, avant les retraites. Un championnat inscrit n'est pas repris."""
    done = set(session.scalars(select(AwardRow.league).where(AwardRow.year == season.year)))
    if finals is None:
        leagues = [code for code in _season_league_codes(season) if code not in done]
    else:
        leagues = [
            code
            for code in sort_codes(finals)
            if code not in done and _phase(season, code) == "finished"
        ]
    if not leagues:
        return
    players = {row.id: row for row in session.scalars(select(PlayerRow))}
    domain = {pid: row.to_domain() for pid, row in players.items()}
    for league in leagues:
        for award in season_awards(_league_domain(season, league, stats=True), domain):
            row = players[award.player_id]
            session.add(
                AwardRow(
                    year=season.year,
                    league=league,
                    kind=award.kind.value,
                    slot=award.position.value if award.position else None,
                    player_id=award.player_id,
                    player_name=f"{row.first_name} {row.last_name}",
                    position=row.position,
                    club_id=award.club_id,
                    value=award.value,
                )
            )
    session.commit()


def _offseason_moves(
    session: Session,
    year: int,
    rng: random.Random,
    my_club_id: int | None,
    day: datetime.date,
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
            if player.club_id != neg.club_id:
                log_move(session, MoveKind.PRECONTRACT, player, day, player.club_id, neg.club_id)
            player.club_id = neg.club_id
            player.wage = neg.wage
            player.contract_until = year + neg.years - 1
            neg.stage = "done"
        elif neg.stage != "failed":
            neg.stage = "failed"
            neg.message = "La saison est terminée sans accord."

    session.flush()
    expire_contracts(session, year, my_club_id, rng, day)
    session.commit()
    session.expire_all()  # les effectifs ont changé : relationships à relire


@router.get("/{year}", response_model=SeasonOut)
def get_season(year: int, session: SessionDep, league: str | None = None) -> SeasonOut:
    """Une saison passée (ou en cours), par année et par championnat."""
    season = session.scalars(select(SeasonRow).where(SeasonRow.year == year)).first()
    if season is None:
        raise HTTPException(status_code=404, detail=f"Saison {year} introuvable")
    return _season_out(session, season, league)
