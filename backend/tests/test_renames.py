"""Les noms d'avant : les parties et le catalogue du temps des vrais clubs prennent les
noms inventés à leur ouverture (data/renames.py)."""

import datetime

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

import catalog
import database
from data import renames
from data.generator import load_rosters
from data.leagues import LEAGUES
from models import ATTRIBUTE_NAMES
from models.orm import AwardRow, Base, ClubRow, MoveRow, PlayerRow

NOW = datetime.datetime(2026, 11, 16)


@pytest.fixture
def old_names(monkeypatch) -> None:
    """Une table de reprise d'essai : un ancien club et un ancien joueur."""
    table = {
        "clubs": {renames._key("Ancien Club"): "Roses de Paris"},
        "players": {renames._key("Jean Ancien"): "Jean Ancier"},
    }
    monkeypatch.setattr(renames, "_table", lambda: table)


def test_the_table_leads_to_the_clubs_of_the_game():
    table = renames._table()
    clubs = {club.name for league in LEAGUES for club in league.clubs}
    assert set(table["clubs"].values()) == clubs
    # Un nom d'aujourd'hui n'est jamais un ancien nom : une reprise ne se rejoue pas.
    assert not [name for name in clubs if renames.club(name)]
    rostered = [e["name"] for r in load_rosters().values() for e in r["pros"] + r["youths"]]
    assert rostered and not [name for name in rostered if renames.player(name)]


def test_an_old_save_takes_the_new_names(tmp_path, old_names):
    engine = create_engine(f"sqlite:///{tmp_path / 'ancienne.db'}")
    Base.metadata.create_all(engine)
    with sessionmaker(bind=engine)() as session:
        session.add(ClubRow(id=1, name="Ancien Club"))
        session.add(ClubRow(id=2, name="RC Port-Vasor"))
        skills = dict.fromkeys(ATTRIBUTE_NAMES, 12)
        player = dict(age=24, position="PROP", club_id=1, nationality="FRA", **skills)
        session.add(
            PlayerRow(id=1, first_name="Jean", last_name="Ancien", photo="/photos/J.jpg", **player)
        )
        session.add(
            PlayerRow(
                id=2, first_name="Paul", last_name="Inventé", photo="/catalog/photos/ab", **player
            )
        )
        session.commit()
        session.add(
            MoveRow(
                date=NOW.date(), kind="transfer", player_id=1,
                player_name="Jean Ancien", position="PROP", age=24, overall=12.0,
            )
        )  # fmt: skip
        session.commit()

    database.init_db(engine)
    database.init_db(engine)  # une seconde ouverture ne change plus rien

    with sessionmaker(bind=engine)() as session:
        assert list(session.scalars(select(ClubRow.name).order_by(ClubRow.id))) == [
            "Roses de Paris",
            "RC Port-Vasor",
        ]
        jean, paul = session.scalars(select(PlayerRow).order_by(PlayerRow.id)).all()
        assert (jean.first_name, jean.last_name, jean.photo) == ("Jean", "Ancier", None)
        # Un joueur inventé garde son nom, et une photo envoyée depuis le backoffice reste.
        assert (paul.last_name, paul.photo) == ("Inventé", "/catalog/photos/ab")
        assert session.scalars(select(MoveRow.player_name)).one() == "Jean Ancier"
        assert session.scalars(select(AwardRow)).all() == []


def test_the_catalog_takes_the_new_names(tmp_path, old_names):
    engine = create_engine(f"sqlite:///{tmp_path / 'catalogue.db'}")
    catalog.CatalogBase.metadata.create_all(engine)
    roster = {"pros": [{"name": "Jean Ancien", "position": "prop", "photo": "J.jpg"}]}
    with Session(engine) as session:
        session.add(
            catalog.ClubEditRow(
                name="Ancien Club", capacity=30_000, roster=roster, updated_at=NOW, updated_by="a"
            )
        )
        session.add(
            catalog.NationEditRow(
                code="FRA",
                squad=[{"club": "Ancien Club", "name": "Jean Ancien"}],
                updated_at=NOW,
                updated_by="a",
            )
        )
        session.commit()

    catalog.prepare(engine)
    catalog.prepare(engine)

    with Session(engine) as session:
        edit = session.scalars(select(catalog.ClubEditRow)).one()
        assert (edit.name, edit.capacity) == ("Roses de Paris", 30_000)
        assert edit.roster == {"pros": [{"name": "Jean Ancier", "position": "prop"}]}
        compo = session.scalars(select(catalog.NationEditRow)).one()
        assert compo.squad == [{"club": "Roses de Paris", "name": "Jean Ancier"}]
