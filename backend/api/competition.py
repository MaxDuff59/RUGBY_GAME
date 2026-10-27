"""Le mode compétition : une partie où le joueur ne mène son équipe que dans une
compétition, la Coupe d'Europe (un club) ou la Coupe du monde (une sélection).

C'est une partie comme une autre, dans un emplacement, avec son monde complet : les
championnats se jouent, le joueur gère son effectif entre deux matchs. Ce qui change :

- l'équipe se choisit parmi les vrais participants : les qualifiés de la Coupe
  d'Europe tirés avec la saison, ou les seize nations de la Coupe du monde ;
- la saison d'une Coupe du monde n'a qu'elle pour calendrier international, dès la
  première saison (api/internationals.py, `ensure_calendar`) ;
- la direction ne limoge pas le manager (routers/seasons.py) ;
- la partie s'arrête au titre ou à l'élimination (`status`) : plus de journée à jouer.

Le club en Coupe d'Europe avance de match de coupe en match de coupe : l'interface
enchaîne les journées de championnat entre deux, menées par le staff.
"""

from dataclasses import dataclass

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from api import cup, internationals
from data.nations import NATIONS_BY_CODE, NATIONS_BY_ID
from engine import europe
from engine import internationals as rules
from models import Stage
from models.orm import CareerRow, ClubRow, CompetitionRow, SeasonRow

CHAMPIONS_CUP = europe.CODE
WORLD_CUP = rules.WORLD_CUP.code
NAMES = {CHAMPIONS_CUP: "Coupe d'Europe", WORLD_CUP: "Coupe du monde"}

# Jusqu'où l'équipe est allée, d'après le tour de son dernier match (perdu).
REACHED = {
    Stage.FINAL: "Finaliste",
    Stage.SEMI: "Demi-finaliste",
    Stage.QUARTER: "Quart de finaliste",
    Stage.REGULAR: "Éliminé en poules",
}
WINNER = "Vainqueur"


def current(session: Session) -> CompetitionRow | None:
    """La compétition de la partie (None : une carrière ordinaire)."""
    return session.scalars(select(CompetitionRow)).first()


def participants(session: Session, season: SeasonRow, code: str) -> list[tuple[int, str]]:
    """Les équipes de la compétition : (identifiant, nom), par ordre alphabétique."""
    if code == CHAMPIONS_CUP:
        ids = [club for clubs in cup.pools(session, season, code).values() for club in clubs]
        names = dict(session.execute(select(ClubRow.id, ClubRow.name)).all())
        teams = [(club_id, names[club_id]) for club_id in ids]
    else:
        teams = [(NATIONS_BY_CODE[c].id, NATIONS_BY_CODE[c].name) for c in rules.WORLD_CUP.nations]
    return sorted(teams, key=lambda team: team[1])


def team_id(session: Session) -> int | None:
    """L'équipe du joueur : son club, ou sa sélection."""
    career = session.scalars(select(CareerRow)).first()
    if career is not None:
        return career.club_id
    human = internationals.selector(session)
    return NATIONS_BY_CODE[human.nation].id if human is not None else None


def team_name(session: Session, team: int) -> str:
    if team in NATIONS_BY_ID:
        return NATIONS_BY_ID[team].name
    return session.get(ClubRow, team).name


@dataclass
class Status:
    """Où en est l'équipe du joueur dans sa compétition."""

    code: str
    team_id: int | None
    over: bool  # titre ou élimination : la partie s'arrête
    result: str | None  # « Vainqueur », « Demi-finaliste »... une fois la partie finie
    champion_id: int | None
    next_date: object | None  # date du prochain match de l'équipe


def status(session: Session, season: SeasonRow | None) -> Status | None:
    """Où en est la compétition (None hors du mode compétition). Les tours suivants
    prêts sont ouverts d'abord : une équipe sans match à venir est alors éliminée,
    ou championne."""
    row = current(session)
    if row is None:
        return None
    team = team_id(session)
    if season is None or team is None:
        return Status(row.code, team, False, None, None, None)
    if row.code == CHAMPIONS_CUP:
        cup.ensure_next_round(session, season)
        matches = cup.matches(season, row.code)
        champion = cup.champion(session, season, row.code)
    else:
        internationals.ensure_next_round(session, season)
        matches = [
            internationals.fixture(r)
            for r in internationals.test_rows(session, season)
            if r.competition == WORLD_CUP
        ]
        champion = rules.champion(rules.WORLD_CUP, matches)
    mine = sorted(
        (m for m in matches if team in (m.home_club_id, m.away_club_id)),
        key=lambda m: (m.date, m.id or 0),
    )
    upcoming = [m for m in mine if not m.is_played]
    if upcoming or not mine:
        date = upcoming[0].date if upcoming else None
        return Status(row.code, team, False, None, champion, date)
    result = WINNER if champion == team else REACHED.get(mine[-1].stage, "Éliminé")
    return Status(row.code, team, True, result, champion, None)


def require_running(session: Session, season: SeasonRow) -> None:
    """Refuse de jouer un jour de plus une fois la compétition finie (400)."""
    found = status(session, season)
    if found is not None and found.over:
        raise HTTPException(
            status_code=400, detail=f"{NAMES[found.code]} terminée : {found.result.lower()}"
        )
