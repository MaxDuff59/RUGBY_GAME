"""Objets du domaine : simples dataclasses, sans aucune dépendance externe.

Ce sont ces objets que manipule le moteur de simulation. La base de données
(voir `orm.py`) n'est qu'un moyen de les sauvegarder et de les recharger.
"""

from dataclasses import dataclass, field
from enum import StrEnum

# Bornes des attributs d'un joueur (échelle façon Football Manager).
ATTRIBUTE_MIN = 1
ATTRIBUTE_MAX = 20

# Noms des 6 attributs, dans un ordre fixe (pratique pour boucler dessus).
ATTRIBUTE_NAMES = ("pace", "technique", "passing", "shooting", "defending", "physical")


class Position(StrEnum):
    """Poste d'un joueur."""

    GK = "GK"  # gardien
    DEF = "DEF"  # défenseur
    MID = "MID"  # milieu
    FWD = "FWD"  # attaquant


@dataclass
class Player:
    id: int
    first_name: str
    last_name: str
    age: int
    position: Position
    pace: int
    technique: int
    passing: int
    shooting: int
    defending: int
    physical: int
    # Référence au club par identifiant (évite une référence circulaire Club <-> Player).
    club_id: int | None = None

    def __post_init__(self) -> None:
        # On refuse tout attribut hors de l'échelle 1-20 dès la création.
        for name in ATTRIBUTE_NAMES:
            value = getattr(self, name)
            if not ATTRIBUTE_MIN <= value <= ATTRIBUTE_MAX:
                raise ValueError(f"{name}={value} hors bornes [{ATTRIBUTE_MIN}, {ATTRIBUTE_MAX}]")

    @property
    def name(self) -> str:
        return f"{self.first_name} {self.last_name}"

    @property
    def attributes(self) -> dict[str, int]:
        """Les 6 attributs sous forme de dictionnaire."""
        return {name: getattr(self, name) for name in ATTRIBUTE_NAMES}

    @property
    def overall(self) -> float:
        """Note générale simple : moyenne des 6 attributs.

        Volontairement naïf : le moteur calculera ses propres notes par ligne.
        """
        return sum(self.attributes.values()) / len(ATTRIBUTE_NAMES)


@dataclass
class Club:
    id: int
    name: str
    players: list[Player] = field(default_factory=list)

    def players_at(self, position: Position) -> list[Player]:
        """Joueurs de l'effectif à un poste donné."""
        return [p for p in self.players if p.position == position]


class EventType(StrEnum):
    """Type d'événement survenu pendant un match."""

    GOAL = "goal"
    SHOT_SAVED = "shot_saved"
    SHOT_MISSED = "shot_missed"


@dataclass
class MatchEvent:
    minute: int
    type: EventType
    club_id: int
    player_id: int | None = None


@dataclass
class Match:
    home_club_id: int
    away_club_id: int
    matchday: int = 0  # numéro de journée dans la saison (0 = match amical)
    # Scores à None tant que le match n'est pas joué.
    home_goals: int | None = None
    away_goals: int | None = None
    events: list[MatchEvent] = field(default_factory=list)
    id: int | None = None

    @property
    def is_played(self) -> bool:
        return self.home_goals is not None and self.away_goals is not None

    @property
    def scorers(self) -> list[MatchEvent]:
        return [e for e in self.events if e.type == EventType.GOAL]


@dataclass
class StandingRow:
    """Ligne du classement pour un club."""

    club_id: int
    played: int = 0
    won: int = 0
    drawn: int = 0
    lost: int = 0
    goals_for: int = 0
    goals_against: int = 0

    @property
    def points(self) -> int:
        return 3 * self.won + self.drawn

    @property
    def goal_difference(self) -> int:
        return self.goals_for - self.goals_against

    def record(self, scored: int, conceded: int) -> None:
        """Enregistre le résultat d'un match du point de vue de ce club."""
        self.played += 1
        self.goals_for += scored
        self.goals_against += conceded
        if scored > conceded:
            self.won += 1
        elif scored == conceded:
            self.drawn += 1
        else:
            self.lost += 1


@dataclass
class Season:
    year: int
    clubs: list[Club]
    matches: list[Match] = field(default_factory=list)
    standings: dict[int, StandingRow] = field(default_factory=dict)

    def __post_init__(self) -> None:
        # Chaque club démarre avec une ligne de classement vide.
        for club in self.clubs:
            self.standings.setdefault(club.id, StandingRow(club_id=club.id))

    def table(self) -> list[StandingRow]:
        """Classement trié : points, puis différence de buts, puis buts marqués."""
        return sorted(
            self.standings.values(),
            key=lambda r: (r.points, r.goal_difference, r.goals_for),
            reverse=True,
        )
