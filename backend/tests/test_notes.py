"""Notes de vie du club : moral, cohésion, fraîcheur, direction, supporters."""

import random
from datetime import date, timedelta

import pytest

from engine.board import BoardSeason, Objective, board_confidence, objective_for, should_sack
from engine.cohesion import START as COHESION_START
from engine.cohesion import team_cohesion
from engine.economy import attendance
from engine.form import NEUTRAL_FORM, Form
from engine.freshness import FULL, player_freshness, team_freshness
from engine.match_engine import simulate_match, team_strength
from engine.medical import training_injuries
from engine.morale import NEUTRAL as MORALE_NEUTRAL
from engine.morale import result_change, team_morale
from engine.notes import MAX_NOTE
from engine.supporters import NEUTRAL as FANS_NEUTRAL
from engine.supporters import fan_fervour
from models import Match, Stage
from tests.conftest import make_club

XV = list(range(1, 16))
OTHER_XV = list(range(101, 116))
START = date(2026, 9, 5)


def _match(
    home_score: int,
    away_score: int,
    week: int = 0,
    stage: Stage = Stage.REGULAR,
    home: int = 1,
    away: int = 2,
    home_lineup: list[int] = XV,
) -> Match:
    return Match(
        home_club_id=home,
        away_club_id=away,
        home_score=home_score,
        away_score=away_score,
        stage=stage,
        date=START + timedelta(weeks=week),
        home_lineup=list(home_lineup),
        away_lineup=list(OTHER_XV),
    )


# --- Moral --------------------------------------------------------------------------


def test_results_move_morale():
    assert result_change(20, 10) > 0
    assert result_change(10, 10) == 0
    assert result_change(10, 20) < 0
    # Large victoire > courte victoire ; courte défaite < lourde défaite.
    assert result_change(40, 10) > result_change(20, 10)
    assert result_change(17, 20) > result_change(10, 40)
    # Les phases finales comptent plus.
    assert result_change(20, 10, Stage.FINAL) > result_change(20, 10)


def test_morale_follows_results_and_stays_on_scale():
    assert team_morale(1, []).value == MORALE_NEUTRAL
    matches = [_match(30, 10, week) for week in range(5)]
    assert team_morale(1, matches).value > MORALE_NEUTRAL > team_morale(2, matches).value
    assert team_morale(3, matches).history == []

    streak = [_match(50, 0, week, Stage.FINAL) for week in range(30)]
    assert team_morale(1, streak).value <= MAX_NOTE


# --- Cohésion -----------------------------------------------------------------------


def test_stable_lineup_builds_cohesion_and_changes_break_it():
    stable = [_match(20, 20, week) for week in range(10)]
    assert team_cohesion(1, stable).value > COHESION_START

    # Un XV totalement différent d'une semaine à l'autre.
    churn = [
        _match(20, 20, week, home_lineup=XV if week % 2 else list(range(201, 216)))
        for week in range(10)
    ]
    assert team_cohesion(1, churn).value < COHESION_START


# --- Fraîcheur ----------------------------------------------------------------------


def test_player_tires_with_matches_and_recovers_with_rest():
    weekly = [START + timedelta(weeks=w) for w in range(6)]
    tired = player_freshness(weekly, START + timedelta(weeks=6), rate=0.11)
    rested = player_freshness(weekly, START + timedelta(weeks=9), rate=0.11)
    assert 10 < tired < 15
    assert tired < rested < FULL
    assert player_freshness([], START, rate=0.11) == FULL
    # Un meilleur préparateur physique fait mieux récupérer.
    assert player_freshness(weekly, START + timedelta(weeks=6), rate=0.16) > tired


def test_team_freshness_is_measured_before_each_match():
    matches = [_match(20, 10, week) for week in range(4)]
    note = team_freshness(1, matches, XV, START + timedelta(weeks=4))
    assert note.history[0].value == FULL  # premier match : personne n'a encore joué
    assert note.history[-1].value < FULL
    # Le XV probable n'ayant jamais joué est frais.
    assert team_freshness(1, matches, list(range(301, 316)), START).value == FULL


# --- Direction ----------------------------------------------------------------------


def test_objective_depends_on_expected_rank():
    assert objective_for(1, 14).label == "Jouer le titre"
    assert objective_for(5, 14).target_rank == 6
    assert objective_for(9, 14).label == "Milieu de tableau"
    assert objective_for(14, 14).label == "Maintien"


def _league(club_one_wins: bool) -> list[Match]:
    """Quatre clubs, club 1 gagne (ou perd) tous ses matchs."""
    matches = []
    for week, opponent in enumerate([2, 3, 4, 2, 3, 4]):
        score = (30, 10) if club_one_wins else (10, 30)
        matches.append(_match(*score, week, home=1, away=opponent))
    return matches


def test_board_rewards_beating_the_objective():
    survival = Objective("Maintien", 3)
    title = Objective("Jouer le titre", 1)
    winning = board_confidence(1, [BoardSeason([1, 2, 3, 4], _league(True), survival)])
    losing = board_confidence(1, [BoardSeason([1, 2, 3, 4], _league(False), title)])
    assert winning.value > 12 > losing.value
    assert len(winning.history) == 6


def test_board_dislikes_debt():
    season = [BoardSeason([1, 2, 3, 4], _league(True), Objective("Phases finales", 2))]
    healthy = board_confidence(1, season, balance_on=lambda day: 1_000_000)
    in_debt = board_confidence(1, season, balance_on=lambda day: -1)
    assert in_debt.value < healthy.value


# --- Supporters ---------------------------------------------------------------------


def test_home_defeats_hurt_more_than_away_ones():
    home_loss = fan_fervour(1, [[_match(10, 30)]])
    away_loss = fan_fervour(2, [[_match(30, 10)]])
    assert home_loss.value < away_loss.value < FANS_NEUTRAL


def test_fervour_has_memory_across_seasons():
    great_season = [_match(30, 10, week) for week in range(10)]
    after = fan_fervour(1, [great_season, []])
    assert after.value > FANS_NEUTRAL  # l'intersaison n'efface qu'une partie


# --- API ----------------------------------------------------------------------------


def test_club_notes_endpoint(manager):
    notes = manager.get("/clubs/3/notes").json()
    assert {"morale", "cohesion", "freshness", "board", "supporters", "objective"} <= set(notes)
    assert notes["sack_threshold"] < notes["sack_warning"]
    form = notes["form"]
    assert form["total"] == pytest.approx(form["morale"] + form["cohesion"] + form["freshness"])
    assert notes["morale"] == {"value": MORALE_NEUTRAL, "history": []}
    assert notes["objective"]["target_rank"] >= notes["objective"]["expected_rank"]

    manager.post("/seasons/current/play")
    notes = manager.get("/clubs/3/notes").json()
    for key in ("morale", "cohesion", "freshness", "board", "supporters"):
        assert len(notes[key]["history"]) == 1, key
        assert 0 <= notes[key]["value"] <= 20
        step = notes[key]["history"][0]
        assert step["result"] in {"V", "N", "D"}
        assert step["opponent"]["id"] != 3
    # Après un match, le XV probable de la journée suivante est entamé.
    assert notes["freshness"]["value"] < 20


def test_club_notes_unknown_club(client):
    assert client.get("/clubs/999/notes").status_code == 404


# --- Effets sur le jeu --------------------------------------------------------------


def test_form_scales_collective_ratings(even_clubs):
    club, _ = even_clubs
    neutral = team_strength(club)
    assert NEUTRAL_FORM.factor([p.id for p in neutral.lineup]) == 1
    great = Form(morale=20, cohesion=20, freshness={p.id: 20 for p in club.players})
    awful = Form(morale=2, cohesion=4, freshness={p.id: 6 for p in club.players})
    assert (
        team_strength(club, form=great).attack
        > neutral.attack
        > team_strength(club, form=awful).attack
    )
    assert team_strength(club, form=great).kicker == neutral.kicker


def test_form_changes_results(even_clubs):
    home, away = even_clubs
    great = Form(morale=20, cohesion=20, freshness={p.id: 20 for p in home.players})
    awful = Form(morale=2, cohesion=4, freshness={p.id: 6 for p in home.players})

    def home_wins(form: Form) -> int:
        rng = random.Random(7)
        matches = [simulate_match(home, away, rng=rng, home_form=form) for _ in range(300)]
        return sum(m.home_score > m.away_score for m in matches)

    assert home_wins(great) > home_wins(NEUTRAL_FORM) > home_wins(awful)


def test_tired_players_get_injured_more(even_clubs):
    club, _ = even_clubs
    player = club.players[0]
    assert Form(freshness={player.id: 4}).injury_weight(player) > 1
    assert Form(freshness={player.id: 20}).injury_weight(player) < 1

    def count(tired: bool) -> int:
        rng = random.Random(3)
        total = 0
        for seed in range(150):
            fresh_club = make_club(1, level=12, seed=seed)
            form = Form(freshness={p.id: 4 if tired else 16 for p in fresh_club.players})
            total += len(training_injuries(fresh_club, START, rng, risk=form.injury_weight))
        return total

    assert count(tired=True) > count(tired=False)


def test_fervour_fills_the_stadium():
    hot = attendance(10_000, 7, 14, rng=random.Random(1), fervour=20)
    cold = attendance(10_000, 7, 14, rng=random.Random(1), fervour=0)
    assert hot > attendance(10_000, 7, 14, rng=random.Random(1)) > cold
    assert attendance(10_000, 7, 14, playoff=True, fervour=0) == 10_000


def test_sack_needs_low_confidence_after_a_third_of_the_season():
    assert not should_sack(2.0, 5, 26)
    assert should_sack(2.0, 9, 26)
    assert not should_sack(8.0, 20, 26)


def test_dismissal_ends_the_career(manager, monkeypatch):
    monkeypatch.setattr("api.routers.seasons.should_sack", lambda *args: True)
    result = manager.post("/seasons/current/play").json()
    assert result["dismissal"]["club_id"] == 3
    assert manager.get("/career").status_code == 404
    assert manager.get("/career/dismissal").json()["club_name"] == result["dismissal"]["club_name"]

    # Le monde continue : on reprend un autre club, le limogeage est oublié.
    assert manager.post("/career", json={"manager_name": "Bis", "club_id": 4}).status_code == 201
    assert manager.get("/career/dismissal").json() is None
