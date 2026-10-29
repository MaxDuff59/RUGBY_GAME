"""Le match libre (api/friendly.py) : choisir deux équipes et jouer le match en direct.

`GET /friendly/teams` donne les équipes au choix, `POST /friendly` prépare l'affiche (et
remplace le match précédent). Le joueur compose son XV (`PUT /friendly/lineup`, comme
l'écran Effectif ; le staff complète), puis `POST /friendly/kickoff` lance le match.
Puis les mêmes gestes que le match en direct d'une carrière
(routers/live.py) : avancer le chrono, la tactique, le discours, les remplacements, la
pénalité décisive. `POST /friendly/finish` laisse le staff finir le match, `POST
/friendly/replay` le remet avant le coup d'envoi, mêmes équipes et même XV. Rien n'est
enregistré dans une partie : ni résultat, ni blessure, ni fatigue.

Ces routes ne demandent qu'un compte (un invité suffit), pas de partie chargée.
"""

from collections.abc import Callable

from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel

from api import friendly
from api.auth import UserDep
from api.live import Live, live_out
from api.schemas import (
    ClubDetail,
    ClubRef,
    DecideIn,
    FacilitiesOut,
    LineupIn,
    LiveOut,
    PlayerOut,
    StrengthOut,
    SubstituteIn,
    TacticsIn,
    TalkIn,
)
from engine.match_engine import Tactics, team_strength

router = APIRouter(prefix="/friendly", tags=["match libre"])


class FriendlyGroupOut(BaseModel):
    """Un championnat et ses clubs, ou les sélections nationales."""

    code: str
    name: str
    teams: list[ClubRef]


class FriendlyIn(BaseModel):
    home_id: int
    away_id: int
    # L'équipe que dirige le joueur ; l'autre est confiée à son staff.
    my_id: int


class AdvanceIn(BaseModel):
    minutes: int = 1


class FriendlyTeamOut(BaseModel):
    """L'affiche préparée, et l'équipe du joueur telle que le coup d'envoi l'alignerait."""

    home: ClubRef
    away: ClubRef
    started: bool
    team: ClubDetail


@router.get("/teams", response_model=list[FriendlyGroupOut])
def teams(user: UserDep) -> list[FriendlyGroupOut]:
    """Les équipes au choix : les clubs de chaque championnat, puis les sélections.
    Le premier appel crée le monde de référence (quelques secondes)."""
    with friendly.reference() as session:
        return [
            FriendlyGroupOut(
                code=group.code,
                name=group.name,
                teams=[ClubRef(id=team_id, name=name) for team_id, name in group.teams],
            )
            for group in friendly.groups(session)
        ]


@router.get("", response_model=LiveOut)
def get_friendly(user: UserDep) -> LiveOut:
    """Le match libre en cours, pour le reprendre là où on l'a laissé (404 sinon)."""
    return _act(user, lambda live: None, save=False)


@router.post("", response_model=FriendlyTeamOut, status_code=201)
def prepare_friendly(payload: FriendlyIn, user: UserDep) -> FriendlyTeamOut:
    """Prépare un match libre entre deux équipes, club contre club, sélection contre
    sélection, ou club contre sélection ; le coup d'envoi attend la composition."""
    with friendly.reference() as session:
        try:
            row = friendly.prepare(
                session, user.id, payload.home_id, payload.away_id, payload.my_id
            )
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        return _team_out(session, row)


@router.get("/team", response_model=FriendlyTeamOut)
def get_team(user: UserDep) -> FriendlyTeamOut:
    """L'affiche préparée et l'équipe du joueur (404 sans match libre)."""
    with friendly.reference() as session:
        return _team_out(session, _setup_or_404(user))


@router.put("/lineup", response_model=FriendlyTeamOut)
def set_lineup(payload: LineupIn, user: UserDep) -> FriendlyTeamOut:
    """Le XV voulu : un joueur (ou null) par place, dans l'ordre de `lineup_ids`."""
    with friendly.reference() as session:
        try:
            row = friendly.set_lineup(session, _setup_or_404(user), payload.player_ids)
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        return _team_out(session, row)


@router.delete("/lineup", response_model=FriendlyTeamOut)
def reset_lineup(user: UserDep) -> FriendlyTeamOut:
    """Rend la composition au staff."""
    with friendly.reference() as session:
        try:
            row = friendly.set_lineup(session, _setup_or_404(user), [])
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        return _team_out(session, row)


@router.post("/kickoff", response_model=LiveOut, status_code=201)
def kick_off(user: UserDep) -> LiveOut:
    """Coup d'envoi du match préparé, avec le XV composé (ou celui du staff)."""
    with friendly.reference() as session:
        live = friendly.kick_off(session, _setup_or_404(user))
        return live_out(live, friendly.names(session), live.row.my_id)


@router.post("/replay", response_model=FriendlyTeamOut)
def replay(user: UserDep) -> FriendlyTeamOut:
    """Rejoue le match : mêmes équipes, même XV, de retour avant le coup d'envoi."""
    with friendly.reference() as session:
        row = friendly.replay(user.id)
        if row is None:
            raise HTTPException(status_code=404, detail="Aucun match libre en cours")
        return _team_out(session, row)


def _setup_or_404(user) -> friendly.FriendlyRow:
    row = friendly.setup(user.id)
    if row is None:
        raise HTTPException(status_code=404, detail="Aucun match libre en cours")
    return row


def _team_out(session, row: friendly.FriendlyRow) -> FriendlyTeamOut:
    team = friendly.my_team(session, row)
    known = friendly.names(session)
    return FriendlyTeamOut(
        home=ClubRef(id=row.home_id, name=known[row.home_id]),
        away=ClubRef(id=row.away_id, name=known[row.away_id]),
        started=row.started,
        team=ClubDetail(
            id=team.id,
            name=team.name,
            balance=0,
            facilities=FacilitiesOut.model_validate(team.facilities),
            strength=StrengthOut.from_team(team_strength(team, row.date)),
            players=[PlayerOut.from_player(player, row.date, known) for player in team.players],
            lineup_custom=any(player_id is not None for player_id in team.lineup_choice),
        ),
    )


@router.delete("", status_code=204)
def drop_friendly(user: UserDep) -> Response:
    """Oublie le match libre en cours."""
    friendly.drop(user.id)
    return Response(status_code=204)


@router.post("/advance", response_model=LiveOut)
def advance(payload: AdvanceIn, user: UserDep) -> LiveOut:
    """Joue les minutes suivantes (une par défaut)."""

    def play(live: Live) -> None:
        if live.match.finished:
            raise ValueError("Le match est terminé")
        if live.match.crunch is not None:
            raise ValueError("Une pénalité attend ta décision")
        live.match.advance(max(1, payload.minutes))

    return _act(user, play)


@router.post("/tactics", response_model=LiveOut)
def set_tactics(payload: TacticsIn, user: UserDep) -> LiveOut:
    """Change la tactique de l'équipe du joueur, dès la minute suivante."""

    def change(live: Live) -> None:
        current = live.match.side(live.row.my_id).tactics
        live.match.set_tactics(
            live.row.my_id,
            Tactics(
                game_plan=payload.game_plan or current.game_plan,
                defence=payload.defence or current.defence,
                penalties=payload.penalties or current.penalties,
            ),
        )

    return _act(user, change)


@router.post("/talk", response_model=LiveOut)
def talk(payload: TalkIn, user: UserDep) -> LiveOut:
    """Le joueur parle à son équipe (vestiaire, mi-temps, bord du terrain)."""
    return _act(user, lambda live: live.match.talk(live.row.my_id, payload.key))


@router.post("/substitute", response_model=LiveOut)
def substitute(payload: SubstituteIn, user: UserDep) -> LiveOut:
    """Fait entrer un remplaçant de l'équipe du joueur."""
    return _act(
        user,
        lambda live: live.match.substitute(live.row.my_id, payload.player_out, payload.player_in),
    )


@router.post("/decide", response_model=LiveOut)
def decide(payload: DecideIn, user: UserDep) -> LiveOut:
    """Le joueur choisit quoi faire de la pénalité décisive."""
    return _act(user, lambda live: live.match.decide(live.row.my_id, payload.option))


@router.post("/finish", response_model=LiveOut)
def finish(user: UserDep) -> LiveOut:
    """Le staff joue la fin du match, banc et pénalités décisives compris."""

    def hand_over(live: Live) -> None:
        live.match.auto = {live.match.home.club.id, live.match.away.club.id}
        live.match.play_to_end()

    return _act(user, hand_over)


def _act(user, action: Callable[[Live], object], save: bool = True) -> LiveOut:
    """Charge le match libre du compte (404 sans match), lui applique `action` (une
    ValueError devient une 400), l'enregistre et le renvoie tel qu'il en est."""
    with friendly.reference() as session:
        live = friendly.load(session, user.id)
        if live is None:
            raise HTTPException(status_code=404, detail="Aucun match libre en cours")
        try:
            action(live)
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        if save:
            friendly.save(live)
        return live_out(live, friendly.names(session), live.row.my_id)
