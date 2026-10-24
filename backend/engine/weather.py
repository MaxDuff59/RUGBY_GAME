"""Météo d'un match : le ciel au-dessus du stade change la façon de jouer.

Le temps d'un match dépend du stade (celui du club, ou de la sélection, qui
reçoit) et de la date :
il se tire toujours de la même façon pour ce club ce jour-là, si bien que la
prévision affichée avant le match est le temps qu'il fera. Le climat suit la
saison de chaque hémisphère : hivers pluvieux et venteux en Europe, de juin à
août dans l'hémisphère Sud (Super Rugby, clubs sud-africains), et chaleur en
été, plus marquée sur les hauts plateaux d'Afrique du Sud, plus secs.

Effets sur le moteur (engine/match_engine.py) :
- pluie : ballon glissant, moins d'essais et d'attaque, plus de fautes au sol,
  le jeu à la main en souffre plus que l'occupation au pied ;
- vent : coups de pied au but plus durs, drops rares, occupation au pied moins sûre ;
- chaleur : les joueurs se vident plus vite (l'endurance pèse davantage).
"""

import datetime
import random
from dataclasses import dataclass
from enum import StrEnum

from models import Club


class Weather(StrEnum):
    CLEAR = "clear"  # temps sec, sans vent
    RAIN = "rain"
    WIND = "wind"
    HEAT = "heat"


@dataclass(frozen=True)
class Effects:
    attack: float = 1.0  # note d'attaque des lignes arrières
    tries: float = 1.0  # chance d'essai d'une action dangereuse
    penalties: float = 1.0  # pénalités obtenues
    kicking: float = 0.0  # réussite des coups de pied au but (en points de pourcentage)
    drops: float = 1.0
    drain: float = 1.0  # énergie dépensée par minute
    # Bonus du plan de jeu sur les essais : sous la pluie, le jeu à la main
    # perd plus que l'occupation au pied (GamePlan -> multiplicateur).
    hands: float = 1.0
    kicking_plan: float = 1.0  # territoire gagné par l'occupation au pied


EFFECTS = {
    Weather.CLEAR: Effects(),
    Weather.RAIN: Effects(attack=0.93, tries=0.88, penalties=1.08, kicking=-0.05, hands=0.92),
    Weather.WIND: Effects(kicking=-0.10, drops=0.5, kicking_plan=0.96),
    Weather.HEAT: Effects(drain=1.2),
}

LABELS = {
    Weather.CLEAR: "Temps sec",
    Weather.RAIN: "Pluie",
    Weather.WIND: "Vent",
    Weather.HEAT: "Chaleur",
}

# Chances de chaque temps selon le moment de la saison, dans l'hémisphère Nord
# (mois -> saison). L'hémisphère Sud décale les mois de six.
SEASON_OF_MONTH = {
    12: "winter", 1: "winter", 2: "winter",
    3: "mid", 4: "mid", 10: "mid", 11: "mid",
    5: "summer", 6: "summer", 7: "summer", 8: "summer", 9: "summer",
}  # fmt: skip
CLIMATE = {
    "winter": {Weather.CLEAR: 0.45, Weather.RAIN: 0.35, Weather.WIND: 0.20, Weather.HEAT: 0.0},
    "mid": {Weather.CLEAR: 0.60, Weather.RAIN: 0.25, Weather.WIND: 0.15, Weather.HEAT: 0.0},
    "summer": {Weather.CLEAR: 0.62, Weather.RAIN: 0.10, Weather.WIND: 0.10, Weather.HEAT: 0.18},
}
# Afrique du Sud : moins de pluie, plus de chaleur.
DRY_RAIN, DRY_HEAT = 0.5, 1.5

SOUTHERN_LEAGUES = {"super_rugby"}
# Les sélections reçoivent chez elles : celles de l'hémisphère Sud suivent ses saisons.
SOUTHERN_NATIONS = {"Nouvelle-Zélande", "Australie", "Argentine", "Fidji", "Samoa", "Tonga"}
# Hauts plateaux et Cap : plus secs.
SOUTH_AFRICAN_CLUBS = {"Bulls", "Stormers", "Sharks", "Lions", "Afrique du Sud"}


def climate(name: str, league: str, day: datetime.date) -> dict[Weather, float]:
    """Chances de chaque temps au stade du club `name` (de ce championnat) à cette date."""
    south_africa = name in SOUTH_AFRICAN_CLUBS
    month = day.month
    if league in SOUTHERN_LEAGUES or name in SOUTHERN_NATIONS or south_africa:
        month = (month + 5) % 12 + 1
    odds = dict(CLIMATE[SEASON_OF_MONTH[month]])
    if south_africa:
        odds[Weather.RAIN] *= DRY_RAIN
        odds[Weather.HEAT] *= DRY_HEAT
    return odds


def forecast_at(club_id: int, name: str, league: str, day: datetime.date | None) -> Weather:
    """Le temps du match que ce club reçoit ce jour-là (sec sans date : match amical)."""
    if day is None:
        return Weather.CLEAR
    odds = climate(name, league, day)
    rng = random.Random(f"weather-{club_id}-{day.isoformat()}")
    return rng.choices(list(odds), weights=list(odds.values()))[0]


def forecast(home: Club, day: datetime.date | None) -> Weather:
    return forecast_at(home.id, home.name, home.league, day)
