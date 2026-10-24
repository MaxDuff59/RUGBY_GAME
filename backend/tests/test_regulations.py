"""Tests des règlements : plafond salarial (club dirigé et clubs IA) et JIFF."""

import random

from data.generator import generate_real_clubs
from engine import regulations
from engine.free_agents import RELEASE_FLOOR, ai_pick, settle_contracts
from engine.match_engine import team_strength
from engine.regulations import (
    cap_breach,
    cap_room,
    committed_payroll,
    fit_under_cap,
    fits_next_season,
    is_jiff,
    jiff_min,
    payroll,
    salary_cap,
)
from engine.transfers import DealKind
from models import StaffMember, StaffRole
from tests.conftest import make_club
from tests.test_market import Always, free_agent, halves, injure, market, star_of


def _french_club(foreigners: int, league: str = "top14"):
    club = make_club(1, 12, seed=4)
    club.league = league
    club.staff = [StaffMember(1, "Jean", "Coach", StaffRole.FORWARDS_COACH, 3, 50_000, club.id)]
    # Les meilleurs sont étrangers : le staff les alignerait tous sans la règle.
    ranked = sorted(club.players, key=lambda p: p.overall, reverse=True)
    for index, player in enumerate(ranked):
        player.nationality = "NZL" if index < foreigners else "FRA"
    return club


def test_only_french_leagues_have_a_jiff_rule():
    assert jiff_min(_french_club(0)) == 14
    assert jiff_min(_french_club(0, league="urc")) == 0
    club = _french_club(0)
    club.staff = []  # une sélection, les espoirs
    assert jiff_min(club) == 0


def test_the_match_sheet_keeps_enough_jiff():
    club = _french_club(foreigners=15)
    team = team_strength(club)
    sheet = team.lineup + team.bench
    assert sum(is_jiff(p) for p in sheet) >= 14
    assert len({p.id for p in sheet}) == len(sheet)  # personne deux fois


def test_without_enough_jiff_the_staff_does_its_best():
    club = _french_club(foreigners=25)  # il ne reste que quelques Français
    french = sum(is_jiff(p) for p in club.players)
    team = team_strength(club)
    assert sum(is_jiff(p) for p in team.lineup + team.bench) == min(french, 23)


def test_the_salary_cap_blocks_what_goes_over():
    club = _french_club(0)
    room = cap_room(club)
    assert room == regulations.SALARY_CAP["top14"] - payroll(club)
    assert cap_breach(club, room) is None
    assert cap_breach(club, room + 1) == (regulations.SALARY_CAP["top14"] + 1, 7_800_000)
    club.league = "urc"
    assert cap_room(club) is None and cap_breach(club, 10**9) is None


# --- API -------------------------------------------------------------------------------


def test_promotion_over_the_cap_is_refused(manager, monkeypatch):
    academy = manager.get("/academy").json()
    youth = academy["youths"][0]["id"]
    finances = manager.get("/finances").json()
    assert finances["salary_cap"] == regulations.SALARY_CAP["top14"]
    monkeypatch.setitem(regulations.SALARY_CAP, "top14", finances["player_wages"])
    response = manager.post(f"/academy/promote/{youth}")
    assert response.status_code == 400 and "Plafond salarial" in response.json()["detail"]
    strength = manager.get("/clubs/3").json()["strength"]
    assert strength["jiff_min"] == 14 and len(strength["bench_ids"]) == 8


# --- Les clubs gérés par le jeu ----------------------------------------------------------


def _at_the_cap(club_id: int, level: float, seed: int, room: int = 10_000):
    """Un club du Top 14 dont la masse salariale arrive à `room` euros du plafond."""
    club = make_club(club_id, level, seed=seed)
    club.league = "top14"
    club.players[0].wage += cap_room(club) - room
    return club


def test_the_generated_clubs_start_under_the_cap():
    clubs = generate_real_clubs(random.Random(0))
    for club in clubs:
        assert cap_breach(club, 0) is None and (cap_room(club) is None or cap_room(club) >= 0)
    # Les vrais effectifs les plus chers ont dû renégocier.
    assert any(cap_room(c) is not None and cap_room(c) < 0.05 * salary_cap(c.league) for c in clubs)


def test_an_ai_club_at_the_cap_signs_no_one():
    club = _at_the_cap(1, 11, seed=1)
    injure(halves(club)[0], weeks=20)
    place = market([club], [free_agent(901, 12)])
    assert place.reinforcements(Always()) == []
    # Avec de la place sous le plafond, le joker signe.
    club.players[0].wage -= 1_000_000
    assert [d.kind for d in place.reinforcements(Always())] == [DealKind.JOKER]


def test_a_precontract_must_fit_next_seasons_cap():
    small, big = make_club(1, level=11, seed=1), make_club(2, level=12, seed=2)
    place = market([small, big], late={"top14"})
    star = star_of(small)
    for name in ("passing", "handling", "pace"):
        setattr(star, name, 20)
    big.players[0].wage += regulations.SALARY_CAP["top14"] - committed_payroll(big, 2026)
    assert place.approaches(Always()) == []
    big.players[0].wage -= 2_000_000
    [deal] = place.approaches(Always())
    assert deal.destination is big
    assert fits_next_season(big, 2026, 0, place.incoming_wages[big.id])


def test_over_the_cap_an_ai_club_lets_players_go_then_renegotiates():
    club = _at_the_cap(1, 12, seed=3, room=-600_000)
    for player in club.players:
        player.contract_until = 2026 + (player.id % 2)  # la moitié en fin de contrat
    leaving = settle_contracts(club, 2027, random.Random(1))
    assert sum(p.wage for p in leaving) >= 600_000 or len(club.players) <= RELEASE_FLOOR
    # Plus personne à laisser partir : les salaires baissent pour passer sous le plafond.
    over = _at_the_cap(2, 12, seed=4, room=-600_000)
    changed = fit_under_cap(over)
    assert changed and payroll(over) <= regulations.SALARY_CAP["top14"]
    assert fit_under_cap(over) == []


def test_the_offseason_pool_only_brings_what_fits():
    club = make_club(1, 12, seed=5)
    club.league = "top14"
    club.players = club.players[:20]
    club.players[0].wage += cap_room(club) - 30_000
    pool = [free_agent(900 + i, 12) for i in range(5)]
    assert ai_pick(club, pool) is None
    club.players[0].wage -= 1_000_000
    assert ai_pick(club, pool) in pool
