"""Moteur de match de rugby probabiliste, minute par minute.

Principe :
1. On choisit un XV de départ (2 piliers, 1 talonneur, 2 deuxième ligne,
   3 troisième ligne, 1 demi de mêlée, 1 ouvreur, 2 centres, 2 ailiers, 1 arrière).
2. On calcule des notes collectives : conquête (mêlée + touche), paquet d'avants,
   attaque des lignes arrières, défense, buteur.
3. Chaque minute, une action dangereuse peut survenir :
   - la conquête et le paquet décident quelle équipe a l'occasion (territoire) ;
   - l'attaque contre la défense décide s'il y a essai (+ transformation) ;
   - sinon la domination des avants peut provoquer une pénalité tentée au pied ;
   - plus rarement, l'ouvreur tente un drop.
4. Chaque minute aussi, un joueur peut se blesser (événement `INJURY`) : un
   joueur fragile, revenu de blessure depuis peu, risque en plus la rechute.
   La blessure elle-même (gravité, durée) est tirée par `engine/medical.py`.
5. La forme du jour (`engine/form.py` : moral, cohésion, fraîcheur) multiplie
   les notes collectives, et la fatigue augmente le risque de blessure.
6. En phase finale, une égalité après 80 minutes mène à une prolongation
   (2 x 10 minutes), puis si besoin à une séance de tirs au but.

Quand le match a une date, les joueurs blessés à cette date ne sont pas
alignés. Le moteur ne travaille que sur les objets de `models` : aucune
dépendance à FastAPI ni à la base de données.
"""

import datetime
import random
from dataclasses import dataclass

from engine.form import NEUTRAL_FORM, Form
from engine.medical import MATCH_INJURY_CHANCE_PER_MINUTE
from models import (
    EXTRA_TIME_MINUTES,
    REGULATION_MINUTES,
    Club,
    EventType,
    Match,
    MatchEvent,
    Player,
    Position,
)

# Composition du XV de départ (à rendre configurable plus tard).
FORMATION = {
    Position.PROP: 2,
    Position.HOOKER: 1,
    Position.LOCK: 2,
    Position.BACK_ROW: 3,
    Position.SCRUM_HALF: 1,
    Position.FLY_HALF: 1,
    Position.CENTRE: 2,
    Position.WING: 2,
    Position.FULLBACK: 1,
}

MATCH_MINUTES = REGULATION_MINUTES

# Probabilité qu'une action dangereuse survienne à une minute donnée.
CHANCE_PER_MINUTE = 0.28

# Entre deux équipes de même niveau, une action dangereuse donne :
TRY_RATE = 0.20  # un essai dans 20 % des cas
PENALTY_RATE = 0.30  # une pénalité tentée dans 30 % des cas
DROP_RATE = 0.02  # un drop réussi dans 2 % des cas
# ... et rien du tout (ballon perdu, en-avant...) le reste du temps.
# Calibrage (sur 4000 matchs simulés) : ~49 points et ~4,7 essais par match,
# ~60 % de victoires à domicile, ~2 % de nuls, proche du Top 14.

# Bonus multiplicatif sur le territoire de l'équipe à domicile
# (l'avantage du terrain est fort au rugby).
HOME_ADVANTAGE = 1.25

# Plus l'exposant est grand, plus l'écart de niveau pèse sur le résultat
# (1 = proportionnel, 2 = l'équipe forte écrase davantage).
# À 1.0, le meilleur club bat le plus faible ~95 % du temps à domicile.
STRENGTH_EXPONENT = 1.0

# Probabilité de réussir un coup de pied au but : 35 % + 3 % par point de kicking
# (kicking 10 => 65 %, 15 => 80 %, 20 => 95 %).
KICK_BASE = 0.35
KICK_PER_POINT = 0.03
# Une transformation se tente là où l'essai a été marqué, souvent excentrée.
CONVERSION_PENALTY = 0.05

# Tirs au but (règlement du Top 14) : 5 buteurs par équipe en alternance, depuis
# la ligne des 22 mètres, puis mort subite tant que l'égalité persiste.
SHOOTOUT_KICKERS = 5
# La pression de la séance coûte un peu de réussite par rapport à une pénalité.
SHOOTOUT_PRESSURE = 0.05

# Probabilité de marquer l'essai selon le poste (les ailiers finissent les actions).
TRY_SCORER_WEIGHT = {
    Position.PROP: 0.5,
    Position.HOOKER: 1.0,
    Position.LOCK: 0.5,
    Position.BACK_ROW: 2.0,
    Position.SCRUM_HALF: 1.5,
    Position.FLY_HALF: 1.0,
    Position.CENTRE: 2.5,
    Position.WING: 4.0,
    Position.FULLBACK: 2.5,
}


# --- Notes des joueurs ---------------------------------------------------------------


def scrum_rating(p: Player) -> float:
    return 0.6 * p.scrum + 0.4 * p.power


def lineout_rating(p: Player) -> float:
    return 0.7 * p.lineout + 0.3 * p.power


def carrying_rating(p: Player) -> float:
    """Avancée dans les contacts et travail dans les rucks."""
    return 0.5 * p.power + 0.3 * p.tackling + 0.2 * p.handling


def attacking_rating(p: Player) -> float:
    return 0.35 * p.pace + 0.35 * p.handling + 0.3 * p.passing


def defending_rating(p: Player) -> float:
    return 0.6 * p.tackling + 0.2 * p.power + 0.2 * p.pace


# Note utilisée pour choisir les titulaires à chaque poste.
RATING_FOR_POSITION = {
    Position.PROP: scrum_rating,
    Position.HOOKER: lambda p: 0.5 * scrum_rating(p) + 0.5 * lineout_rating(p),
    Position.LOCK: lambda p: 0.5 * lineout_rating(p) + 0.5 * carrying_rating(p),
    Position.BACK_ROW: lambda p: 0.5 * carrying_rating(p) + 0.5 * defending_rating(p),
    Position.SCRUM_HALF: lambda p: 0.6 * p.passing + 0.4 * p.handling,
    Position.FLY_HALF: lambda p: 0.4 * p.kicking + 0.3 * p.passing + 0.3 * p.handling,
    Position.CENTRE: lambda p: 0.5 * attacking_rating(p) + 0.5 * defending_rating(p),
    Position.WING: lambda p: 0.6 * p.pace + 0.4 * p.handling,
    Position.FULLBACK: lambda p: 0.4 * attacking_rating(p) + 0.3 * p.kicking + 0.3 * p.pace,
}


def _average(values: list[float]) -> float:
    return sum(values) / len(values) if values else 1.0


# --- Force d'une équipe --------------------------------------------------------------


@dataclass
class TeamStrength:
    """XV de départ et notes collectives d'un club pour un match."""

    club: Club
    lineup: list[Player]
    set_piece: float  # conquête : mêlée + touche
    pack: float  # paquet d'avants dans le jeu courant
    attack: float  # lignes arrières (+ un peu de 3e ligne)
    defense: float  # défense des 15 joueurs
    kicker: Player  # buteur désigné

    @property
    def territory(self) -> float:
        """Capacité à occuper le camp adverse et à se procurer des occasions."""
        return 0.4 * self.set_piece + 0.4 * self.pack + 0.2 * self.kicker.kicking

    @property
    def forward_dominance(self) -> float:
        """Domination des avants, qui pousse l'adversaire à la faute (pénalités)."""
        return 0.5 * self.set_piece + 0.5 * self.pack


def select_lineup(club: Club, day: datetime.date | None = None) -> list[Player]:
    """Choisit les meilleurs joueurs disponibles à chaque poste selon FORMATION.

    Les titularisations promises (`club.forced_starters`) passent devant à leur poste.
    Les blessés à la date `day` sont écartés (sans date, tout le monde est apte).
    S'il manque des joueurs à un poste, on complète avec les meilleurs restants
    (un effectif incomplet peut quand même jouer).
    """
    available = club.available_players(day)
    lineup: list[Player] = []
    for position, count in FORMATION.items():
        candidates = sorted(
            (p for p in available if p.position == position),
            key=lambda p, rating=RATING_FOR_POSITION[position]: (
                p.id in club.forced_starters,
                rating(p),
            ),
            reverse=True,
        )
        lineup.extend(candidates[:count])

    missing = sum(FORMATION.values()) - len(lineup)
    if missing > 0:
        remaining = sorted(
            (p for p in available if p not in lineup), key=lambda p: p.overall, reverse=True
        )
        lineup.extend(remaining[:missing])
    return lineup


def team_strength(
    club: Club, day: datetime.date | None = None, form: Form = NEUTRAL_FORM
) -> TeamStrength:
    """XV de départ et notes collectives ; `form` les module (neutre par défaut)."""
    lineup = select_lineup(club, day)
    factor = form.factor([p.id for p in lineup])

    def at(*positions: Position) -> list[Player]:
        return [p for p in lineup if p.position in positions]

    front_row = at(Position.PROP, Position.HOOKER)
    jumpers = at(Position.HOOKER, Position.LOCK, Position.BACK_ROW)
    forwards = [p for p in lineup if p.position.is_forward]
    backs = [p for p in lineup if not p.position.is_forward]

    scrum = 0.7 * _average([scrum_rating(p) for p in front_row]) + 0.3 * _average(
        [scrum_rating(p) for p in at(Position.LOCK)]
    )
    lineout = _average([lineout_rating(p) for p in jumpers])

    return TeamStrength(
        club=club,
        lineup=lineup,
        set_piece=factor * (0.5 * scrum + 0.5 * lineout),
        pack=factor * _average([carrying_rating(p) for p in forwards]),
        attack=factor
        * (
            0.8 * _average([attacking_rating(p) for p in backs])
            + 0.2 * _average([attacking_rating(p) for p in at(Position.BACK_ROW)])
        ),
        defense=factor * _average([defending_rating(p) for p in lineup]),
        kicker=max(lineup, key=lambda p: p.kicking),
    )


# --- Simulation ----------------------------------------------------------------------


def _win_probability(a: float, b: float) -> float:
    """Probabilité que la note `a` l'emporte sur la note `b` (entre 0 et 1)."""
    a_pow, b_pow = a**STRENGTH_EXPONENT, b**STRENGTH_EXPONENT
    return a_pow / (a_pow + b_pow)


def kick_success_probability(kicking: int, is_conversion: bool = False) -> float:
    probability = KICK_BASE + KICK_PER_POINT * kicking
    if is_conversion:
        probability -= CONVERSION_PENALTY
    return min(probability, 0.95)


def _pick_try_scorer(team: TeamStrength, rng: random.Random) -> Player:
    weights = [TRY_SCORER_WEIGHT[p.position] * (p.pace + p.power) for p in team.lineup]
    return rng.choices(team.lineup, weights=weights)[0]


def _play_chance(
    attacking: TeamStrength, defending: TeamStrength, minute: int, rng: random.Random
) -> list[MatchEvent]:
    """Joue une action dangereuse et renvoie les événements produits (0, 1 ou 2)."""
    club_id = attacking.club.id
    # Les probabilités valent TRY_RATE / PENALTY_RATE entre équipes égales
    # (_win_probability = 0.5) et varient avec l'écart de niveau.
    try_probability = 2 * TRY_RATE * _win_probability(attacking.attack, defending.defense)
    penalty_probability = (
        2
        * PENALTY_RATE
        * _win_probability(attacking.forward_dominance, defending.forward_dominance)
    )

    roll = rng.random()

    # 1) Essai, suivi d'une tentative de transformation.
    if roll < try_probability:
        scorer = _pick_try_scorer(attacking, rng)
        kicker = attacking.kicker
        converted = rng.random() < kick_success_probability(kicker.kicking, is_conversion=True)
        conversion = EventType.CONVERSION if converted else EventType.CONVERSION_MISSED
        return [
            MatchEvent(minute, EventType.TRY, club_id, scorer.id),
            MatchEvent(minute, conversion, club_id, kicker.id),
        ]

    # 2) Pénalité tentée face aux perches.
    if roll < try_probability + penalty_probability:
        kicker = attacking.kicker
        success = rng.random() < kick_success_probability(kicker.kicking)
        event_type = EventType.PENALTY_GOAL if success else EventType.PENALTY_MISSED
        return [MatchEvent(minute, event_type, club_id, kicker.id)]

    # 3) Drop de l'ouvreur (on ne garde que les drops réussis, les ratés sont anecdotiques).
    if roll < try_probability + penalty_probability + DROP_RATE:
        fly_halves = [p for p in attacking.lineup if p.position == Position.FLY_HALF]
        drop_kicker = fly_halves[0] if fly_halves else attacking.kicker
        return [MatchEvent(minute, EventType.DROP_GOAL, club_id, drop_kicker.id)]

    # 4) L'action ne donne rien.
    return []


def _draw_injury_minutes(
    team: TeamStrength, day: datetime.date | None, rng: random.Random, form: Form = NEUTRAL_FORM
) -> dict[int, Player]:
    """Minute à laquelle chaque joueur blessé de l'équipe quitte le terrain.

    Un joueur fragile tire d'abord sa rechute (risque propre à son protocole),
    puis chaque minute un joueur apte peut se blesser : le risque grimpe avec la
    fatigue du XV, et le blessé est plus souvent un joueur fatigué. Un joueur ne
    se blesse qu'une fois par match.
    """
    minutes: dict[int, Player] = {}
    injured: set[int] = set()
    for player in team.lineup:
        if player.is_fragile(day) and rng.random() < player.injury.relapse_risk:
            minute = rng.randint(1, MATCH_MINUTES)
            while minute in minutes:
                minute = rng.randint(1, MATCH_MINUTES)
            minutes[minute] = player
            injured.add(player.id)
    weights = {p.id: form.injury_weight(p) for p in team.lineup}
    for minute in range(1, MATCH_MINUTES + 1):
        fit = [p for p in team.lineup if p.id not in injured]
        if not fit:
            break
        chance = MATCH_INJURY_CHANCE_PER_MINUTE * sum(weights[p.id] for p in fit) / len(fit)
        if rng.random() < chance and minute not in minutes:
            player = rng.choices(fit, weights=[weights[p.id] for p in fit])[0]
            minutes[minute] = player
            injured.add(player.id)
    return minutes


def _shootout(
    first: TeamStrength, second: TeamStrength, unavailable: set[int], rng: random.Random
) -> list[MatchEvent]:
    """Séance de tirs au but, `first` tirant le premier.

    Chaque équipe aligne ses meilleurs buteurs, sauf les blessés du match
    (`unavailable`). La séance s'arrête dès qu'une équipe ne peut plus être
    rattrapée ; après 5 tirs chacun, c'est la mort subite, tir par tir.
    """
    minute = MATCH_MINUTES + EXTRA_TIME_MINUTES
    teams = (first, second)
    kickers = []
    for team in teams:
        fit = [p for p in team.lineup if p.id not in unavailable] or team.lineup
        kickers.append(sorted(fit, key=lambda p: p.kicking, reverse=True))
    goals = [0, 0]
    events: list[MatchEvent] = []
    kicks = 0
    while True:
        side, turn = kicks % 2, kicks // 2
        kicker = kickers[side][turn % len(kickers[side])]
        scored = rng.random() < kick_success_probability(kicker.kicking) - SHOOTOUT_PRESSURE
        goals[side] += scored
        event_type = EventType.SHOOTOUT_GOAL if scored else EventType.SHOOTOUT_MISSED
        events.append(MatchEvent(minute, event_type, teams[side].club.id, kicker.id))
        kicks += 1
        if kicks < 2 * SHOOTOUT_KICKERS:
            left = [SHOOTOUT_KICKERS - (kicks + 1) // 2, SHOOTOUT_KICKERS - kicks // 2]
            if goals[0] > goals[1] + left[1] or goals[1] > goals[0] + left[0]:
                return events
        elif kicks % 2 == 0 and goals[0] != goals[1]:
            return events


def simulate_match(
    home: Club,
    away: Club,
    rng: random.Random | None = None,
    matchday: int = 0,
    neutral: bool = False,
    day: datetime.date | None = None,
    home_form: Form = NEUTRAL_FORM,
    away_form: Form = NEUTRAL_FORM,
    knockout: bool = False,
) -> Match:
    """Simule un match complet et renvoie un `Match` joué (score + événements).

    `rng` permet de fixer le hasard (ex. `random.Random(42)`) pour des résultats
    reproductibles, notamment dans les tests. `neutral` supprime l'avantage du
    terrain (finale). `day` est la date du match : les blessés ce jour-là ne
    jouent pas, et les blessures du match sont signalées en événements.
    `home_form` / `away_form` : forme du jour de chaque club (neutre par défaut).
    `knockout` : match à élimination directe, qui ne peut pas finir sur un nul
    (prolongation, puis tirs au but).
    """
    rng = rng or random.Random()
    home_team = team_strength(home, day, home_form)
    away_team = team_strength(away, day, away_form)
    forms = {home.id: home_form, away.id: away_form}

    # Probabilité que l'action de la minute soit pour l'équipe à domicile.
    advantage = 1.0 if neutral else HOME_ADVANTAGE
    home_share = _win_probability(home_team.territory * advantage, away_team.territory)

    # Les blessures sont tirées à part : elles ne changent pas le fil du match
    # (le remplaçant est supposé du même niveau), seulement l'effectif ensuite.
    injuries = {
        team.club.id: _draw_injury_minutes(team, day, rng, forms[team.club.id])
        for team in (home_team, away_team)
    }

    match = Match(
        home_club_id=home.id,
        away_club_id=away.id,
        matchday=matchday,
        neutral=neutral,
        date=day,
        home_lineup=[p.id for p in home_team.lineup],
        away_lineup=[p.id for p in away_team.lineup],
    )

    def play(first: int, last: int) -> None:
        for minute in range(first, last + 1):
            for club_id, minutes in injuries.items():
                if minute in minutes:
                    match.events.append(
                        MatchEvent(minute, EventType.INJURY, club_id, minutes[minute].id)
                    )
            if rng.random() >= CHANCE_PER_MINUTE:
                continue
            if rng.random() < home_share:
                match.events.extend(_play_chance(home_team, away_team, minute, rng))
            else:
                match.events.extend(_play_chance(away_team, home_team, minute, rng))

    def level() -> bool:
        return match.points_for(home.id) == match.points_for(away.id)

    play(1, MATCH_MINUTES)
    if knockout and level():
        play(MATCH_MINUTES + 1, MATCH_MINUTES + EXTRA_TIME_MINUTES)
    if knockout and level():
        injured = {p.id for minutes in injuries.values() for p in minutes.values()}
        # Tirage au sort de l'équipe qui tire la première.
        first, second = (home_team, away_team) if rng.random() < 0.5 else (away_team, home_team)
        match.events.extend(_shootout(first, second, injured, rng))

    # Le score se déduit des événements : une seule source de vérité.
    match.home_score = match.points_for(home.id)
    match.away_score = match.points_for(away.id)
    return match
