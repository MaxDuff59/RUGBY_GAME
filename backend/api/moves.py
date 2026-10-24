"""Registre des mouvements de joueurs : chaque arrivée, départ ou retraite passe par
`log_move`, pour que le journal (api/routers/journal.py) puisse les raconter.

Rien d'autre ne lit ce registre : les effectifs restent dans `players`. Un joueur qui
quitte le jeu (retraite, agent libre qui arrête) s'efface avec `delete_player`.
"""

import datetime

from sqlalchemy import delete, or_, select
from sqlalchemy.orm import Session

from engine.journal import MoveKind
from models import ATTRIBUTE_NAMES
from models.orm import InjuryRow, JokerRow, MoveRow, NegotiationRow, PlayerRow, SuspensionRow


def delete_player(session: Session, row: PlayerRow) -> None:
    """Le joueur quitte le jeu : sa fiche, et ce qui y renvoie (suspensions, négociations,
    jokers recrutés pour lui ou pour ses blessures ; ses blessures partent avec lui).
    Postgres refuse d'effacer un joueur encore cité ailleurs, SQLite ne vérifie pas."""
    injuries = select(InjuryRow.id).where(InjuryRow.player_id == row.id)
    session.execute(
        delete(JokerRow).where(or_(JokerRow.player_id == row.id, JokerRow.injury_id.in_(injuries)))
    )
    session.execute(delete(SuspensionRow).where(SuspensionRow.player_id == row.id))
    session.execute(delete(NegotiationRow).where(NegotiationRow.player_id == row.id))
    session.delete(row)


def log_move(
    session: Session,
    kind: MoveKind,
    player: PlayerRow,
    day: datetime.date,
    origin: int | None = None,
    destination: int | None = None,
    fee: int | None = None,
) -> MoveRow:
    """Inscrit un mouvement, le joueur tel qu'il est à cet instant (âge, note).

    Un joueur libéré puis recruté le même jour (l'intersaison) ne fait qu'une
    ligne : son départ devient une arrivée libre, de son ancien club au nouveau.
    """
    overall = sum(getattr(player, name) for name in ATTRIBUTE_NAMES) / len(ATTRIBUTE_NAMES)
    if origin is None and destination is not None:
        released = session.scalars(
            select(MoveRow).where(
                MoveRow.player_id == player.id,
                MoveRow.date == day,
                MoveRow.kind == MoveKind.RELEASE.value,
            )
        ).first()
        if released is not None:
            released.kind = kind.value
            released.to_club_id = destination
            released.age, released.overall = player.age, overall
            return released
    row = MoveRow(
        date=day,
        kind=kind.value,
        player_id=player.id,
        player_name=f"{player.first_name} {player.last_name}",
        position=player.position,
        age=player.age,
        overall=overall,
        from_club_id=origin,
        to_club_id=destination,
        fee=fee,
    )
    session.add(row)
    return row
