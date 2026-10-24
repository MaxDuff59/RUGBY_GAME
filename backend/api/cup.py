"""La Coupe d'Europe d'une saison côté API (engine/europe.py) : tirage des poules,
tours suivants, ce qu'il faut à la journée pour jouer ses matchs.

Ses matchs vivent avec ceux de la saison (`SeasonRow.cup_matches`, `squad` = 'cup'),
à part des championnats ; ses poules dans `CupPoolRow`. Elle n'existe que dans un
monde où les trois championnats qualificatifs sont là.
"""

import random

from sqlalchemy import select
from sqlalchemy.orm import Session

from data.leagues import League
from engine import europe
from engine.season import PlayoffFormat
from models import Match
from models.orm import ClubRow, CupPoolRow, MatchRow, SeasonRow

# Valeur de `MatchRow.squad` pour les matchs de la coupe (voir `SeasonRow.cup_matches`).
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


def has_cup(session: Session) -> bool:
    """Le monde a-t-il les trois championnats qualificatifs ?"""
    leagues = set(session.scalars(select(ClubRow.league)))
    return set(europe.LEAGUES) <= leagues


def create_cup(
    session: Session, season: SeasonRow, ranked: dict[str, list[int]], rng: random.Random
) -> None:
    """Tire les poules et les quatre journées de poule de la saison ; `ranked` : les clubs
    de chaque championnat qualificatif, du premier au dernier."""
    pools = europe.draw_pools(ranked, rng)
    for letter, clubs in pools.items():
        for club_id in clubs:
            session.add(CupPoolRow(season_id=season.id, pool=letter, club_id=club_id))
    for match in europe.pool_fixtures(pools, europe.pool_dates(season.year)):
        row = MatchRow.from_domain(match, season.id)
        row.squad = CUP_SQUAD
        season.cup_matches.append(row)
    session.commit()


def pools(session: Session, season: SeasonRow) -> dict[str, list[int]]:
    rows = session.scalars(
        select(CupPoolRow).where(CupPoolRow.season_id == season.id).order_by(CupPoolRow.id)
    )
    out: dict[str, list[int]] = {}
    for row in rows:
        out.setdefault(row.pool, []).append(row.club_id)
    return out


def matches(season: SeasonRow) -> list[Match]:
    return [row.to_domain() for row in season.cup_matches]


def ensure_next_round(session: Session, season: SeasonRow) -> None:
    """Crée les matchs du tour suivant quand tous ceux du tour en cours sont joués."""
    if not season.cup_matches:
        return
    upcoming = europe.next_round(season.year, pools(session, season), matches(season))
    for match in upcoming:
        row = MatchRow.from_domain(match, season.id)
        row.squad = CUP_SQUAD
        season.cup_matches.append(row)
    if upcoming:
        session.commit()


def seeding(session: Session, season: SeasonRow) -> list[int]:
    """Les clubs de la coupe dans l'ordre de ses têtes de série (les qualifiés des poules
    d'abord), pour l'affluence et pour départager une égalité sans tirs au but."""
    pool_map = pools(session, season)
    order = europe.seeds(pool_map, matches(season))
    return order + [club for clubs in pool_map.values() for club in clubs if club not in order]


def champion(session: Session, season: SeasonRow) -> int | None:
    return europe.champion(pools(session, season), matches(season))
