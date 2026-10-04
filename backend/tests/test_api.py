"""Tests de l'API, sur une base SQLite en mémoire (fixtures `client` et `manager` : conftest)."""

from datetime import date


def test_list_clubs(client):
    response = client.get("/clubs")
    assert response.status_code == 200
    clubs = response.json()
    assert len(clubs) == 10
    assert all(club["player_count"] == 31 for club in clubs)
    assert all(1 <= club["level"] <= 20 for club in clubs)


def test_get_club_squad(client):
    response = client.get("/clubs/1")
    assert response.status_code == 200
    club = response.json()
    assert len(club["players"]) == 31
    assert len(club["strength"]["lineup_ids"]) == 15
    player_ids = {p["id"] for p in club["players"]}
    assert set(club["strength"]["lineup_ids"]) <= player_ids


def test_unknown_club_returns_404(client):
    assert client.get("/clubs/999").status_code == 404


def test_simulate_match(client):
    response = client.post(
        "/matches/simulate", json={"home_club_id": 1, "away_club_id": 2, "seed": 7}
    )
    assert response.status_code == 200
    match = response.json()
    home_points = sum(e["points"] for e in match["events"] if e["club_id"] == 1)
    assert match["home_score"] == home_points
    # Même graine, même match.
    again = client.post("/matches/simulate", json={"home_club_id": 1, "away_club_id": 2, "seed": 7})
    assert again.json() == match


def test_club_cannot_play_itself(client):
    response = client.post("/matches/simulate", json={"home_club_id": 1, "away_club_id": 1})
    assert response.status_code == 400


def test_career(client):
    assert client.get("/career").status_code == 404

    created = client.post("/career", json={"manager_name": "Maxence", "club_id": 3})
    assert created.status_code == 201
    assert client.get("/career").json() == created.json()

    # Une nouvelle carrière remplace la précédente.
    client.post("/career", json={"manager_name": "Maxence", "club_id": 4})
    assert client.get("/career").json()["club_id"] == 4


def test_career_needs_an_existing_club(client):
    assert (
        client.post("/career", json={"manager_name": "Maxence", "club_id": 999}).status_code == 404
    )


def test_career_draws_a_dated_calendar(client):
    client.post("/career", json={"manager_name": "Maxence", "club_id": 3})
    season = client.get("/seasons/current").json()
    assert season["year"] == 2026
    assert season["phase"] == "regular"
    assert season["regular_matchdays"] == 18  # 10 clubs dans les tests
    assert len(season["matches"]) == 90
    assert season["next_matchday"]["matchday"] == 1
    assert all(match["home_score"] is None for match in season["matches"])
    assert all(date.fromisoformat(match["date"]).weekday() == 5 for match in season["matches"])
    assert season["standings"][0]["played"] == 0


def test_no_season_without_a_career(client):
    assert client.get("/seasons/current").status_code == 404


def test_play_the_whole_season_until_the_final(manager):
    first = manager.post("/seasons/current/play").json()
    assert first["played"]["matchday"] == 1
    assert len(first["played"]["matches"]) == 5
    assert all(m["home_score"] is not None for m in first["played"]["matches"])
    assert first["season"]["next_matchday"]["matchday"] == 2

    # Après une journée : billetterie ou sponsors en recette, salaires en dépense.
    categories = {t["category"] for t in manager.get("/finances").json()["transactions"]}
    assert {"sponsors", "wages"} <= categories

    # 18 journées, puis barrages, demi-finales et finale.
    for _ in range(17 + 3):
        season = manager.post("/seasons/current/play").json()["season"]
    assert season["phase"] == "finished"
    assert season["champion"] is not None
    assert len(season["matches"]) == 90 + 2 + 2 + 1
    assert all(row["played"] == 18 for row in season["standings"])
    assert season["next_matchday"] is None

    stages = [m["stage"] for m in season["matches"] if m["stage"] != "regular"]
    assert stages == ["barrage", "barrage", "semi", "semi", "final"]
    final = next(m for m in season["matches"] if m["stage"] == "final")
    assert final["neutral"] and final["home_score"] is not None
    # Le champion a reçu sa prime.
    assert manager.post("/seasons/current/play").status_code == 400


def test_next_season_ages_players_and_draws_a_new_calendar(manager):
    assert manager.post("/seasons/next").status_code == 400  # saison en cours

    for _ in range(21):
        manager.post("/seasons/current/play")
    ages_before = sorted(p["age"] for p in manager.get("/clubs/3").json()["players"])

    season = manager.post("/seasons/next").json()
    assert season["year"] == 2027
    assert season["phase"] == "regular"
    assert len(season["matches"]) == 90

    players = manager.get("/clubs/3").json()["players"]
    assert all(p["age"] < 36 for p in players)
    youths = [p for p in players if p["age"] <= 20]
    assert youths  # le centre de formation a produit au moins un jeune
    assert max(p["age"] for p in players) <= max(ages_before) + 1


def test_match_detail(manager):
    played = manager.post("/seasons/current/play").json()["played"]["matches"][0]
    match = manager.get(f"/matches/{played['id']}").json()
    assert match["home_score"] == played["home_score"]
    assert match["events"]
    unplayed = manager.get("/seasons/current").json()["next_matchday"]["matches"][0]
    assert manager.get(f"/matches/{unplayed['id']}").status_code == 400


# --- Gestion du club : finances, staff, infrastructures, transferts -------------------


def test_management_routes_need_a_career(client):
    for path in ("/finances", "/staff", "/facilities", "/transfers", "/medical"):
        assert client.get(path).status_code == 404


def test_finances(manager):
    finances = manager.get("/finances").json()
    assert finances["balance"] > 0
    assert finances["player_wages"] > finances["staff_wages"] > 0
    assert finances["squad_size"] == 31


def test_player_has_wage_and_value(manager):
    player = manager.get("/clubs/3").json()["players"][0]
    assert player["wage"] >= 40_000
    assert player["value"] > 0


def test_staff_fire_then_hire(manager):
    staff = manager.get("/staff").json()
    assert len(staff["slots"]) == 8
    assert all(slot["member"] is not None for slot in staff["slots"])
    slot = staff["slots"][0]
    candidate = next(c for c in staff["candidates"] if c["role"] == slot["role"])

    # Poste pourvu : impossible d'embaucher.
    assert manager.post(f"/staff/hire/{candidate['id']}").status_code == 400

    fired = manager.post(f"/staff/{slot['member']['id']}/fire").json()
    assert fired["slots"][0]["member"] is None
    assert fired["balance"] == staff["balance"] - slot["severance"]
    # Le licencié redevient candidat.
    assert any(c["id"] == slot["member"]["id"] for c in fired["candidates"])

    hired = manager.post(f"/staff/hire/{candidate['id']}").json()
    assert hired["slots"][0]["member"]["id"] == candidate["id"]
    assert all(c["id"] != candidate["id"] for c in hired["candidates"])


def test_cannot_fire_someone_else_staff(manager):
    # Le staff n°1 appartient au club 1, pas au nôtre.
    assert manager.post("/staff/1/fire").status_code == 404


def test_facility_upgrade_costs_money(manager):
    before = manager.get("/facilities").json()
    training = next(u for u in before["upgrades"] if u["kind"] == "training")
    assert training["affordable"]

    after = manager.post("/facilities/training/upgrade").json()
    assert after["facilities"]["training_level"] == training["current"] + 1
    assert after["balance"] == before["balance"] - training["cost"]


def test_facility_upgrade_refused_without_money(manager):
    # On enchaîne les agrandissements du stade jusqu'au refus.
    for _ in range(10):
        response = manager.post("/facilities/stadium/upgrade")
        if response.status_code == 400:
            break
    assert response.status_code == 400
    assert response.json()["detail"] in ("Trésorerie insuffisante", "Niveau maximum déjà atteint")


def test_transfers_buy_and_sell(manager):
    market = manager.get("/transfers").json()
    assert market["squad_size"] == 31
    assert all(listing["club_id"] != 3 for listing in market["listings"])
    cheapest = min(market["listings"], key=lambda listing: listing["asking_price"])
    player_id = cheapest["player"]["id"]

    bought = manager.post(f"/transfers/buy/{player_id}").json()
    assert bought["squad_size"] == 32
    assert bought["balance"] == market["balance"] - cheapest["asking_price"]
    assert all(listing["player"]["id"] != player_id for listing in bought["listings"])

    sold = manager.post(f"/transfers/sell/{player_id}").json()
    assert sold["squad_size"] == 31
    assert sold["balance"] > bought["balance"]
    labels = [t["label"] for t in manager.get("/finances").json()["transactions"]]
    assert any(label.startswith("Vente · ") for label in labels)
    assert any(label.startswith("Achat · ") for label in labels)
    # Le joueur vendu est de nouveau sur le marché.
    assert any(listing["player"]["id"] == player_id for listing in sold["listings"])


def test_transfer_limits(manager):
    # Un joueur d'un autre club ne se vend pas ; le nôtre ne s'achète pas.
    other = manager.get("/clubs/1").json()["players"][0]["id"]
    mine = manager.get("/clubs/3").json()["players"][0]["id"]
    assert manager.post(f"/transfers/sell/{other}").status_code == 404
    assert manager.post(f"/transfers/buy/{mine}").status_code == 404
