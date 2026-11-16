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
    RealClub("Capitouls de Toulouse", "Toulouse", "Stade des Capitouls", 19_000, 14.0, 1.0),
    RealClub("Vendangeurs de Bordeaux", "Bordeaux", "Stade des Quinconces", 33_000, 13.5, 0.85),
    RealClub("Corsaires de Toulon", "Toulon", "Stade de la Rade", 16_000, 12.5, 0.8),
    RealClub("Goélands de La Rochelle", "La Rochelle", "Stade des Deux-Tours", 16_000, 12.5, 0.75),
    RealClub("Volcans de Clermont", "Clermont-Ferrand", "Stade des Puys", 19_000, 12.0, 0.7),
    RealClub("Flèches de Nanterre", "Nanterre", "Arena de la Seine", 30_000, 11.5, 0.85),
    RealClub("Rameurs de Bayonne", "Bayonne", "Stade de la Nive", 17_000, 11.5, 0.55),
    RealClub("Tisserands de Castres", "Castres", "Stade de l'Agout", 12_500, 11.5, 0.5),
    RealClub("Isards de Pau", "Pau", "Stade du Gave", 18_000, 11.0, 0.55),
    RealClub("Roses de Paris", "Paris", "Stade de la Porte d'Auteuil", 20_000, 10.5, 0.75),
    RealClub("Canuts de Lyon", "Lyon", "Stade des Deux-Fleuves", 25_000, 10.5, 0.65),
    RealClub("Flamants de Montpellier", "Montpellier", "Stade de la Garrigue", 15_500, 10.5, 0.65),
    RealClub("Grenats de Perpignan", "Perpignan", "Stade du Canigou", 14_500, 10.0, 0.45),
    RealClub("Faucons de Montauban", "Montauban", "Stade du Tarn", 11_000, 8.5, 0.2),
]

PROD2 = [
    RealClub("Hermines de Vannes", "Vannes", "Stade du Golfe", 11_300, 9.5, 0.35),
    RealClub("Dauphins de Grenoble", "Grenoble", "Stade de la Bastille", 20_000, 9.5, 0.3),
    RealClub("Lynx d'Oyonnax", "Oyonnax", "Stade du Haut-Bugey", 11_500, 9.0, 0.25),
    RealClub("Cigales d'Aix", "Aix-en-Provence", "Stade de la Sainte-Victoire", 8_800, 9.0, 0.3),
    RealClub("Gaillards de Brive", "Brive-la-Gaillarde", "Stade de la Corrèze", 14_000, 9.0, 0.3),
    RealClub("Aviateurs de Colomiers", "Colomiers", "Stade des Ailes", 11_400, 8.5, 0.15),
    RealClub("Pruniers d'Agen", "Agen", "Stade des Vergers", 14_400, 8.5, 0.2),
    RealClub("Taureaux de Béziers", "Béziers", "Stade des Arènes", 18_500, 8.5, 0.25),
    RealClub("Vagues de Biarritz", "Biarritz", "Parc de la Côte basque", 15_000, 8.5, 0.2),
    RealClub("Lavandes de Valence", "Valence", "Stade du Vercors", 15_000, 8.5, 0.15),
    RealClub("Cantalous d'Aurillac", "Aurillac", "Stade de la Jordanne", 9_000, 8.0, 0.1),
    RealClub("Échassiers du Marsan", "Mont-de-Marsan", "Stade des Pins", 16_800, 8.0, 0.15),
    RealClub("Ducs de Nevers", "Nevers", "Stade de la Loire", 7_500, 8.0, 0.15),
    RealClub("Écarteurs de Dax", "Dax", "Stade de l'Adour", 7_300, 7.5, 0.1),
    RealClub("Remparts d'Angoulême", "Angoulême", "Stade de la Charente", 8_000, 7.5, 0.1),
    RealClub("Chevaliers de Carcassonne", "Carcassonne", "Stade de la Cité", 6_500, 7.5, 0.05),
]

PREMIERSHIP = [
    RealClub("Bath Romans", "Bath", "Riverside Ground", 14_500, 13.5, 0.8),
    RealClub("Northampton Pilgrims", "Northampton", "Abbey Gardens", 15_200, 13.0, 0.7),
    RealClub("Leicester Jaguars", "Leicester", "Granby Road", 25_800, 12.5, 0.75),
    RealClub("Bristol Buccaneers", "Bristol", "Harbour Gate", 27_000, 12.5, 0.7),
    RealClub("London Scimitars", "Londres", "Northfields Stadium", 10_500, 12.5, 0.75),
    RealClub("Salford Orcas", "Salford", "Irwell Stadium", 12_000, 12.0, 0.6),
    RealClub("London Jesters", "Londres", "Thames Meadow", 14_800, 11.5, 0.7),
    RealClub("Gloucester Dockers", "Gloucester", "Severnside", 16_100, 11.5, 0.6),
    RealClub("Exeter Stags", "Exeter", "Moorland Park", 15_600, 11.5, 0.6),
    RealClub("Newcastle Kestrels", "Newcastle", "Tyne Park", 10_200, 10.0, 0.45),
]

# Sans les provinces galloises : Irlande, Écosse, Italie et Afrique du Sud.
URC = [
    RealClub("Dublin Harps", "Dublin", "Liffey Arena", 18_500, 14.5, 0.9),
    RealClub("Limerick Raiders", "Limerick", "Shannon Park", 25_600, 12.5, 0.65),
    RealClub("Belfast Shipwrights", "Belfast", "Lagan Ground", 18_200, 11.5, 0.6),
    RealClub("Galway Gales", "Galway", "Corrib Park", 12_100, 10.5, 0.45),
    RealClub("Glasgow Clansmen", "Glasgow", "Clydeside Stadium", 7_400, 12.5, 0.55),
    RealClub("Edinburgh Thistles", "Édimbourg", "Castle Rock Stadium", 7_800, 11.0, 0.5),
    RealClub("Treviso Dogi", "Trévise", "Stadio del Sile", 5_000, 10.5, 0.45),
    RealClub("Parma Ducato", "Parme", "Stadio della Cittadella", 5_000, 9.0, 0.25),
    RealClub("Pretoria Buffaloes", "Pretoria", "Jacaranda Park", 51_800, 13.0, 0.6),
    RealClub("Cape Town Tempest", "Le Cap", "Table Bay Stadium", 55_000, 12.5, 0.55),
    RealClub("Durban Barracudas", "Durban", "Umgeni Park", 52_000, 12.0, 0.6),
    RealClub("Johannesburg Pride", "Johannesburg", "Highveld Park", 62_500, 11.0, 0.45),
]

SUPER_RUGBY = [
    RealClub(
        "Christchurch Knights", "Christchurch", "Canterbury Plains Stadium", 17_100, 13.5, 0.6
    ),
    RealClub("Hamilton Captains", "Hamilton", "Waikato River Stadium", 25_800, 13.5, 0.55),
    RealClub("Wellington Cyclones", "Wellington", "Harbour Stadium", 34_500, 13.0, 0.55),
    RealClub("Auckland Mariners", "Auckland", "Volcano Park", 50_000, 13.0, 0.6),
    RealClub("Canberra Mustangs", "Canberra", "Capital Stadium", 25_000, 12.5, 0.5),
    RealClub("Dunedin Mountaineers", "Dunedin", "Otago Harbour Stadium", 30_700, 11.5, 0.45),
    RealClub("Brisbane Rubies", "Brisbane", "River City Stadium", 52_500, 11.5, 0.5),
    RealClub("Sydney Wattles", "Sydney", "Harbour City Stadium", 42_500, 11.0, 0.5),
    RealClub("Perth Surge", "Perth", "Swan River Park", 20_500, 10.0, 0.35),
    RealClub("Lautoka Voyagers", "Lautoka", "Sugar City Park", 15_400, 10.0, 0.2),
    RealClub("Pacific Tides", "Auckland", "North Shore Stadium", 25_000, 9.5, 0.2),
]

# Tradition du public de chaque stade, de 0 à 1 (0,5 par défaut, et pour les clubs
# inventés) : les chaudrons poussent leur équipe plus fort (engine/crowd.py).
STADIUM_TRADITION = {
    # Top 14
    "Grenats de Perpignan": 1.0,
    "Volcans de Clermont": 0.95,
    "Corsaires de Toulon": 0.95,
    "Rameurs de Bayonne": 0.9,
    "Goélands de La Rochelle": 0.9,
    "Tisserands de Castres": 0.85,
    "Capitouls de Toulouse": 0.8,
    "Vendangeurs de Bordeaux": 0.75,
    "Isards de Pau": 0.75,
    "Faucons de Montauban": 0.7,
    "Canuts de Lyon": 0.45,
    "Flamants de Montpellier": 0.4,
    "Roses de Paris": 0.35,
    "Flèches de Nanterre": 0.3,
    # Pro D2
    "Gaillards de Brive": 0.85,
    "Taureaux de Béziers": 0.8,
    "Échassiers du Marsan": 0.75,
    "Pruniers d'Agen": 0.75,
    "Vagues de Biarritz": 0.75,
    "Cantalous d'Aurillac": 0.7,
    "Écarteurs de Dax": 0.7,
    "Lynx d'Oyonnax": 0.7,
    "Hermines de Vannes": 0.7,
    "Dauphins de Grenoble": 0.6,
    "Cigales d'Aix": 0.4,
    # Premiership
    "Gloucester Dockers": 0.9,
    "Leicester Jaguars": 0.85,
    "Northampton Pilgrims": 0.75,
    "Exeter Stags": 0.75,
    "Bath Romans": 0.7,
    "Bristol Buccaneers": 0.6,
    "London Jesters": 0.55,
    "London Scimitars": 0.4,
    # URC
    "Limerick Raiders": 0.95,
    "Pretoria Buffaloes": 0.9,
    "Belfast Shipwrights": 0.8,
    "Galway Gales": 0.75,
    "Glasgow Clansmen": 0.75,
    "Cape Town Tempest": 0.75,
    "Durban Barracudas": 0.75,
    "Johannesburg Pride": 0.75,
    "Dublin Harps": 0.7,
    "Treviso Dogi": 0.6,
    "Parma Ducato": 0.4,
    # Super Rugby
    "Lautoka Voyagers": 1.0,
    "Christchurch Knights": 0.8,
    "Hamilton Captains": 0.75,
    "Wellington Cyclones": 0.7,
    "Dunedin Mountaineers": 0.7,
    "Auckland Mariners": 0.6,
    "Pacific Tides": 0.6,
    "Canberra Mustangs": 0.55,
    "Brisbane Rubies": 0.55,
}

LEAGUES = [
    League(
        code="top14",
        name="Top 14",
        short_name="Top 14",
        country="France",
        playoffs=PlayoffFormat.TOP6,
        neutral_final=True,
        start=(9, 1),
        # Tournées d'automne, Coupe d'Europe (poules en décembre et janvier, quarts,
        # demies, finale), Noël, Tournoi des Six Nations.
        breaks=(
            ((11, 7), 3),
            ((12, 6), 2),
            ((12, 20), 2),
            ((1, 10), 2),
            ((2, 20), 3),
            ((4, 4), 1),
            ((5, 2), 1),
            ((5, 23), 1),
        ),
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
        # Tournées d'automne, Coupe d'Europe (décembre, janvier, quarts, demies et
        # finale), Six Nations.
        breaks=(
            ((11, 1), 4),
            ((12, 6), 2),
            ((1, 10), 2),
            ((2, 1), 5),
            ((4, 4), 2),
            ((5, 2), 1),
            ((5, 23), 1),
        ),
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
        # Tournées d'automne, Coupe d'Europe (décembre, janvier, quarts, demies et
        # finale), Six Nations.
        breaks=(
            ((11, 1), 4),
            ((12, 6), 2),
            ((1, 10), 2),
            ((2, 1), 3),
            ((4, 4), 1),
            ((5, 2), 1),
            ((5, 23), 1),
        ),
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
