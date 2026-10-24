"""Backoffice : les comptes (formule, parties, saisons) et les vrais clubs (catalog.py).
Les joueurs, un par un, ont leurs routes à part (admin_players.py).

Ouvert au seul compte `ADMIN_EMAIL` : les autres comptes reçoivent un 403, comme un
visiteur sans session reçoit un 401.
"""

import base64
import binascii
import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Path
from pydantic import BaseModel, Field
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

import accounts
import catalog
import database
from api.auth import UserDep
from api.routers.saves import _save_out
from api.schemas import SaveOut
from data.leagues import PROMOTION, RealClub
from data.nations import NATIONS
from engine import europe
from engine.season import PlayoffFormat
from models import ATTRIBUTE_MAX, ATTRIBUTE_MIN, Position
from models.orm import LEAGUE_CODE_LENGTH

router = APIRouter(prefix="/backoffice", tags=["backoffice"])

# Taille des effectifs qu'on peut saisir : le jeu garde 38 pros et 30 espoirs au plus, les
# autres partent chez les espoirs ou les agents libres (data/generator.py).
ROSTER_MAX_PROS, ROSTER_MAX_YOUTHS = 80, 100
# Le seul compte qui ouvre le backoffice.
ADMIN_EMAIL = "maxence.duffuler@epfedu.fr"
# Préfixe de `payment_ref` pour un compte complet accordé depuis le backoffice.
GIFT_REF = "backoffice"


def admin_user(user: UserDep) -> accounts.User:
    if user.email != ADMIN_EMAIL:
        raise HTTPException(status_code=403, detail="Réservé à l'administration du jeu")
    return user


AdminDep = Annotated[accounts.User, Depends(admin_user)]
ClubName = Annotated[str, Path(max_length=100)]


def _now() -> datetime.datetime:
    return datetime.datetime.now(datetime.UTC).replace(tzinfo=None)


def _accounts_session() -> Session:
    return Session(accounts.engine())


# --- Comptes -------------------------------------------------------------------------------


class AccountOut(BaseModel):
    id: int
    email: str
    created_at: datetime.datetime
    last_login_at: datetime.datetime | None
    premium: bool
    premium_at: datetime.datetime | None
    # « stripe » : payé ; « offert » : accordé depuis le backoffice ; None : gratuit.
    premium_source: Literal["stripe", "offert"] | None
    payment_ref: str | None
    seasons_played: int
    seasons_left: int | None
    saves: int
    admin: bool


class AccountDetail(AccountOut):
    slots: list[SaveOut]


class OverviewOut(BaseModel):
    accounts: int
    premium: int
    premium_paid: int
    premium_offered: int
    new_7_days: int
    new_30_days: int
    # Comptes gratuits qui ont joué toutes leurs saisons : ceux à qui proposer la formule.
    free_exhausted: int
    active_sessions: int
    saves: int
    free_seasons: int
    clubs: int
    clubs_edited: int
    logos: int


def _save_counts() -> dict[int, int]:
    """Parties existantes, par compte."""
    if database.uses_postgres():
        with database.shared_engine().connect() as connection:
            rows = connection.execute(text("SELECT user_id, COUNT(*) FROM saves GROUP BY user_id"))
            return {user_id: count for user_id, count in rows}
    counts: dict[int, int] = {}
    for path in database.SAVES_DIR.glob("u*/partie-*.db"):
        user_id = path.parent.name[1:]
        if user_id.isdigit():
            counts[int(user_id)] = counts.get(int(user_id), 0) + 1
    return counts


def _last_logins(session: Session) -> dict[int, datetime.datetime]:
    """Dernière session ouverte par compte (inscription ou connexion)."""
    rows = session.execute(
        select(accounts.SessionRow.user_id, func.max(accounts.SessionRow.created_at)).group_by(
            accounts.SessionRow.user_id
        )
    )
    return {user_id: at for user_id, at in rows}


def _account_out(
    row: accounts.UserRow, saves: dict[int, int], logins: dict[int, datetime.datetime]
) -> AccountOut:
    premium = row.premium_at is not None
    seasons = row.seasons_played or 0
    source = None
    if premium:
        source = "offert" if not row.payment_ref or row.payment_ref == GIFT_REF else "stripe"
    return AccountOut(
        id=row.id,
        email=row.email,
        created_at=row.created_at,
        last_login_at=logins.get(row.id),
        premium=premium,
        premium_at=row.premium_at,
        premium_source=source,
        payment_ref=row.payment_ref,
        seasons_played=seasons,
        seasons_left=None if premium else max(0, accounts.FREE_SEASONS - seasons),
        saves=saves.get(row.id, 0),
        admin=row.email == ADMIN_EMAIL,
    )


def _all_accounts() -> list[AccountOut]:
    saves = _save_counts()
    with _accounts_session() as session:
        logins = _last_logins(session)
        rows = session.scalars(select(accounts.UserRow).order_by(accounts.UserRow.id.desc()))
        return [_account_out(row, saves, logins) for row in rows]


def _account_detail(user_id: int) -> AccountDetail:
    with _accounts_session() as session:
        row = session.get(accounts.UserRow, user_id)
        if row is None:
            raise HTTPException(status_code=404, detail="Compte introuvable")
        out = _account_out(row, _save_counts(), _last_logins(session))
    user = accounts.get(user_id)
    slots = [
        _save_out(user, slot)
        for slot in range(1, database.SLOT_COUNT + 1)
        if database.slot_exists(user_id, slot)
    ]
    return AccountDetail(**out.model_dump(), slots=slots)


@router.get("/me")
def me(user: AdminDep) -> dict:
    """Répond 200 aux administrateurs (l'interface montre alors l'accès au backoffice)."""
    return {"email": user.email}


@router.get("/overview", response_model=OverviewOut)
def overview(_: AdminDep) -> OverviewOut:
    found = _all_accounts()
    now = _now()
    edits = catalog.edits()
    return OverviewOut(
        accounts=len(found),
        premium=sum(a.premium for a in found),
        premium_paid=sum(a.premium_source == "stripe" for a in found),
        premium_offered=sum(a.premium_source == "offert" for a in found),
        new_7_days=sum(a.created_at > now - datetime.timedelta(days=7) for a in found),
        new_30_days=sum(a.created_at > now - datetime.timedelta(days=30) for a in found),
        free_exhausted=sum(a.seasons_left == 0 for a in found),
        active_sessions=_active_sessions(),
        saves=sum(a.saves for a in found),
        free_seasons=accounts.FREE_SEASONS,
        clubs=len(catalog.club_entries()),
        clubs_edited=len(edits),
        logos=len(catalog.logos()),
    )


def _active_sessions() -> int:
    """Sessions encore valides (navigateurs connectés ces trente derniers jours)."""
    with _accounts_session() as session:
        return session.scalar(
            select(func.count())
            .select_from(accounts.SessionRow)
            .where(accounts.SessionRow.expires_at > _now())
        )


@router.get("/users", response_model=list[AccountOut])
def list_users(_: AdminDep) -> list[AccountOut]:
    """Tous les comptes, les plus récents d'abord."""
    return _all_accounts()


@router.get("/users/{user_id}", response_model=AccountDetail)
def get_user(user_id: int, _: AdminDep) -> AccountDetail:
    """Un compte et ses parties (club, saison, dernière sauvegarde)."""
    return _account_detail(user_id)


class PremiumIn(BaseModel):
    premium: bool


@router.put("/users/{user_id}/premium", response_model=AccountDetail)
def set_premium(user_id: int, body: PremiumIn, _: AdminDep) -> AccountDetail:
    """Offre la version complète, ou la retire (un paiement Stripe garde sa trace chez Stripe)."""
    if accounts.get(user_id) is None:
        raise HTTPException(status_code=404, detail="Compte introuvable")
    if body.premium:
        accounts.grant_premium(user_id, GIFT_REF)
    else:
        accounts.revoke_premium(user_id)
    return _account_detail(user_id)


@router.post("/users/{user_id}/seasons/reset", response_model=AccountDetail)
def reset_seasons(user_id: int, _: AdminDep) -> AccountDetail:
    """Remet à zéro les saisons jouées d'un compte gratuit : il en retrouve deux."""
    with _accounts_session() as session:
        row = session.get(accounts.UserRow, user_id)
        if row is None:
            raise HTTPException(status_code=404, detail="Compte introuvable")
        row.seasons_played = 0
        session.commit()
    return _account_detail(user_id)


# --- Clubs ---------------------------------------------------------------------------------


Rating = Annotated[int, Field(ge=ATTRIBUTE_MIN, le=ATTRIBUTE_MAX)]


class Ratings(BaseModel):
    """Les 9 notes d'un joueur, sur 20 (models/domain.py)."""

    pace: Rating
    power: Rating
    handling: Rating
    passing: Rating
    kicking: Rating
    tackling: Rating
    scrum: Rating
    lineout: Rating
    stamina: Rating


class PlayerFields(BaseModel):
    # Sans « / » : le nom sert d'adresse au joueur (api/routers/admin_players.py).
    name: str = Field(min_length=1, max_length=100, pattern=r"^[^/]+$")
    position: Position
    nationality: str | None = Field(default=None, pattern=r"^[A-Z]{3}$")
    international: bool = False
    born: datetime.date | None = None
    # Nom du fichier sur Wikimedia Commons (photo du vrai joueur).
    photo: str | None = Field(default=None, max_length=300)
    # Notes fixées depuis le backoffice ; None : tirées selon le club, l'âge et la sélection.
    attributes: Ratings | None = None


class RosterPlayer(PlayerFields):
    # Photo envoyée depuis le backoffice (son empreinte, catalog.py) : passe avant `photo`.
    photo_id: str | None = Field(default=None, pattern=r"^[0-9a-f]{16}$")


class RosterIn(BaseModel):
    pros: list[RosterPlayer] = Field(max_length=ROSTER_MAX_PROS)
    youths: list[RosterPlayer] = Field(default_factory=list, max_length=ROSTER_MAX_YOUTHS)


class ClubSummary(BaseModel):
    name: str
    league: str
    league_name: str
    # Club créé depuis le backoffice (sinon un vrai club du code).
    created: bool
    # Championnat d'origine d'un vrai club (None pour un club créé).
    home_league: str | None
    # Pays du club : la nationalité de ses joueurs inventés.
    nation: str | None
    city: str
    stadium: str
    capacity: int
    level: float
    wealth: float
    # Champs retouchés depuis le backoffice (city, level, colors, roster, logo, league...).
    edited: list[str]
    colors: list[str] | None
    light: bool | None
    logo: str | None
    pros: int
    youths: int
    # D'où vient l'effectif : le backoffice, data/rosters.json, ou rien (joueurs inventés).
    roster_source: Literal["backoffice", "fichier", "inventé"]


class ClubDetail(ClubSummary):
    defaults: dict | None
    roster: RosterIn
    updated_at: datetime.datetime | None
    updated_by: str | None


Color = Annotated[str, Field(pattern=r"^#[0-9A-Fa-f]{6}$")]
NationCode = Annotated[str, Field(pattern=r"^[A-Z]{3}$")]


class ClubIn(BaseModel):
    league: str = Field(min_length=1, max_length=LEAGUE_CODE_LENGTH)
    city: str = Field(min_length=1, max_length=100)
    stadium: str = Field(min_length=1, max_length=100)
    capacity: int = Field(ge=1_000, le=100_000)
    level: float = Field(ge=4, le=18)
    wealth: float = Field(ge=0, le=1)
    # None : les couleurs d'origine (clubLogos.json) ; sinon une à trois couleurs.
    colors: list[Color] | None = Field(default=None, min_length=1, max_length=3)
    light: bool | None = None
    # Club créé seulement (un vrai club garde son pays).
    nation: NationCode | None = None


class NewClubIn(ClubIn):
    name: str = Field(min_length=2, max_length=100)


class LogoIn(BaseModel):
    # Image encodée en base64 (PNG, JPEG ou WebP), sans l'en-tête « data: ».
    data: str = Field(max_length=catalog.LOGO_MAX_BYTES * 4 // 3 + 8)


def _roster_out(raw: dict | None) -> RosterIn:
    def players(entries: list[dict]) -> list[RosterPlayer]:
        return [
            RosterPlayer(
                name=e["name"][:100],
                position=Position(e["position"].upper()),
                nationality=(e.get("nationality") or "").upper()[:3] or None,
                international=bool(e.get("international")),
                born=e.get("born"),
                photo=e.get("photo"),
                attributes=e.get("attributes"),
                photo_id=e.get("photo_id"),
            )
            for e in entries
        ]

    raw = raw or {}
    return RosterIn(pros=players(raw.get("pros", [])), youths=players(raw.get("youths", [])))


def player_entry(p: RosterPlayer) -> dict:
    """Un joueur au format de data/rosters.json (poste en minuscules, date ISO)."""
    entry = {"name": " ".join(p.name.split()), "position": p.position.value.lower()}
    entry["nationality"] = p.nationality
    entry["international"] = p.international
    if p.born:
        entry["born"] = p.born.isoformat()
    if p.photo:
        entry["photo"] = p.photo
    if p.photo_id:
        entry["photo_id"] = p.photo_id
    if p.attributes:
        entry["attributes"] = p.attributes.model_dump()
    return entry


def _roster_file(roster: RosterIn) -> dict:
    """Effectif au format de data/rosters.json."""
    return {
        "source": "backoffice",
        "pros": [player_entry(p) for p in roster.pros],
        "youths": [player_entry(p) for p in roster.youths],
    }


def _club_summary(
    entry: catalog.ClubEntry, names: dict[str, str], logos: dict, rosters: dict
) -> ClubSummary:
    edit, club, name = entry.edit, entry.club, entry.name
    edited = []
    if edit is not None and not entry.created:
        fields = (*catalog.CLUB_FIELDS, "colors", "light", "roster", "league")
        edited = [field for field in fields if getattr(edit, field) is not None]
    elif entry.created:
        edited = [f for f in ("colors", "light", "roster") if getattr(edit, f) is not None]
    if name in logos:
        edited.append("logo")
    roster = rosters.get(name) or {}
    source = "fichier" if roster.get("pros") else "inventé"
    if "roster" in edited:
        source = "backoffice"
    return ClubSummary(
        name=name,
        league=entry.league,
        league_name=names.get(entry.league, entry.league),
        created=entry.created,
        home_league=entry.home_league,
        nation=entry.nation,
        city=club.city,
        stadium=club.stadium,
        capacity=club.capacity,
        level=club.level,
        wealth=club.wealth,
        edited=edited,
        colors=edit.colors if edit else None,
        light=edit.light if edit else None,
        logo=catalog.logo_url(name, logos[name].digest) if name in logos else None,
        pros=len(roster.get("pros", [])),
        youths=len(roster.get("youths", [])),
        roster_source=source,
    )


def _league_names() -> dict[str, str]:
    return {league.code: league.name for league, _ in catalog.all_leagues()}


def _entry(name: str) -> catalog.ClubEntry:
    entry = catalog.club_entries().get(name)
    if entry is None:
        raise HTTPException(status_code=404, detail="Club introuvable")
    return entry


def _club_detail(name: str) -> ClubDetail:
    entry, rosters = _entry(name), catalog.rosters()
    summary = _club_summary(entry, _league_names(), catalog.logos(), rosters)
    real = catalog.real_clubs().get(name)
    edit = entry.edit
    defaults = None
    if real is not None:
        defaults = {field: getattr(real[1], field) for field in catalog.CLUB_FIELDS}
        defaults["league"] = real[0].code
    return ClubDetail(
        **summary.model_dump(),
        defaults=defaults,
        roster=_roster_out(rosters.get(name)),
        updated_at=edit.updated_at if edit else None,
        updated_by=edit.updated_by if edit else None,
    )


def _check_league(code: str, club: str | None = None) -> None:
    """Un championnat où l'on peut mettre un club de plus (400 sinon)."""
    found = {league.code: row for league, row in catalog.all_leagues()}
    if code not in found:
        raise HTTPException(status_code=400, detail="Championnat inconnu")
    if found[code] is not None and found[code].archived:
        raise HTTPException(status_code=400, detail="Ce championnat est archivé")
    members = [e for e in catalog.club_entries().values() if e.league == code and e.name != club]
    if len(members) >= catalog.MAX_CLUBS:
        raise HTTPException(
            status_code=400, detail=f"Ce championnat a déjà {catalog.MAX_CLUBS} clubs, le maximum"
        )


def _colors(values: dict) -> dict:
    if values.get("colors"):
        values["colors"] = [color.upper() for color in values["colors"]]
    return values


@router.get("/clubs", response_model=list[ClubSummary])
def list_clubs(_: AdminDep) -> list[ClubSummary]:
    """Tous les clubs (vrais et créés), retouches comprises."""
    names, logos, rosters = _league_names(), catalog.logos(), catalog.rosters()
    return [_club_summary(e, names, logos, rosters) for e in catalog.club_entries().values()]


@router.post("/clubs", response_model=ClubDetail, status_code=201)
def create_club(body: NewClubIn, user: AdminDep) -> ClubDetail:
    """Un club de plus, dans le championnat choisi (pour les nouvelles parties)."""
    name = " ".join(body.name.split())
    taken = {n.lower() for n in catalog.club_entries()} | {n.name.lower() for n in NATIONS}
    if name.lower() in taken:
        raise HTTPException(status_code=400, detail="Ce nom est déjà pris")
    _check_league(body.league)
    values = _colors(body.model_dump(exclude={"name", "league", "nation"}))
    club = RealClub(
        name, values.pop("city"), values.pop("stadium"), values.pop("capacity"),
        values.pop("level"), values.pop("wealth"),
    )  # fmt: skip
    catalog.create_club(club, body.league, body.nation, user.email, **values)
    return _club_detail(name)


@router.get("/clubs/{name}", response_model=ClubDetail)
def get_club(name: ClubName, _: AdminDep) -> ClubDetail:
    return _club_detail(name)


@router.put("/clubs/{name}", response_model=ClubDetail)
def save_club(name: ClubName, body: ClubIn, user: AdminDep) -> ClubDetail:
    """Fiche du club : championnat, stade, niveau, budget (nouvelles parties), couleurs
    (tout de suite)."""
    entry = _entry(name)
    if body.league != entry.league:
        _check_league(body.league, name)
    values = _colors(body.model_dump())
    if not entry.created:
        values.pop("nation")
    catalog.save_club(name, user.email, **values)
    return _club_detail(name)


@router.put("/clubs/{name}/roster", response_model=ClubDetail)
def save_roster(name: ClubName, body: RosterIn, user: AdminDep) -> ClubDetail:
    """Remplace l'effectif du club (pour les nouvelles parties)."""
    _entry(name)
    catalog.save_club(name, user.email, roster=_roster_file(body))
    return _club_detail(name)


@router.delete("/clubs/{name}/roster", response_model=ClubDetail)
def reset_roster(name: ClubName, user: AdminDep) -> ClubDetail:
    """L'effectif redevient celui de data/rosters.json (des joueurs inventés pour un club créé)."""
    _entry(name)
    catalog.save_club(name, user.email, roster=None)
    return _club_detail(name)


def decode_image(body: LogoIn, what: str) -> tuple[str, bytes]:
    """(type, octets) d'une image envoyée en base64 (400 si elle ne convient pas)."""
    try:
        data = base64.b64decode(body.data, validate=True)
    except (binascii.Error, ValueError) as error:
        raise HTTPException(status_code=400, detail="Image illisible") from error
    kind = catalog.sniff_image(data)
    if kind is None:
        raise HTTPException(status_code=400, detail=f"{what} en PNG, JPEG ou WebP")
    if len(data) > catalog.LOGO_MAX_BYTES:
        raise HTTPException(status_code=400, detail="Image trop lourde (512 Ko au plus)")
    return kind, data


@router.put("/clubs/{name}/logo", response_model=ClubDetail)
def upload_logo(name: ClubName, body: LogoIn, _: AdminDep) -> ClubDetail:
    _entry(name)
    catalog.save_logo(name, *decode_image(body, "Blason"))
    return _club_detail(name)


@router.delete("/clubs/{name}/logo", response_model=ClubDetail)
def delete_logo(name: ClubName, _: AdminDep) -> ClubDetail:
    _entry(name)
    catalog.delete_logo(name)
    return _club_detail(name)


@router.delete("/clubs/{name}", response_model=ClubDetail | None)
def reset_club(name: ClubName, _: AdminDep) -> ClubDetail | None:
    """Un vrai club redevient celui du code (fiche, championnat, couleurs, blason,
    effectif) ; un club créé est effacé (null), sauf des parties déjà commencées."""
    entry = _entry(name)
    if entry.created:
        catalog.delete_club(name)
        return None
    catalog.reset_club(name)
    return _club_detail(name)


# --- Championnats ----------------------------------------------------------------------------


class LeagueOut(BaseModel):
    code: str
    name: str
    short_name: str
    country: str
    nation: str | None
    playoffs: PlayoffFormat
    neutral_final: bool
    # Championnat du code dont il suit le calendrier (le sien pour un championnat du code).
    calendar: str
    prize_factor: float
    # Créé depuis le backoffice (sinon un championnat du code, dont seuls les clubs changent).
    custom: bool
    archived: bool
    clubs: int
    min_clubs: int
    max_clubs: int
    # Assez de clubs pour sa formule : il sera dans les nouvelles parties.
    ready: bool
    europe: bool
    # « up » : son champion monte ; « down » : son dernier descend.
    promotion: Literal["up", "down"] | None


class LeagueIn(BaseModel):
    name: str = Field(min_length=2, max_length=60)
    short_name: str = Field(min_length=1, max_length=30)
    country: str = Field(default="", max_length=60)
    nation: NationCode | None = None
    playoffs: PlayoffFormat
    neutral_final: bool = True
    calendar: str
    prize_factor: float = Field(ge=0, le=1)
    archived: bool = False


def _leagues_out() -> list[LeagueOut]:
    counts: dict[str, int] = {}
    for entry in catalog.club_entries().values():
        counts[entry.league] = counts.get(entry.league, 0) + 1
    lower, upper = PROMOTION
    out = []
    for league, row in catalog.all_leagues():
        archived = bool(row and row.archived)
        count, minimum = counts.get(league.code, 0), catalog.min_clubs(league)
        out.append(
            LeagueOut(
                code=league.code,
                name=league.name,
                short_name=league.short_name,
                country=league.country,
                nation=row.nation if row else None,
                playoffs=league.playoffs,
                neutral_final=league.neutral_final,
                calendar=row.calendar if row else league.code,
                prize_factor=league.prize_factor,
                custom=row is not None,
                archived=archived,
                clubs=count,
                min_clubs=minimum,
                max_clubs=catalog.MAX_CLUBS,
                ready=not archived and minimum <= count <= catalog.MAX_CLUBS,
                europe=league.code in europe.LEAGUES,
                promotion={lower: "up", upper: "down"}.get(league.code),
            )
        )
    return out


def _league_values(body: LeagueIn) -> dict:
    if body.calendar not in catalog.BUILT_IN:
        raise HTTPException(status_code=400, detail="Calendrier inconnu")
    values = body.model_dump()
    values["playoffs"] = body.playoffs.value
    return values


@router.get("/leagues", response_model=list[LeagueOut])
def list_leagues(_: AdminDep) -> list[LeagueOut]:
    """Les championnats du code puis ceux du backoffice, avec leurs clubs comptés."""
    return _leagues_out()


@router.post("/leagues", response_model=list[LeagueOut], status_code=201)
def create_league(body: LeagueIn, _: AdminDep) -> list[LeagueOut]:
    """Un championnat de plus (vide : on y met ensuite des clubs)."""
    catalog.save_league(None, **_league_values(body))
    return _leagues_out()


@router.put("/leagues/{code}", response_model=list[LeagueOut])
def save_league(code: str, body: LeagueIn, _: AdminDep) -> list[LeagueOut]:
    """Modifie un championnat du backoffice (ceux du code ne changent que par leurs clubs).
    Archivé, il quitte les nouvelles parties ; il n'est jamais effacé, pour que les parties
    qui le jouent gardent sa formule."""
    if code not in catalog.league_rows():
        raise HTTPException(status_code=404, detail="Championnat introuvable (ou du code)")
    catalog.save_league(code, **_league_values(body))
    return _leagues_out()
