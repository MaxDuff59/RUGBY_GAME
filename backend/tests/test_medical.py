"""Blessures : règles médicales, moteur de match et routes de l'infirmerie."""

import random
from datetime import date, timedelta

import pytest

from engine.match_engine import select_lineup, simulate_match
from engine.medical import (
    INJURY_KINDS,
    apply_protocol,
    new_injury,
    planned_weeks,
    protocol_cost,
    relapse_risk,
    training_injuries,
)
from models import (
    FRAGILE_WEEKS,
    EventType,
    Injury,
    InjurySeverity,
    InjurySource,
    Position,
    Protocol,
    StaffMember,
    StaffRole,
)
from tests.conftest import make_club

DAY = date(2026, 9, 5)


def injure(player, weeks: int, on: date = DAY, risk: float = 0.0) -> Injury:
    """Attache une blessure (protocole fixé) à un joueur, pour les tests."""
    player.injury = Injury(
        player_id=player.id,
        severity=InjurySeverity.MODERATE,
        kind="entorse du genou",
        source=InjurySource.MATCH,
        occurred_on=on,
        base_weeks=weeks,
        return_date=on + timedelta(weeks=weeks),
        relapse_risk=risk,
    )
    return player.injury


def with_staff(club, role: StaffRole, level: int):
    club.staff.append(StaffMember(len(club.staff) + 1, "A", "B", role, level, 1, club.id))
    return club


# --- Règles -------------------------------------------------------------------------


def test_protocols_trade_duration_for_relapse_risk():
    cautious = planned_weeks(10, Protocol.CAUTIOUS, physio_level=1)
    standard = planned_weeks(10, Protocol.STANDARD, physio_level=1)
    accelerated = planned_weeks(10, Protocol.ACCELERATED, physio_level=1)
    assert cautious > standard > accelerated >= 1
    assert (
        relapse_risk(Protocol.CAUTIOUS, 1)
        < relapse_risk(Protocol.STANDARD, 1)
        < relapse_risk(Protocol.ACCELERATED, 1)
    )
    # Seul le retour anticipé coûte, et de plus en plus cher avec la gravité.
    assert protocol_cost(InjurySeverity.SEVERE, Protocol.STANDARD) == 0
    assert protocol_cost(InjurySeverity.LIGHT, Protocol.ACCELERATED) < protocol_cost(
        InjurySeverity.SEVERE, Protocol.ACCELERATED
    )


def test_physio_shortens_and_doctor_protects():
    assert planned_weeks(10, Protocol.STANDARD, physio_level=5) < planned_weeks(
        10, Protocol.STANDARD, physio_level=1
    )
    assert relapse_risk(Protocol.STANDARD, 5) < relapse_risk(Protocol.STANDARD, 1)
    # Une blessure dure toujours au moins une semaine.
    assert planned_weeks(1, Protocol.ACCELERATED, physio_level=5) == 1


def test_new_injury_kind_matches_its_severity():
    club = make_club(1, level=12)
    rng = random.Random(0)
    for _ in range(50):
        player = rng.choice(club.players)
        injury = new_injury(player, club, InjurySource.MATCH, DAY, rng)
        kinds = [k for k, _, _ in INJURY_KINDS[injury.severity]]
        assert injury.kind in kinds
        assert injury.return_date > DAY
        assert player.injury is injury
        assert not injury.relapse


def test_protocol_choice_is_definitive():
    club = make_club(1, level=12)
    injury = new_injury(
        club.players[0], club, InjurySource.MATCH, DAY, random.Random(0), decided=False
    )
    standard_return = injury.return_date
    apply_protocol(injury, Protocol.ACCELERATED, club)
    assert injury.protocol_chosen
    assert injury.return_date <= standard_return
    with pytest.raises(ValueError):
        apply_protocol(injury, Protocol.CAUTIOUS, club)


def test_fragile_player_relapses_with_the_same_injury():
    club = make_club(1, level=12)
    player = club.players[0]
    previous = injure(player, weeks=6, on=DAY - timedelta(weeks=7))
    assert player.is_fragile(DAY) and not player.is_injured(DAY)

    injury = new_injury(player, club, InjurySource.MATCH, DAY, random.Random(0))
    assert injury.relapse
    assert injury.kind == previous.kind
    assert injury.severity == previous.severity


def test_training_injures_a_few_available_players():
    club = make_club(1, level=12)
    injured_before = injure(club.players[0], weeks=4)
    rng = random.Random(1)
    injuries = [i for week in range(40) for i in training_injuries(club, DAY, rng)]
    # ~0,12 par semaine : quelques-unes sur une saison, pas des dizaines.
    assert 1 <= len(injuries) <= 15
    assert all(i.source == InjurySource.TRAINING for i in injuries)
    assert all(i.occurred_on < DAY for i in injuries)
    # Le joueur déjà blessé ne s'entraîne pas, donc ne se reblesse pas.
    assert all(i is not injured_before for i in injuries)


# --- Moteur de match -----------------------------------------------------------------


def test_injured_players_are_not_lined_up(even_clubs):
    club, _ = even_clubs
    best_prop = select_lineup(club, DAY)[0]
    assert best_prop.position == Position.PROP
    injure(best_prop, weeks=4)

    assert best_prop not in select_lineup(club, DAY)
    assert best_prop in select_lineup(club, DAY + timedelta(weeks=4))  # le jour du retour
    assert best_prop in select_lineup(club)  # sans date, on ignore les blessures
    assert len(select_lineup(club, DAY)) == 15


def test_matches_injure_a_plausible_number_of_players(even_clubs):
    home, away = even_clubs
    rng = random.Random(0)
    injuries = 0
    for _ in range(300):
        match = simulate_match(home, away, rng=rng, day=DAY)
        events = [e for e in match.events if e.type == EventType.INJURY]
        injuries += len(events)
        assert all(e.points == 0 for e in events)
        # Un joueur ne se blesse qu'une fois par match.
        assert len({e.player_id for e in events}) == len(events)
    # ~0,6 blessé par équipe et par match.
    assert 0.3 * 600 <= injuries <= 1.0 * 600


def test_fragile_players_get_injured_more_often(even_clubs):
    home, away = even_clubs
    fragile = select_lineup(home, DAY)[0]
    control = select_lineup(home, DAY)[1]
    injure(fragile, weeks=6, on=DAY - timedelta(weeks=6), risk=0.25)
    assert fragile.is_fragile(DAY)
    assert DAY + timedelta(weeks=FRAGILE_WEEKS) == fragile.injury.fragile_until

    rng = random.Random(0)
    hits = {fragile.id: 0, control.id: 0}
    for _ in range(400):
        match = simulate_match(home, away, rng=rng, day=DAY)
        for event in match.events:
            if event.type == EventType.INJURY and event.player_id in hits:
                hits[event.player_id] += 1
    assert hits[fragile.id] > 3 * hits[control.id]


def test_same_seed_gives_same_injuries(even_clubs):
    home, away = even_clubs
    first = simulate_match(home, away, rng=random.Random(5), day=DAY)
    second = simulate_match(home, away, rng=random.Random(5), day=DAY)
    assert first == second


# --- API -----------------------------------------------------------------------------


def _play_until_injured(manager, max_matchdays: int = 21) -> dict:
    """Joue des journées jusqu'à ce que le club dirigé ait un blessé (protocole à choisir).

    On ignore les blessures d'une semaine : le joueur serait déjà de retour à la
    journée suivante, donc plus à l'infirmerie.
    """
    for _ in range(max_matchdays):
        result = manager.post("/seasons/current/play").json()
        result["injuries"] = [c for c in result["injuries"] if c["injury"]["weeks_total"] >= 2]
        if result["injuries"]:
            return result
    pytest.fail("aucun blessé sur toute une saison : très improbable")


def test_medical_page_needs_a_career(client):
    assert client.get("/medical").status_code == 404


def test_medical_is_empty_at_the_start(manager):
    medical = manager.get("/medical").json()
    assert medical["injured"] == [] and medical["fragile"] == [] and medical["history"] == []
    assert medical["available"] == medical["squad_size"] == 31
    assert 1 <= medical["physio_level"] <= 5


def test_injured_player_leaves_the_lineup_and_the_manager_picks_a_protocol(manager):
    result = _play_until_injured(manager)
    case = result["injuries"][0]
    assert case["injury"]["status"] == "active"
    assert not case["injury"]["protocol_chosen"]
    assert [o["protocol"] for o in case["options"]] == ["cautious", "standard", "accelerated"]

    # L'infirmerie le liste, l'effectif le signale, le XV s'en passe.
    medical = manager.get("/medical").json()
    assert any(c["injury"]["id"] == case["injury"]["id"] for c in medical["injured"])
    assert medical["available"] < medical["squad_size"]
    club = manager.get("/clubs/3").json()
    player = next(p for p in club["players"] if p["id"] == case["player"]["id"])
    assert player["injury"]["status"] == "active"
    assert player["id"] not in club["strength"]["lineup_ids"]

    # Retour anticipé : plus tôt, plus risqué, payant, et définitif.
    accelerated = next(o for o in case["options"] if o["protocol"] == "accelerated")
    standard = next(o for o in case["options"] if o["protocol"] == "standard")
    assert accelerated["return_date"] <= standard["return_date"]
    assert accelerated["relapse_risk"] > standard["relapse_risk"]
    assert accelerated["cost"] > 0 and accelerated["affordable"]

    balance_before = medical["balance"]
    chosen = manager.post(f"/medical/{case['injury']['id']}/protocol/accelerated").json()
    updated = next(
        c
        for c in chosen["injured"] + chosen["fragile"]
        if c["injury"]["id"] == case["injury"]["id"]
    )
    assert updated["injury"]["protocol"] == "accelerated"
    assert updated["injury"]["protocol_chosen"] and updated["options"] == []
    assert updated["injury"]["return_date"] == accelerated["return_date"]
    assert chosen["balance"] == balance_before - accelerated["cost"]
    labels = [t["label"] for t in manager.get("/finances").json()["transactions"]]
    assert any(label.startswith("Soins · ") for label in labels)
    assert manager.post(f"/medical/{case['injury']['id']}/protocol/cautious").status_code == 400


def test_free_protocols_stay_available_when_broke(manager):
    from api.routers.medical import _options
    from models import Club

    club = Club(id=3, name="Fauché", balance=-500_000)
    injury = new_injury(
        make_club(3, level=12).players[0],
        club,
        InjurySource.MATCH,
        DAY,
        random.Random(0),
        decided=False,
    )
    affordable = {o.protocol: o.affordable for o in _options(injury, club, club.balance)}
    assert affordable[Protocol.CAUTIOUS] and affordable[Protocol.STANDARD]
    assert not affordable[Protocol.ACCELERATED]


def test_cannot_treat_another_club_injury(manager):
    for _ in range(3):
        manager.post("/seasons/current/play")
    others = manager.get("/clubs/1").json()["players"]
    foreign = next((p["injury"]["id"] for p in others if p["injury"]), None)
    if foreign is None:
        pytest.skip("pas de blessé dans le club 1 après trois journées")
    assert manager.post(f"/medical/{foreign}/protocol/standard").status_code == 404


def test_injuries_heal_over_the_season(manager):
    result = _play_until_injured(manager)
    injury = result["injuries"][0]["injury"]
    for _ in range(21):
        if manager.post("/seasons/current/play").status_code != 200:
            break
    medical = manager.get("/medical").json()
    everything = medical["injured"] + medical["fragile"] + medical["history"]
    found = next(c for c in everything if c["injury"]["id"] == injury["id"])
    # Une blessure légère ou modérée est guérie bien avant la fin de saison.
    if injury["severity"] != "severe":
        assert found["injury"]["status"] in ("fragile", "healed")
        assert found["injury"]["weeks_left"] == 0
