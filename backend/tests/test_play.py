"""Tests de ce que joue chaque minute (`new_play`), que le terrain 2D du match en direct
montre : en raccord avec les statistiques et le score, sans changer le match."""

import random

from engine.match_engine import PHASES_PER_MINUTE, LiveMatch, PenaltyOption
from models import EventType
from tests.conftest import make_club


def _minutes(seed: int = 4, minutes: int = 80) -> list[tuple[LiveMatch, dict]]:
    """Le match minute par minute, avec ce que chacune a joué."""
    live = LiveMatch(make_club(1, 13, seed=1), make_club(2, 11, seed=2), rng=random.Random(seed))
    plays = []
    for _ in range(minutes):
        live.step()
        plays.append(live.play)
    return live, plays


def test_each_minute_tells_its_phases_and_set_pieces():
    live, plays = _minutes()
    assert [play["minute"] for play in plays] == list(range(1, 81))
    players = {**live.home.players(), **live.away.players()}
    carries = 0
    breaks = 0
    for play in plays:
        assert len(play["phases"]) == PHASES_PER_MINUTE
        for phase in play["phases"]:
            side = live.side(phase["club_id"])
            assert phase["carrier_id"] in side.players()
            assert phase["tackler_id"] in live.opponent(side).players()
            assert phase["result"] in {"tackled", "turnover", "missed", "break"}
            if phase["result"] == "turnover":
                assert phase["other_id"] in live.opponent(side).players()
            carries += 1
            breaks += phase["result"] == "break"
        if play["lineout"]:
            assert play["lineout"]["jumper_id"] in players
            assert play["lineout"]["won_by"] in {1, 2}
    # Les mêmes temps de jeu que les statistiques des joueurs.
    stats = [line for side in live.sides for line in side.stats.values()]
    assert carries == sum(line.get("carries", 0) for line in stats)
    assert breaks == sum(line.get("line_breaks", 0) for line in stats)


def test_a_try_minute_tells_its_chance():
    live, plays = _minutes(seed=11)
    tries = {(e.minute, e.club_id) for e in live.events if e.type == EventType.TRY}
    assert tries
    for minute, club_id in tries:
        play = plays[minute - 1]
        # Un essai vient d'une action dangereuse, à la main ou sur pénalité jouée.
        assert play["chance"]["club_id"] == club_id
        assert play["chance"]["result"] in {"try", "penalty"}
        if play["chance"]["result"] == "penalty":
            assert play["penalty"]["option"] != PenaltyOption.KICK.value


def test_the_play_survives_a_saved_live_match():
    home, away = make_club(1, 12, seed=1), make_club(2, 12, seed=2)
    live = LiveMatch(home, away, rng=random.Random(3))
    assert live.play is None
    live.advance(12)
    resumed = LiveMatch.from_state(home, away, live.to_state())
    assert resumed.play == live.play and resumed.play["minute"] == 12
    # Un match commencé avant le terrain 2D : rien à montrer jusqu'à la minute suivante.
    state = live.to_state()
    del state["play"]
    resumed = LiveMatch.from_state(home, away, state)
    assert resumed.play is None
    resumed.step()
    assert resumed.play["minute"] == 13


def test_the_crunch_waits_with_its_penalty_then_tells_how_it_was_played():
    home, away = make_club(1, 12, seed=1), make_club(2, 12, seed=2)
    for seed in range(60):
        live = LiveMatch(home, away, rng=random.Random(seed), auto={2})
        live.advance(80)
        if live.crunch is not None:
            break
    else:
        raise AssertionError("aucun choix crucial en 60 matchs")
    assert live.play["chance"] == {**live.play["chance"], "club_id": 1, "result": "crunch"}
    live.decide(1, PenaltyOption.SCRUM)
    assert live.play["penalty"] == {"club_id": 1, "option": "scrum"}


def test_the_live_payload_carries_the_play(manager):
    assert manager.post("/live").json()["play"] is None  # avant le coup d'envoi
    live = manager.post("/live/advance", json={"minutes": 3}).json()
    assert live["play"]["minute"] == 3
    assert len(live["play"]["phases"]) == PHASES_PER_MINUTE
    assert {"club_id", "carrier_id", "tackler_id", "result"} <= set(live["play"]["phases"][0])
