"""Parties sauvegardées : trois emplacements, chacun son monde, sauvegarde au fil du jeu."""

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

import database
from api.main import app


@pytest.fixture
def saves(tmp_path, monkeypatch) -> Iterator[TestClient]:
    """Client sur de vraies parties, rangées dans un dossier temporaire."""
    monkeypatch.setattr(database, "SAVES_DIR", tmp_path)
    monkeypatch.setattr(database, "_engines", {})
    app.dependency_overrides.clear()
    yield TestClient(app)
    for engine in database._engines.values():
        engine.dispose()


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
    assert not (database.SAVES_DIR / "partie-3.db").exists()
