"""Recopie les retouches du backoffice d'une base à une autre : clubs, championnats,
blasons et photos (les tables du catalogue, catalog.py).

Par défaut, du catalogue local (`users.db` du dossier des parties) vers la base de
`RUGBY_CATALOG_DB_URL` : celle de la prod. Une ligne présente des deux côtés prend la
version d'origine ; une ligne que seule la destination a reste en place. Le script
affiche d'abord ce qui change et demande confirmation.

Usage (depuis le dossier backend/) :
    uv run --env-file .env python -m scripts.push_catalog
    uv run python -m scripts.push_catalog --to postgresql://... --yes
"""

import argparse
import os

from sqlalchemy import create_engine, inspect, select
from sqlalchemy.orm import Session

import catalog
import database

MODELS = (catalog.ClubEditRow, catalog.LeagueRow, catalog.ClubLogoRow, catalog.PlayerPhotoRow)


def _engine(url: str):
    url = database._postgres_url(url)
    if url.startswith("postgresql"):
        return create_engine(url, connect_args={"prepare_threshold": None})
    return create_engine(url)


def _values(row) -> dict:
    return {column.key: getattr(row, column.key) for column in inspect(row).mapper.column_attrs}


def _key(row) -> str:
    return str(inspect(row).identity[0])


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--from", dest="source", default=f"sqlite:///{database.SAVES_DIR / 'users.db'}"
    )
    parser.add_argument("--to", dest="target", default=os.environ.get("RUGBY_CATALOG_DB_URL"))
    parser.add_argument("--yes", action="store_true", help="sans demander confirmation")
    args = parser.parse_args()
    if not args.target:
        parser.error("pas de destination : --to, ou RUGBY_CATALOG_DB_URL")

    source, target = _engine(args.source), _engine(args.target)
    catalog.prepare(source)
    catalog.prepare(target)
    with Session(source) as reading, Session(target) as writing:
        changes = []
        for model in MODELS:
            for row in reading.scalars(select(model)):
                values = _values(row)
                there = writing.get(model, inspect(row).identity)
                if there is None:
                    changes.append(("ajout", model, values, _key(row)))
                elif _values(there) != values:
                    changes.append(("remplacement", model, values, _key(row)))
        if not changes:
            print("Rien à recopier : la destination a déjà tout.")
            return
        for kind, model, _, key in changes:
            print(f"  {kind:<13} {model.__tablename__:<16} {key}")
        if not args.yes and input(f"Recopier ces {len(changes)} lignes ? [o/N] ").lower() != "o":
            print("Rien n'a été recopié.")
            return
        for _, model, values, _ in changes:
            writing.merge(model(**values))
        writing.commit()
    print(f"{len(changes)} lignes recopiées.")


if __name__ == "__main__":
    main()
