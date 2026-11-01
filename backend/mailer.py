"""Envoi de mails, par l'API de Resend (https://resend.com), en bibliothèque standard.

Par HTTP plutôt que SMTP : Railway ferme les ports SMTP sortants sur ses petites offres.

Configuration, par variables d'environnement :
- `RESEND_API_KEY` (re_...) : sans elle, rien ne part (`configured()` répond False) ;
- `MAIL_FROM` : l'expéditeur, sur un domaine vérifié chez Resend, par exemple
  « Rugby Manager <contact@rugby-manager.app> » ;
- `MAIL_REPLY_TO` (facultatif) : l'adresse où arrivent les réponses.
"""

import json
import logging
import os
import urllib.error
import urllib.request
from dataclasses import dataclass, field

RESEND_API = "https://api.resend.com"
# Resend prend au plus 100 mails par appel groupé.
BATCH_SIZE = 100

log = logging.getLogger(__name__)


class MailError(Exception):
    """Envoi refusé ou impossible, avec la raison à montrer dans le backoffice."""


@dataclass(frozen=True)
class Mail:
    to: str
    subject: str
    html: str
    text: str
    headers: dict[str, str] = field(default_factory=dict)


def configured() -> bool:
    return bool(os.environ.get("RESEND_API_KEY") and os.environ.get("MAIL_FROM"))


def sender() -> str | None:
    return os.environ.get("MAIL_FROM")


def _payload(mail: Mail) -> dict:
    payload = {
        "from": os.environ["MAIL_FROM"],
        "to": [mail.to],
        "subject": mail.subject,
        "html": mail.html,
        "text": mail.text,
    }
    if mail.headers:
        payload["headers"] = mail.headers
    if reply_to := os.environ.get("MAIL_REPLY_TO"):
        payload["reply_to"] = reply_to
    return payload


def _call(path: str, body: object) -> dict:
    request = urllib.request.Request(
        RESEND_API + path,
        data=json.dumps(body).encode(),
        method="POST",
        headers={
            "Authorization": f"Bearer {os.environ['RESEND_API_KEY']}",
            "Content-Type": "application/json",
            # Sans agent nommé, le pare-feu devant l'API refuse celui d'urllib.
            "User-Agent": "rugby-manager",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.load(response)
    except urllib.error.HTTPError as error:
        try:
            reason = json.load(error).get("message")
        except ValueError:
            reason = None
        log.error("Resend %s : %s %s", path, error.code, reason)
        raise MailError(f"Resend a refusé l'envoi : {reason or error.code}") from error
    except urllib.error.URLError as error:
        log.error("Resend %s injoignable : %s", path, error.reason)
        raise MailError("Resend ne répond pas : réessaie") from error


def send(mails: list[Mail]) -> None:
    """Envoie un paquet d'au plus `BATCH_SIZE` mails, en un appel (MailError s'il est
    refusé : aucun ne part)."""
    if not configured():
        raise MailError("L'envoi de mails n'est pas configuré (RESEND_API_KEY, MAIL_FROM)")
    if len(mails) > BATCH_SIZE:
        raise ValueError(f"Au plus {BATCH_SIZE} mails par paquet")
    if len(mails) == 1:
        _call("/emails", _payload(mails[0]))
    elif mails:
        _call("/emails/batch", [_payload(mail) for mail in mails])
