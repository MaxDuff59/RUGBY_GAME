"""Les sélections nationales : trente-six nations, et leurs rendez-vous de la saison.

Un joueur porte la nationalité de sa fiche (data/rosters.json) ; un joueur
inventé prend celle du pays de son club. Une sélection qui ne trouve pas assez de
monde dans les championnats du jeu appelle des joueurs qui évoluent ailleurs
(engine/internationals.py, `reinforcements`) : c'est le cas de la plupart des
nouvelles nations du rugby. Chaque fenêtre internationale a ses dates (un match par
samedi, comme les championnats) :

- d'août à octobre, le Rugby Championship (hémisphère Sud, aller-retour) et la
  Pacific Nations Cup (Fidji, Samoa, Tonga, Japon, États-Unis, Canada) ;
- en novembre, les tournées d'automne (les nations du Tournoi reçoivent celles du
  Sud, les Fidji, la Géorgie et le Japon) et les tests de novembre des nations
  émergentes ;
- en février-mars, le Tournoi des Six Nations et le Rugby Europe Championship ;
- en avril-mai, les championnats d'Amérique du Sud, d'Afrique et d'Asie.

Une saison sur quatre (engine/calendar.py), la Coupe du monde remplace les rendez-vous
d'août à novembre : vingt-quatre nations, six poules de quatre, puis huitièmes, quarts,
demies et finale. Ses chapeaux suivent le classement mondial (engine/ranking.py) au
moment du tirage.

Un championnat qui joue un samedi de match international est en « doublon » :
ses internationaux manquent à leur club ce jour-là (engine/internationals.py).
"""

from dataclasses import dataclass

from data.leagues import LEAGUES_BY_CODE
from engine.calendar import WORLD_CUP_ROUNDS, WORLD_CUP_START, is_world_cup_year

# Identifiants d'équipe des sélections dans les matchs : loin de ceux des clubs.
NATION_ID_BASE = 9000


@dataclass(frozen=True)
class Nation:
    code: str  # trois lettres : la nationalité des joueurs (`Player.nationality`)
    name: str
    id: int
    # Niveau (sur 20) des joueurs que la sélection va chercher hors des championnats
    # du jeu, quand ses clubs ne fournissent pas assez de monde à un poste.
    level: float
    # Ses points au classement mondial au début d'une partie (engine/ranking.py).
    points: float = 50.0
    # Sa fédération ne retient que les joueurs des clubs du pays.
    home_only: bool = False


NATIONS = [
    Nation("FRA", "France", NATION_ID_BASE + 1, 13.5, 87.0),
    Nation("ENG", "Angleterre", NATION_ID_BASE + 2, 13.5, 89.0, home_only=True),
    Nation("IRE", "Irlande", NATION_ID_BASE + 3, 13.5, 88.0, home_only=True),
    Nation("SCO", "Écosse", NATION_ID_BASE + 4, 13.0, 81.0),
    Nation("WAL", "Pays de Galles", NATION_ID_BASE + 5, 12.5, 74.0),
    Nation("ITA", "Italie", NATION_ID_BASE + 6, 12.5, 78.5),
    Nation("NZL", "Nouvelle-Zélande", NATION_ID_BASE + 7, 14.0, 90.5, home_only=True),
    Nation("RSA", "Afrique du Sud", NATION_ID_BASE + 8, 14.0, 93.0),
    Nation("AUS", "Australie", NATION_ID_BASE + 9, 13.0, 81.5),
    Nation("ARG", "Argentine", NATION_ID_BASE + 10, 13.0, 84.5),
    Nation("FIJ", "Fidji", NATION_ID_BASE + 11, 12.5, 80.0),
    Nation("GEO", "Géorgie", NATION_ID_BASE + 12, 12.0, 74.5),
    Nation("JPN", "Japon", NATION_ID_BASE + 13, 11.5, 73.5),
    Nation("SAM", "Samoa", NATION_ID_BASE + 14, 11.0, 69.5),
    Nation("TON", "Tonga", NATION_ID_BASE + 15, 11.0, 66.5),
    Nation("POR", "Portugal", NATION_ID_BASE + 16, 10.5, 70.0),
    # Les nations émergentes : quelques joueurs dans nos championnats, le gros de leur
    # groupe ailleurs.
    Nation("ESP", "Espagne", NATION_ID_BASE + 17, 10.5, 69.0),
    Nation("ROU", "Roumanie", NATION_ID_BASE + 18, 10.0, 63.0),
    Nation("NED", "Pays-Bas", NATION_ID_BASE + 19, 9.0, 58.0),
    Nation("BEL", "Belgique", NATION_ID_BASE + 20, 9.0, 59.5),
    Nation("GER", "Allemagne", NATION_ID_BASE + 21, 8.5, 55.5),
    Nation("SUI", "Suisse", NATION_ID_BASE + 22, 8.0, 54.0),
    Nation("USA", "États-Unis", NATION_ID_BASE + 23, 10.0, 66.0),
    Nation("CAN", "Canada", NATION_ID_BASE + 24, 9.5, 61.5),
    Nation("URU", "Uruguay", NATION_ID_BASE + 25, 10.5, 70.5),
    Nation("CHI", "Chili", NATION_ID_BASE + 26, 10.0, 64.5),
    Nation("BRA", "Brésil", NATION_ID_BASE + 27, 8.5, 56.5),
    Nation("PAR", "Paraguay", NATION_ID_BASE + 28, 8.0, 52.5),
    Nation("NAM", "Namibie", NATION_ID_BASE + 29, 9.0, 61.0),
    Nation("ZIM", "Zimbabwe", NATION_ID_BASE + 30, 8.5, 57.5),
    Nation("KEN", "Kenya", NATION_ID_BASE + 31, 8.0, 54.5),
    Nation("ALG", "Algérie", NATION_ID_BASE + 32, 7.5, 50.5),
    Nation("HKG", "Hong Kong", NATION_ID_BASE + 33, 8.5, 60.0),
    Nation("KOR", "Corée du Sud", NATION_ID_BASE + 34, 8.0, 54.0),
    Nation("UAE", "Émirats arabes unis", NATION_ID_BASE + 35, 7.0, 48.5),
    Nation("SRI", "Sri Lanka", NATION_ID_BASE + 36, 7.0, 49.0),
]
NATIONS_BY_CODE = {nation.code: nation for nation in NATIONS}
NATIONS_BY_ID = {nation.id: nation for nation in NATIONS}

# Les fiches des joueurs n'écrivent pas toutes un pays de la même façon.
_ALIASES = {
    "FJI": "FIJ",
    "TGA": "TON",
    "MAR": "MOR",
    "COK": "COO",
    "IRL": "IRE",
    "ROM": "ROU",
}


def nation_code(raw: str | None) -> str | None:
    """Le code de nationalité tel que le jeu l'écrit (None s'il est inconnu)."""
    if not raw:
        return None
    code = raw.strip().upper()
    return _ALIASES.get(code, code)


def nation(code: str) -> Nation:
    return NATIONS_BY_CODE[code]


# --- Le pays de chaque club ----------------------------------------------------------------

_LEAGUE_NATION = {"top14": "FRA", "prod2": "FRA", "premiership": "ENG"}
# Championnats à plusieurs pays : club par club.
_CLUB_NATION = {
    "Leinster Rugby": "IRE",
    "Munster Rugby": "IRE",
    "Ulster Rugby": "IRE",
    "Connacht Rugby": "IRE",
    "Glasgow Warriors": "SCO",
    "Edinburgh Rugby": "SCO",
    "Benetton Rugby": "ITA",
    "Zebre Parma": "ITA",
    "Bulls": "RSA",
    "Stormers": "RSA",
    "Sharks": "RSA",
    "Lions": "RSA",
    "Crusaders": "NZL",
    "Chiefs": "NZL",
    "Hurricanes": "NZL",
    "Blues": "NZL",
    "Highlanders": "NZL",
    "Brumbies": "AUS",
    "Queensland Reds": "AUS",
    "NSW Waratahs": "AUS",
    "Western Force": "AUS",
    "Fijian Drua": "FIJ",
    "Moana Pasifika": "SAM",
}
CLUB_NATION: dict[str, str] = {
    **{
        club.name: code
        for league, code in _LEAGUE_NATION.items()
        for club in LEAGUES_BY_CODE[league].clubs
    },
    **_CLUB_NATION,
}


def home_nation(club_name: str | None) -> str | None:
    """Le pays d'un vrai club (None pour un club inventé) : la nationalité de ses
    joueurs inventés et des jeunes de son centre de formation."""
    return CLUB_NATION.get(club_name) if club_name else None


# --- Les fenêtres internationales -----------------------------------------------------------


@dataclass(frozen=True)
class Window:
    code: str
    name: str
    short_name: str
    # Premier samedi possible (mois, jour), puis les samedis joués (True) ou de repos.
    start: tuple[int, int]
    weeks: tuple[bool, ...]
    # tournament : tous contre tous une fois (les réceptions s'inversent chaque année) ;
    # home_away : aller-retour ; tours : `nations` reçoit `visitors`, un adversaire par
    # samedi ; world_cup : poules de quatre sur terrain neutre, puis élimination directe.
    format: str
    nations: tuple[str, ...]
    visitors: tuple[str, ...] = ()

    @property
    def teams(self) -> tuple[str, ...]:
        return (*self.nations, *self.visitors)

    @property
    def has_table(self) -> bool:
        """Un classement et un vainqueur (pas pour une tournée de tests)."""
        return self.format != "tours"


SIX_NATIONS = ("FRA", "ENG", "IRE", "SCO", "WAL", "ITA")
RUGBY_CHAMPIONSHIP = ("NZL", "RSA", "AUS", "ARG")
PACIFIC_NATIONS = ("FIJ", "SAM", "TON", "JPN", "USA", "CAN")
RUGBY_EUROPE = ("GEO", "POR", "ESP", "ROU", "BEL", "NED", "GER", "SUI")

# Les vingt-quatre nations de la Coupe du monde. Le tirage les range en quatre chapeaux de
# six d'après le classement mondial (engine/internationals.py, `world_cup_pools`).
WORLD_CUP_NATIONS = (
    *RUGBY_CHAMPIONSHIP,
    *SIX_NATIONS,
    "FIJ",
    "GEO",
    "JPN",
    "SAM",
    "TON",
    "POR",
    "ESP",
    "ROU",
    "USA",
    "CAN",
    "URU",
    "CHI",
    "ZIM",
    "HKG",
)
WORLD_CUP = Window(
    code="world_cup",
    name="Coupe du monde",
    short_name="Mondial",
    start=WORLD_CUP_START,
    weeks=(True,) * WORLD_CUP_ROUNDS,
    format="world_cup",
    nations=WORLD_CUP_NATIONS,
)

# Toutes les fenêtres, dans l'ordre de la saison (août à mai) ; celles d'une saison
# donnée : `season_windows`. Une même nation n'a jamais deux fenêtres qui se chevauchent.
WINDOWS = [
    Window(
        code="rugby_championship",
        name="Rugby Championship",
        short_name="Championship",
        start=(8, 15),
        weeks=(True, True, False, True, True, False, True, True),
        format="home_away",
        nations=RUGBY_CHAMPIONSHIP,
    ),
    Window(
        code="pacific_nations",
        name="Pacific Nations Cup",
        short_name="Pacifique",
        start=(8, 22),
        weeks=(True, True, False, True, True, True),
        format="tournament",
        nations=PACIFIC_NATIONS,
    ),
    WORLD_CUP,
    Window(
        code="autumn",
        name="Tournées d'automne",
        short_name="Tournées",
        start=(11, 14),
        weeks=(True, True, True),
        format="tours",
        nations=SIX_NATIONS,
        visitors=(*RUGBY_CHAMPIONSHIP, "FIJ", "GEO", "JPN"),
    ),
    Window(
        code="november_tests",
        name="Tests de novembre",
        short_name="Tests",
        start=(11, 14),
        weeks=(True, True, True),
        format="tours",
        nations=("ESP", "POR", "ROU", "URU"),
        visitors=("USA", "CAN", "SAM", "TON", "CHI", "NAM"),
    ),
    Window(
        code="six_nations",
        name="Tournoi des Six Nations",
        short_name="Six Nations",
        start=(2, 1),
        weeks=(True, True, False, True, True, False, True),
        format="tournament",
        nations=SIX_NATIONS,
    ),
    Window(
        code="rugby_europe",
        name="Rugby Europe Championship",
        short_name="Rugby Europe",
        start=(2, 1),
        weeks=(True, True, False, True, True, False, True, True, True),
        format="tournament",
        nations=RUGBY_EUROPE,
    ),
    Window(
        code="sudamericano",
        name="Championnat sud-américain",
        short_name="Sudamericano",
        start=(4, 18),
        weeks=(True, True, True),
        format="tournament",
        nations=("URU", "CHI", "BRA", "PAR"),
    ),
    Window(
        code="africa_cup",
        name="Rugby Africa Cup",
        short_name="Africa Cup",
        start=(4, 18),
        weeks=(True, True, True),
        format="tournament",
        nations=("NAM", "ZIM", "KEN", "ALG"),
    ),
    Window(
        code="asia",
        name="Asia Rugby Championship",
        short_name="Asie",
        start=(4, 18),
        weeks=(True, True, True),
        format="tournament",
        nations=("HKG", "KOR", "UAE", "SRI"),
    ),
]
WINDOWS_BY_CODE = {window.code: window for window in WINDOWS}
# Ce que la Coupe du monde remplace la saison où elle se joue : tout ce qui se joue
# d'août à novembre.
_REPLACED_BY_WORLD_CUP = {"rugby_championship", "pacific_nations", "autumn", "november_tests"}


def window(code: str) -> Window:
    return WINDOWS_BY_CODE[code]


def season_windows(year: int) -> list[Window]:
    """Les fenêtres de la saison `year` : la Coupe du monde, une saison sur quatre, à
    la place de celles d'août à novembre."""
    if is_world_cup_year(year):
        return [w for w in WINDOWS if w.code not in _REPLACED_BY_WORLD_CUP]
    return [w for w in WINDOWS if w is not WORLD_CUP]
