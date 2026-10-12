"""Registre des mouvements de joueurs : chaque arrivée, départ ou retraite passe par
`log_move`, pour que le journal (api/routers/journal.py) puisse les raconter.

Rien d'autre ne lit ce registre : les effectifs restent dans `players`.
"""

import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from engine.journal import MoveKind
from models import ATTRIBUTE_NAMES
from models.orm import MoveRow, PlayerRow


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
