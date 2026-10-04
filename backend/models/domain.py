"""Objets du domaine : simples dataclasses, sans aucune dépendance externe.

Ce sont ces objets que manipule le moteur de simulation. La base de données
(voir `orm.py`) n'est qu'un moyen de les sauvegarder et de les recharger.
"""

import datetime
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


# --- Blessures -----------------------------------------------------------------------


class InjurySeverity(StrEnum):
    LIGHT = "light"  # légère : quelques semaines
    MODERATE = "moderate"  # modérée : un à deux mois
    SEVERE = "severe"  # grave : plusieurs mois


class InjurySource(StrEnum):
    MATCH = "match"
    TRAINING = "training"


class Protocol(StrEnum):
    """Protocole de soins choisi par le manager (les règles sont dans engine/medical.py)."""

    CAUTIOUS = "cautious"  # prudent : plus long, rechute rare
    STANDARD = "standard"  # normal
    ACCELERATED = "accelerated"  # accéléré : retour anticipé, rechute fréquente, coûteux


# Après son retour, un joueur reste fragile pendant quelques semaines.
FRAGILE_WEEKS = 4


@dataclass
class Injury:
    """Une blessure d'un joueur, en cours ou passée.

    Les dates font foi : le joueur est indisponible tant que `return_date` n'est
    pas atteinte, puis fragile (risque de rechute) jusqu'à `fragile_until`.
    """

    player_id: int
    severity: InjurySeverity
    kind: str  # ex. « entorse de la cheville »
    source: InjurySource
    occurred_on: datetime.date
    base_weeks: int  # durée médicale, avant protocole et staff
    return_date: datetime.date
    protocol: Protocol = Protocol.STANDARD
    protocol_chosen: bool = True  # False tant que le manager n'a pas tranché
    relapse: bool = False  # rechute d'une blessure précédente
    relapse_risk: float = 0.0  # probabilité de rechute par match, une fois revenu
    id: int | None = None

    @property
    def fragile_until(self) -> datetime.date:
        return self.return_date + datetime.timedelta(weeks=FRAGILE_WEEKS)

    def is_active(self, day: datetime.date) -> bool:
        return day < self.return_date

    def is_fragile(self, day: datetime.date) -> bool:
        return self.return_date <= day < self.fragile_until

    def weeks_left(self, day: datetime.date) -> int:
        """Semaines d'indisponibilité restantes (0 si le joueur est revenu)."""
        return max(0, -(-(self.return_date - day).days // 7))


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
    # Salaire par saison, en euros (fixé au contrat ; la valeur marchande, elle,
    # se calcule : voir engine/economy.py).
    wage: int = 0
    # Blessure la plus récente (en cours ou guérie), None s'il n'en a jamais eu.
    injury: Injury | None = None

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

    def is_injured(self, day: datetime.date | None) -> bool:
        """Indisponible à cette date (sans date, on ignore les blessures)."""
        return day is not None and self.injury is not None and self.injury.is_active(day)

    def is_fragile(self, day: datetime.date | None) -> bool:
        """Revenu de blessure depuis peu : risque de rechute."""
        return day is not None and self.injury is not None and self.injury.is_fragile(day)


class StaffRole(StrEnum):
    """Postes du staff autour de l'entraîneur principal (le joueur)."""

    FORWARDS_COACH = "FORWARDS_COACH"  # entraîneur des avants (mêlée, touche)
    ATTACK_COACH = "ATTACK_COACH"  # entraîneur de l'attaque
    DEFENCE_COACH = "DEFENCE_COACH"  # entraîneur de la défense
    KICKING_COACH = "KICKING_COACH"  # entraîneur du jeu au pied
    FITNESS_COACH = "FITNESS_COACH"  # préparateur physique
    ANALYST = "ANALYST"  # analyste vidéo
    PHYSIO = "PHYSIO"  # kinésithérapeute
    DOCTOR = "DOCTOR"  # médecin


STAFF_LEVEL_MIN = 1
STAFF_LEVEL_MAX = 5


@dataclass
class StaffMember:
    id: int
    first_name: str
    last_name: str
    role: StaffRole
    level: int  # de 1 à 5 étoiles
    wage: int  # par saison, en euros
    club_id: int | None = None  # None = disponible sur le marché

    def __post_init__(self) -> None:
        if not STAFF_LEVEL_MIN <= self.level <= STAFF_LEVEL_MAX:
            raise ValueError(f"level={self.level} hors bornes [1, 5]")

    @property
    def name(self) -> str:
        return f"{self.first_name} {self.last_name}"


@dataclass
class Facilities:
    """Infrastructures du club. Les paliers et coûts sont dans engine/economy.py."""

    stadium_capacity: int = 4000
    training_level: int = 1  # centre d'entraînement, de 1 à 5
    academy_level: int = 1  # centre de formation, de 1 à 5


@dataclass
class Club:
    id: int
    name: str
    players: list[Player] = field(default_factory=list)
    staff: list[StaffMember] = field(default_factory=list)
    balance: int = 0  # trésorerie, en euros
    facilities: Facilities = field(default_factory=Facilities)

    def players_at(self, position: Position) -> list[Player]:
        """Joueurs de l'effectif à un poste donné."""
        return [p for p in self.players if p.position == position]

    def available_players(self, day: datetime.date | None) -> list[Player]:
        """Joueurs aptes à jouer à cette date (les blessés sont exclus)."""
        return [p for p in self.players if not p.is_injured(day)]

    def staff_level(self, role: StaffRole) -> int:
        """Niveau (1 à 5) du membre du staff à ce poste, 0 si le poste est vacant."""
        return next((s.level for s in self.staff if s.role == role), 0)

    @property
    def player_wages(self) -> int:
        """Masse salariale des joueurs, par saison."""
        return sum(p.wage for p in self.players)

    @property
    def staff_wages(self) -> int:
        return sum(s.wage for s in self.staff)


class EventType(StrEnum):
    """Type d'événement survenu pendant un match."""

    TRY = "try"  # essai
    CONVERSION = "conversion"  # transformation réussie
    CONVERSION_MISSED = "conversion_missed"
    PENALTY_GOAL = "penalty_goal"  # pénalité réussie
    PENALTY_MISSED = "penalty_missed"
    DROP_GOAL = "drop_goal"  # drop réussi
    INJURY = "injury"  # un joueur se blesse et quitte le terrain


# Points rapportés par chaque type d'événement (0 pour les tentatives manquées).
EVENT_POINTS = {
    EventType.TRY: 5,
    EventType.CONVERSION: 2,
    EventType.CONVERSION_MISSED: 0,
    EventType.PENALTY_GOAL: 3,
    EventType.PENALTY_MISSED: 0,
    EventType.DROP_GOAL: 3,
    EventType.INJURY: 0,
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


class Stage(StrEnum):
    """Étape de la saison à laquelle appartient un match."""

    REGULAR = "regular"  # saison régulière
    BARRAGE = "barrage"  # barrages (3e-6e, 4e-5e)
    SEMI = "semi"  # demi-finales
    FINAL = "final"  # finale, sur terrain neutre

    @property
    def is_playoff(self) -> bool:
        return self != Stage.REGULAR


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
    stage: Stage = Stage.REGULAR
    date: datetime.date | None = None
    neutral: bool = False  # terrain neutre : pas d'avantage du terrain

    @property
    def is_played(self) -> bool:
        return self.home_score is not None and self.away_score is not None

    def winner_id(self, seeding: list[int]) -> int:
        """Vainqueur d'un match de phase finale.

        En cas d'égalité, le mieux classé en saison régulière (`seeding`, du 1er
        au dernier) se qualifie.
        """
        if not self.is_played:
            raise ValueError("Le match n'a pas encore été joué")
        if self.home_score != self.away_score:
            return self.home_club_id if self.home_score > self.away_score else self.away_club_id
        return min(self.home_club_id, self.away_club_id, key=seeding.index)

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
