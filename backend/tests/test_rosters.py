"""Vrais effectifs : un club connu de data/rosters.json reçoit ses vrais joueurs."""

import random

from data.generator import REAL_SQUAD_CAP, generate_real_clubs
from data.leagues import league
from engine.economy import SQUAD_MIN
from models import Position, Squad

POSITIONS = ["prop"] * 10 + ["hooker"] * 4 + ["lock"] * 6 + ["back_row"] * 9
POSITIONS += ["scrum_half"] * 3 + ["fly_half"] * 3 + ["centre"] * 5 + ["wing"] * 5 + ["fullback"]


def roster(pros: list[dict], youths: list[dict] | None = None) -> dict:
    return {"Stade Toulousain": {"pros": pros, "youths": youths or []}}


def pro(i: int, position: str, **extra) -> dict:
    return {"name": f"Joueur Réel{i}", "position": position, "international": False, **extra}


def toulouse(rosters: dict, released: list | None = None):
    clubs = generate_real_clubs(random.Random(0), [league("top14")], rosters, released)
    return next(c for c in clubs if c.name == "Stade Toulousain"), clubs


def test_a_known_club_gets_its_real_players_with_their_age():
    pros = [pro(i, pos) for i, pos in enumerate(POSITIONS[:31])]
    pros[0] = pro(0, "prop", born="1996-11-15", international=True, photo="Joueur Réel.jpg")
    club, clubs = toulouse(roster(pros, [pro(100, "wing", born="2006-03-01")]))
    names = {p.name for p in club.players}
    assert {f"Joueur Réel{i}" for i in range(31)} <= names
    first = next(p for p in club.players if p.name == "Joueur Réel0")
    assert (first.first_name, first.last_name, first.age) == ("Joueur", "Réel0", 29)
    assert first.photo == "/photos/Joueur_R%C3%A9el.jpg"
    youth = next(p for p in club.youths if p.name == "Joueur Réel100")
    assert youth.squad == Squad.YOUTH and youth.age == 20
    # Les autres clubs, absents du fichier, restent inventés.
    other = next(c for c in clubs if c.name == "RC Toulon")
    assert not any(p.name.startswith("Joueur Réel") for p in other.players)


def test_an_oversized_squad_is_trimmed_young_to_academy_others_released():
    pros = [pro(i, pos, born="1995-01-01") for i, pos in enumerate(POSITIONS)]
    pros += [pro(200 + i, "back_row", born="2007-01-01") for i in range(3)]
    released = []
    club, _ = toulouse(roster(pros), released)
    assert len(club.players) == REAL_SQUAD_CAP
    kept = {p.name for p in club.players + club.youths} | {p.name for p in released}
    assert {f"Joueur Réel{200 + i}" for i in range(3)} <= {p.name for p in club.youths}
    assert all(p.club_id is None and p.age > 21 for p in released)
    assert len(kept & {e["name"] for e in pros}) == len(pros)  # personne ne disparaît


def test_missing_positions_are_filled_with_invented_players():
    pros = [pro(i, "prop") for i in range(6)] + [pro(10 + i, "back_row") for i in range(6)]
    club, _ = toulouse(roster(pros))
    counts = {pos: sum(p.position == pos for p in club.players) for pos in Position}
    assert counts[Position.FULLBACK] >= 1 and counts[Position.SCRUM_HALF] >= 2
    assert len(club.players) >= SQUAD_MIN
    assert all(counts[pos] >= 1 for pos in Position)


def test_internationals_are_rated_above_their_teammates_on_average():
    pros = [
        pro(i, pos, international=i % 2 == 0, born="1995-01-01")
        for i, pos in enumerate(POSITIONS[:32])
    ]
    club, _ = toulouse(roster(pros))
    by_name = {p.name: p.overall for p in club.players}
    caps = [by_name[f"Joueur Réel{i}"] for i in range(0, 32, 2)]
    others = [by_name[f"Joueur Réel{i}"] for i in range(1, 32, 2)]
    assert sum(caps) / len(caps) > sum(others) / len(others) + 0.5


def test_outside_backs_without_fullback_give_some_fullbacks():
    positions = [p if p != "fullback" else "wing" for p in POSITIONS]  # 6 « ailiers »
    pros = [pro(i, pos) for i, pos in enumerate(positions)]
    club, _ = toulouse(roster(pros))
    real_fullbacks = [
        p for p in club.players if p.position == Position.FULLBACK and "Réel" in p.name
    ]
    assert len(real_fullbacks) == 2  # le dernier tiers des ailiers


def test_reserve_players_too_old_for_the_academy_are_left_out():
    pros = [pro(i, pos) for i, pos in enumerate(POSITIONS[:31])]
    youths = [pro(300, "wing", born="2006-01-01"), pro(301, "wing", born="1998-01-01")]
    club, _ = toulouse(roster(pros, youths))
    names = {p.name for p in club.youths}
    assert "Joueur Réel300" in names and "Joueur Réel301" not in names
