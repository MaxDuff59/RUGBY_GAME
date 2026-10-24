"""Tests de la semaine d'entraînement : rythme et thème."""

import datetime
import random

from engine.coaching import coaching
from engine.form import Form
from engine.matchday import training_week
from engine.training import Intensity, Plan, Theme, plan_of
from tests.conftest import make_club

DAY = datetime.date(2026, 10, 10)


def _club(intensity: str = "normal", theme: str = "none", seed: int = 1):
    club = make_club(1, 12, seed=seed)
    club.training_intensity, club.training_theme = intensity, theme
    return club


def test_an_ai_club_trains_normally_without_a_theme():
    plan = plan_of(make_club(2, 12))
    assert plan == Plan(Intensity.NORMAL, Theme.NONE)
    assert plan.multipliers() == {"forwards": 1.0, "attack": 1.0, "defence": 1.0}


def test_intensity_trades_freshness_for_progress():
    light, intense = Plan(Intensity.LIGHT).rhythm, Plan(Intensity.INTENSE).rhythm
    assert light.pace < 1 < intense.pace
    assert light.freshness > 0 > intense.freshness
    assert light.injuries < 1 < intense.injuries


def test_an_intense_week_brings_more_training_injuries():
    def injuries(intensity: str) -> int:
        rng, count = random.Random(0), 0
        for seed in range(40):
            club = _club(intensity, seed=seed)
            count += len(training_week([club], {club.id: Form()}, DAY, rng))
        return count

    assert injuries("intense") > injuries("light")


def test_a_theme_sharpens_one_line_and_blunts_the_others():
    base = coaching(_club())
    attack = coaching(_club(theme="attack"))
    assert attack.attack > base.attack and attack.defence < base.defence
    assert coaching(_club(theme="kicking")).kicking > base.kicking
    assert coaching(_club(theme="fitness")).endurance < base.endurance
    assert Plan(theme=Theme.SET_PIECE).training().focus == ("scrum", "lineout")


# --- API -------------------------------------------------------------------------------


def test_the_manager_sets_the_training_week(manager):
    week = manager.get("/training").json()
    assert (week["intensity"], week["theme"]) == ("normal", "none")
    assert {o["key"] for o in week["intensities"]} == {"light", "normal", "intense"}
    assert week["players"] and all("potential_low" in p for p in week["players"])
    week = manager.put("/training", json={"intensity": "intense"}).json()
    week = manager.put("/training", json={"theme": "defence"}).json()
    assert (week["intensity"], week["theme"]) == ("intense", "defence")
    assert manager.put("/training", json={"theme": "yoga"}).status_code == 422
    # La semaine choisie vaut pour les journées suivantes.
    assert manager.post("/seasons/current/play").status_code == 200
    assert manager.get("/training").json()["theme"] == "defence"
