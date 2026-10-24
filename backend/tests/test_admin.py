"""Backoffice : réservé aux administrateurs, comptes et formule, clubs retouchés qui
servent aux nouvelles parties, couleurs et blasons lus par l'interface."""

import base64

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

import accounts
import catalog
import database
from api import auth
from api.main import app
from api.routers.admin import ADMIN_EMAIL
from models.orm import ClubRow, PlayerRow

ADMIN = ADMIN_EMAIL
# Le plus petit PNG valable (un pixel).
PIXEL = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
)


def sign_up(email: str) -> TestClient:
    client = TestClient(app)
    created = client.post("/auth/register", json={"email": email, "password": "ballon-ovale"})
    assert created.status_code == 201, created.text
    return client


@pytest.fixture
def admin(world) -> TestClient:
    auth._attempts.clear()  # le frein des inscriptions compte par adresse IP, tests compris
    return sign_up(ADMIN)


def test_only_admins_get_in(admin):
    player = sign_up("joueur@example.com")
    assert player.get("/backoffice/me").status_code == 403
    assert player.get("/backoffice/users").status_code == 403
    assert TestClient(app).get("/backoffice/overview").status_code == 401
    assert admin.get("/backoffice/me").json() == {"email": ADMIN}


def test_accounts_and_premium(admin):
    player = sign_up("joueur@example.com")
    assert player.post("/saves/1/new").status_code == 201
    users = {u["email"]: u for u in admin.get("/backoffice/users").json()}
    joueur = users["joueur@example.com"]
    assert users[ADMIN]["admin"] and not joueur["admin"]
    assert joueur["saves"] == 1 and not joueur["premium"] and joueur["last_login_at"]
    assert joueur["seasons_left"] == accounts.FREE_SEASONS

    offered = admin.put(f"/backoffice/users/{joueur['id']}/premium", json={"premium": True}).json()
    assert offered["premium"] and offered["premium_source"] == "offert"
    assert offered["seasons_left"] is None and len(offered["slots"]) == 1
    overview = admin.get("/backoffice/overview").json()
    assert overview["accounts"] == 2 and overview["premium_offered"] == 1
    assert overview["saves"] == 1 and overview["clubs"] == len(catalog.real_clubs())

    revoked = admin.put(f"/backoffice/users/{joueur['id']}/premium", json={"premium": False}).json()
    assert not revoked["premium"] and revoked["premium_source"] is None
    assert admin.get("/backoffice/users/999").status_code == 404


def test_paid_accounts_show_as_stripe(admin):
    user = accounts.find(ADMIN)
    accounts.grant_premium(user.id, "pi_123")
    found = admin.get(f"/backoffice/users/{user.id}").json()
    assert found["premium_source"] == "stripe" and found["payment_ref"] == "pi_123"


def test_reset_seasons(admin):
    user = accounts.find(ADMIN)
    accounts.count_season(user.id)
    accounts.count_season(user.id)
    assert admin.get(f"/backoffice/users/{user.id}").json()["seasons_left"] == 0
    assert admin.post(f"/backoffice/users/{user.id}/seasons/reset").json()["seasons_played"] == 0


def club_form(club: dict, **changes) -> dict:
    form = {k: club[k] for k in ("league", "city", "stadium", "capacity", "level", "wealth")}
    return {**form, "colors": None, "light": None, **changes}


def test_club_edits_reach_new_worlds_only(admin):
    accounts.grant_premium(accounts.find(ADMIN).id)
    assert admin.post("/saves/1/new").status_code == 201
    club = admin.get("/backoffice/clubs/Stade Toulousain").json()
    assert club["edited"] == [] and club["roster_source"] == "fichier"

    saved = admin.put(
        "/backoffice/clubs/Stade Toulousain", json=club_form(club, capacity=40_000, wealth=0.2)
    ).json()
    assert sorted(saved["edited"]) == ["capacity", "wealth"]
    assert saved["defaults"]["capacity"] == 19_000
    roster = {
        "pros": [
            {
                "name": "Jean Neuf",
                "position": "FLY_HALF",
                "nationality": "FRA",
                "born": "2000-01-02",
            }
        ],
        "youths": [],
    }
    saved = admin.put("/backoffice/clubs/Stade Toulousain/roster", json=roster).json()
    assert saved["roster_source"] == "backoffice" and saved["pros"] == 1
    assert saved["roster"]["pros"][0]["position"] == "FLY_HALF"

    def toulouse(slot: int) -> tuple[ClubRow, list[str]]:
        with database.open_slot(accounts.find(ADMIN).id, slot) as session:
            row = session.scalars(select(ClubRow).where(ClubRow.name == "Stade Toulousain")).one()
            names = session.scalars(
                select(PlayerRow.last_name).where(PlayerRow.club_id == row.id)
            ).all()
            return row, names

    old, old_names = toulouse(1)
    assert old.stadium_capacity == 19_000 and "Neuf" not in old_names
    assert admin.post("/saves/2/new").status_code == 201
    new, new_names = toulouse(2)
    # Le plus grand stade constructible plafonne la capacité ; l'effectif saisi est là,
    # complété par des joueurs inventés.
    assert new.stadium_capacity > old.stadium_capacity and "Neuf" in new_names
    assert new.balance < old.balance

    # Revenir à la valeur du code efface la retouche ; tout effacer rend le club d'origine.
    back = admin.put("/backoffice/clubs/Stade Toulousain", json=club_form(club, wealth=0.2)).json()
    assert sorted(back["edited"]) == ["roster", "wealth"]
    assert admin.delete("/backoffice/clubs/Stade Toulousain").json()["edited"] == []
    assert catalog.edits() == {}


def test_colours_and_logo_are_public(admin):
    club = admin.get("/backoffice/clubs/RC Toulon").json()
    form = club_form(club, colors=["#ff0000", "#000000"], light=True)
    saved = admin.put("/backoffice/clubs/RC Toulon", json=form).json()
    assert saved["colors"] == ["#FF0000", "#000000"]
    assert (
        admin.put(
            "/backoffice/clubs/RC Toulon/logo", json={"data": base64.b64encode(b"<svg/>").decode()}
        ).status_code
        == 400
    )
    saved = admin.put(
        "/backoffice/clubs/RC Toulon/logo", json={"data": base64.b64encode(PIXEL).decode()}
    ).json()
    assert "logo" in saved["edited"]

    visitor = TestClient(app)
    shown = visitor.get("/catalog/clubs").json()["RC Toulon"]
    assert shown["colors"] == ["#FF0000", "#000000"] and shown["light"] is True
    image = visitor.get(shown["logo"])
    assert image.status_code == 200 and image.content == PIXEL
    assert image.headers["content-type"] == "image/png"

    admin.delete("/backoffice/clubs/RC Toulon/logo")
    assert "logo" not in visitor.get("/catalog/clubs").json()["RC Toulon"]


def test_unknown_club_and_bad_roster(admin):
    assert admin.get("/backoffice/clubs/Club Inconnu").status_code == 404
    bad = {"pros": [{"name": "X", "position": "GOALKEEPER"}]}
    assert admin.put("/backoffice/clubs/RC Toulon/roster", json=bad).status_code == 422


def world_clubs(slot: int) -> dict[str, str]:
    """Nom -> championnat de chaque club de la partie de l'admin."""
    with database.open_slot(accounts.find(ADMIN).id, slot) as session:
        return dict(session.execute(select(ClubRow.name, ClubRow.league)).all())


def test_a_club_changes_league_in_new_worlds(admin):
    accounts.grant_premium(accounts.find(ADMIN).id)
    vannes = admin.get("/backoffice/clubs/RC Vannes").json()
    moved = admin.put("/backoffice/clubs/RC Vannes", json=club_form(vannes, league="top14")).json()
    assert moved["league"] == "top14" and moved["edited"] == ["league"]
    assert moved["defaults"]["league"] == "prod2"
    leagues = {lg["code"]: lg for lg in admin.get("/backoffice/leagues").json()}
    assert leagues["top14"]["clubs"] == 15 and leagues["prod2"]["clubs"] == 15
    assert leagues["prod2"]["promotion"] == "up" and leagues["top14"]["europe"]

    assert admin.post("/saves/1/new").status_code == 201
    clubs = world_clubs(1)
    assert clubs["RC Vannes"] == "top14"
    assert sum(league == "top14" for league in clubs.values()) == 15
    # Retour dans son championnat d'origine : plus de retouche.
    back = admin.put("/backoffice/clubs/RC Vannes", json=club_form(vannes, league="prod2")).json()
    assert back["edited"] == [] and catalog.edits() == {}
    unknown = admin.put("/backoffice/clubs/RC Vannes", json=club_form(vannes, league="nope"))
    assert unknown.status_code == 400


def test_a_league_has_at_most_sixteen_clubs(admin):
    prod2 = [c for c in admin.get("/backoffice/clubs").json() if c["league"] == "prod2"]
    assert len(prod2) == 16
    toulon = admin.get("/backoffice/clubs/RC Toulon").json()
    refused = admin.put("/backoffice/clubs/RC Toulon", json=club_form(toulon, league="prod2"))
    assert refused.status_code == 400 and "16" in refused.json()["detail"]


def new_league(admin, **changes) -> dict:
    body = {
        "name": "Fédérale 1",
        "short_name": "Fédérale 1",
        "country": "France",
        "nation": "FRA",
        "playoffs": "top4",
        "calendar": "prod2",
        "prize_factor": 0.1,
        **changes,
    }
    created = admin.post("/backoffice/leagues", json=body)
    assert created.status_code == 201, created.text
    return next(lg for lg in created.json() if lg["name"] == body["name"])


def new_club(admin, name: str, league: str, **changes) -> dict:
    body = {
        "name": name,
        "league": league,
        "city": "Ville",
        "stadium": "Stade municipal",
        "capacity": 5_000,
        "level": 7.0,
        "wealth": 0.1,
        "colors": ["#123456", "#FFFFFF"],
        **changes,
    }
    created = admin.post("/backoffice/clubs", json=body)
    assert created.status_code == 201, created.text
    return created.json()


def test_created_league_and_clubs_reach_new_worlds(admin):
    accounts.grant_premium(accounts.find(ADMIN).id)
    league = new_league(admin)
    assert league["code"] == "federale1" and league["custom"] and league["clubs"] == 0
    assert not league["ready"] and league["min_clubs"] == 4

    for i in range(1, 5):
        club = new_club(admin, f"Club Fédéral {i}", "federale1")
    assert club["created"] and club["nation"] is None and club["roster_source"] == "inventé"
    assert (
        admin.post("/backoffice/clubs", json={**club, "name": "Club Fédéral 1"}).status_code == 400
    )
    assert admin.post("/backoffice/clubs", json={**club, "name": "France"}).status_code == 400
    shown = admin.get("/catalog/clubs").json()["Club Fédéral 1"]
    assert shown["colors"] == ["#123456", "#FFFFFF"]
    leagues = {lg["code"]: lg for lg in admin.get("/backoffice/leagues").json()}
    assert leagues["federale1"]["ready"] and leagues["federale1"]["clubs"] == 4

    assert admin.post("/saves/1/new").status_code == 201
    clubs = world_clubs(1)
    assert [n for n, lg in clubs.items() if lg == "federale1"] == [
        f"Club Fédéral {i}" for i in range(1, 5)
    ]
    # Le championnat créé a son nom dans la partie, et ses clubs le pays du championnat.
    names = {lg["code"]: lg["name"] for lg in admin.get("/leagues").json()}
    assert names["federale1"] == "Fédérale 1"
    with database.open_slot(accounts.find(ADMIN).id, 1) as session:
        row = session.scalars(select(ClubRow).where(ClubRow.name == "Club Fédéral 1")).one()
        nationalities = {p.nationality for p in row.players}
    assert nationalities == {"FRA"}

    # Archivé, il quitte les nouvelles parties mais reste connu des anciennes.
    archived = admin.put(
        "/backoffice/leagues/federale1",
        json={**league, "archived": True, "playoffs": "top4", "calendar": "prod2"},
    ).json()
    assert not next(lg for lg in archived if lg["code"] == "federale1")["ready"]
    assert admin.post("/saves/2/new").status_code == 201
    assert "Club Fédéral 1" not in world_clubs(2)
    assert admin.get("/leagues").status_code == 200
    refused = admin.post("/backoffice/clubs", json={**club, "name": "Club Fédéral 5"})
    assert refused.status_code == 400

    # Un club créé s'efface (il reste dans les parties déjà commencées).
    assert admin.delete("/backoffice/clubs/Club Fédéral 4").json() is None
    assert admin.get("/backoffice/clubs/Club Fédéral 4").status_code == 404
    assert "Club Fédéral 4" in world_clubs(1)


def test_built_in_leagues_are_read_only(admin):
    body = {"name": "Top 15", "short_name": "Top 15", "playoffs": "top6", "calendar": "top14",
            "prize_factor": 1}  # fmt: skip
    assert admin.put("/backoffice/leagues/top14", json=body).status_code == 404
    assert admin.post("/backoffice/leagues", json={**body, "calendar": "nope"}).status_code == 400
