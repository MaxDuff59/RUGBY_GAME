"""Les derbies : les vraies rivalités entre clubs voisins, et entre sélections.

Un derby est un match à enjeu, comme un match à élimination directe : en direct,
une fin de match serrée y donne toujours un choix crucial au manager
(engine/match_engine.py, `stakes`). Les clubs inventés n'ont pas de derby.
"""

from itertools import combinations


def _rivals(name: str, *teams: str) -> dict[frozenset[str], str]:
    """Le derby `name` entre chacune de ces équipes et chacune des autres."""
    return {frozenset(pair): name for pair in combinations(teams, 2)}


DERBIES: dict[frozenset[str], str] = {
    # Top 14 et Pro D2
    **_rivals("Derby basque", "Rameurs de Bayonne", "Vagues de Biarritz"),
    **_rivals("Derby basco-béarnais", "Rameurs de Bayonne", "Isards de Pau"),
    **_rivals("Derby occitan", "Capitouls de Toulouse", "Tisserands de Castres"),
    **_rivals("Derby occitan", "Capitouls de Toulouse", "Faucons de Montauban"),
    **_rivals("Derby toulousain", "Capitouls de Toulouse", "Aviateurs de Colomiers"),
    **_rivals("Derby francilien", "Flèches de Nanterre", "Roses de Paris"),
    **_rivals("Derby de la Méditerranée", "Corsaires de Toulon", "Flamants de Montpellier"),
    **_rivals("Derby provençal", "Corsaires de Toulon", "Cigales d'Aix"),
    **_rivals("Derby héraultais", "Flamants de Montpellier", "Taureaux de Béziers"),
    **_rivals(
        "Derby du Languedoc-Roussillon",
        "Grenats de Perpignan",
        "Taureaux de Béziers",
        "Chevaliers de Carcassonne",
    ),
    **_rivals("Derby de l'Atlantique", "Goélands de La Rochelle", "Vendangeurs de Bordeaux"),
    **_rivals("Derby charentais", "Goélands de La Rochelle", "Remparts d'Angoulême"),
    **_rivals("Derby de la Garonne", "Pruniers d'Agen", "Vendangeurs de Bordeaux"),
    **_rivals("Derby du Sud-Ouest", "Pruniers d'Agen", "Faucons de Montauban"),
    **_rivals("Derby landais", "Écarteurs de Dax", "Échassiers du Marsan"),
    **_rivals("Derby auvergnat", "Volcans de Clermont", "Cantalous d'Aurillac"),
    **_rivals("Derby du Massif central", "Volcans de Clermont", "Gaillards de Brive"),
    **_rivals("Derby du Massif central", "Gaillards de Brive", "Cantalous d'Aurillac"),
    **_rivals("Derby rhônalpin", "Canuts de Lyon", "Dauphins de Grenoble", "Lynx d'Oyonnax"),
    **_rivals("Derby dauphinois", "Dauphins de Grenoble", "Lavandes de Valence"),
    # Premiership
    **_rivals("Derby des East Midlands", "Leicester Jaguars", "Northampton Pilgrims"),
    **_rivals("Derby du West Country", "Bath Romans", "Bristol Buccaneers", "Gloucester Dockers"),
    **_rivals("Derby londonien", "London Scimitars", "London Jesters"),
    **_rivals("Derby du Nord", "Salford Orcas", "Newcastle Kestrels"),
    # United Rugby Championship
    **_rivals(
        "Derby irlandais", "Dublin Harps", "Limerick Raiders", "Belfast Shipwrights", "Galway Gales"
    ),
    **_rivals("Derby écossais", "Glasgow Clansmen", "Edinburgh Thistles"),
    **_rivals("Derby italien", "Treviso Dogi", "Parma Ducato"),
    **_rivals(
        "Derby sud-africain",
        "Pretoria Buffaloes",
        "Cape Town Tempest",
        "Durban Barracudas",
        "Johannesburg Pride",
    ),
    # Super Rugby
    **_rivals(
        "Derby néo-zélandais",
        "Christchurch Knights",
        "Hamilton Captains",
        "Wellington Cyclones",
        "Auckland Mariners",
        "Dunedin Mountaineers",
    ),
    **_rivals(
        "Derby australien", "Canberra Mustangs", "Brisbane Rubies", "Sydney Wattles", "Perth Surge"
    ),
    **_rivals("Derby du Pacifique", "Lautoka Voyagers", "Pacific Tides"),
    # Sélections
    **_rivals("Le Crunch", "France", "Angleterre"),
    **_rivals("Calcutta Cup", "Angleterre", "Écosse"),
    **_rivals("Derby britannique", "Angleterre", "Pays de Galles"),
    **_rivals("Centenary Quaich", "Irlande", "Écosse"),
    **_rivals("Trophée Garibaldi", "France", "Italie"),
    **_rivals("Bledisloe Cup", "Nouvelle-Zélande", "Australie"),
    **_rivals("Freedom Cup", "Nouvelle-Zélande", "Afrique du Sud"),
    **_rivals("Mandela Plate", "Australie", "Afrique du Sud"),
    **_rivals("Puma Trophy", "Argentine", "Australie"),
    **_rivals("Derby du Pacifique", "Fidji", "Samoa", "Tonga"),
}


def derby(home: str, away: str) -> str | None:
    """Le nom du derby entre ces deux équipes (None si ce n'en est pas un)."""
    return DERBIES.get(frozenset((home, away)))
