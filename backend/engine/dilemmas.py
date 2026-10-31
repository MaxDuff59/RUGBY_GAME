"""Les dilemmes du joueur, en carrière de joueur : les moments où le match lui revient.

Le joueur que l'on incarne (`LiveMatch.hero`) joue dans un club mené par son staff.
Tant qu'il est sur le terrain, le match s'arrête de temps en temps sur une situation
de jeu (`Situation`) : un un-contre-un, un plaquage, un ruck, une mêlée... Il choisit
une des voies proposées (`Option`) ; sa réussite se tire d'après ses attributs, face
à la ligne adverse qui s'y oppose, et son énergie du moment.

Chaque voie se joue à pile ou face entre audace et prudence : la plus risquée a le
moins de chances mais rapporte le plus à la note du joueur (sur 10), et peut décider
du score (un essai, une pénalité obtenue) ; la plus sûre rapporte peu, et coûte peu
si elle échoue. Un échec peut aussi coûter à l'équipe : un ballon perdu, une pénalité
concédée, un essai encaissé, un carton jaune.

Certaines réussites en appellent une autre aussitôt (`Option.follow`) : un
franchissement débouche sur un deux contre un, finir seul ou servir le partenaire.

La pression du moment (`pressure`) grossit ce que la note gagne ou perd : une fin de
match serrée, un match à élimination directe, plus encore une finale. Le joueur
apporte aussi sa confiance (`confidence`, de -1 à 1 : ses derniers matchs) et, s'il
joue blessé, des attributs entamés (`HURT_FACTOR`).

Le module ne connaît que les règles : tirer une situation (`draw`), chiffrer les
chances (`success_chance`), dire ce qu'un échec déclenche (`failure_effect`). Le
match (`engine/match_engine.py`) applique les effets au score et aux notes.
"""

import random
from dataclasses import dataclass
from enum import StrEnum

from models import Player, Position

# Un dilemme en moyenne toutes les 7 minutes passées sur le terrain (pas deux à moins
# de DILEMMA_GAP minutes d'écart), jamais plus de DILEMMA_MAX par match.
DILEMMA_CHANCE = 0.15
DILEMMA_GAP = 5
DILEMMA_MAX = 7
# Un remplaçant que le staff garde au chaud entre à cette minute, à son poste.
HERO_ENTRY_MINUTE = 52
# Pour un manager (ou un sélectionneur), les dilemmes portent sur un joueur de son XV : un
# peu plus rares, il a aussi les changements, les discours et le choix crucial.
COACH_DILEMMA_CHANCE = 0.06
COACH_DILEMMA_GAP = 8
COACH_DILEMMA_MAX = 4

# Chances de réussite : `Option.base` entre un joueur et une opposition de même niveau,
# plus SKILL_SWING par point d'écart, entre CHANCE_MIN et CHANCE_MAX.
SKILL_SWING = 0.035
CHANCE_MIN, CHANCE_MAX = 0.05, 0.95
# Confiance du joueur (de -1 à 1) : jusqu'à 6 points de réussite en plus, ou en moins.
CONFIDENCE_SWING = 0.06
# Joué blessé : ses attributs ne rendent que cette part.
HURT_FACTOR = 0.85

# Pression du moment : dans les 10 dernières minutes à 7 points d'écart ou moins, en
# phase finale, en finale ; les facteurs se multiplient, jusqu'à PRESSURE_MAX.
PRESSURE_LATE_MINUTES = 10
PRESSURE_MARGIN = 7
PRESSURE_LATE = 1.5
PRESSURE_KNOCKOUT = 1.25
PRESSURE_FINAL = 1.5
PRESSURE_MAX = 2.5


class Effect(StrEnum):
    """Ce que l'issue d'un dilemme change au match, au-delà de la note du joueur."""

    NONE = "none"
    TRY = "try"  # le joueur marque
    ASSIST = "assist"  # un partenaire marque sur son offrande
    BREAK = "break"  # franchissement
    DROP = "drop"  # drop réussi
    PENALTY_WON = "penalty_won"  # pénalité obtenue, tentée par le buteur
    TURNOVER = "turnover"  # ballon récupéré
    LOST = "lost"  # ballon perdu
    MISSED = "missed"  # plaquage manqué
    PENALTY_CONCEDED = "penalty_conceded"  # pénalité contre son équipe
    TRY_CONCEDED = "try_conceded"  # l'adversaire file à l'essai
    YELLOW = "yellow"  # carton jaune, et pénalité contre son équipe


class Opposition(StrEnum):
    """La note collective adverse qui s'oppose au joueur (`Collective`)."""

    DEFENSE = "defense"  # le joueur a le ballon
    ATTACK = "attack"  # l'adversaire a le ballon
    PACK = "pack"  # combat au sol
    SET_PIECE = "set_piece"  # mêlée, touche
    NONE = "none"  # personne : la réussite ne tient qu'au choix (une provocation)


@dataclass(frozen=True)
class Option:
    """Une voie : les attributs qui la font réussir (poids sur 1), ses chances à niveau
    égal, ce qu'elle rapporte ou coûte à la note du joueur, et ce qu'elle déclenche.

    `on_failure` : les effets possibles d'un échec, chacun avec sa probabilité, tirés
    dans l'ordre (le premier qui tombe l'emporte ; aucun : un échec sans conséquence)."""

    key: str
    skills: dict[str, float]
    base: float
    reward: float
    cost: float
    on_success: Effect = Effect.NONE
    on_failure: tuple[tuple[Effect, float], ...] = ()
    follow: str | None = None  # la situation qui s'enchaîne sur une réussite


@dataclass(frozen=True)
class Situation:
    key: str
    opposition: Opposition
    positions: frozenset[Position]
    options: tuple[Option, ...]
    drawable: bool = True  # False : seulement enchaînée sur une autre


FORWARDS = frozenset({Position.PROP, Position.HOOKER, Position.LOCK, Position.BACK_ROW})
BACKS = frozenset(Position) - FORWARDS
EVERYONE = frozenset(Position)

SITUATIONS = (
    Situation(
        "one_on_one",
        Opposition.DEFENSE,
        BACKS | {Position.BACK_ROW},
        (
            Option("step", {"pace": 0.6, "handling": 0.4}, 0.45, 0.8, -0.4,
                   Effect.BREAK, ((Effect.LOST, 1.0),), "two_on_one"),
            Option("fend", {"power": 0.7, "handling": 0.3}, 0.5, 0.6, -0.35,
                   Effect.BREAK, ((Effect.LOST, 1.0),), "two_on_one"),
            Option("pass", {"passing": 0.7, "handling": 0.3}, 0.75, 0.25, -0.3,
                   Effect.NONE, ((Effect.LOST, 1.0),)),
        ),
    ),
    Situation(
        "try_line",
        Opposition.DEFENSE,
        EVERYONE,
        (
            Option("dive", {"power": 0.6, "pace": 0.4}, 0.35, 0.3, -0.5,
                   Effect.TRY, ((Effect.LOST, 1.0),)),
            Option("offload", {"passing": 0.6, "handling": 0.4}, 0.45, 0.5, -0.4,
                   Effect.ASSIST, ((Effect.LOST, 1.0),)),
            Option("recycle", {"handling": 0.5, "power": 0.5}, 0.8, 0.15, -0.2,
                   Effect.PENALTY_WON, ((Effect.LOST, 0.5),)),
        ),
    ),
    Situation(
        "tackle",
        Opposition.ATTACK,
        EVERYONE,
        (
            Option("smash", {"tackling": 0.6, "power": 0.4}, 0.5, 0.6, -0.6,
                   Effect.TURNOVER, ((Effect.TRY_CONCEDED, 0.35), (Effect.MISSED, 1.0))),
            Option("hold", {"tackling": 0.7, "pace": 0.3}, 0.8, 0.2, -0.4,
                   Effect.NONE, ((Effect.TRY_CONCEDED, 0.2), (Effect.MISSED, 1.0))),
            Option("ball", {"power": 0.6, "tackling": 0.4}, 0.55, 0.5, -0.7,
                   Effect.TURNOVER, ((Effect.YELLOW, 0.35), (Effect.PENALTY_CONCEDED, 1.0))),
        ),
    ),
    Situation(
        "ruck",
        Opposition.PACK,
        FORWARDS | {Position.CENTRE, Position.SCRUM_HALF},
        (
            Option("jackal", {"power": 0.5, "tackling": 0.5}, 0.4, 0.7, -0.5,
                   Effect.TURNOVER, ((Effect.PENALTY_CONCEDED, 0.7),)),
            Option("counter", {"power": 0.8, "stamina": 0.2}, 0.55, 0.4, -0.25,
                   Effect.TURNOVER),
            Option("fold", {"tackling": 0.6, "stamina": 0.4}, 0.85, 0.1, -0.2),
        ),
    ),
    Situation(
        "scrum",
        Opposition.SET_PIECE,
        frozenset({Position.PROP, Position.HOOKER, Position.LOCK}),
        (
            Option("drive", {"scrum": 0.7, "power": 0.3}, 0.45, 0.7, -0.5,
                   Effect.PENALTY_WON, ((Effect.PENALTY_CONCEDED, 0.8),)),
            Option("steady", {"scrum": 0.6, "stamina": 0.4}, 0.8, 0.2, -0.3,
                   Effect.NONE, ((Effect.LOST, 1.0),)),
        ),
    ),
    Situation(
        "lineout",
        Opposition.SET_PIECE,
        frozenset({Position.LOCK, Position.BACK_ROW}),
        (
            Option("maul", {"lineout": 0.5, "power": 0.5}, 0.35, 0.4, -0.4,
                   Effect.TRY, ((Effect.LOST, 1.0),)),
            Option("front", {"lineout": 0.8, "handling": 0.2}, 0.8, 0.2, -0.3,
                   Effect.NONE, ((Effect.LOST, 1.0),)),
        ),
    ),
    Situation(
        "kick",
        Opposition.DEFENSE,
        frozenset({Position.SCRUM_HALF, Position.FLY_HALF, Position.CENTRE, Position.FULLBACK}),
        (
            Option("drop", {"kicking": 1.0}, 0.35, 0.1, -0.4, Effect.DROP),
            Option("grubber", {"kicking": 0.6, "pace": 0.4}, 0.4, 0.6, -0.3,
                   Effect.BREAK, ((Effect.LOST, 1.0),), "two_on_one"),
            Option("hands", {"passing": 0.7, "handling": 0.3}, 0.75, 0.2, -0.2,
                   Effect.NONE, ((Effect.LOST, 1.0),)),
        ),
    ),
    Situation(
        "cross_kick",
        Opposition.DEFENSE,
        frozenset({Position.FLY_HALF}),
        (
            Option("cross", {"kicking": 0.8, "passing": 0.2}, 0.35, 0.5, -0.4,
                   Effect.ASSIST, ((Effect.LOST, 1.0),)),
            Option("flat", {"passing": 0.7, "handling": 0.3}, 0.45, 0.5, -0.4,
                   Effect.BREAK, ((Effect.LOST, 1.0),), "two_on_one"),
            Option("touch", {"kicking": 1.0}, 0.8, 0.15, -0.2, Effect.NONE, ((Effect.LOST, 0.5),)),
        ),
    ),
    Situation(
        "box_kick",
        Opposition.DEFENSE,
        frozenset({Position.SCRUM_HALF}),
        (
            Option("box", {"kicking": 0.8, "pace": 0.2}, 0.5, 0.4, -0.3,
                   Effect.TURNOVER, ((Effect.LOST, 1.0),)),
            Option("snipe", {"pace": 0.6, "power": 0.4}, 0.4, 0.6, -0.4,
                   Effect.BREAK, ((Effect.LOST, 1.0),), "two_on_one"),
            Option("serve", {"passing": 1.0}, 0.85, 0.1, -0.2, Effect.NONE, ((Effect.LOST, 1.0),)),
        ),
    ),
    Situation(
        "touchline",
        Opposition.DEFENSE,
        frozenset({Position.WING}),
        (
            Option("outside", {"pace": 0.8, "power": 0.2}, 0.4, 0.6, -0.4,
                   Effect.BREAK, ((Effect.LOST, 1.0),), "two_on_one"),
            Option("inside", {"pace": 0.4, "handling": 0.6}, 0.5, 0.4, -0.3,
                   Effect.BREAK, ((Effect.LOST, 1.0),)),
            Option("chip", {"kicking": 0.6, "pace": 0.4}, 0.25, 0.2, -0.4,
                   Effect.TRY, ((Effect.LOST, 1.0),)),
        ),
    ),
    Situation(
        "counter",
        Opposition.ATTACK,
        frozenset({Position.FULLBACK, Position.WING}),
        (
            Option("run", {"pace": 0.5, "handling": 0.3, "power": 0.2}, 0.4, 0.7, -0.5,
                   Effect.BREAK, ((Effect.PENALTY_CONCEDED, 0.3), (Effect.LOST, 1.0)),
                   "two_on_one"),
            Option("up_and_under", {"kicking": 0.7, "pace": 0.3}, 0.45, 0.4, -0.3,
                   Effect.TURNOVER, ((Effect.LOST, 1.0),)),
            Option("touch", {"kicking": 1.0}, 0.8, 0.15, -0.2, Effect.NONE, ((Effect.LOST, 0.5),)),
        ),
    ),
    Situation(
        "throw",
        Opposition.SET_PIECE,
        frozenset({Position.HOOKER}),
        (
            Option("back", {"lineout": 0.8, "handling": 0.2}, 0.4, 0.5, -0.4,
                   Effect.BREAK, ((Effect.LOST, 1.0),)),
            Option("maul", {"lineout": 0.5, "power": 0.5}, 0.4, 0.3, -0.4,
                   Effect.TRY, ((Effect.LOST, 1.0),)),
            Option("front", {"lineout": 1.0}, 0.85, 0.15, -0.3, Effect.NONE, ((Effect.LOST, 1.0),)),
        ),
    ),
    Situation(
        "provocation",
        Opposition.NONE,
        EVERYONE,
        (
            Option("hit_back", {"power": 1.0}, 0.45, 0.3, -0.8,
                   Effect.NONE, ((Effect.YELLOW, 0.7), (Effect.PENALTY_CONCEDED, 1.0))),
            Option("referee", {"stamina": 1.0}, 0.5, 0.3, -0.1, Effect.PENALTY_WON),
            Option("walk_away", {"stamina": 1.0}, 0.95, 0.1, 0.0),
        ),
    ),
    Situation(
        "two_on_one",
        Opposition.DEFENSE,
        EVERYONE,
        (
            Option("finish", {"pace": 0.6, "power": 0.4}, 0.45, 0.2, -0.4,
                   Effect.TRY, ((Effect.LOST, 1.0),)),
            Option("dummy", {"pace": 0.5, "handling": 0.5}, 0.35, 0.4, -0.4,
                   Effect.TRY, ((Effect.LOST, 1.0),)),
            Option("give", {"passing": 0.7, "handling": 0.3}, 0.75, 0.5, -0.3,
                   Effect.ASSIST, ((Effect.LOST, 1.0),)),
        ),
        drawable=False,
    ),
)  # fmt: skip
SITUATIONS_BY_KEY = {situation.key: situation for situation in SITUATIONS}


def option(situation: Situation, key: str) -> Option:
    found = next((o for o in situation.options if o.key == key), None)
    if found is None:
        raise ValueError(f"Voie « {key} » inconnue")
    return found


def safest(situation: Situation) -> Option:
    """La voie que prend un joueur qui ne choisit pas : la plus sûre."""
    return max(situation.options, key=lambda o: o.base)


def draw(position: Position, last: str | None, rng: random.Random) -> Situation:
    """Une situation qui se présente au joueur à son poste, pas deux fois la même de suite."""
    pool = [s for s in SITUATIONS if s.drawable and position in s.positions]
    fresh = [s for s in pool if s.key != last] or pool
    return rng.choice(fresh)


def skill(player: Player, choice: Option, energy_efficiency: float = 1.0) -> float:
    """Ce que le joueur met dans cette voie (sur 20), entamé par la fatigue."""
    return energy_efficiency * sum(w * getattr(player, name) for name, w in choice.skills.items())


def success_chance(
    skill_value: float, opposition: float | None, choice: Option, confidence: float = 0.0
) -> float:
    """Chances de réussite : `opposition` à None, rien que la voie et la confiance."""
    gap = 0.0 if opposition is None else skill_value - opposition
    chance = choice.base + SKILL_SWING * gap + CONFIDENCE_SWING * confidence
    return min(CHANCE_MAX, max(CHANCE_MIN, chance))


def pressure(minute: int, last_minute: int, margin: int, knockout: bool, final: bool) -> float:
    """Ce que pèse une action à ce moment du match (1 : un moment ordinaire)."""
    factor = 1.0
    if minute > last_minute - PRESSURE_LATE_MINUTES and abs(margin) <= PRESSURE_MARGIN:
        factor *= PRESSURE_LATE
    if knockout:
        factor *= PRESSURE_KNOCKOUT
    if final:
        factor *= PRESSURE_FINAL
    return round(min(factor, PRESSURE_MAX), 2)


def failure_effect(choice: Option, rng: random.Random) -> Effect:
    for effect, probability in choice.on_failure:
        if rng.random() < probability:
            return effect
    return Effect.NONE


@dataclass
class Dilemma:
    """Une situation qui attend le choix du joueur, et de quoi finir sa minute (comme
    `Crunch`, engine/match_engine.py)."""

    minute: int
    situation: str
    play: dict[int, int]
    chance: tuple[int, float] | None
    pressure: float = 1.0
    chained: bool = False  # enchaîné sur une réussite (`Option.follow`)
    # Le joueur concerné : celui du manager qui tranche pour lui ; None, le joueur incarné.
    player_id: int | None = None

    def to_dict(self) -> dict:
        return {
            "minute": self.minute,
            "situation": self.situation,
            "play": [[club_id, points] for club_id, points in self.play.items()],
            "chance": list(self.chance) if self.chance else None,
            "pressure": self.pressure,
            "chained": self.chained,
            "player_id": self.player_id,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Dilemma":
        chance = data["chance"]
        return cls(
            minute=data["minute"],
            situation=data["situation"],
            play={club_id: points for club_id, points in data["play"]},
            chance=(chance[0], chance[1]) if chance else None,
            pressure=data.get("pressure", 1.0),
            chained=data.get("chained", False),
            player_id=data.get("player_id"),
        )


@dataclass(frozen=True)
class Outcome:
    """Comment un dilemme s'est fini : la voie prise, réussie ou non, ce que la note du
    joueur y a gagné (ou perdu), et l'effet sur le match."""

    minute: int
    situation: str
    option: str
    success: bool
    chance: float
    delta: float
    effect: Effect
    pressure: float = 1.0
    player_id: int | None = None  # le joueur concerné (None : le joueur incarné)

    def to_dict(self) -> dict:
        return {
            "minute": self.minute,
            "situation": self.situation,
            "option": self.option,
            "success": self.success,
            "chance": self.chance,
            "delta": self.delta,
            "effect": self.effect.value,
            "pressure": self.pressure,
            "player_id": self.player_id,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Outcome":
        return cls(**{**data, "effect": Effect(data["effect"])})
