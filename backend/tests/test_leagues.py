"""Plusieurs championnats dans le même monde : calendriers, classements, montée et descente."""

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from api.main import app
from database import get_session, seed_if_empty
from engine.economy import SQUAD_MIN
from models.orm import Base, ClubRow


@pytest.fixture
def two_leagues() -> Iterator[TestClient]:
    """14 clubs inventés : les 7 premiers en Top 14, les 7 autres en Pro D2 ; on dirige le 3."""
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    TestSession = sessionmaker(bind=engine, expire_on_commit=False)
    with TestSession() as session:
        seed_if_empty(session, club_count=14, seed=0, real=False)
        for row in session.scalars(select(ClubRow)):
            row.league = "top14" if row.id <= 7 else "prod2"
        session.commit()

    def override_get_session() -> Iterator[Session]:
        with TestSession() as session:
            yield session

    app.dependency_overrides[get_session] = override_get_session
    client = TestClient(app)
    client.post("/career", json={"manager_name": "Maxence", "club_id": 3})
    yield client
    app.dependency_overrides.clear()


def played_matchdays(season: dict) -> set[int]:
    return {m["matchday"] for m in season["matches"] if m["home_score"] is not None}


def test_each_league_has_its_own_table_and_calendar(two_leagues):
    leagues = two_leagues.get("/leagues").json()
    assert [(lg["code"], lg["club_count"]) for lg in leagues] == [("top14", 7), ("prod2", 7)]
    assert two_leagues.get("/career").json()["league_name"] == "Top 14"

    top14 = two_leagues.get("/seasons/current").json()
    prod2 = two_leagues.get("/seasons/current?league=prod2").json()
    assert top14["league"]["code"] == "top14" and len(top14["standings"]) == 7
    assert {row["club_id"] for row in prod2["standings"]} == set(range(8, 15))
    assert [lg["code"] for lg in top14["leagues"]] == ["top14", "prod2"]
    # La Pro D2 démarre fin août, deux samedis avant le Top 14.
    assert prod2["matches"][0]["date"] < top14["matches"][0]["date"]
    assert two_leagues.get("/seasons/current?league=urc").status_code == 404


def test_other_leagues_play_their_matchdays_on_the_way(two_leagues):
    result = two_leagues.post("/seasons/current/play").json()
    assert result["played"]["matchday"] == 1
    assert all(m["home"]["id"] <= 7 for m in result["played"]["matches"])
    # Trois samedis de Pro D2 (22 et 29 août, 5 septembre) pour une journée de Top 14.
    prod2 = two_leagues.get("/seasons/current?league=prod2").json()
    assert played_matchdays(prod2) == {1, 2, 3}


def test_pro_d2_champion_goes_up_and_top14_last_goes_down(two_leagues):
    while two_leagues.get("/seasons/current").json()["phase"] != "finished":
        assert two_leagues.post("/seasons/current/play").status_code == 200
    top14 = two_leagues.get("/seasons/current").json()
    last = top14["standings"][-1]["club_id"]
    prod2 = two_leagues.get("/seasons/current?league=prod2").json()
    # La Pro D2 finit en même temps : son champion est connu.
    assert prod2["phase"] == "finished"
    champion = prod2["champion"]["id"]

    review = two_leagues.get("/seasons/current/review").json()
    assert review["league"]["code"] == "top14"
    assert review["movement"] == ("relegated" if last == 3 else None)

    for contract in two_leagues.get("/contracts").json()["pros"]:
        if contract["status"] == "open":
            two_leagues.post(
                f"/contracts/{contract['player']['id']}/extend",
                json={"years": contract["years_min"]},
            )
    # Des concurrents ont pu signer nos joueurs en fin de contrat : on complète
    # l'effectif avec des espoirs, comme le ferait le manager.
    youths = sorted(two_leagues.get("/academy").json()["youths"], key=lambda p: -p["overall"])
    while two_leagues.get("/contracts").json()["squad_next"] < SQUAD_MIN:
        two_leagues.post(f"/academy/promote/{youths.pop(0)['id']}")
    assert two_leagues.post("/seasons/next").status_code == 201
    leagues = {club["id"]: club["league"] for club in two_leagues.get("/clubs").json()}
    assert leagues[champion] == "top14" and leagues[last] == "prod2"
    top14 = two_leagues.get("/seasons/current?league=top14").json()
    assert champion in {row["club_id"] for row in top14["standings"]}
    assert top14["year"] == review["year"] + 1
