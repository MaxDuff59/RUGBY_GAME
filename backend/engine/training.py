"""L'entraînement de la semaine : son rythme et son thème, choisis par le manager.

Le rythme (`Intensity`) arbitre entre la fraîcheur et les progrès : une semaine
légère laisse les organismes récupérer (fraîcheur plus haute au coup d'envoi,
moins de blessures à l'entraînement) mais fait moins progresser ; une semaine
intense fait progresser plus vite, au prix de la fraîcheur et de quelques blessés.

Le thème (`Theme`) oriente le travail : les attributs du thème progressent en
priorité (engine/development.py), et l'équipe en tire un petit plus dès le match
suivant (engine/coaching.py) ; un thème a son prix : ce qu'on ne travaille pas
s'émousse un peu. Sans thème, rien de tout ça. Les clubs de l'IA s'entraînent sur
un rythme normal, sans thème.
"""

from dataclasses import dataclass
from enum import StrEnum

from engine.development import Training
from models import Club


class Intensity(StrEnum):
    LIGHT = "light"
    NORMAL = "normal"
    INTENSE = "intense"


class Theme(StrEnum):
    NONE = "none"
    SET_PIECE = "set_piece"  # conquête : mêlée, touche
    ATTACK = "attack"  # jeu courant : passes, prise de balle, vitesse
    DEFENCE = "defence"  # plaquage, travail au sol
    KICKING = "kicking"  # jeu au pied
    FITNESS = "fitness"  # préparation physique


@dataclass(frozen=True)
class Rhythm:
    pace: float  # multiplicateur de la progression
    freshness: float  # points de fraîcheur (sur 20) au coup d'envoi
    injuries: float  # multiplicateur du risque de blessure à l'entraînement


RHYTHMS = {
    Intensity.LIGHT: Rhythm(pace=0.8, freshness=1.5, injuries=0.6),
    Intensity.NORMAL: Rhythm(pace=1.0, freshness=0.0, injuries=1.0),
    Intensity.INTENSE: Rhythm(pace=1.25, freshness=-1.5, injuries=1.6),
}

# Attributs travaillés par chaque thème.
FOCUS = {
    Theme.NONE: (),
    Theme.SET_PIECE: ("scrum", "lineout"),
    Theme.ATTACK: ("handling", "passing", "pace"),
    Theme.DEFENCE: ("tackling", "power"),
    Theme.KICKING: ("kicking",),
    Theme.FITNESS: ("stamina", "power"),
}

# Le plus du match suivant (multiplicateurs de engine/coaching.py) et son prix sur le
# reste : +4 % sur ce qu'on travaille, -1 % sur ce qu'on délaisse.
THEME_BONUS, THEME_COST = 0.04, 0.01
# Jeu au pied : points de réussite des coups de pied au but ; physique : énergie
# dépensée en moins par minute de jeu.
THEME_KICKING = 0.03
THEME_STAMINA = 0.08


@dataclass(frozen=True)
class Plan:
    intensity: Intensity = Intensity.NORMAL
    theme: Theme = Theme.NONE

    @property
    def rhythm(self) -> Rhythm:
        return RHYTHMS[self.intensity]

    def training(self) -> Training:
        """Ce que la semaine change à la progression des joueurs."""
        return Training(pace=self.rhythm.pace, focus=FOCUS[self.theme])

    def multipliers(self) -> dict[str, float]:
        """Ce que le thème change aux notes collectives du match suivant : conquête et
        paquet (`forwards`), attaque, défense."""
        boosted = {
            Theme.SET_PIECE: "forwards",
            Theme.ATTACK: "attack",
            Theme.DEFENCE: "defence",
        }.get(self.theme)
        if self.theme == Theme.NONE:
            return {"forwards": 1.0, "attack": 1.0, "defence": 1.0}
        return {
            line: 1 + THEME_BONUS if line == boosted else 1 - THEME_COST
            for line in ("forwards", "attack", "defence")
        }

    @property
    def kicking(self) -> float:
        return THEME_KICKING if self.theme == Theme.KICKING else 0.0

    @property
    def stamina(self) -> float:
        """Part d'énergie économisée par minute de jeu."""
        return THEME_STAMINA if self.theme == Theme.FITNESS else 0.0


def plan_of(club: Club) -> Plan:
    """La semaine d'entraînement d'un club (rythme normal, sans thème pour l'IA)."""
    return Plan(Intensity(club.training_intensity), Theme(club.training_theme))
