"""Un jour de match : la semaine d'entraînement, les matchs, puis l'argent.

`play_day` joue tous les matchs d'une date, tous championnats confondus, chacun
sous le temps du jour (engine/weather.py). Il remplit les matchs reçus (score,
événements, XV de départ, statistiques), attache les blessures et les
suspensions (engine/discipline.py) aux joueurs, et rend compte de ce qui
s'est passé (`DayReport`) : à l'appelant de l'enregistrer
(api/routers/seasons.py) ou de le garder en mémoire (engine/world.py). Aucune
dépendance à FastAPI ni à la base de données.
"""

import datetime
import random
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field

from data.leagues import League
from engine import development, discipline
from engine.crowd import gate
from engine.economy import (
    CHAMPION_PRIZE,
    PLAYOFF_PRIZES,
    TransactionCategory,
    attendance,
    attendance_bonus,
    hospitality_revenue,
    matchday_wages,
    sponsor_revenue,
    ticketing_revenue,
)
from engine.form import Form
from engine.match_engine import simulate_match
from engine.medical import new_injury, training_injuries
from engine.supporters import NEUTRAL as FANS_NEUTRAL
from engine.training import plan_of
from engine.weather import forecast
from models import Club, EventType, Injury, InjurySource, Match, Stage

STAGE_LABELS = {
    Stage.QUARTER: "quarts de finale",
    Stage.BARRAGE: "barrages",
    Stage.SEMI: "demi-finales",
    Stage.FINAL: "finale",
}


def matchday_label(stage: Stage, matchday: int) -> str:
    return f"journée {matchday}" if stage == Stage.REGULAR else STAGE_LABELS[stage]


@dataclass(frozen=True)
class Movement:
    """Un mouvement d'argent d'un club (positif = recette, négatif = dépense)."""

    club_id: int
    category: TransactionCategory
    label: str
    amount: int
    matchday: int


@dataclass
class Day:
    """Ce qu'il faut savoir du monde pour jouer les matchs d'une date.

    `clubs` : au moins tous les clubs des championnats qui jouent ce jour-là.
    `forms` : leur forme du jour. `seeding` : le classement de chaque championnat
    avant la journée (il fixe l'affluence et départage les phases finales).
    `managed_club_id` : le club du joueur, dont les blessures attendent un
    protocole de soins.
    """

    date: datetime.date
    clubs: dict[int, Club]
    forms: dict[int, Form]
    leagues: dict[str, League]
    seeding: dict[str, list[int]]
    regular_matchdays: dict[str, int]
    managed_club_id: int | None = None
    # Ferveur des supporters d'un club (engine/supporters.py), pour l'affluence.
    fervour: Callable[[int], float] = lambda club_id: FANS_NEUTRAL
    # Recette par match des sponsors du maillot d'un club (engine/sponsors.py).
    shirt_revenue: Callable[[int], int] = lambda club_id: 0


@dataclass
class DayReport:
    played: list[Match] = field(default_factory=list)
    # (club, blessure) : à l'entraînement puis en match, dans l'ordre.
    injuries: list[tuple[int, Injury]] = field(default_factory=list)
    movements: list[Movement] = field(default_factory=list)
    suspensions: list[discipline.Suspension] = field(default_factory=list)
    # Joueurs dont la suspension ou le compteur de jaunes a changé, à enregistrer.
    disciplined: set[int] = field(default_factory=set)
    # Progression (engine/development.py) : joueurs qui ont avancé ce jour-là (à
    # enregistrer), et les attributs gagnés par chacun.
    developed: set[int] = field(default_factory=set)
    gains: dict[int, list[str]] = field(default_factory=dict)


def training_week(
    clubs: Iterable[Club],
    forms: dict[int, Form],
    day: datetime.date,
    rng: random.Random,
    managed_club_id: int | None = None,
) -> list[tuple[int, Injury]]:
    """Semaine d'entraînement des clubs avant les matchs du jour `day`.

    Un blessé à l'entraînement manque le match du jour ; les joueurs fatigués se
    blessent plus, et plus encore pendant une semaine intense. Renvoie les
    blessures, avec le club de chacune.
    """
    injuries = []
    for club in clubs:
        form, rhythm = forms[club.id], plan_of(club).rhythm

        def risk(player, form=form, rhythm=rhythm) -> float:
            # La fatigue, et le rythme de la semaine (engine/training.py).
            return form.injury_weight(player) * rhythm.injuries

        decided = club.id != managed_club_id
        for injury in training_injuries(club, day, rng, decided, risk):
            injuries.append((club.id, injury))
    return injuries


def _fill(match: Match, result: Match) -> None:
    """Reporte sur le match du calendrier ce que le moteur a joué."""
    match.home_score, match.away_score = result.home_score, result.away_score
    match.events = list(result.events)
    match.home_lineup, match.away_lineup = list(result.home_lineup), list(result.away_lineup)
    match.weather, match.stats = result.weather, dict(result.stats)
    match.spectators, match.atmosphere = result.spectators, result.atmosphere
    match.momentum = list(result.momentum)


def play_day(
    world: Day,
    matches: list[Match],
    rng: random.Random,
    youth_matches: Iterable[Match] = (),
    trained: bool = False,
    finished: Callable[[Match], Match | None] = lambda match: None,
) -> DayReport:
    """Joue les matchs du jour (`matches`, pas encore joués) et les matchs espoirs.

    `trained` : la semaine d'entraînement a déjà eu lieu (match en direct commencé).
    `finished` : le résultat d'un match joué par ailleurs (le match en direct du
    club dirigé), None pour le laisser au moteur.
    """
    day, clubs = world.date, world.clubs
    report = DayReport()
    leagues = sorted({m.league for m in matches})
    playing = sorted(
        (club for club in clubs.values() if club.league in leagues), key=lambda club: club.id
    )
    # Avec les espoirs appelés en renfort un jour de doublon (engine/internationals.py).
    players = {p.id: p for club in clubs.values() for p in [*club.players, *club.cover]}
    rank_of = {
        club_id: rank
        for league in leagues
        for rank, club_id in enumerate(world.seeding[league], start=1)
    }

    if not trained:
        report.injuries += training_week(playing, world.forms, day, rng, world.managed_club_id)

    def pay(club: Club, category: TransactionCategory, label: str, amount: int, on: int) -> None:
        report.movements.append(Movement(club.id, category, label, amount, on))

    for match in matches:
        stage, matchday = match.stage, match.matchday
        label = matchday_label(stage, matchday)
        config = world.leagues[match.league]
        order = world.seeding[match.league]
        home, away = clubs[match.home_club_id], clubs[match.away_club_id]
        result = finished(match)
        if result is None:
            # Le public arrive avant le coup d'envoi : il fait l'avantage du terrain.
            crowd = None
            if not match.neutral:
                crowd = gate(
                    home,
                    rank_of[home.id],
                    len(order),
                    stage.is_playoff,
                    rng,
                    world.fervour(home.id),
                )
            result = simulate_match(
                home,
                away,
                rng=rng,
                matchday=matchday,
                neutral=match.neutral,
                day=day,
                home_form=world.forms[home.id],
                away_form=world.forms[away.id],
                knockout=stage.is_playoff,
                weather=forecast(home, day),
                crowd=crowd,
            )
        _fill(match, result)
        report.played.append(match)

        # Les suspendus ont purgé ce match ; la commission juge ensuite les cartons du jour.
        for club in (home, away):
            report.disciplined.update(p.id for p in discipline.serve(club))
        suspensions = discipline.sanctions(match, players, rng)
        report.suspensions += suspensions
        report.disciplined.update(
            e.player_id for e in match.events if e.type == EventType.YELLOW_CARD
        )
        report.disciplined.update(s.player_id for s in suspensions)

        # Chacun progresse selon ce qu'il a fait du match (ou de la semaine).
        for club in (home, away):
            report.gains.update(
                development.develop(club, match.stats, rng, training=plan_of(club).training())
            )
            report.developed.update(p.id for p in club.players)

        for event in match.events:
            if event.type == EventType.INJURY:
                club = clubs[event.club_id]
                injury = new_injury(
                    players[event.player_id],
                    club,
                    InjurySource.MATCH,
                    day,
                    rng,
                    decided=club.id != world.managed_club_id,
                )
                report.injuries.append((club.id, injury))

        spectators = match.spectators
        if spectators is None:  # terrain neutre : la recette revient au club qui reçoit
            spectators = attendance(
                home.facilities.stadium_capacity,
                rank_of[home.id],
                len(order),
                stage.is_playoff,
                rng,
                fervour=world.fervour(home.id),
                bonus=attendance_bonus(home.facilities),
            )
        pay(
            home,
            TransactionCategory.TICKETING,
            f"Billetterie · {away.name} · {spectators:,} spectateurs".replace(",", " "),
            ticketing_revenue(spectators),
            matchday,
        )
        if hospitality := hospitality_revenue(home.facilities, spectators):
            pay(
                home,
                TransactionCategory.HOSPITALITY,
                f"Buvettes, boutique et loges · {away.name}",
                hospitality,
                matchday,
            )
        for club in (home, away):
            pay(
                club,
                TransactionCategory.SPONSORS,
                f"Sponsors · {label}",
                sponsor_revenue(club.facilities),
                matchday,
            )
            if shirt := world.shirt_revenue(club.id):
                pay(
                    club,
                    TransactionCategory.SPONSORS,
                    f"Sponsors du maillot · {label}",
                    shirt,
                    matchday,
                )
            if stage.is_playoff:
                prize = round(PLAYOFF_PRIZES[stage] * config.prize_factor)
                pay(club, TransactionCategory.PRIZE, f"Prime · {label}", prize, matchday)
        if stage == Stage.FINAL:
            winner = clubs[match.winner_id(order)]
            prize = round(CHAMPION_PRIZE * config.prize_factor)
            pay(winner, TransactionCategory.PRIZE, "Prime · champion", prize, matchday)

    # Les espoirs jouent leur journée en même temps que les pros (sans blessures).
    for match in youth_matches:
        result = simulate_match(
            clubs[match.home_club_id].youth_team(),
            clubs[match.away_club_id].youth_team(),
            rng=rng,
            matchday=match.matchday,
            weather=forecast(clubs[match.home_club_id], day),
        )
        _fill(match, result)
        for club in (clubs[match.home_club_id], clubs[match.away_club_id]):
            report.gains.update(development.develop(club, match.stats, rng, youth=True))
            report.developed.update(p.id for p in club.youths)

    # Les salaires se versent à chaque journée de saison régulière du championnat,
    # à tous ses clubs.
    for league in leagues:
        regular = next(
            (m for m in matches if m.league == league and m.stage == Stage.REGULAR), None
        )
        if regular is None:
            continue
        matchday = regular.matchday
        label = matchday_label(Stage.REGULAR, matchday)
        for club in playing:
            if club.league == league:
                wages = matchday_wages(club, world.regular_matchdays[league])
                pay(club, TransactionCategory.WAGES, f"Salaires · {label}", -wages, matchday)

    return report
