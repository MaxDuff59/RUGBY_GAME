"""Abonnement au jeu complet : 2 € par an, par Stripe (voir api/plans.py).

Le jeu complet vaut pour la saison du jeu, jusqu'au 1er juillet (accounts.season_end) :
la première saison se paie tout de suite, en entier, puis l'abonnement se renouvelle
chaque 1er juillet. Sans renouvellement (résilié, carte refusée), le compte repasse en
gratuit.

1. `POST /billing/checkout` crée une page de paiement Stripe pour le compte connecté
   et renvoie son adresse : le navigateur y part. La saison en cours y est une ligne
   payée une fois, sur la première facture ; l'abonnement annuel démarre au 1er
   juillet, au bout d'une période d'essai (`trial_end`). Stripe refuse l'autre montage,
   un ancrage au 1er juillet sans prorata, dès qu'il y a une ligne payée une fois.
2. Stripe ramène le joueur sur `/parties?paiement=ok&session_id=...` ; l'interface
   appelle `POST /billing/confirm`, qui relit la session chez Stripe et débloque le compte.
3. Stripe prévient aussi `POST /billing/webhook` : checkout.session.completed débloque
   le compte même si le joueur ferme l'onglet avant de revenir, invoice.paid (chaque
   1er juillet) le prolonge d'un an.
4. `POST /billing/portal` ouvre l'espace client de Stripe : carte, factures, résiliation.

Configuration, par variables d'environnement :
- `STRIPE_SECRET_KEY` (sk_live_... ou sk_test_...) : sans elle, le paiement est fermé ;
- `STRIPE_WEBHOOK_SECRET` (whsec_...) : signature des appels de Stripe au webhook ;
- `RUGBY_PUBLIC_URL` (facultatif) : adresse de l'interface pour le retour, sinon
  l'origine de la requête.
Dans le tableau de bord Stripe : le webhook écoute checkout.session.completed,
checkout.session.async_payment_succeeded et invoice.paid ; l'espace client
(Paramètres → Facturation → Portail client) est activé, résiliation comprise.

Codes promo : la page de paiement en accepte (`allow_promotion_codes`). Un coupon de
100 % créé dans le tableau de bord Stripe offre le jeu complet : la session se règle
alors à 0 € (`no_payment_required`) et débloque le compte comme un paiement.

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


def long_day(day: datetime.date) -> str:
    """« 1er juillet 2027 »."""
    return f"{'1er' if day.day == 1 else day.day} {MONTHS[day.month - 1]} {day.year}"


def checkout_fields(user: accounts.User, site: str) -> dict[str, str]:
    """La session d'abonnement d'un compte, rattachée à lui par `client_reference_id` :
    2 € tout de suite pour la saison en cours, puis 2 € chaque 1er juillet."""
    end = accounts.sold_season_end()
    until = long_day(accounts.paris_day(end))
    yearly = "line_items[0][price_data]"
    season = "line_items[1][price_data]"
    fields = {
        "mode": "subscription",
        "client_reference_id": str(user.id),
        "metadata[user_id]": str(user.id),
        "metadata[app]": APP,
        "subscription_data[metadata][user_id]": str(user.id),
        "subscription_data[metadata][app]": APP,
        # Premier prélèvement de l'abonnement le 1er juillet, puis chaque année ; la
        # période d'ici là est payée par la ligne de la saison en cours.
        "subscription_data[trial_end]": str(int(end.replace(tzinfo=datetime.UTC).timestamp())),
        "success_url": f"{site}/parties?paiement=ok&session_id={{CHECKOUT_SESSION_ID}}",
        "cancel_url": f"{site}/parties?paiement=annule",
        "allow_promotion_codes": "true",
        "line_items[0][quantity]": "1",
        f"{yearly}[currency]": "eur",
        f"{yearly}[unit_amount]": str(PRICE_CENTS),
        f"{yearly}[recurring][interval]": "year",
        f"{yearly}[product_data][name]": PRODUCT_NAME,
        f"{yearly}[product_data][description]": PRODUCT_DESCRIPTION,
        "line_items[1][quantity]": "1",
        f"{season}[currency]": "eur",
        f"{season}[unit_amount]": str(PRICE_CENTS),
        f"{season}[product_data][name]": f"{PRODUCT_NAME} : saison en cours, jusqu'au {until}",
        # Sous le bouton « S'abonner ».
        "custom_text[submit][message]": (
            f"Le jeu complet vaut pour la saison, jusqu'au {until}. L'abonnement se "
            "renouvelle ensuite chaque 1er juillet, avec la nouvelle version du jeu ; "
            "résiliable à tout moment depuis le jeu."
        ),
    }
    # Stripe va chercher l'image lui-même : seulement depuis une adresse publique.
    if site.startswith("https://"):
        fields[f"{yearly}[product_data][images][0]"] = site + PRODUCT_IMAGE
        fields[f"{season}[product_data][images][0]"] = site + PRODUCT_IMAGE
    # Un compte déjà client (abonnement arrêté, puis repris) garde sa fiche chez Stripe.
    if user.stripe_customer:
        fields["customer"] = user.stripe_customer
    else:
        fields["customer_email"] = user.email
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
    """Débloque le compte d'une session de paiement du jeu, réglée ou offerte (None
    sinon)."""
    reference = checkout.get("client_reference_id") or ""
    if (
        (checkout.get("metadata") or {}).get("app") != APP
        or checkout.get("payment_status") not in SETTLED
        or not reference.isdigit()
    ):
        return None
    return accounts.grant_premium(
        int(reference),
        checkout.get("subscription") or checkout.get("payment_intent") or checkout["id"],
        checkout.get("customer"),
    )


# --- Routes ---------------------------------------------------------------------------


def _site(request: Request) -> str:
    """L'adresse de l'interface, où Stripe ramène le joueur."""
    site = os.environ.get("RUGBY_PUBLIC_URL") or request.headers.get("origin")
    return (site or str(request.base_url)).rstrip("/")


@router.post("/checkout", response_model=CheckoutOut)
def checkout(user: UserDep, request: Request) -> CheckoutOut:
    """Ouvre une page de paiement Stripe pour le compte connecté."""
    if user.premium:
        raise HTTPException(status_code=409, detail="Ton compte a déjà le jeu complet")
    if user.guest:
        raise HTTPException(status_code=403, detail="Crée un compte avant de payer")
    session = stripe_call("POST", "/checkout/sessions", checkout_fields(user, _site(request)))
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
