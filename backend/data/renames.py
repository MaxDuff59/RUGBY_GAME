"""Les noms d'avant : le jeu a d'abord porté les noms de vrais clubs et de vrais joueurs.

Tout y est inventé désormais. Les parties commencées avant et le catalogue du backoffice
gardent les anciens noms : ils sont renommés à leur ouverture (database.py, catalog.py).
data/renames.json ne garde que l'empreinte de chaque ancien nom, avec le nom qui le
remplace : on retrouve le nouveau nom d'un ancien, jamais l'inverse.
"""

import hashlib
import json
from functools import cache
from pathlib import Path

RENAMES_PATH = Path(__file__).with_name("renames.json")


def _key(name: str) -> str:
    return hashlib.sha256(name.encode()).hexdigest()[:16]


@cache
def _table() -> dict[str, dict[str, str]]:
    return json.loads(RENAMES_PATH.read_text())


def club(name: str | None) -> str | None:
    """Le nouveau nom de cet ancien club, None si ce n'en est pas un."""
    return _table()["clubs"].get(_key(name)) if name else None


def player(name: str | None) -> str | None:
    """Le nouveau nom complet de cet ancien joueur, None si ce n'en est pas un."""
    return _table()["players"].get(_key(name.strip())) if name else None


def text(value):
    """Une valeur enregistrée, renommée si c'est un ancien nom de club ou de joueur."""
    if not isinstance(value, str):
        return value
    return club(value) or player(value) or value


def roster(roster: dict) -> dict:
    """Un effectif au format de data/rosters.json, joueurs renommés et sans leur photo
    d'origine (une photo envoyée depuis le backoffice reste)."""
    renamed = dict(roster)
    for group in ("pros", "youths"):
        if group in roster:
            renamed[group] = [
                {
                    **{k: v for k, v in entry.items() if k != "photo"},
                    "name": player(entry.get("name")) or entry.get("name"),
                }
                for entry in roster[group]
            ]
    return renamed
