"""Affaires entre deux matchs : catalogue, tirage, effets sur les notes, cycle de l'API."""

import random
from datetime import date, timedelta

import pytest

import api.affairs
from engine.affairs import (
    CATALOGUE,
    SCENARIOS,
    Draft,
    Fixture,
    PastChoice,
    PlayerInfo,
    Result,
    Situation,
    StaffInfo,
    draw,
    follow_up,
    render,
)
from engine.freshness import FULL, MATCH_COST, player_freshness
from engine.match_engine import select_lineup
from engine.morale import NEUTRAL as MORALE_NEUTRAL
from engine.morale import team_morale
from engine.notes import Boost
from models import Match, Position, StaffRole
from tests.conftest import make_club

DAY = date(2026, 12, 12)


def _player(pid: int, position: Position = Position.WING, **kwargs) -> PlayerInfo:
    values = {"name": f"Joueur {pid}", "age": 27, "overall": 12.0} | kwargs
    return PlayerInfo(id=pid, position=position, **values)


def _situation(**kwargs) -> Situation:
    """Un club où presque tout peut arriver."""
    players = [
        _player(1, Position.FLY_HALF, overall=15, starts=10, years_left=1),
        _player(2, Position.FLY_HALF, overall=13, starts=1),
        _player(3, Position.LOCK, age=34, overall=11, starts=9),
        _player(4, Position.LOCK, age=22, overall=10, injured_weeks=8),
        _player(5, Position.PROP, age=29, overall=12, starts=10),
    ]
    values = {
        "club": "Stade Test",
        "day": DAY,
        "rank": 11,
        "target_rank": 6,
        "played": 10,
        "last": Result("Racing Test", 10, 40, at_home=True),
        "streak": -3,
        "next": Fixture("Toulouse Test", 1, at_home=False),
        "notes": {"morale": 8, "cohesion": 8, "freshness": 12, "board": 6, "supporters": 6},
        "balance": -1000,
        "academy_level": 3,
        "players": players,
        "youths": [_player(50, Position.CENTRE, age=19, overall=11, youth=True)],
        "staff": [StaffInfo(70, "Paul Prépa", StaffRole.FITNESS_COACH, 5)],
        "matches_since_affair": 3,
        "past": [
            PastChoice("night_out", "look_away", 5, DAY - timedelta(days=60), "Joueur 5"),
            PastChoice("press_star_rumour", "not_for_sale", 99, DAY - timedelta(days=60), "Parti"),
        ],
    }
    return Situation(**(values | kwargs))


# --- Catalogue ----------------------------------------------------------------------------


def test_scenario_keys_are_unique_and_options_too():
    assert len(CATALOGUE) == len(SCENARIOS) >= 39
    for scenario in SCENARIOS:
        keys = [o.key for o in scenario.options]
        assert len(keys) == len(set(keys)), scenario.key


def test_every_triggered_scenario_renders():
    """Chaque texte et chaque réponse se remplissent avec le contexte de leur trigger."""
    rng = random.Random(1)
    happy = {"morale": 15, "cohesion": 15, "freshness": 16, "board": 17, "supporters": 15}
    situations = [
        _situation(),
        _situation(streak=4, last=Result("X", 40, 10, True), notes=happy),
        _situation(last=Result("X", 20, 25, True)),
    ]
    fired = set()
    for s in situations:
        for scenario in SCENARIOS:
            if scenario.trigger is None:
                continue
            ctx = scenario.trigger(s, rng)
            if ctx is None:
                continue
            fired.add(scenario.key)
            render(scenario.text, ctx)
            for option in scenario.options:
                render(option.label, ctx)
                render(option.outcome, ctx)
    triggered = {s.key for s in SCENARIOS if s.trigger is not None}
    assert triggered - fired == set()


def test_follow_ups_render_with_the_original_context():
    rng = random.Random(1)
    ctx = CATALOGUE["playing_time"].trigger(_situation(), rng)
    result = Result("Brive Test", 20, 25, at_home=True)
    for scenario in SCENARIOS:
        for option in scenario.options:
            if option.promise is None:
                continue
            for key in (option.promise.kept, option.promise.broken):
                if key is not None:
                    draft = follow_up(key, ctx, result)
                    render(draft.scenario.text, draft.context)
                    for follow in draft.scenario.options:
                        render(follow.label, draft.context)
                        render(follow.outcome, draft.context)


def test_unhappy_player_is_a_good_player_who_does_not_start():
    ctx = CATALOGUE["playing_time"].trigger(_situation(), random.Random(0))
    assert ctx["player_id"] == 2
    assert ctx["starts"] == "une seule titularisation" and ctx["played"] == 10


def test_resignation_gamble_depends_on_the_board():
    option = next(o for o in CATALOGUE["board_summons"].options if o.key == "resign")
    rng = random.Random(0)
    trusted = [option.resolve({"board": 9.0}, rng)[0]["board"] for _ in range(400)]
    doubted = [option.resolve({"board": 3.0}, rng)[0]["board"] for _ in range(400)]
    assert sum(v > 0 for v in trusted) > sum(v > 0 for v in doubted)


# --- Tirage -------------------------------------------------------------------------------


def test_broken_word_is_urgent():
    draft = draw(_situation(), random.Random(0))
    assert draft.scenario.key == "contradiction"
    assert draft.context["player"] == "Parti"


def test_an_affair_every_two_or_three_matches():
    def drawn(since: int) -> int:
        calm = _situation(past=[], matches_since_affair=since)
        return sum(draw(calm, random.Random(seed)) is not None for seed in range(200))

    assert drawn(0) == drawn(1) == 0
    assert 60 < drawn(2) < 140  # une fois sur deux
    assert drawn(3) == drawn(5) == 200


def test_a_question_is_asked_once_per_season():
    calm = _situation(past=[])
    keys = {draw(calm, random.Random(seed)).scenario.key for seed in range(200)}
    assert {"press_heavy_loss", "press_job_threat", "board_summons", "fans_banner"} <= keys

    asked = [PastChoice(s.key, None, None, DAY - timedelta(days=200)) for s in SCENARIOS]
    assert draw(_situation(past=asked), random.Random(0)) is None
    # Les questions de la saison passée peuvent revenir.
    last_season = [PastChoice(p.scenario, None, None, p.day, this_season=False) for p in asked]
    assert draw(_situation(past=last_season), random.Random(0)) is not None


def test_same_player_is_not_bothered_twice_in_a_row():
    past = [PastChoice("night_out", "fine", 2, DAY - timedelta(days=7))]
    for seed in range(100):
        draft = draw(_situation(past=past), random.Random(seed))
        assert draft.player_id != 2


def test_no_affair_right_after_the_first_matchday(manager):
    assert manager.post("/seasons/current/play").json()["affairs"] == []


def test_no_affair_the_matchday_after_one(manager, monkeypatch):
    real_draw = api.affairs.draw
    _force_draw(monkeypatch, "fans_open_training")
    affair = manager.post("/seasons/current/play").json()["affairs"][0]
    manager.post(f"/affairs/{affair['id']}/answer", json={"choice": "open"})
    monkeypatch.setattr(api.affairs, "draw", real_draw)
    assert manager.post("/seasons/current/play").json()["affairs"] == []


# --- Effets sur les notes -----------------------------------------------------------------


def _win(day: date) -> Match:
    return Match(home_club_id=1, away_club_id=2, home_score=20, away_score=10, date=day)


def test_boost_counts_after_its_day_and_fades_like_the_rest():
    first, second = date(2026, 9, 5), date(2026, 9, 12)
    matches = [_win(first), _win(second)]
    plain = team_morale(1, matches)
    boosted = team_morale(1, matches, [Boost(first, 2.0)])
    # Décidé après le 1er match : il passe par le retour vers la note neutre du 2e.
    assert boosted.history[0].value == plain.history[0].value
    assert boosted.value == pytest.approx(plain.value + 2.0 * 0.75)
    # Décidé après le dernier match : il compte tout de suite, en entier.
    assert team_morale(1, matches, [Boost(second, 1.0)]).value == pytest.approx(plain.value + 1)
    assert team_morale(1, [], [Boost(first, -3.0)]).value == MORALE_NEUTRAL - 3


def test_rest_days_and_extra_training_change_freshness():
    played = date(2026, 9, 5)
    rate = 0.11
    plain = player_freshness([played], played + timedelta(days=7), rate)
    rested = player_freshness([played], played + timedelta(days=7), rate, [Boost(played, 3.0)])
    tired = player_freshness([played], played + timedelta(days=7), rate, [Boost(played, -2.0)])
    assert tired < plain < rested < FULL
    # Le coup de pouce du jour du match compte après lui, pas avant.
    assert player_freshness([played], played + timedelta(days=1), 0, [Boost(played, 3)]) == (
        FULL - MATCH_COST + 3
    )


def test_promised_starter_goes_in_the_xv():
    club = make_club(1, level=12)
    flyhalves = sorted(
        (p for p in club.players if p.position == Position.FLY_HALF), key=lambda p: p.overall
    )
    weakest = flyhalves[0]
    assert weakest not in select_lineup(club)
    club.forced_starters = {weakest.id}
    assert weakest in select_lineup(club)


# --- API ----------------------------------------------------------------------------------


def _force_draw(monkeypatch, key: str, pick=lambda ctx: ctx) -> None:
    """Le prochain tirage sort ce scénario (son trigger, sur la vraie situation)."""

    def fake_draw(situation, rng):
        scenario = CATALOGUE[key]
        ctx = scenario.trigger(situation, random.Random(0))
        return Draft(scenario, pick(ctx)) if ctx is not None else None

    monkeypatch.setattr(api.affairs, "draw", fake_draw)


def test_answer_reveals_effects_and_moves_the_notes(manager, monkeypatch):
    _force_draw(monkeypatch, "hospital_visit")
    played = manager.post("/seasons/current/play").json()
    [affair] = played["affairs"]
    assert affair["title"] == "Visite à l'hôpital"
    assert not affair["answered"] and affair["effects"] == {}

    assert manager.get("/affairs").json()["pending"][0]["id"] == affair["id"]
    before = manager.get("/clubs/3/notes").json()
    answered = manager.post(f"/affairs/{affair['id']}/answer", json={"choice": "go"}).json()
    assert answered["answered"] and answered["choice_label"].startswith("Y aller")
    assert answered["effects"] == {
        "morale": 0.3,
        "cohesion": 0.3,
        "freshness": -0.3,
        "supporters": 0.8,
    }

    after = manager.get("/clubs/3/notes").json()
    for key in ("morale", "cohesion", "supporters"):
        gap = after[key]["value"] - before[key]["value"]
        assert gap == pytest.approx(answered["effects"][key], abs=0.11)
    assert manager.get("/affairs").json()["pending"] == []
    again = manager.post(f"/affairs/{affair['id']}/answer", json={"choice": "go"})
    assert again.status_code == 400


def test_unanswered_affair_is_settled_before_the_next_matchday(manager, monkeypatch):
    _force_draw(monkeypatch, "fans_open_training")
    affair = manager.post("/seasons/current/play").json()["affairs"][0]
    monkeypatch.setattr(api.affairs, "draw", lambda situation, rng: None)
    manager.post("/seasons/current/play")
    settled = manager.get("/affairs").json()["recent"][0]
    assert settled["id"] == affair["id"]
    assert settled["choice"] is None and settled["effects"] == {"supporters": -0.5}


def test_money_goes_through_the_ledger(manager, monkeypatch):
    _force_draw(monkeypatch, "team_building")
    affair = manager.post("/seasons/current/play").json()["affairs"][0]
    balance = manager.get("/finances").json()["balance"]
    manager.post(f"/affairs/{affair['id']}/answer", json={"choice": "trip"})
    finances = manager.get("/finances").json()
    assert finances["balance"] == balance - 25_000
    assert finances["transactions"][0]["category"] == "affairs"


def test_start_promise_puts_the_player_in_the_xv_then_follows_up(manager, monkeypatch):
    squad = sorted(manager.get("/clubs/3").json()["players"], key=lambda p: p["overall"])
    bench = next(
        p
        for p in squad
        if not p["injury"] and not manager.get(f"/players/{p['id']}").json()["starter"]
    )

    def unhappy_bench_player(situation, rng):
        ctx = CATALOGUE["press_rival_taunt"].trigger(situation, rng)
        ctx |= {"player": bench["name"], "player_id": bench["id"], "position": "centre"}
        ctx |= {"age": bench["age"], "starts": "aucune titularisation", "played": 1}
        return Draft(CATALOGUE["playing_time"], ctx)

    monkeypatch.setattr(api.affairs, "draw", unhappy_bench_player)
    affair = manager.post("/seasons/current/play").json()["affairs"][0]
    answered = manager.post(f"/affairs/{affair['id']}/answer", json={"choice": "promise_start"})
    assert answered.json()["promise"] == "start"

    # Promesse tenue au match suivant (le joueur est imposé dans le XV), puis la suite.
    monkeypatch.setattr(api.affairs, "draw", lambda situation, rng: None)
    played = manager.post("/seasons/current/play").json()
    assert [a["scenario"] for a in played["affairs"]] == ["start_kept"]
    assert manager.get(f"/players/{bench['id']}").json()["season"]["matches"] == 1


def test_sold_player_cannot_be_acted_upon(manager, monkeypatch):
    sold = manager.get("/clubs/3").json()["players"][0]

    def about_sold_player(situation, rng):
        ctx = CATALOGUE["press_rival_taunt"].trigger(situation, rng)
        ctx |= {"player": sold["name"], "player_id": sold["id"], "position": "centre", "age": 30}
        return Draft(CATALOGUE["contract_future"], ctx)

    monkeypatch.setattr(api.affairs, "draw", about_sold_player)
    affair = manager.post("/seasons/current/play").json()["affairs"][0]
    assert manager.post(f"/transfers/sell/{sold['id']}").status_code == 200
    response = manager.post(f"/affairs/{affair['id']}/answer", json={"choice": "extend"})
    assert response.status_code == 400
    assert manager.get("/affairs").json()["pending"][0]["id"] == affair["id"]


def test_affairs_need_a_career(client):
    assert client.get("/affairs").status_code == 404
