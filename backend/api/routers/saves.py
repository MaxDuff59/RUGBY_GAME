"""Parties sauvegardées : trois emplacements, chacun avec son monde (voir database.py).

La partie chargée se sauvegarde toute seule : chaque action est enregistrée
aussitôt dans son fichier.
"""

import datetime
from typing import Annotated

from fastapi import APIRouter, HTTPException, Path
from sqlalchemy import select

from api.ledger import current_season, game_date
from api.schemas import SaveOut
from data.leagues import league_config
from database import (
    SLOT_COUNT,
    OutdatedSave,
    active_slot,
    delete_slot,
    engine_for,
    init_db,
    load_slot,
    new_slot,
    session_for,
    slot_exists,
    slot_path,
)
from models.orm import CareerRow, ClubRow

router = APIRouter(prefix="/saves", tags=["parties"])

Slot = Annotated[int, Path(ge=1, le=SLOT_COUNT)]


def _save_out(slot: int) -> SaveOut:
    if not slot_exists(slot):
        return SaveOut(slot=slot, empty=True, active=False)
    saved_at = datetime.datetime.fromtimestamp(slot_path(slot).stat().st_mtime)
    out = SaveOut(slot=slot, empty=False, active=slot == active_slot(), saved_at=saved_at)
    try:
        init_db(engine_for(slot))
    except OutdatedSave:
        out.outdated = True
        return out
    with session_for(slot) as session:
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


@router.get("", response_model=list[SaveOut])
def list_saves() -> list[SaveOut]:
    """Les trois emplacements, vides ou non."""
    return [_save_out(slot) for slot in range(1, SLOT_COUNT + 1)]


@router.post("/{slot}/load", response_model=SaveOut)
def load_save(slot: Slot) -> SaveOut:
    """Charge une partie : toutes les autres routes travaillent ensuite sur elle."""
    if not slot_exists(slot):
        raise HTTPException(status_code=404, detail="Cet emplacement est vide")
    try:
        load_slot(slot)
    except OutdatedSave as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    return _save_out(slot)


@router.post("/{slot}/new", response_model=SaveOut, status_code=201)
def new_save(slot: Slot) -> SaveOut:
    """Crée un monde neuf dans un emplacement libre et le charge ; la carrière se
    choisit ensuite (`POST /career`)."""
    if slot_exists(slot):
        raise HTTPException(
            status_code=409, detail="Cet emplacement est pris : supprime d'abord cette partie"
        )
    new_slot(slot)
    return _save_out(slot)


@router.delete("/{slot}", response_model=list[SaveOut])
def delete_save(slot: Slot) -> list[SaveOut]:
    """Efface une partie, définitivement."""
    delete_slot(slot)
    return list_saves()
