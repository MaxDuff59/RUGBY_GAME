"""Le journal : ce qui se passe dans le monde, en titres et en brèves.

Chaque fonction écrit un article à partir d'un fait du jeu (un match joué ou à
venir, un mouvement de joueur, une blessure, une liste de sélection, un
classement) et lui donne un poids : c'est lui qui décide de la une (`edition`).
Rien n'est tiré au hasard : le même monde donne le même journal.

Les textes s'en tiennent à ce que le jeu sait dire sans faute. Un club s'écrit
sans article, comme dans un titre de dépêche (« Stade Toulousain écrase... ») ;
une sélection prend le sien (« la France », « les Fidji »), comme une franchise
au nom pluriel (« les Crusaders »), et le verbe s'accorde.
"""

import datetime
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass, field
from enum import StrEnum

from engine.season import league_table
from models import (
    EventType,
    Injury,
    InjurySource,
    Match,
    Position,
    Stage,
    StandingRow,
    level_at_overall,
)
from models.domain import DEFENSIVE_BONUS_MAX_GAP, OFFENSIVE_BONUS_TRY_MARGIN

# --- Les mots ------------------------------------------------------------------------------

MONTHS = (
    "janvier",
    "février",
    "mars",
    "avril",
    "mai",
    "juin",
    "juillet",
    "août",
    "septembre",
    "octobre",
    "novembre",
    "décembre",
)
WEEKDAYS = ("lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche")

POSITION_NOUNS = {
    Position.PROP: "le pilier",
    Position.HOOKER: "le talonneur",
    Position.LOCK: "le deuxième ligne",
    Position.BACK_ROW: "le troisième ligne",
    Position.SCRUM_HALF: "le demi de mêlée",
    Position.FLY_HALF: "le demi d'ouverture",
    Position.CENTRE: "le centre",
    Position.WING: "l'ailier",
    Position.FULLBACK: "l'arrière",
}

STAGE_TITLES = {
    Stage.QUARTER: "Quarts de finale",
    Stage.BARRAGE: "Barrages",
    Stage.SEMI: "Demi-finales",
    Stage.FINAL: "Finale",
}
# Une affiche de ce tour (au singulier), et où mène une victoire.
_STAGE_FIXTURE = {
    Stage.QUARTER: "Quart de finale",
    Stage.BARRAGE: "Barrage",
    Stage.SEMI: "Demi-finale",
    Stage.FINAL: "Finale",
}
_NEXT_ROUND = {
    Stage.QUARTER: "en demi-finales",
    Stage.BARRAGE: "en demi-finales",
    Stage.SEMI: "en finale",
}

# Sélections : leur article, et celles dont le nom est un pluriel.
_NATION_ARTICLES = {
    "FRA": "la ",
    "ENG": "l'",
    "IRE": "l'",
    "SCO": "l'",
    "WAL": "le ",
    "ITA": "l'",
    "NZL": "la ",
    "RSA": "l'",
    "AUS": "l'",
    "ARG": "l'",
    "FIJ": "les ",
    "GEO": "la ",
    "JPN": "le ",
    "SAM": "les ",
    "TON": "les ",
    "POR": "le ",
}
_PLURAL_NATIONS = frozenset({"FIJ", "SAM", "TON"})
# Franchises dont le dernier mot du nom est un pluriel (« les Crusaders dominent... »).
_PLURAL_NAMES = frozenset(
    {
        "Bears",
        "Blues",
        "Brumbies",
        "Bulls",
        "Chiefs",
        "Crusaders",
        "Harlequins",
        "Highlanders",
        "Hurricanes",
        "Lions",
        "Reds",
        "Saints",
        "Saracens",
        "Sharks",
        "Stormers",
        "Tigers",
        "Waratahs",
        "Warriors",
    }
)
_FEATS = {2: "Doublé", 3: "Triplé", 4: "Quadruplé"}
_VOWELS = "aeiouyhàâéèêëîïôöùûü"


def day_label(day: datetime.date) -> str:
    """« samedi 12 septembre »"""
    return f"{WEEKDAYS[day.weekday()]} {short_day(day)}"


def short_day(day: datetime.date) -> str:
    """« 12 septembre », « 1er mars »"""
    return f"{'1er' if day.day == 1 else day.day} {MONTHS[day.month - 1]}"


def money(amount: int) -> str:
    """2 850 000 -> « 2,85 M€ », 40 000 -> « 40 k€ »"""
    if amount >= 1_000_000:
        return f"{amount / 1_000_000:.2f}".rstrip("0").rstrip(".").replace(".", ",") + " M€"
    if amount >= 1_000:
        return f"{round(amount / 1_000)} k€"
    return f"{amount} €"


def place(rank: int) -> str:
    """« 1re place », « 3e place »"""
    return f"{'1re' if rank == 1 else f'{rank}e'} place"


def nth(rank: int) -> str:
    return "1er" if rank == 1 else f"{rank}e"


def of(name: str) -> str:
    """« de Thomas Ramos », « d'Antoine Dupont »"""
    return f"d'{name}" if name[:1].lower() in _VOWELS else f"de {name}"


def note(value: float) -> str:
    return f"{value:.1f}".replace(".", ",")


def cap(text: str) -> str:
    return text[:1].upper() + text[1:]


def _plural(count: int, word: str) -> str:
    return f"{count} {word}{'s' if count > 1 else ''}"


def _pick(options: list[str], seed: int) -> str:
    """Une tournure parmi plusieurs, toujours la même pour un même fait."""
    return options[seed % len(options)]


# --- Les acteurs ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Team:
    """Un club ou une sélection, tel qu'on l'écrit dans une phrase."""

    id: int
    name: str
    article: str = ""
    plural: bool = False

    @property
    def subject(self) -> str:
        return f"{self.article}{self.name}"

    def verb(self, singular: str, plural: str) -> str:
        return plural if self.plural else singular

    def does(self, singular: str, plural: str) -> str:
        """Le sujet en tête de phrase et son verbe : « Les Fidji battent »."""
        return f"{cap(self.subject)} {self.verb(singular, plural)}"


def club_team(club_id: int, name: str) -> Team:
    plural = name.split()[-1] in _PLURAL_NAMES if name else False
    # « les Crusaders », mais « Leicester Tigers » : l'article ne va qu'au nom seul.
    return Team(club_id, name, "les " if plural and " " not in name else "", plural)


def nation_team(team_id: int, code: str, name: str) -> Team:
    return Team(team_id, name, _NATION_ARTICLES.get(code, ""), code in _PLURAL_NATIONS)


@dataclass(frozen=True)
class Person:
    """Un joueur tel que le journal le présente. `id` à None : il n'a plus de fiche."""

    id: int | None
    name: str
    position: Position
    age: int
    overall: float

    @property
    def noun(self) -> str:
        return POSITION_NOUNS[self.position]


class MoveKind(StrEnum):
    """Un mouvement de joueur (`MoveRow`, models/orm.py)."""

    TRANSFER = "transfer"  # en cours de contrat, contre une indemnité
    LOAN = "loan"
    FREE = "free"  # libre : sans club, ou en fin de contrat (`origin` renseigné)
    PRECONTRACT = "precontract"  # signé pendant sa dernière année de contrat
    JOKER = "joker"  # joker médical
    RELEASE = "release"  # fin de contrat, sans nouveau club
    RETIREMENT = "retirement"


@dataclass(frozen=True)
class Move:
    kind: MoveKind
    date: datetime.date
    player: Person
    origin: Team | None = None
    destination: Team | None = None
    fee: int | None = None
    # Pré-contrat signé mais pas encore exécuté : il arrivera à l'intersaison.
    pending: bool = False
    key: str = ""


# --- Les articles --------------------------------------------------------------------------


class Kind(StrEnum):
    RESULT = "result"
    PREVIEW = "preview"
    STANDING = "standing"
    TRANSFER = "transfer"
    MARKET = "market"  # ce qui se prépare : fins de contrat, joueurs sans club
    INJURY = "injury"
    DISCIPLINE = "discipline"  # suspensions de la commission de discipline
    SELECTION = "selection"
    CLUB = "club"  # coulisses : un manager remercié


@dataclass
class Article:
    key: str
    kind: Kind
    date: datetime.date
    title: str
    body: str
    weight: float
    competition: str | None = None
    teams: list[Team] = field(default_factory=list)
    player: Person | None = None
    match: Match | None = None
    move: Move | None = None
    international: bool = False
    mine: bool = False  # concerne le club ou la sélection du joueur


# Poids de départ de chaque sujet ; ce qui touche le joueur passe devant.
RESULT_WEIGHT = 30.0
PREVIEW_WEIGHT = 22.0
TABLE_WEIGHT = 20.0
LEADER_WEIGHT = 40.0
MOVE_WEIGHT = 16.0
MARKET_WEIGHT = 8.0
INJURY_WEIGHT = 12.0
SUSPENSION_WEIGHT = 10.0
SQUAD_WEIGHT = 32.0
TITLE_WEIGHT = 55.0
DISMISSAL_WEIGHT = 60.0
PLAYOFF_BONUS = {Stage.QUARTER: 25.0, Stage.BARRAGE: 25.0, Stage.SEMI: 38.0, Stage.FINAL: 70.0}
INTERNATIONAL_BONUS = 16.0
MINE_BONUS = 35.0
HOME_BONUS = 12.0  # le championnat du joueur
# Un joueur compte à partir de ce niveau (models/domain.py) ; chaque point au-dessus pèse.
NOTABLE_LEVEL = 9.0

# Une surprise : le vainqueur était classé au moins cette part du tableau plus bas.
UPSET_GAP = 0.4
# Un classement se lit à partir de quelques journées.
TABLE_MIN_ROUNDS = 3
STREAK_IN_TITLE = 4
STREAK_IN_TEXT = 3


def _contenders(size: int) -> int:
    """Jusqu'à quel rang on joue le haut de tableau (4 sur 14, 2 sur 4)."""
    return max(2, round(size * 0.3))


def _strugglers(size: int) -> int:
    """Combien d'équipes font le bas de tableau (aucun duel possible sous six équipes)."""
    return max(1, size // 5)


def favour(article: Article, mine: bool, home: bool = False) -> Article:
    """Remonte un article qui touche le joueur (`mine`) ou son championnat (`home`)."""
    if mine:
        article.mine = True
        article.weight += MINE_BONUS
    elif home:
        article.weight += HOME_BONUS
    return article


# --- Classements et séries -----------------------------------------------------------------


@dataclass
class Table:
    """Le classement d'une compétition autour de sa dernière journée jouée."""

    rows: list[StandingRow]  # du premier au dernier
    previous: dict[int, int]  # rang avant la dernière journée (vide après la première)
    rounds: int  # journées jouées
    ranks: dict[int, int] = field(init=False)

    def __post_init__(self) -> None:
        self.ranks = {row.club_id: rank for rank, row in enumerate(self.rows, start=1)}

    @property
    def readable(self) -> bool:
        return self.rounds >= TABLE_MIN_ROUNDS


def table_of(matches: Iterable[Match]) -> Table | None:
    """Classement de la saison régulière d'après ses matchs joués (None si aucun)."""
    matches = list(matches)
    played = [m for m in matches if m.stage == Stage.REGULAR and m.is_played]
    if not played:
        return None
    rounds = len({m.matchday for m in played})
    previous: dict[int, int] = {}
    if rounds > 1:
        last = max(m.date for m in played)
        earlier = [m for m in matches if m.stage == Stage.REGULAR and m.date != last]
        before = league_table(earlier).table()
        previous = {row.club_id: rank for rank, row in enumerate(before, start=1)}
    return Table(league_table(matches).table(), previous, rounds)


def streaks(matches: Iterable[Match]) -> dict[int, int]:
    """Série en cours de chaque équipe : 3 = trois victoires de rang, -2 = deux défaites."""
    runs: dict[int, int] = {}
    played = [m for m in matches if m.is_played]
    for match in sorted(played, key=lambda m: (m.date, m.id or 0)):
        for team in (match.home_club_id, match.away_club_id):
            result = match.result_for(team)
            run = runs.get(team, 0)
            runs[team] = run + result if run * result > 0 else result
    return runs


# --- Matchs joués --------------------------------------------------------------------------


def _feat(match: Match, team_id: int, people: dict[int, str]) -> str:
    """Le joueur du match côté vainqueur : plusieurs essais, ou beaucoup de points."""
    events = [e for e in match.events if e.club_id == team_id and e.player_id in people]
    tries = Counter(e.player_id for e in events if e.type == EventType.TRY)
    if tries:
        player_id, count = tries.most_common(1)[0]
        if count >= 2:
            return f"{_FEATS.get(count, f'{count} essais')} {of(people[player_id])}."
    points: Counter[int] = Counter()
    for event in events:
        points[event.player_id] += event.points
    if points:
        player_id, total = points.most_common(1)[0]
        if total >= 15:
            return f"{people[player_id]} inscrit {total} points."
    return ""


def _score(match: Match, winner: int, loser: int) -> str:
    """« 31-17, 4 essais à 2. », le vainqueur d'abord."""
    high = max(match.home_score, match.away_score)
    low = min(match.home_score, match.away_score)
    tries = (match.tries_for(winner), match.tries_for(loser))
    line = f"{high}-{low}"
    if match.went_to_shootout:
        line += f" après prolongation, {match.shootout_for(winner)} tirs au but"
        line += f" à {match.shootout_for(loser)}"
    elif match.went_to_extra_time:
        line += " après prolongation"
    if not any(tries):
        return f"{line}, sans le moindre essai."
    return f"{line}, {_plural(tries[0], 'essai')} à {tries[1]}."


def result_article(
    match: Match,
    teams: dict[int, Team],
    people: dict[int, str],
    competition: str,
    table: Table | None = None,
    runs: dict[int, int] | None = None,
    international: bool = False,
) -> Article:
    """Un match joué. `table` : le classement de sa compétition, s'il compte pour lui ;
    `runs` : les séries en cours (`streaks`) ; `people` : le nom des joueurs."""
    home, away = teams[match.home_club_id], teams[match.away_club_id]
    outcome = match.result_for(home.id)
    margin = abs(match.home_score - match.away_score)
    seed = match.id or 0
    runs = runs or {}
    ranked = table is not None and match.stage == Stage.REGULAR
    weight = RESULT_WEIGHT + min(margin, 40) * 0.25 + PLAYOFF_BONUS.get(match.stage, 0.0)
    if international:
        weight += INTERNATIONAL_BONUS
    article = Article(
        key=f"result-{'i' if international else 'c'}{match.id}",
        kind=Kind.RESULT,
        date=match.date,
        title="",
        body="",
        weight=weight,
        competition=competition,
        teams=[home, away],
        match=match,
        international=international,
    )

    if outcome == 0:
        article.title = _pick(
            [
                f"{cap(home.subject)} et {away.subject} se neutralisent",
                f"{cap(home.subject)} et {away.subject} dos à dos",
                f"Pas de vainqueur entre {home.subject} et {away.subject}",
            ],
            seed,
        )
        article.body = _score(match, home.id, away.id)
        return article

    winner, loser = (home, away) if outcome > 0 else (away, home)
    victim = loser.subject
    upset = False
    if ranked and table.readable and table.previous:
        gap = table.previous[winner.id] - table.previous[loser.id]
        upset = gap >= max(4, len(table.rows) * UPSET_GAP)
    run = runs.get(winner.id, 0)

    if match.stage == Stage.FINAL:
        title = (
            f"{winner.does('bat', 'battent')} {victim} "
            f"et {winner.verb('décroche', 'décrochent')} le titre"
        )
    elif match.stage in _NEXT_ROUND:
        title = (
            f"{winner.does('élimine', 'éliminent')} {victim} "
            f"et {winner.verb('file', 'filent')} {_NEXT_ROUND[match.stage]}"
        )
    elif upset:
        article.weight += 25
        title = _pick(
            [
                f"{winner.does('surprend', 'surprennent')} {victim}",
                f"{winner.does('fait', 'font')} tomber {victim}",
                f"Sensation : {winner.subject} {winner.verb('bat', 'battent')} {victim}",
            ],
            seed,
        )
    elif ranked and run >= STREAK_IN_TITLE:
        article.weight += 6
        title = f"{winner.does('enchaîne', 'enchaînent')} une {run}e victoire de rang"
    elif margin >= 25:
        title = _pick(
            [
                f"{winner.does('écrase', 'écrasent')} {victim}",
                f"{winner.does('surclasse', 'surclassent')} {victim}",
                f"{winner.does('balaie', 'balaient')} {victim}",
            ],
            seed,
        )
    elif margin <= 7:
        article.weight += 6
        title = _pick(
            [
                f"{winner.does('bat', 'battent')} {victim} sur le fil",
                f"{winner.does('arrache', 'arrachent')} la victoire contre {victim}",
                f"{winner.does('fait', 'font')} plier {victim} d'un souffle",
            ],
            seed,
        )
    elif winner is away and not match.neutral and not international:
        title = _pick(
            [
                f"{winner.does('gagne', 'gagnent')} chez {victim}",
                f"{winner.does("s'impose", "s'imposent")} chez {victim}",
            ],
            seed,
        )
    else:
        title = _pick(
            [
                f"{winner.does('domine', 'dominent')} {victim}",
                f"{winner.does('maîtrise', 'maîtrisent')} {victim}",
                f"{winner.does('bat', 'battent')} {victim} sans trembler",
            ],
            seed,
        )
    article.title = title

    lines = [_score(match, winner.id, loser.id), _feat(match, winner.id, people)]
    if ranked:
        tries = match.tries_for(winner.id) - match.tries_for(loser.id)
        if tries >= OFFENSIVE_BONUS_TRY_MARGIN:
            lines.append("Bonus offensif à la clé.")
        if margin <= DEFENSIVE_BONUS_MAX_GAP:
            lines.append(f"{loser.does('sauve', 'sauvent')} le bonus défensif.")
        rank, before = table.ranks[winner.id], table.previous.get(winner.id)
        if rank == 1 and before not in (None, 1):
            article.weight += 10
            lines.append(f"{winner.does('prend', 'prennent')} la tête du classement.")
        elif rank == 1:
            lines.append(f"{winner.does('reste', 'restent')} en tête du classement.")
        elif before is not None and rank < before:
            lines.append(f"{winner.does('grimpe', 'grimpent')} à la {place(rank)}.")
        elif table.rounds > 1:
            lines.append(f"{winner.does('pointe', 'pointent')} à la {place(rank)}.")
        slump = -runs.get(loser.id, 0)
        if slump >= STREAK_IN_TEXT:
            lines.append(f"{slump}e défaite de suite pour {victim}.")
        top = _contenders(len(table.rows))
        if table.readable and max(table.ranks[home.id], table.ranks[away.id]) <= top:
            article.weight += 10  # deux équipes du haut de tableau
    article.body = " ".join(line for line in lines if line)
    return article


# --- Matchs à venir ------------------------------------------------------------------------


def preview_article(
    match: Match,
    teams: dict[int, Team],
    competition: str,
    table: Table | None = None,
    runs: dict[int, int] | None = None,
    international: bool = False,
) -> Article:
    """Une affiche à venir : ce qui l'oppose au classement, les séries en cours."""
    home, away = teams[match.home_club_id], teams[match.away_club_id]
    seed = match.id or 0
    runs = runs or {}
    versus = f"{home.name} – {away.name}"
    weight = PREVIEW_WEIGHT + PLAYOFF_BONUS.get(match.stage, 0.0)
    if international:
        weight += INTERNATIONAL_BONUS
    receives = home.verb("reçoit", "reçoivent")
    hosts = f"{cap(home.subject)} {receives} {away.subject}"
    lines = []

    ranked = table is not None and match.stage == Stage.REGULAR
    if match.stage != Stage.REGULAR:
        title = f"{_STAGE_FIXTURE[match.stage]} : {versus}"
    elif ranked and table.readable:
        size = len(table.rows)
        top, low = sorted((table.ranks[home.id], table.ranks[away.id]))
        weight += (2 * size - top - low) / (2 * size) * 24
        if low <= 2:
            weight += 22
            title = f"Choc au sommet : {versus}"
        elif low <= _contenders(size):
            weight += 14
            title = _pick(
                [f"{versus}, l'affiche de la journée", f"Duel de prétendants : {versus}"], seed
            )
        elif top > size - _strugglers(size):
            weight += 6
            title = _pick(
                [f"Duel de mal classés : {versus}", f"{versus} : le match de la peur"], seed
            )
        elif table.ranks[home.id] == 1:
            title = f"{cap(home.subject)}, en tête, {receives} {away.subject}"
        else:
            title = _pick([hosts, f"{versus} à l'affiche"], seed)
    elif match.neutral:
        title = versus
    elif match.matchday == 1 and not international and table is None:
        title = f"La saison s'ouvre : {home.subject} {receives} {away.subject}"
    else:
        title = hosts

    if ranked and table.rounds >= 1:
        lines.append(f"{cap(nth(table.ranks[home.id]))} contre {nth(table.ranks[away.id])}.")
    for team in (home, away):
        run = runs.get(team.id, 0)
        if run >= STREAK_IN_TEXT:
            lines.append(f"{team.does('reste', 'restent')} sur {run} victoires de rang.")
        elif run <= -STREAK_IN_TEXT:
            lines.append(f"{team.does('reste', 'restent')} sur {-run} défaites de suite.")
    venue = ", sur terrain neutre" if match.neutral else ""
    lines.append(f"Coup d'envoi {day_label(match.date)}{venue}.")

    return Article(
        key=f"preview-{'i' if international else 'c'}{match.id}",
        kind=Kind.PREVIEW,
        date=match.date,
        title=title,
        body=" ".join(lines),
        weight=weight,
        competition=competition,
        teams=[home, away],
        match=match,
        international=international,
    )


# --- Classement ----------------------------------------------------------------------------


def table_article(
    code: str,
    competition: str,
    table: Table,
    teams: dict[int, Team],
    day: datetime.date,
    international: bool = False,
) -> Article | None:
    """Le point sur un classement après sa dernière journée ; un changement de leader
    fait un titre à lui seul."""
    if len(table.rows) < 3:
        return None
    first, second, third = (teams[row.club_id] for row in table.rows[:3])
    last = teams[table.rows[-1].club_id]
    points = [row.league_points for row in table.rows[:3]]
    was = table.previous.get(first.id)
    weight = TABLE_WEIGHT
    if was not in (None, 1) and table.readable:
        weight = LEADER_WEIGHT
        title = f"{first.does("s'empare", "s'emparent")} de la première place"
    else:
        title = f"{cap(first.subject)} en tête après {_plural(table.rounds, 'journée')}"
    gap = points[0] - points[1]
    lead = f"{_plural(gap, 'point')} d'avance" if gap > 0 else "à égalité de points"
    body = (
        f"{_plural(points[0], 'point')} pour {first.subject}, {lead} sur {second.subject}. "
        f"{third.does('complète', 'complètent')} le podium. "
        f"{last.does('ferme', 'ferment')} la marche."
    )
    return Article(
        key=f"table-{code}-{table.rounds}",
        kind=Kind.STANDING,
        date=day,
        title=title,
        body=body,
        weight=weight + (INTERNATIONAL_BONUS if international else 0.0),
        competition=competition,
        teams=[first],
        international=international,
    )


def cup_title_article(code: str, competition: str, winner: Team, day: datetime.date) -> Article:
    """Une coupe de clubs (la Coupe d'Europe) s'achève sur sa finale."""
    return Article(
        key=f"title-{code}",
        kind=Kind.RESULT,
        date=day,
        title=f"{competition} : {winner.subject} {winner.verb('soulève', 'soulèvent')} le trophée",
        body=f"{winner.does('remporte', 'remportent')} la finale et règne sur l'Europe.",
        weight=TITLE_WEIGHT,
        competition=competition,
        teams=[winner],
    )


def title_article(code: str, competition: str, winner: Team, day: datetime.date) -> Article:
    """Une fenêtre internationale s'achève sur un vainqueur."""
    return Article(
        key=f"title-{code}",
        kind=Kind.SELECTION,
        date=day,
        title=f"{competition} : le titre pour {winner.subject}",
        body=f"{winner.does('termine', 'terminent')} en tête du classement final.",
        weight=TITLE_WEIGHT,
        competition=competition,
        teams=[winner],
        international=True,
    )


# --- Mouvements ----------------------------------------------------------------------------


def _star(overall: float, per_point: float) -> float:
    return max(0.0, level_at_overall(overall) - NOTABLE_LEVEL) * per_point


def move_article(move: Move) -> Article:
    """Un transfert, un prêt, une signature, un départ ou une retraite."""
    player, origin, to = move.player, move.origin, move.destination
    who = f"{player.noun} de {player.age} ans"
    seed = player.id or 0
    weight = MOVE_WEIGHT + _star(player.overall, 7)
    if move.kind == MoveKind.TRANSFER:
        weight += 8
        title = _pick(
            [
                f"{player.name} rejoint {to.subject}",
                f"{to.does("s'offre", "s'offrent")} {player.name}",
            ],
            seed,
        )
        body = f"{cap(who)} quitte {origin.subject}"
        body += f" : indemnité de {money(move.fee)}." if move.fee else "."
    elif move.kind == MoveKind.LOAN:
        title = f"{to.does('obtient', 'obtiennent')} le prêt {of(player.name)}"
        body = (
            f"{cap(who)}, sous contrat avec {origin.subject}, "
            "est prêté jusqu'à la fin de la saison."
        )
    elif move.kind == MoveKind.PRECONTRACT and move.pending:
        title = f"{player.name} rejoindra {to.subject}"
        body = f"En fin de contrat avec {origin.subject}, {who} a signé pour la saison prochaine."
    elif move.kind in (MoveKind.PRECONTRACT, MoveKind.FREE) and origin is not None:
        title = f"{player.name} quitte {origin.subject} pour {to.subject}"
        body = f"{cap(who)} arrive libre, au terme de son contrat."
    elif move.kind == MoveKind.JOKER:
        title = f"{to.does('engage', 'engagent')} {player.name} en joker médical"
        body = f"{cap(who)} vient pallier une longue blessure."
    elif move.kind == MoveKind.RELEASE:
        weight -= 6
        title = f"{player.name} quitte {origin.subject}"
        body = f"En fin de contrat, {who} est libre de s'engager où il veut."
    elif move.kind == MoveKind.RETIREMENT:
        title = f"{player.name} raccroche les crampons"
        club = f" ({origin.name})" if origin is not None else ""
        body = f"À {player.age} ans, {player.noun}{club} met un terme à sa carrière."
    else:  # agent libre, ou pré-contrat dont on ignore le club d'origine
        title = f"{to.does('engage', 'engagent')} {player.name}"
        body = f"Sans club, {who} retrouve un contrat."
        if move.kind == MoveKind.PRECONTRACT:
            body = f"{cap(who)} arrive libre, au terme de son contrat."
    return Article(
        key=f"move-{move.key}",
        kind=Kind.TRANSFER,
        date=move.date,
        title=title,
        body=body,
        weight=weight,
        teams=[team for team in (origin, to) if team is not None],
        player=player,
        move=move,
    )


def contract_article(player: Person, club: Team, day: datetime.date) -> Article:
    """Un joueur en dernière année de contrat : il peut signer ailleurs dès maintenant."""
    return Article(
        key=f"contract-{player.id}",
        kind=Kind.MARKET,
        date=day,
        title=f"{player.name} en fin de contrat",
        body=(
            f"{cap(player.noun)} de {player.age} ans (note {note(player.overall)}) entre dans "
            f"les derniers mois de son bail avec {club.subject} : il peut signer un "
            "pré-contrat ailleurs dès maintenant."
        ),
        weight=MARKET_WEIGHT + _star(player.overall, 3),
        teams=[club],
        player=player,
    )


def free_agent_article(player: Person, seasons_out: int, day: datetime.date) -> Article:
    """Un agent libre de bon niveau, à signer tout de suite."""
    since = "depuis plus d'une saison" if seasons_out >= 1 else "depuis l'intersaison"
    return Article(
        key=f"free-{player.id}",
        kind=Kind.MARKET,
        date=day,
        title=f"{player.name} toujours sans club",
        body=(
            f"Libre {since}, {player.noun} de {player.age} ans (note {note(player.overall)}) "
            "attend une offre : il peut s'engager du jour au lendemain."
        ),
        weight=MARKET_WEIGHT + _star(player.overall, 3),
        player=player,
    )


# --- Infirmerie ----------------------------------------------------------------------------


def injury_article(player: Person, club: Team | None, injury: Injury) -> Article:
    """Une blessure qui écarte un joueur des terrains."""
    weeks = max(1, round((injury.return_date - injury.occurred_on).days / 7))
    where = "en match" if injury.source == InjurySource.MATCH else "à l'entraînement"
    if club is not None:
        title = _pick(
            [
                f"{player.name} absent {_plural(weeks, 'semaine')}",
                f"Coup dur pour {club.subject} : {player.name} forfait",
            ],
            player.id or 0,
        )
    else:
        title = f"{player.name} absent {_plural(weeks, 'semaine')}"
    return Article(
        key=f"injury-{injury.id}",
        kind=Kind.INJURY,
        date=injury.occurred_on,
        title=title,
        body=(
            f"{cap(player.noun)} de {player.age} ans s'est blessé {where} ({injury.kind}). "
            f"Retour prévu le {short_day(injury.return_date)}."
        ),
        weight=INJURY_WEIGHT + _star(player.overall, 4) + min(weeks, 16) * 0.8,
        teams=[club] if club is not None else [],
        player=player,
    )


_SUSPENSION_CAUSES = {
    "red_card": "après son carton rouge",
    "second_yellow": "après son second carton jaune du match",
    "yellow_cards": "pour son troisième carton jaune de la saison",
}


def suspension_article(
    key: int, player: Person, club: Team, matches: int, reason: str, day: datetime.date
) -> Article:
    """Une suspension prononcée par la commission de discipline (engine/discipline.py)."""
    title = _pick(
        [
            f"{player.name} suspendu {_plural(matches, 'match')}",
            f"{cap(club.subject)} privé{'s' if club.plural else ''} de {player.name}",
        ],
        key,
    )
    return Article(
        key=f"suspension-{key}",
        kind=Kind.DISCIPLINE,
        date=day,
        title=title,
        body=(
            f"La commission de discipline a suspendu {player.noun} de {club.subject} "
            f"{_plural(matches, 'match')} {_SUSPENSION_CAUSES[reason]}."
        ),
        weight=SUSPENSION_WEIGHT + _star(player.overall, 4) + min(matches, 6),
        teams=[club],
        player=player,
    )


# --- Sélections ----------------------------------------------------------------------------


def squad_article(
    code: str,
    nation: Team,
    competition: str,
    size: int,
    clubs: list[tuple[str, int]],
    day: datetime.date,
) -> Article:
    """Une sélection annonce sa liste. `clubs` : (club, joueurs retenus), les plus
    représentés d'abord."""
    body = f"{_plural(size, 'joueur')} retenus."
    if clubs:
        names = ", ".join(f"{name} ({count})" for name, count in clubs[:3])
        body += f" Clubs les plus représentés : {names}."
    return Article(
        key=f"squad-{code}-{nation.id}",
        kind=Kind.SELECTION,
        date=day,
        title=f"{nation.does('dévoile', 'dévoilent')} {nation.verb('sa', 'leur')} liste",
        body=body,
        weight=SQUAD_WEIGHT,
        competition=competition,
        teams=[nation],
        international=True,
    )


# --- Coulisses -----------------------------------------------------------------------------


def dismissal_article(key: int, manager: str, club: Team, day: datetime.date) -> Article:
    return Article(
        key=f"dismissal-{key}",
        kind=Kind.CLUB,
        date=day,
        title=f"{club.does('se sépare', 'se séparent')} {of(manager)}",
        body=f"La direction a tranché le {short_day(day)} : les résultats ne suivaient plus.",
        weight=DISMISSAL_WEIGHT,
        teams=[club],
    )


# --- La mise en page -----------------------------------------------------------------------

FRONT_PAGE = 6  # la une, puis cinq articles mis en avant
EDITION_SIZE = 70
# Une nouvelle de la semaine garde tout son poids ; ensuite elle s'efface, sans disparaître.
FRESH_DAYS = 8
STALE_DAYS = 30
STALE_FLOOR = 0.3
# Sur la une, chaque article d'un même genre déjà retenu fait reculer les suivants.
SAME_KIND = 0.65


def freshness(article: Article, today: datetime.date, quiet: int = 0) -> float:
    """Ce qu'il reste du poids d'un article. `quiet` : les jours qui viennent de passer
    sans que rien n'arrive (intersaison, trêve) ; ils ne vieillissent pas les nouvelles."""
    age = max(0, abs((today - article.date).days) - quiet)
    return max(STALE_FLOOR, 1 - max(0, age - FRESH_DAYS) / STALE_DAYS)


def edition(articles: Iterable[Article], today: datetime.date, quiet: int = 0) -> list[Article]:
    """Le journal du jour, du sujet le plus lourd au plus léger ; en tête, la une, qu'un
    même genre ne peut pas occuper toute."""
    score = {a.key: a.weight * freshness(a, today, quiet) for a in articles}
    pool = sorted({a.key: a for a in articles}.values(), key=lambda a: score[a.key], reverse=True)
    pool = pool[:EDITION_SIZE]
    front: list[Article] = []
    seen: Counter[Kind] = Counter()
    while pool and len(front) < FRONT_PAGE:
        best = max(pool, key=lambda a: score[a.key] * SAME_KIND ** seen[a.kind])
        pool.remove(best)
        front.append(best)
        seen[best.kind] += 1
    return front + pool
