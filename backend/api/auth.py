"""Connexion des joueurs : routes /auth et dépendance `current_user`.

Le navigateur reçoit un cookie de session (HttpOnly) à l'inscription ou à la
connexion ; chaque route du jeu retrouve le compte par ce cookie. Le cookie est
marqué Secure quand `RUGBY_COOKIE_SECURE=1` (en production, derrière HTTPS).

Pour jouer sans compte, `POST /auth/guest` crée un invité (accounts.py) et lui ouvre
une session de la même façon ; s'il s'inscrit ensuite, son compte devient un vrai
compte et garde sa partie.
"""

import os
import threading
import time
from collections import defaultdict, deque
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field

import accounts
from accounts import AccountError, User
from api import plans

COOKIE = "rugby_session"
COOKIE_MAX_AGE = accounts.SESSION_DAYS * 24 * 3600
# Tentatives de connexion par adresse IP et par fenêtre : au-delà, on fait attendre.
LOGIN_ATTEMPTS, LOGIN_WINDOW = 10, 60.0

router = APIRouter(prefix="/auth", tags=["comptes"])


def _secure_cookies() -> bool:
    return os.environ.get("RUGBY_COOKIE_SECURE", "0") == "1"


def current_user(request: Request) -> User:
    """Le compte connecté (401 sinon)."""
    user = accounts.user_for_token(request.cookies.get(COOKIE))
    if user is None:
        raise HTTPException(status_code=401, detail="Connecte-toi pour jouer")
    return user


UserDep = Annotated[User, Depends(current_user)]


class Credentials(BaseModel):
    email: str = Field(max_length=254)
    password: str = Field(max_length=200)


class UserOut(BaseModel):
    id: int
    email: str
    active_slot: int | None
    # Formule (accounts.py) : jeu complet, ou saisons qu'il reste au compte gratuit.
    premium: bool
    seasons_played: int
    seasons_left: int | None
    free_seasons: int = accounts.FREE_SEASONS
    free_saves: int = accounts.FREE_SAVES
    # Formule active (api/plans.py) ; en pause, tout est gratuit et l'interface n'en parle pas.
    paywall: bool
    # Invité : pas d'adresse à montrer, une seule partie, perdue s'il ne revient pas.
    guest: bool = False


def user_out(user: User) -> UserOut:
    return UserOut(
        id=user.id,
        email="" if user.guest else user.email,
        active_slot=user.active_slot,
        premium=user.premium,
        seasons_played=user.seasons_played,
        seasons_left=user.seasons_left,
        paywall=plans.PAYWALL,
        guest=user.guest,
    )


def _start_session(response: Response, user: User) -> UserOut:
    response.set_cookie(
        COOKIE,
        accounts.open_session(user.id),
        max_age=accounts.GUEST_DAYS * 24 * 3600 if user.guest else COOKIE_MAX_AGE,
        httponly=True,
        samesite="lax",
        secure=_secure_cookies(),
        path="/",
    )
    return user_out(user)


# --- Frein sur les connexions (par IP, en mémoire : suffit pour une instance) -----------

_attempts: dict[str, deque[float]] = defaultdict(deque)
_attempts_lock = threading.Lock()


def _client_ip(request: Request) -> str:
    return request.client.host if request.client else "?"


def _throttle(request: Request) -> None:
    now = time.monotonic()
    with _attempts_lock:
        recent = _attempts[_client_ip(request)]
        while recent and now - recent[0] > LOGIN_WINDOW:
            recent.popleft()
        if len(recent) >= LOGIN_ATTEMPTS:
            raise HTTPException(
                status_code=429, detail="Trop de tentatives : réessaie dans une minute"
            )
        recent.append(now)


# --- Routes ---------------------------------------------------------------------------


@router.post("/register", response_model=UserOut, status_code=201)
def register(credentials: Credentials, request: Request, response: Response) -> UserOut:
    """Crée un compte et ouvre la session. Depuis une session d'invité, c'est son compte
    qui devient un vrai compte, avec sa partie."""
    _throttle(request)
    current = accounts.user_for_token(request.cookies.get(COOKIE))
    try:
        user = accounts.register(
            credentials.email,
            credentials.password,
            guest_id=current.id if current is not None and current.guest else None,
        )
    except AccountError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    return _start_session(response, user)


@router.post("/guest", response_model=UserOut, status_code=201)
def guest(request: Request, response: Response) -> UserOut:
    """Joue sans compte : crée un invité et ouvre sa session. Les invités partis depuis
    trop longtemps sont effacés au passage."""
    _throttle(request)
    accounts.purge_guests()
    return _start_session(response, accounts.register_guest())


@router.post("/login", response_model=UserOut)
def login(credentials: Credentials, request: Request, response: Response) -> UserOut:
    _throttle(request)
    try:
        user = accounts.authenticate(credentials.email, credentials.password)
    except AccountError as error:
        raise HTTPException(status_code=401, detail=str(error)) from error
    return _start_session(response, user)


@router.post("/logout", status_code=204)
def logout(request: Request, response: Response) -> Response:
    """Ferme la session. Un invité n'a pas d'autre moyen de revenir : sa partie est
    effacée avec lui."""
    current = accounts.user_for_token(request.cookies.get(COOKIE))
    accounts.close_session(request.cookies.get(COOKIE))
    if current is not None and current.guest:
        accounts.purge_guests()
    response.delete_cookie(COOKIE, path="/")
    response.status_code = 204
    return response


@router.get("/me", response_model=UserOut)
def me(user: UserDep) -> UserOut:
    """Le compte connecté (401 sinon : l'interface montre alors l'écran de connexion)."""
    return user_out(user)
