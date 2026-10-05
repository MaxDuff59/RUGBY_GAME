"""Génère des clubs fictifs, simule une saison et affiche le classement final.

Le joueur incarne le manager d'un des clubs : il est mis en avant dans le
classement et on affiche le détail de sa saison.

Usage (depuis le dossier backend/) :
    uv run python -m scripts.run_season
    uv run python -m scripts.run_season --clubs 14 --seed 42 --club 3
"""

import argparse
import random
from collections import Counter

from data.generator import generate_clubs, generate_real_clubs
from data.leagues import LEAGUES_BY_CODE
from engine.match_engine import team_strength
from engine.season import simulate_season
from models import Career, Club, Season

MY_CLUB_MARKER = "◀ ton club"


def print_club_levels(clubs: list[Club], career: Career) -> None:
    """Niveau de départ des clubs, pour comparer avec le classement final."""
    print("Niveau des effectifs (conquête / paquet / attaque / défense) :")
    for club in sorted(clubs, key=lambda c: c.name):
        t = team_strength(club)
        level = (t.set_piece + t.pack + t.attack + t.defense) / 4
        marker = f"  {MY_CLUB_MARKER}" if club.id == career.club_id else ""
        print(f"  {club.name:<26}{level:5.1f}{marker}")
    print()


def print_table(season: Season, clubs_by_id: dict[int, Club], career: Career) -> None:
    header = (
        f"{'#':>2}  {'Club':<26}{'J':>3}{'G':>4}{'N':>3}{'P':>4}"
        f"{'PP':>6}{'PC':>6}{'Diff':>6}{'Ess':>5}{'BO':>4}{'BD':>4}{'Pts':>5}"
    )
    print(header)
    print("-" * len(header))
    for rank, row in enumerate(season.table(), start=1):
        marker = f"  {MY_CLUB_MARKER}" if row.club_id == career.club_id else ""
        print(
            f"{rank:>2}  {clubs_by_id[row.club_id].name:<26}{row.played:>3}{row.won:>4}"
            f"{row.drawn:>3}{row.lost:>4}{row.points_for:>6}{row.points_against:>6}"
            f"{row.points_difference:>+6}{row.tries_for:>5}{row.offensive_bonus:>4}"
            f"{row.defensive_bonus:>4}{row.league_points:>5}{marker}"
        )
    print("PP/PC : points pour/contre, Ess : essais, BO/BD : bonus offensif/défensif")


def print_leaders(season: Season, clubs: list[Club], limit: int = 5) -> None:
    """Meilleurs marqueurs d'essais et meilleurs réalisateurs (points au total)."""
    players = {p.id: p for club in clubs for p in club.players}
    clubs_by_id = {club.id: club for club in clubs}
    events = [e for match in season.matches for e in match.events if e.player_id is not None]
    tries = Counter(e.player_id for match in season.matches for e in match.try_scorers)
    points: Counter[int] = Counter()
    for event in events:
        points[event.player_id] += event.points

    for title, counter, unit in (
        ("Meilleurs marqueurs d'essais", tries, "essais"),
        ("Meilleurs réalisateurs", points, "pts"),
    ):
        print(f"\n{title}")
        for player_id, count in counter.most_common(limit):
            player = players[player_id]
            club_name = clubs_by_id[player.club_id].name
            print(f"  {count:>3} {unit:<6} {player.name:<22} {player.position:<11} ({club_name})")


def print_my_season(season: Season, clubs_by_id: dict[int, Club], career: Career) -> None:
    """Résultats match par match du club du joueur."""
    my_id = career.club_id
    rank = [row.club_id for row in season.table()].index(my_id) + 1
    print(f"\nSaison de {clubs_by_id[my_id].name} (manager : {career.manager_name})")
    print(f"Classement final : {rank}e sur {len(clubs_by_id)}\n")

    for match in season.matches:
        if my_id not in (match.home_club_id, match.away_club_id):
            continue
        at_home = match.home_club_id == my_id
        opponent = clubs_by_id[match.away_club_id if at_home else match.home_club_id]
        mine, theirs = match.points_for(my_id), match.points_for(opponent.id)
        result = "V" if mine > theirs else "N" if mine == theirs else "D"
        venue = "dom" if at_home else "ext"
        print(f"  J{match.matchday:<3}{venue}  {result}  {mine:>3}-{theirs:<3} vs {opponent.name}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Simule une saison complète.")
    parser.add_argument("--clubs", type=int, default=10, help="nombre de clubs (défaut : 10)")
    parser.add_argument(
        "--league",
        choices=sorted(LEAGUES_BY_CODE),
        help="les vrais clubs d'un championnat (ex. top14, prod2, urc)",
    )
    parser.add_argument("--seed", type=int, help="graine du hasard, pour rejouer la même saison")
    parser.add_argument("--year", type=int, default=2026, help="année de la saison")
    parser.add_argument("--club", type=int, help="id du club que tu diriges (défaut : au hasard)")
    parser.add_argument("--manager", default="Toi", help="ton nom de manager")
    args = parser.parse_args()

    rng = random.Random(args.seed)
    if args.league:
        clubs = generate_real_clubs(rng, [LEAGUES_BY_CODE[args.league]])
    else:
        clubs = generate_clubs(args.clubs, rng)
    clubs_by_id = {club.id: club for club in clubs}
    if args.club is not None and args.club not in clubs_by_id:
        parser.error(f"--club doit être compris entre 1 et {len(clubs)}")
    career = Career(manager_name=args.manager, club_id=args.club or rng.choice(clubs).id)

    season = simulate_season(clubs, year=args.year, rng=rng)

    print(f"\nSaison {season.year} : {len(clubs)} clubs, {len(season.matches)} matchs\n")
    print_club_levels(clubs, career)
    print_table(season, clubs_by_id, career)
    print_leaders(season, clubs)
    print_my_season(season, clubs_by_id, career)


if __name__ == "__main__":
    main()
