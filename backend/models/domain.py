"""Objets du domaine : simples dataclasses, sans aucune dépendance externe.

Ce sont ces objets que manipule le moteur de simulation. La base de données
(voir `orm.py`) n'est qu'un moyen de les sauvegarder et de les recharger.
"""

from dataclasses import dataclass, field
from enum import StrEnum

# Bornes des attributs d'un joueur (échelle façon Football Manager).
ATTRIBUTE_MIN = 1
ATTRIBUTE_MAX = 20

# Noms des 8 attributs, dans un ordre fixe (pratique pour boucler dessus).
ATTRIBUTE_NAMES = (
    "pace",  # vitesse
    "power",  # puissance, impact dans les contacts
    "handling",  # jeu à la main, réception
    "passing",  # qualité de passe
    "kicking",  # jeu au pied, buteur
    "tackling",  # plaquage
    "scrum",  # mêlée
    "lineout",  # touche (lancer, saut, soutien)
)


class Position(StrEnum):
    """Poste d'un joueur de rugby à XV."""

    PROP = "PROP"  # pilier
    HOOKER = "HOOKER"  # talonneur
    LOCK = "LOCK"  # deuxième ligne
    BACK_ROW = "BACK_ROW"  # troisième ligne (flanker ou numéro 8)
    SCRUM_HALF = "SCRUM_HALF"  # demi de mêlée
    FLY_HALF = "FLY_HALF"  # demi d'ouverture
    CENTRE = "CENTRE"  # centre
    WING = "WING"  # ailier
    FULLBACK = "FULLBACK"  # arrière

    @property
    def is_forward(self) -> bool:
        """Vrai pour les avants (numéros 1 à 8)."""
        return self in FORWARDS


FORWARDS = frozenset({Position.PROP, Position.HOOKER, Position.LOCK, Position.BACK_ROW})


@dataclass
class Player:
    id: int
    first_name: str
    last_name: str
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
        """Les 8 attributs sous forme de dictionnaire."""
        return {name: getattr(self, name) for name in ATTRIBUTE_NAMES}

    @property
    def overall(self) -> float:
        """Note générale simple : moyenne des attributs.

        Volontairement naïve (un pilier n'a pas besoin de jeu au pied) : le
        moteur calcule ses propres notes selon le poste.
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

    TRY = "try"  # essai
    CONVERSION = "conversion"  # transformation réussie
    CONVERSION_MISSED = "conversion_missed"
    PENALTY_GOAL = "penalty_goal"  # pénalité réussie
    PENALTY_MISSED = "penalty_missed"
    DROP_GOAL = "drop_goal"  # drop réussi


# Points rapportés par chaque type d'événement (0 pour les tentatives manquées).
EVENT_POINTS = {
    EventType.TRY: 5,
    EventType.CONVERSION: 2,
    EventType.CONVERSION_MISSED: 0,
    EventType.PENALTY_GOAL: 3,
    EventType.PENALTY_MISSED: 0,
    EventType.DROP_GOAL: 3,
}


@dataclass
class MatchEvent:
    minute: int
    type: EventType
    club_id: int
    player_id: int | None = None

    @property
    def points(self) -> int:
        return EVENT_POINTS[self.type]


@dataclass
class Match:
    home_club_id: int
    away_club_id: int
    matchday: int = 0  # numéro de journée dans la saison (0 = match amical)
    # Scores à None tant que le match n'est pas joué.
    home_score: int | None = None
    away_score: int | None = None
    events: list[MatchEvent] = field(default_factory=list)
    id: int | None = None

    @property
    def is_played(self) -> bool:
        return self.home_score is not None and self.away_score is not None

    def points_for(self, club_id: int) -> int:
        """Points marqués par un club, recalculés à partir des événements."""
        return sum(e.points for e in self.events if e.club_id == club_id)

    def tries_for(self, club_id: int) -> int:
        return sum(1 for e in self.events if e.club_id == club_id and e.type == EventType.TRY)

    @property
    def try_scorers(self) -> list[MatchEvent]:
        return [e for e in self.events if e.type == EventType.TRY]


# --- Classement (règles du Top 14) ----------------------------------------------------

POINTS_WIN = 4
POINTS_DRAW = 2
# Bonus offensif : victoire avec au moins 3 essais de plus que l'adversaire.
OFFENSIVE_BONUS_TRY_MARGIN = 3
# Bonus défensif : défaite de 5 points ou moins.
DEFENSIVE_BONUS_MAX_GAP = 5


@dataclass
class StandingRow:
    """Ligne du classement pour un club."""

    club_id: int
    played: int = 0
    won: int = 0
    drawn: int = 0
    lost: int = 0
    points_for: int = 0
    points_against: int = 0
    tries_for: int = 0
    tries_against: int = 0
    offensive_bonus: int = 0
    defensive_bonus: int = 0

    @property
    def league_points(self) -> int:
        """Points au classement (à ne pas confondre avec les points marqués)."""
        return (
            POINTS_WIN * self.won
            + POINTS_DRAW * self.drawn
            + self.offensive_bonus
            + self.defensive_bonus
        )

    @property
    def points_difference(self) -> int:
        return self.points_for - self.points_against

    def record(self, scored: int, conceded: int, tries: int, tries_conceded: int) -> None:
        """Enregistre le résultat d'un match du point de vue de ce club."""
        self.played += 1
        self.points_for += scored
        self.points_against += conceded
        self.tries_for += tries
        self.tries_against += tries_conceded

        if scored > conceded:
            self.won += 1
            if tries - tries_conceded >= OFFENSIVE_BONUS_TRY_MARGIN:
                self.offensive_bonus += 1
        elif scored == conceded:
            self.drawn += 1
        else:
            self.lost += 1
            if conceded - scored <= DEFENSIVE_BONUS_MAX_GAP:
                self.defensive_bonus += 1


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
        """Classement trié : points, puis différence de points, puis essais marqués."""
        return sorted(
            self.standings.values(),
            key=lambda r: (r.league_points, r.points_difference, r.tries_for),
            reverse=True,
        )


# --- Carrière du joueur --------------------------------------------------------------


@dataclass
class Career:
    """La partie du joueur : le manager qu'il incarne et le club qu'il dirige."""

    manager_name: str
    club_id: int
    id: int | None = None
