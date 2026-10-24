"""Tests du niveau de difficulté de la carrière."""

from engine.board import SACK_THRESHOLD, should_sack
from engine.difficulty import Difficulty, rules


def test_each_level_bends_the_rules_around_the_manager():
    easy, normal, hard = (rules(level) for level in Difficulty)
    assert easy.sack_threshold < normal.sack_threshold == SACK_THRESHOLD < hard.sack_threshold
    assert easy.revenue > normal.revenue == 1 > hard.revenue
    assert easy.demands < normal.demands == 1 < hard.demands
    assert rules(None) == normal  # une carrière d'avant les niveaux


def test_a_patient_board_keeps_its_manager_longer():
    confidence = SACK_THRESHOLD - 0.5
    assert should_sack(confidence, 20, 26)
    assert not should_sack(confidence, 20, 26, rules("easy").sack_threshold)


def _transfer_fee(manager) -> int:
    market = manager.get("/transfers").json()
    listing = next(row for row in market["listings"] if row["transfer_fee"])
    return listing["player"]["id"], listing["transfer_fee"]


def test_a_hard_career_makes_recruiting_dearer(client):
    client.post("/career", json={"manager_name": "Max", "club_id": 3})
    player_id, normal = _transfer_fee(client)
    client.post("/career", json={"manager_name": "Max", "club_id": 3, "difficulty": "hard"})
    career = client.get("/career").json()
    assert career["difficulty"] == "hard"
    market = client.get("/transfers").json()
    hard = next(row for row in market["listings"] if row["player"]["id"] == player_id)
    assert hard["transfer_fee"] > normal
    notes = client.get("/clubs/3/notes").json()
    assert notes["sack_threshold"] == rules("hard").sack_threshold
    unknown = {"manager_name": "Max", "club_id": 3, "difficulty": "x"}
    assert client.post("/career", json=unknown).status_code == 422
