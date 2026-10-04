"""Dates des journées : un match par semaine, le samedi, avec des trêves.

La saison démarre le premier samedi de septembre. Trois coupures, comme dans le
calendrier réel : tournées d'automne en novembre, Noël, et le Tournoi des Six
Nations en février-mars.
"""

from collections.abc import Iterator
from datetime import date, timedelta

SATURDAY = 5  # date.weekday() : lundi = 0

# Trêves : à partir du (mois, jour) indiqué, on saute N samedis.
BREAKS = [
    ((11, 7), 3),  # tournées d'automne
    ((12, 20), 2),  # Noël
    ((2, 20), 3),  # Six Nations
]

# Nombre de tours de phases finales (barrages, demi-finales, finale).
PLAYOFF_ROUNDS = 3


def season_saturdays(year: int) -> Iterator[date]:
    """Samedis jouables à partir de septembre `year`, trêves exclues, sans fin."""
    day = date(year, 9, 1)
    while day.weekday() != SATURDAY:
        day += timedelta(days=1)

    # Chaque trêve a une date de début ; on la place dans l'année civile qui suit
    # le début de saison si elle tombe avant septembre.
    pending = []
    for (month, day_of_month), skipped in BREAKS:
        break_year = year if month >= 9 else year + 1
        pending.append([date(break_year, month, day_of_month), skipped])

    while True:
        for entry in pending:
            start, skipped = entry
            if skipped > 0 and day >= start:
                entry[1] -= 1
                break
        else:
            yield day
        day += timedelta(days=7)


def season_dates(year: int, regular_matchdays: int) -> tuple[list[date], list[date]]:
    """Dates des journées de saison régulière, puis des tours de phases finales."""
    saturdays = season_saturdays(year)
    regular = [next(saturdays) for _ in range(regular_matchdays)]
    playoffs = [next(saturdays) for _ in range(PLAYOFF_ROUNDS)]
    return regular, playoffs
