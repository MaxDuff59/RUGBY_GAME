"""Le marché des clubs IA en cours de saison : pré-contrats, prêts et agents libres."""

import datetime
import random
from collections import Counter

from data.generator import generate_player
from engine.market import LENDER_MIN_SQUAD, MAX_INCOMING, Market, cover
from engine.match_engine import RATING_FOR_POSITION
from engine.transfers import DealKind
from models import Club, Injury, InjurySeverity, InjurySource, Player, Position
from tests.conftest import make_club

DAY = datetime.date(2026, 11, 7)
YEAR = 2026
NINE = Position.SCRUM_HALF


class Always(random.Random):
    """Un hasard qui dit toujours oui : chaque club agit, chaque joueur est approché."""

    def random(self) -> float:
        return 0.0


def market(clubs: list[Club], pool: list[Player] = (), **fields) -> Market:
    fields.setdefault("late", set())
    fields.setdefault("active", {"top14"})
    for club in clubs:
        for player in club.players:
            player.contract_until = YEAR + 2
    return Market(clubs=clubs, pool=list(pool), day=DAY, season_year=YEAR, **fields)


def injure(player: Player, weeks: int) -> None:
    player.injury = Injury(
        player.id,
        InjurySeverity.SEVERE,
        "entorse du genou",
        InjurySource.MATCH,
        occurred_on=DAY - datetime.timedelta(days=1),
        base_weeks=weeks,
        return_date=DAY + datetime.timedelta(weeks=weeks),
    )


def halves(club: Club) -> list[Player]:
    """Les demis de mêlée du club, du meilleur au moins bon."""
    return sorted(club.players_at(NINE), key=RATING_FOR_POSITION[NINE], reverse=True)


def free_agent(player_id: int, level: float, position: Position = NINE) -> Player:
    player = generate_player(player_id, position, level, None, random.Random(player_id))
    player.contract_until = YEAR - 1
    return player


# --- Prêts et agents libres ------------------------------------------------------------------


def test_a_club_short_at_a_position_borrows_a_reserve():
    borrower, lender = make_club(1, level=9, seed=1), make_club(2, level=13, seed=2)
    injure(halves(borrower)[0], weeks=8)
    # Le prêteur a trois demis de mêlée : le troisième ne joue pas.
    lender.players.append(generate_player(299, NINE, 13, 2, random.Random(9)))
    reserve = halves(lender)[-1]
    place = market([borrower, lender])

    [deal] = place.reinforcements(Always())
    assert deal.kind == DealKind.LOAN and deal.player is reserve
    assert (deal.origin, deal.destination) == (lender, borrower)
    assert reserve in borrower.players and reserve not in lender.players
    assert (reserve.club_id, reserve.loaned_from) == (1, 2)
    # Le poste est de nouveau couvert : rien de plus la semaine suivante.
    assert place.reinforcements(Always()) == []


def test_a_lender_keeps_enough_players_for_itself():
    borrower, lender = make_club(1, level=9, seed=1), make_club(2, level=13, seed=2)
    injure(halves(borrower)[0], weeks=8)
    # Deux demis de mêlée seulement : titulaire et doublure, rien à prêter.
    assert len(lender.players_at(NINE)) == cover(NINE)
    assert market([borrower, lender]).reinforcements(Always()) == []

    # Trois, mais un effectif trop mince pour s'en séparer.
    lender.players.append(generate_player(299, NINE, 13, 2, random.Random(9)))
    others = [p for p in lender.players if p.position != NINE]
    lender.players = lender.players_at(NINE) + others[: LENDER_MIN_SQUAD - 3]
    assert len(lender.players) == LENDER_MIN_SQUAD
    deals = market([borrower, lender]).reinforcements(Always())
    assert [deal for deal in deals if deal.origin is lender] == []


def test_a_league_out_of_season_does_not_recruit():
    borrower, lender = make_club(1, level=9, seed=1), make_club(2, level=13, seed=2)
    injure(halves(borrower)[0], weeks=8)
    lender.players.append(generate_player(299, NINE, 13, 2, random.Random(9)))
    assert market([borrower, lender], active=set()).reinforcements(Always()) == []


def test_a_long_injury_brings_a_medical_joker():
    club = make_club(1, level=11, seed=1)
    injure(halves(club)[0], weeks=20)
    good, weak = free_agent(901, 12), free_agent(902, 3)
    place = market([club], [weak, good, free_agent(903, 12, Position.PROP)])

    [deal] = place.reinforcements(Always())
    assert deal.kind == DealKind.JOKER and deal.player is good and deal.origin is None
    assert good in club.players and good not in place.pool
    # Sous contrat jusqu'à la fin de la saison, au salaire d'un agent libre.
    assert (good.club_id, good.contract_until, good.wage) == (1, YEAR, deal.wage)
    assert deal.wage >= 40_000


def test_a_weak_free_agent_is_not_worth_signing():
    club = make_club(1, level=13, seed=1)
    injure(halves(club)[0], weeks=20)
    place = market([club], [free_agent(902, 3)])
    assert place.reinforcements(Always()) == []
    assert len(place.pool) == 1


def test_a_short_absence_changes_nothing():
    club = make_club(1, level=11, seed=1)
    injure(halves(club)[0], weeks=3)
    assert market([club], [free_agent(901, 12)]).reinforcements(Always()) == []


# --- Pré-contrats ----------------------------------------------------------------------------


def star_of(club: Club) -> Player:
    """Le meilleur demi de mêlée du club, mis en dernière année de contrat."""
    star = halves(club)[0]
    star.contract_until = YEAR
    return star


def test_a_player_in_his_last_year_signs_where_he_would_play():
    small, big = make_club(1, level=11, seed=1), make_club(2, level=12, seed=2)
    place = market([small, big], late={"top14"})
    star = star_of(small)
    for name in ("passing", "handling", "pace"):
        setattr(star, name, 20)  # il serait titulaire partout

    [deal] = place.approaches(Always())
    assert deal.kind == DealKind.PRECONTRACT and deal.player is star
    assert (deal.origin, deal.destination) == (small, big)
    assert 1 <= deal.years <= 4 and deal.wage <= star.wage * 1.3
    # Rien ne bouge avant l'intersaison ; le joueur n'est plus sur le marché.
    assert star in small.players and star.club_id == 1
    assert place.incoming == Counter({2: 1}) and star.id in place.taken
    assert place.approaches(Always()) == []


def test_precontracts_wait_for_the_second_half_of_the_season():
    small, big = make_club(1, level=11, seed=1), make_club(2, level=12, seed=2)
    place = market([small, big], late=set())
    star_of(small)
    assert place.approaches(Always()) == []


def test_a_player_already_committed_or_in_talks_is_left_alone():
    small, big = make_club(1, level=11, seed=1), make_club(2, level=12, seed=2)
    place = market([small, big], late={"top14"})
    place.taken.add(star_of(small).id)
    assert place.approaches(Always()) == []


def test_a_club_signs_only_so_many_players_for_next_season():
    small, big = make_club(1, level=11, seed=1), make_club(2, level=12, seed=2)
    place = market([small, big], late={"top14"}, incoming=Counter({2: MAX_INCOMING}))
    star_of(small)
    assert place.approaches(Always()) == []


def test_a_reserve_elsewhere_does_not_sign():
    big, small = make_club(1, level=14, seed=1), make_club(2, level=9, seed=2)
    place = market([small, big], late={"top14"})
    # Le moins bon demi de mêlée du petit club ne jouerait pas dans le grand.
    worst = halves(small)[-1]
    worst.contract_until = YEAR
    for name in ("passing", "handling", "pace", "kicking", "tackling"):
        setattr(worst, name, 2)
    assert [d for d in place.approaches(Always()) if d.destination is big] == []


# --- Dans une partie -------------------------------------------------------------------------


def by_player(listings: list[dict]) -> dict[int, dict]:
    return {listing["player"]["id"]: listing for listing in listings}


def play_season(client) -> None:
    while client.get("/seasons/current").json()["phase"] != "finished":
        client.post("/seasons/current/play")


def test_ai_clubs_deal_with_each_other_during_the_season(manager):
    play_season(manager)
    moves = manager.get("/journal").json()["moves"]
    between = [
        m
        for m in moves
        if 3 not in ((m["origin"] or {}).get("id"), (m["destination"] or {}).get("id"))
    ]
    # Des pré-contrats signés entre clubs IA attendent l'intersaison.
    pending = [m for m in between if m["pending"]]
    assert pending and all(m["kind"] == "precontract" for m in pending)
    assert all(m["origin"]["id"] != m["destination"]["id"] for m in pending)

    # Le manager ne peut plus signer ces joueurs, seulement les emprunter.
    listings = by_player(manager.get("/transfers").json()["listings"])
    move = pending[0]
    listing = listings[move["player"]["id"]]
    assert listing["signed_with"] == move["destination"]["name"]
    assert not listing["precontract"] and listing["transfer_fee"] is None
    target = manager.get(f"/transfers/{move['player']['id']}").json()
    options = {option["kind"]: option for option in target["options"]}
    for kind in ("transfer", "precontract"):
        assert not options[kind]["available"] and "déjà engagé" in options[kind]["reason"]
    refused = manager.post(f"/transfers/{move['player']['id']}/open", json={"kind": "precontract"})
    assert refused.status_code == 400

    # À l'intersaison, chacun rejoint le club avec qui il a signé.
    assert manager.post("/seasons/next").status_code == 201
    listings = by_player(manager.get("/transfers").json()["listings"])
    for move in pending:
        arrived = listings.get(move["player"]["id"])
        if arrived is not None:  # sinon il a raccroché entre-temps
            assert arrived["club_id"] == move["destination"]["id"]
            assert arrived["signed_with"] is None
