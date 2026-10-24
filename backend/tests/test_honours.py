"""Tests du palmarès : trophées de fin de saison, champions, histoire et records."""

import random

from engine.awards import AwardKind, season_awards, season_lines
from engine.match_engine import FORMATION, simulate_match
from tests.conftest import make_club


def _league(rounds: int = 2):
    clubs = [make_club(i, 11 + i % 3, seed=i) for i in range(1, 7)]
    rng = random.Random(0)
    matches = []
    for _ in range(rounds):
        for home in clubs:
            for away in clubs:
                if home is not away:
                    matches.append(simulate_match(home, away, rng=rng))
    players = {p.id: p for club in clubs for p in club.players}
    return matches, players


def test_season_lines_count_matches_points_and_tackles():
    matches, _ = _league(rounds=1)
    lines = season_lines(matches)
    scorer = max(lines, key=lambda pid: lines[pid].points)
    assert lines[scorer].points > 0 and lines[scorer].matches >= 1
    assert sum(line.tackles for line in lines.values()) > 0
    assert all(line.rated for line in lines.values())


def test_each_league_crowns_its_season():
    matches, players = _league()
    awards = season_awards(matches, players)
    kinds = [a.kind for a in awards]
    for kind in (AwardKind.PLAYER, AwardKind.TRIES, AwardKind.POINTS, AwardKind.TACKLES):
        assert kinds.count(kind) == 1
    team = [a for a in awards if a.kind == AwardKind.TEAM]
    assert len(team) == sum(FORMATION.values())
    assert all(players[a.player_id].position == a.position for a in team)
    # Le joueur de la saison a la meilleure note moyenne de ceux qui ont assez joué.
    lines = season_lines(matches)
    best = next(a for a in awards if a.kind == AwardKind.PLAYER)
    assert lines[best.player_id].rating == max(
        line.rating for pid, line in lines.items() if line.matches >= 0.5 * 20
    )
    # Les mêmes matchs donnent les mêmes trophées.
    assert season_awards(matches, players) == awards


def test_the_revelation_is_young():
    matches, players = _league()
    for player in players.values():
        player.age = 25
    some = next(iter(players.values()))
    some.age = 19
    awards = season_awards(matches, players)
    revelation = [a for a in awards if a.kind == AwardKind.REVELATION]
    assert all(players[a.player_id].age <= 21 for a in revelation)


def test_retired_players_do_not_compete():
    matches, players = _league(rounds=1)
    awards = season_awards(matches, players)
    winner = next(a for a in awards if a.kind == AwardKind.TRIES).player_id
    del players[winner]
    assert winner not in {a.player_id for a in season_awards(matches, players)}


# --- API -------------------------------------------------------------------------------


def test_honours_follow_the_seasons(manager):
    honours = manager.get("/honours").json()
    assert honours["club"]["id"] == 3
    assert honours["club_history"][0]["playoffs"] == "running"
    for _ in range(21):  # toute la saison, phases finales comprises
        manager.post("/seasons/current/play")
    honours = manager.get("/honours").json()
    league = next(lg for lg in honours["leagues"] if lg["code"] == honours["league"])
    season = league["seasons"][0]
    assert season["champion"] is not None and season["runner_up"] is not None
    assert league["titles"][0]["titles"] == 1
    assert {a["kind"] for a in season["awards"]} >= {"player", "tries", "points", "team"}
    assert honours["records"]["tries"] and honours["records"]["biggest_wins"]

    # L'intersaison inscrit les trophées : ils restent, même si des lauréats raccrochent.
    manager.post("/seasons/next")
    honours = manager.get("/honours").json()
    league = next(lg for lg in honours["leagues"] if lg["code"] == honours["league"])
    past = next(s for s in league["seasons"] if s["year"] == season["year"])
    assert [a["player_id"] for a in past["awards"]] == [a["player_id"] for a in season["awards"]]
    assert [s["year"] for s in honours["club_history"]] == [season["year"] + 1, season["year"]]
