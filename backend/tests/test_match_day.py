"""Tests de ce qui entoure le jeu d'un match : météo, statistiques des joueurs,
pénalité en touche, capitaine et discipline."""

import datetime
import random

from engine import discipline
from engine.journal import Kind, Person, club_team, suspension_article
from engine.match_engine import (
    LiveMatch,
    PenaltyChoice,
    Tactics,
    captain_of,
    kick_success_probability,
    leadership,
    select_lineup,
    simulate_match,
)
from engine.weather import Weather, climate, forecast
from models import MATCH_STAT_NAMES, Club, EventType, Match, MatchEvent, Position

# --- Météo ---------------------------------------------------------------------------


def test_forecast_is_the_weather_of_the_day():
    club = Club(id=7, name="Club 7")
    day = datetime.date(2026, 1, 10)
    assert forecast(club, day) == forecast(club, day)
    assert forecast(club, None) == Weather.CLEAR  # match amical


def test_climate_follows_the_hemisphere():
    january, july = datetime.date(2027, 1, 9), datetime.date(2027, 7, 10)
    # L'hiver européen est pluvieux, l'été austral sec et parfois chaud.
    assert climate("Leinster Rugby", "urc", january)[Weather.RAIN] > 0.3
    assert climate("Crusaders", "super_rugby", january)[Weather.HEAT] > 0
    assert climate("Crusaders", "super_rugby", july)[Weather.HEAT] == 0
    # Les hauts plateaux sud-africains : un hiver austral plus sec qu'en Nouvelle-Zélande.
    bulls = climate("Bulls", "urc", july)[Weather.RAIN]
    assert bulls < climate("Crusaders", "super_rugby", july)[Weather.RAIN]


def _average(home, away, weather, count=300, **kwargs):
    rng = random.Random(0)
    tries = points = 0
    for _ in range(count):
        match = simulate_match(home, away, rng=rng, weather=weather, **kwargs)
        tries += match.tries_for(home.id) + match.tries_for(away.id)
        points += match.home_score + match.away_score
    return tries / count, points / count


def test_rain_and_wind_change_the_game(even_clubs):
    home, away = even_clubs
    clear_tries, clear_points = _average(home, away, Weather.CLEAR)
    rain_tries, _ = _average(home, away, Weather.RAIN)
    _, wind_points = _average(home, away, Weather.WIND)
    assert rain_tries < clear_tries  # ballon glissant
    assert wind_points < clear_points  # coups de pied au but manqués


def test_wind_spoils_goal_kicks(even_clubs):
    home, away = even_clubs
    live = LiveMatch(home, away, weather=Weather.WIND)
    kicker = max(home.players, key=lambda p: p.kicking)
    assert live._kick_probability(live.home, kicker) < kick_success_probability(kicker.kicking)


def test_heat_drains_energy_faster(even_clubs):
    home, away = even_clubs
    energy = {}
    for weather in (Weather.CLEAR, Weather.HEAT):
        live = LiveMatch(home, away, rng=random.Random(1), weather=weather, auto=())
        live.advance(40)
        energy[weather] = sum(live.home.energy(p) for p in live.home.lineup)
    assert energy[Weather.HEAT] < energy[Weather.CLEAR]


def test_weather_survives_a_saved_live_match(even_clubs):
    home, away = even_clubs
    live = LiveMatch(home, away, rng=random.Random(2), weather=Weather.RAIN)
    live.advance(30)
    resumed = LiveMatch.from_state(home, away, live.to_state())
    assert resumed.weather == Weather.RAIN
    assert resumed.play_to_end() == live.play_to_end()


# --- Statistiques ---------------------------------------------------------------------


def test_every_player_who_played_has_stats(even_clubs):
    home, away = even_clubs
    match = simulate_match(home, away, rng=random.Random(4))
    entered = {e.other_player_id for e in match.events if e.type == EventType.SUBSTITUTION}
    assert set(match.stats) == {*match.home_lineup, *match.away_lineup, *entered}
    starters = [match.stats[i] for i in match.home_lineup]
    assert all(1 <= line.minutes <= 80 for line in starters)
    assert all(1 <= line.rating <= 10 for line in match.stats.values())


def test_stats_look_like_rugby(even_clubs):
    home, away = even_clubs
    rng = random.Random(5)
    totals = dict.fromkeys(MATCH_STAT_NAMES, 0)
    count = 100
    for _ in range(count):
        match = simulate_match(home, away, rng=rng)
        for line in match.stats.values():
            for name in MATCH_STAT_NAMES:
                totals[name] += getattr(line, name)
    per_team = {name: total / count / 2 for name, total in totals.items()}
    assert 100 < per_team["carries"] < 160
    assert 100 < per_team["tackles"] < 150
    assert 8 < per_team["missed_tackles"] < 25
    assert 2 < per_team["line_breaks"] < 9
    assert 9 < per_team["lineouts_won"] + per_team["lineout_steals"] < 17


def test_back_rows_tackle_more_than_wings(even_clubs):
    home, away = even_clubs
    rng = random.Random(6)
    by_position = {}
    for _ in range(50):
        match = simulate_match(home, away, rng=rng)
        players = {p.id: p for p in [*home.players, *away.players]}
        for player_id, line in match.stats.items():
            position = players[player_id].position
            by_position.setdefault(position, []).append(line.tackles)
    average = {pos: sum(v) / len(v) for pos, v in by_position.items()}
    assert average["BACK_ROW"] > average["WING"]


def test_live_stats_survive_a_save(even_clubs):
    home, away = even_clubs
    live = LiveMatch(home, away, rng=random.Random(7))
    live.advance(50)
    resumed = LiveMatch.from_state(home, away, live.to_state())
    assert resumed.home.stats == live.home.stats
    assert resumed.play_to_end().stats == live.play_to_end().stats


# --- Pénalité en touche -------------------------------------------------------------------


def test_kicking_to_the_corner_brings_forward_tries(strong_and_weak):
    strong, weak = strong_and_weak
    rng = random.Random(8)
    touch = Tactics(penalties=PenaltyChoice.TOUCH)
    forwards = {p.id for p in strong.players if p.position.is_forward}
    penalty_goals = forward_tries = 0
    for _ in range(200):
        match = simulate_match(strong, weak, rng=rng, home_tactics=touch)
        for event in match.events:
            if event.club_id != strong.id:
                continue
            penalty_goals += event.type == EventType.PENALTY_GOAL
            forward_tries += event.type == EventType.TRY and event.player_id in forwards
    # Les pénalités au but ne viennent plus que des cartons adverses.
    assert penalty_goals < 200
    assert forward_tries > 200


# --- Capitaine ---------------------------------------------------------------------------


def test_leadership_grows_with_experience(even_clubs):
    home, _ = even_clubs
    player = home.players[0]
    player.age = 21
    young = leadership(player)
    player.age = 32
    old = leadership(player)
    assert 0 <= young < old <= 1


def test_captain_is_the_managers_choice_when_he_starts(even_clubs):
    home, _ = even_clubs
    lineup = select_lineup(home)
    assert captain_of(home, lineup) is max(lineup, key=leadership)
    home.captain_id = lineup[5].id
    assert captain_of(home, lineup) is lineup[5]
    home.captain_id = next(p.id for p in home.players if p not in lineup)
    assert captain_of(home, lineup) is max(lineup, key=leadership)


def test_captain_on_the_field_calms_the_team(even_clubs):
    home, away = even_clubs
    live = LiveMatch(home, away, rng=random.Random(9))
    with_captain = live.home.captaincy(1)
    assert with_captain > 0
    live.home.card(live.home.captain(1), 1, red=True)
    assert live.home.captaincy(2) == 0


# --- Discipline ---------------------------------------------------------------------------


def _match_with(events: list[MatchEvent]) -> Match:
    return Match(home_club_id=1, away_club_id=2, home_score=0, away_score=0, events=events)


def test_red_card_brings_a_suspension(even_clubs):
    home, _ = even_clubs
    player = home.players[0]
    players = {p.id: p for p in home.players}
    red = MatchEvent(30, EventType.RED_CARD, home.id, player.id)
    [suspension] = discipline.sanctions(_match_with([red]), players, random.Random(0))
    assert suspension.reason == discipline.Reason.RED_CARD
    assert suspension.matches in discipline.RED_CARD_BANS
    assert player.suspended_matches == suspension.matches
    assert player not in home.available_players(None)
    # Il purge sa peine match après match.
    for _ in range(suspension.matches):
        assert player in discipline.serve(home)
    assert player in home.available_players(None)


def test_a_suspended_youth_serves_with_the_club(even_clubs):
    home, _ = even_clubs
    youth = home.players.pop()
    home.youths.append(youth)
    youth.suspended_matches = 1
    assert discipline.serve(home) == [youth]
    assert not youth.is_suspended


def test_second_yellow_is_one_match(even_clubs):
    home, _ = even_clubs
    player = home.players[0]
    events = [
        MatchEvent(10, EventType.YELLOW_CARD, home.id, player.id),
        MatchEvent(50, EventType.RED_CARD, home.id, player.id),
    ]
    [suspension] = discipline.sanctions(_match_with(events), {player.id: player}, random.Random())
    assert (suspension.matches, suspension.reason) == (1, discipline.Reason.SECOND_YELLOW)
    assert player.yellow_cards == 0  # les jaunes de ce rouge ne comptent pas au cumul


def test_three_yellows_in_a_season_cost_a_match(even_clubs):
    home, _ = even_clubs
    player = home.players[0]
    players = {player.id: player}
    yellow = [MatchEvent(20, EventType.YELLOW_CARD, home.id, player.id)]
    assert discipline.sanctions(_match_with(yellow), players, random.Random()) == []
    assert discipline.sanctions(_match_with(yellow), players, random.Random()) == []
    [suspension] = discipline.sanctions(_match_with(yellow), players, random.Random())
    assert suspension.reason == discipline.Reason.YELLOW_CARDS
    assert (player.suspended_matches, player.yellow_cards) == (1, 0)
    discipline.new_season([player])
    assert player.yellow_cards == 0


def test_suspension_makes_the_news():
    player = Person(1, "Jean Dupont", Position.PROP, 28, 12.0)
    article = suspension_article(5, player, club_team(3, "RC Toulon"), 3, "red_card", None)
    assert article.kind == Kind.DISCIPLINE
    assert "3 matchs" in article.body and "carton rouge" in article.body


def test_suspended_player_is_left_out(even_clubs):
    home, _ = even_clubs
    best = select_lineup(home)[0]
    best.suspended_matches = 2
    assert best not in select_lineup(home)


# --- API ----------------------------------------------------------------------------------


def test_match_detail_has_weather_and_player_stats(manager):
    played = manager.post("/seasons/current/play").json()["played"]["matches"][0]
    match = manager.get(f"/matches/{played['id']}").json()
    assert match["weather"] in {w.value for w in Weather}
    starters = [p for p in match["players"] if p["number"] is not None]
    assert len(starters) == 30
    assert all(p["name"] for p in starters)
    assert sum(p["stats"]["tackles"] for p in match["players"]) > 100
    # Le calendrier annonce le temps des matchs à venir.
    upcoming = manager.get("/seasons/current").json()["next_matchday"]["matches"]
    assert all(m["weather"] for m in upcoming)


def test_player_season_stats_count_tackles(manager):
    manager.post("/seasons/current/play")
    club = manager.get("/clubs/3").json()
    starter = club["strength"]["lineup_ids"][0]
    season = manager.get(f"/players/{starter}").json()["season"]
    assert season["matches"] >= 1
    assert season["minutes"] > 0
    assert season["rating"] is not None


def test_manager_picks_the_captain(manager):
    club = manager.get("/clubs/3").json()
    assert club["strength"]["captain_id"] in club["strength"]["lineup_ids"]
    chosen = club["strength"]["lineup_ids"][3]
    club = manager.put("/clubs/3/captain", json={"player_id": chosen}).json()
    assert (club["captain_choice"], club["strength"]["captain_id"]) == (chosen, chosen)
    stranger = manager.get("/clubs/4").json()["players"][0]["id"]
    assert manager.put("/clubs/3/captain", json={"player_id": stranger}).status_code == 400
    assert (
        manager.put("/clubs/3/captain", json={"player_id": None}).json()["captain_choice"] is None
    )
    assert manager.put("/clubs/4/captain", json={"player_id": None}).status_code == 403


def test_live_match_shows_weather_captain_and_stats(manager):
    live = manager.post("/live").json()
    assert live["weather"] in {w.value for w in Weather}
    mine = live["home"] if live["home"]["club"]["id"] == 3 else live["away"]
    assert mine["captain_id"] in [p["id"] for p in mine["players"][:15]]
    live = manager.post("/live/advance", json={"minutes": 20}).json()
    mine = live["home"] if live["home"]["club"]["id"] == 3 else live["away"]
    starters = [p for p in mine["players"] if p["since"] == 0]
    assert sum(p["stats"]["carries"] + p["stats"]["tackles"] for p in starters) > 0
    bench = [p for p in mine["players"] if p["status"] == "bench"]
    assert all(p["stats"] is None for p in bench)
