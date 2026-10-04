"""Formats des requêtes et réponses de l'API (modèles Pydantic).

Ils sont séparés des objets du domaine : on choisit ce qu'on expose au frontend
sans contraindre le moteur.
"""

from pydantic import BaseModel, ConfigDict, Field

from engine.match_engine import TeamStrength
from models import EventType, Match, Position

# --- Clubs et joueurs ----------------------------------------------------------------


class PlayerOut(BaseModel):
    # Permet de construire le schéma directement depuis un `Player` du domaine.
    model_config = ConfigDict(from_attributes=True)

    id: int
    first_name: str
    last_name: str
    name: str
    age: int
    position: Position
    pace: int
    power: int
    handling: int
    passing: int
    kicking: int
    tackling: int
    scrum: int
    lineout: int
    overall: float


class StrengthOut(BaseModel):
    """Notes collectives sur 20, calculées par le moteur sur le XV de départ."""

    set_piece: float
    pack: float
    attack: float
    defense: float
    kicking: int
    kicker_id: int
    lineup_ids: list[int]

    @classmethod
    def from_team(cls, team: TeamStrength) -> "StrengthOut":
        return cls(
            set_piece=round(team.set_piece, 1),
            pack=round(team.pack, 1),
            attack=round(team.attack, 1),
            defense=round(team.defense, 1),
            kicking=team.kicker.kicking,
            kicker_id=team.kicker.id,
            lineup_ids=[p.id for p in team.lineup],
        )


class ClubSummary(BaseModel):
    id: int
    name: str
    player_count: int
    # Moyenne des 4 notes collectives : un indicateur rapide du niveau.
    level: float


class ClubDetail(BaseModel):
    id: int
    name: str
    strength: StrengthOut
    players: list[PlayerOut]


# --- Matchs --------------------------------------------------------------------------


class SimulateMatchIn(BaseModel):
    home_club_id: int
    away_club_id: int
    # Graine optionnelle pour rejouer exactement le même match.
    seed: int | None = None


class MatchEventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    minute: int
    type: EventType
    club_id: int
    player_id: int | None
    points: int


class MatchOut(BaseModel):
    home_club_id: int
    away_club_id: int
    matchday: int
    home_score: int
    away_score: int
    home_tries: int
    away_tries: int
    events: list[MatchEventOut]

    @classmethod
    def from_match(cls, match: Match) -> "MatchOut":
        return cls(
            home_club_id=match.home_club_id,
            away_club_id=match.away_club_id,
            matchday=match.matchday,
            home_score=match.home_score,
            away_score=match.away_score,
            home_tries=match.tries_for(match.home_club_id),
            away_tries=match.tries_for(match.away_club_id),
            events=[MatchEventOut.model_validate(e) for e in match.events],
        )


# --- Carrière ------------------------------------------------------------------------


class CareerIn(BaseModel):
    manager_name: str = Field(min_length=1, max_length=100)
    club_id: int


class CareerOut(BaseModel):
    id: int
    manager_name: str
    club_id: int
    club_name: str


# --- Saisons -------------------------------------------------------------------------


class SeasonIn(BaseModel):
    year: int
    seed: int | None = None


class StandingOut(BaseModel):
    rank: int
    club_id: int
    club_name: str
    played: int
    won: int
    drawn: int
    lost: int
    points_for: int
    points_against: int
    points_difference: int
    tries_for: int
    offensive_bonus: int
    defensive_bonus: int
    league_points: int


class SeasonOut(BaseModel):
    year: int
    matchdays: int
    standings: list[StandingOut]
