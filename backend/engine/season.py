"""Calendrier aller-retour, classement et phases finales d'un championnat.

Tout part de la liste des matchs d'un championnat (`Match`, joués ou non) : le
classement, la phase en cours et le tour suivant s'en déduisent. La journée
elle-même se joue dans engine/matchday.py, et une saison entière sans base de
données dans engine/world.py.
"""

import datetime
import random
from collections.abc import Iterable
from enum import StrEnum
from typing import TYPE_CHECKING

from engine.calendar import playoff_dates, season_dates
from models import Match, Season, Stage, StandingRow

if TYPE_CHECKING:
    from data.leagues import League

# Phases finales façon Top 14 : 6 qualifiés.
PLAYOFF_QUALIFIERS = 6


class PlayoffFormat(StrEnum):
    """Formule des phases finales d'un championnat (le mieux classé reçoit)."""

    TOP4 = "top4"  # demi-finales 1-4 et 2-3, finale (Premiership)
    TOP6 = "top6"  # barrages 3-6 et 4-5, demies chez le 1er et le 2e, finale (Top 14, Pro D2)
    TOP8 = "top8"  # quarts 1-8, 2-7, 3-6, 4-5, demies selon le tableau, finale (URC)
    # Qualifications 1-6, 2-5, 3-4 ; les vainqueurs et le meilleur perdant (classé
    # 4e, à l'extérieur) jouent les demies, puis la finale (Super Rugby).
    SUPER6 = "super6"

    @property
    def qualifiers(self) -> int:
        return {"top4": 4, "top6": 6, "top8": 8, "super6": 6}[self.value]

    @property
    def stages(self) -> list[Stage]:
        """Les tours, dans l'ordre."""
        first = {
            PlayoffFormat.TOP4: [],
            PlayoffFormat.TOP6: [Stage.BARRAGE],
            PlayoffFormat.TOP8: [Stage.QUARTER],
            PlayoffFormat.SUPER6: [Stage.QUARTER],
        }[self]
        return [*first, Stage.SEMI, Stage.FINAL]


# Une journée = liste de rencontres (id domicile, id extérieur).
Fixture = tuple[int, int]


def generate_fixtures(club_ids: list[int]) -> list[list[Fixture]]:
    """Calendrier aller-retour par la méthode du tourniquet ("round robin").

    On fixe le premier club et on fait tourner les autres d'un cran à chaque
    journée : chacun rencontre ainsi tous les autres une fois. La phase retour
    reprend la phase aller en inversant domicile et extérieur, donc chaque club
    joue autant de matchs à domicile qu'à l'extérieur sur la saison.

    Avec N clubs (N pair) : 2 x (N - 1) journées de N / 2 matchs.
    Avec N impair, un club est exempté à chaque journée : 2 x N journées.
    """
    if len(club_ids) < 2:
        raise ValueError("Il faut au moins 2 clubs pour un championnat")

    # None = club fictif "exempt" pour un nombre impair de clubs.
    teams: list[int | None] = list(club_ids)
    if len(teams) % 2 == 1:
        teams.append(None)

    # Pour alterner domicile/extérieur : nombre de réceptions et lieu du dernier match.
    home_count = dict.fromkeys(club_ids, 0)
    last_was_home = dict.fromkeys(club_ids, False)

    n = len(teams)
    first_leg: list[list[Fixture]] = []
    for _ in range(n - 1):
        matchday: list[Fixture] = []
        for i in range(n // 2):
            home, away = teams[i], teams[n - 1 - i]
            if home is None or away is None:
                continue  # le club opposé au "exempt" ne joue pas cette journée
            # Reçoit le club qui a le moins reçu ; à égalité, celui qui vient de jouer dehors.
            if (home_count[away], last_was_home[away]) < (home_count[home], last_was_home[home]):
                home, away = away, home
            home_count[home] += 1
            last_was_home[home], last_was_home[away] = True, False
            matchday.append((home, away))
        first_leg.append(matchday)
        # Rotation : le premier reste en place, le dernier passe en deuxième position.
        teams = [teams[0], teams[-1], *teams[1:-1]]

    second_leg = [[(away, home) for home, away in matchday] for matchday in first_leg]
    return first_leg + second_leg


def record_result(season: Season, match: Match) -> None:
    """Met à jour le classement de la saison avec le résultat d'un match joué.

    Les essais sont transmis pour calculer le bonus offensif.
    """
    if not match.is_played:
        raise ValueError("Le match n'a pas encore été joué")
    home_id, away_id = match.home_club_id, match.away_club_id
    home_tries, away_tries = match.tries_for(home_id), match.tries_for(away_id)
    season.standings[home_id].record(match.home_score, match.away_score, home_tries, away_tries)
    season.standings[away_id].record(match.away_score, match.home_score, away_tries, home_tries)


def rng_for(seed: int, *labels: object) -> random.Random:
    """Le hasard d'un moment de la saison (une journée, l'intersaison...), tiré de la
    graine de la saison : la même graine redonne les mêmes tirages."""
    return random.Random(":".join(str(part) for part in (seed, *labels)))


def schedule(
    league: "League", club_ids: list[int], year: int, code: str | None = None
) -> list[Match]:
    """Les matchs de saison régulière d'un championnat, datés mais pas encore joués.

    `code` : code du championnat s'il diffère de celui de `league` (un monde
    inventé joue avec la formule du Top 14)."""
    fixtures = generate_fixtures(club_ids)
    dates, _ = season_dates(year, len(fixtures), league.start, league.breaks)
    return [
        Match(
            home_club_id=home,
            away_club_id=away,
            matchday=number,
            date=dates[number - 1],
            league=code or league.code,
        )
        for number, matchday in enumerate(fixtures, start=1)
        for home, away in matchday
    ]


def regular_matchdays(matches: Iterable[Match]) -> int:
    """Nombre de journées de saison régulière d'un championnat."""
    return max(m.matchday for m in matches if m.stage == Stage.REGULAR)


def league_table(matches: Iterable[Match]) -> Season:
    """Classement de la saison régulière d'un championnat, d'après ses matchs joués."""
    matches = list(matches)
    table = Season(year=0, clubs=[])
    club_ids = sorted({c for m in matches for c in (m.home_club_id, m.away_club_id)})
    table.standings = {club_id: StandingRow(club_id=club_id) for club_id in club_ids}
    for match in matches:
        if match.stage == Stage.REGULAR and match.is_played:
            table.matches.append(match)
            record_result(table, match)
    return table


def seeding(matches: Iterable[Match]) -> list[int]:
    """Identifiants des clubs du championnat, du 1er au dernier de la saison régulière."""
    return [row.club_id for row in league_table(matches).table()]


def phase(matches: Iterable[Match]) -> str:
    """Où en est le championnat : "regular", "playoffs" ou "finished"."""
    matches = list(matches)
    if any(m.stage == Stage.REGULAR and not m.is_played for m in matches):
        return "regular"
    finals = [m for m in matches if m.stage == Stage.FINAL]
    if finals and all(m.is_played for m in finals):
        return "finished"
    return "playoffs"


def champion(matches: Iterable[Match]) -> int | None:
    """Le vainqueur de la finale, None tant qu'elle n'est pas jouée."""
    matches = list(matches)
    final = next((m for m in matches if m.stage == Stage.FINAL), None)
    if final is None or not final.is_played:
        return None
    return final.winner_id(seeding(matches))


def next_playoff_matches(league: "League", matches: Iterable[Match], year: int) -> list[Match]:
    """Les matchs du tour suivant d'un championnat, quand tous ceux du tour en cours
    sont joués (aucun sinon, ou une fois la finale jouée)."""
    matches = list(matches)
    if any(not m.is_played for m in matches):
        return []
    stages = league.playoffs.stages
    played = {stage: [m for m in matches if m.stage == stage] for stage in stages}
    next_round = playoff_round(league.playoffs, seeding(matches), played)
    if next_round is None:
        return []
    stage, pairings = next_round
    regular = regular_matchdays(matches)
    last_regular = max(m.date for m in matches if m.stage == Stage.REGULAR)
    dates = playoff_dates(year, league.start, league.breaks, last_regular, len(stages))
    index = stages.index(stage)
    return [
        Match(
            home_club_id=home,
            away_club_id=away,
            matchday=regular + index + 1,
            stage=stage,
            date=dates[index],
            neutral=stage == Stage.FINAL and league.neutral_final,
            league=matches[0].league,
        )
        for home, away in pairings
    ]


def next_date(matches: Iterable[Match]) -> datetime.date | None:
    """Le prochain jour de match (None si tout est joué)."""
    return min((m.date for m in matches if not m.is_played), default=None)


# --- Phases finales ------------------------------------------------------------------
#
# `seeding` est le classement final de la saison régulière (identifiants de clubs,
# du 1er au dernier). Chaque fonction renvoie des affiches (domicile, extérieur) :
# le mieux classé reçoit, sauf en finale, jouée sur terrain neutre.


def barrage_pairings(seeding: list[int]) -> list[Fixture]:
    """Barrages : 3e contre 6e, 4e contre 5e."""
    if len(seeding) < PLAYOFF_QUALIFIERS:
        raise ValueError(f"Il faut au moins {PLAYOFF_QUALIFIERS} clubs pour des phases finales")
    return [(seeding[2], seeding[5]), (seeding[3], seeding[4])]


def semi_pairings(seeding: list[int], barrages: list[Match]) -> list[Fixture]:
    """Demi-finales : le 1er reçoit le vainqueur de 4e-5e, le 2e celui de 3e-6e."""
    winners = {m.home_club_id: m.winner_id(seeding) for m in barrages}
    winner_3_6 = winners[seeding[2]]
    winner_4_5 = winners[seeding[3]]
    return [(seeding[0], winner_4_5), (seeding[1], winner_3_6)]


def final_pairing(seeding: list[int], semis: list[Match]) -> Fixture:
    """Finale entre les deux vainqueurs, le mieux classé cité en premier."""
    winners = sorted((m.winner_id(seeding) for m in semis), key=seeding.index)
    return (winners[0], winners[1])


def _by_seed(seeding: list[int], *club_ids: int) -> Fixture:
    first, second = sorted(club_ids, key=seeding.index)
    return (first, second)


def playoff_round(
    fmt: PlayoffFormat, seeding: list[int], played: dict[Stage, list[Match]]
) -> tuple[Stage, list[Fixture]] | None:
    """Le tour suivant des phases finales et ses affiches, d'après les tours déjà
    joués (`played`, par étape) ; None une fois la finale jouée."""
    if len(seeding) < fmt.qualifiers:
        raise ValueError(f"Il faut au moins {fmt.qualifiers} clubs pour ces phases finales")
    stage = next((s for s in fmt.stages if not played.get(s)), None)
    if stage is None:
        return None
    seeds = seeding[: fmt.qualifiers]
    if stage == Stage.FINAL:
        return stage, [final_pairing(seeding, played[Stage.SEMI])]
    if stage == Stage.BARRAGE:
        return stage, barrage_pairings(seeding)
    if stage == Stage.QUARTER:
        n = len(seeds)
        return stage, [(seeds[i], seeds[n - 1 - i]) for i in range(n // 2)]

    # Demi-finales.
    if fmt == PlayoffFormat.TOP4:
        return stage, [(seeds[0], seeds[3]), (seeds[1], seeds[2])]
    if fmt == PlayoffFormat.TOP6:
        return stage, semi_pairings(seeding, played[Stage.BARRAGE])
    quarters = played[Stage.QUARTER]
    if fmt == PlayoffFormat.TOP8:
        # Tableau : vainqueur de 1-8 contre celui de 4-5, de 2-7 contre 3-6.
        winner = {m.home_club_id: m.winner_id(seeding) for m in quarters}
        return stage, [
            _by_seed(seeding, winner[seeds[0]], winner[seeds[3]]),
            _by_seed(seeding, winner[seeds[1]], winner[seeds[2]]),
        ]
    # Super Rugby : le meilleur perdant est repêché comme 4e, et se déplace.
    winners = sorted((m.winner_id(seeding) for m in quarters), key=seeding.index)
    losers = {c for m in quarters for c in (m.home_club_id, m.away_club_id)} - set(winners)
    best_loser = min(losers, key=seeding.index)
    return stage, [(winners[0], best_loser), (winners[1], winners[2])]
