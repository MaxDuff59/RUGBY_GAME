"""Dates des journées : un match par semaine, le samedi, avec des trêves.

Par défaut (Top 14), la saison démarre le premier samedi de septembre, avec
trois coupures comme dans le calendrier réel : tournées d'automne en novembre,
Noël, et le Tournoi des Six Nations en février-mars. Chaque championnat a sa
date de départ et ses trêves (data/leagues.py) ; un départ avant août (Super
Rugby) tombe dans l'année civile qui suit le début de la saison.
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

Breaks = Iterable[tuple[tuple[int, int], int]]


def season_saturdays(
    year: int, start: tuple[int, int] = START, breaks: Breaks = BREAKS
) -> Iterator[date]:
    """Samedis jouables de la saison `year`, à partir de `start`, trêves exclues, sans fin."""
    month, day_of_month = start
    first = date(year if month >= 8 else year + 1, month, day_of_month)
    day = first
    while day.weekday() != SATURDAY:
        day += timedelta(days=1)

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
