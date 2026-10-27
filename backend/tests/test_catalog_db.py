"""Catalogue dans une autre base que les comptes (`RUGBY_CATALOG_DB_URL`) : le backoffice
local écrit dans celle de la prod, et scripts/push_catalog.py y recopie l'existant."""

import sys

import pytest
from sqlalchemy import create_engine, inspect, select
from sqlalchemy.orm import Session

import accounts
import catalog
from api import auth
from scripts import push_catalog
from tests.test_admin import ADMIN, PIXEL, club_form, sign_up


@pytest.fixture
def remote(world, tmp_path, monkeypatch) -> str:
    """Une base de catalogue à part (un fichier SQLite pour « la prod »)."""
    url = f"sqlite:///{tmp_path / 'prod.db'}"
    monkeypatch.setenv("RUGBY_CATALOG_DB_URL", url)
    monkeypatch.setattr(catalog, "_own", None)
    yield url
    if catalog._own is not None:
        catalog._own.dispose()
    monkeypatch.setattr(catalog, "_own", None)


def remote_names(url: str) -> list[str]:
    with Session(create_engine(url)) as session:
        return list(session.scalars(select(catalog.ClubEditRow.name)))


def test_backoffice_writes_to_the_catalog_database(remote):
    auth._attempts.clear()
    admin = sign_up(ADMIN)
    club = admin.get("/backoffice/clubs/Stade Toulousain").json()
    saved = admin.put("/backoffice/clubs/Stade Toulousain", json=club_form(club, capacity=40_000))
    assert saved.status_code == 200, saved.text
    assert remote_names(remote) == ["Stade Toulousain"]
    # Les comptes, eux, restent dans leur base, sans le catalogue.
    tables = inspect(accounts.engine()).get_table_names()
    assert "users" in tables and "catalog_clubs" not in tables


def test_push_copies_local_edits(world, tmp_path, monkeypatch, capsys):
    local = f"sqlite:///{tmp_path / 'local.db'}"
    prod = f"sqlite:///{tmp_path / 'prod.db'}"
    monkeypatch.setenv("RUGBY_CATALOG_DB_URL", local)
    monkeypatch.setattr(catalog, "_own", None)
    catalog.save_club("Stade Toulousain", ADMIN, capacity=40_000)
    catalog.save_logo("Stade Toulousain", "image/png", PIXEL)
    catalog._own.dispose()
    monkeypatch.setattr(catalog, "_own", None)
    monkeypatch.delenv("RUGBY_CATALOG_DB_URL")

    argv = ["push_catalog", "--from", local, "--to", prod, "--yes"]
    monkeypatch.setattr(sys, "argv", argv)
    push_catalog.main()
    assert "2 lignes recopiées" in capsys.readouterr().out
    assert remote_names(prod) == ["Stade Toulousain"]

    # Une seconde fois, rien ne change.
    push_catalog.main()
    assert "Rien à recopier" in capsys.readouterr().out
