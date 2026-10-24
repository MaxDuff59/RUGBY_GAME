"""Clubs et championnats retouchés depuis le backoffice.

Les vrais clubs viennent du code (data/leagues.py) et de leurs vrais effectifs
(data/rosters.json) ; le backoffice n'en garde que les retouches, dans la base des
comptes (le schéma `public` en Postgres), une ligne par club. Un champ vide reprend
la valeur du code : une mise à jour des fichiers continue d'arriver aux clubs que
personne n'a touchés.

- Niveau, budget, capacité et effectif servent à créer les mondes : ils valent pour
  les nouvelles parties, les parties commencées gardent leurs clubs.
- Couleurs et blason sont lus par l'interface (`GET /catalog/clubs`) par-dessus
  frontend/src/clubLogos.json : ils changent tout de suite, dans toutes les parties.

Le backoffice peut aussi faire changer un club de championnat, créer des clubs et des
championnats : eux aussi valent pour les nouvelles parties. Un championnat créé n'est
jamais effacé, seulement archivé : les parties qui l'utilisent doivent pouvoir retrouver
sa formule et son calendrier (`sync`, qui l'inscrit dans data/leagues.py au démarrage).
Un championnat trop petit pour sa formule (`MIN_CLUBS`) reste en dehors des nouveaux
mondes, avec ses clubs, tant qu'il n'est pas complet.

Les joueurs vivent dans les effectifs des clubs. Une photo envoyée depuis le
backoffice est rangée à part, sous son empreinte (`photo_id` du joueur), et n'est
jamais effacée : les parties commencées avec ce joueur continuent de la montrer.
"""

import dataclasses
import datetime
import hashlib
import re
import unicodedata

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Engine,
    Float,
    Integer,
    LargeBinary,
    String,
    inspect,
    select,
    text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column

import accounts
from data import leagues as league_data
from data import nations
from data.generator import UPLOADED_PHOTO_PATH, load_rosters
from data.leagues import LEAGUES, League, RealClub
from engine import europe
from engine.season import PlayoffFormat
from models.orm import LEAGUE_CODE_LENGTH

# Champs de RealClub que le backoffice peut changer (le nom reste : le jeu s'en sert de clé).
CLUB_FIELDS = ("city", "stadium", "capacity", "level", "wealth")
LOGO_TYPES = {"image/png", "image/jpeg", "image/webp"}
LOGO_MAX_BYTES = 512 * 1024
# Au-delà, la saison régulière (aller-retour, trêves comprises) ne tient plus dans l'année.
MAX_CLUBS = 16
# Codes déjà pris par les coupes (engine/europe.py).
RESERVED_CODES = {europe.CODE, europe.CHALLENGE}


def min_clubs(league: League) -> int:
    """Clubs qu'il faut au moins : les qualifiés des phases finales, et les huit clubs
    que la Coupe d'Europe prend dans les championnats qui la jouent."""
    return max(
        league.playoffs.qualifiers, europe.PER_LEAGUE if league.code in europe.LEAGUES else 0
    )


class CatalogBase(DeclarativeBase):
    pass


class ClubEditRow(CatalogBase):
    __tablename__ = "catalog_clubs"

    name: Mapped[str] = mapped_column(String(100), primary_key=True)
    city: Mapped[str | None] = mapped_column(String(100))
    stadium: Mapped[str | None] = mapped_column(String(100))
    capacity: Mapped[int | None] = mapped_column(Integer)
    level: Mapped[float | None] = mapped_column(Float)
    wealth: Mapped[float | None] = mapped_column(Float)
    # Couleurs du maillot ["#RRGGBB", ...] ; light : blason blanc, posé sur une pastille.
    colors: Mapped[list | None] = mapped_column(JSON)
    light: Mapped[bool | None] = mapped_column()
    # Effectif complet, au format de data/rosters.json ({"pros": [...], "youths": [...]}).
    roster: Mapped[dict | None] = mapped_column(JSON)
    # Championnat où le club joue s'il a changé (code de data/leagues.py ou du backoffice).
    league: Mapped[str | None] = mapped_column(String(LEAGUE_CODE_LENGTH))
    # Club créé depuis le backoffice (sinon un vrai club du code, retouché).
    created: Mapped[bool] = mapped_column(Boolean, default=False)
    # Pays d'un club créé : la nationalité de ses joueurs inventés.
    nation: Mapped[str | None] = mapped_column(String(3))
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime)
    updated_by: Mapped[str] = mapped_column(String(254))


# Colonnes ajoutées à `catalog_clubs` après sa création : (nom, définition SQL).
_ADDED_CLUB_COLUMNS = [
    ("league", f"VARCHAR({LEAGUE_CODE_LENGTH})"),
    ("created", "BOOLEAN NOT NULL DEFAULT FALSE"),
    ("nation", "VARCHAR(3)"),
]


class LeagueRow(CatalogBase):
    """Championnat créé depuis le backoffice."""

    __tablename__ = "catalog_leagues"

    code: Mapped[str] = mapped_column(String(LEAGUE_CODE_LENGTH), primary_key=True)
    name: Mapped[str] = mapped_column(String(60))
    short_name: Mapped[str] = mapped_column(String(30))
    country: Mapped[str] = mapped_column(String(60))
    # Nationalité des joueurs inventés de ses clubs créés (None : aucune).
    nation: Mapped[str | None] = mapped_column(String(3))
    playoffs: Mapped[str] = mapped_column(String(8))
    neutral_final: Mapped[bool] = mapped_column(Boolean, default=True)
    # Championnat du code dont il reprend la date de départ et les trêves.
    calendar: Mapped[str] = mapped_column(String(LEAGUE_CODE_LENGTH))
    prize_factor: Mapped[float] = mapped_column(Float, default=0.3)
    archived: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime)


class ClubLogoRow(CatalogBase):
    __tablename__ = "catalog_logos"

    name: Mapped[str] = mapped_column(String(100), primary_key=True)
    content_type: Mapped[str] = mapped_column(String(20))
    data: Mapped[bytes] = mapped_column(LargeBinary)
    # Empreinte du fichier : l'adresse change avec lui (cache du navigateur).
    digest: Mapped[str] = mapped_column(String(16))
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime)


class PlayerPhotoRow(CatalogBase):
    __tablename__ = "catalog_photos"

    digest: Mapped[str] = mapped_column(String(16), primary_key=True)
    content_type: Mapped[str] = mapped_column(String(20))
    data: Mapped[bytes] = mapped_column(LargeBinary)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime)


_ready: Engine | None = None


def _session() -> Session:
    global _ready
    engine = accounts.engine()
    if engine is not _ready:
        CatalogBase.metadata.create_all(engine)
        present = {column["name"] for column in inspect(engine).get_columns("catalog_clubs")}
        with engine.begin() as connection:
            for name, definition in _ADDED_CLUB_COLUMNS:
                if name not in present:
                    connection.execute(
                        text(f"ALTER TABLE catalog_clubs ADD COLUMN {name} {definition}")
                    )
        _ready = engine
    return Session(engine, expire_on_commit=False)


def _now() -> datetime.datetime:
    return datetime.datetime.now(datetime.UTC).replace(tzinfo=None)


BUILT_IN = {league.code for league in LEAGUES}


def real_clubs() -> dict[str, tuple[League, RealClub]]:
    """Chaque vrai club du code, par nom, avec son championnat d'origine."""
    return {club.name: (league, club) for league in LEAGUES for club in league.clubs}


def edits() -> dict[str, ClubEditRow]:
    with _session() as session:
        return {row.name: row for row in session.scalars(select(ClubEditRow))}


def league_rows() -> dict[str, LeagueRow]:
    with _session() as session:
        rows = session.scalars(select(LeagueRow).order_by(LeagueRow.created_at))
        return {row.code: row for row in rows}


def logos() -> dict[str, ClubLogoRow]:
    """Blasons envoyés, sans leurs octets (seulement de quoi faire l'adresse)."""
    with _session() as session:
        rows = session.execute(
            select(ClubLogoRow.name, ClubLogoRow.content_type, ClubLogoRow.digest)
        )
        return {
            name: ClubLogoRow(name=name, content_type=kind, digest=digest)
            for name, kind, digest in rows
        }


def logo_url(name: str, digest: str) -> str:
    """Adresse du blason dans l'API (l'interface y ajoute son préfixe /api)."""
    import urllib.parse

    return f"/catalog/logos/{urllib.parse.quote(name)}?v={digest}"


# --- Ce que lisent la création des mondes et l'interface -----------------------------------


@dataclasses.dataclass(frozen=True)
class ClubEntry:
    """Un club tel que le backoffice le voit : vrai club (retouché ou non) ou club créé."""

    club: RealClub
    league: str
    created: bool
    # Championnat d'origine d'un vrai club (None pour un club créé).
    home_league: str | None
    nation: str | None
    edit: ClubEditRow | None

    @property
    def name(self) -> str:
        return self.club.name


def edited_club(club: RealClub, edit: ClubEditRow | None) -> RealClub:
    if edit is None:
        return club
    changes = {field: getattr(edit, field) for field in CLUB_FIELDS}
    return dataclasses.replace(club, **{k: v for k, v in changes.items() if v is not None})


def _league_of_row(row: LeagueRow) -> League:
    template = league_data.LEAGUES_BY_CODE.get(
        row.calendar, league_data.league(league_data.DEFAULT_LEAGUE)
    )
    return League(
        code=row.code,
        name=row.name,
        short_name=row.short_name,
        country=row.country,
        playoffs=PlayoffFormat(row.playoffs),
        neutral_final=row.neutral_final,
        start=template.start,
        breaks=template.breaks,
        prize_factor=row.prize_factor,
    )


def all_leagues(rows: dict[str, LeagueRow] | None = None) -> list[tuple[League, LeagueRow | None]]:
    """Les championnats du code puis ceux du backoffice (archivés compris), sans clubs."""
    rows = league_rows() if rows is None else rows
    return [(dataclasses.replace(league, clubs=[]), None) for league in LEAGUES] + [
        (_league_of_row(row), row) for row in rows.values()
    ]


def club_entries(found: dict[str, ClubEditRow] | None = None) -> dict[str, ClubEntry]:
    """Tous les clubs par nom : les vrais dans l'ordre du code, puis les créés par nom."""
    found = edits() if found is None else found
    entries = {}
    for league in LEAGUES:
        for club in league.clubs:
            edit = found.get(club.name)
            entries[club.name] = ClubEntry(
                club=edited_club(club, edit),
                league=(edit.league if edit and edit.league else league.code),
                created=False,
                home_league=league.code,
                nation=nations.home_nation(club.name),
                edit=edit,
            )
    for name in sorted(n for n, e in found.items() if e.created):
        edit = found[name]
        club = RealClub(name, edit.city, edit.stadium, edit.capacity, edit.level, edit.wealth)
        entries[name] = ClubEntry(club, edit.league, True, None, edit.nation, edit)
    return entries


def leagues() -> list[League]:
    """Les championnats d'un nouveau monde, avec leurs clubs (retouchés, déplacés, créés) :
    ceux du code et ceux du backoffice non archivés, s'ils ont assez de clubs."""
    sync()
    rows = league_rows()
    by_league: dict[str, list[RealClub]] = {}
    for entry in club_entries().values():
        by_league.setdefault(entry.league, []).append(entry.club)
    ready = []
    for league, row in all_leagues(rows):
        clubs = by_league.get(league.code, [])
        if (row is None or not row.archived) and min_clubs(league) <= len(clubs) <= MAX_CLUBS:
            ready.append(dataclasses.replace(league, clubs=clubs))
    return ready


_synced = False


def ensure_synced() -> None:
    """`sync` une fois par processus, avant d'ouvrir une partie (api/deps.py)."""
    if not _synced:
        sync()


def sync() -> None:
    """Inscrit les championnats et les clubs créés là où le jeu les cherche : formule et
    calendrier (data/leagues.py), pays des clubs (data/nations.py)."""
    global _synced
    rows = league_rows()
    for code, row in rows.items():
        if code not in BUILT_IN:
            league_data.LEAGUES_BY_CODE[code] = _league_of_row(row)
    for name, edit in edits().items():
        if edit.created:
            nation = edit.nation or (rows[edit.league].nation if edit.league in rows else None)
            if nation:
                nations.CLUB_NATION[name] = nation
            else:
                nations.CLUB_NATION.pop(name, None)
    _synced = True


def rosters() -> dict:
    """Les vrais effectifs (data/rosters.json), remplacés par ceux du backoffice."""
    known = load_rosters()
    for name, edit in edits().items():
        if edit.roster is not None:
            known[name] = edit.roster
    return known


def appearance() -> dict[str, dict]:
    """Couleurs et blasons retouchés, par nom de club (seulement ce qui change)."""
    found: dict[str, dict] = {}
    for name, edit in edits().items():
        entry = {}
        if edit.colors:
            entry["colors"] = edit.colors
        if edit.light is not None:
            entry["light"] = edit.light
        if entry:
            found[name] = entry
    for name, logo in logos().items():
        found.setdefault(name, {})["logo"] = logo_url(name, logo.digest)
    return found


# --- Écritures du backoffice ---------------------------------------------------------------


def save_club(name: str, by: str, **values) -> None:
    """Enregistre les retouches d'un club : pour un vrai club, une valeur égale à celle
    du code (ou None) efface la retouche. Seules les clés données changent."""
    real = real_clubs().get(name)
    with _session() as session:
        row = session.get(ClubEditRow, name) or ClubEditRow(name=name, created=False)
        for field, value in values.items():
            if real is not None and field in CLUB_FIELDS and value == getattr(real[1], field):
                value = None
            if real is not None and field == "league" and value == real[0].code:
                value = None
            setattr(row, field, value)
        row.updated_at, row.updated_by = _now(), by
        session.merge(row)
        session.commit()
        _drop_if_empty(session, name)
    sync()


def _drop_if_empty(session: Session, name: str) -> None:
    row = session.get(ClubEditRow, name)
    fields = (*CLUB_FIELDS, "colors", "light", "roster", "league")
    if row is not None and not row.created and all(getattr(row, f) is None for f in fields):
        session.delete(row)
        session.commit()


def create_club(club: RealClub, league: str, nation: str | None, by: str, **values) -> None:
    with _session() as session:
        session.add(
            ClubEditRow(
                name=club.name,
                city=club.city,
                stadium=club.stadium,
                capacity=club.capacity,
                level=club.level,
                wealth=club.wealth,
                league=league,
                nation=nation,
                created=True,
                updated_at=_now(),
                updated_by=by,
                **values,
            )
        )
        session.commit()
    sync()


def delete_club(name: str) -> None:
    """Efface un club créé (il reste dans les parties déjà commencées)."""
    reset_club(name)
    nations.CLUB_NATION.pop(name, None)


# --- Championnats ----------------------------------------------------------------------------


def new_code(name: str) -> str:
    """Code d'un nouveau championnat, tiré de son nom (« Fédérale 1 » -> « federale1 »)."""
    plain = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode().lower()
    base = re.sub(r"[^a-z0-9]+", "", plain)[: LEAGUE_CODE_LENGTH - 2] or "ligue"
    taken = BUILT_IN | RESERVED_CODES | set(league_rows())
    code, n = base, 2
    while code in taken:
        code, n = f"{base}{n}", n + 1
    return code


def save_league(code: str | None, **values) -> str:
    """Crée (code None) ou modifie un championnat du backoffice ; renvoie son code."""
    with _session() as session:
        if code is None:
            code = new_code(values["name"])
            row = LeagueRow(code=code, created_at=_now(), archived=False)
        else:
            row = session.get(LeagueRow, code)
        for field, value in values.items():
            setattr(row, field, value)
        session.merge(row)
        session.commit()
    sync()
    return code


def reset_club(name: str) -> None:
    """Le club redevient celui du code : retouches et blason envoyé effacés."""
    with _session() as session:
        for model in (ClubEditRow, ClubLogoRow):
            row = session.get(model, name)
            if row is not None:
                session.delete(row)
        session.commit()


def save_logo(name: str, content_type: str, data: bytes) -> str:
    """Remplace le blason d'un club ; renvoie sa nouvelle adresse."""
    digest = hashlib.sha256(data).hexdigest()[:16]
    with _session() as session:
        session.merge(
            ClubLogoRow(
                name=name, content_type=content_type, data=data, digest=digest, updated_at=_now()
            )
        )
        session.commit()
    return logo_url(name, digest)


def delete_logo(name: str) -> None:
    with _session() as session:
        row = session.get(ClubLogoRow, name)
        if row is not None:
            session.delete(row)
            session.commit()


def logo(name: str) -> ClubLogoRow | None:
    with _session() as session:
        return session.get(ClubLogoRow, name)


def save_photo(content_type: str, data: bytes) -> str:
    """Range la photo d'un joueur ; renvoie son empreinte (le `photo_id` du joueur)."""
    digest = hashlib.sha256(data).hexdigest()[:16]
    with _session() as session:
        if session.get(PlayerPhotoRow, digest) is None:
            session.add(
                PlayerPhotoRow(
                    digest=digest, content_type=content_type, data=data, created_at=_now()
                )
            )
            session.commit()
    return digest


def photo(digest: str) -> PlayerPhotoRow | None:
    with _session() as session:
        return session.get(PlayerPhotoRow, digest)


def photo_url(digest: str) -> str:
    """Adresse de la photo dans l'API (la même que celle des parties, data/generator.py)."""
    return UPLOADED_PHOTO_PATH.format(digest)


def sniff_image(data: bytes) -> str | None:
    """Le type d'une image d'après ses premiers octets (PNG, JPEG, WebP), None sinon.
    Pas de SVG : il peut porter du script, servi depuis l'adresse du jeu."""
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return None
