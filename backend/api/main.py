"""Point d'entrée de l'API.

Lancement (depuis backend/) :
    uv run uvicorn api.main:app --reload
Documentation interactive : http://localhost:8000/docs
"""

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from api.routers import (
    academy,
    affairs,
    career,
    clubs,
    contracts,
    facilities,
    finances,
    leagues,
    live,
    matches,
    medical,
    players,
    saves,
    seasons,
    staff,
    transfers,
)
from database import NoSaveLoaded, OutdatedSave

app = FastAPI(title="Rugby Manager API", version="0.1.0")


@app.exception_handler(NoSaveLoaded)
def no_save_loaded(request: Request, error: NoSaveLoaded) -> JSONResponse:
    # Les parties se choisissent (ou se créent) par les routes /saves.
    return JSONResponse(status_code=409, content={"detail": "Aucune partie chargée"})


@app.exception_handler(OutdatedSave)
def outdated_save(request: Request, error: OutdatedSave) -> JSONResponse:
    return JSONResponse(status_code=409, content={"detail": str(error)})


app.include_router(saves.router)
app.include_router(clubs.router)
app.include_router(leagues.router)
app.include_router(matches.router)
app.include_router(career.router)
app.include_router(seasons.router)
app.include_router(finances.router)
app.include_router(staff.router)
app.include_router(facilities.router)
app.include_router(transfers.router)
app.include_router(medical.router)
app.include_router(academy.router)
app.include_router(players.router)
app.include_router(affairs.router)
app.include_router(contracts.router)
app.include_router(live.router)
