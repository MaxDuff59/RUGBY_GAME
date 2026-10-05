"""Calendrier aller-retour, phases finales et simulation d'une saison complète."""

import random
from enum import StrEnum

from engine.match_engine import simulate_match
from models import Club, Match, Season, Stage

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


def simulate_season(clubs: list[Club], year: int, rng: random.Random | None = None) -> Season:
    """Génère le calendrier, joue tous les matchs et renvoie la saison avec son classement."""
    rng = rng or random.Random()
    clubs_by_id = {club.id: club for club in clubs}
    season = Season(year=year, clubs=clubs)

    for matchday_number, fixtures in enumerate(generate_fixtures(list(clubs_by_id)), start=1):
        for home_id, away_id in fixtures:
            match = simulate_match(
                clubs_by_id[home_id], clubs_by_id[away_id], rng=rng, matchday=matchday_number
            )
            season.matches.append(match)
            record_result(season, match)

    return season


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
