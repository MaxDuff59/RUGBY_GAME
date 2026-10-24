"""Tests des règlements : plafond salarial et JIFF."""

from engine import regulations
from engine.match_engine import team_strength
from engine.regulations import cap_breach, cap_room, is_jiff, jiff_min, payroll
from models import StaffMember, StaffRole
from tests.conftest import make_club


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
