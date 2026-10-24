"""Discours du manager pendant un match : un coup de fouet... ou un coup d'épée dans l'eau.

Le manager parle à son équipe à trois moments :
- avant le coup d'envoi, dans le vestiaire ;
- à la pause (mi-temps, ou avant la prolongation), dans le vestiaire : c'est là que
  se tentent les gestes forts, l'engueulade ou le coup de poing dans la télé ;
- pendant le jeu, depuis le bord du terrain, au plus une fois toutes les 10 minutes.

Chaque discours a trois issues : il porte (l'élan monte), il glisse (rien ne change)
ou il se retourne contre le manager (l'élan baisse). Les chances dépendent du
discours, du score (une engueulade quand on mène vexe le groupe, un discours
enflammé quand on est mené de loin sonne creux) et du moral de l'équipe (un groupe
au plus bas encaisse mal les cris, un groupe en confiance les prend comme un défi).

L'élan multiplie les notes collectives (+0,05 = +5 %) ; la nervosité multiplie le
risque de carton (+0,5 = 50 % de cartons en plus). Les deux s'estompent au fil des
minutes de jeu.
"""

from dataclasses import dataclass
from enum import StrEnum

from models import Player


class Moment(StrEnum):
    """Où le manager prend la parole."""

    KICKOFF = "kickoff"  # vestiaire, avant le coup d'envoi
    BREAK = "break"  # vestiaire, à la mi-temps ou avant la prolongation
    TOUCHLINE = "touchline"  # bord du terrain, pendant le jeu


class Outcome(StrEnum):
    LIFTED = "lifted"  # le discours porte
    FLAT = "flat"  # il glisse sur le groupe
    BACKFIRED = "backfired"  # il se retourne contre le manager


class Score(StrEnum):
    """Le score vu par l'équipe qui écoute : devant, au contact ou derrière."""

    AHEAD = "ahead"
    CLOSE = "close"
    BEHIND = "behind"


# Au-delà d'un essai transformé d'écart, le match n'est plus « au contact ».
CLOSE_MARGIN = 7
# Entre deux discours du bord du terrain (ou depuis le dernier passage au vestiaire).
TOUCHLINE_COOLDOWN = 10

# Moral sur 20 (engine/morale.py) : sous LOW, le groupe doute ; au-dessus de HIGH, il croit en lui.
LOW_MORALE, HIGH_MORALE = 10.0, 15.0
# Un discours « fort » (cris, pression) sur un groupe qui doute : moins de chances
# de porter, plus de chances de se retourner. Sur un groupe en confiance : un peu mieux.
LOUD_LOW_MORALE = (-0.10, 0.15)
LOUD_HIGH_MORALE = (0.05, 0.0)
# Un discours doux sur un groupe qui doute : il en avait besoin.
SOFT_LOW_MORALE = (0.05, 0.0)

# Laisser parler les cadres : la chance de porter grandit avec les joueurs d'expérience du XV.
VETERAN_AGE = 29
LEADERS_BASE, LEADERS_PER_VETERAN, LEADERS_MAX = 0.25, 0.06, 0.80

# L'élan et la nervosité restent dans ces bornes, et perdent cette part à chaque minute.
SPIRIT_MIN, SPIRIT_MAX = -0.12, 0.15
HEAT_MIN, HEAT_MAX = -0.6, 1.5
SPIRIT_FADE = 0.97  # la moitié de l'élan s'est envolée au bout de ~23 minutes
HEAT_FADE = 0.95  # la nervosité retombe plus vite (~14 minutes)


@dataclass(frozen=True)
class Talk:
    """Un discours : où il se tient, ses chances selon le score, ce qu'il change.

    `odds` : par situation de score, (chance de porter, chance de se retourner) ;
    le reste du temps, il glisse. `boost` : élan gagné s'il porte ; `drop` : élan
    perdu s'il se retourne. `heat` : nervosité ajoutée quelle que soit l'issue
    (négative : le discours calme les esprits). `loud` : un discours qui crie ou
    met la pression, sensible au moral du groupe.
    """

    key: str
    moments: frozenset[Moment]
    odds: dict[Score, tuple[float, float]]
    boost: float
    drop: float
    heat: float = 0.0
    loud: bool = False


def _same(success: float, backfire: float) -> dict[Score, tuple[float, float]]:
    return {score: (success, backfire) for score in Score}


VESTIAIRE = frozenset({Moment.KICKOFF, Moment.BREAK})

TALKS: dict[str, Talk] = {
    talk.key: talk
    for talk in (
        # Avant le coup d'envoi.
        Talk("fire_up", frozenset({Moment.KICKOFF}), _same(0.55, 0.15), 0.05, 0.03, heat=0.3),
        Talk("focus", frozenset({Moment.KICKOFF}), _same(0.60, 0.05), 0.03, 0.015, heat=-0.2),
        Talk(
            "pressure",
            frozenset({Moment.KICKOFF}),
            _same(0.45, 0.30),
            0.07,
            0.05,
            heat=0.2,
            loud=True,
        ),
        # À la pause.
        Talk(
            "encourage",
            frozenset({Moment.BREAK}),
            {Score.AHEAD: (0.50, 0.05), Score.CLOSE: (0.60, 0.05), Score.BEHIND: (0.40, 0.10)},
            0.04,
            0.02,
        ),
        Talk("tactical", frozenset({Moment.BREAK}), _same(0.65, 0.05), 0.03, 0.01, heat=-0.3),
        Talk(
            "rant",
            frozenset({Moment.BREAK}),
            {Score.AHEAD: (0.20, 0.45), Score.CLOSE: (0.50, 0.20), Score.BEHIND: (0.60, 0.20)},
            0.06,
            0.04,
            heat=0.4,
            loud=True,
        ),
        Talk(
            "smash_tv",
            frozenset({Moment.BREAK}),
            {Score.AHEAD: (0.15, 0.60), Score.CLOSE: (0.45, 0.35), Score.BEHIND: (0.55, 0.35)},
            0.10,
            0.06,
            heat=0.8,
            loud=True,
        ),
        # Les cadres parlent à la place du manager, au vestiaire : leurs chances
        # dépendent du XV (voir `odds`), pas du score.
        Talk("leaders", VESTIAIRE, _same(LEADERS_BASE, 0.05), 0.04, 0.02),
        # Depuis le bord du terrain.
        Talk(
            "cheer",
            frozenset({Moment.TOUCHLINE}),
            {Score.AHEAD: (0.40, 0.05), Score.CLOSE: (0.50, 0.05), Score.BEHIND: (0.40, 0.05)},
            0.025,
            0.015,
        ),
        Talk(
            "shout",
            frozenset({Moment.TOUCHLINE}),
            {Score.AHEAD: (0.20, 0.40), Score.CLOSE: (0.40, 0.20), Score.BEHIND: (0.50, 0.20)},
            0.04,
            0.03,
            heat=0.3,
            loud=True,
        ),
        Talk("calm", frozenset({Moment.TOUCHLINE}), _same(0.55, 0.10), 0.01, 0.02, heat=-0.5),
    )
}


def score_situation(margin: int) -> Score:
    """`margin` : nos points moins ceux de l'adversaire."""
    if margin > CLOSE_MARGIN:
        return Score.AHEAD
    if margin < -CLOSE_MARGIN:
        return Score.BEHIND
    return Score.CLOSE


def odds(talk: Talk, margin: int, morale: float, lineup: list[Player]) -> tuple[float, float]:
    """(chance de porter, chance de se retourner) de ce discours, maintenant."""
    success, backfire = talk.odds[score_situation(margin)]
    if talk.key == "leaders":
        veterans = sum(1 for p in lineup if p.age >= VETERAN_AGE)
        success = min(LEADERS_MAX, LEADERS_BASE + LEADERS_PER_VETERAN * veterans)
    if morale < LOW_MORALE:
        nudge = LOUD_LOW_MORALE if talk.loud else SOFT_LOW_MORALE
    elif morale > HIGH_MORALE and talk.loud:
        nudge = LOUD_HIGH_MORALE
    else:
        nudge = (0.0, 0.0)
    success = max(0.0, success + nudge[0])
    backfire = max(0.0, backfire + nudge[1])
    return success, min(backfire, 1 - success)


def outcome(roll: float, success: float, backfire: float) -> Outcome:
    """L'issue d'un discours pour un tirage `roll` entre 0 et 1."""
    if roll < success:
        return Outcome.LIFTED
    if roll < success + backfire:
        return Outcome.BACKFIRED
    return Outcome.FLAT


def spirit_change(talk: Talk, result: Outcome) -> float:
    if result == Outcome.LIFTED:
        return talk.boost
    if result == Outcome.BACKFIRED:
        return -talk.drop
    return 0.0


def clamp(value: float, low: float, high: float) -> float:
    return min(high, max(low, value))


@dataclass(frozen=True)
class Heard:
    """Un discours tenu pendant le match : quand, lequel, son issue et ce qu'il a
    changé à l'élan et à la nervosité."""

    minute: int
    key: str
    outcome: Outcome
    spirit: float
    heat: float

    def to_dict(self) -> dict:
        return {
            "minute": self.minute,
            "key": self.key,
            "outcome": self.outcome.value,
            "spirit": self.spirit,
            "heat": self.heat,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Heard":
        return cls(
            data["minute"], data["key"], Outcome(data["outcome"]), data["spirit"], data["heat"]
        )
