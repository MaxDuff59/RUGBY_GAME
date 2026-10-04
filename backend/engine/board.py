"""Confiance de la direction : le manager tient-il l'objectif de la saison ?

Avant chaque saison, la direction fixe un objectif d'après le rang attendu du
club (niveau de son XV parmi tous les clubs) : jouer le titre, les phases
finales, le milieu de tableau ou le maintien.

Après chaque journée de saison régulière, la confiance se rapproche d'une cible
qui dépend de l'écart entre le classement et l'objectif, d'autant plus fort que
la saison avance ; le résultat du jour l'ajuste un peu, et une trésorerie dans
le rouge l'entame. En phases finales, chaque victoire compte ; un club qui
visait le titre n'a pas le droit d'y perdre.

La confiance court sur toute la carrière ; à chaque nouvelle saison, elle revient
en partie vers la note neutre (nouvel objectif, nouveau départ).

Sous `SACK_THRESHOLD`, la direction limoge le manager — pas avant le premier
tiers de la saison régulière, le temps de juger sur pièces.
"""

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import date
from itertools import groupby

from engine.notes import STAGE_WEIGHT, Boost, Boosts, Note, scores, toward
from engine.season import PLAYOFF_QUALIFIERS, record_result
from models.domain import Match, Season, Stage, StandingRow

NEUTRAL = 12.0
SEASON_RESET = 0.3  # part de l'écart à la note neutre effacée à chaque nouvelle saison

# Cible : note neutre + par place d'avance (ou de retard) sur l'objectif.
POINTS_PER_PLACE = 1.2
# Part de l'écart à la cible comblée à chaque journée, en fin de saison régulière.
RATE = 0.3
WIN, DRAW, LOSS = 0.5, 0.0, -0.6
IN_THE_RED = -0.8  # par journée jouée avec une trésorerie négative

SACK_THRESHOLD = 4.0
SACK_WARNING = 6.0  # en dessous, la direction le fait savoir
SACK_GRACE = 1 / 3  # part de la saison régulière à jouer avant de pouvoir être limogé

PLAYOFF_WIN = 1.0
PLAYOFF_LOSS_TITLE_HOPEFUL = -2.0  # éliminé alors qu'on visait le titre
TITLE = 3.0


@dataclass(frozen=True)
class Objective:
    label: str
    target_rank: int  # rang à atteindre au plus bas


def objective_for(expected_rank: int, club_count: int) -> Objective:
    """Objectif fixé par la direction d'après le rang attendu en début de saison."""
    if expected_rank <= 2:
        return Objective("Jouer le titre", 2)
    if expected_rank <= PLAYOFF_QUALIFIERS:
        return Objective("Phases finales", PLAYOFF_QUALIFIERS)
    if expected_rank <= club_count - 4:
        return Objective("Milieu de tableau", club_count - 4)
    return Objective("Maintien", club_count - 2)


@dataclass(frozen=True)
class BoardSeason:
    """Ce qu'il faut savoir d'une saison pour juger le manager."""

    club_ids: list[int]
    matches: list[Match]  # matchs pros de la saison, phases finales comprises
    objective: Objective


def board_confidence(
    club_id: int,
    seasons: list[BoardSeason],
    balance_on: Callable[[date], int | None] = lambda day: None,
    boosts: Iterable[Boost] = (),
) -> Note:
    """Confiance de la direction d'un club après toutes les saisons (dans l'ordre).

    `balance_on` : trésorerie du club à une date (None si inconnue). `boosts` :
    décisions du manager (engine/affairs.py).
    """
    confidence = Note(NEUTRAL)
    pending = Boosts(boosts)
    for index, season in enumerate(seasons):
        if index > 0:
            confidence.value = toward(confidence.value, NEUTRAL, SEASON_RESET)
        table = Season(year=0, clubs=[])
        table.standings = {cid: StandingRow(club_id=cid) for cid in season.club_ids}
        regular_rounds = 2 * (len(season.club_ids) - 1)
        target_rank = season.objective.target_rank

        played = sorted((m for m in season.matches if m.is_played), key=lambda m: m.date)
        for _, day_matches in groupby(played, key=lambda m: m.date):
            day_matches = list(day_matches)
            ours = next(
                (m for m in day_matches if club_id in (m.home_club_id, m.away_club_id)), None
            )
            for match in day_matches:
                if match.stage == Stage.REGULAR:
                    record_result(table, match)
            if ours is None:
                continue

            confidence.nudge(pending.before(ours.date))
            value = confidence.value
            if ours.stage == Stage.REGULAR:
                scored, conceded = scores(ours, club_id)
                rank = 1 + [row.club_id for row in table.table()].index(club_id)
                progress = table.standings[club_id].played / regular_rounds
                target = NEUTRAL + POINTS_PER_PLACE * (target_rank - rank)
                value = toward(value, target, RATE * progress)
                value += WIN if scored > conceded else LOSS if scored < conceded else DRAW
            else:
                # Égalité en phase finale : le mieux classé passe.
                seeding = [row.club_id for row in table.table()]
                if ours.winner_id(seeding) == club_id:
                    value += PLAYOFF_WIN * STAGE_WEIGHT[ours.stage]
                    if ours.stage == Stage.FINAL:
                        value += TITLE
                elif target_rank <= 2:
                    value += PLAYOFF_LOSS_TITLE_HOPEFUL
            balance = balance_on(ours.date)
            if balance is not None and balance < 0:
                value += IN_THE_RED
            confidence.step(ours, value)
    confidence.nudge(pending.rest())
    return confidence


def should_sack(confidence: float, matches_played: int, regular_rounds: int) -> bool:
    """La direction limoge-t-elle le manager après ce match ?"""
    return confidence < SACK_THRESHOLD and matches_played >= SACK_GRACE * regular_rounds
