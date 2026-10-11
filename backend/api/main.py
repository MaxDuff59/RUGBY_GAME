"""Point d'entrée de l'API.

Lancement (depuis backend/) :
    uv run uvicorn api.main:app --reload
Documentation interactive : http://localhost:8000/docs

En production (`uv run uvicorn api.main:site`), le même processus sert aussi
l'interface construite (`RUGBY_STATIC_DIR`, le `dist/` de Vite) : l'API sous
`/api`, tout le reste renvoie l'interface. En développement, c'est Vite qui relaie
`/api` vers `app` (voir frontend/vite.config.js).
"""

import os
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from api import auth
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
    photos,
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


@app.get("/health", include_in_schema=False)
def health() -> dict[str, str]:
    """Pour l'hébergeur : l'API répond."""
    return {"status": "ok"}


app.include_router(auth.router)
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
app.include_router(photos.router)


def make_site(api: FastAPI, static_dir: Path) -> FastAPI:
    """L'application complète : l'API sous /api, l'interface construite partout ailleurs
    (toute adresse inconnue renvoie index.html : c'est le routeur du front qui décide)."""
    site = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    site.mount("/api", api)
    assets = static_dir / "assets"
    if assets.is_dir():
        site.mount("/assets", StaticFiles(directory=assets), name="assets")
    index = static_dir / "index.html"

    @site.get("/{path:path}", include_in_schema=False)
    def page(path: str) -> FileResponse:
        candidate = (static_dir / path).resolve()
        if path and candidate.is_file() and static_dir.resolve() in candidate.parents:
            return FileResponse(candidate)
        return FileResponse(index, headers={"Cache-Control": "no-cache"})

    return site


_static_dir = os.environ.get("RUGBY_STATIC_DIR")
site = make_site(app, Path(_static_dir)) if _static_dir and Path(_static_dir).is_dir() else app
