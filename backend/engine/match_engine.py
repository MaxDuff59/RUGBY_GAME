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

Quand le match a une date, les joueurs blessés à cette date ne sont pas
alignés. Le moteur ne travaille que sur les objets de `models` : aucune
dépendance à FastAPI ni à la base de données.
"""

import datetime
import random
from dataclasses import dataclass

from engine.medical import MATCH_INJURY_CHANCE_PER_MINUTE
from models import Club, EventType, Match, MatchEvent, Player, Position

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

MATCH_MINUTES = 80

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

    Les blessés à la date `day` sont écartés (sans date, tout le monde est apte).
    S'il manque des joueurs à un poste, on complète avec les meilleurs restants
    (un effectif incomplet peut quand même jouer).
    """
    available = club.available_players(day)
    lineup: list[Player] = []
    for position, count in FORMATION.items():
        candidates = sorted(
            (p for p in available if p.position == position),
            key=RATING_FOR_POSITION[position],
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


def team_strength(club: Club, day: datetime.date | None = None) -> TeamStrength:
    lineup = select_lineup(club, day)

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
        set_piece=0.5 * scrum + 0.5 * lineout,
        pack=_average([carrying_rating(p) for p in forwards]),
        attack=0.8 * _average([attacking_rating(p) for p in backs])
        + 0.2 * _average([attacking_rating(p) for p in at(Position.BACK_ROW)]),
        defense=_average([defending_rating(p) for p in lineup]),
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
    team: TeamStrength, day: datetime.date | None, rng: random.Random
) -> dict[int, Player]:
    """Minute à laquelle chaque joueur blessé de l'équipe quitte le terrain.

    Un joueur fragile tire d'abord sa rechute (risque propre à son protocole),
    puis chaque minute un joueur apte peut se blesser. Un joueur ne se blesse
    qu'une fois par match.
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
    for minute in range(1, MATCH_MINUTES + 1):
        if rng.random() < MATCH_INJURY_CHANCE_PER_MINUTE:
            fit = [p for p in team.lineup if p.id not in injured]
            if fit and minute not in minutes:
                player = rng.choice(fit)
                minutes[minute] = player
                injured.add(player.id)
    return minutes


def simulate_match(
    home: Club,
    away: Club,
    rng: random.Random | None = None,
    matchday: int = 0,
    neutral: bool = False,
    day: datetime.date | None = None,
) -> Match:
    """Simule un match complet et renvoie un `Match` joué (score + événements).

    `rng` permet de fixer le hasard (ex. `random.Random(42)`) pour des résultats
    reproductibles, notamment dans les tests. `neutral` supprime l'avantage du
    terrain (finale). `day` est la date du match : les blessés ce jour-là ne
    jouent pas, et les blessures du match sont signalées en événements.
    """
    rng = rng or random.Random()
    home_team, away_team = team_strength(home, day), team_strength(away, day)

    # Probabilité que l'action de la minute soit pour l'équipe à domicile.
    advantage = 1.0 if neutral else HOME_ADVANTAGE
    home_share = _win_probability(home_team.territory * advantage, away_team.territory)

    # Les blessures sont tirées à part : elles ne changent pas le fil du match
    # (le remplaçant est supposé du même niveau), seulement l'effectif ensuite.
    injuries = {
        team.club.id: _draw_injury_minutes(team, day, rng) for team in (home_team, away_team)
    }

    match = Match(
        home_club_id=home.id, away_club_id=away.id, matchday=matchday, neutral=neutral, date=day
    )
    for minute in range(1, MATCH_MINUTES + 1):
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

    # Le score se déduit des événements : une seule source de vérité.
    match.home_score = match.points_for(home.id)
    match.away_score = match.points_for(away.id)
    return match
