"""Point d'entrée de l'API.

Lancement (depuis backend/) :
    uv run uvicorn api.main:app --reload
Documentation interactive : http://localhost:8000/docs
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from api.routers import clubs, matches
from database import SessionLocal, init_db, seed_if_empty


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    # Au démarrage : tables créées et clubs générés si la base est neuve.
    init_db()
    with SessionLocal() as session:
        seed_if_empty(session)
    yield


app = FastAPI(title="Rugby Manager API", version="0.1.0", lifespan=lifespan)
app.include_router(clubs.router)
app.include_router(matches.router)
