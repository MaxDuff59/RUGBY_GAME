"""Photos des vrais joueurs, servies depuis notre propre copie.

Les joueurs gardent le nom du fichier sur Wikimedia Commons (`/photos/<nom>`).
À la première demande, l'API va chercher la vignette chez Wikimedia, avec un
User-Agent identifiable comme ils le demandent, puis la garde sur disque
(`<dossier des parties>/photos/`) : Wikimedia n'est plus appelé pour cette photo,
et le jeu ne dépend plus d'eux en direct. Une photo introuvable répond 404 : le
front montre alors la silhouette.
"""

import hashlib
import mimetypes
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

import database

router = APIRouter(prefix="/photos", tags=["photos"])

SOURCE = "https://commons.wikimedia.org/wiki/Special:FilePath/{}?width=240"
USER_AGENT = "RugbyManager/0.1 (jeu de gestion de rugby ; photos des joueurs)"
FETCH_TIMEOUT = 10.0
MAX_BYTES = 2_000_000
# Après un échec, on ne retente pas avant ce délai (secondes).
RETRY_AFTER = 3600.0
ONE_YEAR = 365 * 24 * 3600

_failed: dict[str, float] = {}
_locks: dict[str, threading.Lock] = {}
_locks_guard = threading.Lock()


def cache_dir() -> Path:
    return database.SAVES_DIR / "photos"


def _cache_path(name: str) -> Path:
    suffix = Path(name).suffix.lower()
    if suffix not in {".jpg", ".jpeg", ".png", ".webp", ".gif"}:
        suffix = ".jpg"
    return cache_dir() / (hashlib.sha256(name.encode()).hexdigest()[:32] + suffix)


def _lock_for(name: str) -> threading.Lock:
    with _locks_guard:
        return _locks.setdefault(name, threading.Lock())


def fetch(name: str) -> bytes | None:
    """La vignette chez Wikimedia, None si elle est introuvable ou si Wikimedia ne répond pas."""
    url = SOURCE.format(urllib.parse.quote(name))
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=FETCH_TIMEOUT) as response:  # noqa: S310
            if not response.headers.get("Content-Type", "").startswith("image/"):
                return None
            data = response.read(MAX_BYTES + 1)
    except (urllib.error.URLError, TimeoutError, OSError):
        return None
    return data if 0 < len(data) <= MAX_BYTES else None


@router.get("/{name}")
def photo(name: str) -> FileResponse:
    if (
        "/" in name
        or "\\" in name
        or name in {".", ".."}
        or not re.fullmatch(r"[^\x00-\x1f]{1,300}", name)
    ):
        raise HTTPException(status_code=404, detail="Photo introuvable")
    path = _cache_path(name)
    headers = {"Cache-Control": f"public, max-age={ONE_YEAR}, immutable"}
    media_type = mimetypes.guess_type(path.name)[0] or "image/jpeg"
    if path.exists():
        return FileResponse(path, media_type=media_type, headers=headers)

    failed_at = _failed.get(name)
    if failed_at is not None and time.monotonic() - failed_at < RETRY_AFTER:
        raise HTTPException(status_code=404, detail="Photo introuvable")

    with _lock_for(name):
        if not path.exists():  # un autre appel a pu la récupérer pendant l'attente
            data = fetch(name)
            if data is None:
                _failed[name] = time.monotonic()
                raise HTTPException(status_code=404, detail="Photo introuvable")
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_suffix(path.suffix + ".part")
            tmp.write_bytes(data)
            tmp.replace(path)
    return FileResponse(path, media_type=media_type, headers=headers)
