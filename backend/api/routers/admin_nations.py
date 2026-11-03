"""Backoffice, onglet Sélections : la compo de chaque nation, son groupe et son XV.

Le groupe se choisit parmi les pros des effectifs (catalog.py) qui peuvent porter le
maillot : même nationalité, et un club du pays si la fédération l'exige. Une compo peut
rester partielle : le staff complète la liste de 42 et les places vides du XV. Le banc
reste au staff, comme dans un club. Les parties s'en servent à la prochaine liste
annoncée, jusqu'à leur première Coupe du monde (api/internationals.py).
"""

import datetime
from collections import Counter
from typing import Annotated

from fastapi import APIRouter, HTTPException, Path
from pydantic import BaseModel, Field

import catalog
from api.routers.admin import AdminDep
from api.routers.admin_players import PlayerOut, _player_out
from data.nations import NATIONS, NATIONS_BY_CODE, Nation, home_nation, nation_code
from engine.internationals import POSITION_PLURALS, SQUAD_MINIMUM, SQUAD_QUOTA, SQUAD_SIZE
from engine.match_engine import SLOT_NUMBERS, SLOT_POSITIONS
from models import Position

router = APIRouter(prefix="/backoffice/nations", tags=["backoffice"])

NationPath = Annotated[str, Path(pattern=r"^[A-Z]{3}$")]


class CompoPlayer(BaseModel):
    club: str = Field(min_length=1, max_length=100)
    name: str = Field(min_length=1, max_length=100)


class NationIn(BaseModel):
    squad: list[CompoPlayer] = Field(max_length=SQUAD_SIZE)
    # Le XV, place par place : l'indice du joueur dans `squad`, ou None. Vide : tout au staff.
    lineup: list[int | None] = Field(default_factory=list, max_length=len(SLOT_POSITIONS))


class NationSummary(BaseModel):
    code: str
    name: str
    home_only: bool
    # Joueurs qui peuvent porter le maillot, dans les effectifs.
    pool: int
    edited: bool
    listed: int
    starters: int
    updated_at: datetime.datetime | None
    updated_by: str | None


class SlotOut(BaseModel):
    number: int
    position: Position


class NationDetail(NationSummary):
    players: list[PlayerOut]
    squad: list[CompoPlayer]
    lineup: list[int | None]
    # Joueurs de la compo qui ne peuvent plus porter le maillot : ils n'en font plus partie.
    missing: list[str]
    slots: list[SlotOut]
    size: int
    quota: dict[Position, int]
    minimum: dict[Position, int]


def _pools() -> dict[str, list[PlayerOut]]:
    """Les pros des effectifs qui peuvent porter chaque maillot, les internationaux d'abord."""
    catalog.ensure_synced()
    rosters = catalog.rosters()
    pools: dict[str, list[PlayerOut]] = {nation.code: [] for nation in NATIONS}
    for club, entry in catalog.club_entries().items():
        for raw in (rosters.get(club) or {}).get("pros", []):
            code = nation_code(raw.get("nationality"))
            if code in pools and _allowed(NATIONS_BY_CODE[code], club):
                pools[code].append(_player_out(club, entry.league, "pros", raw))
    for players in pools.values():
        players.sort(key=lambda p: (not p.international, -(p.overall or 0), p.name))
    return pools


def _allowed(nation: Nation, club: str) -> bool:
    return not nation.home_only or home_nation(club) == nation.code


def _nation_or_404(code: str) -> Nation:
    nation = NATIONS_BY_CODE.get(code)
    if nation is None:
        raise HTTPException(status_code=404, detail="Sélection introuvable")
    return nation


def _compo(
    row: catalog.NationEditRow | None, players: list[PlayerOut]
) -> tuple[list[CompoPlayer], list[int | None], list[str]]:
    """La compo enregistrée telle qu'elle vaut aujourd'hui : (groupe, XV, joueurs partis)."""
    if row is None:
        return [], [], []
    found = catalog.match_compo(row.squad, players, lambda p: (p.club, p.name))
    squad, missing = [], []
    places: dict[int, int] = {}
    for index, (entry, player) in enumerate(zip(row.squad, found, strict=True)):
        if player is None:
            missing.append(entry["name"])
        else:
            places[index] = len(squad)
            squad.append(CompoPlayer(club=player.club, name=player.name))
    return squad, [places.get(index) for index in row.lineup], missing


def _summary(nation: Nation, players: list[PlayerOut], row) -> NationSummary:
    squad, lineup, _ = _compo(row, players)
    return NationSummary(
        code=nation.code,
        name=nation.name,
        home_only=nation.home_only,
        pool=len(players),
        edited=row is not None,
        listed=len(squad),
        starters=sum(index is not None for index in lineup),
        updated_at=row.updated_at if row else None,
        updated_by=row.updated_by if row else None,
    )


def _detail(nation: Nation) -> NationDetail:
    players = _pools()[nation.code]
    row = catalog.nation_compos().get(nation.code)
    squad, lineup, missing = _compo(row, players)
    return NationDetail(
        **_summary(nation, players, row).model_dump(),
        players=players,
        squad=squad,
        lineup=lineup,
        missing=missing,
        slots=[
            SlotOut(number=number, position=position)
            for number, position in zip(SLOT_NUMBERS, SLOT_POSITIONS, strict=True)
        ],
        size=SQUAD_SIZE,
        quota=SQUAD_QUOTA,
        minimum=SQUAD_MINIMUM,
    )


def _check(body: NationIn, players: list[PlayerOut], nation: Nation) -> None:
    """Refuse (400) une compo que le jeu ne pourrait pas compléter en une liste valable."""
    known = {(p.club, p.name): p for p in players}
    wanted = [(entry.club, entry.name) for entry in body.squad]
    for club, name in wanted:
        if (club, name) not in known:
            raise HTTPException(
                status_code=400, detail=f"{name} ne peut pas porter le maillot : {nation.name}"
            )
    if len(set(wanted)) != len(wanted):
        raise HTTPException(status_code=400, detail="Un joueur figure deux fois dans le groupe")

    counts = Counter(known[key].position for key in wanted)
    room = SQUAD_SIZE - len(wanted)
    short = {pos: minimum - counts[pos] for pos, minimum in SQUAD_MINIMUM.items()}
    if sum(max(0, count) for count in short.values()) > room:
        position = next(pos for pos, count in short.items() if count > 0)
        raise HTTPException(
            status_code=400,
            detail=f"Il faut au moins {SQUAD_MINIMUM[position]} {POSITION_PLURALS[position]} "
            "dans la liste",
        )

    if body.lineup and len(body.lineup) != len(SLOT_POSITIONS):
        raise HTTPException(status_code=400, detail=f"Il faut {len(SLOT_POSITIONS)} places")
    chosen = [index for index in body.lineup if index is not None]
    if len(set(chosen)) != len(chosen):
        raise HTTPException(status_code=400, detail="Un joueur ne peut occuper qu'une place")
    if any(not 0 <= index < len(wanted) for index in chosen):
        raise HTTPException(status_code=400, detail="Le XV se choisit dans le groupe")


@router.get("", response_model=list[NationSummary])
def list_nations(_: AdminDep) -> list[NationSummary]:
    pools = _pools()
    rows = catalog.nation_compos()
    return [_summary(nation, pools[nation.code], rows.get(nation.code)) for nation in NATIONS]


@router.get("/{code}", response_model=NationDetail)
def get_nation(code: NationPath, _: AdminDep) -> NationDetail:
    return _detail(_nation_or_404(code))


@router.put("/{code}", response_model=NationDetail)
def save_nation(code: NationPath, body: NationIn, user: AdminDep) -> NationDetail:
    nation = _nation_or_404(code)
    _check(body, _pools()[code], nation)
    squad = [entry.model_dump() for entry in body.squad]
    catalog.save_nation(code, user.email, squad, list(body.lineup))
    return _detail(nation)


@router.delete("/{code}", response_model=NationDetail)
def reset_nation(code: NationPath, _: AdminDep) -> NationDetail:
    """La sélection repasse aux mains de son staff."""
    nation = _nation_or_404(code)
    catalog.reset_nation(code)
    return _detail(nation)
