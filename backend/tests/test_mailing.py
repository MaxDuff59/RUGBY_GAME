"""Relances par mail : qui les reçoit (gratuits seulement, pas deux fois de suite), ce
qu'elles contiennent, et la désinscription."""

import re

import pytest
from fastapi.testclient import TestClient

import accounts
import mailer
from api import auth
from api.main import app
from api.routers.admin import ADMIN_EMAIL

MESSAGE = {
    "subject": "Ton club t'attend",
    "body": "Bonjour,\n\nIl te reste {saisons_restantes} saison.\nPrix : {prix}.",
    "cta": "Reprendre ma partie",
}


def sign_up(email: str) -> TestClient:
    client = TestClient(app)
    created = client.post("/auth/register", json={"email": email, "password": "ballon-ovale"})
    assert created.status_code == 201, created.text
    return client


@pytest.fixture
def outbox(monkeypatch) -> list[mailer.Mail]:
    """Les mails « envoyés » : Resend n'est jamais appelé."""
    sent: list[mailer.Mail] = []
    monkeypatch.setenv("RESEND_API_KEY", "re_test")
    monkeypatch.setenv("MAIL_FROM", "Rugby Manager <contact@example.com>")
    monkeypatch.setattr(mailer, "send", lambda mails: sent.extend(mails))
    return sent


@pytest.fixture
def admin(world) -> TestClient:
    auth._attempts.clear()
    return sign_up(ADMIN_EMAIL)


def segment(data: dict, key: str) -> dict:
    return next(s for s in data["segments"] if s["key"] == key)


def test_only_admins(admin):
    player = sign_up("joueur@example.com")
    assert player.get("/backoffice/relances").status_code == 403
    assert TestClient(app).post("/backoffice/relances/envoi", json={}).status_code == 401


def test_who_gets_mailed(admin, outbox):
    sign_up("neuf@example.com")
    sign_up("essai@example.com")
    sign_up("bout@example.com")
    sign_up("paye@example.com")
    TestClient(app).post("/auth/guest")
    essai, bout, paye = (accounts.find(f"{n}@example.com") for n in ("essai", "bout", "paye"))
    accounts.count_season(essai.id)
    for _ in range(accounts.FREE_SEASONS):
        accounts.count_season(bout.id)
        accounts.count_season(paye.id)
    accounts.grant_premium(paye.id, "pi_1")

    data = admin.get("/backoffice/relances").json()
    assert not data["configured"] or data["sender"]
    emails = {s["key"]: [r["email"] for r in s["recipients"]] for s in data["segments"]}
    # Ni l'administrateur, ni l'invité, ni le compte complet.
    assert emails == {
        "au-bout": ["bout@example.com"],
        "en-cours": ["essai@example.com"],
        "jamais-joue": ["neuf@example.com"],
    }


def test_send_then_rest(admin, outbox):
    sign_up("essai@example.com")
    user = accounts.find("essai@example.com")
    accounts.count_season(user.id)

    sent = admin.post(
        "/backoffice/relances/envoi",
        json={**MESSAGE, "segment": "en-cours", "user_ids": [user.id, 999]},
        headers={"origin": "https://rugby.example"},
    ).json()
    assert sent == {"sent": 1, "to": ["essai@example.com"], "error": None}
    (mail,) = outbox
    assert mail.to == "essai@example.com" and mail.subject == "Ton club t'attend"
    assert "Il te reste 1 saison." in mail.text and "{prix}" not in mail.text
    assert "https://rugby.example/parties" in mail.html
    assert mail.headers["List-Unsubscribe"].startswith(
        "<https://rugby.example/api/mail/desinscription?u="
    )

    # Relancé : il sort du groupe le temps du délai, et l'envoi est noté.
    data = admin.get("/backoffice/relances").json()
    assert segment(data, "en-cours")["recipients"] == []
    assert segment(data, "en-cours")["resting"] == 1
    assert data["history"][0]["count"] == 1
    again = admin.post(
        "/backoffice/relances/envoi",
        json={**MESSAGE, "segment": "en-cours", "user_ids": [user.id]},
    )
    assert again.status_code == 400 and len(outbox) == 1


def test_wrong_segment_is_ignored(admin, outbox):
    sign_up("neuf@example.com")
    user = accounts.find("neuf@example.com")
    sent = admin.post(
        "/backoffice/relances/envoi",
        json={**MESSAGE, "segment": "au-bout", "user_ids": [user.id]},
    )
    assert sent.status_code == 400 and outbox == []


def test_preview_and_test_mail(admin, outbox):
    sign_up("neuf@example.com")
    preview = admin.post(
        "/backoffice/relances/apercu", json={**MESSAGE, "segment": "jamais-joue"}
    ).json()
    assert preview["example"] == "neuf@example.com"
    assert f"Il te reste {accounts.FREE_SEASONS} saison." in preview["html"]

    tested = admin.post("/backoffice/relances/test", json={**MESSAGE, "segment": "jamais-joue"})
    assert tested.json()["to"] == [ADMIN_EMAIL]
    assert outbox[0].to == ADMIN_EMAIL
    # Un test ne compte pas comme une relance.
    assert admin.get("/backoffice/relances").json()["history"] == []


def test_not_configured(admin, monkeypatch):
    monkeypatch.delenv("RESEND_API_KEY", raising=False)
    assert admin.get("/backoffice/relances").json()["configured"] is False
    tested = admin.post("/backoffice/relances/test", json={**MESSAGE, "segment": "au-bout"})
    assert tested.status_code == 502


def test_unsubscribe(admin, outbox):
    sign_up("essai@example.com")
    user = accounts.find("essai@example.com")
    accounts.count_season(user.id)
    admin.post(
        "/backoffice/relances/envoi",
        json={**MESSAGE, "segment": "en-cours", "user_ids": [user.id]},
    )
    link = re.search(r"/api(/mail/desinscription\?u=\d+&t=[\w-]+)", outbox[0].text).group(1)
    visitor = TestClient(app)

    # Ouvrir le lien demande confirmation, sans désinscrire.
    page = visitor.get(link)
    assert page.status_code == 200 and "Ne plus recevoir ces mails" in page.text
    assert visitor.get(link.replace("&t=", "&t=x")).text.count("Lien invalide")

    assert "Tu ne recevras plus" in visitor.post(link).text
    data = admin.get("/backoffice/relances").json()
    assert data["opted_out"] == 1
    assert all(not s["recipients"] and not s["resting"] for s in data["segments"])
