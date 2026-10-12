"""Le marché des clubs IA côté base : chaque jour de match, ce qu'ils concluent entre eux.

Règles : engine/market.py. Ici on charge les clubs IA et le vivier, on laisse le
moteur conclure, puis on enregistre : un pré-contrat est une négociation signée
(`NegotiationRow`, exécutée à l'intersaison comme celles du manager), un prêt ou
une signature change l'effectif tout de suite et s'inscrit au registre des
mouvements (api/moves.py).
"""

import datetime
import random
from collections import Counter

from sqlalchemy import select
from sqlalchemy.orm import Session

from api.deps import load_clubs
from api.free_agents import free_agent_rows
from api.moves import log_move
from engine.journal import MoveKind
from engine.market import Deal, Market
from engine.transfers import DealKind
from models import Stage
from models.orm import CareerRow, ClubRow, NegotiationRow, PlayerRow, SeasonRow

OPEN_STAGES = ("club", "player")


def _phases(season: SeasonRow) -> tuple[set[str], set[str]]:
    """Championnats en phase retour ou en phases finales, et championnats dont la
    saison régulière est en cours (commencée, pas finie)."""
    late, active = set(), set()
    for league in {m.league for m in season.matches}:
        regular = [
            m for m in season.matches if m.league == league and m.stage == Stage.REGULAR.value
        ]
        played = [m.matchday for m in regular if m.is_played]
        if not played:
            continue
        unplayed = any(not m.is_played for m in regular)
        if unplayed:
            active.add(league)
        if not unplayed or max(played) > max(m.matchday for m in regular) // 2:
            late.add(league)
    return late, active


def market_day(
    session: Session, season: SeasonRow, day: datetime.date, rng: random.Random
) -> list[Deal]:
    """Joue le marché des clubs IA après les matchs du jour `day` et enregistre ses
    accords (à l'appelant de ne rien garder en mémoire des effectifs d'avant)."""
    career = session.scalars(select(CareerRow)).first()
    mine = career.club_id if career is not None else None
    session.expire_all()  # blessures et effectifs du jour
    ids = [club_id for club_id in session.scalars(select(ClubRow.id)) if club_id != mine]
    clubs = load_clubs(session, ids)
    pool = {row.id: row for row in free_agent_rows(session)}
    late, active = _phases(season)
    signed = session.execute(
        select(NegotiationRow.player_id, NegotiationRow.club_id).where(
            NegotiationRow.stage == "agreed"
        )
    ).all()
    talks = session.scalars(
        select(NegotiationRow.player_id).where(NegotiationRow.stage.in_(OPEN_STAGES))
    )
    market = Market(
        clubs=[clubs[club_id] for club_id in sorted(clubs)],
        pool=[row.to_domain() for row in pool.values()],
        day=day,
        season_year=season.year,
        late=late,
        active=active,
        incoming=Counter(club_id for _, club_id in signed),
        taken={player_id for player_id, _ in signed} | set(talks),
    )
    deals = market.play(rng)

    for deal in deals:
        player, destination = deal.player, deal.destination
        if deal.kind == DealKind.PRECONTRACT:
            session.add(
                NegotiationRow(
                    club_id=destination.id,
                    player_id=player.id,
                    kind=DealKind.PRECONTRACT.value,
                    stage="agreed",
                    opened_on=day,
                    patience=0,
                    last_offer=None,
                    fee_demand=None,
                    fee_floor=None,
                    fee=None,
                    wage_demand=deal.wage,
                    wage_floor=None,
                    wage=deal.wage,
                    years=deal.years,
                    message=(
                        f"{player.name} s'engage avec {destination.name} "
                        f"pour {deal.years} saison(s)."
                    ),
                )
            )
            continue
        row = pool.get(player.id) or session.get(PlayerRow, player.id)
        row.club_id = destination.id
        if deal.kind == DealKind.LOAN:
            row.loaned_from = deal.origin.id
            log_move(session, MoveKind.LOAN, row, day, deal.origin.id, destination.id)
        else:
            row.wage, row.contract_until = player.wage, player.contract_until
            log_move(session, MoveKind(deal.kind.value), row, day, destination=destination.id)
    session.commit()
    return deals
