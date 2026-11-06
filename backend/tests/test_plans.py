"""Formule du compte : le compte gratuit garde une partie et joue deux saisons en tout,
supprimées comprises ; le jeu complet, abonnement annuel chez Stripe, n'a plus de limite
jusqu'au 1er juillet, et chaque renouvellement le prolonge d'un an."""

import datetime
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


def test_those_who_paid_once_keep_the_full_game_until_july_2027(world):
    if database.uses_postgres():
        old = database.shared_engine()
    else:
        old = create_engine(f"sqlite:///{database.SAVES_DIR / 'users.db'}")
    with old.begin() as connection:
        connection.execute(
            text(
                "CREATE TABLE users (id INTEGER PRIMARY KEY, email VARCHAR(254) UNIQUE, "
                "password_hash VARCHAR(300), created_at TIMESTAMP, active_slot INTEGER, "
                "premium_at TIMESTAMP, payment_ref VARCHAR(255))"
            )
        )
        connection.execute(
            text(
                "INSERT INTO users VALUES (1, 'paye@example.com', 'x', '2026-01-01', NULL, "
                "'2026-10-01', 'pi_1'), (2, 'gratuit@example.com', 'x', '2026-01-01', NULL, "
                "NULL, NULL)"
            )
        )
    if not database.uses_postgres():
        old.dispose()
    paid, free = accounts.get(1), accounts.get(2)
    assert paid.premium and paid.premium_until == datetime.datetime(2027, 6, 30, 22, 0)
    assert not free.premium and free.premium_until is None


# --- Abonnement : jusqu'au 1er juillet, renouvelé d'année en année --------------------


def at(monkeypatch, *when: int) -> None:
    """L'horloge des comptes (UTC) marque `when`."""
    monkeypatch.setattr(accounts, "_now", lambda: datetime.datetime(*when))


def test_the_season_ends_on_july_first_at_midnight_in_paris():
    end = datetime.datetime(2027, 6, 30, 22, 0)
    assert accounts.season_end(datetime.datetime(2026, 11, 1)) == end
    assert accounts.season_end(datetime.datetime(2027, 6, 30, 21, 59)) == end
    assert accounts.season_end(end) == datetime.datetime(2028, 6, 30, 22, 0)
    assert accounts.paris_day(end) == datetime.date(2027, 7, 1)


def test_in_the_last_days_of_a_season_the_next_one_is_sold(monkeypatch):
    # Un 1er juillet à moins de trois jours est sauté : la saison vendue est la suivante.
    at(monkeypatch, 2027, 6, 27, 21, 0)
    assert accounts.sold_season_end() == datetime.datetime(2027, 6, 30, 22, 0)
    at(monkeypatch, 2027, 6, 28)
    assert accounts.sold_season_end() == datetime.datetime(2028, 6, 30, 22, 0)
    fields = billing.checkout_fields(accounts.User(id=1, email="a@b.fr", active_slot=None), "")
    assert "1er juillet 2028" in fields["custom_text[submit][message]"]
    # Plus d'un an avant le premier prélèvement : Stripe n'ancre pas si loin, l'abonnement
    # attend par une période d'essai.
    subscription = billing.subscription_fields(1, "cus_1", "pm_1")
    assert subscription["trial_end"] == "1846015200"
    assert "billing_cycle_anchor" not in subscription


def test_without_renewal_the_account_goes_back_to_free(player, monkeypatch):
    at(monkeypatch, 2026, 11, 1)
    accounts.grant_premium(1, "sub_1", "cus_1")
    me = player.get("/auth/me").json()
    assert me["premium"] and me["subscribed"] and me["premium_until"] == "2027-07-01"
    # (l'horloge avancée, la session du joueur a expiré : on lit son compte)
    at(monkeypatch, 2027, 7, 4)  # Stripe réessaie encore la carte
    assert accounts.get(1).premium
    at(monkeypatch, 2027, 7, 8)
    lapsed = auth.user_out(accounts.get(1))
    assert not lapsed.premium and lapsed.seasons_left == 2 and lapsed.premium_until is None
    assert lapsed.season_end == datetime.date(2028, 7, 1)


def test_each_renewal_paid_adds_a_season(player, monkeypatch):
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", SECRET)
    at(monkeypatch, 2026, 11, 1)
    accounts.grant_premium(1, "sub_1", "cus_1")

    def invoice_paid(customer: str):
        invoice = {"id": "in_1", "customer": customer, "billing_reason": "subscription_cycle"}
        payload = json.dumps({"type": "invoice.paid", "data": {"object": invoice}}).encode()
        return TestClient(app).post(
            "/billing/webhook", content=payload, headers={"Stripe-Signature": signed(payload)}
        )

    at(monkeypatch, 2027, 7, 1, 1)
    assert invoice_paid("cus_1").status_code == 200
    assert invoice_paid("cus_1").status_code == 200  # Stripe prévient parfois deux fois
    assert auth.user_out(accounts.get(1)).premium_until == datetime.date(2028, 7, 1)
    # Le client d'une autre vente du compte Stripe : rien ne bouge.
    assert invoice_paid("cus_autre").status_code == 200
    at(monkeypatch, 2028, 6, 1)
    assert accounts.get(1).premium


def test_the_subscriber_manages_it_in_stripe(player, monkeypatch):
    sent = []

    def stripe_call(method, path, fields=None):
        sent.append((method, path, fields))
        return {"url": "https://billing.stripe.com/p/session/test_1"}

    monkeypatch.setattr(billing, "stripe_call", stripe_call)
    assert player.post("/billing/portal").status_code == 404
    accounts.grant_premium(1, "sub_1", "cus_1")
    opened = player.post("/billing/portal", headers={"Origin": "https://rugby.example"})
    assert opened.json()["url"].startswith("https://billing.stripe.com/")
    assert sent == [
        (
            "POST",
            "/billing_portal/sessions",
            {"customer": "cus_1", "return_url": "https://rugby.example/parties"},
        )
    ]


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
        "customer": "cus_test_1",
        "subscription": "sub_test_1",
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
    payload = json.dumps(offered).encode()
    response = TestClient(app).post(
        "/billing/webhook", content=payload, headers={"Stripe-Signature": signed(payload)}
    )
    assert response.status_code == 200
    assert plan(player)[0] is True


class FakeStripe:
    """Stripe, le temps d'un test : une session de paiement payée par carte (ou offerte),
    et les abonnements créés."""

    def __init__(self, status: str = "paid", refuse_subscription: bool = False):
        self.sent: list[tuple[str, str, dict | None]] = []
        self.subscriptions: list[dict] = []
        self.products: set[str] = set()
        self.refuse_subscription = refuse_subscription
        self.session = {
            "id": "cs_test_1",
            "url": "https://checkout.stripe.com/c/pay/cs_test_1",
            "client_reference_id": "1",
            "payment_status": status,
            "customer": "cus_test_1",
            "payment_intent": "pi_test_1" if status == "paid" else None,
            "metadata": {"app": billing.APP},
        }

    def __call__(self, method, path, fields=None, *, idempotency_key=None, missing_ok=False):
        self.sent.append((method, path, fields))
        if path == "/checkout/sessions" or path.startswith("/checkout/sessions/"):
            return self.session
        if path == "/payment_intents/pi_test_1":
            return {"id": "pi_test_1", "payment_method": "pm_test_1"}
        if path.startswith("/products"):
            if method == "POST":
                self.products.add(fields["id"])
            return {"id": PRODUCT} if PRODUCT in self.products or method == "POST" else None
        if path == "/subscriptions" and method == "GET":
            return {"data": self.subscriptions}
        if path == "/subscriptions":
            if self.refuse_subscription:
                raise billing.HTTPException(status_code=502, detail="Stripe a refusé la demande")
            subscription = {"id": "sub_test_1", "status": "active", **fields}
            subscription["metadata"] = {"app": fields["metadata[app]"]}
            self.subscriptions.append(subscription)
            return subscription
        raise AssertionError(f"appel inattendu : {method} {path}")


PRODUCT = billing.PRODUCT_ID


def test_checkout_then_confirm_on_the_way_back(player, monkeypatch):
    stripe = FakeStripe()
    monkeypatch.setattr(billing, "stripe_call", stripe)
    at(monkeypatch, 2026, 11, 1)
    # Sans la case cochée (CGV, accès immédiat sans rétractation), pas de paiement.
    refused = player.post("/billing/checkout", headers={"Origin": "https://rugby.example"})
    assert refused.status_code == 400 and not stripe.sent
    created = player.post(
        "/billing/checkout",
        headers={"Origin": "https://rugby.example"},
        json={"accept_terms": True},
    )
    assert created.json()["url"].startswith("https://checkout.stripe.com/")
    fields = stripe.sent[0][2]
    # L'accord est gardé chez Stripe, daté, comme preuve.
    accepted = fields["metadata[terms_accepted_at]"]
    assert accepted == fields["payment_intent_data[metadata][terms_accepted_at]"]
    assert accepted.startswith("2026-11-01T")
    assert "https://rugby.example/cgv" in fields["custom_text[submit][message]"]
    # Un paiement simple, 2 € pour la saison : ni essai ni abonnement sur la page.
    assert fields["client_reference_id"] == "1" and fields["mode"] == "payment"
    assert fields["metadata[app]"] == fields["payment_intent_data[metadata][app]"] == billing.APP
    assert fields["payment_intent_data[setup_future_usage]"] == "off_session"
    assert fields["line_items[0][price_data][unit_amount]"] == "200"
    assert not [key for key in fields if "recurring" in key or "subscription" in key]
    assert "1er juillet 2027" in fields["line_items[0][price_data][product_data][name]"]
    message = fields["custom_text[submit][message]"]
    assert "1er juillet 2027" in message and "2 € chaque 1er juillet" in message
    assert fields["customer_email"] == "maxence@example.com"
    assert fields["customer_creation"] == "always"
    assert fields["success_url"].startswith("https://rugby.example/parties?paiement=ok")
    assert fields["allow_promotion_codes"] == "true"
    image = fields["line_items[0][price_data][product_data][images][0]"]
    assert image == "https://rugby.example/logo.png"

    assert player.post("/billing/confirm", json={"session_id": "../secret"}).status_code == 400
    confirmed = player.post("/billing/confirm", json={"session_id": "cs_test_1"})
    assert confirmed.status_code == 200 and confirmed.json()["premium"]
    assert confirmed.json()["premium_until"] == "2027-07-01" and confirmed.json()["subscribed"]
    assert player.post("/billing/checkout", json={"accept_terms": True}).status_code == 409

    # L'abonnement : 2 € par an sur la carte du paiement, prélevés le 1er juillet.
    (subscription,) = stripe.subscriptions
    assert subscription["customer"] == "cus_test_1"
    assert subscription["default_payment_method"] == "pm_test_1"
    assert subscription["items[0][price_data][product]"] == PRODUCT in stripe.products
    assert subscription["items[0][price_data][unit_amount]"] == "200"
    assert subscription["items[0][price_data][recurring][interval]"] == "year"
    assert subscription["billing_cycle_anchor"] == "1814392800"
    assert subscription["proration_behavior"] == "none"
    assert "trial_end" not in subscription
    assert accounts.get(1).stripe_customer == "cus_test_1"


def test_the_webhook_after_confirm_subscribes_only_once(player, monkeypatch):
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", SECRET)
    stripe = FakeStripe()
    monkeypatch.setattr(billing, "stripe_call", stripe)
    assert player.post("/billing/confirm", json={"session_id": "cs_test_1"}).status_code == 200
    payload = json.dumps(
        {"type": "checkout.session.completed", "data": {"object": stripe.session}}
    ).encode()
    webhook = TestClient(app).post(
        "/billing/webhook", content=payload, headers={"Stripe-Signature": signed(payload)}
    )
    assert webhook.status_code == 200
    assert len(stripe.subscriptions) == 1


def test_a_season_offered_by_a_promotion_code_has_no_subscription(player, monkeypatch):
    stripe = FakeStripe(status="no_payment_required")
    monkeypatch.setattr(billing, "stripe_call", stripe)
    at(monkeypatch, 2026, 11, 1)
    confirmed = player.post("/billing/confirm", json={"session_id": "cs_test_1"})
    assert confirmed.json()["premium"] and confirmed.json()["premium_until"] == "2027-07-01"
    # Pas de carte enregistrée : rien à prélever au 1er juillet.
    assert not stripe.subscriptions and not confirmed.json()["subscribed"]


def test_a_refused_subscription_keeps_the_paid_season(player, monkeypatch):
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", SECRET)
    stripe = FakeStripe(refuse_subscription=True)
    monkeypatch.setattr(billing, "stripe_call", stripe)
    confirmed = player.post("/billing/confirm", json={"session_id": "cs_test_1"})
    assert confirmed.status_code == 200 and confirmed.json()["premium"]
    assert not confirmed.json()["subscribed"]
    # Le webhook répond en erreur : Stripe le rappellera, et l'abonnement sera créé.
    payload = json.dumps(
        {"type": "checkout.session.completed", "data": {"object": stripe.session}}
    ).encode()
    webhook = TestClient(app, raise_server_exceptions=False).post(
        "/billing/webhook", content=payload, headers={"Stripe-Signature": signed(payload)}
    )
    assert webhook.status_code == 502
    stripe.refuse_subscription = False
    webhook = TestClient(app).post(
        "/billing/webhook", content=payload, headers={"Stripe-Signature": signed(payload)}
    )
    assert webhook.status_code == 200 and len(stripe.subscriptions) == 1
    assert accounts.get(1).stripe_customer == "cus_test_1"


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
    assert player.post("/billing/checkout", json={"accept_terms": True}).status_code == 503
    assert TestClient(app).post("/billing/webhook", content=b"{}").status_code == 503
