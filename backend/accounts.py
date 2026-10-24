"""Comptes des joueurs : inscription, connexion, sessions.

Les comptes vivent dans leur propre base (`RUGBY_USERS_DB_URL`, par défaut
`users.db` dans le dossier des parties), à part des mondes de jeu : une partie
reste un fichier par emplacement et par joueur (voir database.py).

Une session est un jeton aléatoire remis au navigateur (cookie) ; on n'en garde
ici que l'empreinte, comme pour les mots de passe (scrypt, bibliothèque standard).

Un compte gratuit garde une seule partie et joue deux saisons en tout. Les saisons
se comptent sur le compte, pas dans la partie, dès qu'elles commencent : supprimer
une carrière ne rend pas les saisons jouées. Le compte complet (payé une fois, voir
api/billing.py) n'a plus de limite.
"""

import datetime
import hashlib
import hmac
import os
import re
import secrets
from dataclasses import dataclass

from sqlalchemy import (
    DateTime,
    Engine,
    ForeignKey,
    Integer,
    String,
    create_engine,
    inspect,
    select,
    text,
    update,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker

SESSION_DAYS = 30
PASSWORD_MIN_LENGTH = 8
_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

# Compte gratuit : une partie à la fois, deux saisons en tout.
FREE_SAVES = 1
FREE_SEASONS = 2

# scrypt : paramètres recommandés (16 Mio de mémoire par calcul).
_SCRYPT_N, _SCRYPT_R, _SCRYPT_P = 2**14, 8, 1


class AccountsBase(DeclarativeBase):
    pass


class UserRow(AccountsBase):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(254), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(300))
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime)
    # Emplacement de la partie chargée (None : passer par l'écran des parties).
    active_slot: Mapped[int | None] = mapped_column(Integer)
    # Saisons commencées par ce compte, toutes parties confondues (supprimées comprises).
    seasons_played: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    # Compte complet : date du paiement, et sa référence chez Stripe.
    premium_at: Mapped[datetime.datetime | None] = mapped_column(DateTime)
    payment_ref: Mapped[str | None] = mapped_column(String(255))


class SessionRow(AccountsBase):
    __tablename__ = "sessions"

    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime)
    expires_at: Mapped[datetime.datetime] = mapped_column(DateTime)


@dataclass(frozen=True)
class User:
    id: int
    email: str
    active_slot: int | None
    premium: bool = False
    seasons_played: int = 0

    @property
    def seasons_left(self) -> int | None:
        """Saisons qu'il reste à commencer (None : sans limite)."""
        return None if self.premium else max(0, FREE_SEASONS - self.seasons_played)


class AccountError(Exception):
    """Inscription ou connexion refusée, avec le message à montrer au joueur."""


_engine: Engine | None = None


def engine() -> Engine:
    """Connexion à la base des comptes (créée au premier appel, tables comprises) :
    le serveur Postgres du jeu s'il y en a un, sinon `RUGBY_USERS_DB_URL`, sinon un
    fichier SQLite à côté des parties."""
    global _engine
    if _engine is None:
        import database  # import tardif : le dossier et l'URL sont surchargés par les tests

        url = os.environ.get("RUGBY_USERS_DB_URL")
        if database.uses_postgres() and not url:
            _engine = database.shared_engine()
        elif url and not url.startswith("sqlite"):
            _engine = create_engine(url, pool_pre_ping=True)
        else:
            database.SAVES_DIR.mkdir(parents=True, exist_ok=True)
            url = url or f"sqlite:///{database.SAVES_DIR / 'users.db'}"
            _engine = create_engine(url, connect_args={"check_same_thread": False})
        AccountsBase.metadata.create_all(_engine)
        _add_columns(_engine)
    return _engine


# Colonnes ajoutées après coup : les comptes déjà créés les reçoivent au démarrage.
_NEW_COLUMNS = {
    "seasons_played": "INTEGER NOT NULL DEFAULT 0",
    "premium_at": "TIMESTAMP",
    "payment_ref": "VARCHAR(255)",
}


def _add_columns(engine: Engine) -> None:
    existing = {column["name"] for column in inspect(engine).get_columns("users")}
    with engine.begin() as connection:
        for name, definition in _NEW_COLUMNS.items():
            if name not in existing:
                connection.execute(text(f"ALTER TABLE users ADD COLUMN {name} {definition}"))


def reset() -> None:
    """Oublie la connexion (tests : changer de base entre deux cas)."""
    global _engine
    import database

    if _engine is not None and _engine is not database._shared:
        _engine.dispose()
    _engine = None


def _session() -> Session:
    return sessionmaker(bind=engine(), expire_on_commit=False)()


def _now() -> datetime.datetime:
    return datetime.datetime.now(datetime.UTC).replace(tzinfo=None)


# --- Mots de passe ---------------------------------------------------------------------


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(
        password.encode(), salt=salt, n=_SCRYPT_N, r=_SCRYPT_R, p=_SCRYPT_P, dklen=32
    )
    return f"scrypt${salt.hex()}${digest.hex()}"


def check_password(password: str, stored: str) -> bool:
    try:
        _, salt_hex, digest_hex = stored.split("$")
        salt, expected = bytes.fromhex(salt_hex), bytes.fromhex(digest_hex)
    except ValueError:
        return False
    digest = hashlib.scrypt(
        password.encode(), salt=salt, n=_SCRYPT_N, r=_SCRYPT_R, p=_SCRYPT_P, dklen=32
    )
    return hmac.compare_digest(digest, expected)


def normalize_email(email: str) -> str:
    email = email.strip().lower()
    if len(email) > 254 or not _EMAIL.match(email):
        raise AccountError("Adresse e-mail invalide")
    return email


# --- Comptes ---------------------------------------------------------------------------


def _user(row: UserRow) -> User:
    return User(
        id=row.id,
        email=row.email,
        active_slot=row.active_slot,
        premium=row.premium_at is not None,
        seasons_played=row.seasons_played or 0,
    )


def register(email: str, password: str) -> User:
    """Crée un compte (AccountError si l'adresse est prise ou le mot de passe trop court)."""
    email = normalize_email(email)
    if len(password) < PASSWORD_MIN_LENGTH:
        raise AccountError(f"Mot de passe trop court ({PASSWORD_MIN_LENGTH} caractères minimum)")
    with _session() as session:
        if session.scalars(select(UserRow).where(UserRow.email == email)).first():
            raise AccountError("Un compte existe déjà avec cette adresse")
        row = UserRow(email=email, password_hash=hash_password(password), created_at=_now())
        session.add(row)
        session.commit()
        return _user(row)


def authenticate(email: str, password: str) -> User:
    """Le compte si l'adresse et le mot de passe concordent, AccountError sinon
    (même message dans les deux cas : on ne révèle pas quelles adresses existent)."""
    try:
        email = normalize_email(email)
    except AccountError:
        raise AccountError("Adresse ou mot de passe incorrect") from None
    with _session() as session:
        row = session.scalars(select(UserRow).where(UserRow.email == email)).first()
    if row is None or not check_password(password, row.password_hash):
        raise AccountError("Adresse ou mot de passe incorrect")
    return _user(row)


def set_active_slot(user_id: int, slot: int | None) -> None:
    with _session() as session:
        row = session.get(UserRow, user_id)
        if row is not None:
            row.active_slot = slot
            session.commit()


def get(user_id: int) -> User | None:
    with _session() as session:
        row = session.get(UserRow, user_id)
    return _user(row) if row is not None else None


def find(email: str) -> User | None:
    email = normalize_email(email)
    with _session() as session:
        row = session.scalars(select(UserRow).where(UserRow.email == email)).first()
    return _user(row) if row is not None else None


# --- Formule : gratuit ou complet -------------------------------------------------------


def count_season(user_id: int) -> None:
    """Une saison de plus commencée par le compte (en une seule requête : deux
    saisons lancées en même temps en comptent bien deux)."""
    with _session() as session:
        session.execute(
            update(UserRow)
            .where(UserRow.id == user_id)
            .values(seasons_played=UserRow.seasons_played + 1)
        )
        session.commit()


def grant_premium(user_id: int, payment_ref: str | None = None) -> User | None:
    """Passe le compte en version complète (sans effet s'il l'est déjà : Stripe peut
    prévenir deux fois du même paiement)."""
    with _session() as session:
        row = session.get(UserRow, user_id)
        if row is None:
            return None
        if row.premium_at is None:
            row.premium_at, row.payment_ref = _now(), payment_ref
            session.commit()
        return _user(row)


def revoke_premium(user_id: int) -> User | None:
    """Repasse le compte en gratuit (remboursement) : ses saisons jouées restent comptées."""
    with _session() as session:
        row = session.get(UserRow, user_id)
        if row is None:
            return None
        row.premium_at = row.payment_ref = None
        session.commit()
        return _user(row)


# --- Sessions --------------------------------------------------------------------------


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def open_session(user_id: int) -> str:
    """Ouvre une session et renvoie son jeton (à remettre au navigateur)."""
    token = secrets.token_urlsafe(32)
    now = _now()
    with _session() as session:
        session.add(
            SessionRow(
                token_hash=_token_hash(token),
                user_id=user_id,
                created_at=now,
                expires_at=now + datetime.timedelta(days=SESSION_DAYS),
            )
        )
        session.commit()
    return token


def user_for_token(token: str | None) -> User | None:
    """Le compte derrière un jeton de session, None s'il est inconnu ou expiré."""
    if not token:
        return None
    with _session() as session:
        found = session.get(SessionRow, _token_hash(token))
        if found is None:
            return None
        if found.expires_at < _now():
            session.delete(found)
            session.commit()
            return None
        row = session.get(UserRow, found.user_id)
    return _user(row) if row is not None else None


def close_session(token: str | None) -> None:
    if not token:
        return
    with _session() as session:
        found = session.get(SessionRow, _token_hash(token))
        if found is not None:
            session.delete(found)
            session.commit()
