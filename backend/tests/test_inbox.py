"""Tests de la boîte « à traiter »."""


def test_the_inbox_lists_what_awaits_a_decision(manager):
    assert manager.get("/inbox").status_code == 200
    # Une négociation ouverte attend une offre du manager.
    market = manager.get("/transfers").json()
    listing = next(row for row in market["listings"] if row["free_agent"])
    player_id = listing["player"]["id"]
    opened = manager.post(f"/transfers/{player_id}/open", json={"kind": "free"})
    assert opened.status_code == 201
    items = manager.get("/inbox").json()["items"]
    talk = next(item for item in items if item["kind"] == "transfer")
    assert talk["link"] == "/transferts" and listing["player"]["name"] in talk["title"]
    # Le plus pressant d'abord.
    urgent = [item["urgent"] for item in items]
    assert urgent == sorted(urgent, reverse=True)
    # Réglée, elle disparaît.
    manager.delete(f"/transfers/negotiations/{opened.json()['id']}")
    assert all(item["kind"] != "transfer" for item in manager.get("/inbox").json()["items"])


def test_the_inbox_needs_a_club_career(client):
    assert client.get("/inbox").status_code == 404
