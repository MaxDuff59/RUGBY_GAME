"""Couleurs et blasons des clubs retouchés depuis le backoffice (voir catalog.py).

Lus par l'interface au démarrage, par-dessus frontend/src/clubLogos.json ; sans
compte, comme les blasons d'origine. Les photos de joueurs envoyées depuis le
backoffice aussi, comme celles de Wikimedia (api/routers/photos.py).
"""

from fastapi import APIRouter, HTTPException, Response

import catalog

router = APIRouter(prefix="/catalog", tags=["catalogue"])

ONE_YEAR = 365 * 24 * 3600


@router.get("/clubs")
def club_appearance(response: Response) -> dict[str, dict]:
    """{nom du club: {colors?, light?, logo?}}, seulement pour les clubs retouchés."""
    response.headers["Cache-Control"] = "no-cache"
    return catalog.appearance()


@router.get("/logos/{name}")
def club_logo(name: str) -> Response:
    """Blason envoyé depuis le backoffice (son adresse change avec lui : cache long)."""
    found = catalog.logo(name)
    if found is None:
        raise HTTPException(status_code=404, detail="Pas de blason envoyé pour ce club")
    return Response(
        found.data,
        media_type=found.content_type,
        headers={
            "Cache-Control": f"public, max-age={ONE_YEAR}, immutable",
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.get("/photos/{digest}")
def player_photo(digest: str) -> Response:
    """Photo de joueur envoyée depuis le backoffice (rangée sous son empreinte : cache long)."""
    found = catalog.photo(digest)
    if found is None:
        raise HTTPException(status_code=404, detail="Photo introuvable")
    return Response(
        found.data,
        media_type=found.content_type,
        headers={
            "Cache-Control": f"public, max-age={ONE_YEAR}, immutable",
            "X-Content-Type-Options": "nosniff",
        },
    )
