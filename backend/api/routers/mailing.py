"""Relances par mail des comptes gratuits, depuis le backoffice, et désinscription.

L'administrateur choisit un groupe (au bout des saisons gratuites, en cours d'essai,
inscrits sans avoir joué), relit le message, s'envoie un test, puis l'envoie. Ne
reçoivent jamais rien : les invités, les comptes complets, l'administrateur, les
désinscrits, ni un compte déjà relancé il y a moins de `COOLDOWN_DAYS` jours.

Chaque mail porte un lien « ne plus recevoir ces mails » (et l'en-tête
List-Unsubscribe, désinscription en un clic chez Gmail ou Yahoo) : il ouvre une page
de l'API qui demande confirmation, pour qu'un antivirus qui suit les liens ne
désinscrive personne.

L'envoi passe par mailer.py (Resend), configuré par variables d'environnement.
"""

import datetime
import hmac
import html
import os
import secrets
from collections.abc import Callable
from dataclasses import dataclass

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

import accounts
import mailer
from api.plans import PRICE_LABEL
from api.routers.admin import ADMIN_EMAIL, AdminDep

router = APIRouter(prefix="/backoffice/relances", tags=["backoffice"])
public = APIRouter(prefix="/mail", tags=["mail"])

# Un compte relancé ne l'est plus pendant ce temps, quel que soit le groupe.
COOLDOWN_DAYS = 14
# Couleurs du jeu (frontend/src/styles.css), en dur : les messageries ignorent les variables.
INK, MUTED, LINE, SURFACE, BG, ACCENT = (
    "#16181b",
    "#5e6168",
    "#d6d6d0",
    "#f7f7f4",
    "#edede8",
    "#7a1f2b",
)


@dataclass(frozen=True)
class Segment:
    key: str
    label: str
    description: str
    keep: Callable[[accounts.UserRow], bool]
    subject: str
    body: str
    cta: str


def _played(row: accounts.UserRow) -> int:
    return row.seasons_played or 0


def _left(row: accounts.UserRow) -> int:
    return max(0, accounts.FREE_SEASONS - _played(row))


SEGMENTS = [
    Segment(
        key="au-bout",
        label="Au bout des saisons gratuites",
        description="Ont joué leurs saisons gratuites : la partie est bloquée.",
        keep=lambda row: _left(row) == 0,
        subject="Ton club t'attend sur Rugby Manager",
        body=(
            "Bonjour,\n\n"
            "Tu as joué tes saisons gratuites sur Rugby Manager : merci d'avoir lancé "
            "ta carrière avec nous.\n\n"
            "Ton club n'a pas dit son dernier mot. Avec le jeu complet, tu reprends ta "
            "partie là où tu l'as laissée, sans limite de saisons, et tu peux mener "
            "jusqu'à trois carrières en parallèle.\n\n"
            "Le jeu complet, c'est {prix}.\n\n"
            "À bientôt sur le terrain,\nRugby Manager"
        ),
        cta="Reprendre ma partie",
    ),
    Segment(
        key="en-cours",
        label="En cours d'essai",
        description="Ont commencé à jouer et ont encore des saisons gratuites.",
        keep=lambda row: _played(row) > 0 and _left(row) > 0,
        subject="Ta saison continue sur Rugby Manager",
        body=(
            "Bonjour,\n\n"
            "Ton club t'attend : il te reste {saisons_restantes} saison gratuite à jouer "
            "sur Rugby Manager.\n\n"
            "Et quand tu voudras aller plus loin, le jeu complet t'ouvre des saisons sans "
            "fin et trois carrières en parallèle, pour {prix}.\n\n"
            "À bientôt sur le terrain,\nRugby Manager"
        ),
        cta="Reprendre ma partie",
    ),
    Segment(
        key="jamais-joue",
        label="Inscrits sans avoir joué",
        description="Ont créé un compte sans commencer de saison.",
        keep=lambda row: _played(row) == 0,
        subject="Ton club est prêt sur Rugby Manager",
        body=(
            "Bonjour,\n\n"
            "Tu as créé ton compte sur Rugby Manager, mais ta première saison n'a pas "
            "encore commencé.\n\n"
            "Choisis ton club, compose ton XV et lance le premier match : tes "
            "{saisons_restantes} saisons gratuites t'attendent.\n\n"
            "À bientôt sur le terrain,\nRugby Manager"
        ),
        cta="Choisir mon club",
    ),
]
SEGMENTS_BY_KEY = {segment.key: segment for segment in SEGMENTS}


def _now() -> datetime.datetime:
    return datetime.datetime.now(datetime.UTC).replace(tzinfo=None)


def _session() -> Session:
    return Session(accounts.engine(), expire_on_commit=False)


def _segment(key: str) -> Segment:
    segment = SEGMENTS_BY_KEY.get(key)
    if segment is None:
        raise HTTPException(status_code=404, detail="Groupe inconnu")
    return segment


# --- Destinataires ------------------------------------------------------------------------


def _last_mails(session: Session) -> dict[int, datetime.datetime]:
    rows = session.execute(
        select(accounts.MailRow.user_id, func.max(accounts.MailRow.sent_at)).group_by(
            accounts.MailRow.user_id
        )
    )
    return {user_id: at for user_id, at in rows}


def _contactable(session: Session) -> list[accounts.UserRow]:
    """Les comptes sans jeu complet qu'on a le droit de relancer (tous groupes confondus) :
    un jeu complet arrivé à son terme compte comme gratuit, comme pour le jeu (accounts.py)."""
    rows = session.scalars(
        select(accounts.UserRow)
        .where(
            ~accounts.UserRow.guest,
            accounts.UserRow.mail_opt_out_at.is_(None),
            accounts.UserRow.email != ADMIN_EMAIL,
        )
        .order_by(accounts.UserRow.id.desc())
    )
    return [
        row
        for row in rows
        if not accounts._user(row).premium and not row.email.endswith(f"@{accounts.GUEST_DOMAIN}")
    ]


def _resting(last: datetime.datetime | None) -> bool:
    return last is not None and last > _now() - datetime.timedelta(days=COOLDOWN_DAYS)


# --- Message ------------------------------------------------------------------------------


def _fill(text: str, row: accounts.UserRow) -> str:
    values = {
        "saisons_jouees": str(_played(row)),
        "saisons_restantes": str(_left(row)),
        "prix": PRICE_LABEL,
    }
    for name, value in values.items():
        text = text.replace("{" + name + "}", value)
    return text


def _site(request: Request) -> str:
    """Adresse de l'interface, pour les liens des mails."""
    site = os.environ.get("RUGBY_PUBLIC_URL") or request.headers.get("origin")
    return (site or str(request.base_url)).rstrip("/")


def _unsubscribe_url(site: str, row: accounts.UserRow) -> str:
    return f"{site}/api/mail/desinscription?u={row.id}&t={row.mail_token}"


def _ensure_token(row: accounts.UserRow) -> None:
    if not row.mail_token:
        row.mail_token = secrets.token_urlsafe(24)


def _html(paragraphs: str, cta: str, cta_url: str, unsubscribe: str) -> str:
    blocks = "".join(
        f'<p style="margin:0 0 16px">{html.escape(block).replace(chr(10), "<br>")}</p>'
        for block in paragraphs.split("\n\n")
        if block.strip()
    )
    button = ""
    if cta:
        button = (
            f'<tr><td style="padding:8px 32px 32px"><a href="{html.escape(cta_url)}" '
            f'style="display:inline-block;background:{ACCENT};color:#ffffff;padding:13px 22px;'
            f'border-radius:6px;text-decoration:none;font-weight:600">{html.escape(cta)}</a>'
            "</td></tr>"
        )
    return (
        '<!DOCTYPE html><html lang="fr"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1"></head>'
        f'<body style="margin:0;background:{BG};font-family:Helvetica,Arial,sans-serif">'
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0">'
        '<tr><td align="center" style="padding:32px 16px">'
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
        f'style="max-width:560px;background:{SURFACE};border:1px solid {LINE};border-radius:10px">'
        f'<tr><td style="padding:28px 32px 12px;font-size:12px;letter-spacing:2px;'
        f'text-transform:uppercase;color:{MUTED};font-weight:600">Rugby Manager</td></tr>'
        f'<tr><td style="padding:0 32px;color:{INK};font-size:16px;line-height:1.55">{blocks}'
        f"</td></tr>{button}</table>"
        f'<p style="max-width:560px;margin:16px auto 0;font-size:12px;line-height:1.5;'
        f'color:{MUTED}">Tu reçois ce mail parce que tu as un compte sur Rugby Manager. '
        f'<a href="{html.escape(unsubscribe)}" style="color:{MUTED}">Ne plus recevoir ces '
        "mails</a></p></td></tr></table></body></html>"
    )


class MessageIn(BaseModel):
    segment: str = Field(max_length=32)
    subject: str = Field(min_length=1, max_length=200)
    body: str = Field(min_length=1, max_length=5000)
    cta: str = Field(default="", max_length=60)


def _mail(
    message: MessageIn,
    row: accounts.UserRow,
    site: str,
    recipient: accounts.UserRow | None = None,
) -> mailer.Mail:
    """Le mail de `message` rempli pour le compte `row`, envoyé à `recipient` (lien de
    désinscription compris), à `row` lui-même sinon."""
    recipient = recipient or row
    unsubscribe = _unsubscribe_url(site, recipient)
    cta_url = f"{site}/parties"
    body = _fill(message.body, row).strip()
    text = body
    if message.cta:
        text += f"\n\n{message.cta} : {cta_url}"
    text += f"\n\n--\nNe plus recevoir ces mails : {unsubscribe}"
    return mailer.Mail(
        to=recipient.email,
        subject=_fill(message.subject, row).strip(),
        html=_html(body, message.cta, cta_url, unsubscribe),
        text=text,
        headers={
            "List-Unsubscribe": f"<{unsubscribe}>",
            "List-Unsubscribe-Post": "List-Unsubscribe=One-Click",
        },
    )


# --- Backoffice ---------------------------------------------------------------------------


class RecipientOut(BaseModel):
    id: int
    email: str
    created_at: datetime.datetime
    seasons_played: int
    seasons_left: int
    last_mail_at: datetime.datetime | None


class SegmentOut(BaseModel):
    key: str
    label: str
    description: str
    subject: str
    body: str
    cta: str
    recipients: list[RecipientOut]
    # Comptes du groupe relancés il y a moins de `cooldown_days` jours : laissés de côté.
    resting: int


class BatchOut(BaseModel):
    batch: str
    segment: str
    subject: str
    sent_at: datetime.datetime
    count: int


class MailingOut(BaseModel):
    configured: bool
    sender: str | None
    cooldown_days: int
    opted_out: int
    placeholders: list[str]
    segments: list[SegmentOut]
    history: list[BatchOut]


@router.get("", response_model=MailingOut)
def overview(_: AdminDep) -> MailingOut:
    """Les groupes et leurs destinataires, le message proposé, et les derniers envois."""
    with _session() as session:
        rows = _contactable(session)
        last = _last_mails(session)
        opted_out = session.scalar(
            select(func.count())
            .select_from(accounts.UserRow)
            .where(accounts.UserRow.mail_opt_out_at.is_not(None))
        )
        history = session.execute(
            select(
                accounts.MailRow.batch,
                func.min(accounts.MailRow.segment),
                func.min(accounts.MailRow.subject),
                func.min(accounts.MailRow.sent_at),
                func.count(),
            )
            .group_by(accounts.MailRow.batch)
            .order_by(func.min(accounts.MailRow.sent_at).desc())
            .limit(20)
        ).all()

    segments = []
    for segment in SEGMENTS:
        members = [row for row in rows if segment.keep(row)]
        segments.append(
            SegmentOut(
                key=segment.key,
                label=segment.label,
                description=segment.description,
                subject=segment.subject,
                body=segment.body,
                cta=segment.cta,
                recipients=[
                    RecipientOut(
                        id=row.id,
                        email=row.email,
                        created_at=row.created_at,
                        seasons_played=_played(row),
                        seasons_left=_left(row),
                        last_mail_at=last.get(row.id),
                    )
                    for row in members
                    if not _resting(last.get(row.id))
                ],
                resting=sum(_resting(last.get(row.id)) for row in members),
            )
        )
    return MailingOut(
        configured=mailer.configured(),
        sender=mailer.sender(),
        cooldown_days=COOLDOWN_DAYS,
        opted_out=opted_out,
        placeholders=["{saisons_jouees}", "{saisons_restantes}", "{prix}"],
        segments=segments,
        history=[
            BatchOut(batch=b, segment=s, subject=subj, sent_at=at, count=n)
            for b, s, subj, at, n in history
        ],
    )


def _sample(session: Session, segment: Segment, admin: accounts.User) -> accounts.UserRow:
    """Le compte qui sert d'exemple : le premier du groupe, sinon l'administrateur."""
    members = [row for row in _contactable(session) if segment.keep(row)]
    return members[0] if members else session.get(accounts.UserRow, admin.id)


class PreviewOut(BaseModel):
    subject: str
    html: str
    example: str


@router.post("/apercu", response_model=PreviewOut)
def preview(message: MessageIn, request: Request, admin: AdminDep) -> PreviewOut:
    """Le mail tel qu'il partira, rempli pour un compte du groupe."""
    segment = _segment(message.segment)
    with _session() as session:
        row = _sample(session, segment, admin)
        mail = _mail(message, row, _site(request))
    return PreviewOut(subject=mail.subject, html=mail.html, example=row.email)


class SentOut(BaseModel):
    sent: int
    to: list[str]
    error: str | None = None


@router.post("/test", response_model=SentOut)
def send_test(message: MessageIn, request: Request, admin: AdminDep) -> SentOut:
    """Envoie le mail à l'administrateur seul (rempli pour un compte du groupe)."""
    segment = _segment(message.segment)
    with _session() as session:
        row = _sample(session, segment, admin)
        mine = session.get(accounts.UserRow, admin.id)
        _ensure_token(mine)
        session.commit()
        mail = _mail(message, row, _site(request), recipient=mine)
    try:
        mailer.send([mail])
    except mailer.MailError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error
    return SentOut(sent=1, to=[admin.email])


class SendIn(MessageIn):
    user_ids: list[int] = Field(min_length=1, max_length=5000)


@router.post("/envoi", response_model=SentOut)
def send(body: SendIn, request: Request, _: AdminDep) -> SentOut:
    """Envoie le message aux comptes choisis, parmi ceux du groupe qu'on peut relancer
    (les autres sont ignorés). Un paquet refusé arrête l'envoi : ceux d'avant sont partis
    et comptés."""
    segment = _segment(body.segment)
    site = _site(request)
    wanted = set(body.user_ids)
    batch = secrets.token_hex(8)
    sent: list[str] = []
    with _session() as session:
        last = _last_mails(session)
        rows = [
            row
            for row in _contactable(session)
            if row.id in wanted and segment.keep(row) and not _resting(last.get(row.id))
        ]
        if not rows:
            raise HTTPException(status_code=400, detail="Aucun compte à relancer dans ce choix")
        for row in rows:
            _ensure_token(row)
        session.commit()
        for start in range(0, len(rows), mailer.BATCH_SIZE):
            chunk = rows[start : start + mailer.BATCH_SIZE]
            try:
                mailer.send([_mail(body, row, site) for row in chunk])
            except mailer.MailError as error:
                return SentOut(sent=len(sent), to=sent, error=str(error))
            now = _now()
            for row in chunk:
                session.add(
                    accounts.MailRow(
                        user_id=row.id,
                        batch=batch,
                        segment=segment.key,
                        subject=_fill(body.subject, row).strip()[:200],
                        sent_at=now,
                    )
                )
                sent.append(row.email)
            session.commit()
    return SentOut(sent=len(sent), to=sent)


# --- Désinscription -----------------------------------------------------------------------


def _page(title: str, text: str, form: str = "") -> HTMLResponse:
    return HTMLResponse(
        '<!DOCTYPE html><html lang="fr"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        f"<title>{html.escape(title)} · Rugby Manager</title></head>"
        f'<body style="margin:0;background:{BG};font-family:Helvetica,Arial,sans-serif;'
        f'color:{INK}"><main style="max-width:480px;margin:12vh auto;padding:32px;'
        f'background:{SURFACE};border:1px solid {LINE};border-radius:10px">'
        f'<p style="margin:0 0 8px;font-size:12px;letter-spacing:2px;text-transform:uppercase;'
        f'color:{MUTED};font-weight:600">Rugby Manager</p>'
        f'<h1 style="margin:0 0 12px;font-size:24px">{html.escape(title)}</h1>'
        f'<p style="margin:0 0 20px;line-height:1.5;color:{MUTED}">{html.escape(text)}</p>'
        f"{form}</main></body></html>"
    )


def _subscriber(session: Session, user_id: int, token: str) -> accounts.UserRow | None:
    row = session.get(accounts.UserRow, user_id)
    if row is None or not row.mail_token or not hmac.compare_digest(row.mail_token, token):
        return None
    return row


_INVALID = ("Lien invalide", "Ce lien de désinscription n'est pas (ou plus) valable.")


@public.get("/desinscription", response_class=HTMLResponse)
def unsubscribe_page(u: int, t: str = Query(max_length=64)) -> HTMLResponse:
    """Demande confirmation (un lien suivi par un antivirus ne désinscrit personne)."""
    with _session() as session:
        row = _subscriber(session, u, t)
    if row is None:
        return _page(*_INVALID)
    if row.mail_opt_out_at is not None:
        return _page("C'est noté", "Tu ne recevras plus de mails de Rugby Manager.")
    form = (
        f'<form method="post" action="?u={row.id}&amp;t={html.escape(t)}">'
        f'<button type="submit" style="background:{ACCENT};color:#fff;border:0;'
        'padding:13px 22px;border-radius:6px;font:inherit;font-weight:600;cursor:pointer">'
        "Ne plus recevoir ces mails</button></form>"
    )
    return _page(
        "Se désinscrire",
        f"Tu ne recevras plus de mails de Rugby Manager à l'adresse {row.email}. "
        "Ton compte et tes parties restent intacts.",
        form,
    )


@public.post("/desinscription", response_class=HTMLResponse)
def unsubscribe(u: int, t: str = Query(max_length=64)) -> HTMLResponse:
    """Désinscrit le compte (formulaire de la page, ou désinscription en un clic)."""
    with _session() as session:
        row = _subscriber(session, u, t)
        if row is None:
            return _page(*_INVALID)
        if row.mail_opt_out_at is None:
            row.mail_opt_out_at = _now()
            session.commit()
    return _page("C'est noté", "Tu ne recevras plus de mails de Rugby Manager.")
