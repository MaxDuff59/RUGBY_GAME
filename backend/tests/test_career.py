"""Tests de la carrière du manager : réputation, passages dans les clubs, offres, et
son contrat."""

import random

from api.deps import get_session
from api.main import app
from engine import manager_contract as terms
from engine.career import (
    Season,
    label,
    nation_offer,
    offers,
    prestige,
    reach,
    reachable,
    reputation,
)
from models.orm import CareerRow, TransactionRow


def _season(champion=False, playoffs=False, rank=6, expected=6):
    return Season(2026, 1, champion, playoffs, rank, expected)


def test_reputation_grows_with_titles_and_falls_with_dismissals():
    beginner = reputation([], 0)
    assert beginner == 30 and label(beginner) == "Espoir du banc"
    good = reputation([_season(playoffs=True, rank=3, expected=6)], 0)
    champion = reputation([_season(champion=True, playoffs=True, rank=1, expected=4)], 0)
    assert beginner < good < champion
    assert reputation([_season()], 1) < reputation([_season()], 0)
    assert 0 <= reputation([_season(rank=14, expected=1)] * 10, 5) <= 100


def test_a_bigger_reputation_reaches_bigger_clubs():
    assert reach(30) == 0 < reach(60) < reach(90)
    assert prestige(12, "top14") > prestige(12, "prod2")
    candidates = {cid: 10 + cid * 0.5 for cid in range(1, 12)}  # de 10,5 à 15,5
    assert offers(11.0, candidates, 30, random.Random(0)) == []  # inconnu : personne
    star = offers(11.0, candidates, 100, random.Random(0))
    assert star and all(candidates[cid] > 11.0 for cid in star) and len(star) <= 3
    assert star == offers(11.0, candidates, 100, random.Random(0))  # mêmes offres


def test_leaving_before_the_end_of_a_contract_costs_reputation():
    assert reputation([], 0, 1) == reputation([], 0) - 5


def test_only_a_known_manager_is_called_by_a_nation():
    nations = {"FRA": 16.9, "ITA": 15.1, "FIJ": 14.8}
    assert nation_offer(14.0, nations, 59, random.Random(0)) is None
    rngs = [random.Random(seed) for seed in range(30)]
    called = {nation_offer(14.0, nations, 70, rng) for rng in rngs} - {None}
    assert called and called <= {"ITA", "FIJ"}  # la France est hors de portée


def test_a_free_manager_reaches_clubs_up_to_his_last_one():
    candidates = {1: 9.0, 2: 12.0, 3: 14.0}
    assert reachable(12.0, candidates, 30) == [1, 2]
    assert reachable(12.0, candidates, 70) == [1, 2, 3]


def test_the_board_grants_extensions_by_its_support():
    assert terms.support(12, 10) == 12
    assert terms.support(12, 18) > 12 > terms.support(12, 10, demand=1.5)
    assert terms.grant(16, left=1) == 3
    assert terms.grant(13, left=1) == 2
    assert terms.grant(10.5, left=1) == 1
    assert terms.grant(9, left=1) == 0
    assert terms.grant(16, left=3) == 1  # quatre saisons sous contrat au plus
    assert terms.answer(2, 3) == terms.Answer("accepted", 2)
    assert terms.answer(3, 1) == terms.Answer("countered", 1)
    assert terms.answer(1, 0) == terms.Answer("refused", 0)
    assert terms.remaining(2027, 2026, finished=False) == 2
    assert terms.remaining(2027, 2027, finished=True) == 0


# --- API -------------------------------------------------------------------------------


def test_the_career_follows_the_manager(manager):
    history = manager.get("/career/history").json()
    assert history["reputation"] == 30
    assert [s["club"]["id"] for s in history["spells"]] == [3]
    assert history["spells"][0]["end"] is None
    assert history["offers"] == []  # pas avant la fin de la saison
    assert history["seasons"][0]["rank"] is None  # saison en cours
    assert manager.post("/career/offers/4").status_code == 400


def test_accepting_an_offer_moves_the_manager(manager, monkeypatch):
    from api import careers

    for _ in range(21):  # toute la saison, phases finales comprises
        manager.post("/seasons/current/play")
    history = manager.get("/career/history").json()
    assert history["seasons"][0]["rank"] is not None
    monkeypatch.setattr(careers, "offers", lambda session, reputation=None, clubs=None: {5: 12.0})
    career = manager.post("/career/offers/5").json()
    assert career["club_id"] == 5
    history = manager.get("/career/history").json()
    assert [(s["club"]["id"], s["reason"]) for s in history["spells"]] == [(3, "left"), (5, None)]
    # Il arrive au début de la saison suivante : ni bilan, ni nouvelles offres. La
    # saison passée reste au crédit de l'ancien club.
    season = manager.get("/seasons/current").json()
    assert season["year"] == 2027 and season["phase"] != "finished"
    assert [(s["year"], s["club"]["id"]) for s in history["seasons"]] == [(2027, 5), (2026, 3)]
    assert history["offers"] == []


def _support(monkeypatch, value):
    """La direction appuie le manager à `value` (sur 20)."""
    monkeypatch.setattr(terms, "support", lambda board, fervour, demand=0.0: value)


def _db():
    return next(app.dependency_overrides[get_session]())


def _play(client, matchdays):
    for _ in range(matchdays):
        client.post("/seasons/current/play")


def test_a_new_manager_signs_for_two_seasons(manager):
    assert manager.get("/career").json()["contract_until"] == 2027
    contract = manager.get("/career/contract").json()
    assert contract["seasons_left"] == 2 and not contract["expiring"]
    assert contract["renewal"] is None
    assert contract["blocked"] == "too_soon"  # la direction veut le voir à l'œuvre
    assert contract["indemnity"] == 2 * terms.INDEMNITY_PER_SEASON
    assert manager.post("/career/contract/extend", json={"seasons": 1}).status_code == 400


def test_asking_for_an_extension(manager, monkeypatch):
    _play(manager, terms.ASK_AFTER_MATCHES)
    assert manager.get("/career/contract").json()["max_ask"] == 2  # quatre saisons au plus
    assert manager.post("/career/contract/extend", json={"seasons": 3}).status_code == 400
    _support(monkeypatch, 10.5)  # une saison au plus
    countered = manager.post("/career/contract/extend", json={"seasons": 2}).json()
    assert (countered["outcome"], countered["seasons"]) == ("countered", 1)
    accepted = manager.post("/career/contract/extend", json={"seasons": 1}).json()
    assert accepted["outcome"] == "accepted" and accepted["contract"]["until"] == 2028
    _support(monkeypatch, 16)
    again = manager.post("/career/contract/extend", json={"seasons": 1}).json()
    assert again["contract"]["until"] == 2029
    assert again["contract"]["blocked"] == "too_long"


def test_a_refusal_closes_the_door_for_a_while(manager, monkeypatch):
    _play(manager, terms.ASK_AFTER_MATCHES)
    _support(monkeypatch, 8)
    refused = manager.post("/career/contract/extend", json={"seasons": 1}).json()
    assert refused["outcome"] == "refused"
    assert refused["contract"]["blocked"] == "refused"
    assert refused["contract"]["retry_on"] is not None
    _support(monkeypatch, 18)
    assert manager.post("/career/contract/extend", json={"seasons": 1}).status_code == 400


def _expiring(client):
    """Le contrat s'achève avec la saison en cours, jouée jusqu'au bout."""
    session = _db()
    session.query(CareerRow).one().contract_until = 2026
    session.commit()
    _play(client, 21)  # toute la saison, phases finales comprises


def test_an_ending_contract_must_be_settled(manager, monkeypatch):
    _expiring(manager)
    _support(monkeypatch, 11)
    contract = manager.get("/career/contract").json()
    assert contract["expiring"] and contract["renewal"] == 1
    assert contract["resign_cost"] == 0
    response = manager.post("/seasons/next")
    assert response.status_code == 400 and "contrat" in response.json()["detail"]
    renewed = manager.post("/career/contract/extend", json={"seasons": 1}).json()
    assert renewed["outcome"] == "accepted" and renewed["contract"]["until"] == 2027
    assert manager.post("/seasons/next").status_code == 201


def test_the_board_may_let_an_ending_contract_go(manager, monkeypatch):
    _expiring(manager)
    _support(monkeypatch, 6)
    assert manager.get("/career/contract").json()["renewal"] == 0
    before = manager.get("/career/history").json()["reputation"]
    assert manager.post("/career/leave").json()["reason"] == "expired"
    departure = manager.get("/career/dismissal").json()
    assert departure["reason"] == "expired"
    manager.post("/career", json={"manager_name": "Maxence", "club_id": departure["reachable"][0]})
    history = manager.get("/career/history").json()
    assert history["reputation"] == before  # parti au bout de son contrat : rien à redire
    assert [s["reason"] for s in history["spells"]] == ["expired", None]
    # Il reprend un club pour la saison suivante, sous contrat pour deux saisons.
    assert manager.get("/seasons/current").json()["year"] == 2027
    assert manager.get("/career").json()["contract_until"] == 2028


def test_resigning_mid_contract(manager):
    departure = manager.post("/career/leave").json()
    assert departure["reason"] == "resigned" and departure["club_id"] == 3
    assert manager.get("/career").status_code == 404
    reachable_ids = manager.get("/career/dismissal").json()["reachable"]
    assert 3 not in reachable_ids
    out_of_reach = [cid for cid in range(1, 11) if cid not in reachable_ids and cid != 3]
    if out_of_reach:
        refused = manager.post(
            "/career", json={"manager_name": "Maxence", "club_id": out_of_reach[0]}
        )
        assert refused.status_code == 400
    # Un autre manager, sans passé, choisit librement.
    assert manager.post("/career", json={"manager_name": "Autre", "club_id": 3}).status_code == 201


def test_resigning_costs_reputation(manager):
    manager.post("/career/leave")
    club_id = manager.get("/career/dismissal").json()["reachable"][0]
    manager.post("/career", json={"manager_name": "Maxence", "club_id": club_id})
    history = manager.get("/career/history").json()
    assert history["reputation"] == 25
    assert [s["reason"] for s in history["spells"]] == ["resigned", None]


def test_a_club_pays_to_hire_a_manager_under_contract(manager, monkeypatch):
    from api import careers

    _play(manager, 21)
    monkeypatch.setattr(careers, "offers", lambda session, reputation=None, clubs=None: {5: 12.0})
    offer = manager.get("/career/history").json()["offers"][0]
    assert offer["seasons"] == 2 and offer["indemnity"] == terms.INDEMNITY_PER_SEASON
    career = manager.post("/career/offers/5").json()
    assert career["contract_until"] == 2028  # deux saisons, à partir de la prochaine
    fees = {
        row.club_id: row.amount
        for row in _db().query(TransactionRow).filter(TransactionRow.label.like("Indemnit%"))
    }
    assert fees == {3: terms.INDEMNITY_PER_SEASON, 5: -terms.INDEMNITY_PER_SEASON}


def test_a_nation_can_hire_the_manager(manager, monkeypatch):
    from api import careers

    code = "FRA"
    _play(manager, 21)
    monkeypatch.setattr(
        careers, "nation_offer", lambda session, reputation=None, clubs=None: (code, 16.0)
    )
    offer = manager.get("/career/history").json()["offers"][-1]
    assert offer["kind"] == "nation" and offer["nation"] == code and offer["seasons"] is None
    assert manager.post("/career/offers/nation/ITA").status_code == 400
    career = manager.post(f"/career/offers/nation/{code}").json()
    assert career["kind"] == "nation" and career["nation"] == code
    assert manager.get("/career").json()["kind"] == "nation"
