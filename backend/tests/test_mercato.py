"""Tests du mercato d'été : les clubs IA s'achètent des joueurs entre eux."""

import random

from engine import regulations
from engine.match_engine import FORMATION, RATING_FOR_POSITION
from engine.mercato import BUDGET_SHARE, summer_market
from models import ATTRIBUTE_NAMES, Position
from tests.conftest import make_club

YEAR = 2027


def _clubs(buyer_level: float, seller_level: float, balance: int = 20_000_000):
    buyer, seller = make_club(1, buyer_level, seed=1), make_club(2, seller_level, seed=2)
    for club in (buyer, seller):
        club.balance = balance
        for player in club.players:
            player.contract_until = YEAR + 1
    return buyer, seller


def _star_prop(seller):
    """Un pilier du vendeur, nettement meilleur que tous ceux de l'acheteur."""
    prop = seller.players_at(Position.PROP)[-1]
    for name in ATTRIBUTE_NAMES:
        setattr(prop, name, min(20, getattr(prop, name) + 5))
    return prop


def test_a_weak_club_buys_a_starter_from_a_deep_squad():
    buyer, seller = _clubs(12, 12)
    _star_prop(seller)
    before = buyer.balance + seller.balance
    [deal] = [d for d in summer_market([buyer, seller], YEAR, random.Random(0)) if d.buyer is buyer]
    player, position = deal.player, deal.player.position
    assert player in buyer.players and player not in seller.players
    assert (player.club_id, player.wage) == (buyer.id, deal.wage)
    assert player.contract_until == YEAR + deal.years - 1
    # L'indemnité passe d'un club à l'autre, dans le budget de l'acheteur.
    assert buyer.balance + seller.balance == before
    assert deal.fee <= BUDGET_SHARE * (buyer.balance + deal.fee)
    # Le vendeur garde ses titulaires et une doublure ; la recrue est titulaire.
    assert len(seller.players_at(position)) >= FORMATION[position] + 1
    rating = RATING_FOR_POSITION[position]
    ranked = sorted(buyer.players_at(position), key=rating, reverse=True)
    assert player in ranked[: FORMATION[position]]


def test_no_money_no_deal():
    buyer, seller = _clubs(12, 12, balance=0)
    _star_prop(seller)
    assert [
        d for d in summer_market([buyer, seller], YEAR, random.Random(0)) if d.buyer is buyer
    ] == []


def test_the_hemispheres_do_not_trade():
    buyer, seller = _clubs(12, 12)
    _star_prop(seller)
    seller.league = "super_rugby"
    assert summer_market([buyer, seller], YEAR, random.Random(0)) == []


def test_the_buyer_stays_under_the_cap():
    buyer, seller = _clubs(12, 12)
    _star_prop(seller)
    buyer.players[0].wage += regulations.cap_room(buyer) - 1_000
    deals = summer_market([buyer, seller], YEAR, random.Random(0))
    assert [d for d in deals if d.buyer is buyer] == []
    assert regulations.cap_breach(buyer, 0) is None


def test_the_summer_market_in_a_game(manager):
    """À l'intersaison, des clubs IA s'achètent des joueurs : l'indemnité passe au grand
    livre des deux clubs, le club dirigé n'est pas concerné."""
    from sqlalchemy import select

    from models.orm import MoveRow, TransactionRow
    from tests.test_jokers import db

    while manager.get("/seasons/current").json()["phase"] != "finished":
        manager.post("/seasons/current/play")
    for line in manager.get("/contracts").json()["pros"]:
        manager.post(f"/contracts/{line['player']['id']}/extend", json={"years": 2})
    assert manager.post("/seasons/next").status_code == 201
    session = db()
    moves = session.scalars(select(MoveRow).where(MoveRow.kind == "transfer")).all()
    assert moves and all(3 not in (m.from_club_id, m.to_club_id) for m in moves)
    sales = session.scalars(
        select(TransactionRow).where(TransactionRow.label.like("Vente · %"))
    ).all()
    buys = session.scalars(
        select(TransactionRow).where(TransactionRow.label.like("Achat · %"))
    ).all()
    assert len(sales) == len(buys) == len(moves)
    assert sum(t.amount for t in sales) == -sum(t.amount for t in buys) > 0
