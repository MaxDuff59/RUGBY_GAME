"""Les sélections nationales : seize nations, et leurs rendez-vous de la saison.

Un joueur porte la nationalité de sa fiche (data/rosters.json) ; un joueur
inventé prend celle du pays de son club. Trois fenêtres internationales par
saison, chacune avec ses dates (un match par samedi, comme les championnats) :

- le Rugby Championship, d'août à octobre (hémisphère Sud, aller-retour) ;
- les tournées d'automne, en novembre : les nations du Tournoi reçoivent celles
  du Sud, les Fidji et la Géorgie ;
- le Tournoi des Six Nations, en février-mars (un seul match contre chacun).

Une saison sur quatre (engine/calendar.py), la Coupe du monde remplace le Rugby
Championship et les tournées d'automne : seize nations, quatre poules de quatre
puis quarts, demies et finale, en six samedis de septembre-octobre. Quatre de
ces nations (Japon, Samoa, Tonga, Portugal) n'ont pas d'autre rendez-vous : on
ne les dirige pas.

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
    # Sa fédération ne retient que les joueurs des clubs du pays.
    home_only: bool = False


NATIONS = [
    Nation("FRA", "France", NATION_ID_BASE + 1, 13.5),
    Nation("ENG", "Angleterre", NATION_ID_BASE + 2, 13.5, home_only=True),
    Nation("IRE", "Irlande", NATION_ID_BASE + 3, 13.5, home_only=True),
    Nation("SCO", "Écosse", NATION_ID_BASE + 4, 13.0),
    Nation("WAL", "Pays de Galles", NATION_ID_BASE + 5, 12.5),
    Nation("ITA", "Italie", NATION_ID_BASE + 6, 12.5),
    Nation("NZL", "Nouvelle-Zélande", NATION_ID_BASE + 7, 14.0, home_only=True),
    Nation("RSA", "Afrique du Sud", NATION_ID_BASE + 8, 14.0),
    Nation("AUS", "Australie", NATION_ID_BASE + 9, 13.0),
    Nation("ARG", "Argentine", NATION_ID_BASE + 10, 13.0),
    Nation("FIJ", "Fidji", NATION_ID_BASE + 11, 12.5),
    Nation("GEO", "Géorgie", NATION_ID_BASE + 12, 12.0),
    # Invitées de la Coupe du monde : presque tout leur groupe vient d'ailleurs.
    Nation("JPN", "Japon", NATION_ID_BASE + 13, 11.5),
    Nation("SAM", "Samoa", NATION_ID_BASE + 14, 11.0),
    Nation("TON", "Tonga", NATION_ID_BASE + 15, 11.0),
    Nation("POR", "Portugal", NATION_ID_BASE + 16, 10.5),
]
NATIONS_BY_CODE = {nation.code: nation for nation in NATIONS}
NATIONS_BY_ID = {nation.id: nation for nation in NATIONS}

# Les fiches des joueurs n'écrivent pas toutes un pays de la même façon.
_ALIASES = {"FJI": "FIJ", "TGA": "TON", "MAR": "MOR", "COK": "COO", "IRL": "IRE"}


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

# Têtes de série de la Coupe du monde : quatre chapeaux, une nation de chacun par poule.
WORLD_CUP_POTS = (
    ("RSA", "NZL", "IRE", "FRA"),
    ("ENG", "ARG", "SCO", "AUS"),
    ("ITA", "WAL", "FIJ", "GEO"),
    ("JPN", "SAM", "TON", "POR"),
)
WORLD_CUP = Window(
    code="world_cup",
    name="Coupe du monde",
    short_name="Mondial",
    start=WORLD_CUP_START,
    weeks=(True,) * WORLD_CUP_ROUNDS,
    format="world_cup",
    nations=tuple(code for pot in WORLD_CUP_POTS for code in pot),
)

# Toutes les fenêtres, dans l'ordre de la saison (août à mars) ; celles d'une saison
# donnée : `season_windows`.
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
    WORLD_CUP,
    Window(
        code="autumn",
        name="Tournées d'automne",
        short_name="Tournées",
        start=(11, 14),
        weeks=(True, True, True),
        format="tours",
        nations=SIX_NATIONS,
        visitors=(*RUGBY_CHAMPIONSHIP, "FIJ", "GEO"),
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
]
WINDOWS_BY_CODE = {window.code: window for window in WINDOWS}
# Ce que la Coupe du monde remplace la saison où elle se joue.
_REPLACED_BY_WORLD_CUP = {"rugby_championship", "autumn"}


def window(code: str) -> Window:
    return WINDOWS_BY_CODE[code]


def season_windows(year: int) -> list[Window]:
    """Les fenêtres de la saison `year` : la Coupe du monde, une saison sur quatre, à
    la place du Rugby Championship et des tournées d'automne."""
    if is_world_cup_year(year):
        return [w for w in WINDOWS if w.code not in _REPLACED_BY_WORLD_CUP]
    return [w for w in WINDOWS if w is not WORLD_CUP]
