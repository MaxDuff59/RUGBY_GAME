"""Ce que le club dirigé sait des joueurs : la justesse de son estimation de leur
potentiel (engine/development.py, `estimate`).

Ses propres joueurs (et ceux qu'il a prêtés), il les voit tous les jours ; les
autres, il les devine de loin.
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from engine.development import OTHER_UNCERTAINTY, OWN_UNCERTAINTY
from models import Player
from models.orm import CareerRow


class Knowledge:
    def __init__(self, session: Session) -> None:
        career = session.scalars(select(CareerRow)).first()
        self.club_id = career.club_id if career is not None else None

    def uncertainty(self, player: Player) -> float:
        """Écart possible, en points de note, entre l'estimation du potentiel et la vérité."""
        mine = self.club_id is not None and self.club_id in (player.club_id, player.loaned_from)
        return OWN_UNCERTAINTY if mine else OTHER_UNCERTAINTY
