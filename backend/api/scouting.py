"""Ce que le club dirigé sait des joueurs (engine/scouting.py).

Ses propres joueurs (et ceux qu'il a prêtés), il les voit tous les jours : leurs vrais
attributs, et leur potentiel à un point près. Ceux qu'un recruteur a supervisés
(`ScoutReportRow`), il les connaît aussi, une fois le rapport rendu (au soir de la
journée suivante, ou tout de suite s'il n'y a plus de journée à jouer). Les autres,
il ne les voit que de loin : attributs estimés, potentiel à deux points et demi près.
Un sélectionneur, sans club, voit tout.
"""

import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from api.schemas import DutyOut, PlayerOut
from engine.development import OTHER_UNCERTAINTY, OWN_UNCERTAINTY
from engine.scouting import estimate
from models import Player
from models.orm import CareerRow, MatchRow, ScoutReportRow

# own : un de nos joueurs ; report : supervisé ; pending : rapport attendu ;
# estimate : vu de loin ; all : un sélectionneur, qui voit tout.
Status = str


class Knowledge:
    def __init__(self, session: Session) -> None:
        career = session.scalars(select(CareerRow)).first()
        self.club_id = career.club_id if career is not None else None
        self.reports: dict[int, datetime.date] = {}
        # Le prochain jour de match de clubs encore à jouer (None : plus aucun).
        self.next_day: datetime.date | None = None
        if self.club_id is not None:
            self.reports = dict(
                session.execute(
                    select(ScoutReportRow.player_id, func.min(ScoutReportRow.requested_on))
                    .where(ScoutReportRow.club_id == self.club_id)
                    .group_by(ScoutReportRow.player_id)
                ).all()
            )
            self.next_day = session.scalar(
                select(func.min(MatchRow.date)).where(MatchRow.home_score.is_(None))
            )

    def status(self, player: Player) -> Status:
        if self.club_id is None:
            return "all"
        if self.club_id in (player.club_id, player.loaned_from):
            return "own"
        requested = self.reports.get(player.id)
        if requested is None:
            return "estimate"
        # Rendu au soir de la journée demandée : dès qu'elle est jouée, ou s'il n'y en a plus.
        ready = self.next_day is None or self.next_day > requested
        return "report" if ready else "pending"

    def known(self, player: Player) -> bool:
        return self.status(player) in ("own", "report", "all")

    def uncertainty(self, player: Player) -> float:
        """Écart possible, en points de note, entre l'estimation du potentiel et la vérité."""
        return OWN_UNCERTAINTY if self.known(player) else OTHER_UNCERTAINTY

    def view(self, player: Player) -> Player:
        """Le joueur tel que le club le voit : vrai s'il le connaît, estimé sinon."""
        return player if self.known(player) else estimate(player)

    def report_on(self, player: Player) -> datetime.date | None:
        return self.reports.get(player.id)

    def player_out(
        self,
        player: Player,
        day: datetime.date | None = None,
        names: dict[int, str] | None = None,
        duty: DutyOut | None = None,
    ) -> PlayerOut:
        """La fiche d'un joueur telle que le club la voit (vraie ou estimée)."""
        return PlayerOut.from_player(
            self.view(player),
            day,
            names,
            duty,
            self.uncertainty(player),
            self.status(player),
            self.report_on(player),
        )
