"""Jouer le match du club dirigé en direct, minute par minute.

`POST /live` lance le match de la prochaine journée (la semaine d'entraînement a
lieu tout de suite, comme avant une journée simulée). Puis le frontend fait
avancer le chrono (`/live/advance`), met en pause pour changer la tactique
(`/live/tactics`) ou faire un remplacement (`/live/substitute`), et quand le
match est fini (ou pour l'abandonner au staff), `POST /live/finish` joue le
reste de la journée : les autres matchs, l'économie, les affaires.
"""

import random

from fastapi import APIRouter, HTTPException
from sqlalchemy import select

from api.affairs import forced_starters, ignore_pending
from api.deps import SessionDep
from api.live import Live, live_out, load_live, run_training_week
from api.notes import History
from api.routers.seasons import (
    _club_rows,
    _current_or_404,
    _ensure_next_stage,
    play_next_matchday,
)
from api.schemas import AdvanceIn, LiveOut, PlayOut, SubstituteIn, TacticsIn
from engine.match_engine import LiveMatch, Tactics, staff_tactics, team_strength
from models import Stage
from models.orm import CareerRow, LiveMatchRow

router = APIRouter(prefix="/live", tags=["match en direct"])


def _my_club_id(session) -> int:
    career = session.scalars(select(CareerRow)).first()
    if career is None:
        raise HTTPException(status_code=404, detail="Aucune carrière en cours")
    return career.club_id


def _load(session) -> tuple[Live, dict[int, str], int]:
    """Le match en direct en cours (404 sinon), les noms des clubs et le club dirigé."""
    my_club_id = _my_club_id(session)
    club_rows = _club_rows(session)
    clubs = {row.id: row.to_domain() for row in club_rows}
    live = load_live(session, clubs)
    if live is None:
        raise HTTPException(status_code=404, detail="Aucun match en direct")
    return live, {row.id: row.name for row in club_rows}, my_club_id


@router.get("", response_model=LiveOut)
def get_live(session: SessionDep) -> LiveOut:
    """Le match en direct en cours, pour le reprendre là où on l'a laissé."""
    live, names, my_club_id = _load(session)
    return live_out(live, names, my_club_id)


@router.post("", response_model=LiveOut, status_code=201)
def start_live(session: SessionDep) -> LiveOut:
    """Lance le match du club dirigé de la prochaine journée (ou reprend celui en cours).

    Les affaires sans réponse sont réglées d'office, la semaine d'entraînement de
    tous les clubs est jouée, puis le XV et le banc sont choisis à la date du match.
    L'adversaire est géré par son staff ; notre banc attend les ordres du manager.
    """
    my_club_id = _my_club_id(session)
    season = _current_or_404(session)
    club_rows = _club_rows(session)
    names = {row.id: row.name for row in club_rows}
    clubs = {row.id: row.to_domain() for row in club_rows}

    existing = load_live(session, clubs)
    if existing is not None:
        return live_out(existing, names, my_club_id)

    ignore_pending(session)
    clubs[my_club_id].forced_starters = forced_starters(session, my_club_id)
    _ensure_next_stage(session, season, clubs)
    unplayed = [m for m in season.matches if not m.is_played]
    if not unplayed:
        raise HTTPException(status_code=400, detail="La saison est terminée")
    matchday = min(m.matchday for m in unplayed)
    todays = [m for m in unplayed if m.matchday == matchday]
    match_row = next((m for m in todays if my_club_id in (m.home_club_id, m.away_club_id)), None)
    if match_row is None:
        raise HTTPException(status_code=400, detail="Ton club ne joue pas cette journée")
    stage, day = Stage(match_row.stage), match_row.date

    rng = random.Random()
    history = History.load(session)
    forms = {club_id: history.form(club, day) for club_id, club in clubs.items()}
    mine = run_training_week(session, clubs, forms, day, rng, my_club_id)
    session.commit()

    home, away = clubs[match_row.home_club_id], clubs[match_row.away_club_id]
    opponent = away if home.id == my_club_id else home
    opponent_tactics = staff_tactics(team_strength(opponent, day, forms[opponent.id]))
    live = LiveMatch(
        home,
        away,
        rng=rng,
        matchday=matchday,
        neutral=match_row.neutral,
        day=day,
        home_form=forms[home.id],
        away_form=forms[away.id],
        knockout=stage.is_playoff,
        home_tactics=opponent_tactics if home is opponent else Tactics(),
        away_tactics=opponent_tactics if away is opponent else Tactics(),
        auto={opponent.id},
    )
    row = LiveMatchRow(
        match_id=match_row.id,
        my_injuries=[injury_row.id for injury_row, _ in mine],
        state=live.to_state(),
    )
    session.add(row)
    session.commit()
    return live_out(Live(row=row, match=live, match_row=match_row), names, my_club_id)


@router.post("/advance", response_model=LiveOut)
def advance(payload: AdvanceIn, session: SessionDep) -> LiveOut:
    """Joue les minutes suivantes (une par défaut) et renvoie le match tel qu'il en est."""
    live, names, my_club_id = _load(session)
    if live.match.finished:
        raise HTTPException(status_code=400, detail="Le match est terminé")
    live.match.advance(payload.minutes)
    live.save()
    session.commit()
    return live_out(live, names, my_club_id)


@router.post("/tactics", response_model=LiveOut)
def set_tactics(payload: TacticsIn, session: SessionDep) -> LiveOut:
    """Change la tactique du club dirigé, effective dès la minute suivante."""
    live, names, my_club_id = _load(session)
    current = live.match.side(my_club_id).tactics
    tactics = Tactics(
        game_plan=payload.game_plan or current.game_plan,
        defence=payload.defence or current.defence,
        penalties=payload.penalties or current.penalties,
    )
    live.match.set_tactics(my_club_id, tactics)
    live.save()
    session.commit()
    return live_out(live, names, my_club_id)


@router.post("/substitute", response_model=LiveOut)
def substitute(payload: SubstituteIn, session: SessionDep) -> LiveOut:
    """Fait entrer un remplaçant du club dirigé à la place d'un joueur sur le terrain."""
    live, names, my_club_id = _load(session)
    try:
        live.match.substitute(my_club_id, payload.player_out, payload.player_in)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    live.save()
    session.commit()
    return live_out(live, names, my_club_id)


@router.post("/finish", response_model=PlayOut)
def finish(session: SessionDep) -> PlayOut:
    """Termine la journée : le match en direct (joué jusqu'au bout par le staff s'il
    reste des minutes), puis les autres matchs, l'économie et les affaires. Même
    résultat que `POST /seasons/current/play`."""
    _load(session)
    return play_next_matchday(session)
