"""Vivier des agents libres (joueurs sans club) à l'intersaison.

Règles : engine/free_agents.py. Un agent libre est un `PlayerRow` pro sans club
(`club_id` à None) ; son `contract_until` est la dernière saison de son ancien
contrat. Le premier vivier est créé avec le monde (database.py) ; le
recrutement par le manager passe par routers/transfers.py.
"""

import datetime
import random
from collections.abc import Iterator

from sqlalchemy import select
from sqlalchemy.orm import Session

import engine.free_agents
from api.moves import log_move
from engine.economy import wage_for
from engine.free_agents import age_free_agent
from engine.journal import MoveKind
from models import ATTRIBUTE_NAMES, Squad
from models.orm import ClubRow, PlayerRow


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
        if not age_free_agent(player, season_year, rng):
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
    day: datetime.date,
) -> None:
    """Intersaison, après les départs : les clubs IA au-dessus du plafond salarial
    renégocient leurs salaires, ceux à court d'effectif piochent dans le vivier, qui
    est ensuite ramené entre son minimum et son maximum.
    `day` : la date de l'intersaison, pour le registre des mouvements."""
    session.flush()
    session.expire_all()
    rows = {row.id: row for row in free_agent_rows(session)}
    pool = [row.to_domain() for row in rows.values()]
    clubs = [
        row.to_domain()
        for row in session.scalars(
            select(ClubRow).where(ClubRow.id != my_club_id).order_by(ClubRow.id)
        )
    ]
    renewal = engine.free_agents.renew_pool(clubs, pool, season_year, rng, player_ids)
    for player in renewal.signed:
        row = rows[player.id]
        row.club_id, row.wage, row.contract_until = (
            player.club_id,
            player.wage,
            player.contract_until,
        )
        log_move(session, MoveKind.FREE, row, day, destination=player.club_id)
    for player in renewal.renegotiated:
        session.get(PlayerRow, player.id).wage = player.wage
    for player in renewal.dropped:
        session.delete(rows[player.id])
    for player in renewal.arrivals:
        session.add(PlayerRow.from_domain(player))
