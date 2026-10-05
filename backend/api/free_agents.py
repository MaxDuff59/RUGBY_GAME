"""Vivier des agents libres (joueurs sans club) à l'intersaison.

Règles : engine/free_agents.py. Un agent libre est un `PlayerRow` pro sans club
(`club_id` à None) ; son `contract_until` est la dernière saison de son ancien
contrat. Le premier vivier est créé avec le monde (database.py) ; le
recrutement par le manager passe par routers/transfers.py.
"""

import random
from collections.abc import Iterator

from sqlalchemy import select
from sqlalchemy.orm import Session

from engine.economy import wage_for
from engine.free_agents import ai_pick, newcomers, quits, trim_pool
from engine.offseason import develop_player
from engine.transfers import preferred_years
from models import ATTRIBUTE_NAMES, Squad
from models.orm import ClubRow, PlayerRow

# Un agent libre ne s'entraîne nulle part : il progresse (ou décline) comme
# dans le plus petit centre d'entraînement.
FREE_TRAINING_LEVEL = 1


def free_agent_rows(session: Session) -> list[PlayerRow]:
    return list(
        session.scalars(
            select(PlayerRow).where(PlayerRow.club_id.is_(None), PlayerRow.squad == Squad.PRO.value)
        )
    )


def release(row: PlayerRow, season_year: int) -> None:
    """Le joueur quitte son club sans contrat (un espoir sort du centre en pro)."""
    if row.squad == Squad.YOUTH.value:
        row.squad = Squad.PRO.value
        row.wage = wage_for(row.to_domain())
    row.club_id = None
    row.loaned_from = None
    row.contract_until = min(row.contract_until, season_year - 1)


def age_free_agents(session: Session, season_year: int, rng: random.Random) -> None:
    """Intersaison, avant le vieillissement des clubs : les agents libres vieillissent,
    progressent ou déclinent, et certains arrêtent."""
    for row in free_agent_rows(session):
        player = row.to_domain()
        player.age += 1
        develop_player(player, FREE_TRAINING_LEVEL, rng)
        if quits(player, season_year, rng):
            session.delete(row)
            continue
        row.age = player.age
        for name in ATTRIBUTE_NAMES:
            setattr(row, name, getattr(player, name))


def renew_pool(
    session: Session,
    season_year: int,
    rng: random.Random,
    my_club_id: int | None,
    player_ids: Iterator[int],
) -> None:
    """Intersaison, après les départs : les clubs IA à court d'effectif piochent
    dans le vivier, qui est ensuite ramené entre son minimum et son maximum."""
    session.flush()
    session.expire_all()
    rows = {row.id: row for row in free_agent_rows(session)}
    pool = [row.to_domain() for row in rows.values()]
    for club_row in session.scalars(select(ClubRow).where(ClubRow.id != my_club_id)):
        club = club_row.to_domain()
        while (player := ai_pick(club, pool)) is not None:
            row = rows[player.id]
            row.club_id = club.id
            row.wage = wage_for(player)
            row.contract_until = season_year + rng.randint(*preferred_years(player)) - 1
            player.club_id = club.id
            club.players.append(player)
            pool.remove(player)
    for player in trim_pool(pool):
        session.delete(rows[player.id])
        pool.remove(player)
    for player in newcomers(pool, player_ids, season_year, rng):
        session.add(PlayerRow.from_domain(player))
