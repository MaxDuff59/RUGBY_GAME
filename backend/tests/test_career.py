"""Tests de la carrière du manager : réputation, passages dans les clubs, offres."""

import random

from engine.career import Season, label, offers, prestige, reach, reputation


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
    monkeypatch.setattr(careers, "offers", lambda session, reputation=None: {5: 12.0})
    career = manager.post("/career/offers/5").json()
    assert career["club_id"] == 5
    history = manager.get("/career/history").json()
    assert [(s["club"]["id"], s["reason"]) for s in history["spells"]] == [(3, "left"), (5, None)]
    # La saison passée reste au crédit de l'ancien club.
    assert history["seasons"][0]["club"]["id"] == 3
