"""Les coupes d'Europe d'une saison côté API (engine/europe.py) : la Coupe d'Europe et
le Challenge européen. Tirage des poules, tours suivants, ce qu'il faut à la journée
pour jouer leurs matchs.

Leurs matchs vivent avec ceux de la saison (`SeasonRow.cup_matches`, `squad` = 'cup'),
à part des championnats, chaque coupe sous son code (`MatchRow.league`) ; leurs poules
dans `CupPoolRow`. Elles n'existent que dans un monde où les trois championnats
qualificatifs sont là. Sans code précisé, une fonction parle de la Coupe d'Europe.
"""

import random
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from data.leagues import League
from engine import europe
from engine.season import PlayoffFormat
from models import Match, Stage
from models.orm import ClubRow, CupPoolRow, MatchRow, SeasonRow

# Valeur de `MatchRow.squad` pour les matchs des coupes (voir `SeasonRow.cup_matches`).
CUP_SQUAD = "cup"

# Ce que la journée (engine/matchday.py) lit d'un « championnat » : primes et finale.
LEAGUE = League(
    code=europe.CODE,
    name=europe.NAME,
    short_name="Coupe d'Europe",
    country="Europe",
    playoffs=PlayoffFormat.TOP8,
    neutral_final=True,
    start=europe.POOL_WEEKENDS[0],
    prize_factor=0.8,
)
CHALLENGE = League(
    code=europe.CHALLENGE,
    name=europe.CHALLENGE_NAME,
    short_name="Challenge européen",
    country="Europe",
    playoffs=PlayoffFormat.TOP8,
    neutral_final=True,
    start=europe.POOL_WEEKENDS[0],
    prize_factor=0.35,
)
# Les deux coupes, la plus prestigieuse d'abord.
CUPS = {LEAGUE.code: LEAGUE, CHALLENGE.code: CHALLENGE}


def has_cup(session: Session) -> bool:
    """Le monde a-t-il les trois championnats qualificatifs ?"""
    leagues = set(session.scalars(select(ClubRow.league)))
    return set(europe.LEAGUES) <= leagues


def create_cup(
    session: Session,
    season: SeasonRow,
    ranked: dict[str, list[int]],
    rng: random.Random,
    code: str = europe.CODE,
) -> None:
    """Tire les poules et les journées de poule d'une coupe ; `ranked` : ses clubs de
    chaque championnat qualificatif, du mieux au moins bien classé."""
    if code == europe.CODE:
        pool_map = europe.draw_pools(ranked, rng)
    else:
        pool_map = europe.draw_challenge(ranked, rng)
    for letter, clubs in pool_map.items():
        for club_id in clubs:
            session.add(
                CupPoolRow(season_id=season.id, competition=code, pool=letter, club_id=club_id)
            )
    dates = europe.pool_dates(season.year, code)
    for match in europe.pool_fixtures(pool_map, dates, code):
        row = MatchRow.from_domain(match, season.id)
        row.squad = CUP_SQUAD
        season.cup_matches.append(row)
    session.commit()


def codes(season: SeasonRow) -> list[str]:
    """Les coupes de la saison, la Coupe d'Europe d'abord."""
    present = {m.league for m in season.cup_matches}
    return [code for code in CUPS if code in present]


def pools(session: Session, season: SeasonRow, code: str = europe.CODE) -> dict[str, list[int]]:
    rows = session.scalars(
        select(CupPoolRow)
        .where(CupPoolRow.season_id == season.id, CupPoolRow.competition == code)
        .order_by(CupPoolRow.id)
    )
    out: dict[str, list[int]] = {}
    for row in rows:
        out.setdefault(row.pool, []).append(row.club_id)
    return out


def rows(season: SeasonRow, code: str = europe.CODE) -> list[MatchRow]:
    return [row for row in season.cup_matches if row.league == code]


def matches(season: SeasonRow, code: str = europe.CODE) -> list[Match]:
    return [row.to_domain(stats=False) for row in rows(season, code)]


def ensure_next_round(session: Session, season: SeasonRow) -> None:
    """Crée les matchs du tour suivant de chaque coupe quand tous ceux du tour en cours
    sont joués."""
    created = False
    for code in codes(season):
        upcoming = europe.next_round(
            season.year, pools(session, season, code), matches(season, code), code
        )
        for match in upcoming:
            row = MatchRow.from_domain(match, season.id)
            row.squad = CUP_SQUAD
            season.cup_matches.append(row)
        created = created or bool(upcoming)
    if created:
        session.commit()


def seeding(session: Session, season: SeasonRow, code: str = europe.CODE) -> list[int]:
    """Les clubs d'une coupe dans l'ordre de ses têtes de série (les qualifiés des poules
    d'abord), pour l'affluence et pour départager une égalité sans tirs au but."""
    pool_map = pools(session, season, code)
    order = europe.seeds(pool_map, matches(season, code))
    return order + [club for clubs in pool_map.values() for club in clubs if club not in order]


def champion(session: Session, season: SeasonRow, code: str = europe.CODE) -> int | None:
    return europe.champion(pools(session, season, code), matches(season, code))


@dataclass
class Run:
    """Le parcours d'un club dans une coupe de la saison."""

    code: str
    name: str  # « Coupe d'Europe », « Challenge européen »
    # champion ; final, semi, quarter, pools : éliminé à ce tour ; running : encore en course.
    result: str
    won: int
    drawn: int
    lost: int
    champion_id: int | None


def runs(session: Session, season: SeasonRow, club_id: int) -> list[Run]:
    """Les coupes que le club a jouées cette saison, la Coupe d'Europe d'abord. Un match
    à élimination directe resté nul compte pour celui qui passe."""
    out = []
    for code in codes(season):
        everything = matches(season, code)
        played = [
            m
            for m in sorted(everything, key=lambda m: (m.date, m.id or 0))
            if club_id in (m.home_club_id, m.away_club_id) and m.is_played
        ]
        pending = any(
            club_id in (m.home_club_id, m.away_club_id) and not m.is_played for m in everything
        )
        if not played and not pending:
            continue
        order = seeding(session, season, code)
        record = {1: 0, 0: 0, -1: 0}
        for match in played:
            result = match.result_for(club_id)
            if match.stage.is_playoff and result == 0:
                result = 1 if match.winner_id(order) == club_id else -1
            record[result] += 1
        winner = champion(session, season, code)
        last = played[-1] if played else None
        knockout = any(m.stage.is_playoff for m in everything)
        if winner == club_id:
            result = "champion"
        elif (
            pending
            or last is None
            or winner is None
            and (
                (last.stage.is_playoff and last.winner_id(order) == club_id)
                or (not last.stage.is_playoff and not knockout)
            )
        ):
            result = "running"
        else:
            result = "pools" if last.stage == Stage.REGULAR else last.stage.value
        out.append(
            Run(
                code=code,
                name=CUPS[code].short_name,
                result=result,
                won=record[1],
                drawn=record[0],
                lost=record[-1],
                champion_id=winner,
            )
        )
    return out
