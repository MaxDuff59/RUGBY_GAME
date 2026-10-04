"""Calendrier aller-retour, phases finales et simulation d'une saison complète."""

import random

from engine.match_engine import simulate_match
from models import Club, Match, Season

# Phases finales façon Top 14 : 6 qualifiés.
PLAYOFF_QUALIFIERS = 6

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
