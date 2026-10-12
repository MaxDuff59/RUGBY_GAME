"""La carrière de sélectionneur : annoncer sa liste, composer son XV, avancer dans la saison.

Deux semaines avant le premier match d'une fenêtre internationale, la liste de 42
joueurs doit être annoncée : la saison n'avance plus tant qu'elle ne l'est pas
(`phase` à « list »). Le sélectionneur fait avancer le monde un jour de match à
la fois (`POST /selection/advance`) : les clubs jouent leur saison, les autres
sélections leurs matchs, la sienne avec le XV qu'il a composé. Son match peut
aussi se jouer en direct (api/routers/live.py).

Règles : engine/internationals.py ; lecture et écriture en base : api/internationals.py.
"""

import datetime
from dataclasses import dataclass

from fastapi import APIRouter, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from api import internationals
from api.deps import SessionDep
from api.ledger import game_date
from api.notes import History
from api.routers.internationals import (
    nation_out,
    season_starts,
    squad_player_out,
    summary,
    window_out,
)
from api.routers.seasons import _current_or_404, _play_day, _prepare_day
from api.schemas import (
    AdvanceOut,
    ClubDetail,
    FacilitiesOut,
    LineupIn,
    PlayerOut,
    PoolOut,
    RecordOut,
    ReplaceIn,
    SelectionOut,
    SquadListIn,
    StrengthOut,
)
from data.nations import NATIONS_BY_CODE, WINDOWS_BY_CODE, Nation, Window
from engine import internationals as rules
from engine.match_engine import SLOT_POSITIONS, team_strength
from models import Club, Facilities, Player
from models.orm import CallUpRow, InternationalRow, PlayerRow, SeasonRow, SelectorRow

router = APIRouter(prefix="/selection", tags=["sélectionneur"])


def selector_or_404(session: Session) -> SelectorRow:
    human = internationals.selector(session)
    if human is None:
        raise HTTPException(status_code=404, detail="Aucune carrière de sélectionneur en cours")
    return human


@dataclass
class Situation:
    """Où en est la sélection du joueur dans la saison."""

    nation: Nation
    rows: list[InternationalRow]  # tous les matchs internationaux de la saison
    mine: list[InternationalRow]  # les nôtres, dans l'ordre
    window: Window | None  # notre fenêtre en cours ou à venir
    call: CallUpRow | None  # notre liste pour cette fenêtre, si elle est annoncée
    next_day: datetime.date | None  # prochain jour de match dans le monde

    @property
    def upcoming(self) -> list[InternationalRow]:
        return [row for row in self.mine if not row.is_played]

    @property
    def window_rows(self) -> list[InternationalRow]:
        code = self.window.code if self.window else None
        return [row for row in self.rows if row.competition == code]

    @property
    def phase(self) -> str:
        if self.next_day is None:
            return "finished"
        if self.window is not None and self.call is None:
            deadline = rules.announce_by(internationals.fixture(r) for r in self.window_rows)
            if deadline <= self.next_day:
                return "list"
        if self.upcoming and self.upcoming[0].date == self.next_day:
            return "match"
        return "wait"


def situation(session: Session, season: SeasonRow, human: SelectorRow) -> Situation:
    nation = NATIONS_BY_CODE[human.nation]
    next_day = _prepare_day(session, season)  # ouvre aussi le calendrier international
    rows = internationals.test_rows(session, season)
    mine = [row for row in rows if nation.id in (row.home_id, row.away_id)]
    upcoming = [row for row in mine if not row.is_played]
    window = WINDOWS_BY_CODE[upcoming[0].competition] if upcoming else None
    call = None
    if window is not None:
        call = next(
            (
                row
                for row in internationals.call_up_rows(session, season)
                if row.competition == window.code and row.nation == nation.code
            ),
            None,
        )
    return Situation(nation, rows, mine, window, call, next_day)


def selection_out(session: Session, season: SeasonRow, where: Situation) -> SelectionOut:
    nation = where.nation
    record = RecordOut(played=0, won=0, drawn=0, lost=0)
    for row in where.mine:
        if not row.is_played:
            continue
        result = internationals.fixture(row).result_for(nation.id)
        record.played += 1
        record.won += result > 0
        record.drawn += result == 0
        record.lost += result < 0
    window = None
    if where.window is not None:
        window = window_out(where.window, where.window_rows, internationals.squads(session, season))
    return SelectionOut(
        nation=nation_out(nation),
        year=season.year,
        today=where.next_day or game_date(session),
        phase=where.phase,
        window=window,
        list_announced=where.call is not None,
        next_match=summary(where.upcoming[0]) if where.upcoming else None,
        next_day=where.next_day,
        record=record,
        squad_size=rules.SQUAD_SIZE,
    )


def _load(session: Session) -> tuple[SelectorRow, SeasonRow, Situation]:
    human = selector_or_404(session)
    season = _current_or_404(session)
    return human, season, situation(session, season, human)


def _first_match(where: Situation) -> datetime.date | None:
    """Le prochain match de notre sélection : la date à laquelle il faut être apte."""
    return where.upcoming[0].date if where.upcoming else None


def _players(session: Session, player_ids: list[int]) -> list[Player]:
    """Les joueurs demandés, dans l'ordre de la liste."""
    rows = session.scalars(select(PlayerRow).where(PlayerRow.id.in_(player_ids)))
    by_id = {row.id: row.to_domain() for row in rows}
    return [by_id[player_id] for player_id in player_ids if player_id in by_id]


# --- Où j'en suis ---------------------------------------------------------------------------


@router.get("", response_model=SelectionOut)
def get_selection(session: SessionDep) -> SelectionOut:
    """Ce qui attend le sélectionneur : liste à annoncer, match à jouer, ou jours à passer."""
    _, season, where = _load(session)
    return selection_out(session, season, where)


# --- La liste -------------------------------------------------------------------------------


def _pool_out(session: Session, season: SeasonRow, where: Situation) -> PoolOut:
    nation = where.nation
    day = game_date(session)
    names = internationals.club_names(session)
    eligible = internationals.eligible_players(session, {nation.code}, names)[nation.code]
    selected = list(where.call.player_ids) if where.call is not None else []
    # Un joueur de la liste reste affiché même s'il n'est plus sélectionnable.
    known = {player.id for player in eligible}
    everyone = eligible + _players(session, [i for i in selected if i not in known])
    starts = season_starts(season, where.rows)
    window = None
    if where.window is not None:
        window = window_out(where.window, where.window_rows, internationals.squads(session, season))
    return PoolOut(
        nation=nation_out(nation),
        window=window,
        announced=where.call is not None,
        size=rules.SQUAD_SIZE,
        quota=rules.SQUAD_QUOTA,
        minimum=rules.SQUAD_MINIMUM,
        selected=selected,
        suggested=[p.id for p in rules.pick_squad(eligible, _first_match(where) or day)],
        players=[squad_player_out(player, day, names, starts) for player in everyone],
    )


@router.get("/pool", response_model=PoolOut)
def get_pool(session: SessionDep) -> PoolOut:
    """Tous les joueurs sélectionnables, la proposition du staff, et la liste annoncée."""
    _, season, where = _load(session)
    return _pool_out(session, season, where)


@router.post("/list", response_model=PoolOut, status_code=201)
def announce_list(payload: SquadListIn, session: SessionDep) -> PoolOut:
    """Annonce la liste pour la prochaine fenêtre de la sélection : 42 joueurs
    sélectionnables, de quoi remplir une feuille de match à chaque poste."""
    _, season, where = _load(session)
    if where.window is None:
        raise HTTPException(status_code=400, detail="Plus aucun rendez-vous cette saison")
    if where.call is not None:
        raise HTTPException(status_code=400, detail="Ta liste est déjà annoncée")
    nation = where.nation
    eligible = {
        player.id: player
        for player in internationals.eligible_players(session, {nation.code})[nation.code]
    }
    if any(player_id not in eligible for player_id in payload.player_ids):
        raise HTTPException(
            status_code=400, detail="Un joueur de la liste n'est pas sélectionnable"
        )
    problem = rules.check_squad([eligible[player_id] for player_id in payload.player_ids])
    if problem is not None:
        raise HTTPException(status_code=400, detail=problem)
    session.add(
        CallUpRow(
            season_id=season.id,
            competition=where.window.code,
            nation=nation.code,
            player_ids=list(payload.player_ids),
            announced_on=game_date(session),
        )
    )
    session.commit()
    return _pool_out(session, season, situation(session, season, selector_or_404(session)))


@router.post("/replace", response_model=PoolOut)
def replace_player(payload: ReplaceIn, session: SessionDep) -> PoolOut:
    """Forfait : un joueur blessé de la liste laisse sa place à un autre joueur sélectionnable."""
    human, season, where = _load(session)
    if where.call is None:
        raise HTTPException(status_code=400, detail="Aucune liste annoncée")
    listed = list(where.call.player_ids)
    if payload.player_out not in listed:
        raise HTTPException(status_code=400, detail="Ce joueur n'est pas dans ta liste")
    if payload.player_in in listed:
        raise HTTPException(status_code=400, detail="Ce joueur est déjà dans ta liste")
    nation = where.nation
    eligible = {
        player.id: player
        for player in internationals.eligible_players(session, {nation.code})[nation.code]
    }
    arriving = eligible.get(payload.player_in)
    if arriving is None:
        raise HTTPException(status_code=400, detail="Ce joueur n'est pas sélectionnable")
    day = _first_match(where) or game_date(session)
    leaving = _players(session, [payload.player_out])[0]
    if not leaving.is_injured(day):
        raise HTTPException(
            status_code=400, detail=f"{leaving.name} n'est pas blessé : la liste est annoncée"
        )
    if arriving.is_injured(day):
        raise HTTPException(status_code=400, detail=f"{arriving.name} est blessé")
    where.call.player_ids = [payload.player_in if i == payload.player_out else i for i in listed]
    # Le forfait quitte aussi le XV choisi.
    human.lineup_choice = [None if i == payload.player_out else i for i in human.lineup_choice]
    session.commit()
    return _pool_out(session, season, situation(session, season, human))


# --- Le XV ----------------------------------------------------------------------------------


def _team(session: Session, human: SelectorRow, where: Situation) -> tuple[Club, datetime.date]:
    """La sélection avec sa liste (celle du staff tant qu'elle n'est pas annoncée),
    et le jour pour lequel on compose : notre prochain match."""
    nation = where.nation
    day = _first_match(where) or game_date(session)
    if where.call is not None:
        players = _players(session, list(where.call.player_ids))
    else:
        eligible = internationals.eligible_players(session, {nation.code})[nation.code]
        players = rules.pick_squad(eligible, day)
    return rules.national_team(nation, players, human.lineup_choice or []), day


def _team_out(session: Session, human: SelectorRow, where: Situation) -> ClubDetail:
    team, day = _team(session, human, where)
    form = rules.national_form(team, History.load(session).appearances, day)
    names = internationals.club_names(session)
    return ClubDetail(
        id=team.id,
        name=team.name,
        balance=0,
        facilities=FacilitiesOut.model_validate(Facilities()),
        strength=StrengthOut.from_team(team_strength(team, day, form)),
        players=[PlayerOut.from_player(player, day, names) for player in team.players],
        lineup_custom=any(player_id is not None for player_id in team.lineup_choice),
    )


@router.get("/team", response_model=ClubDetail)
def get_team(session: SessionDep) -> ClubDetail:
    """Le groupe (la liste annoncée, sinon celle que propose le staff) et son XV de départ."""
    human, _, where = _load(session)
    return _team_out(session, human, where)


@router.put("/lineup", response_model=ClubDetail)
def set_lineup(lineup: LineupIn, session: SessionDep) -> ClubDetail:
    """Le sélectionneur compose son XV parmi sa liste, place par place."""
    human, _, where = _load(session)
    ids = lineup.player_ids
    if len(ids) != len(SLOT_POSITIONS):
        raise HTTPException(status_code=400, detail=f"Il faut {len(SLOT_POSITIONS)} places")
    chosen = [player_id for player_id in ids if player_id is not None]
    if len(set(chosen)) != len(chosen):
        raise HTTPException(status_code=400, detail="Un joueur ne peut occuper qu'une place")
    team, day = _team(session, human, where)
    players = {player.id: player for player in team.players}
    for player_id in chosen:
        player = players.get(player_id)
        if player is None:
            raise HTTPException(status_code=400, detail="Ce joueur n'est pas dans ta liste")
        if player.is_injured(day):
            raise HTTPException(status_code=400, detail=f"{player.name} est blessé")
    human.lineup_choice = list(ids)
    session.commit()
    return _team_out(session, human, where)


@router.delete("/lineup", response_model=ClubDetail)
def reset_lineup(session: SessionDep) -> ClubDetail:
    """Rend la composition du XV au staff."""
    human, _, where = _load(session)
    human.lineup_choice = []
    session.commit()
    return _team_out(session, human, where)


# --- Avancer --------------------------------------------------------------------------------


@router.post("/advance", response_model=AdvanceOut)
def advance(session: SessionDep) -> AdvanceOut:
    """Joue le prochain jour de match du monde : clubs, sélections, et la nôtre si elle
    joue ce jour-là (avec le XV choisi ; un match en direct en cours est fini par le staff).

    Refusé tant que la liste due n'est pas annoncée."""
    human, season, where = _load(session)
    if where.phase == "finished":
        raise HTTPException(status_code=400, detail="La saison est terminée")
    if where.phase == "list":
        raise HTTPException(
            status_code=400,
            detail=f"Annonce ta liste de {rules.SQUAD_SIZE} joueurs avant de continuer",
        )
    day = where.next_day
    result = _play_day(session, season, day)
    return AdvanceOut(
        date=day,
        tests=[summary(row) for row in result.tests],
        club_matches=len(result.matches),
        injuries=result.cases,
        selection=selection_out(session, season, situation(session, season, human)),
    )
