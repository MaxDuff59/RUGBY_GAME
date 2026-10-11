"""Parties sauvegardées : trois emplacements par joueur, chacun son monde, sauvegarde
au fil du jeu, et chaque compte ne voit que les siennes."""

import pytest
from fastapi.testclient import TestClient

import database
from api.main import app


def sign_up(email: str) -> TestClient:
    client = TestClient(app)
    created = client.post("/auth/register", json={"email": email, "password": "ballon-ovale"})
    assert created.status_code == 201, created.text
    return client


@pytest.fixture
def saves(world) -> TestClient:
    return sign_up("maxence@example.com")


def start(client: TestClient, slot: int, manager: str, club_name: str) -> None:
    assert client.post(f"/saves/{slot}/new").status_code == 201
    club = next(c for c in client.get("/clubs").json() if c["name"] == club_name)
    client.post("/career", json={"manager_name": manager, "club_id": club["id"]})


def test_nothing_is_loaded_at_first(saves):
    listed = saves.get("/saves").json()
    assert [(s["slot"], s["empty"]) for s in listed] == [(1, True), (2, True), (3, True)]
    refused = saves.get("/career")
    assert refused.status_code == 409 and refused.json()["detail"] == "Aucune partie chargée"
    assert saves.post("/saves/2/load").status_code == 404
    assert saves.post("/saves/4/new").status_code == 422


def test_each_slot_keeps_its_own_world(saves):
    start(saves, 1, "Maxence", "Stade Toulousain")
    saves.post("/seasons/current/play")
    start(saves, 2, "Alex", "Leinster Rugby")

    listed = {s["slot"]: s for s in saves.get("/saves").json()}
    assert listed[2]["active"] and not listed[1]["active"]
    assert listed[1]["manager_name"] == "Maxence" and listed[1]["league_name"] == "Top 14"
    assert listed[2]["club_name"] == "Leinster Rugby" and listed[3]["empty"]
    # La journée jouée dans la partie 1 y est restée (sauvegarde automatique).
    assert listed[1]["game_date"] > listed[2]["game_date"]

    assert saves.post("/saves/1/load").json()["active"]
    assert saves.get("/career").json()["club_name"] == "Stade Toulousain"
    assert saves.post("/saves/1/new").status_code == 409  # emplacement pris


def test_a_deleted_save_is_gone(saves):
    start(saves, 3, "Maxence", "Bath Rugby")
    listed = saves.delete("/saves/3").json()
    assert listed[2]["empty"]
    assert saves.get("/career").status_code == 409
    assert not database.slot_exists(1, 3)


def test_each_player_has_their_own_saves(world):
    maxence = sign_up("maxence@example.com")
    alex = sign_up("alex@example.com")
    start(maxence, 1, "Maxence", "Stade Toulousain")
    start(alex, 1, "Alex", "Leinster Rugby")

    # Même emplacement, deux mondes : chacun retrouve le sien.
    assert maxence.get("/career").json()["club_name"] == "Stade Toulousain"
    assert alex.get("/career").json()["club_name"] == "Leinster Rugby"
    assert [s["empty"] for s in alex.get("/saves").json()] == [False, True, True]

    # Alex quitte sa partie : Maxence n'est pas touché.
    alex.delete("/saves/1")
    assert alex.get("/career").status_code == 409
    assert maxence.get("/career").json()["manager_name"] == "Maxence"
    assert database.slot_exists(1, 1) and not database.slot_exists(2, 1)


def test_the_loaded_save_follows_the_account(world):
    maxence = sign_up("maxence@example.com")
    start(maxence, 2, "Maxence", "Bath Rugby")
    # Un autre navigateur : nouvelle session, même compte, même partie chargée.
    other = TestClient(app)
    other.post("/auth/login", json={"email": "Maxence@Example.com", "password": "ballon-ovale"})
    assert other.get("/auth/me").json()["active_slot"] == 2
    assert other.get("/career").json()["club_name"] == "Bath Rugby"


def test_the_game_needs_an_account(world):
    anonymous = TestClient(app)
    assert anonymous.get("/saves").status_code == 401
    assert anonymous.get("/career").status_code == 401
    assert anonymous.post("/saves/1/new").status_code == 401
