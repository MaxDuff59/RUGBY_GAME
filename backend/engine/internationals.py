"""Les sélections nationales : calendrier des fenêtres, listes, doublons et matchs.

Chaque saison a ses fenêtres internationales (data/nations.py). Deux semaines
avant le premier match d'une fenêtre, chaque sélection annonce une liste de 42
joueurs : son staff la compose (`pick_squad`), ou le sélectionneur quand c'est
le joueur. Un match international se joue avec le moteur des clubs : la
sélection y est un `Club` éphémère dont l'effectif est la liste (`national_team`).

Doublon : le jour où sa sélection joue, un joueur de la liste manque à son club
(`absentees`, puis `release` : le club l'écarte et fait monter ses meilleurs
espoirs aux postes dégarnis). Les autres samedis de la fenêtre, il est rendu à
son club, avec la fatigue de ses matchs.

Une sélection peut manquer de monde à un poste (aucun club gallois dans le jeu,
peu de piliers fidjiens...) : elle appelle alors des joueurs qui évoluent hors
des championnats du jeu (`reinforcements`, `Squad.AWAY`), sans club ici et hors
du marché. Aucune dépendance à FastAPI ni à la base.
"""

import datetime
import random
from collections import Counter
from collections.abc import Callable, Iterable, Iterator

from data.generator import generate_player
from data.nations import (
    NATIONS,
    NATIONS_BY_CODE,
    WINDOWS,
    WINDOWS_BY_CODE,
    Nation,
    Window,
    home_nation,
)
from engine.calendar import SATURDAY
from engine.form import Form
from engine.freshness import squad_freshness
from engine.match_engine import RATING_FOR_POSITION, simulate_match
from engine.medical import new_injury
from engine.season import generate_fixtures
from models import Club, EventType, Injury, InjurySource, Match, Player, Position, Squad

# La liste d'une sélection pour une fenêtre, et sa répartition quand le staff la compose.
SQUAD_SIZE = 42
SQUAD_QUOTA = {
    Position.PROP: 6,
    Position.HOOKER: 4,
    Position.LOCK: 5,
    Position.BACK_ROW: 8,
    Position.SCRUM_HALF: 4,
    Position.FLY_HALF: 3,
    Position.CENTRE: 5,
    Position.WING: 4,
    Position.FULLBACK: 3,
}
# Ce qu'une liste doit au moins compter à chaque poste pour remplir une feuille de match.
SQUAD_MINIMUM = {
    Position.PROP: 4,
    Position.HOOKER: 2,
    Position.LOCK: 3,
    Position.BACK_ROW: 4,
    Position.SCRUM_HALF: 2,
    Position.FLY_HALF: 2,
    Position.CENTRE: 2,
    Position.WING: 2,
    Position.FULLBACK: 1,
}
POSITION_PLURALS = {
    Position.PROP: "piliers",
    Position.HOOKER: "talonneurs",
    Position.LOCK: "deuxièmes lignes",
    Position.BACK_ROW: "troisièmes lignes",
    Position.SCRUM_HALF: "demis de mêlée",
    Position.FLY_HALF: "demis d'ouverture",
    Position.CENTRE: "centres",
    Position.WING: "ailiers",
    Position.FULLBACK: "arrières",
}
# Les 23 d'une feuille de match, par poste : ce qu'un club en doublon doit garder.
MATCHDAY_SQUAD = {**SQUAD_MINIMUM, Position.CENTRE: 3}
# La liste s'annonce ce nombre de jours avant le premier match de la fenêtre.
ANNOUNCE_DAYS = 14

# Hors des championnats du jeu : la sélection y trouve de quoi avoir, à chaque
# poste, un joueur de plus que sa liste n'en prend.
DEPTH_MARGIN = 1
AWAY_AGES = (22, 31)
# Hors des championnats du jeu, un joueur s'entraîne comme dans un centre de ce niveau.
AWAY_TRAINING_LEVEL = 3
# Une sélection récupère comme un club au préparateur physique de ce niveau.
NATION_FITNESS_LEVEL = 3

# Clé d'une liste : (code de la fenêtre, identifiant de la sélection).
SquadKey = tuple[str, int]


# --- Calendrier --------------------------------------------------------------------------


def window_dates(window: Window, year: int) -> list[datetime.date]:
    """Les samedis de match d'une fenêtre pour la saison `year` (août `year` à juillet)."""
    month, day_of_month = window.start
    day = datetime.date(year if month >= 8 else year + 1, month, day_of_month)
    while day.weekday() != SATURDAY:
        day += datetime.timedelta(days=1)
    return [day + datetime.timedelta(weeks=i) for i, played in enumerate(window.weeks) if played]


def _pairings(window: Window, year: int) -> list[list[tuple[int, int]]]:
    """Les affiches (reçoit, se déplace) de chaque samedi de match de la fenêtre."""
    ids = [NATIONS_BY_CODE[code].id for code in window.nations]
    if window.format == "tours":
        visitors = [NATIONS_BY_CODE[code].id for code in window.visitors]
        rounds = sum(window.weeks)
        # Les adversaires tournent d'une saison à l'autre.
        shift = rounds * year
        return [
            [(home, visitors[(i + r + shift) % len(visitors)]) for i, home in enumerate(ids)]
            for r in range(rounds)
        ]
    fixtures = generate_fixtures(ids)
    if window.format == "home_away":
        return fixtures
    # Un seul match contre chacun : qui reçoit s'inverse une saison sur deux.
    half = len(fixtures) // 2
    return fixtures[:half] if year % 2 == 0 else fixtures[half:]


def schedule(year: int, windows: Iterable[Window] = WINDOWS) -> list[Match]:
    """Tous les matchs internationaux de la saison, datés mais pas encore joués.
    `Match.league` porte le code de la fenêtre, `matchday` le numéro du match dans celle-ci."""
    return [
        Match(home_club_id=home, away_club_id=away, matchday=number, date=day, league=window.code)
        for window in windows
        for number, (day, pairings) in enumerate(
            zip(window_dates(window, year), _pairings(window, year), strict=True), start=1
        )
        for home, away in pairings
    ]


def window_matches(matches: Iterable[Match], code: str) -> list[Match]:
    return [m for m in matches if m.league == code]


def announce_by(matches: Iterable[Match]) -> datetime.date:
    """Date limite d'annonce des listes d'une fenêtre, d'après ses matchs."""
    return min(m.date for m in matches) - datetime.timedelta(days=ANNOUNCE_DAYS)


def due_lists(
    matches: Iterable[Match], announced: Iterable[SquadKey], day: datetime.date
) -> list[SquadKey]:
    """Les listes à annoncer au jour `day` : celles des fenêtres pas encore finies dont
    la date limite est atteinte, moins celles déjà annoncées."""
    matches = list(matches)
    announced = set(announced)
    due = []
    for window in WINDOWS:
        ours = window_matches(matches, window.code)
        if not ours or all(m.is_played for m in ours) or announce_by(ours) > day:
            continue
        teams = sorted({team for m in ours for team in (m.home_club_id, m.away_club_id)})
        due += [(window.code, team) for team in teams if (window.code, team) not in announced]
    return due


def absentees(
    matches: Iterable[Match], squads: dict[SquadKey, list[int]], day: datetime.date
) -> dict[int, int]:
    """Les joueurs retenus par une sélection qui joue le jour `day` : identifiant du
    joueur -> identifiant de sa sélection. Ils manquent à leur club ce jour-là."""
    away: dict[int, int] = {}
    for match in matches:
        if match.date != day:
            continue
        for team in (match.home_club_id, match.away_club_id):
            for player_id in squads.get((match.league, team), []):
                away[player_id] = team
    return away


def release(club: Club, away: Iterable[int], day: datetime.date | None) -> None:
    """Prépare un club à un jour de match : ses joueurs retenus en sélection (`away`)
    sont écartés et, aux postes où il n'a plus de quoi remplir sa feuille de match,
    ses meilleurs espoirs les suppléent. Sans joueur retenu, rien ne change."""
    away = set(away)
    club.called_up = {p.id for p in club.players if p.id in away}
    club.cover = []
    if not club.called_up:
        return
    counts = Counter(p.position for p in club.available_players(day))
    for position, needed in MATCHDAY_SQUAD.items():
        youths = sorted(
            (p for p in club.youths if p.position == position and not p.is_injured(day)),
            key=position_rating,
            reverse=True,
        )
        club.cover += youths[: max(0, needed - counts[position])]


# --- Les joueurs d'une sélection -----------------------------------------------------------


def is_eligible(player: Player, nation: Nation, club_name: str | None) -> bool:
    """Sélectionnable : de la bonne nationalité, pro dans un club (du pays si la
    fédération l'exige) ou évoluant hors des championnats du jeu."""
    if player.nationality != nation.code:
        return False
    if player.squad == Squad.AWAY:
        return True
    if player.squad != Squad.PRO or player.club_id is None:
        return False
    return not nation.home_only or home_nation(club_name) == nation.code


def position_rating(player: Player) -> float:
    """La note d'un joueur à son poste, critère du staff pour composer."""
    return RATING_FOR_POSITION[player.position](player)


def pick_squad(
    candidates: Iterable[Player], day: datetime.date | None, size: int = SQUAD_SIZE
) -> list[Player]:
    """La liste que compose le staff : les meilleurs à chaque poste (`SQUAD_QUOTA`),
    sans les joueurs blessés au jour `day` (le premier match de la fenêtre) ; s'il
    manque du monde à un poste, les meilleurs restants complètent."""
    fit = [p for p in candidates if not p.is_injured(day)]
    squad: list[Player] = []
    for position, quota in SQUAD_QUOTA.items():
        at = sorted((p for p in fit if p.position == position), key=position_rating, reverse=True)
        squad += at[:quota]
    taken = {p.id for p in squad}
    rest = sorted((p for p in fit if p.id not in taken), key=lambda p: p.overall, reverse=True)
    return (squad + rest)[:size]


def check_squad(players: list[Player], size: int = SQUAD_SIZE) -> str | None:
    """Ce qui cloche dans une liste proposée (None si elle tient debout)."""
    if len(players) != size:
        return f"La liste compte {len(players)} joueurs : il en faut {size}"
    if len({p.id for p in players}) != len(players):
        return "Un joueur ne peut figurer qu'une fois dans la liste"
    counts = Counter(p.position for p in players)
    for position, minimum in SQUAD_MINIMUM.items():
        if counts[position] < minimum:
            return f"Il faut au moins {minimum} {POSITION_PLURALS[position]} dans la liste"
    return None


def reinforcements(
    nation: Nation,
    eligible: Iterable[Player],
    player_ids: Iterator[int],
    rng: random.Random,
    season_year: int,
) -> list[Player]:
    """Joueurs que la sélection va chercher hors des championnats du jeu pour avoir
    assez de monde à chaque poste (aucun si ses clubs suffisent)."""
    counts = Counter(p.position for p in eligible)
    arrivals = []
    for position, quota in SQUAD_QUOTA.items():
        for _ in range(quota + DEPTH_MARGIN - counts[position]):
            player = generate_player(
                next(player_ids), position, nation.level, None, rng, season_year, nation.code
            )
            player.age = rng.randint(*AWAY_AGES)
            player.squad = Squad.AWAY
            player.wage = 0  # payé ailleurs
            arrivals.append(player)
    return arrivals


def national_team(
    nation: Nation, players: Iterable[Player], lineup_choice: Iterable[int | None] = ()
) -> Club:
    """La sélection vue comme une équipe, pour la faire jouer avec le moteur."""
    return Club(
        id=nation.id, name=nation.name, players=list(players), lineup_choice=list(lineup_choice)
    )


def national_form(
    team: Club, appearances: dict[int, list[datetime.date]], day: datetime.date
) -> Form:
    """Forme d'une sélection : moral et cohésion neutres, fraîcheur de chacun d'après
    ses matchs (club et sélection)."""
    ids = [p.id for p in team.players]
    return Form(freshness=squad_freshness(appearances, ids, day, NATION_FITNESS_LEVEL))


# --- Les matchs -----------------------------------------------------------------------------

# Staff médical d'un joueur sans club dans le jeu.
NO_CLUB = Club(id=0, name="")


def play_tests(
    day: datetime.date,
    matches: list[Match],
    teams: dict[int, Club],
    rng: random.Random,
    forms: dict[int, Form] | None = None,
    staff_of: Callable[[Player], Club] = lambda player: NO_CLUB,
    managed_club_id: int | None = None,
    finished: Callable[[Match], Match | None] = lambda match: None,
) -> list[Injury]:
    """Joue les matchs internationaux du jour (`matches`, pas encore joués) et les
    remplit : score, événements, XV de départ. Renvoie les blessures, attachées aux joueurs.

    `teams` : les sélections du jour (`national_team`). `staff_of` : le club d'un
    joueur, pour son staff médical ; les blessés de `managed_club_id` attendent
    le protocole de leur manager. `finished` : un match joué par ailleurs (le
    match en direct du sélectionneur), None pour le laisser au moteur.
    """
    forms = forms or {}
    injuries = []
    for match in matches:
        home, away = teams[match.home_club_id], teams[match.away_club_id]
        result = finished(match) or simulate_match(
            home,
            away,
            rng=rng,
            matchday=match.matchday,
            neutral=match.neutral,
            day=day,
            home_form=forms.get(home.id, Form()),
            away_form=forms.get(away.id, Form()),
        )
        match.home_score, match.away_score = result.home_score, result.away_score
        match.events = list(result.events)
        match.home_lineup, match.away_lineup = list(result.home_lineup), list(result.away_lineup)

        players = {p.id: p for team in (home, away) for p in team.players}
        for event in match.events:
            if event.type == EventType.INJURY:
                player = players[event.player_id]
                injuries.append(
                    new_injury(
                        player,
                        staff_of(player),
                        InjurySource.MATCH,
                        day,
                        rng,
                        decided=player.club_id is None or player.club_id != managed_club_id,
                    )
                )
    return injuries


def window_of(match: Match) -> Window:
    return WINDOWS_BY_CODE[match.league]


def participants(windows: Iterable[Window] = WINDOWS) -> list[Nation]:
    """Les sélections qui ont au moins un rendez-vous, dans l'ordre de data/nations.py."""
    codes = {code for window in windows for code in window.teams}
    return [nation for nation in NATIONS if nation.code in codes]
