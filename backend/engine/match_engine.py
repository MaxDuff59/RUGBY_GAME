"""Moteur de match de rugby probabiliste, minute par minute.

Principe :
1. On choisit un XV de départ (2 piliers, 1 talonneur, 2 deuxième ligne,
   3 troisième ligne, 1 demi de mêlée, 1 ouvreur, 2 centres, 2 ailiers, 1 arrière)
   et un banc de 8 remplaçants.
2. On calcule des notes collectives : conquête (mêlée + touche), paquet d'avants,
   attaque des lignes arrières, défense, buteur. Elles se recalculent à chaque
   minute à partir des joueurs présents sur le terrain : l'énergie de chaque
   joueur baisse avec ses minutes de jeu, une équipe réduite (carton) perd de sa
   force, et la tactique
   choisie (`Tactics`) déplace le curseur entre occupation, jeu à la main et
   agressivité défensive.
3. Chaque minute, une action dangereuse peut survenir :
   - la conquête et le paquet décident quelle équipe a l'occasion (territoire) ;
   - l'attaque contre la défense décide s'il y a essai (+ transformation) ;
   - sinon la domination des avants peut provoquer une pénalité, tentée au pied
     ou jouée à la main selon la tactique ;
   - plus rarement, l'ouvreur tente un drop.
4. Chaque minute aussi, un joueur peut se blesser (événement `INJURY`, un
   remplaçant entre s'il en reste) ou prendre un carton (`YELLOW_CARD` : 10
   minutes à 14, `RED_CARD` : exclusion) qui donne une pénalité à l'adversaire.
   La blessure elle-même (gravité, durée) est tirée par `engine/medical.py`.
5. Chaque joueur reçoit une note sur 10 qui évolue avec le match : ses actions
   (essai, coup de pied, carton) et la domination de sa ligne.
6. La forme du jour (`engine/form.py` : moral, cohésion, fraîcheur) multiplie
   les notes collectives (et fixe l'énergie de départ de chaque joueur), et la
   fatigue augmente le risque de blessure.
7. En phase finale, une égalité après 80 minutes mène à une prolongation
   (2 x 10 minutes), puis si besoin à une séance de tirs au but.

`LiveMatch` joue le match minute par minute : on peut l'arrêter, changer la
tactique d'une équipe ou faire un remplacement, puis reprendre. `simulate_match`
joue tout d'une traite, le staff (IA) gérant les deux bancs.

Quand le match a une date, les joueurs blessés à cette date ne sont pas
alignés. Le moteur ne travaille que sur les objets de `models` : aucune
dépendance à FastAPI ni à la base de données.
"""

import datetime
import random
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from enum import StrEnum

from engine.form import NEUTRAL_FORM, Form
from engine.medical import MATCH_INJURY_CHANCE_PER_MINUTE
from models import (
    EXTRA_TIME_MINUTES,
    REGULATION_MINUTES,
    Club,
    EventType,
    Match,
    MatchEvent,
    Player,
    Position,
)

# Composition du XV de départ (à rendre configurable plus tard).
FORMATION = {
    Position.PROP: 2,
    Position.HOOKER: 1,
    Position.LOCK: 2,
    Position.BACK_ROW: 3,
    Position.SCRUM_HALF: 1,
    Position.FLY_HALF: 1,
    Position.CENTRE: 2,
    Position.WING: 2,
    Position.FULLBACK: 1,
}

# Les 15 places du terrain, dans l'ordre de FORMATION, et leur numéro de maillot.
SLOT_POSITIONS: tuple[Position, ...] = tuple(
    position for position, count in FORMATION.items() for _ in range(count)
)
SLOT_NUMBERS = (1, 3, 2, 4, 5, 6, 7, 8, 9, 10, 12, 13, 11, 14, 15)

# Le banc : 8 remplaçants, du 16 au 23. None = le meilleur arrière restant.
BENCH_FORMATION: tuple[Position | None, ...] = (
    Position.HOOKER,
    Position.PROP,
    Position.PROP,
    Position.LOCK,
    Position.BACK_ROW,
    Position.SCRUM_HALF,
    Position.FLY_HALF,
    None,
)
BENCH_SIZE = len(BENCH_FORMATION)
BACKS_FOR_BENCH = (Position.CENTRE, Position.WING, Position.FULLBACK)
MAX_SUBSTITUTIONS = 8

MATCH_MINUTES = REGULATION_MINUTES
HALF_TIME = MATCH_MINUTES // 2

# Probabilité qu'une action dangereuse survienne à une minute donnée.
CHANCE_PER_MINUTE = 0.28

# Entre deux équipes de même niveau, une action dangereuse donne :
TRY_RATE = 0.20  # un essai dans 20 % des cas
PENALTY_RATE = 0.26  # une pénalité tentée dans 26 % des cas (plus celles des cartons)
DROP_RATE = 0.02  # un drop réussi dans 2 % des cas
# ... et rien du tout (ballon perdu, en-avant...) le reste du temps.
# Calibrage (sur 4000 matchs simulés, cartons compris) : ~49 points et ~4,7 essais
# par match, ~60 % de victoires à domicile, ~2 % de nuls, proche du Top 14.

# Bonus multiplicatif sur le territoire de l'équipe à domicile
# (l'avantage du terrain est fort au rugby).
HOME_ADVANTAGE = 1.25

# Plus l'exposant est grand, plus l'écart de niveau pèse sur le résultat
# (1 = proportionnel, 2 = l'équipe forte écrase davantage).
# À 1.0, le meilleur club bat le plus faible ~95 % du temps à domicile.
STRENGTH_EXPONENT = 1.0

# Probabilité de réussir un coup de pied au but : 35 % + 3 % par point de kicking
# (kicking 10 => 65 %, 15 => 80 %, 20 => 95 %).
KICK_BASE = 0.35
KICK_PER_POINT = 0.03
# Une transformation se tente là où l'essai a été marqué, souvent excentrée.
CONVERSION_PENALTY = 0.05

# Tirs au but (règlement du Top 14) : 5 buteurs par équipe en alternance, depuis
# la ligne des 22 mètres, puis mort subite tant que l'égalité persiste.
SHOOTOUT_KICKERS = 5
# La pression de la séance coûte un peu de réussite par rapport à une pénalité.
SHOOTOUT_PRESSURE = 0.05

# Probabilité de marquer l'essai selon le poste (les ailiers finissent les actions).
TRY_SCORER_WEIGHT = {
    Position.PROP: 0.5,
    Position.HOOKER: 1.0,
    Position.LOCK: 0.5,
    Position.BACK_ROW: 2.0,
    Position.SCRUM_HALF: 1.5,
    Position.FLY_HALF: 1.0,
    Position.CENTRE: 2.5,
    Position.WING: 4.0,
    Position.FULLBACK: 2.5,
}

# --- Tactique ------------------------------------------------------------------------


class GamePlan(StrEnum):
    """Plan de jeu : où l'équipe cherche ses points."""

    KICKING = "kicking"  # occupation au pied : plus de territoire et de pénalités, moins d'essais
    BALANCED = "balanced"
    HANDS = "hands"  # jeu à la main : plus d'essais marqués... et encaissés


class Defence(StrEnum):
    """Agressivité défensive : une défense qui monte vite fait plus de fautes."""

    CAUTIOUS = "cautious"
    NORMAL = "normal"
    AGGRESSIVE = "aggressive"


class PenaltyChoice(StrEnum):
    """Que faire d'une pénalité en position : tenter les 3 points, ou jouer l'essai."""

    KICK = "kick"
    PLAY = "play"


@dataclass(frozen=True)
class Tactics:
    game_plan: GamePlan = GamePlan.BALANCED
    defence: Defence = Defence.NORMAL
    penalties: PenaltyChoice = PenaltyChoice.KICK

    def to_dict(self) -> dict[str, str]:
        return {
            "game_plan": self.game_plan.value,
            "defence": self.defence.value,
            "penalties": self.penalties.value,
        }

    @classmethod
    def from_dict(cls, data: dict[str, str]) -> "Tactics":
        return cls(
            game_plan=GamePlan(data.get("game_plan", GamePlan.BALANCED)),
            defence=Defence(data.get("defence", Defence.NORMAL)),
            penalties=PenaltyChoice(data.get("penalties", PenaltyChoice.KICK)),
        )


DEFAULT_TACTICS = Tactics()

# Effets du plan de jeu : sur le territoire, les essais tentés, les pénalités
# obtenues, et les essais que l'adversaire peut marquer (contre-attaques).
GAME_PLAN_EFFECTS = {
    GamePlan.KICKING: {"territory": 1.06, "tries": 0.82, "penalties": 1.10, "conceded": 0.92},
    GamePlan.BALANCED: {"territory": 1.0, "tries": 1.0, "penalties": 1.0, "conceded": 1.0},
    GamePlan.HANDS: {"territory": 0.96, "tries": 1.20, "penalties": 0.90, "conceded": 1.08},
}
# Effets de l'agressivité : sur la note de défense, les cartons, les pénalités
# concédées et l'énergie dépensée (une défense qui monte vite use plus).
DEFENCE_EFFECTS = {
    Defence.CAUTIOUS: {"defense": 0.93, "cards": 0.6, "fouls": 0.9, "effort": 1.0},
    Defence.NORMAL: {"defense": 1.0, "cards": 1.0, "fouls": 1.0, "effort": 1.0},
    Defence.AGGRESSIVE: {"defense": 1.10, "cards": 1.6, "fouls": 1.1, "effort": 1.1},
}
# Pénalité jouée à la main : chance d'essai entre équipes égales (contre 3 points
# quasi assurés au pied : le pari paie surtout quand l'attaque domine).
PLAY_PENALTY_TRY_RATE = 0.38

# --- Cartons ---------------------------------------------------------------------------

# Par équipe et par minute : ~0,3 carton jaune et ~0,03 rouge par équipe et par match.
YELLOW_CHANCE_PER_MINUTE = 0.004
RED_CHANCE_PER_MINUTE = 0.0004
SIN_BIN_MINUTES = 10
# Chaque joueur manquant coûte 12 % des notes collectives.
SHORT_HANDED_FACTOR = 0.88
# Les avants prennent plus de cartons (rucks, mêlées) que les arrières.
CARD_WEIGHT_FORWARD, CARD_WEIGHT_BACK = 2.0, 1.0

# --- Énergie et remplacements ------------------------------------------------------------

# Chaque joueur a une énergie de 0 à 1. Il commence le match entre 60 % (fraîcheur
# nulle, engine/freshness.py) et 100 % (tout frais), et en perd à chaque minute
# de jeu selon son endurance : 1,6 % moins 0,05 % par point (endurance 4 : 1,4 %,
# 12 : 1 %, 20 : 0,6 %). À la 80e, un titulaire parti à 100 % garde donc 0 %,
# 20 % ou 52 % selon qu'il est fragile, moyen ou increvable. Son apport aux
# notes collectives va de 100 % de ses moyens (énergie pleine) à 60 % (vide).
ENERGY_START_MIN = 0.6
ENERGY_DRAIN_BASE = 0.016
ENERGY_DRAIN_PER_STAMINA = 0.0005
EFFICIENCY_MIN = 0.60
# Les faits de jeu pèsent sur l'énergie : à 14 ou 13 (carton, blessé sans
# remplaçant), ceux qui restent couvrent plus de terrain et s'usent 25 % plus
# vite par joueur manquant. Un joueur au banc des pénalités, lui, souffle.
SHORT_HANDED_EFFORT = 0.25
# Le staff (IA) fait entrer un remplaçant à ces minutes, en gardant un
# changement en réserve pour une blessure.
AI_SUBSTITUTION_MINUTES = (50, 56, 62, 68, 74)
AI_SUBSTITUTIONS_KEPT = 1
# Il ne remplace pas un joueur entré depuis moins de 25 minutes.
AI_MIN_MINUTES_ON_FIELD = 25

# --- Notes des joueurs sur 10 ----------------------------------------------------------

RATING_START = 6.0
RATING_MIN, RATING_MAX = 1.0, 10.0
# Chaque minute, un joueur gagne ou perd selon la domination de sa ligne
# (avants : conquête et paquet ; arrières : attaque contre défense).
RATING_DRIFT_PER_MINUTE = 0.03
# ... plus une part de hasard propre à chacun (un bon ou un mauvais jour).
RATING_NOISE_PER_MINUTE = 0.03
RATING_EVENT = {
    EventType.TRY: 1.0,
    EventType.CONVERSION: 0.2,
    EventType.CONVERSION_MISSED: -0.2,
    EventType.PENALTY_GOAL: 0.3,
    EventType.PENALTY_MISSED: -0.3,
    EventType.DROP_GOAL: 0.5,
    EventType.YELLOW_CARD: -1.0,
    EventType.RED_CARD: -2.0,
    EventType.SHOOTOUT_GOAL: 0.3,
    EventType.SHOOTOUT_MISSED: -0.5,
}
# Un essai marque toute l'équipe : les attaquants présents gagnent, les défenseurs perdent.
RATING_TEAM_SCORED = 0.1
RATING_TEAM_CONCEDED = -0.15


# --- Notes des joueurs ---------------------------------------------------------------


def scrum_rating(p: Player) -> float:
    return 0.6 * p.scrum + 0.4 * p.power


def lineout_rating(p: Player) -> float:
    return 0.7 * p.lineout + 0.3 * p.power


def carrying_rating(p: Player) -> float:
    """Avancée dans les contacts et travail dans les rucks."""
    return 0.5 * p.power + 0.3 * p.tackling + 0.2 * p.handling


def attacking_rating(p: Player) -> float:
    return 0.35 * p.pace + 0.35 * p.handling + 0.3 * p.passing


def defending_rating(p: Player) -> float:
    return 0.6 * p.tackling + 0.2 * p.power + 0.2 * p.pace


# Note utilisée pour choisir les titulaires à chaque poste.
RATING_FOR_POSITION = {
    Position.PROP: scrum_rating,
    Position.HOOKER: lambda p: 0.5 * scrum_rating(p) + 0.5 * lineout_rating(p),
    Position.LOCK: lambda p: 0.5 * lineout_rating(p) + 0.5 * carrying_rating(p),
    Position.BACK_ROW: lambda p: 0.5 * carrying_rating(p) + 0.5 * defending_rating(p),
    Position.SCRUM_HALF: lambda p: 0.6 * p.passing + 0.4 * p.handling,
    Position.FLY_HALF: lambda p: 0.4 * p.kicking + 0.3 * p.passing + 0.3 * p.handling,
    Position.CENTRE: lambda p: 0.5 * attacking_rating(p) + 0.5 * defending_rating(p),
    Position.WING: lambda p: 0.6 * p.pace + 0.4 * p.handling,
    Position.FULLBACK: lambda p: 0.4 * attacking_rating(p) + 0.3 * p.kicking + 0.3 * p.pace,
}


def _average(values: list[float]) -> float:
    return sum(values) / len(values) if values else 1.0


def start_energy(freshness: float) -> float:
    """Énergie au coup d'envoi selon la fraîcheur du joueur (sur 20)."""
    return ENERGY_START_MIN + (1 - ENERGY_START_MIN) * freshness / 20


def energy_drain(stamina: int) -> float:
    """Énergie perdue par minute de jeu selon l'endurance (sur 20)."""
    return ENERGY_DRAIN_BASE - ENERGY_DRAIN_PER_STAMINA * stamina


def efficiency(energy: float) -> float:
    """Part de ses moyens qu'un joueur garde avec cette énergie."""
    return EFFICIENCY_MIN + (1 - EFFICIENCY_MIN) * energy


# --- Force d'une équipe --------------------------------------------------------------


@dataclass
class Collective:
    """Les quatre notes collectives d'un XV à un instant du match."""

    set_piece: float  # conquête : mêlée + touche
    pack: float  # paquet d'avants dans le jeu courant
    attack: float  # lignes arrières (+ un peu de 3e ligne)
    defense: float  # défense des 15 joueurs

    @property
    def forward_dominance(self) -> float:
        """Domination des avants, qui pousse l'adversaire à la faute (pénalités)."""
        return 0.5 * self.set_piece + 0.5 * self.pack

    def territory(self, kicker_kicking: float) -> float:
        """Capacité à occuper le camp adverse et à se procurer des occasions."""
        return 0.4 * self.set_piece + 0.4 * self.pack + 0.2 * kicker_kicking


# Un joueur et la place (le poste) qu'il occupe sur le terrain.
Fielded = tuple[Position, Player]


def collective_ratings(
    fielded: Iterable[Fielded],
    weight: Callable[[Player], float] = lambda p: 1.0,
    factor: float = 1.0,
) -> Collective:
    """Notes collectives des joueurs présents, chacun jugé au poste qu'il occupe.

    `weight` pondère l'apport de chaque joueur (son énergie) ; `factor` multiplie
    le tout (forme du jour, infériorité numérique).
    """
    fielded = list(fielded)

    def at(*positions: Position) -> list[Player]:
        return [p for pos, p in fielded if pos in positions]

    def rate(players: list[Player], rating: Callable[[Player], float]) -> float:
        return _average([rating(p) * weight(p) for p in players])

    front_row = at(Position.PROP, Position.HOOKER)
    jumpers = at(Position.HOOKER, Position.LOCK, Position.BACK_ROW)
    forwards = [p for pos, p in fielded if pos.is_forward]
    backs = [p for pos, p in fielded if not pos.is_forward]
    everyone = [p for _, p in fielded]

    scrum = 0.7 * rate(front_row, scrum_rating) + 0.3 * rate(at(Position.LOCK), scrum_rating)
    lineout = rate(jumpers, lineout_rating)
    return Collective(
        set_piece=factor * (0.5 * scrum + 0.5 * lineout),
        pack=factor * rate(forwards, carrying_rating),
        attack=factor
        * (
            0.8 * rate(backs, attacking_rating)
            + 0.2 * rate(at(Position.BACK_ROW), attacking_rating)
        ),
        defense=factor * rate(everyone, defending_rating),
    )


@dataclass
class TeamStrength:
    """XV de départ, banc et notes collectives d'un club pour un match."""

    club: Club
    lineup: list[Player]
    set_piece: float  # conquête : mêlée + touche
    pack: float  # paquet d'avants dans le jeu courant
    attack: float  # lignes arrières (+ un peu de 3e ligne)
    defense: float  # défense des 15 joueurs
    kicker: Player  # buteur désigné
    bench: list[Player] = field(default_factory=list)

    @property
    def territory(self) -> float:
        """Capacité à occuper le camp adverse et à se procurer des occasions."""
        return 0.4 * self.set_piece + 0.4 * self.pack + 0.2 * self.kicker.kicking

    @property
    def forward_dominance(self) -> float:
        """Domination des avants, qui pousse l'adversaire à la faute (pénalités)."""
        return 0.5 * self.set_piece + 0.5 * self.pack


def select_lineup(club: Club, day: datetime.date | None = None) -> list[Player]:
    """Choisit les meilleurs joueurs disponibles à chaque poste selon FORMATION.

    Le joueur d'indice i occupe la place SLOT_POSITIONS[i] (numéro SLOT_NUMBERS[i]).
    Les titularisations promises (`club.forced_starters`) passent devant à leur poste.
    Les blessés à la date `day` sont écartés (sans date, tout le monde est apte).
    S'il manque des joueurs à un poste, on complète avec les meilleurs restants
    (un effectif incomplet peut quand même jouer).
    """
    available = club.available_players(day)
    slots: list[Player | None] = []
    for position, count in FORMATION.items():
        candidates = sorted(
            (p for p in available if p.position == position),
            key=lambda p, rating=RATING_FOR_POSITION[position]: (
                p.id in club.forced_starters,
                rating(p),
            ),
            reverse=True,
        )[:count]
        slots.extend([*candidates, *[None] * (count - len(candidates))])

    taken = {p.id for p in slots if p is not None}
    remaining = sorted(
        (p for p in available if p.id not in taken), key=lambda p: p.overall, reverse=True
    )
    for index, player in enumerate(slots):
        if player is None and remaining:
            slots[index] = remaining.pop(0)
    return [p for p in slots if p is not None]


def select_bench(
    club: Club, lineup: list[Player], day: datetime.date | None = None
) -> list[Player]:
    """Les 8 remplaçants (BENCH_FORMATION), parmi les joueurs aptes hors du XV.

    À chaque place, le meilleur joueur restant du poste ; à défaut, le meilleur
    restant tout court. Un effectif court donne un banc plus court.
    """
    taken = {p.id for p in lineup}
    remaining = [p for p in club.available_players(day) if p.id not in taken]
    bench: list[Player] = []
    for wanted in BENCH_FORMATION:
        positions = BACKS_FOR_BENCH if wanted is None else (wanted,)
        candidates = [p for p in remaining if p.position in positions]
        if candidates:
            pick = max(candidates, key=lambda p: RATING_FOR_POSITION[p.position](p))
        elif remaining:
            pick = max(remaining, key=lambda p: p.overall)
        else:
            break
        bench.append(pick)
        remaining.remove(pick)
    return bench


def team_strength(
    club: Club, day: datetime.date | None = None, form: Form = NEUTRAL_FORM
) -> TeamStrength:
    """XV de départ, banc et notes collectives ; `form` les module (neutre par défaut)."""
    lineup = select_lineup(club, day)
    factor = form.factor([p.id for p in lineup])
    ratings = collective_ratings(zip(SLOT_POSITIONS, lineup, strict=False), factor=factor)
    return TeamStrength(
        club=club,
        lineup=lineup,
        set_piece=ratings.set_piece,
        pack=ratings.pack,
        attack=ratings.attack,
        defense=ratings.defense,
        kicker=max(lineup, key=lambda p: p.kicking),
        bench=select_bench(club, lineup, day),
    )


# Au-delà de cet écart entre lignes arrières et paquet, le staff adapte son plan de jeu.
STAFF_PLAN_GAP = 1.0


def staff_tactics(team: TeamStrength) -> Tactics:
    """La tactique qu'adopte un staff (IA) selon les forces de son XV : jeu à la main
    quand les lignes arrières dominent le paquet, occupation au pied dans le cas
    inverse, défense agressive avec un gros paquet et un buteur fiable."""
    if team.attack > team.pack + STAFF_PLAN_GAP:
        plan = GamePlan.HANDS
    elif team.pack > team.attack + STAFF_PLAN_GAP:
        plan = GamePlan.KICKING
    else:
        plan = GamePlan.BALANCED
    aggressive = team.pack >= 14 and team.kicker.kicking >= 14
    return Tactics(game_plan=plan, defence=Defence.AGGRESSIVE if aggressive else Defence.NORMAL)


# --- Probabilités --------------------------------------------------------------------


def _win_probability(a: float, b: float) -> float:
    """Probabilité que la note `a` l'emporte sur la note `b` (entre 0 et 1)."""
    a_pow, b_pow = a**STRENGTH_EXPONENT, b**STRENGTH_EXPONENT
    return a_pow / (a_pow + b_pow)


def kick_success_probability(kicking: int, is_conversion: bool = False) -> float:
    probability = KICK_BASE + KICK_PER_POINT * kicking
    if is_conversion:
        probability -= CONVERSION_PENALTY
    return min(probability, 0.95)


# --- Une équipe pendant le match ----------------------------------------------------------


@dataclass
class Slot:
    """Une place du terrain : son poste, qui l'occupe, et depuis quand.

    Un joueur au banc des pénalités garde sa place (`absent_until` : la minute où
    il revient) ; un exclu ou un blessé sans remplaçant la laisse vide (`player` à None).
    """

    position: Position
    player: Player | None  # None : place vide (exclusion ou blessure sans remplaçant)
    since: int = 0  # minute d'entrée du joueur
    absent_until: int | None = None  # joueur sur le banc des pénalités jusqu'à cette minute

    def present(self, minute: int) -> bool:
        return self.player is not None and (
            self.absent_until is None or minute >= self.absent_until
        )


class Side:
    """L'état d'une équipe pendant le match : terrain, banc, cartons, notes."""

    def __init__(
        self,
        club: Club,
        lineup: list[Player],
        bench: list[Player],
        form: Form = NEUTRAL_FORM,
        tactics: Tactics = DEFAULT_TACTICS,
    ) -> None:
        self.club = club
        self.lineup = list(lineup)  # XV de départ
        self.slots = [
            Slot(position, player) for position, player in zip(SLOT_POSITIONS, lineup, strict=False)
        ]
        self.bench = list(bench)
        self.tactics = tactics
        self.form = form
        self.factor = form.factor([p.id for p in lineup])  # forme du jour, fixée avant le match
        self.substitutions = 0
        # Minute d'entrée de chaque joueur qui a joué (0 pour les titulaires) ; un
        # remplaçant entré ne peut plus entrer.
        self.entered_at: dict[int, int] = {p.id: 0 for p in lineup}
        self.off: dict[int, int] = {}  # joueurs sortis -> minute (remplacés, blessés, exclus)
        self.injured: set[int] = set()
        self.yellows: dict[int, int] = {}
        self.reds: set[int] = set()
        self.ratings: dict[int, float] = {p.id: RATING_START for p in lineup}
        # Énergie restante de ceux qui ont joué ; les autres sont à leur énergie de départ.
        self.energy_left: dict[int, float] = {}
        self.kicker_id = max(lineup, key=lambda p: p.kicking).id if lineup else None

    # -- Qui est où -----------------------------------------------------------------

    def players(self) -> dict[int, Player]:
        """Tous les joueurs de la feuille de match, par identifiant."""
        return {p.id: p for p in [*self.lineup, *self.bench]}

    def on_field(self, minute: int) -> list[Slot]:
        return [s for s in self.slots if s.present(minute)]

    def fielded(self, minute: int) -> list[Fielded]:
        return [(s.position, s.player) for s in self.on_field(minute)]

    def missing(self, minute: int) -> int:
        """Joueurs en moins sur le terrain (cartons, blessés sans remplaçant)."""
        return len(SLOT_POSITIONS) - len(self.on_field(minute))

    def slot_of(self, player_id: int) -> Slot | None:
        return next(
            (s for s in self.slots if s.player is not None and s.player.id == player_id), None
        )

    def available_bench(self) -> list[Player]:
        """Remplaçants qui peuvent encore entrer."""
        return [p for p in self.bench if p.id not in self.entered_at]

    def substitutions_left(self) -> int:
        return MAX_SUBSTITUTIONS - self.substitutions

    def kicker(self, minute: int) -> Player | None:
        present = [s.player for s in self.on_field(minute)]
        if not present:
            return None
        designated = next((p for p in present if p.id == self.kicker_id), None)
        return designated or max(present, key=lambda p: p.kicking)

    # -- Force du moment ------------------------------------------------------------------

    def energy(self, player: Player) -> float:
        """Énergie du joueur : celle du coup d'envoi tant qu'il n'a pas joué, puis
        ce qu'il lui reste (figée à sa sortie)."""
        if player.id in self.energy_left:
            return self.energy_left[player.id]
        return start_energy(self.form.player_freshness(player.id))

    def effort(self, minute: int) -> float:
        """Multiplicateur de la dépense d'énergie à cette minute : infériorité
        numérique et agressivité défensive."""
        short_handed = 1 + SHORT_HANDED_EFFORT * self.missing(minute)
        return short_handed * DEFENCE_EFFECTS[self.tactics.defence]["effort"]

    def spend_energy(self, minute: int) -> None:
        """Une minute de jeu : chaque joueur présent dépense selon son endurance."""
        effort = self.effort(minute)
        for slot in self.on_field(minute):
            player = slot.player
            left = self.energy(player) - energy_drain(player.stamina) * effort
            self.energy_left[player.id] = max(0.0, left)

    def collective(self, minute: int) -> Collective:
        """Notes collectives des joueurs présents : énergie, forme, infériorité, tactique."""
        factor = self.factor * SHORT_HANDED_FACTOR ** self.missing(minute)
        ratings = collective_ratings(
            self.fielded(minute),
            weight=lambda p: efficiency(self.energy(p)),
            factor=factor,
        )
        ratings.defense *= DEFENCE_EFFECTS[self.tactics.defence]["defense"]
        return ratings

    def territory(self, minute: int, ratings: Collective) -> float:
        kicker = self.kicker(minute)
        plan = GAME_PLAN_EFFECTS[self.tactics.game_plan]["territory"]
        return plan * ratings.territory(kicker.kicking if kicker else 0)

    # -- Mouvements ------------------------------------------------------------------------

    def substitute(self, player_out: int, player_in: int, minute: int) -> MatchEvent:
        """Fait entrer `player_in` à la place de `player_out` ; lève ValueError si impossible."""
        slot = self.slot_of(player_out)
        if slot is None or not slot.present(minute):
            raise ValueError("Ce joueur n'est pas sur le terrain")
        incoming = next((p for p in self.available_bench() if p.id == player_in), None)
        if incoming is None:
            raise ValueError("Ce remplaçant ne peut pas entrer")
        if self.substitutions_left() <= 0:
            raise ValueError("Plus de remplacement possible")
        self.off[player_out] = minute
        self.entered_at[player_in] = minute
        self.substitutions += 1
        self.ratings.setdefault(player_in, RATING_START)
        slot.player, slot.since, slot.absent_until = incoming, minute, None
        return MatchEvent(minute, EventType.SUBSTITUTION, self.club.id, player_out, player_in)

    def replacement_for(self, slot: Slot) -> Player | None:
        """Le remplaçant que le staff ferait entrer à cette place : même poste de
        préférence, sinon le meilleur restant."""
        bench = self.available_bench()
        if not bench or self.substitutions_left() <= 0:
            return None
        same = [p for p in bench if p.position == slot.position]
        pool = same or bench
        return max(pool, key=lambda p: RATING_FOR_POSITION[slot.position](p))

    def injure(self, player: Player, minute: int) -> list[MatchEvent]:
        """Le joueur se blesse et sort ; un remplaçant entre s'il en reste."""
        slot = self.slot_of(player.id)
        self.injured.add(player.id)
        self.off[player.id] = minute
        events = [MatchEvent(minute, EventType.INJURY, self.club.id, player.id)]
        if slot is None:
            return events
        replacement = self.replacement_for(slot)
        if replacement is None:
            slot.player = None
            return events
        self.entered_at[replacement.id] = minute
        self.substitutions += 1
        self.ratings.setdefault(replacement.id, RATING_START)
        slot.player, slot.since, slot.absent_until = replacement, minute, None
        events.append(
            MatchEvent(minute, EventType.SUBSTITUTION, self.club.id, player.id, replacement.id)
        )
        return events

    def card(self, player: Player, minute: int, red: bool) -> MatchEvent:
        """Carton : jaune (10 minutes dehors, rouge au second) ou rouge direct."""
        slot = self.slot_of(player.id)
        if not red:
            self.yellows[player.id] = self.yellows.get(player.id, 0) + 1
            red = self.yellows[player.id] >= 2
        if red:
            self.reds.add(player.id)
            self.off[player.id] = minute
            if slot is not None:
                slot.player = None
            return MatchEvent(minute, EventType.RED_CARD, self.club.id, player.id)
        if slot is not None:
            slot.absent_until = minute + SIN_BIN_MINUTES
        return MatchEvent(minute, EventType.YELLOW_CARD, self.club.id, player.id)

    def auto_substitution(self, minute: int) -> MatchEvent | None:
        """Le changement que ferait le staff à cette minute, s'il y en a un à faire.

        Il remplace le joueur qui a le moins d'énergie parmi ceux qui ont un
        remplaçant de leur poste sur le banc, en gardant un changement pour une blessure.
        """
        if self.substitutions_left() <= AI_SUBSTITUTIONS_KEPT:
            return None
        bench = self.available_bench()
        candidates = [
            s
            for s in self.on_field(minute)
            if minute - s.since >= AI_MIN_MINUTES_ON_FIELD
            and any(p.position == s.position for p in bench)
        ]
        if not candidates:
            return None
        slot = min(candidates, key=lambda s: self.energy(s.player))
        incoming = max(
            (p for p in bench if p.position == slot.position),
            key=lambda p: RATING_FOR_POSITION[slot.position](p),
        )
        return self.substitute(slot.player.id, incoming.id, minute)

    # -- Notes sur 10 ---------------------------------------------------------------------

    def rate(self, player_id: int, delta: float) -> None:
        if player_id in self.ratings:
            value = self.ratings[player_id] + delta
            self.ratings[player_id] = min(RATING_MAX, max(RATING_MIN, value))

    def rate_present(self, minute: int, delta: float, forwards: bool | None = None) -> None:
        """Fait varier la note de tous les joueurs présents (ou d'une seule ligne)."""
        for slot in self.on_field(minute):
            if forwards is None or slot.position.is_forward == forwards:
                self.rate(slot.player.id, delta)

    # -- Sauvegarde ------------------------------------------------------------------------

    def to_state(self) -> dict:
        return {
            "club_id": self.club.id,
            "lineup": [p.id for p in self.lineup],
            "bench": [p.id for p in self.bench],
            "slots": [
                {
                    "position": s.position.value,
                    "player_id": s.player.id if s.player else None,
                    "since": s.since,
                    "absent_until": s.absent_until,
                }
                for s in self.slots
            ],
            "tactics": self.tactics.to_dict(),
            "form": {
                "morale": self.form.morale,
                "cohesion": self.form.cohesion,
                "freshness": {str(k): v for k, v in self.form.freshness.items()},
            },
            "substitutions": self.substitutions,
            "entered_at": {str(k): v for k, v in self.entered_at.items()},
            "off": {str(k): v for k, v in self.off.items()},
            "injured": sorted(self.injured),
            "yellows": {str(k): v for k, v in self.yellows.items()},
            "reds": sorted(self.reds),
            "ratings": {str(k): v for k, v in self.ratings.items()},
            "energy_left": {str(k): v for k, v in self.energy_left.items()},
            "kicker_id": self.kicker_id,
        }

    @classmethod
    def from_state(cls, club: Club, state: dict) -> "Side":
        players = {p.id: p for p in club.players}
        form = Form(
            morale=state["form"]["morale"],
            cohesion=state["form"]["cohesion"],
            freshness={int(k): v for k, v in state["form"]["freshness"].items()},
        )
        side = cls(
            club,
            [players[i] for i in state["lineup"] if i in players],
            [players[i] for i in state["bench"] if i in players],
            form,
            Tactics.from_dict(state["tactics"]),
        )
        side.slots = [
            Slot(
                Position(s["position"]),
                players.get(s["player_id"]) if s["player_id"] is not None else None,
                s["since"],
                s["absent_until"],
            )
            for s in state["slots"]
        ]
        side.substitutions = state["substitutions"]
        side.entered_at = {int(k): v for k, v in state["entered_at"].items()}
        side.off = {int(k): v for k, v in state["off"].items()}
        side.injured = set(state["injured"])
        side.yellows = {int(k): v for k, v in state["yellows"].items()}
        side.reds = set(state["reds"])
        side.ratings = {int(k): v for k, v in state["ratings"].items()}
        side.energy_left = {int(k): v for k, v in state["energy_left"].items()}
        side.kicker_id = state["kicker_id"]
        return side


# --- Le match, minute par minute ---------------------------------------------------------


class LiveMatch:
    """Un match qu'on joue minute par minute, avec la main sur les bancs.

    `step()` joue la minute suivante ; `advance(n)` en joue plusieurs ; entre deux,
    on peut changer la tactique d'une équipe (`set_tactics`) ou faire un
    remplacement (`substitute`). Les équipes de `auto` sont gérées par le staff
    (remplacements automatiques) ; une équipe hors de `auto` ne change de joueur
    que sur blessure ou sur ordre du manager.
    """

    def __init__(
        self,
        home: Club,
        away: Club,
        rng: random.Random | None = None,
        matchday: int = 0,
        neutral: bool = False,
        day: datetime.date | None = None,
        home_form: Form = NEUTRAL_FORM,
        away_form: Form = NEUTRAL_FORM,
        knockout: bool = False,
        home_tactics: Tactics = DEFAULT_TACTICS,
        away_tactics: Tactics = DEFAULT_TACTICS,
        auto: Iterable[int] | None = None,
    ) -> None:
        self.rng = rng or random.Random()
        self.matchday = matchday
        self.neutral = neutral
        self.day = day
        self.knockout = knockout
        self.auto = set(auto) if auto is not None else {home.id, away.id}
        home_team = team_strength(home, day, home_form)
        away_team = team_strength(away, day, away_form)
        self.home = Side(home, home_team.lineup, home_team.bench, home_form, home_tactics)
        self.away = Side(away, away_team.lineup, away_team.bench, away_form, away_tactics)
        self.events: list[MatchEvent] = []
        self.minute = 0  # dernière minute jouée
        self.extra_time = False
        self.finished = False

    # -- Lecture ------------------------------------------------------------------------

    @property
    def sides(self) -> tuple[Side, Side]:
        return self.home, self.away

    def side(self, club_id: int) -> Side:
        if club_id == self.home.club.id:
            return self.home
        if club_id == self.away.club.id:
            return self.away
        raise ValueError("Ce club ne joue pas ce match")

    def opponent(self, side: Side) -> Side:
        return self.away if side is self.home else self.home

    def score(self, club_id: int) -> int:
        return sum(e.points for e in self.events if e.club_id == club_id)

    def level(self) -> bool:
        return self.score(self.home.club.id) == self.score(self.away.club.id)

    @property
    def last_minute(self) -> int:
        """Dernière minute du match telle qu'on la connaît (80, ou 100 en prolongation)."""
        return MATCH_MINUTES + (EXTRA_TIME_MINUTES if self.extra_time else 0)

    def result(self) -> Match:
        """Le match tel qu'il en est (complet si `finished`)."""
        home_id, away_id = self.home.club.id, self.away.club.id
        return Match(
            home_club_id=home_id,
            away_club_id=away_id,
            matchday=self.matchday,
            home_score=self.score(home_id),
            away_score=self.score(away_id),
            events=list(self.events),
            neutral=self.neutral,
            date=self.day,
            home_lineup=[p.id for p in self.home.lineup],
            away_lineup=[p.id for p in self.away.lineup],
        )

    # -- Ordres du manager ------------------------------------------------------------------

    def set_tactics(self, club_id: int, tactics: Tactics) -> None:
        self.side(club_id).tactics = tactics

    def substitute(self, club_id: int, player_out: int, player_in: int) -> MatchEvent:
        """Remplacement décidé par le manager, effectif à la minute en cours."""
        if self.finished:
            raise ValueError("Le match est terminé")
        event = self.side(club_id).substitute(player_out, player_in, self.minute)
        self.events.append(event)
        return event

    # -- Déroulement ----------------------------------------------------------------------

    def advance(self, minutes: int = 1) -> list[MatchEvent]:
        """Joue `minutes` minutes (ou jusqu'à la fin) et renvoie les événements survenus."""
        before = len(self.events)
        for _ in range(minutes):
            if self.finished:
                break
            self.step()
        return self.events[before:]

    def play_to_end(self) -> Match:
        while not self.finished:
            self.step()
        return self.result()

    def step(self) -> None:
        """Joue la minute suivante."""
        if self.finished:
            return
        minute = self.minute + 1
        self._play_minute(minute)
        self.minute = minute
        if minute == MATCH_MINUTES:
            if self.knockout and self.level():
                self.extra_time = True
            else:
                self.finished = True
        elif minute == MATCH_MINUTES + EXTRA_TIME_MINUTES:
            if self.level():
                self._shootout(minute)
            self.finished = True

    def _play_minute(self, minute: int) -> None:
        rng = self.rng
        # Blessures, cartons et changements d'abord : ils décident qui joue l'action.
        for side in self.sides:
            self._injuries(side, minute)
        for side in self.sides:
            self._cards(side, minute)
        for side in self.sides:
            side.spend_energy(minute)
        for side in self.sides:
            if side.club.id in self.auto and minute in AI_SUBSTITUTION_MINUTES:
                event = side.auto_substitution(minute)
                if event is not None:
                    self.events.append(event)

        home_ratings = self.home.collective(minute)
        away_ratings = self.away.collective(minute)
        self._drift_ratings(minute, home_ratings, away_ratings)

        if rng.random() >= CHANCE_PER_MINUTE:
            return
        advantage = 1.0 if self.neutral else HOME_ADVANTAGE
        home_share = _win_probability(
            self.home.territory(minute, home_ratings) * advantage,
            self.away.territory(minute, away_ratings),
        )
        if rng.random() < home_share:
            self._chance(self.home, self.away, home_ratings, away_ratings, minute)
        else:
            self._chance(self.away, self.home, away_ratings, home_ratings, minute)

    def _injuries(self, side: Side, minute: int) -> None:
        """Un joueur fragile peut rechuter ; tout joueur présent peut se blesser."""
        rng = self.rng
        present = [s.player for s in side.on_field(minute)]
        if not present:
            return
        for player in present:
            if player.is_fragile(self.day):
                # Risque de rechute par match, réparti sur les 80 minutes.
                per_minute = 1 - (1 - player.injury.relapse_risk) ** (1 / MATCH_MINUTES)
                if rng.random() < per_minute:
                    self.events.extend(side.injure(player, minute))
                    return
        weights = [side.form.injury_weight(p) for p in present]
        chance = MATCH_INJURY_CHANCE_PER_MINUTE * sum(weights) / len(weights)
        if rng.random() < chance:
            player = rng.choices(present, weights=weights)[0]
            self.events.extend(side.injure(player, minute))

    def _cards(self, side: Side, minute: int) -> None:
        """Carton jaune ou rouge, suivi d'une pénalité pour l'adversaire."""
        rng = self.rng
        present = side.on_field(minute)
        if not present:
            return
        cards = DEFENCE_EFFECTS[side.tactics.defence]["cards"]
        roll = rng.random()
        if roll < RED_CHANCE_PER_MINUTE * cards:
            red = True
        elif roll < (RED_CHANCE_PER_MINUTE + YELLOW_CHANCE_PER_MINUTE) * cards:
            red = False
        else:
            return
        weights = [
            CARD_WEIGHT_FORWARD if s.position.is_forward else CARD_WEIGHT_BACK for s in present
        ]
        player = rng.choices([s.player for s in present], weights=weights)[0]
        event = side.card(player, minute, red)
        self.events.append(event)
        side.rate(player.id, RATING_EVENT[event.type])
        # La faute est sanctionnée : pénalité face aux perches pour l'adversaire.
        self._penalty_kick(self.opponent(side), minute)

    def _penalty_kick(self, side: Side, minute: int) -> None:
        kicker = side.kicker(minute)
        if kicker is None:
            return
        success = self.rng.random() < kick_success_probability(kicker.kicking)
        event_type = EventType.PENALTY_GOAL if success else EventType.PENALTY_MISSED
        self.events.append(MatchEvent(minute, event_type, side.club.id, kicker.id))
        side.rate(kicker.id, RATING_EVENT[event_type])

    def _try(self, attacking: Side, defending: Side, minute: int) -> None:
        """Un essai et sa transformation."""
        rng = self.rng
        present = attacking.on_field(minute)
        weights = [
            TRY_SCORER_WEIGHT[s.position] * (s.player.pace + s.player.power) for s in present
        ]
        scorer = rng.choices([s.player for s in present], weights=weights)[0]
        self.events.append(MatchEvent(minute, EventType.TRY, attacking.club.id, scorer.id))
        attacking.rate_present(minute, RATING_TEAM_SCORED)
        attacking.rate(scorer.id, RATING_EVENT[EventType.TRY])
        defending.rate_present(minute, RATING_TEAM_CONCEDED)

        kicker = attacking.kicker(minute)
        converted = rng.random() < kick_success_probability(kicker.kicking, is_conversion=True)
        conversion = EventType.CONVERSION if converted else EventType.CONVERSION_MISSED
        self.events.append(MatchEvent(minute, conversion, attacking.club.id, kicker.id))
        attacking.rate(kicker.id, RATING_EVENT[conversion])

    def _chance(
        self,
        attacking: Side,
        defending: Side,
        att: Collective,
        dfn: Collective,
        minute: int,
    ) -> None:
        """Joue une action dangereuse de `attacking`."""
        rng = self.rng
        plan = GAME_PLAN_EFFECTS[attacking.tactics.game_plan]
        their_plan = GAME_PLAN_EFFECTS[defending.tactics.game_plan]
        their_defence = DEFENCE_EFFECTS[defending.tactics.defence]
        # Les probabilités valent TRY_RATE / PENALTY_RATE entre équipes égales
        # (_win_probability = 0.5) et varient avec l'écart de niveau et la tactique.
        try_probability = (
            2 * TRY_RATE * _win_probability(att.attack, dfn.defense) * plan["tries"]
        ) * their_plan["conceded"]
        penalty_probability = (
            2
            * PENALTY_RATE
            * _win_probability(att.forward_dominance, dfn.forward_dominance)
            * plan["penalties"]
            * their_defence["fouls"]
        )
        roll = rng.random()

        # 1) Essai, suivi d'une tentative de transformation.
        if roll < try_probability:
            self._try(attacking, defending, minute)
            return

        # 2) Pénalité en position : tentée face aux perches, ou jouée à la main.
        if roll < try_probability + penalty_probability:
            if attacking.tactics.penalties == PenaltyChoice.PLAY:
                scored = rng.random() < 2 * PLAY_PENALTY_TRY_RATE * _win_probability(
                    att.attack, dfn.defense
                )
                if scored:
                    self._try(attacking, defending, minute)
                return
            self._penalty_kick(attacking, minute)
            return

        # 3) Drop de l'ouvreur (on ne garde que les drops réussis, les ratés sont anecdotiques).
        if roll < try_probability + penalty_probability + DROP_RATE:
            fly_half = next(
                (s.player for s in attacking.on_field(minute) if s.position == Position.FLY_HALF),
                None,
            )
            drop_kicker = fly_half or attacking.kicker(minute)
            if drop_kicker is not None:
                self.events.append(
                    MatchEvent(minute, EventType.DROP_GOAL, attacking.club.id, drop_kicker.id)
                )
                attacking.rate(drop_kicker.id, RATING_EVENT[EventType.DROP_GOAL])

        # 4) L'action ne donne rien.

    def _drift_ratings(self, minute: int, home: Collective, away: Collective) -> None:
        """Chaque minute, la ligne qui domine son duel gagne un peu, l'autre perd,
        et chaque joueur y ajoute son grain de hasard."""
        forwards = _win_probability(home.forward_dominance, away.forward_dominance)
        home_backs = _win_probability(home.attack, away.defense)
        away_backs = _win_probability(away.attack, home.defense)
        drift = RATING_DRIFT_PER_MINUTE
        self.home.rate_present(minute, drift * (2 * forwards - 1), forwards=True)
        self.away.rate_present(minute, drift * (1 - 2 * forwards), forwards=True)
        self.home.rate_present(minute, drift * (home_backs - away_backs), forwards=False)
        self.away.rate_present(minute, drift * (away_backs - home_backs), forwards=False)
        noise = RATING_NOISE_PER_MINUTE
        for side in self.sides:
            for slot in side.on_field(minute):
                side.rate(slot.player.id, self.rng.uniform(-noise, noise))

    def _shootout(self, minute: int) -> None:
        """Séance de tirs au but, l'ordre tiré au sort.

        Chaque équipe aligne ses meilleurs buteurs présents sur le terrain. La
        séance s'arrête dès qu'une équipe ne peut plus être rattrapée ; après 5
        tirs chacun, c'est la mort subite, tir par tir.
        """
        rng = self.rng
        first, second = (self.home, self.away) if rng.random() < 0.5 else (self.away, self.home)
        teams = (first, second)
        kickers = []
        for team in teams:
            present = [s.player for s in team.on_field(minute)] or team.lineup
            kickers.append(sorted(present, key=lambda p: p.kicking, reverse=True))
        goals = [0, 0]
        kicks = 0
        while True:
            side, turn = kicks % 2, kicks // 2
            kicker = kickers[side][turn % len(kickers[side])]
            scored = rng.random() < kick_success_probability(kicker.kicking) - SHOOTOUT_PRESSURE
            goals[side] += scored
            event_type = EventType.SHOOTOUT_GOAL if scored else EventType.SHOOTOUT_MISSED
            self.events.append(MatchEvent(minute, event_type, teams[side].club.id, kicker.id))
            teams[side].rate(kicker.id, RATING_EVENT[event_type])
            kicks += 1
            if kicks < 2 * SHOOTOUT_KICKERS:
                left = [SHOOTOUT_KICKERS - (kicks + 1) // 2, SHOOTOUT_KICKERS - kicks // 2]
                if goals[0] > goals[1] + left[1] or goals[1] > goals[0] + left[0]:
                    return
            elif kicks % 2 == 0 and goals[0] != goals[1]:
                return

    # -- Sauvegarde -------------------------------------------------------------------------

    def to_state(self) -> dict:
        """Tout ce qu'il faut pour reprendre le match plus tard (JSON)."""
        version, internal, gauss = self.rng.getstate()
        return {
            "matchday": self.matchday,
            "neutral": self.neutral,
            "day": self.day.isoformat() if self.day else None,
            "knockout": self.knockout,
            "auto": sorted(self.auto),
            "minute": self.minute,
            "extra_time": self.extra_time,
            "finished": self.finished,
            "rng": [version, list(internal), gauss],
            "events": [
                {
                    "minute": e.minute,
                    "type": e.type.value,
                    "club_id": e.club_id,
                    "player_id": e.player_id,
                    "other_player_id": e.other_player_id,
                }
                for e in self.events
            ],
            "home": self.home.to_state(),
            "away": self.away.to_state(),
        }

    @classmethod
    def from_state(cls, home: Club, away: Club, state: dict) -> "LiveMatch":
        live = cls.__new__(cls)
        live.rng = random.Random()
        version, internal, gauss = state["rng"]
        live.rng.setstate((version, tuple(internal), gauss))
        live.matchday = state["matchday"]
        live.neutral = state["neutral"]
        live.day = datetime.date.fromisoformat(state["day"]) if state["day"] else None
        live.knockout = state["knockout"]
        live.auto = set(state["auto"])
        live.minute = state["minute"]
        live.extra_time = state["extra_time"]
        live.finished = state["finished"]
        live.events = [
            MatchEvent(
                e["minute"],
                EventType(e["type"]),
                e["club_id"],
                e["player_id"],
                e["other_player_id"],
            )
            for e in state["events"]
        ]
        live.home = Side.from_state(home, state["home"])
        live.away = Side.from_state(away, state["away"])
        return live


def simulate_match(
    home: Club,
    away: Club,
    rng: random.Random | None = None,
    matchday: int = 0,
    neutral: bool = False,
    day: datetime.date | None = None,
    home_form: Form = NEUTRAL_FORM,
    away_form: Form = NEUTRAL_FORM,
    knockout: bool = False,
    home_tactics: Tactics = DEFAULT_TACTICS,
    away_tactics: Tactics = DEFAULT_TACTICS,
) -> Match:
    """Simule un match complet et renvoie un `Match` joué (score + événements).

    `rng` permet de fixer le hasard (ex. `random.Random(42)`) pour des résultats
    reproductibles, notamment dans les tests. `neutral` supprime l'avantage du
    terrain (finale). `day` est la date du match : les blessés ce jour-là ne
    jouent pas, et les blessures du match sont signalées en événements.
    `home_form` / `away_form` : forme du jour de chaque club (neutre par défaut).
    `knockout` : match à élimination directe, qui ne peut pas finir sur un nul
    (prolongation, puis tirs au but). Les deux bancs sont gérés par le staff.
    """
    live = LiveMatch(
        home,
        away,
        rng=rng,
        matchday=matchday,
        neutral=neutral,
        day=day,
        home_form=home_form,
        away_form=away_form,
        knockout=knockout,
        home_tactics=home_tactics,
        away_tactics=away_tactics,
    )
    return live.play_to_end()
