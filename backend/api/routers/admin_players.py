"""Backoffice, onglet Joueurs : tous les joueurs des effectifs (catalog.py), un par un.

Un joueur se désigne par son club et son nom (un club n'a pas deux joueurs du même nom).
Le modifier, le faire changer de club, le créer ou le supprimer réécrit l'effectif des
clubs concernés, comme l'onglet Effectif d'un club : pour les nouvelles parties.
Ses notes fixées remplacent le tirage autour du niveau de son club ; sa photo envoyée
passe avant celle de Wikimedia.
"""

import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, HTTPException, Path
from pydantic import Field

import catalog
from api.routers.admin import (
    ROSTER_MAX_PROS,
    ROSTER_MAX_YOUTHS,
    AdminDep,
    ClubName,
    LogoIn,
    PlayerFields,
    Ratings,
    RosterPlayer,
    decode_image,
    player_entry,
)
from data.generator import SEASON_START, photo_path, real_player_level, typical_attributes
from models import Position

router = APIRouter(prefix="/backoffice/players", tags=["backoffice"])

PlayerName = Annotated[str, Path(max_length=100)]
SquadName = Literal["pros", "youths"]
SQUAD_MAX = {"pros": ROSTER_MAX_PROS, "youths": ROSTER_MAX_YOUTHS}
# Âge d'un joueur sans date de naissance, pour ses notes typiques.
DEFAULT_AGE = {"pros": 26, "youths": 19}


class PlayerOut(RosterPlayer):
    club: str
    league: str
    squad: SquadName
    # Adresse de sa photo (envoyée, sinon Wikimedia), None sans photo.
    photo_url: str | None


class PlayerDetail(PlayerOut):
    # Notes d'un joueur comme lui dans ce club, sans hasard : le point de départ des notes fixées.
    typical: Ratings


class PlayerIn(PlayerFields):
    club: str = Field(min_length=1, max_length=100)
    squad: SquadName = "pros"


def _player_out(club: str, league: str, squad: SquadName, entry: dict) -> PlayerOut:
    player = RosterPlayer(
        name=entry["name"][:100],
        position=Position(entry["position"].upper()),
        nationality=(entry.get("nationality") or "").upper()[:3] or None,
        international=bool(entry.get("international")),
        born=entry.get("born"),
        photo=entry.get("photo"),
        attributes=entry.get("attributes"),
        photo_id=entry.get("photo_id"),
    )
    return PlayerOut(
        **player.model_dump(), club=club, league=league, squad=squad, photo_url=photo_path(entry)
    )


def _age(born: datetime.date | None, squad: SquadName) -> int:
    if born is None:
        return DEFAULT_AGE[squad]
    birthday = (SEASON_START.month, SEASON_START.day) < (born.month, born.day)
    return SEASON_START.year - born.year - birthday


def _detail(club: str, name: str) -> PlayerDetail:
    entry = _club(club)
    squad, _, found = _find(_roster(club), name)
    out = _player_out(club, entry.league, squad, found)
    level = real_player_level(
        entry.club.level,
        out.international,
        _age(out.born, squad),
        youth=squad == "youths",
        academy_level=1 + round(entry.club.wealth * 2),
    )
    return PlayerDetail(**out.model_dump(), typical=typical_attributes(out.position, level))


def _club(name: str) -> catalog.ClubEntry:
    entry = catalog.club_entries().get(name)
    if entry is None:
        raise HTTPException(status_code=404, detail="Club introuvable")
    return entry


def _roster(club: str) -> dict:
    """Copie de l'effectif du club, à modifier puis enregistrer (`_save`)."""
    raw = catalog.rosters().get(club) or {}
    return {squad: [dict(e) for e in raw.get(squad, [])] for squad in ("pros", "youths")}


def _find(roster: dict, name: str) -> tuple[SquadName, int, dict]:
    for squad in ("pros", "youths"):
        for i, entry in enumerate(roster[squad]):
            if entry["name"] == name:
                return squad, i, entry
    raise HTTPException(status_code=404, detail="Joueur introuvable")


def _check_free(roster: dict, name: str, squad: SquadName) -> None:
    """La place pour un joueur de ce nom dans ce groupe (400 sinon)."""
    if any(e["name"].lower() == name.lower() for e in roster["pros"] + roster["youths"]):
        raise HTTPException(status_code=400, detail="Ce club a déjà un joueur de ce nom")
    if len(roster[squad]) >= SQUAD_MAX[squad]:
        raise HTTPException(status_code=400, detail=f"Ce groupe a déjà {SQUAD_MAX[squad]} joueurs")


def _save(club: str, roster: dict, by: str) -> None:
    catalog.save_club(club, by, roster={"source": "backoffice", **roster})


@router.get("", response_model=list[PlayerOut])
def list_players(_: AdminDep) -> list[PlayerOut]:
    """Tous les joueurs des effectifs, club par club dans l'ordre des clubs (pros puis espoirs).
    Un club sans effectif n'en a pas : le jeu invente ses joueurs."""
    rosters = catalog.rosters()
    out = []
    for name, entry in catalog.club_entries().items():
        roster = rosters.get(name) or {}
        for squad in ("pros", "youths"):
            out += [_player_out(name, entry.league, squad, e) for e in roster.get(squad, [])]
    return out


@router.post("", response_model=PlayerDetail, status_code=201)
def create_player(body: PlayerIn, user: AdminDep) -> PlayerDetail:
    """Un joueur de plus dans l'effectif du club choisi (pour les nouvelles parties)."""
    _club(body.club)
    roster = _roster(body.club)
    entry = player_entry(RosterPlayer(**body.model_dump(exclude={"club", "squad"})))
    _check_free(roster, entry["name"], body.squad)
    roster[body.squad].append(entry)
    _save(body.club, roster, user.email)
    return _detail(body.club, entry["name"])


@router.get("/{club}/{name}", response_model=PlayerDetail)
def get_player(club: ClubName, name: PlayerName, _: AdminDep) -> PlayerDetail:
    return _detail(club, name)


@router.put("/{club}/{name}", response_model=PlayerDetail)
def save_player(club: ClubName, name: PlayerName, body: PlayerIn, user: AdminDep) -> PlayerDetail:
    """Fiche, notes, groupe et club du joueur. Changer de club le retire de l'effectif de
    l'un pour l'ajouter à celui de l'autre ; sa photo envoyée le suit."""
    _club(club)
    roster = _roster(club)
    squad, index, found = _find(roster, name)
    entry = player_entry(
        RosterPlayer(**body.model_dump(exclude={"club", "squad"}), photo_id=found.get("photo_id"))
    )
    del roster[squad][index]
    if body.club == club:
        _check_free(roster, entry["name"], body.squad)
        # Dans le même groupe, il garde sa place dans la liste.
        roster[body.squad].insert(index if body.squad == squad else len(roster[body.squad]), entry)
        _save(club, roster, user.email)
    else:
        _club(body.club)
        target = _roster(body.club)
        _check_free(target, entry["name"], body.squad)
        target[body.squad].append(entry)
        _save(body.club, target, user.email)
        _save(club, roster, user.email)
    return _detail(body.club, entry["name"])


@router.delete("/{club}/{name}", status_code=204)
def delete_player(club: ClubName, name: PlayerName, user: AdminDep) -> None:
    """Le joueur quitte l'effectif (il reste dans les parties déjà commencées)."""
    _club(club)
    roster = _roster(club)
    squad, index, _ = _find(roster, name)
    del roster[squad][index]
    _save(club, roster, user.email)


@router.put("/{club}/{name}/photo", response_model=PlayerDetail)
def upload_photo(club: ClubName, name: PlayerName, body: LogoIn, user: AdminDep) -> PlayerDetail:
    _club(club)
    roster = _roster(club)
    _, _, found = _find(roster, name)
    found["photo_id"] = catalog.save_photo(*decode_image(body, "Photo"))
    _save(club, roster, user.email)
    return _detail(club, name)


@router.delete("/{club}/{name}/photo", response_model=PlayerDetail)
def delete_photo(club: ClubName, name: PlayerName, user: AdminDep) -> PlayerDetail:
    """Retire la photo envoyée : celle de Wikimedia revient, s'il en a une."""
    _club(club)
    roster = _roster(club)
    _, _, found = _find(roster, name)
    if found.pop("photo_id", None) is not None:
        _save(club, roster, user.email)
    return _detail(club, name)
