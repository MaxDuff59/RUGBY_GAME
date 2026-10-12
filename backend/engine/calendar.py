"""Dates des journées : un match par semaine, le samedi, avec des trêves.

Par défaut (Top 14), la saison démarre le premier samedi de septembre, avec
trois coupures comme dans le calendrier réel : tournées d'automne en novembre,
Noël, et le Tournoi des Six Nations en février-mars. Chaque championnat a sa
date de départ et ses trêves (data/leagues.py) ; un départ avant août (Super
Rugby) tombe dans l'année civile qui suit le début de la saison.

Une saison sur quatre s'ouvre par la Coupe du monde (six samedis à partir de la
mi-septembre). Les clubs décalent alors leur saison : aucun match avant le
dernier samedi des poules, et plus de trêve en novembre, puisqu'il n'y a pas de
tournées d'automne cette année-là. Le Top 14 démarre ainsi trois samedis plus
tard et finit à la même date ; ses premières journées tombent pendant la fin
des poules et les phases finales du Mondial (doublons).
"""

from collections.abc import Iterable, Iterator
from datetime import date, timedelta

SATURDAY = 5  # date.weekday() : lundi = 0

# Premier jour possible (mois, jour).
START = (9, 1)

# Trêves : à partir du (mois, jour) indiqué, on saute N samedis.
BREAKS = [
    ((11, 7), 3),  # tournées d'automne
    ((12, 20), 2),  # Noël
    ((2, 20), 3),  # Six Nations
]

# Nombre de tours de phases finales (barrages, demi-finales, finale).
PLAYOFF_ROUNDS = 3

# Coupe du monde : 2027, puis tous les quatre ans, au début de la saison.
WORLD_CUP_FIRST_YEAR = 2027
WORLD_CUP_EVERY = 4
WORLD_CUP_START = (9, 8)  # premier samedi possible (mois, jour)
# Trois samedis de poules, puis quarts, demies et finale.
WORLD_CUP_POOL_ROUNDS = 3
WORLD_CUP_ROUNDS = 6
# Mois de la trêve des tournées d'automne, sans objet une année de Coupe du monde.
AUTUMN_BREAK_MONTH = 11

Breaks = Iterable[tuple[tuple[int, int], int]]


def first_saturday(year: int, month: int, day_of_month: int) -> date:
    """Le premier samedi à partir du (mois, jour) de l'année `year`."""
    day = date(year, month, day_of_month)
    while day.weekday() != SATURDAY:
        day += timedelta(days=1)
    return day


def is_world_cup_year(year: int) -> bool:
    """La saison `year` (août `year` à juillet) s'ouvre-t-elle par une Coupe du monde ?"""
    return year >= WORLD_CUP_FIRST_YEAR and (year - WORLD_CUP_FIRST_YEAR) % WORLD_CUP_EVERY == 0


def world_cup_saturdays(year: int) -> list[date]:
    """Les six samedis de la Coupe du monde de la saison `year`."""
    first = first_saturday(year, *WORLD_CUP_START)
    return [first + timedelta(weeks=week) for week in range(WORLD_CUP_ROUNDS)]


def season_saturdays(
    year: int, start: tuple[int, int] = START, breaks: Breaks = BREAKS
) -> Iterator[date]:
    """Samedis jouables de la saison `year`, à partir de `start`, trêves exclues, sans fin.

    Une année de Coupe du monde, un championnat qui démarre à l'automne attend le
    dernier samedi des poules et saute sa trêve de novembre."""
    month, day_of_month = start
    first = date(year if month >= 8 else year + 1, month, day_of_month)
    day = first
    while day.weekday() != SATURDAY:
        day += timedelta(days=1)
    if is_world_cup_year(year) and month >= 8:
        day = max(day, world_cup_saturdays(year)[WORLD_CUP_POOL_ROUNDS - 1])
        breaks = [entry for entry in breaks if entry[0][0] != AUTUMN_BREAK_MONTH]

    # Chaque trêve a une date de début ; on la place dans l'année civile qui suit
    # si elle tombe avant le premier jour.
    pending = []
    for (month, day_of_month), skipped in breaks:
        begins = date(first.year, month, day_of_month)
        if begins < first:
            begins = date(first.year + 1, month, day_of_month)
        pending.append([begins, skipped])

    while True:
        for entry in pending:
            start, skipped = entry
            if skipped > 0 and day >= start:
                entry[1] -= 1
                break
        else:
            yield day
        day += timedelta(days=7)


def season_dates(
    year: int,
    regular_matchdays: int,
    start: tuple[int, int] = START,
    breaks: Breaks = BREAKS,
    playoff_rounds: int = PLAYOFF_ROUNDS,
) -> tuple[list[date], list[date]]:
    """Dates des journées de saison régulière, puis des tours de phases finales."""
    saturdays = season_saturdays(year, start, breaks)
    regular = [next(saturdays) for _ in range(regular_matchdays)]
    playoffs = [next(saturdays) for _ in range(playoff_rounds)]
    return regular, playoffs


def playoff_dates(
    year: int, start: tuple[int, int], breaks: Breaks, after: date, rounds: int
) -> list[date]:
    """Dates des tours de phases finales : les samedis jouables du championnat qui
    suivent sa dernière journée (`after`). On part des matchs tels qu'ils ont été
    datés, pas du calendrier théorique : une saison tirée avec d'autres règles de
    calendrier garde des phases finales après sa saison régulière."""
    following = (day for day in season_saturdays(year, start, breaks) if day > after)
    return [next(following) for _ in range(rounds)]
