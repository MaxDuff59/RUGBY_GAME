"""Le journal : rédaction des articles (moteur), registre des mouvements et route."""

import datetime
import random
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from api.deps import get_session
from api.main import app
from api.moves import log_move
from data.generator import generate_real_clubs
from data.leagues import league
from data.nations import WINDOWS_BY_CODE
from engine import journal
from engine.journal import Article, Kind, Move, MoveKind, Person, Table
from models import EventType, Match, MatchEvent, Position, Stage, StandingRow
from models.orm import Base, ClubRow, MoveRow, PlayerRow
from tests import conftest

DAY = datetime.date(2026, 10, 3)
TOULOUSE = journal.club_team(1, "Stade Toulousain")
CASTRES = journal.club_team(2, "Castres Olympique")
TEAMS = {1: TOULOUSE, 2: CASTRES}


def played(home_tries=(), away_tries=(), home_penalties=0, away_penalties=0, **fields) -> Match:
    """Un match joué : un essai par joueur cité, et des pénalités sans buteur."""
    events = [MatchEvent(10, EventType.TRY, 1, player) for player in home_tries]
    events += [MatchEvent(20, EventType.TRY, 2, player) for player in away_tries]
    events += [MatchEvent(30, EventType.PENALTY_GOAL, 1)] * home_penalties
    events += [MatchEvent(40, EventType.PENALTY_GOAL, 2)] * away_penalties
    match = Match(1, 2, matchday=5, events=events, id=7, date=DAY, **fields)
    match.home_score, match.away_score = match.points_for(1), match.points_for(2)
    return match


# --- Les mots --------------------------------------------------------------------------------


def test_names_take_their_article_and_their_verb():
    assert TOULOUSE.does("bat", "battent") == "Stade Toulousain bat"
    # Une franchise au nom pluriel s'accorde ; seule, elle prend l'article.
    assert journal.club_team(3, "Crusaders").does("bat", "battent") == "Les Crusaders battent"
    assert journal.club_team(4, "Leicester Tigers").subject == "Leicester Tigers"
    assert journal.club_team(4, "Leicester Tigers").verb("bat", "battent") == "battent"
    assert journal.nation_team(9011, "FIJ", "Fidji").does("bat", "battent") == "Les Fidji battent"
    assert journal.nation_team(9002, "ENG", "Angleterre").subject == "l'Angleterre"


def test_small_words_follow_french_usage():
    assert journal.of("Antoine Dupont") == "d'Antoine Dupont"
    assert journal.of("Thomas Ramos") == "de Thomas Ramos"
    assert journal.short_day(datetime.date(2027, 3, 1)) == "1er mars"
    assert journal.day_label(DAY) == "samedi 3 octobre"
    assert journal.money(2_850_000) == "2,85 M€" and journal.money(40_000) == "40 k€"
    assert journal.place(1) == "1re place" and journal.place(3) == "3e place"


# --- Matchs ----------------------------------------------------------------------------------


def test_a_result_gives_the_score_and_the_player_of_the_match():
    match = played(home_tries=(7, 7, 8, 9), away_penalties=1)
    article = journal.result_article(match, TEAMS, {7: "Antoine Dupont"}, "Top 14")
    assert article.kind == Kind.RESULT and article.match is match
    assert article.title.startswith("Stade Toulousain") and "Castres Olympique" in article.title
    assert article.body.startswith("20-3, 4 essais à 0.")
    assert "Doublé d'Antoine Dupont." in article.body
    assert [team.id for team in article.teams] == [1, 2]


def test_a_draw_names_both_sides_and_no_winner():
    match = played(home_penalties=2, away_penalties=2)
    article = journal.result_article(match, TEAMS, {}, "Top 14")
    assert "Stade Toulousain" in article.title and "Castres Olympique" in article.title
    assert article.body == "6-6, sans le moindre essai."


def test_a_low_ranked_winner_makes_a_bigger_story():
    match = played(away_tries=(20, 21), home_penalties=1)
    rows = [StandingRow(club_id=club_id) for club_id in range(1, 13)]
    even = Table(rows, previous={club_id: club_id for club_id in range(1, 13)}, rounds=5)
    upset = Table(rows, previous={**even.previous, 1: 2, 2: 11}, rounds=5)
    plain = journal.result_article(match, TEAMS, {}, "Top 14", even)
    shock = journal.result_article(match, TEAMS, {}, "Top 14", upset)
    assert shock.weight > plain.weight
    assert any(word in shock.title for word in ("surprend", "tomber", "Sensation"))
    # Battu de moins de six points : le bonus défensif est signalé.
    assert "Stade Toulousain sauve le bonus défensif." not in shock.body
    close = played(away_tries=(20,), home_penalties=1)
    assert "sauve le bonus défensif" in journal.result_article(close, TEAMS, {}, "T", even).body


def test_a_final_crowns_its_winner():
    match = played(home_tries=(7,), away_penalties=1, stage=Stage.FINAL)
    article = journal.result_article(match, TEAMS, {}, "Top 14")
    assert article.title == "Stade Toulousain bat Castres Olympique et décroche le titre"
    assert article.weight > journal.result_article(played(home_tries=(7,)), TEAMS, {}, "T").weight


def test_a_preview_sets_the_fixture_in_the_table():
    match = Match(1, 2, matchday=6, id=9, date=DAY)
    rows = [StandingRow(club_id=club_id) for club_id in range(1, 15)]
    table = Table(rows, previous={}, rounds=5)
    article = journal.preview_article(match, TEAMS, "Top 14", table, {2: -3})
    assert article.kind == Kind.PREVIEW
    assert article.title == "Choc au sommet : Stade Toulousain – Castres Olympique"
    assert "1er contre 2e." in article.body
    assert "Castres Olympique reste sur 3 défaites de suite." in article.body
    assert article.body.endswith("Coup d'envoi samedi 3 octobre.")


def test_streaks_count_results_in_a_row():
    def game(day: int, home: int, away: int, score: tuple[int, int]) -> Match:
        return Match(
            home, away, home_score=score[0], away_score=score[1], id=day, date=DAY.replace(day=day)
        )

    matches = [game(3, 1, 2, (20, 10)), game(10, 2, 1, (3, 9)), game(17, 1, 3, (12, 12))]
    assert journal.streaks(matches[:2]) == {1: 2, 2: -2}
    assert journal.streaks(matches) == {1: 0, 2: -2, 3: 0}  # un nul remet la série à zéro


# --- Mouvements ------------------------------------------------------------------------------

DUPONT = Person(7, "Antoine Dupont", Position.SCRUM_HALF, 29, 16.0)


def test_a_move_reads_by_its_kind():
    def article(kind: MoveKind, **fields) -> Article:
        return journal.move_article(Move(kind, DAY, DUPONT, key="1", **fields))

    transfer = article(MoveKind.TRANSFER, origin=TOULOUSE, destination=CASTRES, fee=1_200_000)
    assert "Castres Olympique" in transfer.title and "Antoine Dupont" in transfer.title
    assert transfer.body == (
        "Le demi de mêlée de 29 ans quitte Stade Toulousain : indemnité de 1,2 M€."
    )
    signed = article(MoveKind.PRECONTRACT, origin=TOULOUSE, destination=CASTRES, pending=True)
    assert signed.title == "Antoine Dupont rejoindra Castres Olympique"
    left = article(MoveKind.FREE, origin=TOULOUSE, destination=CASTRES)
    assert left.title == "Antoine Dupont quitte Stade Toulousain pour Castres Olympique"
    assert article(MoveKind.FREE, destination=CASTRES).title == (
        "Castres Olympique engage Antoine Dupont"
    )
    retired = article(MoveKind.RETIREMENT, origin=TOULOUSE)
    assert retired.title == "Antoine Dupont raccroche les crampons"
    assert [team.id for team in retired.teams] == [1]
    # Un départ sans club pèse moins qu'une arrivée.
    assert article(MoveKind.RELEASE, origin=TOULOUSE).weight < left.weight


def test_edition_keeps_one_kind_from_filling_the_front_page():
    def story(key: str, kind: Kind, weight: float, age: int = 0) -> Article:
        return Article(key, kind, DAY - datetime.timedelta(days=age), key, "", weight)

    results = [story(f"r{i}", Kind.RESULT, 50 - i) for i in range(8)]
    others = [story("t", Kind.TRANSFER, 30), story("old", Kind.RESULT, 60, age=45)]
    ordered = journal.edition([*results, *others], DAY)
    front = ordered[: journal.FRONT_PAGE]
    assert ordered[0].key == "r0"
    assert "t" in [article.key for article in front]  # moins lourd, mais d'un autre genre
    assert "old" not in [article.key for article in front]  # une vieille nouvelle s'efface
    assert len(ordered) == 10
    # Après six semaines sans rien d'autre (intersaison), elle n'a pas vieilli.
    assert journal.edition([*results, *others], DAY, quiet=45)[0].key == "old"


# --- Registre des mouvements -----------------------------------------------------------------


def test_a_release_followed_by_a_signing_is_one_move():
    engine = conftest.test_engine()
    Base.metadata.create_all(engine)
    with sessionmaker(bind=engine)() as session:
        session.add_all([ClubRow(id=1, name="A"), ClubRow(id=2, name="B")])
        player = PlayerRow(
            id=5, first_name="Léo", last_name="Banos", age=24, position="BACK_ROW", club_id=1,
            pace=12, power=12, handling=12, passing=12, kicking=12, tackling=12, scrum=12,
            lineout=12, stamina=12,
        )  # fmt: skip
        session.add(player)
        session.commit()

        log_move(session, MoveKind.RELEASE, player, DAY, origin=1)
        log_move(session, MoveKind.FREE, player, DAY, destination=2)
        # Un autre jour : une ligne à part.
        log_move(session, MoveKind.LOAN, player, DAY + datetime.timedelta(days=30), 2, 1)
        session.commit()

        first, second = session.scalars(select(MoveRow).order_by(MoveRow.id)).all()
        assert (first.kind, first.from_club_id, first.to_club_id) == ("free", 1, 2)
        assert (first.player_name, first.overall) == ("Léo Banos", 12.0)
        assert (second.kind, second.from_club_id, second.to_club_id) == ("loan", 2, 1)


# --- La route --------------------------------------------------------------------------------


def play_season(client: TestClient) -> None:
    while client.get("/seasons/current").json()["phase"] != "finished":
        client.post("/seasons/current/play")


def test_journal_opens_on_the_coming_fixtures(manager):
    data = manager.get("/journal").json()
    assert data["focus"] == "top14" and data["moves"] == []
    # À suivre : des fins de contrat (avec leur club) puis des agents libres, par note.
    ending = [p for p in data["prospects"] if p["club"]]
    free = [p for p in data["prospects"] if not p["club"]]
    assert ending and free and data["prospects"] == ending + free
    for group in (ending, free):
        notes = [prospect["player"]["overall"] for prospect in group]
        assert notes == sorted(notes, reverse=True)
    assert all(prospect["mine"] == (prospect["club"]["id"] == 3) for prospect in ending)
    ours = [a for a in data["articles"] if a["mine"] and a["kind"] == "preview"]
    assert len(ours) == 1
    assert 3 in (ours[0]["match"]["home"]["id"], ours[0]["match"]["away"]["id"])
    assert ours[0]["match"]["home_score"] is None
    [competition] = data["competitions"]
    assert competition["last"] is None
    assert competition["next"]["label"] == "Journée 1" and len(competition["next"]["matches"]) == 5


def test_journal_leads_with_our_result(manager):
    played_day = manager.post("/seasons/current/play").json()["played"]
    data = manager.get("/journal").json()
    lead = data["articles"][0]
    assert lead["kind"] == "result" and lead["mine"]
    assert 3 in (lead["match"]["home"]["id"], lead["match"]["away"]["id"])
    assert lead["date"] == played_day["date"]
    kinds = {article["kind"] for article in data["articles"]}
    assert {"result", "preview", "standing"} <= kinds
    # Notre championnat : tous ses résultats y sont.
    assert sum(1 for a in data["articles"] if a["kind"] == "result") == 5
    [competition] = data["competitions"]
    assert competition["last"]["label"] == "Journée 1"
    assert competition["next"]["label"] == "Journée 2"
    assert len({article["id"] for article in data["articles"]}) == len(data["articles"])


def test_a_sale_makes_the_news(manager):
    player = manager.get("/clubs/3").json()["players"][0]
    assert manager.post(f"/transfers/sell/{player['id']}").status_code == 200

    data = manager.get("/journal").json()
    [move] = data["moves"]
    assert move["kind"] == "transfer" and move["mine"] and not move["pending"]
    assert move["origin"]["id"] == 3 and move["destination"]["id"] != 3
    assert move["fee"] > 0 and move["player"]["id"] == player["id"]
    [article] = [a for a in data["articles"] if a["kind"] == "transfer"]
    assert article["mine"] and article["move"]["id"] == move["id"]
    assert player["name"] in article["title"]


def test_the_offseason_fills_the_register(manager):
    play_season(manager)
    assert manager.post("/seasons/next").status_code == 201

    data = manager.get("/journal").json()
    moves = data["moves"]
    kinds = {move["kind"] for move in moves}
    # Des concurrents ont pu signer nos fins de contrat en pré-contrat pendant la saison.
    assert moves and kinds <= {"free", "release", "retirement", "precontract"}
    assert len({move["date"] for move in moves}) == 1 and moves[0]["date"] < data["today"]
    # Les mieux notés d'abord.
    notes = [move["player"]["overall"] for move in moves]
    assert notes == sorted(notes, reverse=True)
    for move in moves:
        assert not move["pending"]
        if move["kind"] == "retirement":
            assert move["player"]["id"] is None and move["destination"] is None
        elif move["kind"] == "release":
            assert move["origin"] is not None and move["destination"] is None
        else:
            assert move["destination"] is not None and move["player"]["id"] is not None
        if move["kind"] == "precontract":
            assert move["origin"]["id"] == 3 and move["mine"]
    assert any(article["kind"] == "transfer" for article in data["articles"])
    # La nouvelle saison n'a pas commencé : les affiches de la première journée.
    assert data["competitions"][0]["last"] is None


@pytest.fixture
def nations() -> Iterator[TestClient]:
    """Le Top 14 réel : des pays, donc des sélections et leurs fenêtres."""
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
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_a_selector_reads_the_journal_too(nations):
    assert nations.get("/journal").status_code == 404  # aucune saison avant la carrière
    created = nations.post("/career", json={"manager_name": "Max", "nation": "fra"})
    assert created.status_code == 201

    data = nations.get("/journal").json()
    # La France joue d'abord les tournées d'automne ; le monde s'ouvre sur le Rugby Championship.
    assert data["focus"] == "autumn"
    assert {c["code"] for c in data["competitions"]} >= {"top14", "autumn", "six_nations"}
    names = {c["code"]: c["name"] for c in data["competitions"]}
    assert names["six_nations"] == WINDOWS_BY_CODE["six_nations"].name
    tests = [a for a in data["articles"] if a["international"]]
    assert tests and all(not a["mine"] for a in tests if a["kind"] == "preview")
    lists = [a for a in data["articles"] if a["kind"] == "selection"]
    assert lists and all("liste" in a["title"] for a in lists)
