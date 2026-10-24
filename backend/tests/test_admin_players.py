"""Backoffice, joueurs : modifier, déplacer, créer et supprimer les joueurs des effectifs,
fixer leurs notes et leur photo, pour les nouvelles parties."""

import base64
import urllib.parse

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

import accounts
import catalog
import database
from api import auth
from api.routers.admin import ADMIN_EMAIL, Ratings
from models import ATTRIBUTE_NAMES
from models.orm import ClubRow, PlayerRow
from tests.test_admin import PIXEL, sign_up

TOULOUSE, TOULON = "Stade Toulousain", "RC Toulon"
PLAYER = "Dorian Aldegheri"
NOTES = {name: 17 for name in ATTRIBUTE_NAMES} | {"kicking": 3}


@pytest.fixture
def admin(world) -> TestClient:
    auth._attempts.clear()  # le frein des inscriptions compte par adresse IP, tests compris
    client = sign_up(ADMIN_EMAIL)
    accounts.grant_premium(accounts.find(ADMIN_EMAIL).id)
    return client


def url(club: str, name: str, tail: str = "") -> str:
    return f"/backoffice/players/{urllib.parse.quote(club)}/{urllib.parse.quote(name)}{tail}"


def form(player: dict, **changes) -> dict:
    keys = ("name", "position", "nationality", "international", "born", "photo", "attributes")
    return {**{k: player[k] for k in keys}, "club": player["club"], "squad": player["squad"]} | (
        changes
    )


def world_player(slot: int, last_name: str) -> tuple[str, PlayerRow]:
    """(club, joueur) de ce nom dans la partie de l'admin."""
    with database.open_slot(accounts.find(ADMIN_EMAIL).id, slot) as session:
        player = session.scalars(select(PlayerRow).where(PlayerRow.last_name == last_name)).one()
        return session.get(ClubRow, player.club_id).name, player


def test_ratings_cover_every_attribute():
    assert set(Ratings.model_fields) == set(ATTRIBUTE_NAMES)


def test_move_a_player_and_fix_his_notes(admin):
    players = admin.get("/backoffice/players").json()
    found = next(p for p in players if p["name"] == PLAYER)
    assert found["club"] == TOULOUSE and found["league"] == "top14" and found["squad"] == "pros"
    assert found["attributes"] is None and found["photo_url"].startswith("/photos/")

    detail = admin.get(url(TOULOUSE, PLAYER)).json()
    assert detail["typical"]["scrum"] > detail["typical"]["kicking"]  # un pilier
    moved = admin.put(url(TOULOUSE, PLAYER), json=form(detail, club=TOULON, attributes=NOTES))
    assert moved.status_code == 200, moved.text
    assert moved.json()["club"] == TOULON and moved.json()["attributes"] == NOTES
    assert admin.get(url(TOULOUSE, PLAYER)).status_code == 404

    clubs = {c["name"]: c for c in admin.get("/backoffice/clubs").json()}
    assert clubs[TOULOUSE]["roster_source"] == clubs[TOULON]["roster_source"] == "backoffice"
    assert clubs[TOULOUSE]["pros"] == 36 and clubs[TOULON]["pros"] == 37

    # L'onglet Effectif d'un club réenregistre ses joueurs sans perdre leurs notes.
    toulon = admin.get(f"/backoffice/clubs/{TOULON}").json()
    admin.put(f"/backoffice/clubs/{TOULON}/roster", json=toulon["roster"])
    assert admin.get(url(TOULON, PLAYER)).json()["attributes"] == NOTES

    assert admin.post("/saves/1/new").status_code == 201
    club, row = world_player(1, "Aldegheri")
    assert club == TOULON
    assert {name: getattr(row, name) for name in ATTRIBUTE_NAMES} == NOTES


def test_create_and_delete_players(admin):
    body = {"name": "Jean  Neuf", "position": "WING", "nationality": "FRA", "club": "RC Vannes"}
    created = admin.post("/backoffice/players", json=body)
    assert created.status_code == 201, created.text
    assert created.json()["name"] == "Jean Neuf" and created.json()["squad"] == "pros"
    assert admin.post("/backoffice/players", json=body).status_code == 400
    assert admin.post("/backoffice/players", json={**body, "club": "Nulle Part"}).status_code == 404
    assert admin.post("/backoffice/players", json={**body, "name": "A/B"}).status_code == 422
    bad = {**body, "name": "Jean Trop", "attributes": {**NOTES, "pace": 21}}
    assert admin.post("/backoffice/players", json=bad).status_code == 422

    # Le renommer vers le nom d'un coéquipier est refusé ; passer chez les espoirs, non.
    detail = created.json()
    teammate = next(
        p["name"] for p in admin.get("/backoffice/players").json() if p["club"] == "RC Vannes"
    )
    renamed = admin.put(url("RC Vannes", "Jean Neuf"), json=form(detail, name=teammate))
    assert renamed.status_code == 400
    youth = admin.put(url("RC Vannes", "Jean Neuf"), json=form(detail, squad="youths")).json()
    assert youth["squad"] == "youths"

    assert admin.delete(url("RC Vannes", "Jean Neuf")).status_code == 204
    assert admin.get(url("RC Vannes", "Jean Neuf")).status_code == 404
    assert admin.delete(url("RC Vannes", "Jean Neuf")).status_code == 404


def test_a_club_without_roster_gets_its_first_player(admin):
    club = next(c for c in admin.get("/backoffice/clubs").json() if c["roster_source"] == "inventé")
    body = {"name": "Paul Premier", "position": "FLY_HALF", "club": club["name"]}
    assert admin.post("/backoffice/players", json=body).status_code == 201
    assert admin.get(f"/backoffice/clubs/{club['name']}").json()["pros"] == 1

    assert admin.post("/saves/1/new").status_code == 201
    name, _ = world_player(1, "Premier")
    assert name == club["name"]


def test_an_uploaded_photo_wins_over_wikimedia(admin):
    refused = admin.put(url(TOULOUSE, PLAYER, "/photo"), json={"data": "pas une image"})
    assert refused.status_code == 400
    sent = admin.put(
        url(TOULOUSE, PLAYER, "/photo"), json={"data": base64.b64encode(PIXEL).decode()}
    ).json()
    assert sent["photo_id"] and sent["photo_url"] == catalog.photo_url(sent["photo_id"])

    image = TestClient(admin.app).get(sent["photo_url"])
    assert image.status_code == 200 and image.content == PIXEL
    assert image.headers["content-type"] == "image/png"

    # Elle suit le joueur dans son nouveau club, et dans les nouvelles parties.
    moved = admin.put(url(TOULOUSE, PLAYER), json=form(sent, club=TOULON)).json()
    assert moved["photo_id"] == sent["photo_id"]
    assert admin.post("/saves/1/new").status_code == 201
    assert world_player(1, "Aldegheri")[1].photo == sent["photo_url"]

    back = admin.delete(url(TOULON, PLAYER, "/photo")).json()
    assert back["photo_id"] is None and back["photo_url"].startswith("/photos/")
    # La photo reste servie : la partie commencée la montre encore.
    assert TestClient(admin.app).get(sent["photo_url"]).status_code == 200
