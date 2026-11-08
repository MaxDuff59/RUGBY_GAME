"""Les trophées mondiaux d'une saison : tous les championnats, les coupes d'Europe et les
matchs internationaux réunis.

Chaque fin de saison, le monde du rugby distingue :
- le meilleur joueur du monde : la meilleure note moyenne de la saison, club et sélection
  confondus, un test comptant TEST_WEIGHT fois un match de club, parmi ceux qui ont été
  notés au moins PLAYER_MATCHES fois ;
- le meilleur espoir du monde : de même parmi les REVELATION_AGE ans ou moins (au moins
  REVELATION_MATCHES matchs) ;
- le meilleur joueur en sélection : la meilleure note moyenne en tests (au moins
  INTERNATIONAL_MATCHES) ;
- le meilleur marqueur d'essais, le meilleur réalisateur et le meilleur plaqueur du monde ;
- le XV mondial de l'année : à chaque poste, les meilleures notes (comme le joueur du
  monde).

Rien n'est tiré au hasard : les mêmes matchs donnent les mêmes trophées. Aucune
dépendance à FastAPI ni à la base.
"""

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from enum import StrEnum

from engine.awards import Line, season_lines
from engine.match_engine import FORMATION
from models import Match, Player, Position

TEST_WEIGHT = 2
PLAYER_MATCHES = 12
REVELATION_AGE = 21
REVELATION_MATCHES = 8
INTERNATIONAL_MATCHES = 3


class WorldAwardKind(StrEnum):
    PLAYER = "player"  # meilleur joueur du monde
    REVELATION = "revelation"  # meilleur espoir du monde
    INTERNATIONAL = "international"  # meilleur joueur en sélection
    TRIES = "tries"
    POINTS = "points"
    TACKLES = "tackles"
    TEAM = "team"  # XV mondial (un trophée par place)


@dataclass(frozen=True)
class WorldAward:
    kind: WorldAwardKind
    player_id: int
    value: float  # note moyenne, essais, points ou plaquages
    matches: int  # matchs joués dans la saison, club et sélection
    tests: int  # dont en sélection
    position: Position | None = None  # XV mondial : la place


@dataclass
class _Season:
    """La saison d'un joueur, club et sélection séparés."""

    club: Line | None
    test: Line | None

    def _lines(self) -> list[Line]:
        return [line for line in (self.club, self.test) if line is not None]

    @property
    def matches(self) -> int:
        return sum(line.matches for line in self._lines())

    @property
    def tests(self) -> int:
        return self.test.matches if self.test else 0

    @property
    def rated(self) -> int:
        return sum(len(line.rated) for line in self._lines())

    @property
    def rating(self) -> float:
        """Moyenne des notes, un test pesant TEST_WEIGHT matchs de club."""
        club = self.club.rated if self.club else []
        test = self.test.rated if self.test else []
        weight = len(club) + TEST_WEIGHT * len(test)
        return (sum(club) + TEST_WEIGHT * sum(test)) / weight if weight else 0.0

    @property
    def test_rating(self) -> float:
        return self.test.rating if self.test else 0.0

    def total(self, name: str) -> int:
        return sum(getattr(line, name) for line in self._lines())


def world_awards(
    club_matches: Iterable[Match], tests: Iterable[Match], players: Mapping[int, Player]
) -> list[WorldAward]:
    """Les trophées mondiaux de la saison. `club_matches` : championnats et coupes ;
    `tests` : les matchs internationaux ; `players` : les joueurs encore là (âge, poste)."""
    clubs, internationals = season_lines(club_matches), season_lines(tests)
    seasons = {
        pid: _Season(clubs.get(pid), internationals.get(pid))
        for pid in {*clubs, *internationals}
        if pid in players
    }
    awards: list[WorldAward] = []

    def award(kind: WorldAwardKind, pid: int, value: float, position=None) -> WorldAward:
        season = seasons[pid]
        return WorldAward(kind, pid, round(value, 2), season.matches, season.tests, position)

    def best(kind: WorldAwardKind, candidates: Iterable[int], value) -> None:
        candidates = [pid for pid in candidates if value(pid) > 0]
        if candidates:
            # À égalité, le plus de matchs, puis le plus petit identifiant (stable).
            pid = max(candidates, key=lambda p: (value(p), seasons[p].matches, -p))
            awards.append(award(kind, pid, value(pid)))

    regulars = [pid for pid, season in seasons.items() if season.rated >= PLAYER_MATCHES]
    best(WorldAwardKind.PLAYER, regulars, lambda pid: seasons[pid].rating)
    young = [
        pid
        for pid, season in seasons.items()
        if players[pid].age <= REVELATION_AGE and season.rated >= REVELATION_MATCHES
    ]
    best(WorldAwardKind.REVELATION, young, lambda pid: seasons[pid].rating)
    capped = [
        pid
        for pid, season in seasons.items()
        if season.test is not None and len(season.test.rated) >= INTERNATIONAL_MATCHES
    ]
    best(WorldAwardKind.INTERNATIONAL, capped, lambda pid: seasons[pid].test_rating)
    best(WorldAwardKind.TRIES, seasons, lambda pid: seasons[pid].total("tries"))
    best(WorldAwardKind.POINTS, seasons, lambda pid: seasons[pid].total("points"))
    best(WorldAwardKind.TACKLES, seasons, lambda pid: seasons[pid].total("tackles"))

    for position, count in FORMATION.items():
        at = [pid for pid in regulars if players[pid].position == position]
        at.sort(key=lambda pid: (seasons[pid].rating, seasons[pid].matches, -pid), reverse=True)
        awards += [
            award(WorldAwardKind.TEAM, pid, seasons[pid].rating, position) for pid in at[:count]
        ]
    return awards
