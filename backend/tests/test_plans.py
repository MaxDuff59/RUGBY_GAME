"""Formule du compte : le compte gratuit garde une partie et joue deux saisons en tout,
supprimées comprises ; le jeu complet, payé une fois par Stripe, n'a plus de limite."""

import hashlib
import hmac
import json
import time

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select, text

import accounts
import database
from api import auth, billing, plans
from api.main import app
from models.orm import SeasonRow
from tests.test_saves import sign_up, start

SECRET = "whsec_test"


@pytest.fixture(autouse=True)
def paywall(monkeypatch) -> None:
    """La formule est active (api/plans.py) : ses tests ne dépendent pas de l'interrupteur."""
    monkeypatch.setattr(plans, "PAYWALL", True)


@pytest.fixture
def player(world) -> TestClient:
    auth._attempts.clear()
    return sign_up("maxence@example.com")


def plan(client: TestClient) -> tuple[bool, int, int | None]:
    me = client.get("/auth/me").json()
    return me["premium"], me["seasons_played"], me["seasons_left"]


def test_a_free_account_counts_its_seasons_even_once_deleted(player):
    assert plan(player) == (False, 0, 2)
    start(player, 1, "Maxence", "Stade Toulousain")
    assert plan(player) == (False, 1, 1)

    # Une seule partie : la deuxième attend qu'on supprime la première.
    second = player.post("/saves/2/new")
    assert second.status_code == 402 and "une seule partie" in second.json()["detail"]
    assert not database.slot_exists(1, 2)

    # Supprimer la carrière ne rend pas sa saison : la suivante est la dernière.
    player.delete("/saves/1")
    start(player, 1, "Maxence", "Bath Rugby")
    assert plan(player) == (False, 2, 0)
    player.delete("/saves/1")
    refused = player.post("/saves/1/new")
    assert refused.status_code == 402 and "2 saisons" in refused.json()["detail"]
    assert not database.slot_exists(1, 1)


def test_the_next_season_waits_for_the_full_game(player):
    start(player, 1, "Maxence", "Stade Toulousain")
    accounts.count_season(1)  # la deuxième saison est commencée
    refused = player.post("/seasons/next")
    assert refused.status_code == 402 and "jeu complet" in refused.json()["detail"]
    with database.open_slot(1, 1) as session:
        assert session.scalar(select(func.count()).select_from(SeasonRow)) == 1


def test_taking_another_club_in_the_same_world_costs_no_season(player):
    start(player, 1, "Maxence", "Stade Toulousain")
    clubs = {c["name"]: c["id"] for c in player.get("/clubs").json()}
    again = player.post("/career", json={"manager_name": "Alex", "club_id": clubs["Bath Rugby"]})
    assert again.status_code == 201
    assert plan(player) == (False, 1, 1)


def test_a_guest_at_the_limit_is_sent_to_create_an_account(world):
    auth._attempts.clear()
    guest = TestClient(app)
    guest.post("/auth/guest")
    start(guest, 1, "Maxence", "Stade Toulousain")
    user_id = guest.get("/auth/me").json()["id"]
    accounts.count_season(user_id)  # ses deux saisons sont commencées
    refused = guest.post("/seasons/next")
    assert refused.status_code == 403 and "crée un compte" in refused.json()["detail"]
    assert guest.post("/billing/checkout").status_code == 403


def test_without_the_paywall_everything_is_free(player, monkeypatch):
    monkeypatch.setattr(plans, "PAYWALL", False)
    start(player, 1, "Maxence", "Stade Toulousain")
    accounts.count_season(1)
    assert player.get("/auth/me").json()["paywall"] is False
    start(player, 2, "Alex", "Leinster Rugby")  # une deuxième partie
    assert database.slot_exists(1, 2)
    assert plan(player) == (False, 3, 0)  # les saisons se comptent toujours
    assert player.post("/seasons/next").status_code != 402


def test_the_full_game_has_no_limit(player):
    start(player, 1, "Maxence", "Stade Toulousain")
    accounts.count_season(1)
    accounts.grant_premium(1, "pi_test")
    assert plan(player) == (True, 2, None)
    start(player, 2, "Alex", "Leinster Rugby")
    assert plan(player) == (True, 2, None)  # le jeu complet ne compte plus
    assert player.post("/seasons/next").status_code != 402


def test_accounts_from_before_get_the_new_columns(world):
    if database.uses_postgres():
        old = database.shared_engine()
    else:
        old = create_engine(f"sqlite:///{database.SAVES_DIR / 'users.db'}")
    with old.begin() as connection:
        connection.execute(
            text(
                "CREATE TABLE users (id INTEGER PRIMARY KEY, email VARCHAR(254) UNIQUE, "
                "password_hash VARCHAR(300), created_at TIMESTAMP, active_slot INTEGER)"
            )
        )
        connection.execute(
            text("INSERT INTO users VALUES (1, 'ancien@example.com', 'x', '2026-01-01', NULL)")
        )
    if not database.uses_postgres():
        old.dispose()
    assert accounts.get(1) == accounts.User(id=1, email="ancien@example.com", active_slot=None)
    accounts.count_season(1)
    assert accounts.get(1).seasons_left == 1


# --- Paiement Stripe -------------------------------------------------------------------


def signed(payload: bytes, secret: str = SECRET, at: int | None = None) -> str:
    timestamp = str(int(time.time()) if at is None else at)
    digest = hmac.new(secret.encode(), f"{timestamp}.".encode() + payload, hashlib.sha256)
    return f"t={timestamp},v1={digest.hexdigest()}"


def paid_event(user_id: int, status: str = "paid", app: str = billing.APP) -> bytes:
    checkout = {
        "id": "cs_test_1",
        "client_reference_id": str(user_id),
        "payment_status": status,
        "payment_intent": "pi_test_1",
        "metadata": {"app": app},
    }
    return json.dumps({"type": "checkout.session.completed", "data": {"object": checkout}}).encode()


def test_the_signature_is_stripes_scheme():
    payload = b'{"id": "evt_1"}'
    assert billing.verify_signature(payload, signed(payload), SECRET)
    assert not billing.verify_signature(payload, signed(payload, "whsec_autre"), SECRET)
    assert not billing.verify_signature(b'{"id": "evt_2"}', signed(payload), SECRET)
    assert not billing.verify_signature(payload, signed(payload, at=1_000_000), SECRET)
    assert not billing.verify_signature(payload, "", SECRET)


def test_the_webhook_unlocks_the_account_it_is_told(player, monkeypatch):
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", SECRET)
    stripe = TestClient(app)  # Stripe, sans cookie

    def call(payload: bytes, signature: str):
        return stripe.post(
            "/billing/webhook", content=payload, headers={"Stripe-Signature": signature}
        )

    forged = paid_event(1)
    assert call(forged, signed(forged, "whsec_pirate")).status_code == 400
    unpaid = paid_event(1, status="unpaid")
    assert call(unpaid, signed(unpaid)).status_code == 200
    # Une autre vente du même compte Stripe (sub-athletes...) : rien ne se débloque ici.
    other = paid_event(1, app="sub-athletes")
    assert call(other, signed(other)).status_code == 200
    assert plan(player)[0] is False

    event = paid_event(1)
    assert call(event, signed(event)).status_code == 200
    assert call(event, signed(event)).status_code == 200  # Stripe prévient parfois deux fois
    assert plan(player)[0] is True


def test_a_100_percent_promotion_code_unlocks_the_account(player, monkeypatch):
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", SECRET)
    offered = json.loads(paid_event(1, status="no_payment_required"))
    offered["data"]["object"]["payment_intent"] = None  # rien n'a été débité
    payload = json.dumps(offered).encode()
    response = TestClient(app).post(
        "/billing/webhook", content=payload, headers={"Stripe-Signature": signed(payload)}
    )
    assert response.status_code == 200
    assert plan(player)[0] is True


def test_checkout_then_confirm_on_the_way_back(player, monkeypatch):
    sent = []

    def stripe_call(method, path, fields=None):
        sent.append((method, path, fields))
        if method == "POST":
            return {"id": "cs_test_1", "url": "https://checkout.stripe.com/c/pay/cs_test_1"}
        return {
            "id": "cs_test_1",
            "client_reference_id": "1",
            "payment_status": "paid",
            "payment_intent": "pi_test_1",
            "metadata": {"app": billing.APP},
        }

    monkeypatch.setattr(billing, "stripe_call", stripe_call)
    created = player.post("/billing/checkout", headers={"Origin": "https://rugby.example"})
    assert created.json()["url"].startswith("https://checkout.stripe.com/")
    fields = sent[0][2]
    assert fields["client_reference_id"] == "1" and fields["mode"] == "payment"
    assert fields["metadata[app]"] == billing.APP
    assert fields["line_items[0][price_data][unit_amount]"] == "200"
    assert fields["line_items[0][price_data][currency]"] == "eur"
    assert fields["success_url"].startswith("https://rugby.example/parties?paiement=ok")
    assert fields["allow_promotion_codes"] == "true"

    assert player.post("/billing/confirm", json={"session_id": "../secret"}).status_code == 400
    confirmed = player.post("/billing/confirm", json={"session_id": "cs_test_1"})
    assert confirmed.status_code == 200 and confirmed.json()["premium"]
    assert sent[1][:2] == ("GET", "/checkout/sessions/cs_test_1")
    assert player.post("/billing/checkout").status_code == 409


def test_someone_elses_payment_unlocks_nothing(player, monkeypatch):
    monkeypatch.setattr(
        billing,
        "stripe_call",
        lambda *_: {
            "id": "cs_test_9",
            "client_reference_id": "1",
            "payment_status": "paid",
            "metadata": {"app": "sub-athletes"},
        },
    )
    assert player.post("/billing/confirm", json={"session_id": "cs_test_9"}).status_code == 403
    assert plan(player)[0] is False


def test_without_stripe_keys_the_payment_is_closed(player, monkeypatch):
    monkeypatch.delenv("STRIPE_SECRET_KEY", raising=False)
    monkeypatch.delenv("STRIPE_WEBHOOK_SECRET", raising=False)
    assert player.post("/billing/checkout").status_code == 503
    assert TestClient(app).post("/billing/webhook", content=b"{}").status_code == 503
