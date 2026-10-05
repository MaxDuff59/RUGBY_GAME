"""Joker médical : recrutement pendant une longue blessure, fin de pige, avis."""

from datetime import date, timedelta

from sqlalchemy import select

from api.ledger import game_date
from api.main import app
from database import get_session
from engine.medical import allows_joker
from models import Injury, InjurySeverity, InjurySource
from models.orm import InjuryRow, PlayerRow

DAY = date(2026, 10, 1)


def injury(weeks: int) -> Injury:
    return Injury(
        player_id=1,
        severity=InjurySeverity.SEVERE,
        kind="rupture des ligaments croisés",
        source=InjurySource.MATCH,
        occurred_on=DAY,
        base_weeks=weeks,
        return_date=DAY + timedelta(weeks=weeks),
    )


def test_only_absences_over_three_months_allow_a_joker():
    assert allows_joker(injury(16), DAY + timedelta(weeks=2))
    assert not allows_joker(injury(13), DAY)  # trois mois tout juste
    assert not allows_joker(injury(16), DAY + timedelta(weeks=16))  # il est revenu


# --- Routes -------------------------------------------------------------------------


def db():
    return next(app.dependency_overrides[get_session]())


def injure_long(manager, weeks: int = 16) -> tuple[int, int]:
    """Blesse le meilleur pro du club 3 pour `weeks` semaines : (joueur, blessure)."""
    session = db()
    day = game_date(session)
    player = max(
        session.scalars(select(PlayerRow).where(PlayerRow.club_id == 3, PlayerRow.squad == "pro")),
        key=lambda p: p.to_domain().overall,
    )
    row = InjuryRow(
        player_id=player.id,
        severity="severe",
        kind="rupture des ligaments croisés",
        source="match",
        occurred_on=day - timedelta(days=1),
        base_weeks=weeks,
        return_date=day - timedelta(days=1) + timedelta(weeks=weeks),
        protocol="standard",
        protocol_chosen=True,
    )
    session.add(row)
    session.commit()
    return player.id, row.id


def sign_joker(manager, injury_id: int) -> int:
    market = manager.get("/transfers").json()
    free = next(listing for listing in market["listings"] if listing["free_agent"])
    player_id = free["player"]["id"]
    target = manager.get(f"/transfers/{player_id}").json()
    option = next(o for o in target["options"] if o["kind"] == "joker")
    assert option["available"] and option["injury_id"] == injury_id
    opened = manager.post(
        f"/transfers/{player_id}/open", json={"kind": "joker", "injury_id": injury_id}
    ).json()
    answer = manager.post(
        f"/transfers/negotiations/{opened['id']}/offer", json={"wage": opened["wage_demand"]}
    ).json()
    assert answer["concluded"], answer["message"]
    return player_id


def test_no_joker_without_a_long_injury(manager):
    assert manager.get("/transfers").json()["joker_slots"] == []
    injure_long(manager, weeks=8)
    assert manager.get("/transfers").json()["joker_slots"] == []


def test_a_joker_comes_on_top_of_the_squad(manager):
    injured_id, injury_id = injure_long(manager)
    market = manager.get("/transfers").json()
    assert [slot["injury_id"] for slot in market["joker_slots"]] == [injury_id]
    case = next(
        c for c in manager.get("/medical").json()["injured"] if c["player"]["id"] == injured_id
    )
    assert case["joker_allowed"] and case["joker"] is None

    joker_id = sign_joker(manager, injury_id)
    market = manager.get("/transfers").json()
    assert market["squad_size"] == 31  # le joker ne compte pas
    assert market["joker_slots"] == []  # un seul joker par blessure
    assert [j["player"]["id"] for j in market["jokers"]] == [joker_id]
    assert joker_id in {p["id"] for p in manager.get("/clubs/3").json()["players"]}
    case = next(
        c for c in manager.get("/medical").json()["injured"] if c["player"]["id"] == injured_id
    )
    assert case["joker"]["id"] == joker_id and not case["joker_allowed"]
    # Ni à vendre, ni à prolonger pendant sa pige.
    assert manager.post(f"/transfers/sell/{joker_id}").status_code == 400
    contracts = manager.get("/contracts").json()
    assert joker_id not in {c["player"]["id"] for c in contracts["pros"]}


def _end_pige(manager, injury_id: int) -> dict:
    """Le blessé revient avant la prochaine journée : renvoie l'avis de fin de pige."""
    session = db()
    row = session.get(InjuryRow, injury_id)
    row.return_date = game_date(session)
    session.commit()
    played = manager.post("/seasons/current/play").json()
    return next(a for a in played["affairs"] if a["scenario"] == "joker_end")


def test_end_of_pige_offers_a_real_contract(manager):
    _, injury_id = injure_long(manager)
    joker_id = sign_joker(manager, injury_id)
    notice = _end_pige(manager, injury_id)
    assert notice["player_id"] == joker_id
    assert "vrai contrat" in notice["text"]
    assert [o["key"] for o in notice["options"]] == ["sign", "release"]

    answered = manager.post(f"/affairs/{notice['id']}/answer", json={"choice": "sign"}).json()
    assert answered["choice"] == "sign"
    market = manager.get("/transfers").json()
    assert market["jokers"] == [] and market["squad_size"] == 32
    player = manager.get(f"/players/{joker_id}").json()
    assert player["club"]["id"] == 3 and player["player"]["contract_until"] >= 2026


def test_an_unanswered_pige_ends_with_his_departure(manager):
    _, injury_id = injure_long(manager)
    joker_id = sign_joker(manager, injury_id)
    _end_pige(manager, injury_id)
    manager.post("/seasons/current/play")  # sans réponse : il repart

    player = manager.get(f"/players/{joker_id}").json()
    assert player["club"] is None
    market = manager.get("/transfers").json()
    assert market["jokers"] == [] and market["squad_size"] == 31
    assert joker_id in {f["player"]["id"] for f in market["listings"] if f["free_agent"]}


def test_a_pige_ends_with_the_season(manager):
    _, injury_id = injure_long(manager, weeks=60)  # absent bien au-delà de la saison
    joker_id = sign_joker(manager, injury_id)
    notices = []
    while manager.get("/seasons/current").json()["phase"] != "finished":
        played = manager.post("/seasons/current/play").json()
        notices += [a for a in played["affairs"] if a["scenario"] == "joker_end"]
    assert len(notices) == 1 and "saison est finie" in notices[0]["text"]

    # Sans réponse, il repart à l'intersaison.
    assert manager.post("/seasons/next").status_code == 201
    club = manager.get(f"/players/{joker_id}").json()["club"]
    assert club is None or club["id"] != 3
    assert manager.get("/transfers").json()["jokers"] == []
