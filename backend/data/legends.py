"""Les équipes de légende : les plus grands joueurs de l'histoire d'une nation, réunis.

Une équipe de légende se joue en match libre (api/friendly.py), contre un club, une
sélection ou une autre légende, et en mode compétition à la place de son pays en
Coupe du monde (api/competition.py) : même poule, même tableau, mais son effectif est
fait de ses légendes.

Chaque légende a une note visée (sur 20, la note générale à son poste) et ses points
forts ; ses attributs s'en déduisent (`players`), toujours les mêmes. Les meilleurs
joueurs actuels du jeu tournent autour de 18 à 19 : une légende est un cran au-dessus.
On ajoute une équipe, ou un joueur, en complétant `LEGENDS` ; une liste doit garder de
quoi remplir une feuille de match à chaque poste (`SQUAD_MINIMUM`), plus des doublures.
"""

import random
from dataclasses import dataclass

from data.nations import NATION_ID_BASE, NATIONS_BY_CODE
from models import (
    ATTRIBUTE_MAX,
    ATTRIBUTE_MIN,
    ATTRIBUTE_NAMES,
    POSITION_PROFILES,
    Player,
    Position,
    Squad,
    overall_of,
)

# Identifiants d'équipe des légendes dans les matchs : après ceux des sélections.
LEGEND_ID_BASE = NATION_ID_BASE + 100
# Identifiants de leurs joueurs : loin de ceux d'un monde, un bloc par équipe.
LEGEND_PLAYER_ID_BASE = 10_000_000
PLAYER_BLOCK = 1000
SUFFIX = " de légende"

# Un point fort ajoute ceci à l'attribut (avant d'ajuster la note visée).
STRENGTH_BONUS = 3
# Écart-type du hasard propre à chaque légende autour du profil de son poste.
SPREAD = 1.0
PEAK_AGE = 28

P, H, L, B = Position.PROP, Position.HOOKER, Position.LOCK, Position.BACK_ROW
SH, FH, C = Position.SCRUM_HALF, Position.FLY_HALF, Position.CENTRE
W, FB = Position.WING, Position.FULLBACK


@dataclass(frozen=True)
class Legend:
    first_name: str
    last_name: str
    position: Position
    rating: float  # note générale visée, sur 20
    strengths: tuple[str, ...] = ()  # attributs (models.ATTRIBUTE_NAMES)


@dataclass(frozen=True)
class LegendTeam:
    nation: str  # code du pays (data/nations.py), aussi celui de l'équipe
    id: int
    legends: tuple[Legend, ...]

    @property
    def name(self) -> str:
        return NATIONS_BY_CODE[self.nation].name + SUFFIX

    @property
    def nation_id(self) -> int:
        return NATIONS_BY_CODE[self.nation].id

    def player_id(self, index: int) -> int:
        return LEGEND_PLAYER_ID_BASE + (self.id - LEGEND_ID_BASE) * PLAYER_BLOCK + index

    @property
    def player_ids(self) -> frozenset[int]:
        return frozenset(self.player_id(i) for i in range(len(self.legends)))


def _team(index: int, nation: str, *legends: Legend) -> LegendTeam:
    return LegendTeam(nation, LEGEND_ID_BASE + index, legends)


def _l(name: str, position: Position, rating: float, *strengths: str) -> Legend:
    first, last = name.split(" ", 1)
    return Legend(first, last, position, rating, strengths)


# fmt: off
LEGENDS = [
    _team(1, "FRA",
        _l("Robert Paparemborde", P, 18.8, "scrum"),
        _l("Christian Califano", P, 18.5),
        _l("Pieter de Villiers", P, 18.3, "scrum"),
        _l("Sylvain Marconnet", P, 18.3),
        _l("Nicolas Mas", P, 18.0, "scrum"),
        _l("Raphaël Ibañez", H, 18.6, "lineout"),
        _l("William Servat", H, 18.4, "scrum"),
        _l("Philippe Dintrans", H, 18.0),
        _l("Fabien Pelous", L, 19.0, "lineout", "stamina"),
        _l("Jean Condom", L, 18.3, "power"),
        _l("Olivier Merle", L, 18.1, "power"),
        _l("Lionel Nallet", L, 18.0),
        _l("Thierry Dusautoir", B, 19.4, "tackling", "stamina"),
        _l("Jean-Pierre Rives", B, 19.0, "tackling", "pace"),
        _l("Imanol Harinordoquy", B, 18.9, "lineout", "handling"),
        _l("Olivier Magne", B, 18.8, "pace"),
        _l("Serge Betsen", B, 18.7, "tackling"),
        _l("Abdelatif Benazzi", B, 18.6, "power"),
        _l("Walter Spanghero", B, 18.6, "power"),
        _l("Antoine Dupont", SH, 19.9, "pace", "handling", "passing"),
        _l("Fabien Galthié", SH, 18.5, "kicking"),
        _l("Pierre Berbizier", SH, 18.2),
        _l("Frédéric Michalak", FH, 18.7, "handling", "kicking"),
        _l("Christophe Lamaison", FH, 18.3, "kicking"),
        _l("Didier Camberabero", FH, 18.2, "kicking"),
        _l("Philippe Sella", C, 19.3, "tackling", "handling"),
        _l("Yannick Jauzion", C, 18.8, "power"),
        _l("Jo Maso", C, 18.5, "passing"),
        _l("Thomas Castaignède", C, 18.6, "pace", "kicking"),
        _l("Christophe Dominici", W, 18.8, "pace"),
        _l("Émile Ntamack", W, 18.8, "pace", "handling"),
        _l("Philippe Saint-André", W, 18.6),
        _l("Patrice Lagisquet", W, 18.6, "pace"),
        _l("Serge Blanco", FB, 19.6, "pace", "handling"),
        _l("Jean-Luc Sadourny", FB, 18.3, "kicking"),
    ),
    _team(2, "NZL",
        _l("Tony Woodcock", P, 18.8, "scrum"),
        _l("Olo Brown", P, 18.5, "scrum"),
        _l("Owen Franks", P, 18.5, "scrum"),
        _l("Ken Gray", P, 18.4),
        _l("Craig Dowd", P, 18.2),
        _l("Sean Fitzpatrick", H, 19.2, "lineout", "stamina"),
        _l("Dane Coles", H, 18.7, "pace"),
        _l("Keven Mealamu", H, 18.5, "power"),
        _l("Colin Meads", L, 19.2, "power", "tackling"),
        _l("Brodie Retallick", L, 19.0, "lineout", "handling"),
        _l("Sam Whitelock", L, 19.0, "lineout", "stamina"),
        _l("Ian Jones", L, 18.4, "lineout"),
        _l("Gary Whetton", L, 18.3),
        _l("Richie McCaw", B, 19.8, "tackling", "stamina"),
        _l("Kieran Read", B, 19.1, "handling", "lineout"),
        _l("Michael Jones", B, 19.0, "pace", "tackling"),
        _l("Zinzan Brooke", B, 18.9, "handling", "kicking"),
        _l("Buck Shelford", B, 18.8, "power"),
        _l("Jerry Collins", B, 18.7, "power", "tackling"),
        _l("Jerome Kaino", B, 18.5, "power"),
        _l("Aaron Smith", SH, 19.1, "passing", "pace"),
        _l("Sid Going", SH, 18.5, "power"),
        _l("Justin Marshall", SH, 18.5),
        _l("Dan Carter", FH, 19.8, "kicking", "passing"),
        _l("Beauden Barrett", FH, 18.9, "pace"),
        _l("Grant Fox", FH, 18.7, "kicking"),
        _l("Ma'a Nonu", C, 18.9, "power"),
        _l("Tana Umaga", C, 18.8, "tackling"),
        _l("Conrad Smith", C, 18.8, "passing"),
        _l("Frank Bunce", C, 18.5, "tackling"),
        _l("Jonah Lomu", W, 19.4, "power", "pace"),
        _l("John Kirwan", W, 18.7, "pace"),
        _l("Julian Savea", W, 18.7, "power"),
        _l("Joe Rokocoko", W, 18.6, "pace"),
        _l("Christian Cullen", FB, 19.0, "pace", "handling"),
        _l("Ben Smith", FB, 18.8, "handling"),
    ),
    _team(3, "RSA",
        _l("Os du Randt", P, 18.9, "scrum", "power"),
        _l("Tendai Mtawarira", P, 18.7, "power"),
        _l("Frans Malherbe", P, 18.4, "scrum"),
        _l("Ox Nché", P, 18.4, "scrum"),
        _l("Jannie du Plessis", P, 18.3),
        _l("Malcolm Marx", H, 18.9, "power"),
        _l("Bismarck du Plessis", H, 18.8, "power"),
        _l("John Smit", H, 18.7, "scrum"),
        _l("Victor Matfield", L, 19.2, "lineout"),
        _l("Eben Etzebeth", L, 19.0, "power", "tackling"),
        _l("Frik du Preez", L, 18.8, "pace"),
        _l("Bakkies Botha", L, 18.8, "power"),
        _l("Pieter-Steph du Toit", B, 19.1, "tackling", "stamina"),
        _l("Siya Kolisi", B, 18.9, "tackling"),
        _l("Duane Vermeulen", B, 18.9, "power"),
        _l("Schalk Burger", B, 18.8, "tackling"),
        _l("Francois Pienaar", B, 18.7),
        _l("Juan Smith", B, 18.6, "power"),
        _l("Joost van der Westhuizen", SH, 19.2, "pace", "tackling"),
        _l("Fourie du Preez", SH, 19.0, "kicking", "passing"),
        _l("Faf de Klerk", SH, 18.4, "kicking"),
        _l("Handré Pollard", FH, 18.8, "kicking"),
        _l("Naas Botha", FH, 18.6, "kicking"),
        _l("Joel Stransky", FH, 18.4, "kicking"),
        _l("Danie Gerber", C, 18.9, "pace"),
        _l("Jean de Villiers", C, 18.7),
        _l("Jaque Fourie", C, 18.7, "pace"),
        _l("Damian de Allende", C, 18.6, "power"),
        _l("Bryan Habana", W, 19.2, "pace"),
        _l("Cheslin Kolbe", W, 19.0, "pace", "handling"),
        _l("Chester Williams", W, 18.5),
        _l("JP Pietersen", W, 18.4, "power"),
        _l("Percy Montgomery", FB, 18.7, "kicking"),
        _l("André Joubert", FB, 18.6, "pace"),
    ),
    _team(4, "ENG",
        _l("Jason Leonard", P, 18.7, "scrum", "stamina"),
        _l("Phil Vickery", P, 18.6, "scrum"),
        _l("Dan Cole", P, 18.3, "scrum"),
        _l("Trevor Woodman", P, 18.2),
        _l("Joe Marler", P, 18.2),
        _l("Steve Thompson", H, 18.5, "power"),
        _l("Jamie George", H, 18.5, "lineout"),
        _l("Brian Moore", H, 18.4),
        _l("Martin Johnson", L, 19.3, "lineout", "power"),
        _l("Maro Itoje", L, 19.1, "lineout", "tackling"),
        _l("Ben Kay", L, 18.4, "lineout"),
        _l("Wade Dooley", L, 18.3, "power"),
        _l("Lawrence Dallaglio", B, 19.0, "power", "handling"),
        _l("Richard Hill", B, 18.9, "tackling"),
        _l("Neil Back", B, 18.8, "pace"),
        _l("Dean Richards", B, 18.6, "power"),
        _l("Tom Curry", B, 18.6, "tackling"),
        _l("Peter Winterbottom", B, 18.5, "tackling"),
        _l("Matt Dawson", SH, 18.6, "pace"),
        _l("Ben Youngs", SH, 18.3),
        _l("Kyran Bracken", SH, 18.2),
        _l("Jonny Wilkinson", FH, 19.6, "kicking", "tackling"),
        _l("Owen Farrell", FH, 18.7, "kicking"),
        _l("Rob Andrew", FH, 18.4, "kicking"),
        _l("Jeremy Guscott", C, 18.9, "pace"),
        _l("Will Greenwood", C, 18.6, "passing"),
        _l("Manu Tuilagi", C, 18.6, "power"),
        _l("Mike Tindall", C, 18.3, "tackling"),
        _l("Rory Underwood", W, 18.8, "pace"),
        _l("Ben Cohen", W, 18.5, "power"),
        _l("Jonny May", W, 18.5, "pace"),
        _l("Jason Robinson", FB, 19.0, "pace", "handling"),
        _l("Josh Lewsey", FB, 18.5),
    ),
    _team(5, "AUS",
        _l("Ewen McKenzie", P, 18.4, "scrum"),
        _l("Tony Daly", P, 18.3),
        _l("Bill Young", P, 18.2),
        _l("Benn Robinson", P, 18.2),
        _l("Allan Alaalatoa", P, 18.0),
        _l("Phil Kearns", H, 18.6, "lineout"),
        _l("Stephen Moore", H, 18.5),
        _l("Tatafu Polota-Nau", H, 18.3, "power"),
        _l("John Eales", L, 19.3, "lineout", "kicking"),
        _l("Nathan Sharpe", L, 18.4, "lineout"),
        _l("Justin Harrison", L, 18.2, "lineout"),
        _l("David Giffin", L, 18.2),
        _l("David Pocock", B, 19.2, "tackling", "power"),
        _l("George Smith", B, 19.0, "tackling", "handling"),
        _l("Michael Hooper", B, 18.8, "stamina", "pace"),
        _l("Simon Poidevin", B, 18.6, "stamina"),
        _l("Toutai Kefu", B, 18.6, "power"),
        _l("Willie Ofahengaue", B, 18.5, "power"),
        _l("George Gregan", SH, 19.0, "tackling", "passing"),
        _l("Nick Farr-Jones", SH, 18.9, "passing"),
        _l("Will Genia", SH, 18.8, "pace"),
        _l("Stephen Larkham", FH, 19.0, "passing", "handling"),
        _l("Mark Ella", FH, 19.0, "handling"),
        _l("Michael Lynagh", FH, 18.9, "kicking"),
        _l("Tim Horan", C, 19.1, "tackling", "handling"),
        _l("Matt Giteau", C, 18.7, "kicking"),
        _l("Jason Little", C, 18.6),
        _l("Stirling Mortlock", C, 18.6, "power", "kicking"),
        _l("David Campese", W, 19.3, "pace", "handling"),
        _l("Joe Roff", W, 18.5),
        _l("Lote Tuqiri", W, 18.5, "power"),
        _l("Drew Mitchell", W, 18.3, "pace"),
        _l("Chris Latham", FB, 18.7, "pace"),
        _l("Matt Burke", FB, 18.6, "kicking"),
    ),
    _team(6, "IRE",
        _l("Tadhg Furlong", P, 18.9, "scrum", "handling"),
        _l("Cian Healy", P, 18.5, "power"),
        _l("Andrew Porter", P, 18.4),
        _l("John Hayes", P, 18.3, "scrum"),
        _l("Mike Ross", P, 18.0, "scrum"),
        _l("Keith Wood", H, 19.0, "pace", "handling"),
        _l("Dan Sheehan", H, 18.7, "pace"),
        _l("Rory Best", H, 18.5, "lineout"),
        _l("Paul O'Connell", L, 19.2, "lineout", "stamina"),
        _l("Willie John McBride", L, 19.0, "power"),
        _l("James Ryan", L, 18.5, "tackling"),
        _l("Donncha O'Callaghan", L, 18.3),
        _l("Seán O'Brien", B, 18.8, "power"),
        _l("Josh van der Flier", B, 18.8, "tackling", "stamina"),
        _l("Caelan Doris", B, 18.8, "handling"),
        _l("Jamie Heaslip", B, 18.6),
        _l("Peter O'Mahony", B, 18.5, "lineout"),
        _l("Stephen Ferris", B, 18.5, "power"),
        _l("Conor Murray", SH, 18.8, "kicking"),
        _l("Jamison Gibson-Park", SH, 18.6, "pace"),
        _l("Peter Stringer", SH, 18.2, "passing"),
        _l("Johnny Sexton", FH, 19.3, "kicking", "passing"),
        _l("Ronan O'Gara", FH, 18.9, "kicking"),
        _l("Ollie Campbell", FH, 18.3, "kicking"),
        _l("Brian O'Driscoll", C, 19.6, "handling", "tackling"),
        _l("Mike Gibson", C, 18.9, "passing"),
        _l("Gordon D'Arcy", C, 18.5, "power"),
        _l("Robbie Henshaw", C, 18.5, "tackling"),
        _l("Tommy Bowe", W, 18.6),
        _l("James Lowe", W, 18.5, "kicking"),
        _l("Keith Earls", W, 18.4, "pace"),
        _l("Denis Hickie", W, 18.4, "pace"),
        _l("Rob Kearney", FB, 18.5, "kicking"),
        _l("Hugo Keenan", FB, 18.5),
    ),
    _team(7, "WAL",
        _l("Gethin Jenkins", P, 18.8, "tackling"),
        _l("Adam Jones", P, 18.6, "scrum"),
        _l("Graham Price", P, 18.5, "scrum"),
        _l("Charlie Faulkner", P, 18.0),
        _l("Samson Lee", P, 17.9),
        _l("Ken Owens", H, 18.4),
        _l("Bobby Windsor", H, 18.3, "scrum"),
        _l("Matthew Rees", H, 18.0),
        _l("Alun Wyn Jones", L, 19.1, "stamina", "lineout"),
        _l("Robert Norster", L, 18.4, "lineout"),
        _l("Delme Thomas", L, 18.3),
        _l("Luke Charteris", L, 18.1, "tackling"),
        _l("Mervyn Davies", B, 19.0, "lineout", "handling"),
        _l("Sam Warburton", B, 18.9, "tackling"),
        _l("Taulupe Faletau", B, 18.8, "power"),
        _l("Justin Tipuric", B, 18.7, "pace"),
        _l("Martyn Williams", B, 18.6),
        _l("Ryan Jones", B, 18.4),
        _l("Gareth Edwards", SH, 19.7, "pace", "power", "passing"),
        _l("Mike Phillips", SH, 18.6, "power"),
        _l("Terry Holmes", SH, 18.4, "power"),
        _l("Barry John", FH, 19.2, "kicking", "handling"),
        _l("Phil Bennett", FH, 19.1, "pace"),
        _l("Neil Jenkins", FH, 18.6, "kicking"),
        _l("Scott Gibbs", C, 18.8, "power", "tackling"),
        _l("Jonathan Davies", C, 18.6),
        _l("Jamie Roberts", C, 18.5, "power"),
        _l("Ray Gravell", C, 18.3),
        _l("Gerald Davies", W, 19.2, "pace"),
        _l("Shane Williams", W, 19.1, "pace", "handling"),
        _l("Ieuan Evans", W, 18.8, "pace"),
        _l("George North", W, 18.7, "power"),
        _l("J.P.R. Williams", FB, 19.3, "tackling"),
        _l("Leigh Halfpenny", FB, 18.7, "kicking"),
    ),
]
# fmt: on
LEGENDS_BY_ID = {team.id: team for team in LEGENDS}
LEGENDS_BY_NATION = {team.nation: team for team in LEGENDS}


def _clamp(value: float) -> int:
    return max(ATTRIBUTE_MIN, min(ATTRIBUTE_MAX, round(value)))


def attributes(legend: Legend) -> dict[str, int]:
    """Les 9 attributs d'une légende : le profil de son poste, ses points forts et un
    hasard qui lui est propre, au niveau qui donne la note visée (au plus près)."""
    profile = POSITION_PROFILES[legend.position]
    rng = random.Random(f"legend:{legend.first_name} {legend.last_name}")
    shape = {
        name: profile[name]
        + rng.gauss(0, SPREAD)
        + (STRENGTH_BONUS if name in legend.strengths else 0)
        for name in ATTRIBUTE_NAMES
    }

    def at(base: float) -> dict[str, int]:
        return {name: _clamp(base + offset) for name, offset in shape.items()}

    bases = (step / 20 for step in range(0, 25 * 20))
    best = min(bases, key=lambda base: abs(overall_of(legend.position, at(base)) - legend.rating))
    return at(best)


def players(team: LegendTeam) -> list[Player]:
    """Les joueurs de l'équipe, toujours les mêmes : sans club, payés ailleurs, hors du
    marché (comme les renforts d'une sélection)."""
    return [
        Player(
            id=team.player_id(index),
            first_name=legend.first_name,
            last_name=legend.last_name,
            age=PEAK_AGE,
            position=legend.position,
            squad=Squad.AWAY,
            nationality=team.nation,
            **attributes(legend),
        )
        for index, legend in enumerate(team.legends)
    ]
