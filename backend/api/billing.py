"""Abonnement au jeu complet : 2 € par an, par Stripe (voir api/plans.py).

Le jeu complet vaut pour la saison du jeu, jusqu'au 1er juillet (accounts.season_end) :
la première saison se paie tout de suite, en entier, puis l'abonnement se renouvelle
chaque 1er juillet. Sans renouvellement (résilié, carte refusée), le compte repasse en
gratuit.

1. `POST /billing/checkout` crée une page de paiement Stripe pour le compte connecté
   et renvoie son adresse : le navigateur y part. C'est un paiement simple, 2 € pour
   la saison en cours, qui enregistre la carte pour la suite (`setup_future_usage`).
   Une page d'abonnement afficherait un « essai gratuit » jusqu'au 1er juillet alors
   que le joueur paie tout de suite : Stripe n'accepte pas d'y ancrer l'abonnement au
   1er juillet sans prorata à côté d'une ligne payée une fois.
2. Stripe ramène le joueur sur `/parties?paiement=ok&session_id=...` ; l'interface
   appelle `POST /billing/confirm`, qui relit la session chez Stripe, débloque le compte
   puis crée l'abonnement (`subscribe`) : 2 € par an sur la carte enregistrée, premier
   prélèvement le 1er juillet (`billing_cycle_anchor`, rien de dû d'ici là).
3. Stripe prévient aussi `POST /billing/webhook` : checkout.session.completed fait de
   même si le joueur ferme l'onglet avant de revenir (l'abonnement n'est créé qu'une
   fois), invoice.paid (chaque 1er juillet) prolonge le compte d'un an.
4. `POST /billing/portal` ouvre l'espace client de Stripe : carte, factures, résiliation.

Configuration, par variables d'environnement :
- `STRIPE_SECRET_KEY` (sk_live_... ou sk_test_...) : sans elle, le paiement est fermé ;
- `STRIPE_WEBHOOK_SECRET` (whsec_...) : signature des appels de Stripe au webhook ;
- `RUGBY_PUBLIC_URL` (facultatif) : adresse de l'interface pour le retour, sinon
  l'origine de la requête.
Dans le tableau de bord Stripe : le webhook écoute checkout.session.completed,
checkout.session.async_payment_succeeded et invoice.paid ; l'espace client
(Paramètres → Facturation → Portail client) est activé, résiliation comprise.

La clé Stripe (restreinte) écrit les sessions de paiement, les abonnements, les produits
et l'espace client, et lit les paiements (PaymentIntents).

Codes promo : la page de paiement en accepte (`allow_promotion_codes`). Un coupon de
100 % créé dans le tableau de bord Stripe offre la saison : la session se règle alors à
0 € (`no_payment_required`), débloque le compte comme un paiement, mais sans carte
enregistrée, donc sans abonnement : le jeu complet s'arrête au 1er juillet.

L'API de Stripe s'appelle en bibliothèque standard (urllib), sans son SDK.
"""

import datetime
import hashlib
import hmac
import json
import logging
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request

from fastapi import APIRouter, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field

import accounts
from api.auth import UserDep, UserOut, user_out
from api.plans import PAYMENT_REQUIRED, PRICE_CENTS

STRIPE_API = "https://api.stripe.com/v1"
PRODUCT_NAME = "Rugby Manager : jeu complet"
PRODUCT_DESCRIPTION = (
    "Trois parties en parallèle et des saisons sans fin : club, sélection, compétition "
    "et carrière de joueur, sans limite. Abonnement annuel, renouvelé chaque 1er juillet."
)
# Le produit de l'abonnement, créé chez Stripe au premier abonné sous cet identifiant :
# ses renouvellements le portent sur les factures.
PRODUCT_ID = "rugby-manager-jeu-complet"
# Image du produit sur la page de paiement, servie par l'interface (frontend/public).
PRODUCT_IMAGE = "/logo.png"
MONTHS = (
    "janvier", "février", "mars", "avril", "mai", "juin",
    "juillet", "août", "septembre", "octobre", "novembre", "décembre",
)  # fmt: skip
# Marque des paiements du jeu : le compte Stripe peut servir à d'autres ventes, dont les
# événements arrivent aussi au webhook et ne débloquent rien ici.
APP = "rugby-manager"
# Écart toléré entre l'horodatage signé par Stripe et notre horloge (rejeu d'un appel).
SIGNATURE_TOLERANCE = 300
_SESSION_ID = re.compile(r"^cs_[A-Za-z0-9_]{1,250}$")
# Événements de Stripe qui signalent un paiement reçu (carte : aussitôt ; virement : après).
PAID_EVENTS = {"checkout.session.completed", "checkout.session.async_payment_succeeded"}
# Une facture d'abonnement payée : le renouvellement du 1er juillet.
RENEWAL_EVENT = "invoice.paid"
# Session réglée : payée, ou offerte par un code promo de 100 %.
SETTLED = {"paid", "no_payment_required"}
# Abonnements du jeu encore en cours chez Stripe (pour n'en créer qu'un par client).
LIVE_SUBSCRIPTIONS = {"active", "trialing", "past_due", "incomplete"}
# Stripe n'ancre un abonnement qu'à moins d'une période (un an) ; au-delà, l'attente
# jusqu'au premier prélèvement passe par une période d'essai (accounts.SALE_LEAD).
ANCHOR_LIMIT = datetime.timedelta(days=365)

log = logging.getLogger(__name__)
router = APIRouter(prefix="/billing", tags=["paiement"])


class CheckoutIn(BaseModel):
    # La case cochée avant de partir chez Stripe : le joueur accepte les CGV, demande
    # l'accès immédiat au jeu complet et renonce ainsi à son droit de rétractation
    # (art. L221-28 13° du code de la consommation). Sans elle, pas de paiement.
    accept_terms: bool = False


class CheckoutOut(BaseModel):
    url: str


class ConfirmIn(BaseModel):
    session_id: str = Field(max_length=256)


# --- Stripe ---------------------------------------------------------------------------


def _secret_key() -> str:
    key = os.environ.get("STRIPE_SECRET_KEY")
    if not key:
        raise HTTPException(status_code=503, detail="Le paiement n'est pas encore ouvert")
    return key


def stripe_call(
    method: str,
    path: str,
    fields: dict[str, str] | None = None,
    *,
    idempotency_key: str | None = None,
    missing_ok: bool = False,
) -> dict | None:
    """Appelle l'API de Stripe (formulaire en entrée, en paramètres pour un GET ; JSON en
    sortie) ; 502 si elle refuse ou ne répond pas, avec la raison dans le journal du
    serveur. `idempotency_key` : Stripe ne fait l'opération qu'une fois pour cette clé ;
    `missing_ok` : None pour un objet introuvable (404)."""
    query = urllib.parse.urlencode(fields) if fields else ""
    headers = {"Authorization": f"Bearer {_secret_key()}"}
    if idempotency_key:
        headers["Idempotency-Key"] = idempotency_key
    request = urllib.request.Request(
        STRIPE_API + path + (f"?{query}" if query and method == "GET" else ""),
        data=query.encode() if query and method != "GET" else None,
        method=method,
        headers=headers,
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            return json.load(response)
    except urllib.error.HTTPError as error:
        if missing_ok and error.code == 404:
            return None
        try:
            reason = json.load(error).get("error", {}).get("message")
        except ValueError:
            reason = None
        log.error("Stripe %s %s : %s %s", method, path, error.code, reason)
        raise HTTPException(status_code=502, detail="Stripe a refusé la demande") from error
    except urllib.error.URLError as error:
        log.error("Stripe %s %s injoignable : %s", method, path, error.reason)
        raise HTTPException(status_code=502, detail="Stripe ne répond pas : réessaie") from error


def long_day(day: datetime.date) -> str:
    """« 1er juillet 2027 »."""
    return f"{'1er' if day.day == 1 else day.day} {MONTHS[day.month - 1]} {day.year}"


def _timestamp(at: datetime.datetime) -> str:
    return str(int(at.replace(tzinfo=datetime.UTC).timestamp()))


def checkout_fields(user: accounts.User, site: str) -> dict[str, str]:
    """La page de paiement d'un compte, rattachée à lui par `client_reference_id` : 2 €
    tout de suite pour la saison en cours, la carte gardée pour l'abonnement.

    L'accord du joueur (CGV, accès immédiat, renonciation à la rétractation) est gardé
    chez Stripe, daté, sur la session et sur le paiement : c'est la preuve."""
    until = long_day(accounts.paris_day(accounts.sold_season_end()))
    season = "line_items[0][price_data]"
    accepted = accounts._now().replace(microsecond=0).isoformat() + "Z"
    fields = {
        "mode": "payment",
        "client_reference_id": str(user.id),
        "metadata[user_id]": str(user.id),
        "metadata[app]": APP,
        "payment_intent_data[metadata][user_id]": str(user.id),
        "payment_intent_data[metadata][app]": APP,
        "metadata[terms_accepted_at]": accepted,
        "payment_intent_data[metadata][terms_accepted_at]": accepted,
        # La carte reste au client chez Stripe : l'abonnement la prélèvera (subscribe).
        "payment_intent_data[setup_future_usage]": "off_session",
        "success_url": f"{site}/parties?paiement=ok&session_id={{CHECKOUT_SESSION_ID}}",
        "cancel_url": f"{site}/parties?paiement=annule",
        "allow_promotion_codes": "true",
        "line_items[0][quantity]": "1",
        f"{season}[currency]": "eur",
        f"{season}[unit_amount]": str(PRICE_CENTS),
        f"{season}[product_data][name]": f"{PRODUCT_NAME} : saison jusqu'au {until}",
        f"{season}[product_data][description]": PRODUCT_DESCRIPTION,
        # Sous le bouton « Payer ».
        "custom_text[submit][message]": (
            f"2 € aujourd'hui pour la saison, jusqu'au {until}. L'abonnement se renouvelle "
            "ensuite à 2 € chaque 1er juillet, avec la nouvelle version du jeu ; résiliable "
            "à tout moment depuis le jeu. Accès immédiat demandé : pas de droit de "
            f"rétractation (CGV : {site}/cgv)."
        ),
    }
    # Stripe va chercher l'image lui-même : seulement depuis une adresse publique.
    if site.startswith("https://"):
        fields[f"{season}[product_data][images][0]"] = site + PRODUCT_IMAGE
    # Un compte déjà client (abonnement arrêté, puis repris) garde sa fiche chez Stripe.
    if user.stripe_customer:
        fields["customer"] = user.stripe_customer
    else:
        fields["customer_email"] = user.email
        fields["customer_creation"] = "always"
    return fields


def _ensure_product() -> None:
    """Le produit de l'abonnement existe chez Stripe (créé au premier abonné)."""
    if stripe_call("GET", f"/products/{PRODUCT_ID}", missing_ok=True) is None:
        stripe_call(
            "POST",
            "/products",
            {"id": PRODUCT_ID, "name": PRODUCT_NAME, "description": PRODUCT_DESCRIPTION},
            idempotency_key=f"{APP}-product",
        )


def subscription_fields(user_id: int, customer: str, payment_method: str) -> dict[str, str]:
    """L'abonnement d'un compte qui vient de payer sa saison : 2 € par an sur sa carte,
    premier prélèvement au 1er juillet, rien de dû d'ici là."""
    end = accounts.sold_season_end()
    price = "items[0][price_data]"
    fields = {
        "customer": customer,
        "default_payment_method": payment_method,
        f"{price}[currency]": "eur",
        f"{price}[product]": PRODUCT_ID,
        f"{price}[unit_amount]": str(PRICE_CENTS),
        f"{price}[recurring][interval]": "year",
        "metadata[user_id]": str(user_id),
        "metadata[app]": APP,
        "off_session": "true",
    }
    if end - accounts._now() < ANCHOR_LIMIT:
        fields["billing_cycle_anchor"] = _timestamp(end)
        fields["proration_behavior"] = "none"
    else:
        fields["trial_end"] = _timestamp(end)
    return fields


def subscribe(checkout: dict) -> dict | None:
    """Crée l'abonnement d'une session payée, une seule fois par client (None : pas de
    carte enregistrée, saison offerte par un code promo)."""
    customer, intent = checkout.get("customer"), checkout.get("payment_intent")
    if not customer or not intent:
        return None
    method = stripe_call("GET", f"/payment_intents/{intent}").get("payment_method")
    if not method:
        return None
    existing = stripe_call("GET", "/subscriptions", {"customer": customer, "status": "all"})
    for subscription in existing.get("data", []):
        ours = (subscription.get("metadata") or {}).get("app") == APP
        if ours and subscription.get("status") in LIVE_SUBSCRIPTIONS:
            return subscription
    _ensure_product()
    return stripe_call(
        "POST",
        "/subscriptions",
        subscription_fields(int(checkout["client_reference_id"]), customer, method),
        idempotency_key=f"{APP}-subscription-{checkout['id']}",
    )


def verify_signature(payload: bytes, header: str, secret: str, now: float | None = None) -> bool:
    """L'en-tête `Stripe-Signature` (t=<horodatage>,v1=<HMAC-SHA256>...) authentifie-t-il
    ce corps de requête ? (schéma documenté par Stripe pour les webhooks)"""
    pairs = [item.split("=", 1) for item in header.split(",") if "=" in item]
    timestamp = next((value for key, value in pairs if key == "t"), "")
    signatures = [value for key, value in pairs if key == "v1"]
    if not timestamp.isdigit() or not signatures:
        return False
    if abs((time.time() if now is None else now) - int(timestamp)) > SIGNATURE_TOLERANCE:
        return False
    expected = hmac.new(
        secret.encode(), timestamp.encode() + b"." + payload, hashlib.sha256
    ).hexdigest()
    return any(hmac.compare_digest(expected, signature) for signature in signatures)


def _grant_if_paid(checkout: dict) -> accounts.User | None:
    """Débloque le compte d'une session de paiement du jeu, réglée ou offerte, puis crée
    son abonnement (None : session d'une autre vente, pas réglée, ou compte inconnu)."""
    reference = checkout.get("client_reference_id") or ""
    if (
        (checkout.get("metadata") or {}).get("app") != APP
        or checkout.get("payment_status") not in SETTLED
        or not reference.isdigit()
    ):
        return None
    if checkout.get("subscription"):
        # Page d'abonnement d'avant le paiement simple : Stripe a créé l'abonnement.
        return accounts.grant_premium(
            int(reference), checkout["subscription"], checkout.get("customer")
        )
    # Le compte d'abord : si Stripe refuse l'abonnement, le joueur a quand même sa saison
    # payée, et le webhook, rappelé par Stripe, recommencera.
    granted = accounts.grant_premium(
        int(reference), checkout.get("payment_intent") or checkout["id"]
    )
    if granted is None:
        return None
    if subscription := subscribe(checkout):
        granted = accounts.grant_premium(int(reference), customer=subscription["customer"])
    return granted


# --- Routes ---------------------------------------------------------------------------


def _site(request: Request) -> str:
    """L'adresse de l'interface, où Stripe ramène le joueur."""
    site = os.environ.get("RUGBY_PUBLIC_URL") or request.headers.get("origin")
    return (site or str(request.base_url)).rstrip("/")


@router.post("/checkout", response_model=CheckoutOut)
def checkout(user: UserDep, request: Request, payload: CheckoutIn = CheckoutIn()) -> CheckoutOut:
    """Ouvre une page de paiement Stripe pour le compte connecté, une fois les CGV
    acceptées (case cochée dans le jeu)."""
    if user.premium:
        raise HTTPException(status_code=409, detail="Ton compte a déjà le jeu complet")
    if user.guest:
        raise HTTPException(status_code=403, detail="Crée un compte avant de payer")
    if not payload.accept_terms:
        raise HTTPException(
            status_code=400,
            detail="Coche la case : CGV acceptées et accès immédiat au jeu complet",
        )
    session = stripe_call("POST", "/checkout/sessions", checkout_fields(user, _site(request)))
    return CheckoutOut(url=session["url"])


@router.post("/confirm", response_model=UserOut)
def confirm(payload: ConfirmIn, user: UserDep) -> UserOut:
    """Au retour de Stripe : vérifie chez lui que la session est réglée, et par ce
    compte, puis le débloque et l'abonne (402 tant que le paiement n'est pas reçu)."""
    if user.premium:
        return user_out(user)
    if not _SESSION_ID.match(payload.session_id):
        raise HTTPException(status_code=400, detail="Paiement inconnu")
    session = stripe_call("GET", f"/checkout/sessions/{payload.session_id}")
    ours = (session.get("metadata") or {}).get("app") == APP
    if not ours or session.get("client_reference_id") != str(user.id):
        raise HTTPException(status_code=403, detail="Ce paiement n'est pas celui de ton compte")
    try:
        granted = _grant_if_paid(session)
    except HTTPException:
        # Stripe a refusé l'abonnement après le paiement : la saison payée reste au
        # joueur, et le webhook, rappelé par Stripe, créera l'abonnement.
        granted = accounts.get(user.id)
        if granted is None or not granted.premium:
            raise
    if granted is None:
        raise HTTPException(
            status_code=PAYMENT_REQUIRED, detail="Le paiement n'est pas encore confirmé"
        )
    return user_out(granted)


@router.post("/portal", response_model=CheckoutOut)
def portal(user: UserDep, request: Request) -> CheckoutOut:
    """Ouvre l'espace client de Stripe (carte, factures, résiliation) du compte abonné."""
    if not user.stripe_customer:
        raise HTTPException(status_code=404, detail="Pas d'abonnement à gérer")
    session = stripe_call(
        "POST",
        "/billing_portal/sessions",
        {"customer": user.stripe_customer, "return_url": f"{_site(request)}/parties"},
    )
    return CheckoutOut(url=session["url"])


@router.post("/webhook", include_in_schema=False)
async def webhook(request: Request) -> dict[str, bool]:
    """Stripe prévient d'un paiement ; seuls ses appels signés sont crus."""
    secret = os.environ.get("STRIPE_WEBHOOK_SECRET")
    if not secret:
        raise HTTPException(status_code=503, detail="Webhook non configuré")
    payload = await request.body()
    if not verify_signature(payload, request.headers.get("stripe-signature", ""), secret):
        raise HTTPException(status_code=400, detail="Signature invalide")
    event = json.loads(payload)
    if event.get("type") in PAID_EVENTS:
        # Un virement arrive « unpaid » d'abord, puis par async_payment_succeeded.
        checkout = event["data"]["object"]
        granted = await run_in_threadpool(_grant_if_paid, checkout)
        ours = (checkout.get("metadata") or {}).get("app") == APP
        if granted is None and ours and checkout.get("payment_status") in SETTLED:
            log.warning("Paiement Stripe %s sans compte à débloquer", checkout.get("id"))
    elif event.get("type") == RENEWAL_EVENT:
        # Les clients des autres ventes du compte Stripe ne sont rattachés à aucun compte.
        if customer := event["data"]["object"].get("customer"):
            await run_in_threadpool(accounts.renew_premium, customer)
    return {"received": True}
