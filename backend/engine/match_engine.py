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
   (essai, coup de pied, carton, plaquages, franchissements...) et la
   domination de sa ligne. Chaque minute se joue aussi en temps de jeu
   (ballons portés, plaquages, touches) : ces statistiques de chaque joueur
   (`PlayerMatchStats`) suivent le rapport de force sans décider du score.
6. La forme du jour (`engine/form.py` : moral, cohésion, fraîcheur) multiplie
   les notes collectives (et fixe l'énergie de départ de chaque joueur), et la
   fatigue augmente le risque de blessure. En direct, les discours du manager
   (`engine/team_talk.py`) ajoutent un élan passager aux notes collectives, et
   de la nervosité qui fait monter (ou baisser) le risque de carton.
7. En phase finale, une égalité après 80 minutes mène à une prolongation
   (2 x 10 minutes), puis si besoin à une séance de tirs au but.
8. La météo (`engine/weather.py`) pèse sur l'attaque, les coups de pied et
   l'énergie ; le public (`engine/crowd.py`) fait l'avantage du terrain et siffle
   le buteur adverse ; le capitaine, tant qu'il est sur le terrain, calme les esprits
   (moins de cartons) et tire un peu l'équipe vers le haut.
9. Le staff technique (`engine/coaching.py`) multiplie les notes collectives
   (avants, attaque, défense) et le territoire (analyste), et règle le buteur.
10. Dans les 5 dernières minutes d'un match serré (7 points d'écart ou moins), une
   pénalité en position pour une équipe menée par son manager attend sa décision
   (`decide`) : les perches, la touche, la mêlée ou la jouer vite. Dans un match à
   enjeu (élimination directe, derby), si aucune ne vient d'elle-même, le jeu en
   offre une avant le coup de sifflet final.
11. En carrière de joueur, le joueur incarné (`hero`) joue dans un club mené par son
   staff : sur le terrain, le match s'arrête de temps en temps sur un dilemme
   (`engine/dilemmas.py`) qu'il tranche (`choose`), pour sa note et parfois le score.
   Remplaçant, il entre à l'heure de jeu ; le staff ne le sort pas. Un manager
   (`coach` : son club) a les siens, plus rares, pour un joueur de son XV sur le terrain
   tiré au hasard, la situation selon son poste.

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
from itertools import accumulate

from engine import crowd as crowds
from engine import dilemmas, momentum, regulations, team_talk
from engine.coaching import Coaching
from engine.coaching import coaching as coaching_of
from engine.crowd import Crowd
from engine.form import NEUTRAL_FORM, Form
from engine.medical import MATCH_INJURY_CHANCE_PER_MINUTE
from engine.weather import EFFECTS as WEATHER_EFFECTS
from engine.weather import Weather
from models import (
    EXTRA_TIME_MINUTES,
    MATCH_STAT_NAMES,
    REGULATION_MINUTES,
    Club,
    EventType,
    Match,
    MatchEvent,
    Player,
    PlayerMatchStats,
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

# Les points qui font réagir le public (engine/crowd.py).
CROWD_SCORES = {EventType.TRY, EventType.PENALTY_GOAL, EventType.DROP_GOAL}

# Bonus multiplicatif sur le territoire de l'équipe à domicile (l'avantage du
# terrain est fort au rugby), quand on ne sait rien du public (match amical,
# match de sélections). Sinon, il suit l'ambiance du stade (engine/crowd.py).
HOME_ADVANTAGE = 1.25

# Plus l'exposant est grand, plus l'écart de niveau pèse sur le résultat
# (1 = proportionnel, 2 = l'équipe forte écrase davantage).
# À 1.0, le meilleur club bat le plus faible ~95 % du temps à domicile.
STRENGTH_EXPONENT = 1.0

# Probabilité de réussir un coup de pied au but : 35 % + 3 % par point de kicking
# (kicking 10 => 65 %, 15 => 80 %, 20 => 95 %).
KICK_BASE = 0.35
KICK_PER_POINT = 0.03
KICK_MAX = 0.95  # même le meilleur buteur, bien entraîné, manque parfois
# Une transformation se tente là où l'essai a été marqué, souvent excentrée.
CONVERSION_PENALTY = 0.05

# Tirs au but (règlement du Top 14) : 5 buteurs par équipe en alternance, depuis
# la ligne des 22 mètres, puis mort subite tant que l'égalité persiste.
SHOOTOUT_KICKERS = 5
# La pression de la séance coûte un peu de réussite par rapport à une pénalité.
SHOOTOUT_PRESSURE = 0.05

# Au bout d'un maul, le talonneur (qui a lancé et se glisse au fond) et la
# troisième ligne aplatissent le plus souvent.
MAUL_SCORER_WEIGHT = {
    Position.PROP: 0.6,
    Position.HOOKER: 3.0,
    Position.LOCK: 0.8,
    Position.BACK_ROW: 2.0,
}

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
    PLAY = "play"  # jouée à la main, vite, par les lignes arrières
    TOUCH = "touch"  # en touche, puis maul ou pick-and-go des avants


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
# Pénalité en touche : l'essai se joue entre les deux paquets (conquête et
# domination des avants contre celles de l'adversaire).
TOUCH_PENALTY_TRY_RATE = 0.38
# Pénalité jouée en mêlée : l'essai en force se joue entre les deux mêlées seules.
SCRUM_PENALTY_TRY_RATE = 0.36


class PenaltyOption(StrEnum):
    """Ce que le manager fait d'une pénalité décisive : les tactiques (`PenaltyChoice`)
    et, en plus, la mêlée."""

    KICK = "kick"
    TOUCH = "touch"
    SCRUM = "scrum"  # mêlée à 5 mètres, pour l'essai en force
    PLAY = "play"


# --- Fin de match serrée : le choix crucial ------------------------------------------

# Dans les CRUNCH_MINUTES dernières minutes, à CRUNCH_MARGIN points d'écart ou moins,
# une pénalité en position pour une équipe hors de `auto` attend la décision du manager.
CRUNCH_MINUTES = 5
CRUNCH_MARGIN = 7
# Le staff, s'il décide à sa place : les 3 points quand ils suffisent à égaliser ou à
# passer devant, sinon la touche pour aller chercher l'essai.
STAFF_KICK_MARGIN = -3


def staff_penalty(margin: int) -> PenaltyOption:
    """Le choix du staff pour une pénalité décisive, selon les points d'avance."""
    return PenaltyOption.KICK if margin >= STAFF_KICK_MARGIN else PenaltyOption.TOUCH


@dataclass
class Crunch:
    """Une pénalité qui attend la décision du manager, et de quoi finir sa minute."""

    minute: int
    club_id: int
    play: dict[int, int]  # points de jeu de la minute, par club (engine/momentum.py)
    chance: tuple[int, float] | None  # l'action de la minute (engine/momentum.py)

    def to_dict(self) -> dict:
        return {
            "minute": self.minute,
            "club_id": self.club_id,
            "play": [[club_id, points] for club_id, points in self.play.items()],
            "chance": list(self.chance) if self.chance else None,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Crunch":
        chance = data["chance"]
        return cls(
            minute=data["minute"],
            club_id=data["club_id"],
            play={club_id: points for club_id, points in data["play"]},
            chance=(chance[0], chance[1]) if chance else None,
        )


# --- Capitaine ----------------------------------------------------------------------

# Le meneur (de 0 à 1) d'un joueur tient à son expérience (l'âge) et à son niveau.
LEADERSHIP_AGE_FROM, LEADERSHIP_AGE_SPAN = 19, 13
LEADERSHIP_AGE_SHARE = 0.6
# Un capitaine meneur à 1 sur le terrain : 30 % de cartons en moins, notes
# collectives +3 %.
CAPTAIN_CARDS = 0.30
CAPTAIN_BOOST = 0.03

# --- Temps de jeu : ballons portés, plaquages, touches -------------------------------

# Chaque minute, les deux équipes se disputent des temps de jeu ; la possession
# suit le territoire. Par équipe et par match : ~130 ballons portés, ~120 plaquages
# réussis, ~15 manqués, ~5 franchissements et ~4 ballons grattés.
PHASES_PER_MINUTE = 3
TACKLE_SUCCESS = 0.86  # entre un plaqueur et un porteur de même niveau
TACKLE_SWING = 0.10  # écart maximal selon le duel
TACKLE_ASSIST = 0.35  # un second plaqueur vient aider
# Un plaquage manqué peut laisser filer le porteur (selon l'attaque et la défense).
LINE_BREAK_ON_MISS = 0.25
TURNOVER_PER_PHASE = 0.045
# Touches : ~13 lancers par équipe ; le lanceur garde son ballon ~88 % du temps.
LINEOUT_PER_MINUTE = 0.33
LINEOUT_KEEP = 0.88
LINEOUT_SWING = 0.10

# Qui porte, plaque, gratte ou saute, selon le poste.
CARRY_WEIGHT = {
    Position.PROP: 1.0,
    Position.HOOKER: 1.0,
    Position.LOCK: 1.2,
    Position.BACK_ROW: 1.6,
    Position.SCRUM_HALF: 0.5,
    Position.FLY_HALF: 0.7,
    Position.CENTRE: 1.4,
    Position.WING: 1.1,
    Position.FULLBACK: 1.1,
}
TACKLE_WEIGHT = {
    Position.PROP: 1.0,
    Position.HOOKER: 1.2,
    Position.LOCK: 1.4,
    Position.BACK_ROW: 1.8,
    Position.SCRUM_HALF: 0.8,
    Position.FLY_HALF: 0.9,
    Position.CENTRE: 1.3,
    Position.WING: 0.6,
    Position.FULLBACK: 0.5,
}
TURNOVER_WEIGHT = {
    Position.PROP: 0.6,
    Position.HOOKER: 1.5,
    Position.LOCK: 0.8,
    Position.BACK_ROW: 3.0,
    Position.SCRUM_HALF: 0.3,
    Position.FLY_HALF: 0.2,
    Position.CENTRE: 0.8,
    Position.WING: 0.2,
    Position.FULLBACK: 0.3,
}
JUMPER_WEIGHT = {Position.LOCK: 3.0, Position.BACK_ROW: 1.0}

# Ce que rapporte chaque statistique à la note sur 10 du joueur.
STAT_RATING = {
    "tackles": 0.02,
    "missed_tackles": -0.06,
    "line_breaks": 0.15,
    "turnovers": 0.2,
    "lineouts_won": 0.02,
    "lineout_steals": 0.15,
}

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


def leadership(p: Player) -> float:
    """Ascendant d'un joueur sur le groupe, de 0 à 1 : son expérience, puis son niveau."""
    experience = min(max(p.age - LEADERSHIP_AGE_FROM, 0) / LEADERSHIP_AGE_SPAN, 1.0)
    level = p.level / 20
    return LEADERSHIP_AGE_SHARE * experience + (1 - LEADERSHIP_AGE_SHARE) * level


def captain_of(club: Club, lineup: list[Player]) -> Player | None:
    """Le capitaine du XV : celui du manager s'il est titulaire, sinon le plus grand meneur."""
    chosen = next((p for p in lineup if p.id == club.captain_id), None)
    return chosen or max(lineup, key=leadership, default=None)


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


def scrum_strength(
    fielded: Iterable[Fielded], weight: Callable[[Player], float] = lambda p: 1.0
) -> float:
    """Poussée en mêlée : la première ligne surtout, les deuxième ligne derrière."""
    fielded = list(fielded)

    def rate(*positions: Position) -> float:
        return _average([scrum_rating(p) * weight(p) for pos, p in fielded if pos in positions])

    return 0.7 * rate(Position.PROP, Position.HOOKER) + 0.3 * rate(Position.LOCK)


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
    # Le poids de chacun, calculé une fois pour toutes les notes.
    weights = {p.id: weight(p) for _, p in fielded}

    def at(*positions: Position) -> list[Player]:
        return [p for pos, p in fielded if pos in positions]

    def rate(players: list[Player], rating: Callable[[Player], float]) -> float:
        return _average([rating(p) * weights[p.id] for p in players])

    jumpers = at(Position.HOOKER, Position.LOCK, Position.BACK_ROW)
    forwards = [p for pos, p in fielded if pos.is_forward]
    backs = [p for pos, p in fielded if not pos.is_forward]
    everyone = [p for _, p in fielded]

    scrum = scrum_strength(fielded, lambda p: weights[p.id])
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


def coach(ratings: Collective, coaching: Coaching) -> Collective:
    """Les notes collectives travaillées par le staff technique (engine/coaching.py)."""
    ratings.set_piece *= coaching.forwards
    ratings.pack *= coaching.forwards
    ratings.attack *= coaching.attack
    ratings.defense *= coaching.defence
    return ratings


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
    Les places choisies par le manager (`club.lineup_choice`) sont gardées telles
    quelles, même hors poste, tant que le joueur est apte ; le staff pourvoit les autres.
    Les titularisations promises (`club.forced_starters`) passent devant à leur poste.
    Les blessés à la date `day` sont écartés (sans date, tout le monde est apte).
    S'il manque des joueurs à un poste, on complète avec les meilleurs restants
    (un effectif incomplet peut quand même jouer).
    """
    available = club.available_players(day)
    by_id = {p.id: p for p in available}
    slots: list[Player | None] = [None] * len(SLOT_POSITIONS)
    taken: set[int] = set()
    for index, player_id in enumerate(club.lineup_choice[: len(SLOT_POSITIONS)]):
        if player_id in by_id and player_id not in taken:
            slots[index] = by_id[player_id]
            taken.add(player_id)

    for index, position in enumerate(SLOT_POSITIONS):
        if slots[index] is not None:
            continue
        candidates = [p for p in available if p.position == position and p.id not in taken]
        if candidates:
            rating = RATING_FOR_POSITION[position]
            pick = max(candidates, key=lambda p: (p.id in club.forced_starters, rating(p)))
            slots[index] = pick
            taken.add(pick.id)

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
    """XV de départ, banc et notes collectives ; `form` les module (neutre par défaut),
    le staff technique aussi. La feuille de match respecte le minimum de JIFF de son
    championnat (engine/regulations.py)."""
    lineup = select_lineup(club, day)
    lineup, bench = regulations.comply(
        club,
        lineup,
        select_bench(club, lineup, day),
        club.available_players(day),
        list(SLOT_POSITIONS),
        lambda position, player: RATING_FOR_POSITION[position](player),
    )
    factor = form.factor([p.id for p in lineup])
    ratings = coach(
        collective_ratings(zip(SLOT_POSITIONS, lineup, strict=False), factor=factor),
        coaching_of(club),
    )
    return TeamStrength(
        club=club,
        lineup=lineup,
        set_piece=ratings.set_piece,
        pack=ratings.pack,
        attack=ratings.attack,
        defense=ratings.defense,
        kicker=max(lineup, key=lambda p: p.kicking),
        bench=bench,
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
    return min(probability, KICK_MAX)


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
        self.coaching = coaching_of(club)  # staff technique (engine/coaching.py)
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
        captain = captain_of(club, lineup)
        self.captain_id = captain.id if captain else None
        self.weather = Weather.CLEAR  # posée par le match
        # Statistiques de chaque joueur entré en jeu (MATCH_STAT_NAMES -> nombre).
        self.stats: dict[int, dict[str, int]] = {}
        # Discours du manager (engine/team_talk.py) : l'élan multiplie les notes
        # collectives, la nervosité le risque de carton ; les deux s'estompent.
        self.spirit = 0.0
        self.heat = 0.0
        self.talks: list[team_talk.Heard] = []

    # -- Qui est où -----------------------------------------------------------------

    def players(self) -> dict[int, Player]:
        """Tous les joueurs de la feuille de match, par identifiant."""
        return {p.id: p for p in [*self.lineup, *self.bench]}

    def on_field(self, minute: int) -> list[Slot]:
        # Le test de `Slot.present`, écrit ici : appelé plusieurs fois par minute de jeu.
        return [
            s
            for s in self.slots
            if s.player is not None and (s.absent_until is None or minute >= s.absent_until)
        ]

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

    def captain(self, minute: int) -> Player | None:
        """Le capitaine, s'il est sur le terrain à cette minute."""
        slot = self.slot_of(self.captain_id) if self.captain_id is not None else None
        return slot.player if slot is not None and slot.present(minute) else None

    def captaincy(self, minute: int) -> float:
        """Ascendant du capitaine présent (0 s'il est sorti, exclu ou au banc des pénalités)."""
        captain = self.captain(minute)
        return leadership(captain) if captain else 0.0

    def effort(self, minute: int) -> float:
        """Multiplicateur de la dépense d'énergie à cette minute : infériorité
        numérique, agressivité défensive, chaleur, et semaine de préparation physique."""
        short_handed = 1 + SHORT_HANDED_EFFORT * self.missing(minute)
        defence = DEFENCE_EFFECTS[self.tactics.defence]["effort"]
        weather = WEATHER_EFFECTS[self.weather].drain
        return short_handed * defence * weather * self.coaching.endurance

    def spend_energy(self, minute: int) -> None:
        """Une minute de jeu : chaque joueur présent dépense selon son endurance."""
        effort = self.effort(minute)
        for slot in self.on_field(minute):
            player = slot.player
            left = self.energy(player) - energy_drain(player.stamina) * effort
            self.energy_left[player.id] = max(0.0, left)

    def collective(self, minute: int) -> Collective:
        """Notes collectives des joueurs présents : énergie, forme, élan, infériorité,
        staff et tactique."""
        factor = self.factor * (1 + self.spirit) * SHORT_HANDED_FACTOR ** self.missing(minute)
        ratings = coach(
            collective_ratings(
                self.fielded(minute),
                weight=lambda p: efficiency(self.energy(p)),
                factor=factor,
            ),
            self.coaching,
        )
        ratings.defense *= DEFENCE_EFFECTS[self.tactics.defence]["defense"]
        ratings.attack *= WEATHER_EFFECTS[self.weather].attack
        boost = 1 + CAPTAIN_BOOST * self.captaincy(minute)
        ratings.set_piece *= boost
        ratings.pack *= boost
        ratings.attack *= boost
        ratings.defense *= boost
        return ratings

    def scrum(self, minute: int) -> float:
        """Poussée en mêlée des avants présents, avec la forme, l'élan, l'infériorité
        et l'entraîneur des avants, comme les notes collectives."""
        factor = self.factor * (1 + self.spirit) * SHORT_HANDED_FACTOR ** self.missing(minute)
        strength = scrum_strength(self.fielded(minute), lambda p: efficiency(self.energy(p)))
        return factor * self.coaching.forwards * strength

    def territory(self, minute: int, ratings: Collective) -> float:
        kicker = self.kicker(minute)
        plan = GAME_PLAN_EFFECTS[self.tactics.game_plan]["territory"]
        if self.tactics.game_plan == GamePlan.KICKING:
            plan *= WEATHER_EFFECTS[self.weather].kicking_plan
        analysis = self.coaching.analysis
        return analysis * plan * ratings.territory(kicker.kicking if kicker else 0)

    # -- Discours ------------------------------------------------------------------------

    def hear(
        self, talk: team_talk.Talk, outcome: team_talk.Outcome, minute: int
    ) -> team_talk.Heard:
        """L'équipe entend un discours : son élan et sa nervosité bougent selon l'issue."""
        spirit = team_talk.clamp(
            self.spirit + team_talk.spirit_change(talk, outcome),
            team_talk.SPIRIT_MIN,
            team_talk.SPIRIT_MAX,
        )
        heat = team_talk.clamp(self.heat + talk.heat, team_talk.HEAT_MIN, team_talk.HEAT_MAX)
        heard = team_talk.Heard(minute, talk.key, outcome, spirit - self.spirit, heat - self.heat)
        self.spirit, self.heat = spirit, heat
        self.talks.append(heard)
        return heard

    def fade(self) -> None:
        """Une minute de jeu : l'effet des discours s'estompe."""
        self.spirit *= team_talk.SPIRIT_FADE
        self.heat *= team_talk.HEAT_FADE

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

    def auto_substitution(self, minute: int, keep: int | None = None) -> MatchEvent | None:
        """Le changement que ferait le staff à cette minute, s'il y en a un à faire.

        Il remplace le joueur qui a le moins d'énergie parmi ceux qui ont un
        remplaçant de leur poste sur le banc, en gardant un changement pour une blessure.
        Il ne sort jamais `keep` (le joueur incarné, en carrière de joueur).
        """
        if self.substitutions_left() <= AI_SUBSTITUTIONS_KEPT:
            return None
        bench = self.available_bench()
        candidates = [
            s
            for s in self.on_field(minute)
            if minute - s.since >= AI_MIN_MINUTES_ON_FIELD
            and s.player.id != keep
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

    # -- Statistiques ---------------------------------------------------------------------

    def count(self, player_id: int, stat: str) -> None:
        """Une action de plus pour le joueur ; elle compte aussi dans sa note."""
        line = self.stats.setdefault(player_id, dict.fromkeys(MATCH_STAT_NAMES, 0))
        line[stat] += 1
        if stat in STAT_RATING:
            self.rate(player_id, STAT_RATING[stat])

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
            "captain_id": self.captain_id,
            "stats": {str(k): dict(v) for k, v in self.stats.items()},
            "spirit": self.spirit,
            "heat": self.heat,
            "talks": [heard.to_dict() for heard in self.talks],
        }

    @classmethod
    def from_state(cls, club: Club, state: dict) -> "Side":
        # Espoirs compris : ils suppléent les internationaux un jour de doublon.
        players = {p.id: p for p in [*club.players, *club.youths]}
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
        # Un match sauvegardé avant les capitaines et les statistiques garde le
        # capitaine désigné à sa reprise, et ses statistiques partent de zéro.
        side.captain_id = state.get("captain_id", side.captain_id)
        side.stats = {int(k): dict(v) for k, v in state.get("stats", {}).items()}
        # Un match sauvegardé avant les discours n'en a pas.
        side.spirit = state.get("spirit", 0.0)
        side.heat = state.get("heat", 0.0)
        side.talks = [team_talk.Heard.from_dict(heard) for heard in state.get("talks", [])]
        return side


# --- Le match, minute par minute ---------------------------------------------------------


class LiveMatch:
    """Un match qu'on joue minute par minute, avec la main sur les bancs.

    `step()` joue la minute suivante ; `advance(n)` en joue plusieurs ; entre deux,
    on peut changer la tactique d'une équipe (`set_tactics`) ou faire un
    remplacement (`substitute`). Les équipes de `auto` sont gérées par le staff
    (remplacements automatiques) ; une équipe hors de `auto` ne change de joueur
    que sur blessure ou sur ordre du manager, et décide elle-même des pénalités
    d'une fin de match serrée : le match attend alors `decide` (`crunch`).
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
        weather: Weather = Weather.CLEAR,
        crowd: Crowd | None = None,
        derby: bool = False,
        hero: int | None = None,
        hero_entry: int = dilemmas.HERO_ENTRY_MINUTE,
        hero_confidence: float = 0.0,
        hero_hurt: bool = False,
        final: bool = False,
        coach: int | None = None,
    ) -> None:
        self.rng = rng or random.Random()
        self.matchday = matchday
        self.neutral = neutral
        self.day = day
        self.knockout = knockout
        self.derby = derby  # data/derbies.py
        self.auto = set(auto) if auto is not None else {home.id, away.id}
        home_team = team_strength(home, day, home_form)
        away_team = team_strength(away, day, away_form)
        self.home = Side(home, home_team.lineup, home_team.bench, home_form, home_tactics)
        self.away = Side(away, away_team.lineup, away_team.bench, away_form, away_tactics)
        self.weather = weather
        self.home.weather = self.away.weather = weather
        self.crowd = None if neutral else crowd  # public de l'équipe qui reçoit
        self.roar = 0.0  # élan du public, qui réagit au score (engine/crowd.py)
        self.events: list[MatchEvent] = []
        # Une barre par minute jouée (engine/momentum.py), positive pour l'équipe qui reçoit.
        self.momentum: list[int] = []
        self.minute = 0  # dernière minute jouée
        self.extra_time = False
        self.finished = False
        self.crunch: Crunch | None = None  # la pénalité qui attend la décision du manager
        self.crunch_at: int | None = None  # minute du dernier choix crucial offert
        # Carrière de joueur (engine/dilemmas.py) : le joueur incarné, le dilemme qui
        # l'attend, et comment se sont finis les précédents.
        self.hero = hero
        self.hero_entry = hero_entry  # minute où il entre s'il est sur le banc
        self.hero_confidence = hero_confidence  # de -1 à 1 (engine/dilemmas.py)
        self.hero_hurt = hero_hurt  # joue blessé
        self.final = final
        self.coach = coach  # le club dont le manager tranche des dilemmes pour ses joueurs
        self.dilemma: dilemmas.Dilemma | None = None
        self.outcomes: list[dilemmas.Outcome] = []
        if hero is not None:
            self._call_up(hero)

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
    def stakes(self) -> bool:
        """Match à enjeu (élimination directe, derby) : une fin serrée y donne toujours
        un choix crucial au manager."""
        return self.knockout or self.derby

    def hero_side(self) -> Side | None:
        """L'équipe du joueur incarné (None hors carrière de joueur, ou s'il ne joue pas)."""
        if self.hero is None:
            return None
        return next((side for side in self.sides if self.hero in side.players()), None)

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
            weather=self.weather.value,
            stats=self.player_stats(),
            spectators=self.crowd.spectators if self.crowd else None,
            atmosphere=self.crowd.atmosphere if self.crowd else None,
            momentum=list(self.momentum),
        )

    def player_stats(self) -> dict[int, PlayerMatchStats]:
        """Statistiques, minutes et note de chaque joueur entré en jeu, à cette minute."""
        stats = {}
        for side in self.sides:
            for player_id, entered in side.entered_at.items():
                line = side.stats.get(player_id, {})
                stats[player_id] = PlayerMatchStats(
                    minutes=max(0, side.off.get(player_id, self.minute) - entered),
                    rating=round(side.ratings.get(player_id, RATING_START), 1),
                    **line,
                )
        return stats

    # -- Ordres du manager ------------------------------------------------------------------

    def set_tactics(self, club_id: int, tactics: Tactics) -> None:
        self.side(club_id).tactics = tactics

    def talk_moment(self, club_id: int) -> team_talk.Moment | None:
        """Où le manager de ce club peut prendre la parole maintenant (None : pas
        maintenant). Au vestiaire, un discours par passage ; au bord du terrain, un
        toutes les 10 minutes."""
        if self.finished:
            return None
        talks = self.side(club_id).talks
        last = talks[-1].minute if talks else None
        if self.minute == 0:
            return team_talk.Moment.KICKOFF if last is None else None
        if self.minute == HALF_TIME or (self.extra_time and self.minute == MATCH_MINUTES):
            return team_talk.Moment.BREAK if last != self.minute else None
        if last is not None and self.minute < last + team_talk.TOUCHLINE_COOLDOWN:
            return None
        return team_talk.Moment.TOUCHLINE

    def next_talk(self, club_id: int) -> int | None:
        """Minute à partir de laquelle le manager pourra reparler du bord du terrain,
        s'il ne le peut pas maintenant (None sinon, ou si le match est fini)."""
        talks = self.side(club_id).talks
        if self.finished or not talks or self.talk_moment(club_id) is not None:
            return None
        return max(talks[-1].minute + team_talk.TOUCHLINE_COOLDOWN, self.minute + 1)

    def talk_odds(self, club_id: int, talk: team_talk.Talk) -> tuple[float, float]:
        """(chance de porter, chance de se retourner) d'un discours, à cette minute."""
        side = self.side(club_id)
        margin = self.score(club_id) - self.score(self.opponent(side).club.id)
        present = [slot.player for slot in side.on_field(self.minute)]
        return team_talk.odds(talk, margin, side.form.morale, present)

    def talk(self, club_id: int, key: str) -> team_talk.Heard:
        """Le manager parle à son équipe ; lève ValueError si ce n'est pas le moment."""
        moment = self.talk_moment(club_id)
        if moment is None:
            raise ValueError("Ce n'est pas le moment de parler à l'équipe")
        talk = team_talk.TALKS.get(key)
        if talk is None or moment not in talk.moments:
            raise ValueError("Ce discours n'est pas de circonstance")
        success, backfire = self.talk_odds(club_id, talk)
        outcome = team_talk.outcome(self.rng.random(), success, backfire)
        return self.side(club_id).hear(talk, outcome, self.minute)

    def substitute(self, club_id: int, player_out: int, player_in: int) -> MatchEvent:
        """Remplacement décidé par le manager, effectif à la minute en cours."""
        if self.finished:
            raise ValueError("Le match est terminé")
        event = self.side(club_id).substitute(player_out, player_in, self.minute)
        self.events.append(event)
        return event

    def penalty_odds(self, club_id: int) -> dict[PenaltyOption, float]:
        """Chances de chaque choix pour la pénalité en attente : réussir le coup de pied
        aux perches, ou marquer l'essai par les autres voies."""
        crunch = self.crunch
        if crunch is None or crunch.club_id != club_id:
            raise ValueError("Aucune décision à prendre")
        side = self.side(club_id)
        other = self.opponent(side)
        minute = crunch.minute
        att, dfn = side.collective(minute), other.collective(minute)
        kicker = side.kicker(minute)
        odds = {PenaltyOption.KICK: self._kick_probability(side, kicker) if kicker else 0.0}
        for option in (PenaltyOption.TOUCH, PenaltyOption.SCRUM, PenaltyOption.PLAY):
            odds[option] = self._penalty_try_odds(side, other, att, dfn, minute, option)
        return odds

    def conversion_odds(self, club_id: int) -> float:
        """Chance que le buteur du moment transforme un essai."""
        side = self.side(club_id)
        kicker = side.kicker(self.minute)
        return self._kick_probability(side, kicker, is_conversion=True) if kicker else 0.0

    def decide(self, club_id: int, option: PenaltyOption) -> list[MatchEvent]:
        """Le manager joue la pénalité en attente ; la minute se termine (le coup de
        sifflet final peut tomber). Renvoie ce qui s'est passé ; ValueError s'il n'y
        a rien à décider."""
        crunch = self.crunch
        if crunch is None or crunch.club_id != club_id:
            raise ValueError("Aucune décision à prendre")
        side = self.side(club_id)
        other = self.opponent(side)
        minute = crunch.minute
        before = len(self.events)
        att, dfn = side.collective(minute), other.collective(minute)
        self._penalty(side, other, att, dfn, minute, option)
        self.crunch = None
        fresh = self.events[before:]
        self._crowd_reacts(fresh)
        self.momentum[-1] = momentum.minute_bar(
            self.home.club.id,
            crunch.play,
            crunch.chance,
            [e for e in self.events if e.minute == minute],
        )
        self._whistle(minute)
        return fresh

    # -- Déroulement ----------------------------------------------------------------------

    def advance(self, minutes: int = 1) -> list[MatchEvent]:
        """Joue `minutes` minutes (ou jusqu'à la fin) et renvoie les événements survenus."""
        before = len(self.events)
        for _ in range(minutes):
            if self.finished or self.crunch is not None or self.dilemma is not None:
                break
            self.step()
        return self.events[before:]

    def play_to_end(self) -> Match:
        """Joue jusqu'au bout ; le staff décide des pénalités en attente."""
        while not self.finished:
            if self.dilemma is not None:
                # Le joueur incarné qui ne choisit pas joue la sécurité.
                situation = dilemmas.SITUATIONS_BY_KEY[self.dilemma.situation]
                self.choose(dilemmas.safest(situation).key)
                continue
            crunch = self.crunch
            if crunch is None:
                self.step()
                continue
            side = self.side(crunch.club_id)
            margin = self.score(side.club.id) - self.score(self.opponent(side).club.id)
            self.decide(crunch.club_id, staff_penalty(margin))
        return self.result()

    def step(self) -> None:
        """Joue la minute suivante (rien tant qu'une décision attend)."""
        if self.finished or self.crunch is not None or self.dilemma is not None:
            return
        minute = self.minute + 1
        before = len(self.events)
        self._minute_chance = None
        self._minute_play = {}  # points de jeu de la minute, par club (engine/momentum.py)
        self._play_minute(minute)
        self._crowd_reacts(self.events[before:])
        self.momentum.append(
            momentum.minute_bar(
                self.home.club.id, self._minute_play, self._minute_chance, self.events[before:]
            )
        )
        self.minute = minute
        if self.crunch is None:
            self._whistle(minute)
        if self.crunch is None and not self.finished:
            self._dilemma_due(minute)

    def _whistle(self, minute: int) -> None:
        """La minute jouée finit-elle le match, ou mène-t-elle à la prolongation ?"""
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
            side.fade()
        for side in self.sides:
            if side.club.id in self.auto and minute in AI_SUBSTITUTION_MINUTES:
                event = side.auto_substitution(minute, keep=self.hero)
                if event is not None:
                    self.events.append(event)
        if self.hero is not None and minute == self.hero_entry:
            self._hero_enters(minute)

        home_ratings = self.home.collective(minute)
        away_ratings = self.away.collective(minute)
        self._drift_ratings(minute, home_ratings, away_ratings)
        advantage = self.home_advantage
        home_share = _win_probability(
            self.home.territory(minute, home_ratings) * advantage,
            self.away.territory(minute, away_ratings),
        )
        self._phases(minute, home_share, home_ratings, away_ratings)
        self._lineout(minute)

        # Match à enjeu serré sans pénalité pour le manager : le jeu lui en offre une.
        for side in self.sides:
            if self._crunch_due(side, minute):
                self._minute_chance = (side.club.id, momentum.threat(0.0, 1.0))
                self._offer(side, minute)
                return

        if rng.random() >= CHANCE_PER_MINUTE:
            return
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
        cards = DEFENCE_EFFECTS[side.tactics.defence]["cards"] * (1 + side.heat)
        cards *= 1 - CAPTAIN_CARDS * side.captaincy(minute)
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
        success = self.rng.random() < self._kick_probability(side, kicker)
        event_type = EventType.PENALTY_GOAL if success else EventType.PENALTY_MISSED
        self.events.append(MatchEvent(minute, event_type, side.club.id, kicker.id))
        side.rate(kicker.id, RATING_EVENT[event_type])

    # -- Le public ---------------------------------------------------------------------

    def _crowd_reacts(self, events: list[MatchEvent]) -> None:
        """Le public de l'équipe qui reçoit réagit aux points de la minute."""
        if self.crowd is None:
            return
        home = self.home.club.id
        scored = [
            "try" if e.type == EventType.TRY else "kick"
            for e in events
            if e.club_id == home and e.type in CROWD_SCORES
        ]
        conceded = sum(1 for e in events if e.club_id != home and e.type == EventType.TRY)
        self.roar = crowds.roar_after(self.roar, self.crowd.atmosphere, scored, conceded)

    @property
    def margin(self) -> int:
        """Points d'avance de l'équipe qui reçoit."""
        return self.score(self.home.club.id) - self.score(self.away.club.id)

    @property
    def atmosphere(self) -> float | None:
        """L'ambiance du moment (None sans public à soi : terrain neutre, match amical)."""
        if self.crowd is None:
            return None
        return crowds.live_atmosphere(self.crowd.atmosphere, self.roar, self.margin, self.minute)

    @property
    def mood(self) -> str | None:
        """Ce que fait le stade en ce moment (engine/crowd.py, `Mood`)."""
        if self.crowd is None:
            return None
        return crowds.mood(self.roar, self.margin, self.minute)

    @property
    def home_advantage(self) -> float:
        """Multiplicateur du territoire de l'équipe qui reçoit : l'ambiance du moment."""
        if self.neutral:
            return 1.0
        atmosphere = self.atmosphere
        return crowds.advantage(atmosphere) if atmosphere is not None else HOME_ADVANTAGE

    def _kick_probability(self, side: Side, kicker: Player, is_conversion: bool = False) -> float:
        """Réussite d'un coup de pied au but : l'entraîneur du jeu au pied, le vent, la
        pluie, et les sifflets du public adverse pour l'équipe qui se déplace."""
        probability = kick_success_probability(kicker.kicking, is_conversion)
        probability += side.coaching.kicking + WEATHER_EFFECTS[self.weather].kicking
        if side is self.away and self.crowd is not None:
            probability -= crowds.hostility(self.atmosphere)
        return min(max(0.05, probability), KICK_MAX)

    def _try(
        self,
        attacking: Side,
        defending: Side,
        minute: int,
        forwards: bool = False,
        scorer: Player | None = None,
        excluded: int | None = None,
    ) -> None:
        """Un essai et sa transformation ; `forwards` : marqué au bout d'un maul,
        par un avant (le talonneur et la troisième ligne le plus souvent). `scorer` :
        le marqueur, s'il est déjà connu ; sinon tiré parmi les présents, sauf `excluded`
        (celui qui a fait la passe)."""
        rng = self.rng
        if scorer is None:
            present = [s for s in attacking.on_field(minute) if s.player.id != excluded]
            present = present or attacking.on_field(minute)
            if forwards:
                present = [s for s in present if s.position.is_forward] or present
                weights = [
                    MAUL_SCORER_WEIGHT.get(s.position, 1.0) * s.player.power for s in present
                ]
            else:
                weights = [
                    TRY_SCORER_WEIGHT[s.position] * (s.player.pace + s.player.power)
                    for s in present
                ]
            scorer = rng.choices([s.player for s in present], weights=weights)[0]
        self.events.append(MatchEvent(minute, EventType.TRY, attacking.club.id, scorer.id))
        attacking.rate_present(minute, RATING_TEAM_SCORED)
        attacking.rate(scorer.id, RATING_EVENT[EventType.TRY])
        defending.rate_present(minute, RATING_TEAM_CONCEDED)

        kicker = attacking.kicker(minute)
        converted = rng.random() < self._kick_probability(attacking, kicker, is_conversion=True)
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
        weather = WEATHER_EFFECTS[self.weather]
        hands = weather.hands if attacking.tactics.game_plan == GamePlan.HANDS else 1.0
        # Les probabilités valent TRY_RATE / PENALTY_RATE entre équipes égales
        # (_win_probability = 0.5) et varient avec l'écart de niveau, la tactique et la météo.
        try_probability = (
            (2 * TRY_RATE * _win_probability(att.attack, dfn.defense) * plan["tries"])
            * their_plan["conceded"]
            * weather.tries
            * hands
        )
        penalty_probability = (
            2
            * PENALTY_RATE
            * _win_probability(att.forward_dominance, dfn.forward_dominance)
            * plan["penalties"]
            * their_defence["fouls"]
            * weather.penalties
        )
        # Pour le momentum : ce que l'action avait de chances de finir en points.
        self._minute_chance = (
            attacking.club.id,
            momentum.threat(try_probability, penalty_probability),
        )
        roll = rng.random()

        # 1) Essai, suivi d'une tentative de transformation.
        if roll < try_probability:
            self._try(attacking, defending, minute)
            return

        # 2) Pénalité en position : tentée face aux perches, ou jouée à la main ; en fin
        # de match serrée, le manager décide.
        if roll < try_probability + penalty_probability:
            if self._crunch(attacking, minute):
                self._offer(attacking, minute)
                return
            option = PenaltyOption(attacking.tactics.penalties.value)
            self._penalty(attacking, defending, att, dfn, minute, option)
            return

        # 3) Drop de l'ouvreur (on ne garde que les drops réussis, les ratés sont anecdotiques).
        if roll < try_probability + penalty_probability + DROP_RATE * weather.drops:
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

    def _penalty(
        self,
        attacking: Side,
        defending: Side,
        att: Collective,
        dfn: Collective,
        minute: int,
        option: PenaltyOption,
    ) -> None:
        """Une pénalité en position, jouée selon `option`."""
        if option == PenaltyOption.KICK:
            self._penalty_kick(attacking, minute)
            return
        odds = self._penalty_try_odds(attacking, defending, att, dfn, minute, option)
        if self.rng.random() < odds:
            # Au bout du maul ou de la mêlée, c'est un avant qui marque.
            self._try(attacking, defending, minute, forwards=option != PenaltyOption.PLAY)

    def _penalty_try_odds(
        self,
        attacking: Side,
        defending: Side,
        att: Collective,
        dfn: Collective,
        minute: int,
        option: PenaltyOption,
    ) -> float:
        """Chance d'essai d'une pénalité jouée à la main, en touche ou en mêlée."""
        if option == PenaltyOption.PLAY:
            return 2 * PLAY_PENALTY_TRY_RATE * _win_probability(att.attack, dfn.defense)
        if option == PenaltyOption.TOUCH:
            duel = _win_probability(att.forward_dominance, dfn.forward_dominance)
            return 2 * TOUCH_PENALTY_TRY_RATE * duel
        duel = _win_probability(attacking.scrum(minute), defending.scrum(minute))
        return 2 * SCRUM_PENALTY_TRY_RATE * duel

    # -- Le choix crucial --------------------------------------------------------------

    def _crunch(self, side: Side, minute: int) -> bool:
        """Fin de match serrée pour une équipe menée par son manager : ses pénalités
        attendent sa décision."""
        if side.club.id in self.auto or minute <= self.last_minute - CRUNCH_MINUTES:
            return False
        margin = self.score(side.club.id) - self.score(self.opponent(side).club.id)
        return abs(margin) <= CRUNCH_MARGIN

    def _crunch_due(self, side: Side, minute: int) -> bool:
        """Le jeu offre-t-il sa pénalité au manager cette minute ? Dans un match à
        enjeu, une fois par fin serrée, à une minute au hasard, s'il n'en a pas eu
        d'elle-même."""
        if not self.stakes or not self._crunch(side, minute):
            return False
        if self.crunch_at is not None and self.crunch_at > self.last_minute - CRUNCH_MINUTES:
            return False
        return self.rng.random() < 1 / (self.last_minute - minute + 1)

    def _offer(self, side: Side, minute: int) -> None:
        """La pénalité attend la décision du manager : le match s'arrête là."""
        self.crunch = Crunch(minute, side.club.id, dict(self._minute_play), self._minute_chance)
        self.crunch_at = minute

    # -- Le joueur incarné (carrière de joueur) -------------------------------------------

    def _call_up(self, player_id: int) -> None:
        """Le staff garde au joueur incarné une place dans le groupe : sur le banc, à la
        place du remplaçant de son poste (ou du dernier), s'il n'est pas dans le XV.
        Rien s'il n'est pas apte (blessé, suspendu, retenu en sélection)."""
        for side in self.sides:
            if player_id in side.players():
                return
            player = next(
                (p for p in side.club.available_players(self.day) if p.id == player_id), None
            )
            if player is None:
                continue
            same = [i for i, p in enumerate(side.bench) if p.position == player.position]
            if same:
                side.bench[same[-1]] = player
            elif len(side.bench) >= BENCH_SIZE:
                side.bench[-1] = player
            else:
                side.bench.append(player)
            return

    def _hero_enters(self, minute: int) -> None:
        """Le joueur incarné, resté sur le banc, entre à son poste à l'heure de jeu, à la
        place du plus fatigué."""
        side = self.hero_side()
        if side is None or side.club.id not in self.auto or side.substitutions_left() <= 0:
            return
        hero = next((p for p in side.available_bench() if p.id == self.hero), None)
        if hero is None:
            return
        slots = [s for s in side.on_field(minute) if s.position == hero.position]
        if not slots:
            return
        tired = min(slots, key=lambda s: side.energy(s.player))
        self.events.append(side.substitute(tired.player.id, hero.id, minute))

    def _hero_slot(self, minute: int) -> tuple[Side, Slot] | None:
        side = self.hero_side()
        slot = side.slot_of(self.hero) if side is not None else None
        if slot is None or not slot.present(minute):
            return None
        return side, slot

    def _dilemma_due(self, minute: int) -> None:
        """Le match s'arrête-t-il sur un dilemme du joueur incarné ? Seulement s'il est sur
        le terrain, pas trop tôt après le précédent, et pas à la dernière minute."""
        if self.hero is None:
            self._coach_dilemma_due(minute)
            return
        if minute >= self.last_minute:
            return
        found = self._hero_slot(minute)
        if found is None or len(self.outcomes) >= dilemmas.DILEMMA_MAX:
            return
        last = self.outcomes[-1] if self.outcomes else None
        if last is not None and minute - last.minute < dilemmas.DILEMMA_GAP:
            return
        if self.rng.random() >= dilemmas.DILEMMA_CHANCE:
            return
        side, slot = found
        situation = dilemmas.draw(slot.position, last.situation if last else None, self.rng)
        self.dilemma = dilemmas.Dilemma(
            minute,
            situation.key,
            dict(self._minute_play),
            self._minute_chance,
            pressure=self._pressure(side, minute),
        )

    def _coach_dilemma_due(self, minute: int) -> None:
        """Le match s'arrête-t-il sur un dilemme pour le manager (`coach`) ? Pour un de ses
        joueurs sur le terrain, tiré au hasard ; plus rarement qu'en carrière de joueur."""
        if self.coach is None or minute >= self.last_minute:
            return
        if len(self.outcomes) >= dilemmas.COACH_DILEMMA_MAX:
            return
        last = self.outcomes[-1] if self.outcomes else None
        if last is not None and minute - last.minute < dilemmas.COACH_DILEMMA_GAP:
            return
        if self.rng.random() >= dilemmas.COACH_DILEMMA_CHANCE:
            return
        side = self.side(self.coach)
        present = side.on_field(minute)
        if not present:
            return
        slot = self.rng.choice(present)
        situation = dilemmas.draw(slot.position, last.situation if last else None, self.rng)
        self.dilemma = dilemmas.Dilemma(
            minute,
            situation.key,
            dict(self._minute_play),
            self._minute_chance,
            pressure=self._pressure(side, minute),
            player_id=slot.player.id,
        )

    def _actor(self, dilemma: dilemmas.Dilemma) -> tuple[Side, Player]:
        """Le joueur d'un dilemme et son équipe : le joueur incarné, ou celui du manager."""
        player_id = self.hero if dilemma.player_id is None else dilemma.player_id
        side = next(side for side in self.sides if player_id in side.players())
        return side, side.players()[player_id]

    def _pressure(self, side: Side, minute: int) -> float:
        margin = self.score(side.club.id) - self.score(self.opponent(side).club.id)
        return dilemmas.pressure(minute, self.last_minute, margin, self.knockout, self.final)

    def advance_to_hero(self) -> list[MatchEvent]:
        """Joue jusqu'à l'entrée en jeu du joueur incarné resté sur le banc (ou jusqu'à
        ce que le match s'arrête : un dilemme, un choix crucial, la fin)."""
        before = len(self.events)
        side = self.hero_side()
        while not self.finished and self.crunch is None and self.dilemma is None:
            waiting = side is not None and any(p.id == self.hero for p in side.available_bench())
            if not waiting:
                break
            self.step()
        return self.events[before:]

    def dilemma_reward(self, choice: dilemmas.Option) -> float:
        """Ce qu'une voie réussie rapporte à la note du joueur incarné, la pression du
        moment et l'action qu'elle déclenche comprises (son essai, son drop, l'essai de
        l'équipe)."""
        bonus = {
            dilemmas.Effect.TRY: RATING_EVENT[EventType.TRY] + RATING_TEAM_SCORED,
            dilemmas.Effect.ASSIST: RATING_TEAM_SCORED,
            dilemmas.Effect.DROP: RATING_EVENT[EventType.DROP_GOAL],
        }
        pressure = self.dilemma.pressure if self.dilemma else 1.0
        return round(choice.reward * pressure + bonus.get(choice.on_success, 0.0), 2)

    def dilemma_cost(self, choice: dilemmas.Option) -> float:
        """Ce qu'une voie ratée coûte à la note, la pression du moment comprise."""
        pressure = self.dilemma.pressure if self.dilemma else 1.0
        return round(choice.cost * pressure, 2)

    def dilemma_odds(self) -> dict[str, float]:
        """Chances de réussite de chaque voie du dilemme en attente."""
        dilemma = self.dilemma
        if dilemma is None:
            raise ValueError("Aucun dilemme en attente")
        situation = dilemmas.SITUATIONS_BY_KEY[dilemma.situation]
        side, actor = self._actor(dilemma)
        opposition = None
        if situation.opposition != dilemmas.Opposition.NONE:
            other = self.opponent(side).collective(dilemma.minute)
            opposition = getattr(other, situation.opposition.value)
        # La confiance et la blessure sont celles du joueur incarné ; un joueur du manager
        # n'apporte que ses attributs et son énergie.
        incarnated = dilemma.player_id is None
        hurt = dilemmas.HURT_FACTOR if incarnated and self.hero_hurt else 1.0
        confidence = self.hero_confidence if incarnated else 0.0
        fit = efficiency(side.energy(actor)) * hurt
        return {
            choice.key: round(
                dilemmas.success_chance(
                    dilemmas.skill(actor, choice, fit), opposition, choice, confidence
                ),
                2,
            )
            for choice in situation.options
        }

    def choose(self, key: str) -> dilemmas.Outcome:
        """Le joueur incarné (ou le manager, pour son joueur) tranche le dilemme en
        attente : la note du joueur bouge, le score parfois ; la minute se termine.
        ValueError s'il n'y a rien à trancher."""
        dilemma = self.dilemma
        if dilemma is None:
            raise ValueError("Aucun dilemme en attente")
        situation = dilemmas.SITUATIONS_BY_KEY[dilemma.situation]
        choice = dilemmas.option(situation, key)
        chance = self.dilemma_odds()[key]
        side, hero = self._actor(dilemma)
        other = self.opponent(side)
        minute = dilemma.minute
        before_rating = side.ratings.get(hero.id, RATING_START)
        before = len(self.events)
        success = self.rng.random() < chance
        if success:
            effect = choice.on_success
            side.rate(hero.id, choice.reward * dilemma.pressure)
        else:
            effect = dilemmas.failure_effect(choice, self.rng)
            side.rate(hero.id, choice.cost * dilemma.pressure)
        self._apply(effect, side, other, hero, minute)
        outcome = dilemmas.Outcome(
            minute=minute,
            situation=situation.key,
            option=choice.key,
            success=success,
            chance=chance,
            delta=round(side.ratings.get(hero.id, RATING_START) - before_rating, 2),
            effect=effect,
            pressure=dilemma.pressure,
            player_id=dilemma.player_id,
        )
        self.outcomes.append(outcome)
        self.dilemma = None
        if success and choice.follow and not self.finished:
            # La réussite en appelle une autre, aussitôt : un deux contre un...
            self.dilemma = dilemmas.Dilemma(
                minute,
                choice.follow,
                dilemma.play,
                dilemma.chance,
                pressure=dilemma.pressure,
                chained=True,
                player_id=dilemma.player_id,
            )
        fresh = self.events[before:]
        self._crowd_reacts(fresh)
        self.momentum[-1] = momentum.minute_bar(
            self.home.club.id,
            dilemma.play,
            dilemma.chance,
            [e for e in self.events if e.minute == minute],
        )
        return outcome

    def _apply(
        self, effect: dilemmas.Effect, side: Side, other: Side, hero: Player, minute: int
    ) -> None:
        """Ce que l'issue d'un dilemme change au match (engine/dilemmas.py, `Effect`)."""
        Effect = dilemmas.Effect
        if effect == Effect.TRY:
            self._try(side, other, minute, scorer=hero)
        elif effect == Effect.ASSIST:
            self._try(side, other, minute, excluded=hero.id)
        elif effect == Effect.DROP:
            self.events.append(MatchEvent(minute, EventType.DROP_GOAL, side.club.id, hero.id))
            side.rate(hero.id, RATING_EVENT[EventType.DROP_GOAL])
        elif effect == Effect.PENALTY_WON:
            self._penalty_kick(side, minute)
        elif effect == Effect.PENALTY_CONCEDED:
            self._penalty_kick(other, minute)
        elif effect == Effect.TRY_CONCEDED:
            side.count(hero.id, "missed_tackles")
            self._try(other, side, minute)
        elif effect == Effect.YELLOW:
            self.events.append(side.card(hero, minute, red=False))
            side.rate(hero.id, RATING_EVENT[EventType.YELLOW_CARD])
            self._penalty_kick(other, minute)
        elif effect == Effect.BREAK:
            side.count(hero.id, "carries")
            side.count(hero.id, "line_breaks")
        elif effect == Effect.TURNOVER:
            side.count(hero.id, "turnovers")
        elif effect == Effect.MISSED:
            side.count(hero.id, "missed_tackles")

    def _phases(self, minute: int, home_share: float, home: Collective, away: Collective) -> None:
        """Les temps de jeu de la minute : qui porte le ballon, qui plaque, qui
        manque son plaquage et laisse filer, qui gratte. La possession suit le
        territoire (`home_share`)."""
        rng = self.rng
        lines = {}
        for side in self.sides:
            present = side.on_field(minute)
            if not present:
                return
            players = [s.player for s in present]
            lines[side.club.id] = (
                players,
                list(accumulate(CARRY_WEIGHT[s.position] * s.player.power for s in present)),
                list(accumulate(TACKLE_WEIGHT[s.position] * s.player.tackling for s in present)),
                list(accumulate(TURNOVER_WEIGHT[s.position] * s.player.power for s in present)),
            )
        ratings = {self.home.club.id: home, self.away.club.id: away}
        play = self._minute_play = {self.home.club.id: 0, self.away.club.id: 0}
        for _ in range(PHASES_PER_MINUTE):
            attacking, defending = (
                (self.home, self.away) if rng.random() < home_share else (self.away, self.home)
            )
            carriers, carry_weights, _, _ = lines[attacking.club.id]
            tacklers, _, tackle_weights, turnover_weights = lines[defending.club.id]
            carrier = rng.choices(carriers, cum_weights=carry_weights)[0]
            tackler = rng.choices(tacklers, cum_weights=tackle_weights)[0]
            attacking.count(carrier.id, "carries")
            play[attacking.club.id] += momentum.PLAY_POINTS["carries"]
            duel = _win_probability(
                defending_rating(tackler) * efficiency(defending.energy(tackler)),
                carrying_rating(carrier) * efficiency(attacking.energy(carrier)),
            )
            if rng.random() < TACKLE_SUCCESS + TACKLE_SWING * (2 * duel - 1):
                defending.count(tackler.id, "tackles")
                if rng.random() < TACKLE_ASSIST:
                    helper = rng.choices(tacklers, cum_weights=tackle_weights)[0]
                    if helper is not tackler:
                        defending.count(helper.id, "tackles")
                if rng.random() < TURNOVER_PER_PHASE:
                    poacher = rng.choices(tacklers, cum_weights=turnover_weights)[0]
                    defending.count(poacher.id, "turnovers")
                    play[defending.club.id] += momentum.PLAY_POINTS["turnovers"]
                continue
            defending.count(tackler.id, "missed_tackles")
            att, dfn = ratings[attacking.club.id], ratings[defending.club.id]
            if rng.random() < 2 * LINE_BREAK_ON_MISS * _win_probability(att.attack, dfn.defense):
                attacking.count(carrier.id, "line_breaks")
                play[attacking.club.id] += momentum.PLAY_POINTS["line_breaks"]

    def _lineout(self, minute: int) -> None:
        """Une touche, parfois : le lanceur la garde le plus souvent, sinon l'adversaire la vole."""
        rng = self.rng
        if rng.random() >= LINEOUT_PER_MINUTE:
            return
        throwing, other = (self.home, self.away) if rng.random() < 0.5 else (self.away, self.home)
        ours = [s for s in throwing.on_field(minute) if s.position in JUMPER_WEIGHT]
        theirs = [s for s in other.on_field(minute) if s.position in JUMPER_WEIGHT]
        if not ours or not theirs:
            return
        duel = _win_probability(
            _average([lineout_rating(s.player) for s in ours]),
            _average([lineout_rating(s.player) for s in theirs]),
        )
        side, jumpers, stat = (
            (throwing, ours, "lineouts_won")
            if rng.random() < LINEOUT_KEEP + LINEOUT_SWING * (2 * duel - 1)
            else (other, theirs, "lineout_steals")
        )
        weights = [JUMPER_WEIGHT[s.position] * s.player.lineout for s in jumpers]
        side.count(rng.choices([s.player for s in jumpers], weights=weights)[0].id, stat)

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
            probability = self._kick_probability(teams[side], kicker) - SHOOTOUT_PRESSURE
            scored = rng.random() < probability
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
            "derby": self.derby,
            "auto": sorted(self.auto),
            "minute": self.minute,
            "extra_time": self.extra_time,
            "finished": self.finished,
            "crunch": self.crunch.to_dict() if self.crunch else None,
            "crunch_at": self.crunch_at,
            "hero": self.hero,
            "hero_entry": self.hero_entry,
            "hero_confidence": self.hero_confidence,
            "hero_hurt": self.hero_hurt,
            "final": self.final,
            "coach": self.coach,
            "dilemma": self.dilemma.to_dict() if self.dilemma else None,
            "outcomes": [outcome.to_dict() for outcome in self.outcomes],
            "weather": self.weather.value,
            "crowd": self.crowd.to_dict() if self.crowd else None,
            "roar": self.roar,
            "momentum": self.momentum,
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
        live.derby = state.get("derby", False)
        live.auto = set(state["auto"])
        live.minute = state["minute"]
        live.extra_time = state["extra_time"]
        live.finished = state["finished"]
        live.crunch = Crunch.from_dict(state["crunch"]) if state.get("crunch") else None
        live.crunch_at = state.get("crunch_at")
        live.hero = state.get("hero")
        live.hero_entry = state.get("hero_entry", dilemmas.HERO_ENTRY_MINUTE)
        live.hero_confidence = state.get("hero_confidence", 0.0)
        live.hero_hurt = state.get("hero_hurt", False)
        live.final = state.get("final", False)
        live.coach = state.get("coach")
        dilemma = state.get("dilemma")
        live.dilemma = dilemmas.Dilemma.from_dict(dilemma) if dilemma else None
        live.outcomes = [dilemmas.Outcome.from_dict(o) for o in state.get("outcomes", [])]
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
        live.weather = Weather(state.get("weather", Weather.CLEAR))
        live.crowd = Crowd.from_dict(state["crowd"]) if state.get("crowd") else None
        live.roar = state.get("roar", 0.0)
        # Un match commencé avant le graphique : les minutes déjà jouées restent vides.
        bars = state.get("momentum", [])
        live.momentum = [0] * (live.minute - len(bars)) + list(bars)
        live.home.weather = live.away.weather = live.weather
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
    weather: Weather = Weather.CLEAR,
    crowd: Crowd | None = None,
) -> Match:
    """Simule un match complet et renvoie un `Match` joué (score + événements).

    `rng` permet de fixer le hasard (ex. `random.Random(42)`) pour des résultats
    reproductibles, notamment dans les tests. `neutral` supprime l'avantage du
    terrain (finale). `day` est la date du match : les blessés ce jour-là ne
    jouent pas, et les blessures du match sont signalées en événements.
    `home_form` / `away_form` : forme du jour de chaque club (neutre par défaut).
    `knockout` : match à élimination directe, qui ne peut pas finir sur un nul
    (prolongation, puis tirs au but). Les deux bancs sont gérés par le staff.
    `weather` : le temps du match (engine/weather.py), sec par défaut. `crowd` : le
    public de l'équipe qui reçoit (engine/crowd.py), qui fait l'avantage du terrain.
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
        weather=weather,
        crowd=crowd,
    )
    return live.play_to_end()
