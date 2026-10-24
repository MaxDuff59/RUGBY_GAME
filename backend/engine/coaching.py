"""Le staff technique sur le terrain : ce que chaque entraîneur apporte au XV.

Chaque poste pèse sur une partie du jeu, selon le niveau de son titulaire :
- l'entraîneur des avants : la conquête (mêlée, touche) et le paquet ;
- l'entraîneur de l'attaque : la note d'attaque des lignes arrières ;
- l'entraîneur de la défense : la note de défense ;
- l'entraîneur du jeu au pied : la réussite des coups de pied au but ;
- l'analyste vidéo : il décortique l'adversaire, l'équipe se crée plus d'occasions
  (son territoire).

Un entraîneur de 3 étoiles, le niveau courant des clubs, ne change rien ; chaque
étoile en plus ou en moins déplace le curseur, et un poste vacant (niveau 0) coûte
plus cher qu'un entraîneur médiocre. Une équipe sans aucun staff à elle (une
sélection, les espoirs) joue sur le niveau de référence.

Le préparateur physique (fraîcheur, engine/freshness.py), le kiné et le médecin
(engine/medical.py) jouent ailleurs. Le moteur de match (engine/match_engine.py)
applique `Coaching` aux notes collectives et aux coups de pied.
"""

from dataclasses import dataclass

from engine.freshness import BASE_RECOVERY, RECOVERY_PER_FITNESS_LEVEL
from engine.medical import DOCTOR_RELAPSE_PER_LEVEL, PHYSIO_DURATION_PER_LEVEL
from models import Club, StaffRole

# Le niveau d'un entraîneur qui ne change rien au jeu.
REFERENCE_LEVEL = 3
# Notes collectives et territoire, par étoile d'écart : 5 étoiles +5 %, vacant -7,5 %.
COACH_PER_LEVEL = 0.025
# Réussite au pied, en points de pourcentage par étoile : 5 étoiles +3 points.
KICKING_PER_LEVEL = 0.015


@dataclass(frozen=True)
class Coaching:
    """Ce que le staff technique d'une équipe change à son jeu."""

    forwards: float = 1.0  # multiplie la conquête et le paquet
    attack: float = 1.0  # multiplie l'attaque
    defence: float = 1.0  # multiplie la défense
    kicking: float = 0.0  # s'ajoute à la réussite des coups de pied au but
    analysis: float = 1.0  # multiplie le territoire


NEUTRAL = Coaching()


def coaching(club: Club) -> Coaching:
    """L'apport du staff technique de `club` (neutre pour une équipe sans staff)."""
    if not club.staff:
        return NEUTRAL

    def gap(role: StaffRole) -> int:
        return club.staff_level(role) - REFERENCE_LEVEL

    return Coaching(
        forwards=1 + COACH_PER_LEVEL * gap(StaffRole.FORWARDS_COACH),
        attack=1 + COACH_PER_LEVEL * gap(StaffRole.ATTACK_COACH),
        defence=1 + COACH_PER_LEVEL * gap(StaffRole.DEFENCE_COACH),
        kicking=KICKING_PER_LEVEL * gap(StaffRole.KICKING_COACH),
        analysis=1 + COACH_PER_LEVEL * gap(StaffRole.ANALYST),
    )


def effect(role: StaffRole, level: int) -> float:
    """Ce qu'un membre du staff de ce niveau (0 : poste vacant) change, pour l'afficher :
    une part (+0,05 : +5 %), en points de réussite pour le jeu au pied."""
    match role:
        case StaffRole.KICKING_COACH:
            return KICKING_PER_LEVEL * (level - REFERENCE_LEVEL)
        case StaffRole.FITNESS_COACH:  # récupération quotidienne, contre un poste vacant
            return RECOVERY_PER_FITNESS_LEVEL * level / BASE_RECOVERY
        case StaffRole.PHYSIO:  # durée des convalescences
            return -PHYSIO_DURATION_PER_LEVEL * max(level - 1, 0)
        case StaffRole.DOCTOR:  # risque de rechute
            return -DOCTOR_RELAPSE_PER_LEVEL * max(level - 1, 0)
        case _:
            return COACH_PER_LEVEL * (level - REFERENCE_LEVEL)
