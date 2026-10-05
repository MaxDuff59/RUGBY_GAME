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

# Noms des 9 attributs, dans un ordre fixe (pratique pour boucler dessus).
ATTRIBUTE_NAMES = (
    "pace",  # vitesse
    "power",  # puissance, impact dans les contacts
    "handling",  # jeu à la main, réception
    "passing",  # qualité de passe
    "kicking",  # jeu au pied, buteur
    "tackling",  # plaquage
    "scrum",  # mêlée
    "lineout",  # touche (lancer, saut, soutien)
    "stamina",  # endurance : l'énergie tient plus longtemps pendant un match
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


class Squad(StrEnum):
    """Groupe auquel appartient un joueur : effectif pro ou centre de formation."""

    PRO = "pro"
    YOUTH = "youth"  # espoirs


# Âge maximal pour redescendre un pro chez les espoirs, et pour y rester.
YOUTH_MAX_AGE = 23
YOUTH_EXIT_AGE = 22  # un espoir non promu à cet âge quitte le centre


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
    stamina: int
    # Référence au club par identifiant (évite une référence circulaire Club <-> Player).
    club_id: int | None = None
    # Salaire par saison, en euros (fixé au contrat ; la valeur marchande, elle,
    # se calcule : voir engine/economy.py).
    wage: int = 0
    # Blessure la plus récente (en cours ou guérie), None s'il n'en a jamais eu.
    injury: Injury | None = None
    # Année de la dernière saison sous contrat (2026 = jusqu'à la fin de 2026-27).
    contract_until: int = 0
    # Club propriétaire quand le joueur est prêté (None sinon) ; il y retourne à l'intersaison.
    loaned_from: int | None = None
    squad: Squad = Squad.PRO

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

    def years_left(self, season_year: int) -> int:
        """Saisons de contrat restantes, celle en cours comprise (1 = dernière année)."""
        return max(1, self.contract_until - season_year + 1)

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


class StandSide(StrEnum):
    """Les quatre tribunes du stade."""

    NORTH = "north"
    SOUTH = "south"
    EAST = "east"
    WEST = "west"


class AmenityKind(StrEnum):
    """Ce qu'on peut installer dans une tribune (coûts et effets : engine/economy.py)."""

    SPONSOR = "sponsor"  # panneau publicitaire
    BUVETTE = "buvette"
    SHOP = "shop"  # boutique du club
    BOXES = "boxes"  # loges
    SCREEN = "screen"  # écran géant


@dataclass
class Facilities:
    """Infrastructures du club. Les paliers et coûts sont dans engine/economy.py."""

    stadium_capacity: int = 4000
    training_level: int = 1  # centre d'entraînement, de 1 à 5
    academy_level: int = 1  # centre de formation, de 1 à 5
    # Aménagements installés, tribune par tribune (une tribune absente = vide).
    stands: dict[StandSide, list[AmenityKind]] = field(default_factory=dict)

    def amenities(self, side: StandSide) -> list[AmenityKind]:
        return self.stands.setdefault(side, [])


@dataclass
class Club:
    id: int
    name: str
    players: list[Player] = field(default_factory=list)  # effectif pro
    staff: list[StaffMember] = field(default_factory=list)
    balance: int = 0  # trésorerie, en euros
    facilities: Facilities = field(default_factory=Facilities)
    youths: list[Player] = field(default_factory=list)  # espoirs du centre de formation
    league: str = "top14"  # code du championnat (data/leagues.py)
    # Titularisations promises par le manager (engine/affairs.py) : non stocké, posé par l'API.
    forced_starters: set[int] = field(default_factory=set)

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
        """Masse salariale des joueurs pros, par saison."""
        return sum(p.wage for p in self.players)

    @property
    def youth_wages(self) -> int:
        return sum(p.wage for p in self.youths)

    def youth_team(self) -> "Club":
        """Les espoirs vus comme une équipe, pour les faire jouer avec le moteur."""
        return Club(id=self.id, name=self.name, players=self.youths, facilities=self.facilities)

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
    YELLOW_CARD = "yellow_card"  # 10 minutes sur le banc des pénalités
    RED_CARD = "red_card"  # exclusion définitive
    # Remplacement : `player_id` sort, `other_player_id` entre.
    SUBSTITUTION = "substitution"
    # Tirs au but d'une phase finale restée à égalité après prolongation : ils
    # départagent les deux clubs sans changer le score.
    SHOOTOUT_GOAL = "shootout_goal"
    SHOOTOUT_MISSED = "shootout_missed"


# Points rapportés par chaque type d'événement (0 pour les tentatives manquées).
EVENT_POINTS = {
    EventType.TRY: 5,
    EventType.CONVERSION: 2,
    EventType.CONVERSION_MISSED: 0,
    EventType.PENALTY_GOAL: 3,
    EventType.PENALTY_MISSED: 0,
    EventType.DROP_GOAL: 3,
    EventType.INJURY: 0,
    EventType.YELLOW_CARD: 0,
    EventType.RED_CARD: 0,
    EventType.SUBSTITUTION: 0,
    EventType.SHOOTOUT_GOAL: 0,
    EventType.SHOOTOUT_MISSED: 0,
}

# Temps réglementaire, puis prolongation (2 x 10 minutes) en phase finale.
REGULATION_MINUTES = 80
EXTRA_TIME_MINUTES = 20

_SHOOTOUT = {EventType.SHOOTOUT_GOAL, EventType.SHOOTOUT_MISSED}


@dataclass
class MatchEvent:
    minute: int
    type: EventType
    club_id: int
    player_id: int | None = None
    # Second joueur concerné : le remplaçant qui entre (`SUBSTITUTION`).
    other_player_id: int | None = None

    @property
    def points(self) -> int:
        return EVENT_POINTS[self.type]


class Stage(StrEnum):
    """Étape de la saison à laquelle appartient un match."""

    REGULAR = "regular"  # saison régulière
    QUARTER = "quarter"  # quarts de finale (URC), matchs de qualification (Super Rugby)
    BARRAGE = "barrage"  # barrages (3e-6e, 4e-5e)
    SEMI = "semi"  # demi-finales
    FINAL = "final"  # finale, sur terrain neutre ou chez le mieux classé selon le championnat

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
    # XV de départ de chaque club (identifiants), remplis quand le match est joué.
    home_lineup: list[int] = field(default_factory=list)
    away_lineup: list[int] = field(default_factory=list)

    def played_by(self, player_id: int) -> bool:
        return player_id in self.home_lineup or player_id in self.away_lineup

    @property
    def is_played(self) -> bool:
        return self.home_score is not None and self.away_score is not None

    @property
    def went_to_extra_time(self) -> bool:
        """Une prolongation a été jouée (des points marqués, ou des tirs au but)."""
        return any(e.minute > REGULATION_MINUTES or e.type in _SHOOTOUT for e in self.events)

    @property
    def went_to_shootout(self) -> bool:
        return any(e.type in _SHOOTOUT for e in self.events)

    def shootout_for(self, club_id: int) -> int:
        """Tirs au but réussis par un club (0 sans séance)."""
        return sum(
            1 for e in self.events if e.club_id == club_id and e.type == EventType.SHOOTOUT_GOAL
        )

    def result_for(self, club_id: int) -> int:
        """1 victoire, 0 nul, -1 défaite : les tirs au but départagent un nul."""
        home = club_id == self.home_club_id
        other = self.away_club_id if home else self.home_club_id
        diff = (self.home_score - self.away_score) * (1 if home else -1)
        if diff == 0:
            diff = self.shootout_for(club_id) - self.shootout_for(other)
        return (diff > 0) - (diff < 0)

    def winner_id(self, seeding: list[int]) -> int:
        """Vainqueur d'un match de phase finale : au score, sinon aux tirs au but.

        Un match sans séance resté à égalité (joué avant les prolongations) revient
        au mieux classé en saison régulière (`seeding`, du 1er au dernier).
        """
        if not self.is_played:
            raise ValueError("Le match n'a pas encore été joué")
        result = self.result_for(self.home_club_id)
        if result != 0:
            return self.home_club_id if result > 0 else self.away_club_id
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
