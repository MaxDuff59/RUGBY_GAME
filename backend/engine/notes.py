"""Notes de vie du club (moral, cohésion, fraîcheur, direction, supporters).

Chaque note est sur 20 et se recalcule à partir des matchs joués : rien n'est
stocké. Ce module contient ce qu'elles partagent.

Les décisions du manager entre deux matchs (engine/affairs.py) s'y ajoutent sous
forme de coups de pouce datés (`Boost`) : chaque note les applique dans l'ordre
chronologique, puis ils s'estompent comme le reste.
"""

import datetime
from collections.abc import Iterable
from dataclasses import dataclass, field

from models.domain import Match, Stage

MIN_NOTE, MAX_NOTE = 0.0, 20.0

# Les matchs à élimination directe pèsent plus.
STAGE_WEIGHT = {Stage.REGULAR: 1.0, Stage.BARRAGE: 1.5, Stage.SEMI: 1.8, Stage.FINAL: 2.2}


@dataclass(frozen=True)
class NoteStep:
    """La note juste après un match (avant le match pour la fraîcheur)."""

    match: Match
    value: float
    change: float


@dataclass
class Note:
    value: float
    history: list[NoteStep] = field(default_factory=list)

    def step(self, match: Match, value: float) -> None:
        """Passe à `value` (bornée) et l'inscrit à l'historique."""
        value = clamp(value)
        self.history.append(NoteStep(match=match, value=value, change=value - self.value))
        self.value = value

    def nudge(self, delta: float) -> None:
        """Ajoute `delta` (bornée) sans l'inscrire à l'historique."""
        self.value = clamp(self.value + delta)


@dataclass(frozen=True)
class Boost:
    """Variation d'une note décidée entre deux matchs.

    `day` : date du dernier match joué au moment de la décision ; le coup de pouce
    compte après les matchs de ce jour-là et avant tous les suivants.
    """

    day: datetime.date
    delta: float


class Boosts:
    """Coups de pouce à appliquer au fil des matchs, dans l'ordre chronologique."""

    def __init__(self, boosts: Iterable[Boost] = ()) -> None:
        self._pending = sorted(boosts, key=lambda b: b.day)

    def before(self, day: datetime.date | None) -> float:
        """Somme des coups de pouce décidés avant le jour `day` (et retirés de la file)."""
        total = 0.0
        while self._pending and (day is None or self._pending[0].day < day):
            total += self._pending.pop(0).delta
        return total

    def rest(self) -> float:
        """Somme de ceux qui restent (décidés depuis le dernier match)."""
        return self.before(None)


def clamp(value: float) -> float:
    return min(MAX_NOTE, max(MIN_NOTE, value))


def toward(value: float, target: float, share: float) -> float:
    """Rapproche `value` de `target` d'une part `share` de l'écart."""
    return value + (target - value) * share


def club_matches(club_id: int, matches: list[Match]) -> list[Match]:
    """Les matchs joués par un club, dans l'ordre reçu."""
    return [m for m in matches if m.is_played and club_id in (m.home_club_id, m.away_club_id)]


def scores(match: Match, club_id: int) -> tuple[int, int]:
    """Points marqués et encaissés par un club."""
    if match.home_club_id == club_id:
        return match.home_score, match.away_score
    return match.away_score, match.home_score


def lineup_of(match: Match, club_id: int) -> list[int]:
    return match.home_lineup if match.home_club_id == club_id else match.away_lineup
