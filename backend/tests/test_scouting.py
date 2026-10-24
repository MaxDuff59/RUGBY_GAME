"""Tests des recruteurs : joueurs vus de loin, supervisions et rapports."""

from engine.scouting import REPORT_COST, estimate
from models import ATTRIBUTE_NAMES
from tests.conftest import make_club


def test_an_estimate_is_off_by_two_at_most_and_always_the_same():
    players = make_club(1, 12, seed=2).players
    for player in players:
        seen = estimate(player)
        assert seen == estimate(player)
        for name in ATTRIBUTE_NAMES:
            assert abs(getattr(seen, name) - getattr(player, name)) <= 2
            assert 1 <= getattr(seen, name) <= 20
    # Sur tout un effectif, l'estimation se trompe forcément quelque part.
    assert any(estimate(p).attributes != p.attributes for p in players)


def test_scouting_a_player_reveals_him_after_the_next_matchday(manager):
    mine = manager.get("/clubs/3").json()["players"]
    assert {p["scouting"] for p in mine} == {"own"}
    market = manager.get("/transfers").json()
    listing = next(row for row in market["listings"] if not row["free_agent"])
    player_id = listing["player"]["id"]
    assert listing["player"]["scouting"] == "estimate"

    balance = manager.get("/finances").json()["balance"]
    scouted = manager.post(f"/scouting/{player_id}")
    assert scouted.status_code == 201 and scouted.json()["scouting"] == "pending"
    assert manager.get("/finances").json()["balance"] == balance - REPORT_COST
    assert manager.post(f"/scouting/{player_id}").status_code == 400  # déjà supervisé
    assert manager.post(f"/scouting/{mine[0]['id']}").status_code == 400  # un des nôtres

    manager.post("/seasons/current/play")
    detail = manager.get(f"/players/{player_id}").json()["player"]
    assert detail["scouting"] == "report"
    # Le rapport donne un potentiel estimé de près, comme pour nos joueurs.
    width = detail["potential_high"] - detail["potential_low"]
    assert width <= 2.0
