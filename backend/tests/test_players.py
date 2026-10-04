"""Fiche joueur : GET /players/{id}."""


def test_player_detail(manager):
    club = manager.get("/clubs/3").json()
    starter_id = club["strength"]["lineup_ids"][0]

    response = manager.get(f"/players/{starter_id}")
    assert response.status_code == 200
    detail = response.json()
    assert detail["player"]["id"] == starter_id
    assert detail["club"] == {"id": 3, "name": club["name"]}
    assert detail["starter"] is True
    assert set(detail["lineup_ids"]) == set(club["strength"]["lineup_ids"])
    assert set(detail["ratings"]) == {"scrum", "lineout", "carrying", "attack", "defense"}
    assert len(detail["position_ratings"]) == 9
    # 10 clubs : il se compare aux joueurs de son poste de tout le championnat, lui compris.
    assert len(detail["peers"]) > 10
    assert any(peer["id"] == starter_id for peer in detail["peers"])
    assert all(peer["club_id"] for peer in detail["peers"])
    assert all(0 <= share <= 1 for share in detail["better_than"].values())
    assert "overall" in detail["better_than"]
    assert all(1 <= peer["position_rating"] <= 20 for peer in detail["peers"])
    assert detail["season"]["matches"] == 0
    assert detail["injuries"] == []


def test_player_season_stats_count_matches_played(manager):
    manager.post("/seasons/current/play")
    club = manager.get("/clubs/3").json()
    played = [manager.get(f"/players/{p['id']}").json()["season"] for p in club["players"]]
    # Le XV titulaire de la première journée a joué un match ; les autres zéro.
    assert sum(s["matches"] for s in played) == 15
    assert all(s["points"] >= 0 and s["tries"] <= s["matches"] * 5 for s in played)


def test_unknown_player_returns_404(client):
    assert client.get("/players/999999").status_code == 404
