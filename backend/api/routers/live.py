"""Jouer le match du club dirigé (ou de sa sélection) en direct, minute par minute.

`POST /live` lance le match de la prochaine journée (la semaine d'entraînement a
lieu tout de suite, comme avant une journée simulée). Puis le frontend fait
avancer le chrono (`/live/advance`), met en pause pour changer la tactique
(`/live/tactics`), parler à l'équipe (`/live/talk`) ou faire un remplacement
(`/live/substitute`). En fin de match serrée, le chrono s'arrête sur une pénalité
décisive (`crunch`) jusqu'au choix du manager (`/live/decide`). Quand le match
est fini (ou pour l'abandonner au staff), `POST /live/finish` joue le reste de la
journée : les autres matchs, l'économie, les affaires.

Un sélectionneur joue de la même façon le match de sa sélection, le jour où il
tombe : mêmes routes, la sauvegarde est à part (`LiveInternationalRow`).

En carrière de joueur (api/hero.py), le match est celui du club du joueur incarné,
mené de bout en bout par les deux staffs : ni tactique, ni discours, ni changement.
Le chrono s'arrête sur ses dilemmes (`dilemma`), qu'il tranche (`/live/choose`).
"""

from fastapi import APIRouter, HTTPException
from sqlalchemy import select

from api import competition, cup, internationals
from api import hero as heroes
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
    _phase,
    _play_day,
    _prepare_day,
    _season_out,
    _seeding,
    focus_league,
    next_fixture,
    play_next_matchday,
    season_rng,
)
from api.schemas import (
    AdvanceIn,
    AdvanceOut,
    ChooseIn,
    DecideIn,
    HeroDayOut,
    LiveOut,
    PlayOut,
    SubstituteIn,
    TacticsIn,
    TalkIn,
)
from data.derbies import derby
from data.nations import NATIONS_BY_CODE
from engine import hero as hero_rules
from engine.crowd import gate
from engine.dilemmas import HERO_ENTRY_MINUTE
from engine.match_engine import LiveMatch, Tactics, staff_tactics, team_strength
from engine.weather import forecast
from models import Stage
from models.orm import (
    CareerRow,
    ClubRow,
    InternationalRow,
    LiveInternationalRow,
    LiveMatchRow,
    SelectorRow,
)

router = APIRouter(prefix="/live", tags=["match en direct"])


def _my_club_id(session) -> int:
    """L'équipe que mène le joueur : son club, ou sa sélection s'il est sélectionneur."""
    career = session.scalars(select(CareerRow)).first()
    if career is not None:
        return career.club_id
    club_id = heroes.hero_club_id(session)
    if club_id is not None:
        return club_id
    human = internationals.selector(session)
    if human is None:
        raise HTTPException(status_code=404, detail="Aucune carrière en cours")
    return NATIONS_BY_CODE[human.nation].id


def _load(session) -> tuple[Live, dict[int, str], int]:
    """Le match en direct en cours (404 sinon), les noms des équipes et celle du joueur."""
    my_club_id = _my_club_id(session)
    if internationals.selector(session) is not None:
        live, names = load_live_test(session), NATION_NAMES
    elif heroes.hero(session) is not None and _hero_test(session) is not None:
        # Le joueur incarné joue en sélection : son équipe est sa sélection.
        live, names = load_live_test(session), NATION_NAMES
        my_club_id = live.match.hero_side().club.id
    else:
        live = load_live(session, load_clubs(session, live_club_ids(session)))
        names = _names(session)
    if live is None:
        raise HTTPException(status_code=404, detail="Aucun match en direct")
    return live, names, my_club_id


def _hero_test(session) -> LiveInternationalRow | None:
    return session.scalars(select(LiveInternationalRow)).first()


def _manager_only(live: Live) -> None:
    """Tactique, discours et changements sont l'affaire du manager, pas du joueur incarné."""
    if live.match.hero is not None:
        raise HTTPException(status_code=400, detail="C'est le staff qui gère l'équipe")


def _names(session) -> dict[int, str]:
    return dict(session.execute(select(ClubRow.id, ClubRow.name)).all())


@router.get("", response_model=LiveOut)
def get_live(session: SessionDep) -> LiveOut:
    """Le match en direct en cours, pour le reprendre là où on l'a laissé."""
    live, names, my_club_id = _load(session)
    return live_out(live, names, my_club_id)


@router.post("", response_model=LiveOut, status_code=201)
def start_live(session: SessionDep) -> LiveOut:
    """Lance le prochain match du club dirigé (ou reprend celui en cours) : celui de la
    prochaine journée de son championnat, ou de la Coupe d'Europe si elle tombe avant.

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
    if heroes.hero(session) is not None:
        # Carrière de joueur : son match en sélection, s'il tombe avant celui de son club.
        if _hero_test(session) is not None:
            existing = load_live_test(session)
            return live_out(existing, NATION_NAMES, existing.match.hero_side().club.id)
        _prepare_day(session, season)
        test = heroes.next_test(session, season)
        fixture = next_fixture(session, season)
        if test is not None and (fixture is None or test.date <= fixture.date):
            return _start_hero_test(session, season, test)
    competition.require_running(session, season)

    ignore_pending(session)
    league = focus_league(session)
    _prepare_day(session, season)
    if _phase(season, league) == "finished":
        raise HTTPException(status_code=400, detail="La saison est terminée")
    # Le match du club de la prochaine journée de son championnat, ou de la Coupe
    # d'Europe si elle tombe avant.
    match_row = next_fixture(session, season)
    if match_row is None:
        raise HTTPException(status_code=400, detail="Ton club ne joue pas cette journée")
    stage, day = Stage(match_row.stage), match_row.date
    in_cup = match_row.squad == cup.CUP_SQUAD

    # Semaine d'entraînement des clubs qui jouent ce jour-là : ceux des championnats du
    # jour et ceux de la coupe, comme pour une journée simulée.
    leagues = {m.league for m in season.matches if m.date == day and not m.is_played}
    cup_clubs = {
        club_id
        for m in season.cup_matches
        if m.date == day and not m.is_played
        for club_id in (m.home_club_id, m.away_club_id)
    }
    playing_ids = {*session.scalars(select(ClubRow.id).where(ClubRow.league.in_(leagues)))}
    playing_ids |= cup_clubs
    clubs = load_clubs(session, {*playing_ids, my_club_id})
    clubs[my_club_id].forced_starters = forced_starters(session, my_club_id)
    # Doublon : les joueurs retenus par une sélection qui joue ce jour-là manquent.
    internationals.announce_due(session, season, day)
    called_up = internationals.absentees_on(session, season, day)
    for club in clubs.values():
        internationals.rules.release(club, called_up, day)
    playing = {club_id: club for club_id, club in clubs.items() if club_id in playing_ids}
    rng = season_rng(season, day, "live")
    history = History.load(session)
    forms = {club_id: history.form(club, day) for club_id, club in playing.items()}
    # Le joueur incarné ne gère pas son club : ses blessés ne l'attendent pas.
    hero = heroes.hero_player_id(session)
    mine = run_training_week(session, playing, forms, day, rng, None if hero else my_club_id)
    session.commit()

    home, away = clubs[match_row.home_club_id], clubs[match_row.away_club_id]
    opponent = away if home.id == my_club_id else home
    opponent_tactics = staff_tactics(team_strength(opponent, day, forms[opponent.id]))
    hero_row = heroes.hero(session)
    hurt = False
    if hero is not None:
        # L'entraîneur titularise le joueur incarné s'il a sa confiance. Blessé, il ne
        # joue que s'il l'a choisi, diminué.
        team = clubs[my_club_id]
        team.forced_starters = {hero} if hero_row.trust >= hero_rules.TRUST_START else set()
        me = next((p for p in team.players if p.id == hero), None)
        if me is not None and me.is_injured(day) and hero_row.play_hurt:
            me.injury, hurt = None, True
            hero_row.hurt_match_id, hero_row.play_hurt = match_row.id, False
        mine_tactics = staff_tactics(team_strength(team, day, forms[my_club_id]))
    else:
        mine_tactics = Tactics()
    # Le public est là dès le coup d'envoi ; la billetterie de la journée le reprend.
    crowd = None
    if not match_row.neutral:
        if in_cup:
            seeding = cup.seeding(session, season, match_row.league)
        else:
            seeding = _seeding(season, league)
        fervour = history.fervour(home.id).value
        crowd = gate(home, seeding.index(home.id) + 1, len(seeding), stage.is_playoff, rng, fervour)
    live = LiveMatch(
        home,
        away,
        rng=rng,
        matchday=match_row.matchday,
        neutral=match_row.neutral,
        day=day,
        home_form=forms[home.id],
        away_form=forms[away.id],
        knockout=stage.is_playoff,
        home_tactics=opponent_tactics if home is opponent else mine_tactics,
        away_tactics=opponent_tactics if away is opponent else mine_tactics,
        auto={home.id, away.id} if hero is not None else {opponent.id},
        weather=forecast(home, day),
        crowd=crowd,
        derby=derby(names[home.id], names[away.id]) is not None,
        hero=hero,
        hero_entry=hero_rules.entry_minute(hero_row.trust) if hero_row else HERO_ENTRY_MINUTE,
        hero_confidence=hero_row.confidence if hero_row else 0.0,
        hero_hurt=hurt,
        final=stage == Stage.FINAL,
    )
    row = LiveMatchRow(
        match_id=match_row.id,
        my_injuries=[injury_row.id for injury_row, _ in mine],
        state=live.to_state(),
    )
    session.add(row)
    session.commit()
    return live_out(Live(row=row, match=live, match_row=match_row), names, my_club_id)


def _start_hero_test(session, season, test) -> LiveOut:
    """Le match en sélection du joueur incarné : les deux sélections menées par leur
    staff, ses dilemmes à lui."""
    competition.require_running(session, season)
    hero_row = heroes.hero(session)
    day = test.date
    history = History.load(session)
    teams, forms = internationals.national_teams(session, season, [test], history.appearances)
    home, away = teams[test.home_id], teams[test.away_id]
    stage = Stage(test.stage)
    live = LiveMatch(
        home,
        away,
        rng=season_rng(season, day, "live"),
        matchday=test.matchday,
        neutral=test.neutral,
        day=day,
        home_form=forms[home.id],
        away_form=forms[away.id],
        knockout=stage.is_playoff,
        home_tactics=staff_tactics(team_strength(home, day, forms[home.id])),
        away_tactics=staff_tactics(team_strength(away, day, forms[away.id])),
        auto={home.id, away.id},
        derby=derby(NATION_NAMES[home.id], NATION_NAMES[away.id]) is not None,
        hero=hero_row.player_id,
        hero_entry=hero_rules.entry_minute(hero_row.trust),
        hero_confidence=hero_row.confidence,
        final=stage == Stage.FINAL,
    )
    side = live.hero_side()
    if side is None:
        raise HTTPException(status_code=400, detail="Tu n'es pas apte pour ce match")
    row = LiveInternationalRow(match_id=test.id, state=live.to_state())
    session.add(row)
    session.commit()
    return live_out(Live(row=row, match=live, match_row=test), NATION_NAMES, side.club.id)


def _finish_hero_test(session) -> HeroDayOut:
    """Le match en sélection fini (par le staff s'il reste des minutes) : le monde joue
    jusqu'à ce jour-là compris, et le joueur en tire son expérience."""
    season = _current_or_404(session)
    test_day = session.get(InternationalRow, _hero_test(session).match_id).date
    while (day := _prepare_day(session, season)) is not None and day <= test_day:
        _play_day(session, season, day)
    reward = heroes.reward(session, season)
    session.commit()
    return HeroDayOut(season=_season_out(session, season), hero=reward)


def _start_test(session, human: SelectorRow) -> LiveOut:
    """Lance le match de la sélection du joueur (ou reprend celui en cours) : il faut
    que ce soit le prochain jour de match, et que la liste soit annoncée."""
    season = _current_or_404(session)
    my_id = NATIONS_BY_CODE[human.nation].id
    existing = load_live_test(session)
    if existing is not None:
        return live_out(existing, NATION_NAMES, my_id)
    competition.require_running(session, season)

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
        knockout=Stage(match_row.stage).is_playoff,
        home_tactics=opponent_tactics if home is opponent else Tactics(),
        away_tactics=opponent_tactics if away is opponent else Tactics(),
        auto={opponent.id},
        derby=derby(NATION_NAMES[home.id], NATION_NAMES[away.id]) is not None,
    )
    row = LiveInternationalRow(match_id=match_row.id, state=live.to_state())
    session.add(row)
    session.commit()
    return live_out(Live(row=row, match=live, match_row=match_row), NATION_NAMES, my_id)


@router.post("/advance", response_model=LiveOut)
def advance(payload: AdvanceIn, session: SessionDep) -> LiveOut:
    """Joue les minutes suivantes (une par défaut), ou jusqu'à l'entrée en jeu du joueur
    incarné (`until_entry`), et renvoie le match tel qu'il en est."""
    live, names, my_club_id = _load(session)
    if live.match.finished:
        raise HTTPException(status_code=400, detail="Le match est terminé")
    if live.match.crunch is not None:
        raise HTTPException(status_code=400, detail="Une pénalité attend ta décision")
    if live.match.dilemma is not None:
        raise HTTPException(status_code=400, detail="Une action attend ton choix")
    if payload.until_entry:
        live.match.advance_to_hero()
    else:
        live.match.advance(payload.minutes)
    live.save()
    session.commit()
    return live_out(live, names, my_club_id)


@router.post("/tactics", response_model=LiveOut)
def set_tactics(payload: TacticsIn, session: SessionDep) -> LiveOut:
    """Change la tactique du club dirigé, effective dès la minute suivante."""
    live, names, my_club_id = _load(session)
    _manager_only(live)
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


@router.post("/talk", response_model=LiveOut)
def talk(payload: TalkIn, session: SessionDep) -> LiveOut:
    """Le manager parle à son équipe : au vestiaire (avant le coup d'envoi, à la
    pause) ou du bord du terrain. L'issue est dans `talks` de son équipe."""
    live, names, my_club_id = _load(session)
    _manager_only(live)
    try:
        live.match.talk(my_club_id, payload.key)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    live.save()
    session.commit()
    return live_out(live, names, my_club_id)


@router.post("/substitute", response_model=LiveOut)
def substitute(payload: SubstituteIn, session: SessionDep) -> LiveOut:
    """Fait entrer un remplaçant du club dirigé à la place d'un joueur sur le terrain."""
    live, names, my_club_id = _load(session)
    _manager_only(live)
    try:
        live.match.substitute(my_club_id, payload.player_out, payload.player_in)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    live.save()
    session.commit()
    return live_out(live, names, my_club_id)


@router.post("/decide", response_model=LiveOut)
def decide(payload: DecideIn, session: SessionDep) -> LiveOut:
    """Le manager choisit quoi faire de la pénalité décisive : les perches, la touche,
    la mêlée ou la jouer vite. La minute se termine, et le match avec elle si c'était
    la dernière."""
    live, names, my_club_id = _load(session)
    try:
        live.match.decide(my_club_id, payload.option)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    live.save()
    session.commit()
    return live_out(live, names, my_club_id)


@router.post("/choose", response_model=LiveOut)
def choose(payload: ChooseIn, session: SessionDep) -> LiveOut:
    """Le joueur incarné tranche son dilemme : sa note bouge, le score parfois. Le
    chrono peut repartir."""
    live, names, my_club_id = _load(session)
    try:
        live.match.choose(payload.option)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    live.save()
    session.commit()
    return live_out(live, names, my_club_id)


@router.post("/finish", response_model=PlayOut | AdvanceOut | HeroDayOut)
def finish(session: SessionDep) -> PlayOut | AdvanceOut:
    """Termine la journée : le match en direct (joué jusqu'au bout par le staff s'il
    reste des minutes), puis les autres matchs, l'économie et les affaires. Même
    résultat que `POST /seasons/current/play` (ou, pour un sélectionneur, que
    `POST /selection/advance`)."""
    _load(session)
    if internationals.selector(session) is not None:
        return selection.advance(session)
    if heroes.hero(session) is not None and _hero_test(session) is not None:
        return _finish_hero_test(session)
    return play_next_matchday(session)
