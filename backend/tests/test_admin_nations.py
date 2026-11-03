"""Backoffice, sélections : la compo saisie (groupe et XV) guide le staff dans les parties."""

import random
import urllib.parse

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

import accounts
import database
from api import auth, friendly, internationals
from api.ledger import current_season
from api.routers.admin import ADMIN_EMAIL
from data.generator import FIRST_SEASON_YEAR, generate_player
from data.nations import NATIONS_BY_CODE
from engine import internationals as rules
from engine.calendar import WORLD_CUP_FIRST_YEAR
from engine.match_engine import SLOT_POSITIONS, select_lineup
from models import Position
from models.orm import PlayerRow
from tests.test_admin import sign_up

URL = "/backoffice/nations"
FRANCE = f"{URL}/FRA"


@pytest.fixture
def admin(world) -> TestClient:
    auth._attempts.clear()  # le frein des inscriptions compte par adresse IP, tests compris
    client = sign_up(ADMIN_EMAIL)
    accounts.grant_premium(accounts.find(ADMIN_EMAIL).id)
    return client


def entry(player: dict) -> dict:
    return {"club": player["club"], "name": player["name"]}


def worst_at_each_slot(detail: dict) -> tuple[list[dict], list[int]]:
    """Un groupe de 15 joueurs qu'un staff n'aurait pas pris (les derniers de leur poste
    dans la liste, sans sélection), un par place du XV, et ce XV."""
    by_position: dict[str, list[dict]] = {}
    for player in detail["players"]:
        if not player["international"]:
            by_position.setdefault(player["position"], []).append(player)
    squad = [by_position[slot["position"]].pop() for slot in detail["slots"]]
    return [entry(p) for p in squad], list(range(len(squad)))


def test_only_the_admin_reaches_the_compos(world):
    auth._attempts.clear()
    assert sign_up("joueur@example.com").get(URL).status_code == 403


def test_a_compo_stays_with_the_nation_and_goes_back_to_the_staff(admin):
    nations = admin.get(URL).json()
    assert len(nations) == 16
    france = next(n for n in nations if n["code"] == "FRA")
    assert not france["edited"] and france["listed"] == 0 and france["pool"] > 100

    detail = admin.get(FRANCE).json()
    assert len(detail["slots"]) == len(SLOT_POSITIONS) and detail["size"] == rules.SQUAD_SIZE
    assert all(p["squad"] == "pros" and p["nationality"] == "FRA" for p in detail["players"])
    assert detail["players"][0]["international"]

    squad, lineup = worst_at_each_slot(detail)
    saved = admin.put(FRANCE, json={"squad": squad, "lineup": lineup})
    assert saved.status_code == 200, saved.text
    assert saved.json()["squad"] == squad and saved.json()["lineup"] == lineup
    assert saved.json()["edited"] and saved.json()["updated_by"] == ADMIN_EMAIL

    summary = next(n for n in admin.get(URL).json() if n["code"] == "FRA")
    assert summary["listed"] == 15 and summary["starters"] == 15

    back = admin.delete(FRANCE).json()
    assert not back["edited"] and back["squad"] == [] and back["lineup"] == []


def test_a_home_only_federation_limits_who_can_be_listed(admin):
    ireland = admin.get(f"{URL}/IRE").json()
    assert ireland["home_only"]
    assert {p["club"] for p in ireland["players"]} <= {
        "Leinster Rugby",
        "Munster Rugby",
        "Ulster Rugby",
        "Connacht Rugby",
    }
    france = admin.get(FRANCE).json()
    outsider = entry(france["players"][0])
    refused = admin.put(f"{URL}/IRE", json={"squad": [outsider]})
    assert refused.status_code == 400 and outsider["name"] in refused.json()["detail"]


def test_a_compo_that_cannot_make_a_valid_list_is_refused(admin):
    detail = admin.get(FRANCE).json()
    one = entry(detail["players"][0])
    assert admin.get(f"{URL}/XXX").status_code == 404
    assert admin.put(FRANCE, json={"squad": [one, one]}).status_code == 400
    assert admin.put(FRANCE, json={"squad": [one], "lineup": [0]}).status_code == 400
    outside = {"squad": [one], "lineup": [1] + [None] * 14}
    assert admin.put(FRANCE, json=outside).status_code == 400
    twice = {"squad": [one], "lineup": [0, 0] + [None] * 13}
    assert admin.put(FRANCE, json=twice).status_code == 400

    # 42 joueurs sans un seul talonneur : plus de place pour en appeler.
    no_hooker = [entry(p) for p in detail["players"] if p["position"] != "HOOKER"]
    refused = admin.put(FRANCE, json={"squad": no_hooker[:42]})
    assert refused.status_code == 400 and "talonneurs" in refused.json()["detail"]
    assert admin.put(FRANCE, json={"squad": no_hooker[:40]}).status_code == 200
    assert admin.put(FRANCE, json={"squad": no_hooker[:41]}).status_code == 400


def test_a_compo_follows_a_renamed_or_moved_player_and_flags_the_gone(admin):
    detail = admin.get(FRANCE).json()
    squad, lineup = worst_at_each_slot(detail)
    assert admin.put(FRANCE, json={"squad": squad, "lineup": lineup}).status_code == 200

    def player_url(player: dict) -> str:
        return (
            f"/backoffice/players/{urllib.parse.quote(player['club'])}"
            f"/{urllib.parse.quote(player['name'])}"
        )

    first, second = squad[0], squad[1]
    sheet = admin.get(player_url(first)).json()
    keys = ("position", "nationality", "international", "born", "photo", "attributes", "squad")
    moved = {k: sheet[k] for k in keys} | {"name": "Nouveau Nom", "club": sheet["club"]}
    assert admin.put(player_url(first), json=moved).status_code == 200
    assert admin.delete(player_url(second)).status_code == 204

    after = admin.get(FRANCE).json()
    assert after["squad"][0] == {"club": first["club"], "name": "Nouveau Nom"}
    # Le joueur supprimé sort du groupe : les autres gardent leur place dans le XV.
    assert after["missing"] == [second["name"]]
    assert len(after["squad"]) == 14
    assert after["lineup"] == [0, None, *range(1, 14)]


def test_a_new_world_lists_the_compo_and_starts_its_xv(admin):
    detail = admin.get(FRANCE).json()
    squad, lineup = worst_at_each_slot(detail)
    assert admin.put(FRANCE, json={"squad": squad, "lineup": lineup}).status_code == 200
    assert admin.post("/saves/1/new").status_code == 201

    user = accounts.find(ADMIN_EMAIL).id
    with database.open_slot(user, 1) as session:
        pool = internationals.eligible_players(session, {"FRA"})["FRA"]
        chosen = internationals.compo(session, "FRA", pool)
        by_id = {p.id: p for p in pool}
        assert [by_id[i].name for i in chosen.squad] == [e["name"] for e in squad]

        # Le staff garde le groupe de la compo et complète sa liste de 42.
        squad_players = internationals.staff_squad(session, "FRA", pool, None)
        assert len(squad_players) == rules.SQUAD_SIZE
        assert [p.id for p in squad_players[:15]] == chosen.squad
        team = rules.national_team(NATIONS_BY_CODE["FRA"], squad_players, chosen.lineup)
        assert [p.id for p in select_lineup(team)] == chosen.squad

        # Une autre nation reste à son staff ; un joueur absent de la partie laisse sa
        # place du XV au staff, les autres gardent la leur.
        assert internationals.compo(session, "ENG", pool).squad == []
        without = [p for p in pool if p.id != chosen.squad[0]]
        partial = internationals.compo(session, "FRA", without)
        assert partial.lineup == [None, *chosen.squad[1:]]


def test_a_compo_stops_after_the_first_world_cup(admin):
    detail = admin.get(FRANCE).json()
    squad, _ = worst_at_each_slot(detail)
    assert admin.put(FRANCE, json={"squad": squad}).status_code == 200
    assert admin.post("/saves/1/new").status_code == 201
    career = admin.post("/career", json={"manager_name": "Max", "nation": "FRA"})
    assert career.status_code == 201, career.text

    user = accounts.find(ADMIN_EMAIL).id
    with database.open_slot(user, 1) as session:
        pool = internationals.eligible_players(session, {"FRA"})["FRA"]
        season = current_season(session)
        assert season.year == FIRST_SEASON_YEAR
        assert len(internationals.compo(session, "FRA", pool).squad) == 15
        season.year = WORLD_CUP_FIRST_YEAR
        session.flush()
        assert len(internationals.compo(session, "FRA", pool).squad) == 15
        season.year = WORLD_CUP_FIRST_YEAR + 1
        session.flush()
        assert internationals.compo(session, "FRA", pool).squad == []
        session.rollback()


def test_a_selector_is_offered_the_compo_and_can_change_it(admin):
    detail = admin.get(FRANCE).json()
    squad, lineup = worst_at_each_slot(detail)
    assert admin.put(FRANCE, json={"squad": squad, "lineup": lineup}).status_code == 200
    assert admin.post("/saves/1/new").status_code == 201
    career = admin.post("/career", json={"manager_name": "Max", "nation": "FRA"})
    assert career.status_code == 201, career.text

    pool = admin.get("/selection/pool").json()
    names = {p["player"]["id"]: p["player"]["name"] for p in pool["players"]}
    suggested = [names[i] for i in pool["suggested"][:15]]
    assert suggested == [e["name"] for e in squad]

    team = admin.get("/selection/team").json()
    assert not team["lineup_custom"]  # le XV de la compo reste celui du staff
    starters = {p["id"]: p["name"] for p in team["players"]}
    assert [starters[i] for i in team["strength"]["lineup_ids"]] == suggested

    mine = team["strength"]["lineup_ids"]
    mine[0], mine[1] = mine[1], mine[0]
    chosen = admin.put("/selection/lineup", json={"player_ids": mine}).json()
    assert chosen["lineup_custom"] and chosen["strength"]["lineup_ids"][:2] == mine[:2]


def test_a_friendly_nation_fields_the_compo(admin):
    detail = admin.get(FRANCE).json()
    squad, lineup = worst_at_each_slot(detail)
    assert admin.put(FRANCE, json={"squad": squad, "lineup": lineup}).status_code == 200

    with friendly.reference() as session:
        names = {
            p.id: f"{p.first_name} {p.last_name}".strip()
            for p in session.scalars(select(PlayerRow).where(PlayerRow.nationality == "FRA"))
        }
        france, england = NATIONS_BY_CODE["FRA"].id, NATIONS_BY_CODE["ENG"].id
        row = friendly.prepare(session, accounts.find(ADMIN_EMAIL).id, france, england, france)
        home, _ = friendly._teams(session, row)
        assert [names[p.id] for p in select_lineup(home)] == [e["name"] for e in squad]


def test_the_staff_picks_the_preferred_first_then_completes_each_position():
    rng = random.Random(0)
    ids = iter(range(1, 1000))
    pool = [
        generate_player(next(ids), position, 12.0, 1, rng, nationality="FRA")
        for position in rules.SQUAD_QUOTA
        for _ in range(10)
    ]
    props = [p for p in pool if p.position == Position.PROP]
    weakest = min(props, key=rules.position_rating)
    squad = rules.pick_squad(pool, None, preferred=[weakest.id])
    assert squad[0] is weakest and len(squad) == rules.SQUAD_SIZE
    assert rules.check_squad(squad) is None
    # Il prend une place du quota : pas un pilier de plus.
    assert sum(p.position == Position.PROP for p in squad) == rules.SQUAD_QUOTA[Position.PROP]

    # Sans compo, la liste du staff ne change pas.
    assert rules.pick_squad(pool, None) == rules.pick_squad(pool, None, preferred=[])
    # Un joueur inconnu ne prend pas de place.
    assert rules.pick_squad(pool, None, preferred=[99999]) == rules.pick_squad(pool, None)

    # Une compo riche en piliers garde quand même le minimum aux autres postes.
    many = [p.id for p in pool if p.position in (Position.PROP, Position.LOCK, Position.BACK_ROW)]
    squad = rules.pick_squad(pool, None, preferred=many)
    assert len(squad) == rules.SQUAD_SIZE and rules.check_squad(squad) is None
