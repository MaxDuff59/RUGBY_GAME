"""Modèles du jeu.

`from models import ...` n'expose que les objets du domaine (Python pur), pour
que le moteur puisse les importer sans tirer SQLAlchemy. La couche base de
données s'importe explicitement via `models.orm`.
"""

from models.domain import (
    ATTRIBUTE_MAX,
    ATTRIBUTE_MIN,
    ATTRIBUTE_NAMES,
    EVENT_POINTS,
    FORWARDS,
    Career,
    Club,
    EventType,
    Match,
    MatchEvent,
    Player,
    Position,
    Season,
    StandingRow,
)

__all__ = [
    "ATTRIBUTE_MAX",
    "ATTRIBUTE_MIN",
    "ATTRIBUTE_NAMES",
    "EVENT_POINTS",
    "FORWARDS",
    "Career",
    "Club",
    "EventType",
    "Match",
    "MatchEvent",
    "Player",
    "Position",
    "Season",
    "StandingRow",
]
