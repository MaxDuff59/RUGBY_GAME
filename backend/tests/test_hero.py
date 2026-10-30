"""Carrière de joueur : le joueur créé, ses dilemmes en match, sa progression."""

import datetime
import random

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from api.auth import current_user
from api.deps import get_session
from api.main import app
from data.generator import generate_real_clubs
from data.leagues import league
from engine import dilemmas, hero_market, social
from engine import hero as rules
from engine.match_engine import HALF_TIME, LiveMatch, simulate_match
from models import ATTRIBUTE_NAMES, Position
from models.orm import Base, ClubRow, HeroRow, InjuryRow, PlayerRow
from tests import conftest
from tests.conftest import make_club

# --- Règles -------------------------------------------------------------------------------


def test_a_beginner_starts_low_with_the_profile_of_his_position():
    wing = rules.start_attributes(Position.WING)
    prop = rules.start_attributes(Position.PROP)
    assert wing["pace"] > prop["pace"] and prop["scrum"] > wing["scrum"]
    assert max(wing.values()) <= 12


def test_points_cost_more_as_an_attribute_climbs():
    assert rules.cost(5) <= rules.cost(10) <= rules.cost(14) <= rules.cost(19)
    assert rules.cost(20) is None


def test_playing_well_earns_more_than_sitting_on_the_bench():
    assert rules.match_xp(0, None) == 0
    assert rules.match_xp(80, 6.0) > rules.match_xp(20, 6.0) > 0
    assert rules.match_xp(80, 8.0) > rules.match_xp(80, 6.0) == rules.match_xp(80, 5.0)


# --- Moteur -------------------------------------------------------------------------------


def _hero_match(seed: int, position: Position = Position.WING) -> tuple[LiveMatch, int]:
    home, away = make_club(1, 12, 1), make_club(2, 12, 2)
    weakest = min((p for p in home.players if p.position == position), key=lambda p: p.overall)
    live = LiveMatch(home, away, rng=random.Random(seed), hero=weakest.id)
    return live, weakest.id


def test_the_hero_is_always_called_up_and_comes_on_from_the_bench():
    live, hero = _hero_match(1)
    side = live.hero_side()
    assert side is live.home and hero in {p.id for p in side.bench}
    live.advance(HALF_TIME)
    while live.minute < dilemmas.HERO_ENTRY_MINUTE and not live.finished:
        if live.dilemma is not None:
            live.choose(live.dilemma_odds().popitem()[0])
        live.step()
    assert side.entered_at.get(hero) == dilemmas.HERO_ENTRY_MINUTE


def test_dilemmas_stop_the_clock_until_the_hero_chooses():
    seen = 0
    for seed in range(6):
        live, hero = _hero_match(seed)
        while not live.finished:
            if live.dilemma is None:
                live.advance(5)
                continue
            seen += 1
            minute = live.minute
            assert live.advance(3) == [] and live.minute == minute  # le chrono attend
            odds = live.dilemma_odds()
            assert all(dilemmas.CHANCE_MIN <= c <= dilemmas.CHANCE_MAX for c in odds.values())
            before = live.hero_side().ratings[hero]
            outcome = live.choose(next(iter(odds)))
            # Une réussite peut en appeler une autre, à la même minute.
            assert live.dilemma is None or (live.dilemma.chained and outcome.success)
            assert round(live.hero_side().ratings[hero] - before, 2) == outcome.delta
        drawn = [o for o in live.outcomes if o.situation != "two_on_one"]
        gaps = [b.minute - a.minute for a, b in zip(drawn, drawn[1:], strict=False)]
        assert all(gap >= dilemmas.DILEMMA_GAP for gap in gaps)
        assert len(drawn) <= dilemmas.DILEMMA_MAX
    assert seen > 0


def test_a_hero_match_resumes_from_its_saved_state():
    live, _ = _hero_match(3)
    while live.dilemma is None:
        live.step()
    copy = LiveMatch.from_state(live.home.club, live.away.club, live.to_state())
    assert copy.dilemma == live.dilemma and copy.hero == live.hero
    key = next(iter(live.dilemma_odds()))
    assert copy.choose(key) == live.choose(key)
    assert copy.play_to_end() == live.play_to_end()


def test_left_alone_the_hero_plays_safe():
    live, _ = _hero_match(4)
    live.play_to_end()
    for outcome in live.outcomes:
        situation = dilemmas.SITUATIONS_BY_KEY[outcome.situation]
        assert outcome.option == dilemmas.safest(situation).key


def test_without_a_hero_nothing_changes():
    home, away = make_club(1, 12, 1), make_club(2, 12, 2)
    live = LiveMatch(home, away, rng=random.Random(9))
    assert live.play_to_end() == simulate_match(home, away, rng=random.Random(9))
    assert live.outcomes == []


# --- API ----------------------------------------------------------------------------------


def _start(client, club_id=3, position="FLY_HALF"):
    hero = {"first_name": "Jean", "last_name": "Dupont", "position": position, "club_id": club_id}
    response = client.post("/hero", json=hero)
    assert response.status_code == 201, response.text
    return response.json()


def test_a_player_career_follows_his_club(client):
    career = _start(client)
    assert career["kind"] == "player" and career["club_id"] == 3
    assert client.get("/career").json()["kind"] == "player"
    hero = client.get("/hero").json()
    assert hero["age"] == rules.START_AGE and hero["points"] == rules.START_POINTS
    assert hero["club"]["id"] == 3 and hero["status"] in ("bench", "starter")
    # Le calendrier suit son club.
    next_match = client.get("/seasons/current").json()["next_match"]
    assert any(3 in (m["home"]["id"], m["away"]["id"]) for m in next_match["matches"])


def test_points_buy_attributes(client):
    _start(client)
    hero = client.get("/hero").json()
    passing = next(a for a in hero["attributes"] if a["key"] == "passing")
    trained = client.post("/hero/train", json={"attribute": "passing"}).json()
    assert next(a for a in trained["attributes"] if a["key"] == "passing")["value"] == (
        passing["value"] + 1
    )
    assert trained["points"] == hero["points"] - passing["cost"]
    assert trained["overall"] > hero["overall"]
    while client.post("/hero/train", json={"attribute": "passing"}).status_code == 200:
        pass
    refused = client.post("/hero/train", json={"attribute": "passing"})
    assert refused.status_code == 400
    assert client.post("/hero/train", json={"attribute": "luck"}).status_code == 400


def test_a_live_match_with_dilemmas_earns_experience(client):
    _start(client)
    # Titulaire (l'entraîneur lui fait confiance) : assez de minutes pour ses dilemmes.
    session = _db(client)
    session.scalars(select(HeroRow)).first().trust = 90
    session.commit()
    live = client.post("/live").json()
    assert live["hero"] is not None and live["my_club_id"] == 3
    # Le joueur ne gère pas l'équipe.
    assert client.post("/live/tactics", json={"game_plan": "hands"}).status_code == 400
    chosen = 0
    while not live["finished"]:
        if live["dilemma"]:
            assert client.post("/live/advance", json={"minutes": 1}).status_code == 400
            option = live["dilemma"]["options"][0]["key"]
            live = client.post("/live/choose", json={"option": option}).json()
            chosen += 1
        else:
            live = client.post("/live/advance", json={"minutes": 5}).json()
    assert chosen == len(live["hero"]["outcomes"]) > 0
    played = client.post("/live/finish").json()
    reward = played["hero"]
    assert reward is not None and reward["match"] is not None
    assert reward["xp"] >= rules.TRAINING_XP + rules.match_xp(reward["match"]["minutes"], 6.0)
    hero = client.get("/hero").json()
    assert hero["matches"][0]["match_id"] == reward["match"]["match_id"]
    assert hero["last_reward"] == reward
    # Une seconde journée ne recompte pas la première.
    again = client.post("/seasons/current/play").json()["hero"]
    assert (
        again is None
        or again["match"] is None
        or (again["match"]["match_id"] != reward["match"]["match_id"])
    )


def test_the_hero_does_not_progress_on_his_own(client):
    _start(client)
    before = {a["key"]: a["value"] for a in client.get("/hero").json()["attributes"]}
    for _ in range(4):
        client.post("/seasons/current/play")
    after = {a["key"]: a["value"] for a in client.get("/hero").json()["attributes"]}
    assert after == before


def test_a_new_coach_career_replaces_the_player(client):
    _start(client)
    client.post("/career", json={"manager_name": "Maxence", "club_id": 2})
    assert client.get("/career").json()["kind"] == "club"
    assert client.get("/hero").status_code == 404


# --- Réseaux sociaux ------------------------------------------------------------------------


def _appearance(match_id, rating, minutes=80, tries=0, started=True, moments=()):
    return social.Appearance(
        match_id=match_id,
        date=datetime.date(2026, 9, match_id),
        club="Biarritz Olympique",
        opponent="SU Agen",
        score_for=20,
        score_against=13,
        minutes=minutes,
        rating=rating,
        tries=tries,
        started=started,
        moments=list(moments),
    )


HERO = social.Hero("Jean", "Dupont", Position.WING, "Biarritz Olympique")


def test_the_feed_tells_the_story_newest_first():
    signed = datetime.date(2026, 8, 20)
    debut = _appearance(1, 6.2, minutes=28, started=False)
    star = _appearance(
        2,
        8.4,
        tries=1,
        moments=[{"minute": 57, "situation": "one_on_one", "option": "step", "success": True,
                  "chance": 0.4, "delta": 0.8, "effect": "break"}],
    )  # fmt: skip
    feed = social.feed(HERO, [star, debut], signed)
    texts = [post.text for post in feed.posts]
    assert feed.posts[0].date == star.date and feed.posts[-1].date == signed
    assert any("Premiers pas" in t for t in texts) and any("Premier essai" in t for t in texts)
    assert {p.author.voice for p in feed.posts} >= {social.Voice.MEDIA, social.Voice.FAN}
    assert len(texts) == len(set(texts))
    assert feed == social.feed(HERO, [debut, star], signed)  # même parcours, même fil


def test_good_matches_bring_followers_and_praise():
    good = social.feed(HERO, [_appearance(1, 8.5, tries=2)], None)
    bad = social.feed(HERO, [_appearance(1, 4.2)], None)
    assert good.followers > bad.followers >= social.FOLLOWERS_START
    tones = {p.tone for p in good.posts if p.author.voice == social.Voice.FAN}
    assert tones == {social.Tone.PRAISE}
    assert social.Tone.CRITIC in {p.tone for p in bad.posts}


def test_the_social_feed_follows_the_hero(client):
    _start(client)
    feed = client.get("/hero/social").json()
    assert [p["voice"] for p in feed["posts"]] == ["fan", "media"]  # sa signature
    live = client.post("/live").json()
    while not live["finished"]:
        if live["dilemma"]:
            option = live["dilemma"]["options"][0]["key"]
            live = client.post("/live/choose", json={"option": option}).json()
        else:
            live = client.post("/live/advance", json={"minutes": 10}).json()
    client.post("/live/finish")
    after = client.get("/hero/social").json()
    assert len(after["posts"]) > len(feed["posts"])
    assert after["followers"] > feed["followers"] and after["gain"] > 0
    assert after["posts"][0]["match_id"] is not None


def test_a_break_leads_to_a_two_on_one():
    for seed in range(40):
        live, _ = _hero_match(seed)
        while not live.finished:
            if live.dilemma is None:
                live.step()
                continue
            situation = dilemmas.SITUATIONS_BY_KEY[live.dilemma.situation]
            follows = [o for o in situation.options if o.follow]
            outcome = live.choose((follows or situation.options)[0].key)
            if follows and outcome.success:
                assert live.dilemma.situation == "two_on_one" and live.dilemma.chained
                assert live.dilemma.minute == outcome.minute
                return
    raise AssertionError("aucun franchissement en 40 matchs")


def test_pressure_weighs_late_close_and_final_moments():
    assert dilemmas.pressure(30, 80, 0, False, False) == 1.0
    late = dilemmas.pressure(75, 80, -3, False, False)
    assert late > 1.0 and dilemmas.pressure(75, 80, -20, False, False) == 1.0
    assert dilemmas.pressure(75, 80, -3, True, True) == dilemmas.PRESSURE_MAX > late


def test_simulate_until_the_hero_comes_on():
    live, hero = _hero_match(2)
    live.advance_to_hero()  # sur le banc, pas de dilemme : rien n'arrête le chrono
    side = live.hero_side()
    assert side.entered_at.get(hero) == live.hero_entry == live.minute
    assert live.advance_to_hero() == []  # déjà entré : rien à jouer


def test_every_action_has_its_words_on_the_networks():
    keys = {o.key for situation in dilemmas.SITUATIONS for o in situation.options}
    assert keys <= set(social.MOMENT_WON) and keys <= set(social.MOMENT_LOST)


def test_confidence_and_injury_move_the_odds():
    live, _ = _hero_match(3)
    while live.dilemma is None:
        live.step()
    base = live.dilemma_odds()
    live.hero_confidence = 1.0
    confident = live.dilemma_odds()
    live.hero_confidence, live.hero_hurt = 0.0, True
    hurt = live.dilemma_odds()
    assert all(confident[k] >= base[k] >= hurt[k] for k in base)
    assert any(confident[k] > base[k] for k in base)


# --- Confiance, entraîneur, blessure ----------------------------------------------------------


def test_confidence_and_trust_follow_the_matches():
    assert rules.next_confidence(0.0, 8.0) > 0 > rules.next_confidence(0.0, 4.5)
    assert abs(rules.next_confidence(0.5, None)) < 0.5  # sans jouer, elle retombe
    assert rules.next_trust(40, 7.5, False, 0) > rules.next_trust(40, 6.0, False, 0)
    assert rules.next_trust(40, 6.0, True, 0) < rules.next_trust(40, 6.0, False, 0)
    assert rules.next_trust(40, 6.0, False, 2) < rules.next_trust(40, 6.0, False, 1)
    assert rules.entry_minute(80) < rules.entry_minute(40) < rules.entry_minute(10)


def _db(client):
    return next(app.dependency_overrides[get_session]())


def _play_live(client, pick=0):
    live = client.post("/live").json()
    first = live
    while not live["finished"]:
        if live["dilemma"]:
            option = live["dilemma"]["options"][pick]["key"]
            live = client.post("/live/choose", json={"option": option}).json()
        else:
            live = client.post("/live/advance", json={"minutes": 10}).json()
    return first, client.post("/live/finish").json()


def test_the_coach_starts_a_player_he_trusts(client):
    _start(client)
    session = _db(client)
    session.scalars(select(HeroRow)).first().trust = 90
    session.commit()
    hero = client.get("/hero").json()
    assert hero["status"] == "starter" and hero["entry"] == rules.entry_minute(90)
    first, _ = _play_live(client)
    me = next(p for p in [*first["home"]["players"], *first["away"]["players"]]
              if p["id"] == hero["player_id"])  # fmt: skip
    assert me["status"] == "field"


def test_an_injured_hero_can_play_hurt(client):
    _start(client)
    hero = client.get("/hero").json()
    session = _db(client)
    day = client.get("/seasons/current").json()["next_match"]["date"]
    session.add(
        InjuryRow(
            player_id=hero["player_id"],
            severity="moderate",
            kind="entorse",
            source="training",
            occurred_on=datetime.date.fromisoformat(day) - datetime.timedelta(days=3),
            base_weeks=3,
            return_date=datetime.date.fromisoformat(day) + datetime.timedelta(weeks=3),
        )
    )
    session.commit()
    injured = client.get("/hero").json()
    assert injured["status"] == "injured" and injured["injury_weeks"] > 0
    assert client.post("/hero/play-hurt", json={"play": True}).json()["play_hurt"]
    first, _ = _play_live(client)
    assert first["hero"]["hurt"] is True
    after = client.get("/hero").json()
    assert not after["play_hurt"]
    assert after["coach_notes"][0]["kind"] in ("aggravated", "brave")


# --- Mercato ------------------------------------------------------------------------------


def test_bigger_clubs_wait_for_a_better_player():
    levels = {1: 10.0, 2: 11.0, 3: 13.0, 4: 16.0}
    prestige = {cid: level for cid, level in levels.items()}
    none = hero_market.AGENTS["none"]
    rngs = [random.Random(seed) for seed in range(30)]
    beginner = {
        c for rng in rngs for c in hero_market.transfer_clubs(10.5, 1, levels, prestige, none, rng)
    }
    assert beginner and 4 not in beginner  # un débutant n'intéresse pas les grands clubs
    star = hero_market.AGENTS["star"]
    rngs = [random.Random(seed) for seed in range(30)]
    later = {
        c for rng in rngs for c in hero_market.transfer_clubs(15.2, 1, levels, prestige, star, rng)
    }
    assert 4 in later
    # Peu de temps de jeu : un prêt vers plus modeste ; assez joué : pas de prêt.
    assert hero_market.loan_clubs(3, levels, prestige, 0.1, random.Random(0))
    assert hero_market.loan_clubs(3, levels, prestige, 0.8, random.Random(0)) == []
    assert hero_market.wage(50_000, 2, star) > hero_market.wage(50_000, 2, none)


def test_the_end_of_season_mercato_moves_the_hero(client):
    _start(client, club_id=3)
    assert client.get("/hero/offers").json()["offers"] == []  # pas avant la fin
    assert client.post("/hero/offers/choose", json={"index": 0}).status_code == 400
    while client.get("/seasons/current").json()["phase"] != "finished":
        assert client.post("/seasons/current/play").status_code == 200
    client.post("/hero/agent", json={"agent": "star"})
    offers = client.get("/hero/offers").json()
    assert offers["open"] and offers["agent"] == "star"
    assert offers["offers"][0]["kind"] == "extend" and offers["offers"][0]["club"]["id"] == 3
    assert all(o["net_wage"] < o["wage"] for o in offers["offers"])
    away = next((o for o in offers["offers"] if o["kind"] != "extend"), offers["offers"][0])
    chosen = client.post("/hero/offers/choose", json={"index": away["index"]}).json()
    assert [o["chosen"] for o in chosen["offers"]].count(True) == 1
    assert client.get("/hero/offers").json() == chosen  # les mêmes offres
    assert client.post("/seasons/next").status_code == 201
    hero = client.get("/hero").json()
    assert hero["club"]["id"] == away["club"]["id"] and hero["choice"] is None
    if away["kind"] == "loan":
        assert hero["loaned_from"]["id"] == 3
    if away["kind"] != "extend":
        texts = [p["text"] for p in client.get("/hero/social").json()["posts"]]
        assert any(away["club"]["name"] in t and "Officiel" in t for t in texts)


def test_a_season_then_retirement_and_a_coaching_career(client):
    _start(client, club_id=3)
    assert client.post("/hero/retire").status_code == 400  # pas en cours de saison
    first, _ = _play_live(client)
    career = client.get("/hero/career").json()
    assert career["matches"] == 1 and career["seasons"][0]["clubs"][0]["id"] == 3
    assert career["average"] is not None and not career["retired"]
    while client.get("/seasons/current").json()["phase"] != "finished":
        client.post("/seasons/current/play")
    retired = client.post("/hero/retire").json()
    assert retired["retired"] and retired["matches"] >= 1
    assert client.get("/hero").status_code == 404 and client.get("/career").status_code == 404
    # Le même monde, une carrière d'entraîneur.
    assert (
        client.post("/career", json={"manager_name": "Jean Dupont", "club_id": 2}).status_code
        == 201
    )
    assert client.get("/career").json()["kind"] == "club"


def test_the_hero_does_not_retire_on_his_own(client):
    _start(client)
    session = _db(client)
    hero = session.scalars(select(HeroRow)).first()
    session.get(PlayerRow, hero.player_id).age = 40
    session.commit()
    while client.get("/seasons/current").json()["phase"] != "finished":
        client.post("/seasons/current/play")
    assert client.post("/seasons/next").status_code == 201
    assert client.get("/hero").json()["status"] != "retired"


# --- Sélection nationale ------------------------------------------------------------------


@pytest.fixture
def top14():
    """Le Top 14 réel : des pays, donc des sélections et leurs fenêtres."""
    engine = conftest.test_engine()
    Base.metadata.create_all(engine)
    TestSession = sessionmaker(bind=engine, expire_on_commit=False)
    with TestSession() as session:
        clubs = generate_real_clubs(random.Random(0), [league("top14")])
        session.add_all(ClubRow.from_domain(club) for club in clubs)
        session.commit()

    def override_get_session():
        with TestSession() as session:
            yield session

    app.dependency_overrides[get_session] = override_get_session
    app.dependency_overrides[current_user] = conftest.full_account
    yield TestClient(app), TestSession
    app.dependency_overrides.clear()


def test_a_great_player_is_called_up_and_plays_his_test_live(top14):
    client, TestSession = top14
    toulouse = next(c["id"] for c in client.get("/clubs").json() if c["name"] == "Stade Toulousain")
    _start(client, club_id=toulouse)
    with TestSession() as session:
        player = session.get(PlayerRow, session.scalars(select(HeroRow)).first().player_id)
        for name in ATTRIBUTE_NAMES:
            setattr(player, name, 20)
        session.commit()
    while (hero := client.get("/hero").json())["called_up"] is None:
        assert client.post("/seasons/current/play").status_code == 200
    test = hero["called_up"]
    assert test["nation"] == "France"
    # Les journées de son club d'ici là se jouent d'abord.
    while (nxt := client.get("/seasons/current").json()["next_match"]) and nxt["date"] < test[
        "date"
    ]:
        assert client.post("/seasons/current/play").status_code == 200
    live = client.post("/live").json()
    assert live["match_id"] == test["match_id"] and live["hero"] is not None
    while not live["finished"]:
        if live["dilemma"]:
            option = live["dilemma"]["options"][0]["key"]
            live = client.post("/live/choose", json={"option": option}).json()
        else:
            live = client.post("/live/advance", json={"minutes": 10}).json()
    day = client.post("/live/finish").json()
    assert day["hero"]["xp"] > 0 and day["season"]
    after = client.get("/hero").json()
    assert after["caps"] == 1
    texts = [p["text"] for p in client.get("/hero/social").json()["posts"]]
    assert any("France" in t for t in texts)


def test_ai_clubs_never_move_the_hero(client):
    _start(client, club_id=3)
    while client.get("/seasons/current").json()["phase"] != "finished":
        client.post("/seasons/current/play")
        assert client.get("/hero").json()["club"]["id"] == 3
    client.post("/seasons/next")
    assert client.get("/hero").json()["club"]["id"] == 3
