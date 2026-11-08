"""Sélections nationales : calendrier, listes, doublons, carrière de sélectionneur."""

import datetime
import itertools
import random
from collections import Counter
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import Session, sessionmaker

from api.auth import current_user
from api.deps import get_session
from api.main import app
from data.generator import (
    generate_clubs,
    generate_player,
    generate_real_clubs,
    generate_youth_player,
)
from data.leagues import LEAGUES_BY_CODE, league
from data.nations import (
    NATIONS_BY_CODE,
    WINDOWS_BY_CODE,
    WORLD_CUP,
    home_nation,
    season_windows,
)
from database import init_db
from engine import dilemmas
from engine import internationals as rules
from engine.calendar import SATURDAY, is_world_cup_year, season_dates, world_cup_saturdays
from engine.match_engine import SLOT_POSITIONS, select_bench, select_lineup
from engine.medical import new_injury
from engine.season import generate_fixtures, next_playoff_matches, schedule
from engine.world import World
from models import Club, InjurySource, Match, Position, Squad, Stage
from models.orm import (
    Base,
    CallUpRow,
    ClubRow,
    InjuryRow,
    InternationalRow,
    MatchRow,
    PlayerRow,
    SeasonRow,
)
from tests import conftest

FRANCE, ENGLAND, NEW_ZEALAND = (NATIONS_BY_CODE[code] for code in ("FRA", "ENG", "NZL"))


# --- Calendrier ----------------------------------------------------------------------------


def test_a_season_has_its_windows_on_saturdays():
    matches = rules.schedule(2026)
    assert Counter(m.league for m in matches) == {
        "rugby_championship": 12,
        "pacific_nations": 15,
        "autumn": 18,
        "november_tests": 12,
        "six_nations": 15,
        "rugby_europe": 28,
        "sudamericano": 6,
        "africa_cup": 6,
        "asia": 6,
    }
    assert all(m.date.weekday() == SATURDAY for m in matches)
    # Une nation ne joue jamais deux matchs le même samedi.
    busy = Counter((m.date, team) for m in matches for team in (m.home_club_id, m.away_club_id))
    assert set(busy.values()) == {1}
    # Dans l'ordre de la saison : août-octobre, novembre, février-mars, avril-mai.
    first = {
        window.code: min(m.date for m in rules.window_matches(matches, window.code))
        for window in season_windows(2026)
    }
    assert first["rugby_championship"] == datetime.date(2026, 8, 15)
    assert first["pacific_nations"] == datetime.date(2026, 8, 22)
    assert first["autumn"] == first["november_tests"] == datetime.date(2026, 11, 14)
    assert first["six_nations"] == first["rugby_europe"] == datetime.date(2027, 2, 6)
    assert first["sudamericano"] == first["asia"] == datetime.date(2027, 4, 24)
    # Toutes les nations jouent chaque saison : on peut toutes les diriger.
    assert len(rules.participants()) == len(rules.selectable()) == 36


def test_six_nations_is_a_single_round_robin_that_flips_every_year():
    def pairs(year):
        return [
            (m.home_club_id, m.away_club_id)
            for m in rules.window_matches(rules.schedule(year), "six_nations")
        ]

    this_year, next_year = pairs(2026), pairs(2027)
    assert len({frozenset(pair) for pair in this_year}) == 15  # chacun contre chacun, une fois
    assert set(next_year) == {(away, home) for home, away in this_year}


def test_rugby_championship_is_home_and_away():
    matches = rules.window_matches(rules.schedule(2026), "rugby_championship")
    pairs = Counter((m.home_club_id, m.away_club_id) for m in matches)
    assert len(pairs) == 12 and set(pairs.values()) == {1}
    for day in {m.date for m in matches}:
        teams = [t for m in matches if m.date == day for t in (m.home_club_id, m.away_club_id)]
        assert len(teams) == len(set(teams)) == 4


def test_autumn_hosts_meet_three_different_visitors_and_they_rotate():
    def visitors(year):
        met = {}
        for m in rules.window_matches(rules.schedule(year), "autumn"):
            met.setdefault(m.home_club_id, set()).add(m.away_club_id)
        return met

    # 2027 est une année de Coupe du monde, sans tournées : l'édition suivante est en 2028.
    first, second = visitors(2026), visitors(2028)
    assert set(first) == {NATIONS_BY_CODE[code].id for code in WINDOWS_BY_CODE["autumn"].nations}
    for host in first:
        assert len(first[host]) == 3
        assert not first[host] & second[host]  # six adversaires différents en deux saisons


def test_lists_are_due_two_weeks_before_the_first_match():
    matches = rules.schedule(2026)
    november = [m for m in matches if m.league in ("autumn", "november_tests")]
    assert rules.announce_by(november) == datetime.date(2026, 10, 31)

    before = rules.due_lists(matches, [], datetime.date(2026, 10, 24))
    assert {code for code, _ in before} == {"rugby_championship", "pacific_nations"}
    due = rules.due_lists(matches, before, datetime.date(2026, 10, 31))
    teams = {team for m in november for team in (m.home_club_id, m.away_club_id)}
    assert {code for code, _ in due} == {"autumn", "november_tests"}
    assert {team for _, team in due} == teams and len(due) == len(teams)
    # Une fenêtre finie ne réclame plus rien.
    for match in matches:
        if match.league in ("rugby_championship", "pacific_nations"):
            match.home_score = match.away_score = 10
    assert rules.due_lists(matches, [], datetime.date(2026, 10, 24)) == []


# --- Coupe du monde ------------------------------------------------------------------------

WORLD_CUP_IDS = {NATIONS_BY_CODE[code].id for code in WORLD_CUP.nations}


def test_world_cup_replaces_august_to_november_every_four_years():
    assert [year for year in range(2026, 2036) if is_world_cup_year(year)] == [2027, 2031, 2035]
    matches = rules.schedule(2027)
    assert Counter(m.league for m in matches) == {
        "world_cup": 36,
        "six_nations": 15,
        "rugby_europe": 28,
        "sudamericano": 6,
        "africa_cup": 6,
        "asia": 6,
    }
    pools = rules.window_matches(matches, "world_cup")
    assert all(m.neutral and m.stage == Stage.REGULAR for m in pools)
    assert sorted({m.date for m in pools}) == world_cup_saturdays(2027)[:3]
    assert world_cup_saturdays(2027)[0] == datetime.date(2027, 9, 11)
    played = Counter(team for m in pools for team in (m.home_club_id, m.away_club_id))
    assert set(played) == WORLD_CUP_IDS and len(played) == 24 and set(played.values()) == {3}
    assert rules.announce_by(pools) == datetime.date(2027, 8, 28)


def pots(ranking):
    seeded = sorted(WORLD_CUP_IDS, key=lambda team: ranking.index(team))
    return [set(seeded[i * 6 : (i + 1) * 6]) for i in range(4)]


def test_world_cup_pots_follow_the_world_ranking():
    usual = [NATIONS_BY_CODE[code].id for code in rules.default_ranking()]
    first, second = rules.world_cup_pools(2027), rules.world_cup_pools(2031)
    for pools in (first, second):
        assert len(pools) == 6
        for pool in pools:
            assert [len(set(pool) & pot) for pot in pots(usual)] == [1, 1, 1, 1]
    assert first != second  # un autre tirage à chaque édition
    # Le Portugal premier du classement : il devient tête de série.
    shaken = ["POR", *(code for code in rules.default_ranking() if code != "POR")]
    portugal = NATIONS_BY_CODE["POR"].id
    pools = rules.world_cup_pools(2027, shaken)
    assert pools[0][0] == portugal
    # Une fois tirées, les poules se relisent dans les matchs.
    matches = rules.schedule(2027, [WORLD_CUP], ranking=shaken)
    assert [set(pool) for pool in rules.pools_of(matches)] == [set(pool) for pool in pools]


def play_out(matches, favourite=None):
    """Joue les matchs restants : la mieux classée gagne (ou `favourite`)."""
    order = [NATIONS_BY_CODE[code].id for code in rules.default_ranking()]
    for match in matches:
        if match.is_played:
            continue
        home_wins = match.home_club_id == favourite or (
            match.away_club_id != favourite
            and order.index(match.home_club_id) < order.index(match.away_club_id)
        )
        match.home_score, match.away_score = (30, 10) if home_wins else (10, 30)


def test_world_cup_knockout_rounds_follow_the_pools():
    matches = rules.window_matches(rules.schedule(2027), "world_cup")
    assert rules.next_round(matches, 2027) == []  # les poules ne sont pas finies
    play_out(matches)

    last_16 = rules.next_round(matches, 2027)
    assert len(last_16) == 8 and {m.stage for m in last_16} == {Stage.LAST_16}
    assert {m.date for m in last_16} == {datetime.date(2027, 10, 2)}
    assert all(m.neutral and m.matchday == 4 for m in last_16)
    # Les deux premiers de chaque poule et les quatre meilleurs troisièmes, sans revoir
    # dès les huitièmes une nation de sa poule.
    pools = rules.pools_of(matches)
    order = [NATIONS_BY_CODE[code].id for code in rules.default_ranking()]
    ranked = [sorted(pool, key=order.index) for pool in pools]
    qualified = {team for m in last_16 for team in (m.home_club_id, m.away_club_id)}
    assert len(qualified) == 16
    assert {team for pool in ranked for team in pool[:2]} <= qualified
    assert len(qualified & {pool[2] for pool in ranked}) == 4
    assert not qualified & {pool[3] for pool in ranked}
    pool_of = {team: i for i, pool in enumerate(pools) for team in pool}
    assert all(pool_of[m.home_club_id] != pool_of[m.away_club_id] for m in last_16)
    matches += last_16
    assert rules.next_round(matches, 2027) == []  # huitièmes à jouer
    play_out(matches)

    quarters = rules.next_round(matches, 2027)
    assert [m.stage for m in quarters] == [Stage.QUARTER] * 4
    winners = [m.winner_id([m.home_club_id, m.away_club_id]) for m in last_16]
    assert [(m.home_club_id, m.away_club_id) for m in quarters] == list(
        zip(winners[::2], winners[1::2], strict=True)
    )
    matches += quarters
    play_out(matches)

    semis = rules.next_round(matches, 2027)
    assert [m.stage for m in semis] == [Stage.SEMI, Stage.SEMI]
    matches += semis
    underdog = semis[-1].away_club_id
    play_out(matches, favourite=underdog)

    (final,) = rules.next_round(matches, 2027)
    assert final.stage == Stage.FINAL and final.date == datetime.date(2027, 10, 23)
    assert not rules.is_finished(WORLD_CUP, matches + [final])
    matches.append(final)
    assert rules.champion(WORLD_CUP, matches) is None
    play_out(matches, favourite=underdog)
    assert rules.next_round(matches, 2027) == []
    assert rules.is_finished(WORLD_CUP, matches) and rules.champion(WORLD_CUP, matches) == underdog


def test_a_sixteen_nation_world_cup_still_goes_to_the_quarters():
    """Une partie dont la Coupe du monde a été tirée à seize nations la finit ainsi."""
    pools = [[9001, 9002, 9003, 9004], [9005, 9006, 9007, 9008]]
    pools += [[9009, 9010, 9011, 9012], [9013, 9014, 9015, 9016]]
    matches = []
    for r in range(3):
        for pool in pools:
            for home, away in generate_fixtures(pool)[r]:
                matches.append(
                    Match(home, away, r + 1, date=world_cup_saturdays(2027)[r], league="world_cup")
                )
    for match in matches:
        match.home_score, match.away_score = (
            (30, 10) if match.home_club_id < match.away_club_id else (10, 30)
        )
    quarters = rules.next_round(matches, 2027)
    assert [m.stage for m in quarters] == [Stage.QUARTER] * 4
    assert (quarters[0].home_club_id, quarters[0].away_club_id) == (9001, 9006)


def test_clubs_start_later_and_skip_the_november_break_in_a_world_cup_year():
    top14 = LEAGUES_BY_CODE["top14"]
    usual, _ = season_dates(2026, 26, top14.start, top14.breaks)
    shifted, playoffs = season_dates(2027, 26, top14.start, top14.breaks)
    cup = world_cup_saturdays(2027)
    # Pas de club avant le dernier samedi des poules : trois samedis plus tard que d'habitude.
    assert usual[0] == datetime.date(2026, 9, 5) and shifted[0] == cup[2] == datetime.date(
        2027, 9, 25
    )
    # Quelques doublons : la fin des poules, puis les huitièmes, les quarts, les demies et la
    # finale.
    assert sorted(set(shifted) & set(cup)) == cup[2:]
    # Plus de trêve en novembre (pas de tournées d'automne) : la saison finit comme d'habitude.
    november = [day for day in shifted if day.month == 11]
    assert len(november) == 4 and len([day for day in usual if day.month == 11]) == 1
    assert (shifted[-1] - usual[-1]).days in range(360, 368)
    # La finale tombe début juillet : les week-ends de la Coupe d'Europe s'ajoutent aux trêves.
    assert playoffs[-1] == datetime.date(2028, 7, 1)
    # Le Super Rugby, de février à juillet, ne bouge pas.
    southern = LEAGUES_BY_CODE["super_rugby"]
    assert season_dates(2027, 22, southern.start, southern.breaks)[0][0] == datetime.date(
        2028, 2, 5
    )


def test_playoffs_are_dated_after_the_last_matchday_actually_scheduled():
    top14 = LEAGUES_BY_CODE["top14"]
    matches = schedule(top14, list(range(1, 15)), 2027)
    # Une saison tirée avec d'autres dates (partie d'avant ce calendrier) : tout a glissé.
    for match in matches:
        match.date += datetime.timedelta(weeks=5)
        match.home_score = match.away_score = 10
    last = max(m.date for m in matches)
    barrages = next_playoff_matches(top14, matches, 2027)
    assert barrages and all(m.date > last for m in barrages)


# --- Listes --------------------------------------------------------------------------------


def national_pool(nation=FRANCE, per_position: int = 10, seed: int = 0):
    rng = random.Random(seed)
    ids = itertools.count(1)
    return [
        generate_player(next(ids), position, 12, 1, rng, nationality=nation.code)
        for position in Position
        for _ in range(per_position)
    ]


def test_staff_squad_follows_the_quota_and_leaves_the_injured_out():
    pool = national_pool()
    day = datetime.date(2026, 11, 14)
    best_prop = max((p for p in pool if p.position == Position.PROP), key=rules.position_rating)
    new_injury(best_prop, Club(id=1, name="Club"), InjurySource.MATCH, day, random.Random(3))

    squad = rules.pick_squad(pool, day)

    assert len(squad) == rules.SQUAD_SIZE
    assert Counter(p.position for p in squad) == rules.SQUAD_QUOTA
    assert best_prop not in squad
    assert rules.check_squad(squad) is None


def test_the_staff_weighs_form_playing_time_and_continuity():
    wing = generate_player(1, Position.WING, 14, 1, random.Random(0), nationality="FRA")
    base = rules.selection_score(wing)
    assert rules.selection_score(wing, rules.Record()) == base
    good, bad = rules.Record(ratings=(8.0, 7.5, 7.0)), rules.Record(ratings=(4.5, 4.8))
    assert rules.selection_score(wing, bad) < base < rules.selection_score(wing, good)
    assert rules.selection_score(wing, rules.Record(ratings=(10.0,) * 6)) == base + rules.FORM_CAP
    assert rules.selection_score(wing, rules.Record(ratings=(9.0,))) == base  # un match : trop tôt
    starter, unused = rules.Record(share=0.9), rules.Record(share=0.0)
    assert rules.selection_score(wing, starter) == base + rules.PLAYING_TIME_BONUS
    assert rules.selection_score(wing, unused) == base + rules.PLAYING_TIME_FLOOR
    assert rules.selection_score(wing, rules.Record(listed=True)) == base + rules.CONTINUITY


def test_an_in_form_starter_passes_a_better_rated_player_out_of_form():
    pool = national_pool()
    wings = sorted(
        (p for p in pool if p.position == Position.WING), key=rules.position_rating, reverse=True
    )
    quota = rules.SQUAD_QUOTA[Position.WING]
    # Le dernier retenu sur sa note, et le premier laissé de côté.
    last, outsider = wings[quota - 1], wings[quota]
    assert last in rules.pick_squad(pool, None) and outsider not in rules.pick_squad(pool, None)
    records = {
        last.id: rules.Record(ratings=(4.5,) * 6, share=0.05),
        outsider.id: rules.Record(ratings=(7.5,) * 6, share=0.9),
    }
    squad = rules.pick_squad(pool, None, records=records)
    assert outsider in squad and last not in squad


def test_a_list_needs_42_players_and_enough_of_each_position():
    pool = national_pool()
    squad = rules.pick_squad(pool, None)
    assert "42" in rules.check_squad(squad[:-1])
    assert "une fois" in rules.check_squad([*squad[:-1], squad[0]])
    without_props = [p for p in pool if p.position != Position.PROP][:42]
    assert "piliers" in rules.check_squad(without_props)


def test_some_federations_only_pick_players_from_home_clubs():
    english = generate_player(1, Position.WING, 14, 1, random.Random(0), nationality="ENG")
    french = generate_player(2, Position.WING, 14, 1, random.Random(0), nationality="FRA")
    assert rules.is_eligible(english, ENGLAND, "Bath Rugby")
    assert not rules.is_eligible(english, ENGLAND, "Stade Toulousain")  # exilé en Top 14
    assert rules.is_eligible(french, FRANCE, "Bath Rugby")
    assert not rules.is_eligible(french, ENGLAND, "Bath Rugby")
    youth = generate_youth_player(3, Position.WING, 10, 1, random.Random(0), nationality="FRA")
    assert not rules.is_eligible(youth, FRANCE, "Stade Toulousain")


def test_a_thin_nation_calls_players_from_outside_the_game():
    # Deux joueurs par poste, et aucun arrière.
    pool = [p for p in national_pool(per_position=2) if p.position != Position.FULLBACK]
    arrivals = rules.reinforcements(FRANCE, pool, itertools.count(1000), random.Random(1), 2026)
    everyone = Counter(p.position for p in [*pool, *arrivals])
    assert everyone == {
        position: quota + rules.DEPTH_MARGIN for position, quota in rules.SQUAD_QUOTA.items()
    }
    assert all(p.squad == Squad.AWAY and p.club_id is None for p in arrivals)
    assert {p.nationality for p in arrivals} == {"FRA"}
    # Un vivier assez fourni n'appelle personne.
    deep = national_pool()
    assert rules.reinforcements(FRANCE, deep, itertools.count(1), random.Random(1), 2026) == []


# --- Doublons ------------------------------------------------------------------------------


def test_called_up_players_miss_their_club_and_youths_cover_for_them():
    club = conftest.make_club(1, level=12, seed=1)
    rng = random.Random(2)
    club.youths = [
        generate_youth_player(900 + i, position, 9, 1, rng)
        for i, position in enumerate(
            [Position.HOOKER, Position.HOOKER, Position.PROP, Position.WING]
        )
    ]
    day = datetime.date(2026, 11, 28)
    hookers = [p for p in club.players if p.position == Position.HOOKER]
    assert len(hookers) == 3

    rules.release(club, {p.id for p in hookers[:2]}, day)

    lineup = select_lineup(club, day)
    squad = lineup + select_bench(club, lineup, day)
    assert len(lineup) == len(SLOT_POSITIONS)
    assert not {p.id for p in hookers[:2]} & {p.id for p in squad}
    # Il restait un talonneur pour deux places sur la feuille : un espoir monte, pas plus.
    assert [p.position for p in club.cover] == [Position.HOOKER]
    assert club.cover[0] in squad
    assert club.cover[0] not in club.youth_team().players

    # Sans international retenu, le club joue avec ses pros.
    rules.release(club, set(), day)
    assert club.cover == [] and len(club.available_players(day)) == len(club.players)


def test_absentees_are_the_lists_of_the_nations_playing_that_day():
    matches = rules.schedule(2026)
    squads = {
        ("autumn", FRANCE.id): [1, 2],
        ("six_nations", FRANCE.id): [3],
        ("autumn", ENGLAND.id): [4],
    }
    assert rules.absentees(matches, squads, datetime.date(2026, 11, 14)) == {
        1: FRANCE.id,
        2: FRANCE.id,
        4: ENGLAND.id,
    }
    assert rules.absentees(matches, squads, datetime.date(2026, 11, 7)) == {}
    assert rules.absentees(matches, squads, datetime.date(2027, 2, 6)) == {3: FRANCE.id}


# --- Un monde en mémoire -------------------------------------------------------------------


def top14_world(seed: int = 0) -> World:
    return World(generate_real_clubs(random.Random(seed), [league("top14")]), seed=seed)


def test_invented_clubs_have_no_national_teams():
    world = World(generate_clubs(4, random.Random(0)))
    assert not world.has_nations and world.season.tests == []


def test_world_plays_internationals_and_releases_players_on_clash_days():
    world = top14_world()
    season = world.season
    assert world.has_nations and len(season.tests) == len(rules.schedule(2026))
    # Aucun club gallois ni néo-zélandais ici : ces sélections recrutent hors du jeu.
    assert any(p.nationality == "NZL" for p in world.away)

    doublon = datetime.date(2026, 11, 28)  # dernier test d'automne, journée de Top 14
    while (day := world._next_day()) is not None and day <= doublon:
        world.play_day()

    autumn = season.window_matches("autumn")
    assert all(m.is_played for m in autumn)
    assert all(len(squad) == rules.SQUAD_SIZE for squad in season.squads.values())
    french = set(season.squads[("autumn", FRANCE.id)])
    clubs_that_day = [m for m in season.matches if m.date == doublon]
    assert clubs_that_day
    for match in clubs_that_day:
        assert match.is_played and len(match.home_lineup) == len(SLOT_POSITIONS)
        assert not french & {*match.home_lineup, *match.away_lineup}
    # La semaine d'avant (journée sans test pour le Top 14) : rien ne se joue en club.
    assert not [m for m in season.matches if m.date == datetime.date(2026, 11, 21)]
    # Les internationaux ont bien joué en sélection ce jour-là.
    france_match = next(m for m in autumn if m.date == doublon and m.home_club_id == FRANCE.id)
    assert set(france_match.home_lineup) <= french


def test_world_plays_a_whole_world_cup_and_frees_the_eliminated():
    world = World(generate_real_clubs(random.Random(0), [league("top14")]), seed=0, year=2027)
    season = world.season
    cup = world_cup_saturdays(2027)
    assert not season.window_matches("rugby_championship") and not season.window_matches("autumn")
    assert min(m.date for m in season.matches) == cup[2]  # le Top 14 attend la fin des poules

    while (day := world._next_day()) is not None and day <= cup[-1]:
        world.play_day()

    played = season.window_matches("world_cup")
    assert len(played) == 36 + 8 + 4 + 2 + 1 and all(m.is_played for m in played)
    assert Counter(m.stage for m in played)[Stage.FINAL] == 1
    champion = rules.champion(WORLD_CUP, season.tests)
    assert champion in {NATIONS_BY_CODE[code].id for code in WORLD_CUP.nations}
    # Aucun match à élimination directe ne finit sur un nul.
    assert all(m.result_for(m.home_club_id) != 0 for m in played if m.stage.is_playoff)

    # Doublons : le jour d'un tour, seules les sélections encore en course gardent leurs joueurs.
    for day, stage in zip(cup[3:], rules.KNOCKOUT_STAGES, strict=True):
        alive = {
            team for m in played if m.stage == stage for team in (m.home_club_id, m.away_club_id)
        }
        away = rules.absentees(season.tests, season.squads, day)
        assert set(away.values()) == alive
        for match in (m for m in season.matches if m.date == day):
            assert not set(away) & {*match.home_lineup, *match.away_lineup}


# --- API : un monde de vrais clubs (le Top 14 seul, pour aller vite) -------------------------


@pytest.fixture
def nations() -> Iterator[tuple[TestClient, sessionmaker]]:
    engine = conftest.test_engine()
    Base.metadata.create_all(engine)
    TestSession = sessionmaker(bind=engine, expire_on_commit=False)
    with TestSession() as session:
        clubs = generate_real_clubs(random.Random(0), [league("top14")])
        session.add_all(ClubRow.from_domain(club) for club in clubs)
        session.commit()

    def override_get_session() -> Iterator[Session]:
        with TestSession() as session:
            yield session

    app.dependency_overrides[get_session] = override_get_session
    app.dependency_overrides[current_user] = conftest.full_account
    yield TestClient(app), TestSession
    app.dependency_overrides.clear()


def club_id(client: TestClient, name: str) -> int:
    return next(club["id"] for club in client.get("/clubs").json() if club["name"] == name)


def test_invented_world_has_no_internationals(manager):
    assert manager.get("/internationals").json()["windows"] == []
    assert manager.get("/internationals/nations").json() == []
    refused = manager.post("/career", json={"manager_name": "Max", "nation": "FRA"})
    assert refused.status_code == 400


def test_club_career_sees_the_international_calendar_and_its_called_up_players(nations):
    client, _ = nations
    toulouse = club_id(client, "Stade Toulousain")
    assert (
        client.post("/career", json={"manager_name": "Max", "club_id": toulouse}).status_code == 201
    )

    calendar = client.get("/internationals").json()
    assert [w["code"] for w in calendar["windows"]] == [
        "rugby_championship",
        "pacific_nations",
        "autumn",
        "november_tests",
        "six_nations",
        "rugby_europe",
        "sudamericano",
        "africa_cup",
        "asia",
    ]
    championship, autumn = calendar["windows"][0], calendar["windows"][2]
    # Le Rugby Championship commence avant le Top 14 : ses listes sont déjà publiées.
    assert championship["announced"] and not autumn["announced"]
    assert calendar["today"] == "2026-08-15"

    squad = client.get(f"/clubs/{toulouse}").json()["players"]
    assert all(player["nationality"] for player in squad)
    pumas = [p for p in squad if p["duty"] and p["duty"]["nation"]["code"] == "ARG"]
    assert pumas
    # Toulouse reçoit le 5 septembre, jour de Rugby Championship : doublon.
    assert all(p["duty"]["away"] and "2026-09-05" in p["duty"]["dates"] for p in pumas)
    lineup = client.get(f"/clubs/{toulouse}").json()["strength"]["lineup_ids"]
    assert not {p["id"] for p in pumas} & set(lineup)

    listed = client.get("/internationals/rugby_championship/ARG").json()
    assert len(listed["players"]) == rules.SQUAD_SIZE
    assert {p["id"] for p in pumas} <= {p["player"]["id"] for p in listed["players"]}


def test_internationals_miss_the_club_match_on_a_clash_day(nations):
    client, TestSession = nations
    toulouse = club_id(client, "Stade Toulousain")
    client.post("/career", json={"manager_name": "Max", "club_id": toulouse})
    pumas = {
        p["id"]
        for p in client.get(f"/clubs/{toulouse}").json()["players"]
        if p["duty"] and p["duty"]["away"]
    }

    played = client.post("/seasons/current/play").json()

    assert played["played"]["date"] == "2026-09-05"
    with TestSession() as session:
        match = session.scalars(
            select(MatchRow).where(
                MatchRow.squad == "pro",
                MatchRow.date == datetime.date(2026, 9, 5),
                MatchRow.home_club_id == toulouse,
            )
        ).one()
        assert len(match.home_lineup) == len(SLOT_POSITIONS) and not pumas & set(match.home_lineup)
        tests = session.scalars(
            select(InternationalRow).where(
                InternationalRow.home_score.is_not(None),
                InternationalRow.competition == "rugby_championship",
            )
        ).all()
        # Trois samedis de Rugby Championship sont passés (15 et 22 août, 5 septembre).
        assert len(tests) == 6


def test_new_lists_are_announced_to_the_club_manager(nations):
    client, _ = nations
    toulouse = club_id(client, "Stade Toulousain")
    client.post("/career", json={"manager_name": "Max", "club_id": toulouse})

    notices = []
    while not notices:
        played = client.post("/seasons/current/play").json()
        notices = played["call_ups"]
        assert played["played"]["date"] < "2026-11-14"

    # Les listes d'automne tombent deux semaines avant le premier test (14 novembre).
    assert played["played"]["date"] == "2026-10-24"
    assert {n["competition"] for n in notices} == {"Tournées d'automne", "Tests de novembre"}
    notice = next(n for n in notices if n["competition"] == "Tournées d'automne")
    assert {called["nation"]["code"] for called in notice["players"]} >= {"FRA"}
    # Seul le dernier test (28 novembre) tombe un jour de Top 14.
    assert notice["doublons"] == ["2026-11-28"]


def test_the_world_ranking_moves_with_the_tests(nations):
    client, _ = nations
    toulouse = club_id(client, "Stade Toulousain")
    client.post("/career", json={"manager_name": "Max", "club_id": toulouse})
    start = client.get("/internationals/ranking").json()
    assert start["updated"] is None and start["recent"] == []
    assert len(start["nations"]) == 36 and start["nations"][0]["nation"]["code"] == "RSA"
    assert [n["rank"] for n in start["nations"]] == list(range(1, 37))

    client.post("/seasons/current/play")  # 5 septembre : Rugby Championship et Pacifique
    ranking = client.get("/internationals/ranking").json()
    assert ranking["updated"] == "2026-09-05"
    assert {m["competition"] for m in ranking["recent"]} >= {"Rugby Championship"}
    # Le classement se refait à chaque test : ce que l'un gagne, l'autre le perd.
    total = sum(n["points"] for n in ranking["nations"])
    assert total == pytest.approx(sum(n["points"] for n in start["nations"]), abs=0.1)
    latest = ranking["recent"][0]
    home = next(n for n in ranking["nations"] if n["nation"]["id"] == latest["home"]["id"])
    assert home["points"] - home["previous_points"] == pytest.approx(latest["change"], abs=0.02)


def test_world_awards_count_the_tests_and_crown_the_first_nation(nations, monkeypatch):
    client, TestSession = nations
    toulouse = club_id(client, "Stade Toulousain")
    client.post("/career", json={"manager_name": "Max", "club_id": toulouse})
    for _ in range(3):
        client.post("/seasons/current/play")
    with TestSession() as session:
        played = session.scalars(
            select(InternationalRow).where(InternationalRow.home_score.is_not(None))
        ).all()
        # Les tests gardent les notes des joueurs.
        assert played and all(row.stats for row in played)
    # Des seuils bas : la saison ne fait que commencer.
    monkeypatch.setattr("engine.world_awards.PLAYER_MATCHES", 2)
    monkeypatch.setattr("engine.world_awards.INTERNATIONAL_MATCHES", 1)
    world = client.get("/honours/world").json()
    assert world["year"] == 2026 and not world["finished"]
    kinds = [award["kind"] for award in world["awards"]]
    assert {"player", "international", "tries", "points", "tackles"} <= set(kinds)
    assert kinds.count("team") == 15
    international = next(a for a in world["awards"] if a["kind"] == "international")
    assert international["tests"] >= 1 and international["nation"] is not None
    ranking = client.get("/internationals/ranking").json()["nations"]
    assert world["best_nation"]["nation"]["code"] == ranking[0]["nation"]["code"]
    assert world["climber"]["change"] >= 0


# --- API : carrière de sélectionneur --------------------------------------------------------


@pytest.fixture
def selector(nations) -> tuple[TestClient, sessionmaker]:
    """Sélectionneur de la Nouvelle-Zélande : son premier rendez-vous ouvre la saison."""
    client, TestSession = nations
    created = client.post("/career", json={"manager_name": "Max", "nation": "nzl"})
    assert created.status_code == 201
    return client, TestSession


def test_selector_career_replaces_the_club_career(selector):
    client, _ = selector
    career = client.get("/career").json()
    assert career["kind"] == "nation" and career["nation"] == "NZL"
    assert career["club_id"] == NEW_ZEALAND.id and career["club_name"] == "Nouvelle-Zélande"
    assert client.get("/finances").status_code == 404  # aucun club à gérer
    nations = client.get("/internationals/nations").json()
    assert len(nations) == 36 and all(n["player_count"] >= rules.SQUAD_SIZE for n in nations)
    # Du premier au dernier du classement mondial.
    assert [n["rank"] for n in nations] == list(range(1, 37))
    assert nations[0]["code"] == "RSA" and nations[0]["points"] > nations[-1]["points"]
    assert client.post("/career", json={"manager_name": "Max"}).status_code == 400
    assert client.post("/career", json={"manager_name": "Max", "nation": "XXX"}).status_code == 404


def test_the_list_must_be_announced_before_time_moves_on(selector):
    client, TestSession = selector
    state = client.get("/selection").json()
    assert state["phase"] == "list" and not state["list_announced"]
    assert state["window"]["code"] == "rugby_championship"
    assert client.post("/selection/advance").status_code == 400
    assert client.post("/live").status_code == 400

    pool = client.get("/selection/pool").json()
    suggested = pool["suggested"]
    assert len(suggested) == pool["size"] == 42 and not pool["announced"]
    assert client.post("/selection/list", json={"player_ids": suggested[:-1]}).status_code == 400
    assert (
        client.post("/selection/list", json={"player_ids": [*suggested[:-1], 10**6]}).status_code
        == 400
    )

    # On remplace un joueur de la proposition du staff par un autre du même poste.
    by_id = {entry["player"]["id"]: entry["player"] for entry in pool["players"]}
    dropped = by_id[suggested[0]]
    swapped_in = next(
        p
        for p in by_id.values()
        if p["id"] not in suggested and p["position"] == dropped["position"]
    )
    mine = [swapped_in["id"], *suggested[1:]]
    announced = client.post("/selection/list", json={"player_ids": mine})
    assert announced.status_code == 201 and announced.json()["selected"] == mine
    assert client.post("/selection/list", json={"player_ids": mine}).status_code == 400

    with TestSession() as session:
        call = session.scalars(select(CallUpRow).where(CallUpRow.nation == "NZL")).one()
        assert call.player_ids == mine and call.competition == "rugby_championship"
    state = client.get("/selection").json()
    assert state["phase"] == "match" and state["list_announced"]
    assert state["next_match"]["date"] == "2026-08-15"


def announce_staff_list(client: TestClient) -> list[int]:
    suggested = client.get("/selection/pool").json()["suggested"]
    assert client.post("/selection/list", json={"player_ids": suggested}).status_code == 201
    return suggested


def test_selector_picks_his_xv_and_plays_the_match(selector):
    client, TestSession = selector
    listed = announce_staff_list(client)

    team = client.get("/selection/team").json()
    assert team["name"] == "Nouvelle-Zélande" and len(team["players"]) == 42
    lineup = team["strength"]["lineup_ids"]
    assert len(lineup) == 15 and set(lineup) <= set(listed) and not team["lineup_custom"]
    # Le remplaçant le mieux noté prend la place du titulaire à son poste.
    by_id = {p["id"]: p for p in team["players"]}
    index = 9  # demi d'ouverture
    starter = by_id[lineup[index]]
    backup = next(
        p for p in team["players"] if p["position"] == starter["position"] and p["id"] not in lineup
    )
    choice = [None] * 15
    choice[index] = backup["id"]
    changed = client.put("/selection/lineup", json={"player_ids": choice}).json()
    assert changed["lineup_custom"] and changed["strength"]["lineup_ids"][index] == backup["id"]
    outsider = max(by_id) + 10_000
    assert (
        client.put("/selection/lineup", json={"player_ids": [outsider] + [None] * 14}).status_code
        == 400
    )

    played = client.post("/selection/advance")
    assert played.status_code == 200
    result = played.json()
    assert (
        result["date"] == "2026-08-15" and len(result["tests"]) == 2 and result["club_matches"] == 0
    )
    mine = next(m for m in result["tests"] if NEW_ZEALAND.id in (m["home"]["id"], m["away"]["id"]))
    assert mine["home_score"] is not None
    assert result["selection"]["record"]["played"] == 1
    with TestSession() as session:
        row = session.get(InternationalRow, mine["id"])
        ours = row.home_lineup if row.home_id == NEW_ZEALAND.id else row.away_lineup
        assert ours[index] == backup["id"]

    assert client.delete("/selection/lineup").json()["lineup_custom"] is False


def test_selector_plays_his_match_live(selector, monkeypatch):
    # Les dilemmes du sélectionneur arrêteraient le chrono : testés à part (test_live.py).
    monkeypatch.setattr(dilemmas, "COACH_DILEMMA_CHANCE", 0.0)
    client, _ = selector
    announce_staff_list(client)

    live = client.post("/live")
    assert live.status_code == 201
    match = live.json()
    assert match["my_club_id"] == NEW_ZEALAND.id
    assert {match["home"]["club"]["name"], match["away"]["club"]["name"]} == {
        "Nouvelle-Zélande",
        "Argentine",
    }
    assert len(match["home"]["players"]) == 23

    advanced = client.post("/live/advance", json={"minutes": 40}).json()
    assert advanced["minute"] == 40
    assert client.post("/live/tactics", json={"game_plan": "kicking"}).status_code == 200
    assert client.get("/live").json()["minute"] == 40

    finished = client.post("/live/finish")
    assert finished.status_code == 200
    result = finished.json()
    assert result["date"] == "2026-08-15" and result["selection"]["record"]["played"] == 1
    assert client.get("/live").status_code == 404
    # Le match a bien été joué une seule fois : celui du direct.
    mine = next(m for m in result["tests"] if NEW_ZEALAND.id in (m["home"]["id"], m["away"]["id"]))
    assert mine["id"] == match["match_id"]


def test_an_injured_player_can_be_replaced_in_the_list(selector):
    client, TestSession = selector
    listed = announce_staff_list(client)
    pool = client.get("/selection/pool").json()
    spare = next(e["player"]["id"] for e in pool["players"] if e["player"]["id"] not in listed)

    refused = client.post("/selection/replace", json={"player_out": listed[0], "player_in": spare})
    assert refused.status_code == 400  # il n'est pas blessé : la liste est annoncée

    with TestSession() as session:
        player = session.get(PlayerRow, listed[0]).to_domain()
        injury = new_injury(
            player,
            Club(id=0, name=""),
            InjurySource.TRAINING,
            datetime.date(2026, 8, 10),
            random.Random(8),
        )
        injury.return_date = datetime.date(2026, 12, 1)
        session.add(InjuryRow.from_domain(injury))
        session.commit()

    replaced = client.post("/selection/replace", json={"player_out": listed[0], "player_in": spare})
    assert replaced.status_code == 200
    assert replaced.json()["selected"] == [spare, *listed[1:]]


def test_selector_follows_the_whole_season_before_the_next_one(selector):
    client, _ = selector
    announce_staff_list(client)
    assert client.post("/seasons/next").status_code == 400
    assert client.post("/seasons/current/play").status_code == 400  # il avance jour par jour

    # Jusqu'au bout du Rugby Championship, puis la liste d'automne est réclamée.
    dates = []
    while (state := client.get("/selection").json())["phase"] != "list":
        dates.append(client.post("/selection/advance").json()["date"])
    assert state["window"]["code"] == "autumn" and state["record"]["played"] == 6
    assert dates[0] == "2026-08-15" and state["today"] == "2026-10-31"
    championship = client.get("/internationals").json()["windows"][0]
    assert championship["finished"] and championship["champion"] is not None
    assert [row["played"] for row in championship["standings"]] == [6, 6, 6, 6]


def test_selector_season_review(selector):
    client, _ = selector
    assert client.get("/selection/review").status_code == 400
    while (state := client.get("/selection").json())["phase"] != "finished":
        if state["phase"] == "list":
            announce_staff_list(client)
        assert client.post("/selection/advance").status_code == 200
    review = client.get("/selection/review").json()
    assert review["nation"]["code"] == "NZL" and review["record"] == state["record"]
    record = review["record"]
    assert record["won"] + record["drawn"] + record["lost"] == record["played"] > 0
    # Le Rugby Championship (un classement), puis la tournée d'automne (aucun).
    championship, autumn = review["competitions"]
    assert championship["code"] == "rugby_championship" and championship["teams"] == 4
    assert 1 <= championship["rank"] <= 4
    assert (championship["result"] == "champion") == (
        championship["champion"]["id"] == NEW_ZEALAND.id
    )
    assert autumn["rank"] is None and autumn["result"] is None
    assert (
        sum(c["won"] + c["drawn"] + c["lost"] for c in review["competitions"]) == record["played"]
    )
    assert len(review["scorers"]) <= 3 and len(review["caps"]) == 5
    assert review["caps"][0]["starts"] <= record["played"]


# --- API : une saison de Coupe du monde -----------------------------------------------------


@pytest.fixture
def world_cup_year(nations, monkeypatch) -> tuple[TestClient, sessionmaker]:
    """Le monde démarre en 2027, saison de Coupe du monde."""
    monkeypatch.setattr("api.routers.career.FIRST_SEASON_YEAR", 2027)
    return nations


def test_club_career_lives_through_a_world_cup(world_cup_year):
    client, _ = world_cup_year
    toulouse = club_id(client, "Stade Toulousain")
    client.post("/career", json={"manager_name": "Max", "club_id": toulouse})

    calendar = client.get("/internationals").json()
    assert [w["code"] for w in calendar["windows"]] == [
        "world_cup",
        "six_nations",
        "rugby_europe",
        "sudamericano",
        "africa_cup",
        "asia",
    ]
    cup = calendar["windows"][0]
    assert [pool["name"] for pool in cup["pools"]] == [f"Poule {x}" for x in "ABCDEF"]
    assert all(len(pool["standings"]) == 4 for pool in cup["pools"]) and cup["standings"] == []
    assert len(cup["nations"]) == 24 and len(cup["matches"]) == 36
    # Les sept samedis sont connus d'avance, les affiches des tours suivants non.
    assert cup["dates"] == [day.isoformat() for day in world_cup_saturdays(2027)]
    assert cup["announced"] and calendar["today"] == "2027-09-11"

    # La première journée de Top 14 tombe le dernier samedi des poules : doublon.
    season = client.get("/seasons/current").json()
    assert season["next_matchday"]["date"] == "2027-09-25"
    away = [p for p in client.get(f"/clubs/{toulouse}").json()["players"] if p["duty"]]
    assert away and all(p["duty"]["away"] for p in away)
    assert {p["duty"]["competition"] for p in away} == {"Coupe du monde"}

    played = client.post("/seasons/current/play").json()
    assert played["played"]["date"] == "2027-09-25"
    cup = client.get("/internationals").json()["windows"][0]
    last_16 = [m for m in cup["matches"] if m["stage"] == "last16"]
    assert len(last_16) == 8 and {m["date"] for m in last_16} == {"2027-10-02"}
    assert all(m["neutral"] for m in last_16) and not cup["finished"]

    for _ in range(4):
        assert client.post("/seasons/current/play").status_code == 200
    cup = client.get("/internationals").json()["windows"][0]
    assert cup["finished"] and cup["champion"] is not None
    final = next(m for m in cup["matches"] if m["stage"] == "final")
    assert cup["champion"]["id"] in (final["home"]["id"], final["away"]["id"])
    assert (final["home_score"], final["home_shootout"]) != (
        final["away_score"],
        final["away_shootout"],
    )


def test_selector_takes_his_nation_to_the_world_cup(world_cup_year):
    client, _ = world_cup_year
    assert client.post("/career", json={"manager_name": "Max", "nation": "RUS"}).status_code == 404
    assert client.post("/career", json={"manager_name": "Max", "nation": "FRA"}).status_code == 201

    state = client.get("/selection").json()
    assert state["phase"] == "list" and state["window"]["code"] == "world_cup"
    assert len(state["window"]["pools"]) == 6
    announce_staff_list(client)
    state = client.get("/selection").json()
    assert state["phase"] == "match" and state["next_match"]["neutral"]

    # Les trois matchs de poule ; ensuite un huitième si la France est sortie de sa poule.
    for _ in range(3):
        result = client.post("/selection/advance").json()
    state = result["selection"]
    assert state["record"]["played"] == 3
    cup = client.get("/internationals").json()["windows"][0]
    pool = next(p for p in cup["pools"] if FRANCE.id in [row["club_id"] for row in p["standings"]])
    rank = next(row["rank"] for row in pool["standings"] if row["club_id"] == FRANCE.id)
    qualified = state["window"]["code"] == "world_cup"
    assert qualified or rank >= 3
    if qualified:
        assert state["next_match"]["stage"] == "last16"
        live = client.post("/live").json()
        assert live["knockout"] and live["stage"] == "last16"
    else:
        assert state["window"]["code"] == "six_nations"

    # Jusqu'au bout de la saison : le bilan donne la place en poule et le tour atteint.
    while (state := client.get("/selection").json())["phase"] != "finished":
        if state["phase"] == "list":
            announce_staff_list(client)
        if client.get("/live").status_code == 200:
            client.post("/live/finish")
        assert client.post("/selection/advance").status_code == 200
    world_cup = client.get("/selection/review").json()["competitions"][0]
    assert world_cup["code"] == "world_cup" and world_cup["rank"] == rank
    assert world_cup["teams"] == 4
    assert (world_cup["result"] == "pools") == (not qualified)


# --- Parties d'avant les sélections ---------------------------------------------------------


def test_old_saves_get_their_players_nationality_back(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'ancienne.db'}")
    Base.metadata.create_all(engine)
    with sessionmaker(bind=engine)() as session:
        clubs = generate_real_clubs(random.Random(0), [league("top14")])
        session.add_all(ClubRow.from_domain(club) for club in clubs)
        session.commit()
    with engine.begin() as connection:
        connection.execute(text("ALTER TABLE players DROP COLUMN nationality"))

    init_db(engine)

    with sessionmaker(bind=engine)() as session:
        dupont = session.scalars(
            select(PlayerRow).where(
                PlayerRow.first_name == "Antoine", PlayerRow.last_name == "Dupont"
            )
        ).one()
        assert dupont.nationality == "FRA"
        foreigners = session.scalars(
            select(PlayerRow).where(PlayerRow.nationality.not_in(["FRA"]))
        ).all()
        assert foreigners  # les étrangers du Top 14 gardent leur pays
        assert session.scalars(select(PlayerRow).where(PlayerRow.nationality.is_(None))).all() == []
    assert home_nation("Stade Toulousain") == "FRA" and home_nation("RC Port-Vasor") is None


def test_old_saves_get_the_stage_of_their_internationals(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'ancienne.db'}")
    Base.metadata.create_all(engine)
    with sessionmaker(bind=engine)() as session:
        session.add(SeasonRow(id=1, year=2026, seed=1))
        session.flush()
        for match in rules.schedule(2026)[:2]:
            session.add(InternationalRow.from_domain(match, 1))
        session.commit()
    with engine.begin() as connection:
        connection.execute(text("ALTER TABLE internationals DROP COLUMN stage"))

    init_db(engine)

    with sessionmaker(bind=engine)() as session:
        rows = session.scalars(select(InternationalRow)).all()
        assert len(rows) == 2 and {row.stage for row in rows} == {"regular"}
        assert rows[0].to_domain().stage == Stage.REGULAR
