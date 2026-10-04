"""Tables SQLAlchemy et conversion vers/depuis les objets du domaine.

Le moteur ne voit jamais ces classes : l'API charge des lignes, les convertit
avec `to_domain()`, appelle le moteur, puis sauvegarde le résultat.
"""

from sqlalchemy import JSON, ForeignKey, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from models.domain import Club, EventType, Match, MatchEvent, Player, Position


class Base(DeclarativeBase):
    pass


class ClubRow(Base):
    __tablename__ = "clubs"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True)

    players: Mapped[list["PlayerRow"]] = relationship(back_populates="club")

    def to_domain(self) -> Club:
        return Club(id=self.id, name=self.name, players=[p.to_domain() for p in self.players])

    @classmethod
    def from_domain(cls, club: Club) -> "ClubRow":
        return cls(
            id=club.id,
            name=club.name,
            players=[PlayerRow.from_domain(p) for p in club.players],
        )


class PlayerRow(Base):
    __tablename__ = "players"

    id: Mapped[int] = mapped_column(primary_key=True)
    first_name: Mapped[str] = mapped_column(String(50))
    last_name: Mapped[str] = mapped_column(String(50))
    age: Mapped[int]
    position: Mapped[str] = mapped_column(String(3))
    pace: Mapped[int]
    technique: Mapped[int]
    passing: Mapped[int]
    shooting: Mapped[int]
    defending: Mapped[int]
    physical: Mapped[int]
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
            technique=self.technique,
            passing=self.passing,
            shooting=self.shooting,
            defending=self.defending,
            physical=self.physical,
            club_id=self.club_id,
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
            **player.attributes,
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
    home_goals: Mapped[int | None]
    away_goals: Mapped[int | None]
    # Événements stockés en JSON : suffisant tant qu'on ne fait pas de requêtes dessus.
    events: Mapped[list[dict]] = mapped_column(JSON, default=list)

    season: Mapped[SeasonRow | None] = relationship(back_populates="matches")

    def to_domain(self) -> Match:
        return Match(
            id=self.id,
            home_club_id=self.home_club_id,
            away_club_id=self.away_club_id,
            matchday=self.matchday,
            home_goals=self.home_goals,
            away_goals=self.away_goals,
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
            home_goals=match.home_goals,
            away_goals=match.away_goals,
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
