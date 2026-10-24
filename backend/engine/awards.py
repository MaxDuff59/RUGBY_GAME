"""Les trophées d'une saison de championnat, tirés des statistiques des matchs.

À la fin de chaque saison, chaque championnat distingue :
- le joueur de la saison : la meilleure note moyenne, parmi les joueurs qui ont
  joué au moins la moitié des matchs de leur équipe ;
- la révélation : la meilleure note moyenne d'un joueur de 21 ans ou moins (le
  quart des matchs suffit) ;
- le meilleur marqueur d'essais, le meilleur réalisateur et le plaqueur de la saison ;
- l'équipe type : à chaque poste du XV, les meilleures notes moyennes.

Rien n'est tiré au hasard : les mêmes matchs donnent les mêmes trophées. Les matchs
joués avant les statistiques (sans notes) ne comptent que pour les essais et les points.
"""

from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass, field
from enum import StrEnum

from engine.match_engine import FORMATION
from models import EventType, Match, Player, Position


class AwardKind(StrEnum):
    PLAYER = "player"  # joueur de la saison
    REVELATION = "revelation"
    TRIES = "tries"  # meilleur marqueur d'essais
    POINTS = "points"  # meilleur réalisateur
    TACKLES = "tackles"  # plaqueur de la saison
    TEAM = "team"  # équipe type (un trophée par place)


REVELATION_AGE = 21
REGULAR_SHARE, REVELATION_SHARE = 0.5, 0.25


@dataclass(frozen=True)
class Award:
    kind: AwardKind
    player_id: int
    club_id: int
    value: float  # note moyenne, essais, points ou plaquages
    position: Position | None = None  # équipe type : la place


@dataclass
class Line:
    """La saison d'un joueur dans un championnat."""

    club_id: int
    matches: int = 0
    rated: list[float] = field(default_factory=list)
    tries: int = 0
    points: int = 0
    tackles: int = 0

    @property
    def rating(self) -> float:
        return sum(self.rated) / len(self.rated) if self.rated else 0.0


def _club_of(match: Match, player_id: int) -> int | None:
    if player_id in match.home_lineup:
        return match.home_club_id
    if player_id in match.away_lineup:
        return match.away_club_id
    for event in match.events:
        if player_id in (event.player_id, event.other_player_id):
            return event.club_id
    return None


def season_lines(matches: Iterable[Match]) -> dict[int, Line]:
    """Ce que chaque joueur a fait de la saison : matchs, notes, essais, points, plaquages."""
    lines: dict[int, Line] = {}
    for match in matches:
        if not match.is_played:
            continue
        players = set(match.stats) or {*match.home_lineup, *match.away_lineup}
        for player_id in players:
            club_id = _club_of(match, player_id)
            if club_id is None:
                continue
            line = lines.setdefault(player_id, Line(club_id))
            line.club_id = club_id  # le club de son dernier match (un prêt, un transfert)
            line.matches += 1
            stats = match.stats.get(player_id)
            if stats is not None:
                if stats.rating is not None:
                    line.rated.append(stats.rating)
                line.tackles += stats.tackles
        for event in match.events:
            line = lines.get(event.player_id) if event.player_id is not None else None
            if line is None:
                continue
            line.points += event.points
            line.tries += event.type == EventType.TRY
    return lines


def season_awards(matches: Iterable[Match], players: dict[int, Player]) -> list[Award]:
    """Les trophées d'une saison de championnat ; `players` : les joueurs connus (âge,
    poste), ceux qui n'y sont plus (retraités) ne concourent pas."""
    matches = list(matches)
    lines = {pid: line for pid, line in season_lines(matches).items() if pid in players}
    if not lines:
        return []
    games = defaultdict(int)
    for match in matches:
        if match.is_played:
            games[match.home_club_id] += 1
            games[match.away_club_id] += 1

    def regular(pid: int, share: float) -> bool:
        line = lines[pid]
        return bool(line.rated) and line.matches >= share * games[line.club_id]

    awards = []

    def best(kind: AwardKind, candidates: list[int], value) -> None:
        candidates = [pid for pid in candidates if value(pid) > 0]
        if candidates:
            # À égalité, le plus de matchs, puis le plus petit identifiant (stable).
            pid = max(candidates, key=lambda p: (value(p), lines[p].matches, -p))
            awards.append(Award(kind, pid, lines[pid].club_id, round(value(pid), 2)))

    rated = [pid for pid in lines if regular(pid, REGULAR_SHARE)]
    best(AwardKind.PLAYER, rated, lambda pid: lines[pid].rating)
    young = [
        pid
        for pid in lines
        if players[pid].age <= REVELATION_AGE and regular(pid, REVELATION_SHARE)
    ]
    best(AwardKind.REVELATION, young, lambda pid: lines[pid].rating)
    best(AwardKind.TRIES, list(lines), lambda pid: lines[pid].tries)
    best(AwardKind.POINTS, list(lines), lambda pid: lines[pid].points)
    best(AwardKind.TACKLES, list(lines), lambda pid: lines[pid].tackles)

    for position, count in FORMATION.items():
        at = [pid for pid in rated if players[pid].position == position]
        at.sort(key=lambda pid: (lines[pid].rating, lines[pid].matches, -pid), reverse=True)
        for pid in at[:count]:
            line = lines[pid]
            awards.append(Award(AwardKind.TEAM, pid, line.club_id, round(line.rating, 2), position))
    return awards
