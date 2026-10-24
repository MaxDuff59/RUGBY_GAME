"""Tests de la Coupe d'Europe : poules, calendrier, phases finales."""

import random
from collections import Counter

from data.leagues import league_config
from engine import europe
from engine.calendar import season_dates
from engine.match_engine import simulate_match
from models import Stage
from tests.conftest import make_club

RANKED = {league: list(range(1 + k * 8, 9 + k * 8)) for k, league in enumerate(europe.LEAGUES)}


def test_pools_mix_the_three_leagues():
    pools = europe.draw_pools(RANKED, random.Random(0))
    assert len(pools) == 4 and all(len(clubs) == 6 for clubs in pools.values())
    league_of = {club: league for league, clubs in RANKED.items() for club in clubs}
    for clubs in pools.values():
        assert Counter(league_of[c] for c in clubs) == dict.fromkeys(europe.LEAGUES, 2)
        # Un bien classé et un moins bien classé de chaque championnat : 1 avec 8, 2 avec 7...
        for league in europe.LEAGUES:
            ranks = sorted(RANKED[league].index(c) for c in clubs if league_of[c] == league)
            assert sum(ranks) == 7


def test_each_club_plays_four_pool_games_two_at_home():
    pools = europe.draw_pools(RANKED, random.Random(1))
    fixtures = europe.pool_fixtures(pools, europe.pool_dates(2026))
    games = Counter(c for m in fixtures for c in (m.home_club_id, m.away_club_id))
    hosted = Counter(m.home_club_id for m in fixtures)
    assert set(games.values()) == {4} and set(hosted.values()) == {2}
    assert {m.date for m in fixtures} == set(europe.pool_dates(2026))
    # Jamais deux fois la même affiche.
    assert len({frozenset((m.home_club_id, m.away_club_id)) for m in fixtures}) == len(fixtures)


def test_the_leagues_leave_the_cup_weekends_free():
    for year in (2026, 2027, 2028):
        cup = set(europe.pool_dates(year))
        cup |= {europe.knockout_date(year, stage) for stage in europe.KNOCKOUT}
        for code in europe.LEAGUES:
            league = league_config(code)
            regular, playoffs = season_dates(year, 26, league.start, league.breaks)
            assert not cup & set(regular), (year, code)


def test_the_cup_runs_from_the_pools_to_the_final():
    clubs = {i: make_club(i, 10 + i % 5, seed=i) for i in range(1, 25)}
    pools = europe.draw_pools(RANKED, random.Random(2))
    matches = europe.pool_fixtures(pools, europe.pool_dates(2026))
    rng = random.Random(3)

    def play(round_matches):
        for m in round_matches:
            result = simulate_match(
                clubs[m.home_club_id], clubs[m.away_club_id], rng=rng, knockout=m.stage.is_playoff
            )
            m.home_score, m.away_score, m.events = (
                result.home_score,
                result.away_score,
                result.events,
            )

    assert europe.next_round(2026, pools, matches) == []  # poules pas jouées
    play(matches)
    stages = []
    while upcoming := europe.next_round(2026, pools, matches):
        stages.append((upcoming[0].stage, len(upcoming)))
        play(upcoming)
        matches += upcoming
    assert stages == [(Stage.QUARTER, 4), (Stage.SEMI, 2), (Stage.FINAL, 1)]
    final = matches[-1]
    assert final.neutral and europe.champion(pools, matches) in (
        final.home_club_id,
        final.away_club_id,
    )
    # Les quarts opposent les têtes de série 1 à 8, chez la meilleure.
    order = europe.seeds(pools, matches)
    quarters = [m for m in matches if m.stage == Stage.QUARTER]
    assert [(m.home_club_id, m.away_club_id) for m in quarters] == [
        (order[i], order[7 - i]) for i in range(4)
    ]


def test_no_cup_without_the_three_leagues(manager):
    assert manager.get("/seasons/current").json()["cup"] is None


def test_the_cup_is_played_with_the_real_leagues():
    """Dans le monde réel : la coupe est tirée avec la saison, et ses matchs se jouent avec
    les journées des championnats (le club dirigé, du Top 14, est de la coupe)."""
    from fastapi.testclient import TestClient
    from sqlalchemy.orm import sessionmaker

    from api.deps import get_session
    from api.main import app
    from database import seed_if_empty
    from models.orm import Base, ClubRow
    from tests.conftest import test_engine

    engine = test_engine()
    Base.metadata.create_all(engine)
    TestSession = sessionmaker(bind=engine, expire_on_commit=False)
    with TestSession() as session:
        seed_if_empty(session, seed=0, real=True)
        toulouse = next(r.id for r in session.query(ClubRow) if r.name == "Stade Toulousain")

    def override():
        with TestSession() as session:
            yield session

    app.dependency_overrides[get_session] = override
    try:
        client = TestClient(app)
        client.post("/career", json={"manager_name": "Max", "club_id": toulouse})
        cup = client.get("/seasons/current").json()["cup"]
        assert len(cup["pools"]) == 4 and len(cup["matches"]) == 48
        assert any(toulouse in (m["home"]["id"], m["away"]["id"]) for m in cup["matches"])
        # Jusqu'au premier week-end de coupe : le club dirigé s'y arrête, son match se joue
        # en direct comme une journée de championnat.
        for _ in range(20):
            season = client.get("/seasons/current").json()
            if season["next_match"]["cup"]:
                break
            client.post("/seasons/current/play")
        assert season["next_match"]["stage"] == "regular" and season["next_match"]["matchday"] == 1
        assert season["next_matchday"]["date"] > season["next_match"]["date"]
        live = client.post("/live")
        assert live.status_code == 201 and live.json()["cup"]
        assert toulouse in (live.json()["home"]["club"]["id"], live.json()["away"]["club"]["id"])
        finished = client.post("/live/finish").json()
        assert finished["played"]["cup"] and len(finished["played"]["matches"]) == 12
        # Le week-end suivant est aussi de coupe : ses douze affiches, puis la reprise du Top 14.
        assert finished["season"]["next_match"]["cup"]
        assert finished["season"]["next_match"]["matchday"] == 2
        second = client.post("/seasons/current/play").json()
        assert second["played"]["cup"] and second["played"]["matchday"] == 2
        assert not second["season"]["next_match"]["cup"]
        cup = second["season"]["cup"]
        played = [m for m in cup["matches"] if m["home_score"] is not None]
        assert len(played) == 24 and {m["matchday"] for m in played} == {1, 2}
    finally:
        app.dependency_overrides.clear()
