"""Les derbies (data/derbies.py) : de vraies équipes, dans les deux sens."""

from data.derbies import DERBIES, derby
from data.leagues import LEAGUES_BY_CODE
from data.nations import NATIONS_BY_ID


def test_derbies_name_real_teams():
    teams = {club.name for league in LEAGUES_BY_CODE.values() for club in league.clubs}
    teams |= {nation.name for nation in NATIONS_BY_ID.values()}
    for pair in DERBIES:
        assert len(pair) == 2
        assert pair <= teams, pair - teams


def test_derby_works_both_ways():
    assert derby("Aviron Bayonnais", "Biarritz Olympique") == "Derby basque"
    assert derby("Biarritz Olympique", "Aviron Bayonnais") == "Derby basque"
    assert derby("Angleterre", "France") == "Le Crunch"
    assert derby("Stade Toulousain", "Saracens") is None
