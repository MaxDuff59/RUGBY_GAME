"""Le momentum d'un match : minute par minute, quelle équipe se montre dangereuse.

Chaque minute donne une barre, de 0 à 100, à l'équipe qui a le plus menacé (positive
pour celle qui reçoit, négative pour l'autre). Elle se lit comme les chances de
marquer de l'équipe qui a le ballon :

- une minute sans action dangereuse revient à l'équipe qui a eu le jeu : ses ballons
  portés, ses franchissements, ses ballons grattés (`PLAY_POINTS`) ;
- une action dangereuse (engine/match_engine.py, `_chance`) vaut ce qu'elle avait de
  chances de finir en essai ou en pénalité, même si la défense a tenu ;
- des points marqués : une pénalité ou un drop réussis, presque le maximum ; un essai,
  le maximum.

Le calcul ne tire aucun hasard : il lit ce que la minute a déjà joué, si bien qu'un
match se joue pareil, avec ou sans graphique.
"""

from models import EventType, MatchEvent

# Une minute de jeu courant : 6, plus 7 par point de jeu (`PLAY_POINTS`), jusqu'à 45.
PLAY_POINTS = {"carries": 1, "turnovers": 1, "line_breaks": 3}
PLAY_BASE = 6
PLAY_PER_POINT = 7
PLAY_MAX = 45
# Une action dangereuse : 25, plus ses chances de marquer (essai, ou pénalité qui
# rapporte souvent), jusqu'à 85.
CHANCE_BASE = 25
CHANCE_PER_THREAT = 100
CHANCE_MAX = 85
# Une pénalité en position finit souvent en points : elle compte pour cette part.
PENALTY_THREAT = 0.6
# Ce que valent des points marqués, ou un coup de pied au but manqué.
SCORED = {
    EventType.TRY: 100,
    EventType.PENALTY_GOAL: 80,
    EventType.DROP_GOAL: 80,
    EventType.PENALTY_MISSED: 60,
}


def threat(try_probability: float, penalty_probability: float) -> float:
    """Les chances qu'une action dangereuse finisse en points."""
    return try_probability + PENALTY_THREAT * penalty_probability


def minute_bar(
    home_id: int,
    play: dict[int, int],
    chance: tuple[int, float] | None,
    events: list[MatchEvent],
) -> int:
    """La barre d'une minute : positive pour l'équipe qui reçoit, négative pour l'autre.

    `play` : les points de jeu de chaque équipe pendant la minute (`PLAY_POINTS`) ;
    `chance` : l'équipe qui a eu une action dangereuse et ses chances de marquer
    (`threat`), None sans action ; `events` : ce qui s'est passé pendant la minute.
    À égalité, la minute revient à l'équipe qui reçoit."""
    values = {True: 0, False: 0}  # True : l'équipe qui reçoit
    for club_id, points in play.items():
        if points:
            values[club_id == home_id] = min(PLAY_MAX, PLAY_BASE + PLAY_PER_POINT * points)
    if chance is not None:
        club_id, odds = chance
        value = min(CHANCE_MAX, round(CHANCE_BASE + CHANCE_PER_THREAT * odds))
        values[club_id == home_id] = max(values[club_id == home_id], value)
    for event in events:
        if event.type in SCORED:
            home = event.club_id == home_id
            values[home] = max(values[home], SCORED[event.type])
    return values[True] if values[True] >= values[False] else -values[False]
