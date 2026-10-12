"""Jouer le match du club dirigé (ou de sa sélection) en direct, minute par minute.

`POST /live` lance le match de la prochaine journée (la semaine d'entraînement a
lieu tout de suite, comme avant une journée simulée). Puis le frontend fait
avancer le chrono (`/live/advance`), met en pause pour changer la tactique
(`/live/tactics`) ou faire un remplacement (`/live/substitute`), et quand le
match est fini (ou pour l'abandonner au staff), `POST /live/finish` joue le
reste de la journée : les autres matchs, l'économie, les affaires.

Un sélectionneur joue de la même façon le match de sa sélection, le jour où il
tombe : mêmes routes, la sauvegarde est à part (`LiveInternationalRow`).
"""

from fastapi import APIRouter, HTTPException
from sqlalchemy import select

from api import internationals
from api.affairs import forced_starters, ignore_pending
from api.deps import SessionDep, load_clubs
from api.live import (
    Live,
    live_club_ids,
    live_out,
    load_live,
    load_live_test,
    run_training_week,
)
from api.notes import History
from api.routers import selection
from api.routers.internationals import NATION_NAMES
from api.routers.seasons import (
    _current_or_404,
    _ensure_next_stage,
    focus_league,
    play_next_matchday,
    season_rng,
)
from api.schemas import AdvanceIn, AdvanceOut, LiveOut, PlayOut, SubstituteIn, TacticsIn
from data.nations import NATIONS_BY_CODE
from engine.match_engine import LiveMatch, Tactics, staff_tactics, team_strength
from models import Stage
from models.orm import CareerRow, ClubRow, LiveInternationalRow, LiveMatchRow, SelectorRow

router = APIRouter(prefix="/live", tags=["match en direct"])


def _my_club_id(session) -> int:
    """L'équipe que mène le joueur : son club, ou sa sélection s'il est sélectionneur."""
    career = session.scalars(select(CareerRow)).first()
    if career is not None:
        return career.club_id
    human = internationals.selector(session)
    if human is None:
        raise HTTPException(status_code=404, detail="Aucune carrière en cours")
    return NATIONS_BY_CODE[human.nation].id


def _load(session) -> tuple[Live, dict[int, str], int]:
    """Le match en direct en cours (404 sinon), les noms des équipes et celle du joueur."""
    my_club_id = _my_club_id(session)
    if internationals.selector(session) is not None:
        live, names = load_live_test(session), NATION_NAMES
    else:
        live = load_live(session, load_clubs(session, live_club_ids(session)))
        names = _names(session)
    if live is None:
        raise HTTPException(status_code=404, detail="Aucun match en direct")
    return live, names, my_club_id


def _names(session) -> dict[int, str]:
    return dict(session.execute(select(ClubRow.id, ClubRow.name)).all())


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

    Pour un sélectionneur : le match de sa sélection, le jour où il tombe.
    """
    human = internationals.selector(session)
    if human is not None:
        return _start_test(session, human)
    my_club_id = _my_club_id(session)
    season = _current_or_404(session)
    names = _names(session)

    existing = load_live(session, load_clubs(session, live_club_ids(session)))
    if existing is not None:
        return live_out(existing, names, my_club_id)

    ignore_pending(session)
    league = focus_league(session)
    _ensure_next_stage(session, season, league)
    unplayed = [m for m in season.matches if not m.is_played and m.league == league]
    if not unplayed:
        raise HTTPException(status_code=400, detail="La saison est terminée")
    matchday = min(m.matchday for m in unplayed)
    todays = [m for m in unplayed if m.matchday == matchday]
    match_row = next((m for m in todays if my_club_id in (m.home_club_id, m.away_club_id)), None)
    if match_row is None:
        raise HTTPException(status_code=400, detail="Ton club ne joue pas cette journée")
    stage, day = Stage(match_row.stage), match_row.date

    # Semaine d'entraînement des clubs dont le championnat joue ce jour-là.
    leagues = {m.league for m in season.matches if m.date == day and not m.is_played}
    playing_ids = session.scalars(select(ClubRow.id).where(ClubRow.league.in_(leagues)))
    clubs = load_clubs(session, {*playing_ids, my_club_id})
    clubs[my_club_id].forced_starters = forced_starters(session, my_club_id)
    # Doublon : les joueurs retenus par une sélection qui joue ce jour-là manquent.
    internationals.announce_due(session, season, day)
    called_up = internationals.absentees_on(session, season, day)
    for club in clubs.values():
        internationals.rules.release(club, called_up, day)
    playing = {club_id: club for club_id, club in clubs.items() if club.league in leagues}
    rng = season_rng(season, day, "live")
    history = History.load(session)
    forms = {club_id: history.form(club, day) for club_id, club in playing.items()}
    mine = run_training_week(session, playing, forms, day, rng, my_club_id)
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


def _start_test(session, human: SelectorRow) -> LiveOut:
    """Lance le match de la sélection du joueur (ou reprend celui en cours) : il faut
    que ce soit le prochain jour de match, et que la liste soit annoncée."""
    season = _current_or_404(session)
    my_id = NATIONS_BY_CODE[human.nation].id
    existing = load_live_test(session)
    if existing is not None:
        return live_out(existing, NATION_NAMES, my_id)

    where = selection.situation(session, season, human)
    if where.phase == "list":
        raise HTTPException(status_code=400, detail="Annonce ta liste avant de jouer")
    if where.phase != "match":
        raise HTTPException(status_code=400, detail="Ta sélection ne joue pas aujourd'hui")
    match_row = where.upcoming[0]
    day = match_row.date
    history = History.load(session)
    teams, forms = internationals.national_teams(session, season, [match_row], history.appearances)
    home, away = teams[match_row.home_id], teams[match_row.away_id]
    opponent = away if home.id == my_id else home
    opponent_tactics = staff_tactics(team_strength(opponent, day, forms[opponent.id]))
    live = LiveMatch(
        home,
        away,
        rng=season_rng(season, day, "live"),
        matchday=match_row.matchday,
        neutral=match_row.neutral,
        day=day,
        home_form=forms[home.id],
        away_form=forms[away.id],
        home_tactics=opponent_tactics if home is opponent else Tactics(),
        away_tactics=opponent_tactics if away is opponent else Tactics(),
        auto={opponent.id},
    )
    row = LiveInternationalRow(match_id=match_row.id, state=live.to_state())
    session.add(row)
    session.commit()
    return live_out(Live(row=row, match=live, match_row=match_row), NATION_NAMES, my_id)


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


@router.post("/finish", response_model=PlayOut | AdvanceOut)
def finish(session: SessionDep) -> PlayOut | AdvanceOut:
    """Termine la journée : le match en direct (joué jusqu'au bout par le staff s'il
    reste des minutes), puis les autres matchs, l'économie et les affaires. Même
    résultat que `POST /seasons/current/play` (ou, pour un sélectionneur, que
    `POST /selection/advance`)."""
    _load(session)
    if internationals.selector(session) is not None:
        return selection.advance(session)
    return play_next_matchday(session)
