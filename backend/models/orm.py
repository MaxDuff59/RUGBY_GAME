"""Tables SQLAlchemy et conversion vers/depuis les objets du domaine.

Le moteur ne voit jamais ces classes : l'API charge des lignes, les convertit
avec `to_domain()`, appelle le moteur, puis sauvegarde le résultat.
"""

import datetime

from sqlalchemy import JSON, Date, ForeignKey, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from models.domain import (
    Career,
    Club,
    EventType,
    Facilities,
    Injury,
    InjurySeverity,
    InjurySource,
    Match,
    MatchEvent,
    Player,
    Position,
    Protocol,
    StaffMember,
    StaffRole,
    Stage,
)


class Base(DeclarativeBase):
    pass


class ClubRow(Base):
    __tablename__ = "clubs"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True)
    balance: Mapped[int] = mapped_column(default=0)
    stadium_capacity: Mapped[int] = mapped_column(default=4000)
    training_level: Mapped[int] = mapped_column(default=1)
    academy_level: Mapped[int] = mapped_column(default=1)

    players: Mapped[list["PlayerRow"]] = relationship(back_populates="club")
    staff: Mapped[list["StaffRow"]] = relationship(back_populates="club")

    def to_domain(self) -> Club:
        return Club(
            id=self.id,
            name=self.name,
            players=[p.to_domain() for p in self.players],
            staff=[s.to_domain() for s in self.staff],
            balance=self.balance,
            facilities=Facilities(
                stadium_capacity=self.stadium_capacity,
                training_level=self.training_level,
                academy_level=self.academy_level,
            ),
        )

    @classmethod
    def from_domain(cls, club: Club) -> "ClubRow":
        return cls(
            id=club.id,
            name=club.name,
            balance=club.balance,
            stadium_capacity=club.facilities.stadium_capacity,
            training_level=club.facilities.training_level,
            academy_level=club.facilities.academy_level,
            players=[PlayerRow.from_domain(p) for p in club.players],
            staff=[StaffRow.from_domain(s) for s in club.staff],
        )


class PlayerRow(Base):
    __tablename__ = "players"

    id: Mapped[int] = mapped_column(primary_key=True)
    first_name: Mapped[str] = mapped_column(String(50))
    last_name: Mapped[str] = mapped_column(String(50))
    age: Mapped[int]
    position: Mapped[str] = mapped_column(String(12))
    pace: Mapped[int]
    power: Mapped[int]
    handling: Mapped[int]
    passing: Mapped[int]
    kicking: Mapped[int]
    tackling: Mapped[int]
    scrum: Mapped[int]
    lineout: Mapped[int]
    wage: Mapped[int] = mapped_column(default=0)
    club_id: Mapped[int | None] = mapped_column(ForeignKey("clubs.id"))

    club: Mapped[ClubRow | None] = relationship(back_populates="players")
    # Dossier médical complet ; le domaine ne garde que la blessure la plus récente.
    injuries: Mapped[list["InjuryRow"]] = relationship(
        back_populates="player", cascade="all, delete-orphan"
    )

    @property
    def latest_injury(self) -> "InjuryRow | None":
        return max(self.injuries, key=lambda i: (i.occurred_on, i.id), default=None)

    def to_domain(self) -> Player:
        latest = self.latest_injury
        return Player(
            id=self.id,
            first_name=self.first_name,
            last_name=self.last_name,
            age=self.age,
            position=Position(self.position),
            pace=self.pace,
            power=self.power,
            handling=self.handling,
            passing=self.passing,
            kicking=self.kicking,
            tackling=self.tackling,
            scrum=self.scrum,
            lineout=self.lineout,
            club_id=self.club_id,
            wage=self.wage,
            injury=latest.to_domain() if latest is not None else None,
        )

    @classmethod
    def from_domain(cls, player: Player) -> "PlayerRow":
        return cls(
            id=player.id,
            first_name=player.first_name,
            last_name=player.last_name,
            age=player.age,
            position=player.position.value,
            club_id=player.club_id,
            wage=player.wage,
            **player.attributes,
        )


class InjuryRow(Base):
    """Une blessure, en cours ou passée (voir engine/medical.py)."""

    __tablename__ = "injuries"

    id: Mapped[int] = mapped_column(primary_key=True)
    player_id: Mapped[int] = mapped_column(ForeignKey("players.id"))
    severity: Mapped[str] = mapped_column(String(10))
    kind: Mapped[str] = mapped_column(String(100))
    source: Mapped[str] = mapped_column(String(10))
    occurred_on: Mapped[datetime.date] = mapped_column(Date)
    base_weeks: Mapped[int]
    return_date: Mapped[datetime.date] = mapped_column(Date)
    protocol: Mapped[str] = mapped_column(String(12), default=Protocol.STANDARD.value)
    protocol_chosen: Mapped[bool] = mapped_column(default=True)
    relapse: Mapped[bool] = mapped_column(default=False)
    relapse_risk: Mapped[float] = mapped_column(default=0.0)

    player: Mapped[PlayerRow] = relationship(back_populates="injuries")

    def to_domain(self) -> Injury:
        return Injury(
            id=self.id,
            player_id=self.player_id,
            severity=InjurySeverity(self.severity),
            kind=self.kind,
            source=InjurySource(self.source),
            occurred_on=self.occurred_on,
            base_weeks=self.base_weeks,
            return_date=self.return_date,
            protocol=Protocol(self.protocol),
            protocol_chosen=self.protocol_chosen,
            relapse=self.relapse,
            relapse_risk=self.relapse_risk,
        )

    @classmethod
    def from_domain(cls, injury: Injury) -> "InjuryRow":
        return cls(
            id=injury.id,
            player_id=injury.player_id,
            severity=injury.severity.value,
            kind=injury.kind,
            source=injury.source.value,
            occurred_on=injury.occurred_on,
            base_weeks=injury.base_weeks,
            return_date=injury.return_date,
            protocol=injury.protocol.value,
            protocol_chosen=injury.protocol_chosen,
            relapse=injury.relapse,
            relapse_risk=injury.relapse_risk,
        )

    def update_from(self, injury: Injury) -> None:
        """Recopie les champs qui changent avec le protocole."""
        self.protocol = injury.protocol.value
        self.protocol_chosen = injury.protocol_chosen
        self.return_date = injury.return_date
        self.relapse_risk = injury.relapse_risk


class StaffRow(Base):
    __tablename__ = "staff"

    id: Mapped[int] = mapped_column(primary_key=True)
    first_name: Mapped[str] = mapped_column(String(50))
    last_name: Mapped[str] = mapped_column(String(50))
    role: Mapped[str] = mapped_column(String(20))
    level: Mapped[int]
    wage: Mapped[int]
    # NULL = disponible sur le marché.
    club_id: Mapped[int | None] = mapped_column(ForeignKey("clubs.id"))

    club: Mapped[ClubRow | None] = relationship(back_populates="staff")

    def to_domain(self) -> StaffMember:
        return StaffMember(
            id=self.id,
            first_name=self.first_name,
            last_name=self.last_name,
            role=StaffRole(self.role),
            level=self.level,
            wage=self.wage,
            club_id=self.club_id,
        )

    @classmethod
    def from_domain(cls, member: StaffMember) -> "StaffRow":
        return cls(
            id=member.id,
            first_name=member.first_name,
            last_name=member.last_name,
            role=member.role.value,
            level=member.level,
            wage=member.wage,
            club_id=member.club_id,
        )


class SeasonRow(Base):
    __tablename__ = "seasons"

    id: Mapped[int] = mapped_column(primary_key=True)
    year: Mapped[int] = mapped_column(unique=True)

    # Le classement n'est pas stocké : il se recalcule à partir des matchs.
    matches: Mapped[list["MatchRow"]] = relationship(back_populates="season")


class MatchRow(Base):
    __tablename__ = "matches"

    id: Mapped[int] = mapped_column(primary_key=True)
    # Pas de saison pour un match amical.
    season_id: Mapped[int | None] = mapped_column(ForeignKey("seasons.id"))
    matchday: Mapped[int] = mapped_column(default=0)
    home_club_id: Mapped[int] = mapped_column(ForeignKey("clubs.id"))
    away_club_id: Mapped[int] = mapped_column(ForeignKey("clubs.id"))
    home_score: Mapped[int | None]
    away_score: Mapped[int | None]
    stage: Mapped[str] = mapped_column(String(10), default=Stage.REGULAR.value)
    date: Mapped[datetime.date | None] = mapped_column(Date)
    neutral: Mapped[bool] = mapped_column(default=False)
    # Événements stockés en JSON : suffisant tant qu'on ne fait pas de requêtes dessus.
    events: Mapped[list[dict]] = mapped_column(JSON, default=list)

    season: Mapped[SeasonRow | None] = relationship(back_populates="matches")

    @property
    def is_played(self) -> bool:
        return self.home_score is not None

    def to_domain(self) -> Match:
        return Match(
            id=self.id,
            home_club_id=self.home_club_id,
            away_club_id=self.away_club_id,
            matchday=self.matchday,
            home_score=self.home_score,
            away_score=self.away_score,
            stage=Stage(self.stage),
            date=self.date,
            neutral=self.neutral,
            events=[
                MatchEvent(
                    minute=e["minute"],
                    type=EventType(e["type"]),
                    club_id=e["club_id"],
                    player_id=e.get("player_id"),
                )
                for e in self.events
            ],
        )

    @classmethod
    def from_domain(cls, match: Match, season_id: int | None = None) -> "MatchRow":
        return cls(
            id=match.id,
            season_id=season_id,
            matchday=match.matchday,
            home_club_id=match.home_club_id,
            away_club_id=match.away_club_id,
            home_score=match.home_score,
            away_score=match.away_score,
            stage=match.stage.value,
            date=match.date,
            neutral=match.neutral,
            events=[
                {
                    "minute": e.minute,
                    "type": e.type.value,
                    "club_id": e.club_id,
                    "player_id": e.player_id,
                }
                for e in match.events
            ],
        )


class CareerRow(Base):
    """Partie sauvegardée : le club dirigé par le joueur."""

    __tablename__ = "careers"

    id: Mapped[int] = mapped_column(primary_key=True)
    manager_name: Mapped[str] = mapped_column(String(100))
    club_id: Mapped[int] = mapped_column(ForeignKey("clubs.id"))

    def to_domain(self) -> Career:
        return Career(id=self.id, manager_name=self.manager_name, club_id=self.club_id)

    @classmethod
    def from_domain(cls, career: Career) -> "CareerRow":
        return cls(id=career.id, manager_name=career.manager_name, club_id=career.club_id)


class TransactionRow(Base):
    """Une opération financière d'un club (voir api/ledger.py)."""

    __tablename__ = "transactions"

    id: Mapped[int] = mapped_column(primary_key=True)
    club_id: Mapped[int] = mapped_column(ForeignKey("clubs.id"))
    date: Mapped[datetime.date] = mapped_column(Date)
    matchday: Mapped[int | None]  # journée concernée, s'il y en a une
    category: Mapped[str] = mapped_column(String(20))
    label: Mapped[str] = mapped_column(String(200))
    amount: Mapped[int]  # positif = recette, négatif = dépense
    balance_after: Mapped[int]
