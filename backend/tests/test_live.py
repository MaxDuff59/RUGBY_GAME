"""Le match en direct : moteur minute par minute (sans base) et routes `/live`."""

import random

import pytest

from engine.match_engine import (
    BENCH_SIZE,
    MATCH_MINUTES,
    MAX_SUBSTITUTIONS,
    RATING_MAX,
    RATING_MIN,
    SIN_BIN_MINUTES,
    Defence,
    GamePlan,
    LiveMatch,
    PenaltyChoice,
    Tactics,
    select_bench,
    select_lineup,
    simulate_match,
)
from models import EventType, Position

# --- Moteur ------------------------------------------------------------------------------


def test_bench_has_eight_fresh_players(even_clubs):
    club, _ = even_clubs
    lineup = select_lineup(club)
    bench = select_bench(club, lineup)
    assert len(bench) == BENCH_SIZE
    assert not {p.id for p in bench} & {p.id for p in lineup}
    # Le banc couvre la première ligne et la charnière.
    positions = [p.position for p in bench]
    assert positions.count(Position.PROP) == 2
    assert Position.HOOKER in positions
    assert Position.SCRUM_HALF in positions


def test_minute_by_minute_equals_one_shot(even_clubs):
    home, away = even_clubs
    one_shot = simulate_match(home, away, rng=random.Random(11))
    live = LiveMatch(home, away, rng=random.Random(11))
    while not live.finished:
        live.advance(1)
    assert live.minute == MATCH_MINUTES
    assert live.result() == one_shot


def test_saved_state_resumes_exactly(even_clubs):
    home, away = even_clubs
    reference = simulate_match(home, away, rng=random.Random(8), knockout=True)
    live = LiveMatch(home, away, rng=random.Random(8), knockout=True)
    live.advance(37)
    restored = LiveMatch.from_state(home, away, live.to_state())
    assert restored.minute == 37
    assert restored.play_to_end() == reference


def test_substitutions_cards_and_ratings(even_clubs):
    home, away = even_clubs
    rng = random.Random(0)
    yellows = reds = 0
    for _ in range(200):
        live = LiveMatch(home, away, rng=rng)
        live.play_to_end()
        for side in live.sides:
            subs = [
                e
                for e in live.events
                if e.type == EventType.SUBSTITUTION and e.club_id == side.club.id
            ]
            assert len(subs) <= MAX_SUBSTITUTIONS
            # Un remplaçant n'entre qu'une fois.
            assert len({e.other_player_id for e in subs}) == len(subs)
            # Un joueur sorti ne marque plus.
            for event in live.events:
                if event.club_id == side.club.id and event.player_id in side.off:
                    assert event.minute <= side.off[event.player_id]
            # Les notes restent sur 10 ; seuls ceux qui ont joué en ont une.
            assert all(RATING_MIN <= r <= RATING_MAX for r in side.ratings.values())
            assert set(side.ratings) == set(side.entered_at)
            assert len(side.ratings) >= 15
        yellows += sum(e.type == EventType.YELLOW_CARD for e in live.events)
        reds += sum(e.type == EventType.RED_CARD for e in live.events)
    # ~0,6 jaune et ~0,07 rouge par match.
    assert 60 <= yellows <= 200
    assert reds >= 1


def test_yellow_card_empties_a_place_for_ten_minutes(even_clubs):
    home, away = even_clubs
    rng = random.Random(0)
    seen = False
    for _ in range(100):
        live = LiveMatch(home, away, rng=rng)
        while not live.finished:
            before = len(live.events)
            live.advance(1)
            cards = [e for e in live.events[before:] if e.type == EventType.YELLOW_CARD]
            if cards and live.minute + SIN_BIN_MINUTES < MATCH_MINUTES:
                side = live.side(cards[0].club_id)
                slot = side.slot_of(cards[0].player_id)
                assert not slot.present(live.minute)
                assert slot.absent_until == live.minute + SIN_BIN_MINUTES
                assert side.missing(live.minute) >= 1
                assert slot.present(live.minute + SIN_BIN_MINUTES)
                # La faute donne une pénalité à l'adversaire, à la même minute.
                penalties = [
                    e
                    for e in live.events[before:]
                    if e.type in (EventType.PENALTY_GOAL, EventType.PENALTY_MISSED)
                    and e.club_id != cards[0].club_id
                ]
                assert penalties
                seen = True
                break
        if seen:
            break
    assert seen, "100 matchs devraient bien donner un carton jaune"


def test_manager_substitution_rules(even_clubs):
    home, away = even_clubs
    live = LiveMatch(home, away, rng=random.Random(1), auto={away.id})
    live.advance(20)
    side = live.home
    left_before = side.substitutions_left()  # des blessures ont pu en consommer
    starter = side.slots[0].player
    replacement = next(p for p in side.available_bench() if p.position == Position.PROP)
    event = live.substitute(home.id, starter.id, replacement.id)
    assert event.type == EventType.SUBSTITUTION
    assert event.minute == 20
    assert (event.player_id, event.other_player_id) == (starter.id, replacement.id)
    assert side.slots[0].player is replacement
    assert side.slots[0].position == Position.PROP
    assert side.substitutions_left() == left_before - 1
    assert side.off[starter.id] == 20

    # Le sortant ne revient pas, le remplaçant entré ne « rentre » pas deux fois.
    with pytest.raises(ValueError):
        live.substitute(home.id, replacement.id, starter.id)
    with pytest.raises(ValueError):
        live.substitute(home.id, side.slots[1].player.id, replacement.id)
    # Sans ordre du manager, notre banc ne bouge que sur blessure.
    live.play_to_end()
    ours = [
        e
        for e in live.events
        if e.type == EventType.SUBSTITUTION and e.club_id == home.id and e.minute > 20
    ]
    injured_out = {e.player_id for e in live.events if e.type == EventType.INJURY}
    assert all(e.player_id in injured_out for e in ours)


def test_tactics_change_the_game(even_clubs):
    home, away = even_clubs

    def points_for(tactics: Tactics, count: int = 400) -> tuple[int, int]:
        rng = random.Random(3)
        scored = conceded = 0
        for _ in range(count):
            match = simulate_match(home, away, rng=rng, home_tactics=tactics, neutral=True)
            scored += match.home_score
            conceded += match.away_score
        return scored, conceded

    balanced = points_for(Tactics())
    hands = points_for(Tactics(game_plan=GamePlan.HANDS))
    assert hands[0] > balanced[0]  # plus d'essais marqués
    assert hands[1] > balanced[1]  # ... et encaissés

    # Agressif : plus de cartons.
    def cards(defence: Defence) -> int:
        rng = random.Random(4)
        total = 0
        for _ in range(300):
            match = simulate_match(home, away, rng=rng, home_tactics=Tactics(defence=defence))
            total += sum(
                e.type in (EventType.YELLOW_CARD, EventType.RED_CARD) and e.club_id == home.id
                for e in match.events
            )
        return total

    assert cards(Defence.AGGRESSIVE) > cards(Defence.CAUTIOUS)

    # Pénalités jouées à la main : nos pénalités au pied ne viennent plus que des cartons adverses.
    rng = random.Random(5)
    for _ in range(50):
        match = simulate_match(
            home, away, rng=rng, home_tactics=Tactics(penalties=PenaltyChoice.PLAY)
        )
        kicks = [
            e
            for e in match.events
            if e.club_id == home.id and e.type in (EventType.PENALTY_GOAL, EventType.PENALTY_MISSED)
        ]
        cards_against = [
            e
            for e in match.events
            if e.club_id == away.id and e.type in (EventType.YELLOW_CARD, EventType.RED_CARD)
        ]
        assert len(kicks) <= len(cards_against)


# --- API -------------------------------------------------------------------------------------


def _my_side(live: dict) -> dict:
    return live["home"] if live["home"]["club"]["id"] == live["my_club_id"] else live["away"]


def test_live_match_flow(manager):
    assert manager.get("/live").status_code == 404

    started = manager.post("/live")
    assert started.status_code == 201
    live = started.json()
    assert live["my_club_id"] == 3
    assert live["minute"] == 0
    assert live["last_minute"] == 80
    assert live["half_time"] == 40
    assert live["finished"] is False
    mine = _my_side(live)
    assert len(mine["players"]) == 15 + BENCH_SIZE
    assert [p["number"] for p in mine["players"]] == list(range(1, 24))
    assert sorted(p["slot_number"] for p in mine["players"] if p["status"] == "field") == list(
        range(1, 16)
    )
    assert all(p["status"] == "bench" and p["rating"] is None for p in mine["players"][15:])
    assert mine["tactics"] == {"game_plan": "balanced", "defence": "normal", "penalties": "kick"}
    assert mine["substitutions_left"] == MAX_SUBSTITUTIONS

    # Relancer ne redémarre pas : on reprend le même match.
    assert manager.post("/live").json()["match_id"] == live["match_id"]

    # Dix minutes de jeu, sauvegardées entre deux requêtes.
    live = manager.post("/live/advance", json={"minutes": 10}).json()
    assert live["minute"] == 10
    assert all(e["minute"] <= 10 for e in live["events"])
    assert manager.get("/live").json()["minute"] == 10
    for side in (live["home"], live["away"]):
        assert side["score"] == sum(
            e["points"] for e in live["events"] if e["club_id"] == side["club"]["id"]
        )

    # Tactique : changement partiel.
    live = manager.post("/live/tactics", json={"game_plan": "hands"}).json()
    assert _my_side(live)["tactics"] == {
        "game_plan": "hands",
        "defence": "normal",
        "penalties": "kick",
    }

    # Remplacement : un titulaire sort, un remplaçant entre à sa place.
    mine = _my_side(live)
    starter = next(p for p in mine["players"] if p["status"] == "field")
    bench = next(p for p in mine["players"] if p["status"] == "bench")
    live = manager.post(
        "/live/substitute", json={"player_out": starter["id"], "player_in": bench["id"]}
    ).json()
    mine = _my_side(live)
    by_id = {p["id"]: p for p in mine["players"]}
    assert by_id[starter["id"]]["status"] == "replaced"
    assert by_id[starter["id"]]["until"] == 10
    assert by_id[bench["id"]]["status"] == "field"
    assert by_id[bench["id"]]["slot_number"] == starter["slot_number"]
    assert by_id[bench["id"]]["since"] == 10
    assert mine["substitutions_left"] == MAX_SUBSTITUTIONS - 1
    substitution = live["events"][-1]
    assert substitution["type"] == "substitution"
    assert substitution["player_name"] == starter["name"]
    assert substitution["other_player_name"] == bench["name"]
    # Le même remplaçant ne peut pas entrer deux fois.
    refused = manager.post(
        "/live/substitute", json={"player_out": starter["id"], "player_in": bench["id"]}
    )
    assert refused.status_code == 400

    # Jusqu'au bout, puis la journée se termine avec ce résultat.
    live = manager.post("/live/advance", json={"minutes": 100}).json()
    assert live["finished"] is True
    assert live["minute"] == 80
    assert manager.post("/live/advance", json={"minutes": 1}).status_code == 400

    played = manager.post("/live/finish")
    assert played.status_code == 200
    result = played.json()
    my_match = next(
        m for m in result["played"]["matches"] if 3 in (m["home"]["id"], m["away"]["id"])
    )
    assert my_match["id"] == live["match_id"]
    assert (my_match["home_score"], my_match["away_score"]) == (
        live["home"]["score"],
        live["away"]["score"],
    )
    assert len(result["played"]["matches"]) == 5
    assert result["season"]["next_matchday"]["matchday"] == 2
    assert manager.get("/live").status_code == 404

    detail = manager.get(f"/matches/{live['match_id']}").json()
    assert len(detail["events"]) == len(live["events"])


def test_simulating_the_matchday_finishes_the_live_match(manager):
    manager.post("/live")
    live = manager.post("/live/advance", json={"minutes": 25}).json()
    result = manager.post("/seasons/current/play").json()
    my_match = next(
        m for m in result["played"]["matches"] if 3 in (m["home"]["id"], m["away"]["id"])
    )
    assert my_match["id"] == live["match_id"]
    assert my_match["home_score"] is not None
    # Les 25 premières minutes comptent telles quelles.
    detail = manager.get(f"/matches/{live['match_id']}").json()
    assert detail["events"][: len(live["events"])] == [
        {k: e[k] for k in ("minute", "type", "club_id", "player_id", "points")}
        for e in live["events"]
    ]
    assert manager.get("/live").status_code == 404


def test_live_needs_a_career_and_a_match(client):
    assert client.post("/live").status_code == 404
    assert client.get("/live").status_code == 404


def test_stamina_keeps_energy_longer(even_clubs):
    home, away = even_clubs
    live = LiveMatch(home, away, rng=random.Random(2), auto=set())
    tough, frail = live.home.slots[0].player, live.home.slots[1].player
    tough.stamina, frail.stamina = 20, 4
    bench = live.home.available_bench()[0]
    at_start = live.home.energy(bench)
    live.advance(40)
    assert live.home.energy(tough) > live.home.energy(frail)
    # Un remplaçant qui n'est pas entré garde son énergie de départ.
    assert live.home.energy(bench) == at_start
    live.play_to_end()
    assert live.home.energy(tough) > live.home.energy(frail)
    if frail.id not in live.home.off:
        assert live.home.energy(frail) == 0.0  # vidé avant la fin


def test_short_handed_players_tire_faster(even_clubs):
    home, away = even_clubs
    live = LiveMatch(home, away, rng=random.Random(0))
    live.advance(10)
    side = live.home
    assert side.effort(10) == 1.0
    victim = side.slots[3].player
    side.card(victim, 10, red=False)
    assert side.missing(11) == 1
    assert side.effort(11) == 1 + 0.25
    side.tactics = Tactics(defence=Defence.AGGRESSIVE)
    assert side.effort(11) > 1.25
    # Le joueur au banc des pénalités ne dépense rien pendant son absence.
    before = side.energy(victim)
    live.advance(5)
    assert side.energy(victim) == before
