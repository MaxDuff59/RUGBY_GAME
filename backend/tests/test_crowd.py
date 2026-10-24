"""Tests du public : ambiance d'un stade et avantage du terrain."""

import random

from engine.crowd import Crowd, atmosphere, gate, label_for, tradition
from engine.match_engine import HOME_ADVANTAGE, LiveMatch, kick_success_probability, simulate_match
from models import Club

COLD = Crowd(spectators=3_000, capacity=12_000, atmosphere=0.2)
CAULDRON = Crowd(spectators=14_500, capacity=14_500, atmosphere=1.0)


def test_atmosphere_follows_fill_fervour_and_tradition():
    base = atmosphere(0.6, 10, 0.5)
    assert atmosphere(1.0, 10, 0.5) > base  # stade plein
    assert atmosphere(0.6, 16, 0.5) > base  # public en feu
    assert atmosphere(0.6, 10, 1.0) > base  # chaudron de tradition
    assert 0 <= atmosphere(0, 0, 0) <= atmosphere(1, 20, 1) <= 1
    assert label_for(0.9) == "Chaudron" and label_for(0.1) == "Stade clairsemé"


def test_perpignan_has_a_hotter_crowd_than_the_racing():
    assert tradition(Club(1, "USA Perpignan")) > tradition(Club(2, "Racing 92"))
    assert tradition(Club(3, "Club inventé")) == 0.5


def test_gate_fills_the_stadium_with_a_crowd():
    home = Club(1, "USA Perpignan")
    home.facilities.stadium_capacity = 14_500
    crowd = gate(home, rank=1, club_count=14, playoff=True, rng=random.Random(0))
    assert crowd.spectators == crowd.capacity == 14_500  # stade plein en phase finale
    assert crowd.label in {"Chaudron", "Bouillant"}


def _home_wins(home, away, crowd, count=600):
    rng = random.Random(1)
    wins = 0
    for _ in range(count):
        match = simulate_match(home, away, rng=rng, crowd=crowd)
        wins += match.home_score > match.away_score
    return wins / count


def test_a_cauldron_pushes_the_home_team(even_clubs):
    home, away = even_clubs
    assert COLD.advantage < HOME_ADVANTAGE < CAULDRON.advantage
    assert _home_wins(home, away, CAULDRON) > _home_wins(home, away, COLD)


def test_whistles_spoil_the_away_kicker_only(even_clubs):
    home, away = even_clubs
    live = LiveMatch(home, away, crowd=CAULDRON)
    kicker = max(away.players, key=lambda p: p.kicking)
    base = kick_success_probability(kicker.kicking)
    assert live._kick_probability(live.away, kicker) < base
    assert live._kick_probability(live.home, kicker) == base


def test_no_crowd_of_its_own_on_neutral_ground(even_clubs):
    home, away = even_clubs
    live = LiveMatch(home, away, neutral=True, crowd=CAULDRON)
    assert live.home_advantage == 1.0
    assert live.result().spectators is None


def test_crowd_survives_a_saved_live_match(even_clubs):
    home, away = even_clubs
    live = LiveMatch(home, away, rng=random.Random(3), crowd=CAULDRON)
    live.advance(20)
    resumed = LiveMatch.from_state(home, away, live.to_state())
    assert resumed.crowd == CAULDRON
    assert resumed.play_to_end() == live.play_to_end()


def test_the_kickoff_crowd_is_the_one_that_pays(manager):
    live = manager.post("/live").json()
    crowd = live["crowd"]
    assert crowd["spectators"] > 0 and 0 <= crowd["atmosphere"] <= 1 and crowd["label"]
    manager.post("/live/finish")
    # Le public du coup d'envoi est celui du match enregistré...
    detail = manager.get(f"/matches/{live['match_id']}").json()
    assert detail["crowd"] == crowd
    # ... et celui de la billetterie, quand nous recevons.
    if live["home"]["club"]["id"] == 3:
        spectators = f"{crowd['spectators']:,}".replace(",", " ")
        labels = [t["label"] for t in manager.get("/finances").json()["transactions"]]
        assert any(spectators in label for label in labels if label.startswith("Billetterie"))
