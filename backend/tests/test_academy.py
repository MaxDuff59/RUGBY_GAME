"""Centre de formation : espoirs, progression, championnat espoirs, promotions."""

import random

from engine.offseason import age_players, develop_players, youth_exits
from models import Facilities, Squad
from tests.conftest import make_club


def test_young_players_grow_and_old_ones_decline():
    club = make_club(1, level=12, seed=3)
    club.facilities = Facilities(training_level=5)
    young = [p for p in club.players if p.age <= 20]
    old = [p for p in club.players if p.age >= 33]
    before = {p.id: p.overall for p in club.players}
    develop_players(club, random.Random(0))
    assert young and all(p.overall > before[p.id] for p in young)
    assert old and all(p.overall < before[p.id] for p in old)
    assert all(1 <= getattr(p, name) <= 20 for p in club.players for name in p.attributes)


def test_youths_too_old_leave_the_academy():
    club = make_club(1, level=12)
    club.youths = club.players[:3]
    club.players = club.players[3:]
    for youth in club.youths:
        youth.squad = Squad.YOUTH
    club.youths[0].age, club.youths[1].age, club.youths[2].age = 21, 19, 17
    age_players(club)
    assert youth_exits(club) == [club.youths[0]]


# --- API -----------------------------------------------------------------------------


def test_academy_overview(manager):
    academy = manager.get("/academy").json()
    assert academy["academy_level"] >= 1
    assert academy["intake_per_year"] == 2 + academy["academy_level"]
    assert len(academy["youths"]) == 25
    assert all(16 <= y["age"] <= 21 and y["squad"] == "youth" for y in academy["youths"])
    assert all(p["age"] <= 23 for p in academy["eligible_pros"])
    assert len(academy["matches"]) == 90  # même calendrier que les pros, 10 clubs
    assert academy["next_matchday"]["matchday"] == 1 and academy["last_matchday"] is None
    assert all(row["played"] == 0 for row in academy["standings"])
    assert len(academy["strength"]["lineup_ids"]) == 15
    # Les espoirs ne sont pas dans l'effectif pro, ni sur le marché.
    pros = manager.get("/clubs/3").json()["players"]
    assert len(pros) == 31 and all(p["squad"] == "pro" for p in pros)
    listings = manager.get("/transfers").json()["listings"]
    assert all(row["player"]["squad"] == "pro" for row in listings)


def test_youths_play_their_own_matchday(manager):
    manager.post("/seasons/current/play")
    academy = manager.get("/academy").json()
    assert academy["last_matchday"]["matchday"] == 1
    assert all(m["home_score"] is not None for m in academy["last_matchday"]["matches"])
    assert academy["next_matchday"]["matchday"] == 2
    assert sum(row["played"] for row in academy["standings"]) == 10
    # Le classement pro est bien à part.
    season = manager.get("/seasons/current").json()
    assert len(season["matches"]) == 90


def test_promote_and_demote(manager):
    academy = manager.get("/academy").json()
    best = max(academy["youths"], key=lambda y: y["overall"])
    promoted = manager.post(f"/academy/promote/{best['id']}").json()
    assert promoted["squad_size"] == 32
    assert all(y["id"] != best["id"] for y in promoted["youths"])
    pro = next(p for p in manager.get("/clubs/3").json()["players"] if p["id"] == best["id"])
    assert pro["squad"] == "pro" and pro["wage"] >= 40_000  # salaire de pro
    assert any(p["id"] == best["id"] for p in promoted["eligible_pros"])

    demoted = manager.post(f"/academy/demote/{best['id']}").json()
    assert demoted["squad_size"] == 31
    assert any(y["id"] == best["id"] for y in demoted["youths"])

    # Un pro de plus de 23 ans ne redescend pas ; un joueur d'un autre club non plus.
    veteran = next(p for p in manager.get("/clubs/3").json()["players"] if p["age"] > 23)
    assert manager.post(f"/academy/demote/{veteran['id']}").status_code == 400
    other = manager.get("/clubs/1").json()["players"][0]
    assert manager.post(f"/academy/demote/{other['id']}").status_code == 404
    assert manager.post(f"/academy/promote/{other['id']}").status_code == 404


def test_offseason_renews_the_academy(manager):
    before = manager.get("/academy").json()
    oldest = [y["id"] for y in before["youths"] if y["age"] >= 21]
    for _ in range(21):
        manager.post("/seasons/current/play")
    manager.post("/seasons/next")

    after = manager.get("/academy").json()
    ids = {y["id"] for y in after["youths"]}
    assert not ids & set(oldest)  # les 22 ans sont sortis
    newcomers = [y for y in after["youths"] if y["id"] not in {y["id"] for y in before["youths"]}]
    assert len(newcomers) == before["intake_per_year"]
    assert all(16 <= y["age"] <= 17 for y in newcomers)
    assert all(16 <= y["age"] <= 22 for y in after["youths"])
    # Les jeunes ont progressé.
    kept = {y["id"]: y for y in before["youths"] if y["id"] in ids}
    grown = [
        y for y in after["youths"] if y["id"] in kept and y["overall"] > kept[y["id"]]["overall"]
    ]
    assert len(grown) >= len(kept) * 0.8
    # Un championnat espoirs neuf.
    assert after["last_matchday"] is None and after["next_matchday"]["matchday"] == 1
