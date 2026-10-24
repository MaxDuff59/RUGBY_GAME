"""Paiement du jeu complet : 2 €, une fois, par Stripe Checkout (voir api/plans.py).

1. `POST /billing/checkout` crée une page de paiement Stripe pour le compte connecté
   et renvoie son adresse : le navigateur y part.
2. Stripe ramène le joueur sur `/parties?paiement=ok&session_id=...` ; l'interface
   appelle `POST /billing/confirm`, qui relit la session chez Stripe et débloque le compte.
3. Stripe prévient aussi `POST /billing/webhook` (checkout.session.completed) : le
   compte est débloqué même si le joueur ferme l'onglet avant de revenir.

Configuration, par variables d'environnement :
- `STRIPE_SECRET_KEY` (sk_live_... ou sk_test_...) : sans elle, le paiement est fermé ;
- `STRIPE_WEBHOOK_SECRET` (whsec_...) : signature des appels de Stripe au webhook ;
- `STRIPE_PRICE_ID` (facultatif) : un prix créé dans le tableau de bord Stripe, sinon 2 € ;
- `RUGBY_PUBLIC_URL` (facultatif) : adresse de l'interface pour le retour, sinon
  l'origine de la requête.

L'API de Stripe s'appelle en bibliothèque standard (urllib), sans son SDK.
"""

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
PRODUCT_DESCRIPTION = "Autant de parties et de saisons que tu veux, pour toujours."
# Marque des paiements du jeu : le compte Stripe peut servir à d'autres ventes, dont les
# événements arrivent aussi au webhook et ne débloquent rien ici.
APP = "rugby-manager"
# Écart toléré entre l'horodatage signé par Stripe et notre horloge (rejeu d'un appel).
SIGNATURE_TOLERANCE = 300
_SESSION_ID = re.compile(r"^cs_[A-Za-z0-9_]{1,250}$")
# Événements de Stripe qui signalent un paiement reçu (carte : aussitôt ; virement : après).
PAID_EVENTS = {"checkout.session.completed", "checkout.session.async_payment_succeeded"}

log = logging.getLogger(__name__)
router = APIRouter(prefix="/billing", tags=["paiement"])


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


def stripe_call(method: str, path: str, fields: dict[str, str] | None = None) -> dict:
    """Appelle l'API de Stripe (formulaire en entrée, JSON en sortie) ; 502 si elle
    refuse ou ne répond pas, avec la raison dans le journal du serveur."""
    request = urllib.request.Request(
        STRIPE_API + path,
        data=urllib.parse.urlencode(fields).encode() if fields else None,
        method=method,
        headers={"Authorization": f"Bearer {_secret_key()}"},
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            return json.load(response)
    except urllib.error.HTTPError as error:
        try:
            reason = json.load(error).get("error", {}).get("message")
        except ValueError:
            reason = None
        log.error("Stripe %s %s : %s %s", method, path, error.code, reason)
        raise HTTPException(status_code=502, detail="Stripe a refusé la demande") from error
    except urllib.error.URLError as error:
        log.error("Stripe %s %s injoignable : %s", method, path, error.reason)
        raise HTTPException(status_code=502, detail="Stripe ne répond pas : réessaie") from error


def checkout_fields(user: accounts.User, site: str) -> dict[str, str]:
    """La session de paiement d'un compte : 2 € (ou le prix `STRIPE_PRICE_ID`), une
    fois, rattachée au compte par `client_reference_id`."""
    fields = {
        "mode": "payment",
        "client_reference_id": str(user.id),
        "customer_email": user.email,
        "metadata[user_id]": str(user.id),
        "metadata[app]": APP,
        "success_url": f"{site}/parties?paiement=ok&session_id={{CHECKOUT_SESSION_ID}}",
        "cancel_url": f"{site}/parties?paiement=annule",
        "line_items[0][quantity]": "1",
    }
    if price := os.environ.get("STRIPE_PRICE_ID"):
        fields["line_items[0][price]"] = price
    else:
        fields |= {
            "line_items[0][price_data][currency]": "eur",
            "line_items[0][price_data][unit_amount]": str(PRICE_CENTS),
            "line_items[0][price_data][product_data][name]": PRODUCT_NAME,
            "line_items[0][price_data][product_data][description]": PRODUCT_DESCRIPTION,
        }
    return fields


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
    """Débloque le compte d'une session de paiement du jeu, réglée (None sinon)."""
    reference = checkout.get("client_reference_id") or ""
    if (
        (checkout.get("metadata") or {}).get("app") != APP
        or checkout.get("payment_status") != "paid"
        or not reference.isdigit()
    ):
        return None
    return accounts.grant_premium(int(reference), checkout.get("payment_intent") or checkout["id"])


# --- Routes ---------------------------------------------------------------------------


@router.post("/checkout", response_model=CheckoutOut)
def checkout(user: UserDep, request: Request) -> CheckoutOut:
    """Ouvre une page de paiement Stripe pour le compte connecté."""
    if user.premium:
        raise HTTPException(status_code=409, detail="Ton compte a déjà le jeu complet")
    site = os.environ.get("RUGBY_PUBLIC_URL") or request.headers.get("origin")
    site = (site or str(request.base_url)).rstrip("/")
    session = stripe_call("POST", "/checkout/sessions", checkout_fields(user, site))
    return CheckoutOut(url=session["url"])


@router.post("/confirm", response_model=UserOut)
def confirm(payload: ConfirmIn, user: UserDep) -> UserOut:
    """Au retour de Stripe : vérifie chez lui que la session est réglée, et par ce
    compte, puis le débloque (402 tant que le paiement n'est pas reçu)."""
    if user.premium:
        return user_out(user)
    if not _SESSION_ID.match(payload.session_id):
        raise HTTPException(status_code=400, detail="Paiement inconnu")
    session = stripe_call("GET", f"/checkout/sessions/{payload.session_id}")
    ours = (session.get("metadata") or {}).get("app") == APP
    if not ours or session.get("client_reference_id") != str(user.id):
        raise HTTPException(status_code=403, detail="Ce paiement n'est pas celui de ton compte")
    granted = _grant_if_paid(session)
    if granted is None:
        raise HTTPException(
            status_code=PAYMENT_REQUIRED, detail="Le paiement n'est pas encore confirmé"
        )
    return user_out(granted)


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
        if granted is None and ours and checkout.get("payment_status") == "paid":
            log.warning("Paiement Stripe %s sans compte à débloquer", checkout.get("id"))
    return {"received": True}
