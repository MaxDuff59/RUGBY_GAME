"""Parties sauvegardées : trois emplacements par joueur, chacun avec son monde
(voir database.py).

La partie chargée se sauvegarde toute seule : chaque action est enregistrée
aussitôt dans son fichier. L'emplacement chargé est retenu sur le compte.
"""

from typing import Annotated

from fastapi import APIRouter, HTTPException, Path
from sqlalchemy import select

import accounts
from api.auth import UserDep
from api.ledger import current_season, game_date
from api.schemas import SaveOut
from data.leagues import league_config
from database import (
    SLOT_COUNT,
    OutdatedSave,
    delete_slot,
    engine_for,
    init_db,
    load_slot,
    new_slot,
    saved_at,
    session_for,
    slot_exists,
)
from models.orm import CareerRow, ClubRow

router = APIRouter(prefix="/saves", tags=["parties"])

Slot = Annotated[int, Path(ge=1, le=SLOT_COUNT)]


def _save_out(user: accounts.User, slot: int) -> SaveOut:
    if not slot_exists(user.id, slot):
        return SaveOut(slot=slot, empty=True, active=False)
    out = SaveOut(
        slot=slot, empty=False, active=slot == user.active_slot, saved_at=saved_at(user.id, slot)
    )
    try:
        init_db(engine_for(user.id, slot))
    except OutdatedSave:
        out.outdated = True
        return out
    with session_for(user.id, slot) as session:
        season = current_season(session)
        out.season_year = season.year if season else None
        out.game_date = game_date(session) if season else None
        career = session.scalars(select(CareerRow)).first()
        if career is not None:
            club = session.get(ClubRow, career.club_id)
            out.manager_name = career.manager_name
            out.club_name = club.name
            out.league_name = league_config(club.league).name
    return out


def _activate(user: accounts.User, slot: int) -> accounts.User:
    accounts.set_active_slot(user.id, slot)
    return accounts.User(id=user.id, email=user.email, active_slot=slot)


@router.get("", response_model=list[SaveOut])
def list_saves(user: UserDep) -> list[SaveOut]:
    """Les trois emplacements du joueur, vides ou non."""
    return [_save_out(user, slot) for slot in range(1, SLOT_COUNT + 1)]


@router.post("/{slot}/load", response_model=SaveOut)
def load_save(slot: Slot, user: UserDep) -> SaveOut:
    """Charge une partie : toutes les autres routes travaillent ensuite sur elle."""
    if not slot_exists(user.id, slot):
        raise HTTPException(status_code=404, detail="Cet emplacement est vide")
    try:
        load_slot(user.id, slot)
    except OutdatedSave as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    return _save_out(_activate(user, slot), slot)


@router.post("/{slot}/new", response_model=SaveOut, status_code=201)
def new_save(slot: Slot, user: UserDep) -> SaveOut:
    """Crée un monde neuf dans un emplacement libre et le charge ; la carrière se
    choisit ensuite (`POST /career`)."""
    if slot_exists(user.id, slot):
        raise HTTPException(
            status_code=409, detail="Cet emplacement est pris : supprime d'abord cette partie"
        )
    new_slot(user.id, slot)
    return _save_out(_activate(user, slot), slot)


@router.delete("/{slot}", response_model=list[SaveOut])
def delete_save(slot: Slot, user: UserDep) -> list[SaveOut]:
    """Efface une partie, définitivement."""
    delete_slot(user.id, slot)
    if user.active_slot == slot:
        accounts.set_active_slot(user.id, None)
        user = accounts.User(id=user.id, email=user.email, active_slot=None)
    return list_saves(user)
