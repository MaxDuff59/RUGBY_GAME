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
    **_rivals("Derby basque", "Aviron Bayonnais", "Biarritz Olympique"),
    **_rivals("Derby basco-béarnais", "Aviron Bayonnais", "Section Paloise"),
    **_rivals("Derby occitan", "Stade Toulousain", "Castres Olympique"),
    **_rivals("Derby occitan", "Stade Toulousain", "US Montauban"),
    **_rivals("Derby toulousain", "Stade Toulousain", "Colomiers Rugby"),
    **_rivals("Derby francilien", "Racing 92", "Stade Français Paris"),
    **_rivals("Derby de la Méditerranée", "RC Toulon", "Montpellier Hérault Rugby"),
    **_rivals("Derby provençal", "RC Toulon", "Provence Rugby"),
    **_rivals("Derby héraultais", "Montpellier Hérault Rugby", "AS Béziers Hérault"),
    **_rivals(
        "Derby du Languedoc-Roussillon", "USA Perpignan", "AS Béziers Hérault", "US Carcassonne"
    ),
    **_rivals("Derby de l'Atlantique", "Stade Rochelais", "Union Bordeaux-Bègles"),
    **_rivals("Derby charentais", "Stade Rochelais", "Soyaux Angoulême XV"),
    **_rivals("Derby de la Garonne", "SU Agen", "Union Bordeaux-Bègles"),
    **_rivals("Derby du Sud-Ouest", "SU Agen", "US Montauban"),
    **_rivals("Derby landais", "US Dax", "Stade Montois"),
    **_rivals("Derby auvergnat", "ASM Clermont Auvergne", "Stade Aurillacois"),
    **_rivals("Derby du Massif central", "ASM Clermont Auvergne", "CA Brive"),
    **_rivals("Derby du Massif central", "CA Brive", "Stade Aurillacois"),
    **_rivals("Derby rhônalpin", "LOU Rugby", "FC Grenoble", "Oyonnax Rugby"),
    **_rivals("Derby dauphinois", "FC Grenoble", "Valence Romans Drôme Rugby"),
    # Premiership
    **_rivals("Derby des East Midlands", "Leicester Tigers", "Northampton Saints"),
    **_rivals("Derby du West Country", "Bath Rugby", "Bristol Bears", "Gloucester Rugby"),
    **_rivals("Derby londonien", "Saracens", "Harlequins"),
    **_rivals("Derby du Nord", "Sale Sharks", "Newcastle Red Bulls"),
    # United Rugby Championship
    **_rivals(
        "Derby irlandais", "Leinster Rugby", "Munster Rugby", "Ulster Rugby", "Connacht Rugby"
    ),
    **_rivals("Coupe 1872", "Glasgow Warriors", "Edinburgh Rugby"),
    **_rivals("Derby italien", "Benetton Rugby", "Zebre Parma"),
    **_rivals("Derby sud-africain", "Bulls", "Stormers", "Sharks", "Lions"),
    # Super Rugby
    **_rivals("Derby néo-zélandais", "Crusaders", "Chiefs", "Hurricanes", "Blues", "Highlanders"),
    **_rivals("Derby australien", "Brumbies", "Queensland Reds", "NSW Waratahs", "Western Force"),
    **_rivals("Derby du Pacifique", "Fijian Drua", "Moana Pasifika"),
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
