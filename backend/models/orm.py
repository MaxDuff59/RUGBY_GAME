"""Tables SQLAlchemy et conversion vers/depuis les objets du domaine.

Le moteur ne voit jamais ces classes : l'API charge des lignes, les convertit
avec `to_domain()`, appelle le moteur, puis sauvegarde le résultat.
"""

from sqlalchemy import JSON, ForeignKey, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from models.domain import (
    Career,
    Club,
    EventType,
    Facilities,
    Match,
    MatchEvent,
    Player,
    Position,
    StaffMember,
    StaffRole,
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

    def to_domain(self) -> Player:
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
    # Événements stockés en JSON : suffisant tant qu'on ne fait pas de requêtes dessus.
    events: Mapped[list[dict]] = mapped_column(JSON, default=list)

    season: Mapped[SeasonRow | None] = relationship(back_populates="matches")

    def to_domain(self) -> Match:
        return Match(
            id=self.id,
            home_club_id=self.home_club_id,
            away_club_id=self.away_club_id,
            matchday=self.matchday,
            home_score=self.home_score,
            away_score=self.away_score,
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
