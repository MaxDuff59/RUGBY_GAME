"""Les vrais championnats (saison 2025-26) : leurs clubs, stades, formule et calendrier.

Seuls les clubs sont réels : les joueurs et le staff restent inventés par le
générateur. `level` est le niveau sportif visé (sur 20, comme les attributs) ;
`wealth` dose l'argent et le staff (0 = club modeste, 1 = gros budget).
Les capacités sont arrondies ; le jeu plafonne les plus grandes enceintes au
plus grand stade constructible (voir `STADIUM_STEPS`, engine/economy.py).

Chaque championnat se joue en aller-retour, puis en phases finales selon sa
formule (engine/season.py, `PlayoffFormat`). Le calendrier (engine/calendar.py)
démarre à sa date et saute ses trêves : tous finissent vers juin, sauf le Super
Rugby, de février à l'été (saison de l'hémisphère Sud).
"""

from dataclasses import dataclass, field

from engine.season import PlayoffFormat

# Championnat des clubs inventés, et le seul où l'on peut monter (depuis la Pro D2).
DEFAULT_LEAGUE = "top14"


@dataclass(frozen=True)
class RealClub:
    name: str
    city: str
    stadium: str
    capacity: int
    level: float
    wealth: float


@dataclass(frozen=True)
class League:
    code: str
    name: str
    short_name: str
    country: str
    playoffs: PlayoffFormat
    # Finale sur terrain neutre (Top 14, Pro D2, Premiership) ou chez le mieux classé.
    neutral_final: bool
    # Premier samedi possible (mois, jour) et trêves ((mois, jour), samedis sautés).
    start: tuple[int, int]
    breaks: tuple[tuple[tuple[int, int], int], ...] = ()
    # Primes de phases finales, en part de celles du Top 14.
    prize_factor: float = 1.0
    clubs: list[RealClub] = field(default_factory=list)


TOP14 = [
    RealClub("Stade Toulousain", "Toulouse", "Stade Ernest-Wallon", 19_000, 14.0, 1.0),
    RealClub("Union Bordeaux-Bègles", "Bordeaux", "Stade Chaban-Delmas", 33_000, 13.5, 0.85),
    RealClub("RC Toulon", "Toulon", "Stade Mayol", 16_000, 12.5, 0.8),
    RealClub("Stade Rochelais", "La Rochelle", "Stade Marcel-Deflandre", 16_000, 12.5, 0.75),
    RealClub(
        "ASM Clermont Auvergne", "Clermont-Ferrand", "Stade Marcel-Michelin", 19_000, 12.0, 0.7
    ),
    RealClub("Racing 92", "Nanterre", "Paris La Défense Arena", 30_000, 11.5, 0.85),
    RealClub("Aviron Bayonnais", "Bayonne", "Stade Jean-Dauger", 17_000, 11.5, 0.55),
    RealClub("Castres Olympique", "Castres", "Stade Pierre-Fabre", 12_500, 11.5, 0.5),
    RealClub("Section Paloise", "Pau", "Stade du Hameau", 18_000, 11.0, 0.55),
    RealClub("Stade Français Paris", "Paris", "Stade Jean-Bouin", 20_000, 10.5, 0.75),
    RealClub("LOU Rugby", "Lyon", "Matmut Stadium de Gerland", 25_000, 10.5, 0.65),
    RealClub("Montpellier Hérault Rugby", "Montpellier", "GGL Stadium", 15_500, 10.5, 0.65),
    RealClub("USA Perpignan", "Perpignan", "Stade Aimé-Giral", 14_500, 10.0, 0.45),
    RealClub("US Montauban", "Montauban", "Stade Sapiac", 11_000, 8.5, 0.2),
]

PROD2 = [
    RealClub("RC Vannes", "Vannes", "Stade de la Rabine", 11_300, 9.5, 0.35),
    RealClub("FC Grenoble", "Grenoble", "Stade des Alpes", 20_000, 9.5, 0.3),
    RealClub("Oyonnax Rugby", "Oyonnax", "Stade Charles-Mathon", 11_500, 9.0, 0.25),
    RealClub("Provence Rugby", "Aix-en-Provence", "Stade Maurice-David", 8_800, 9.0, 0.3),
    RealClub("CA Brive", "Brive-la-Gaillarde", "Stade Amédée-Domenech", 14_000, 9.0, 0.3),
    RealClub("Colomiers Rugby", "Colomiers", "Stade Michel-Bendichou", 11_400, 8.5, 0.15),
    RealClub("SU Agen", "Agen", "Stade Armandie", 14_400, 8.5, 0.2),
    RealClub("AS Béziers Hérault", "Béziers", "Stade Raoul-Barrière", 18_500, 8.5, 0.25),
    RealClub("Biarritz Olympique", "Biarritz", "Parc des Sports Aguiléra", 15_000, 8.5, 0.2),
    RealClub("Valence Romans Drôme Rugby", "Valence", "Stade Georges-Pompidou", 15_000, 8.5, 0.15),
    RealClub("Stade Aurillacois", "Aurillac", "Stade Jean-Alric", 9_000, 8.0, 0.1),
    RealClub("Stade Montois", "Mont-de-Marsan", "Stade Guy-Boniface", 16_800, 8.0, 0.15),
    RealClub("USON Nevers", "Nevers", "Stade du Pré-Fleuri", 7_500, 8.0, 0.15),
    RealClub("US Dax", "Dax", "Stade Maurice-Boyau", 7_300, 7.5, 0.1),
    RealClub("Soyaux Angoulême XV", "Angoulême", "Stade Chanzy", 8_000, 7.5, 0.1),
    RealClub("US Carcassonne", "Carcassonne", "Stade Albert-Domec", 6_500, 7.5, 0.05),
]

PREMIERSHIP = [
    RealClub("Bath Rugby", "Bath", "The Recreation Ground", 14_500, 13.5, 0.8),
    RealClub("Northampton Saints", "Northampton", "Franklin's Gardens", 15_200, 13.0, 0.7),
    RealClub("Leicester Tigers", "Leicester", "Welford Road", 25_800, 12.5, 0.75),
    RealClub("Bristol Bears", "Bristol", "Ashton Gate", 27_000, 12.5, 0.7),
    RealClub("Saracens", "Londres", "StoneX Stadium", 10_500, 12.5, 0.75),
    RealClub("Sale Sharks", "Salford", "Salford Community Stadium", 12_000, 12.0, 0.6),
    RealClub("Harlequins", "Londres", "Twickenham Stoop", 14_800, 11.5, 0.7),
    RealClub("Gloucester Rugby", "Gloucester", "Kingsholm", 16_100, 11.5, 0.6),
    RealClub("Exeter Chiefs", "Exeter", "Sandy Park", 15_600, 11.5, 0.6),
    RealClub("Newcastle Red Bulls", "Newcastle", "Kingston Park", 10_200, 10.0, 0.45),
]

# Sans les provinces galloises : Irlande, Écosse, Italie et Afrique du Sud.
URC = [
    RealClub("Leinster Rugby", "Dublin", "RDS Arena", 18_500, 14.5, 0.9),
    RealClub("Munster Rugby", "Limerick", "Thomond Park", 25_600, 12.5, 0.65),
    RealClub("Ulster Rugby", "Belfast", "Ravenhill", 18_200, 11.5, 0.6),
    RealClub("Connacht Rugby", "Galway", "The Sportsground", 12_100, 10.5, 0.45),
    RealClub("Glasgow Warriors", "Glasgow", "Scotstoun Stadium", 7_400, 12.5, 0.55),
    RealClub("Edinburgh Rugby", "Édimbourg", "Edinburgh Rugby Stadium", 7_800, 11.0, 0.5),
    RealClub("Benetton Rugby", "Trévise", "Stadio Comunale di Monigo", 5_000, 10.5, 0.45),
    RealClub("Zebre Parma", "Parme", "Stadio Sergio Lanfranchi", 5_000, 9.0, 0.25),
    RealClub("Bulls", "Pretoria", "Loftus Versfeld", 51_800, 13.0, 0.6),
    RealClub("Stormers", "Le Cap", "Cape Town Stadium", 55_000, 12.5, 0.55),
    RealClub("Sharks", "Durban", "Kings Park", 52_000, 12.0, 0.6),
    RealClub("Lions", "Johannesburg", "Ellis Park", 62_500, 11.0, 0.45),
]

SUPER_RUGBY = [
    RealClub("Crusaders", "Christchurch", "Apollo Projects Stadium", 17_100, 13.5, 0.6),
    RealClub("Chiefs", "Hamilton", "FMG Stadium Waikato", 25_800, 13.5, 0.55),
    RealClub("Hurricanes", "Wellington", "Sky Stadium", 34_500, 13.0, 0.55),
    RealClub("Blues", "Auckland", "Eden Park", 50_000, 13.0, 0.6),
    RealClub("Brumbies", "Canberra", "GIO Stadium", 25_000, 12.5, 0.5),
    RealClub("Highlanders", "Dunedin", "Forsyth Barr Stadium", 30_700, 11.5, 0.45),
    RealClub("Queensland Reds", "Brisbane", "Suncorp Stadium", 52_500, 11.5, 0.5),
    RealClub("NSW Waratahs", "Sydney", "Allianz Stadium", 42_500, 11.0, 0.5),
    RealClub("Western Force", "Perth", "HBF Park", 20_500, 10.0, 0.35),
    RealClub("Fijian Drua", "Lautoka", "Churchill Park", 15_400, 10.0, 0.2),
    RealClub("Moana Pasifika", "Auckland", "North Harbour Stadium", 25_000, 9.5, 0.2),
]

LEAGUES = [
    League(
        code="top14",
        name="Top 14",
        short_name="Top 14",
        country="France",
        playoffs=PlayoffFormat.TOP6,
        neutral_final=True,
        start=(9, 1),
        # Tournées d'automne, Noël, Tournoi des Six Nations.
        breaks=(((11, 7), 3), ((12, 20), 2), ((2, 20), 3)),
        clubs=TOP14,
    ),
    League(
        code="prod2",
        name="Pro D2",
        short_name="Pro D2",
        country="France",
        playoffs=PlayoffFormat.TOP6,
        neutral_final=True,
        start=(8, 22),
        breaks=(((11, 7), 2), ((12, 20), 2), ((2, 20), 2)),
        prize_factor=0.3,
        clubs=PROD2,
    ),
    League(
        code="premiership",
        name="Premiership",
        short_name="Premiership",
        country="Angleterre",
        playoffs=PlayoffFormat.TOP4,
        neutral_final=True,  # à Twickenham
        start=(9, 26),
        # Tournées d'automne, Coupe d'Europe (décembre, janvier, avril), Six Nations.
        breaks=(((11, 1), 4), ((12, 6), 2), ((1, 10), 2), ((2, 1), 5), ((4, 4), 2)),
        prize_factor=0.8,
        clubs=PREMIERSHIP,
    ),
    League(
        code="urc",
        name="United Rugby Championship",
        short_name="URC",
        country="Irlande, Écosse, Italie, Afrique du Sud",
        playoffs=PlayoffFormat.TOP8,
        neutral_final=False,
        start=(9, 26),
        breaks=(((11, 1), 4), ((12, 6), 2), ((1, 10), 2), ((2, 1), 3)),
        prize_factor=0.7,
        clubs=URC,
    ),
    League(
        code="super_rugby",
        name="Super Rugby Pacific",
        short_name="Super Rugby",
        country="Nouvelle-Zélande, Australie, Pacifique",
        playoffs=PlayoffFormat.SUPER6,
        neutral_final=False,
        start=(2, 1),
        prize_factor=0.6,
        clubs=SUPER_RUGBY,
    ),
]
LEAGUES_BY_CODE = {league.code: league for league in LEAGUES}

# Montée et descente : le dernier du Top 14 descend, le champion de Pro D2 monte.
PROMOTION = ("prod2", "top14")


def league(code: str) -> League:
    return LEAGUES_BY_CODE[code]


def league_config(code: str) -> League:
    """Formule et calendrier d'un championnat ; ceux du Top 14 pour un monde inventé."""
    return LEAGUES_BY_CODE.get(code, LEAGUES_BY_CODE[DEFAULT_LEAGUE])


def sort_codes(codes) -> list[str]:
    """Codes de championnats dans l'ordre de `LEAGUES` (les inconnus à la fin)."""
    order = [lg.code for lg in LEAGUES]
    return sorted(codes, key=lambda c: (order.index(c) if c in order else len(order), c))
