"""Centre de formation du club dirigé : espoirs, leur championnat, promotions et rétrogradations.

Les espoirs jouent leur propre championnat (mêmes affiches que les pros, le même
jour). Un espoir peut être promu dans l'effectif pro à tout moment ; un pro de
23 ans ou moins peut redescendre chez les espoirs. À l'intersaison, les espoirs
de 22 ans non promus quittent le centre, et de nouveaux jeunes entrent (d'autant
plus que le centre est bon).
"""

from fastapi import APIRouter, HTTPException
from sqlalchemy.orm import Session

from api.deps import SessionDep, load_my_club_row
from api.jokers import joker_ids, squad_count
from api.ledger import current_season, game_date
from api.schemas import AcademyOverview, PlayerOut, StandingOut, StrengthOut
from engine.economy import SQUAD_MAX, SQUAD_MIN, wage_for
from engine.match_engine import team_strength
from engine.offseason import youth_intake_size
from engine.season import record_result
from models import YOUTH_EXIT_AGE, YOUTH_MAX_AGE, Season, Squad
from models.orm import ClubRow, PlayerRow, SeasonRow

router = APIRouter(prefix="/academy", tags=["formation"])


def _overview(session: Session, me: ClubRow) -> AcademyOverview:
    from api.routers.seasons import _club_rows, _matchday_out, _summary

    session.expire_all()
    club = me.to_domain()
    day = game_date(session)
    club_rows = _club_rows(session)
    clubs = {row.id: row.to_domain() for row in club_rows}
    names = {row.id: row.name for row in club_rows}

    # Championnat espoirs : celui du championnat pro du club.
    season: SeasonRow | None = current_season(session)
    rows = sorted(
        (m for m in (season.youth_matches if season else []) if m.league == me.league),
        key=lambda m: (m.matchday, m.id),
    )
    league_clubs = [c for c in clubs.values() if c.league == me.league]
    table = Season(year=season.year if season else 0, clubs=league_clubs)
    for row in rows:
        if row.is_played:
            match = row.to_domain()
            table.matches.append(match)
            record_result(table, match)
    standings = [
        StandingOut(
            rank=rank,
            club_id=line.club_id,
            club_name=names[line.club_id],
            played=line.played,
            won=line.won,
            drawn=line.drawn,
            lost=line.lost,
            points_for=line.points_for,
            points_against=line.points_against,
            points_difference=line.points_difference,
            tries_for=line.tries_for,
            offensive_bonus=line.offensive_bonus,
            defensive_bonus=line.defensive_bonus,
            league_points=line.league_points,
        )
        for rank, line in enumerate(table.table(), start=1)
    ]

    unplayed = [m for m in rows if not m.is_played]
    played = [m for m in rows if m.is_played]
    next_matchday = last_matchday = None
    if unplayed:
        first = unplayed[0].matchday
        next_matchday = _matchday_out([m for m in unplayed if m.matchday == first], names)
    if played:
        last = played[-1].matchday
        last_matchday = _matchday_out([m for m in played if m.matchday == last], names)

    return AcademyOverview(
        academy_level=club.facilities.academy_level,
        intake_per_year=youth_intake_size(club.facilities.academy_level),
        youth_max_age=YOUTH_MAX_AGE,
        youth_exit_age=YOUTH_EXIT_AGE,
        squad_size=squad_count(session, me),
        squad_min=SQUAD_MIN,
        squad_max=SQUAD_MAX,
        youths=[PlayerOut.from_player(p, day) for p in club.youths],
        eligible_pros=[
            PlayerOut.from_player(p, day, names)
            for p in club.players
            if p.age <= YOUTH_MAX_AGE and p.loaned_from is None
        ],
        strength=StrengthOut.from_team(team_strength(club.youth_team())),
        standings=standings,
        matches=[_summary(m, names) for m in rows],
        next_matchday=next_matchday,
        last_matchday=last_matchday,
    )


@router.get("", response_model=AcademyOverview)
def get_academy(session: SessionDep) -> AcademyOverview:
    """Espoirs du club dirigé, leur championnat, et les pros qui pourraient redescendre."""
    return _overview(session, load_my_club_row(session))


def _my_player(session: Session, me: ClubRow, player_id: int, squad: Squad) -> PlayerRow:
    row = session.get(PlayerRow, player_id)
    if row is None or row.club_id != me.id or row.squad != squad.value:
        where = "chez tes espoirs" if squad == Squad.YOUTH else "dans ton effectif pro"
        raise HTTPException(status_code=404, detail=f"Ce joueur n'est pas {where}")
    return row


@router.post("/promote/{player_id}", response_model=AcademyOverview)
def promote(player_id: int, session: SessionDep) -> AcademyOverview:
    """Fait passer un espoir chez les pros, avec un salaire de pro."""
    me = load_my_club_row(session)
    row = _my_player(session, me, player_id, Squad.YOUTH)
    if squad_count(session, me) >= SQUAD_MAX:
        raise HTTPException(status_code=400, detail=f"Effectif pro complet ({SQUAD_MAX} joueurs)")
    row.squad = Squad.PRO.value
    row.wage = wage_for(row.to_domain())
    session.commit()
    return _overview(session, me)


@router.post("/demote/{player_id}", response_model=AcademyOverview)
def demote(player_id: int, session: SessionDep) -> AcademyOverview:
    """Redescend un pro de 23 ans ou moins chez les espoirs (salaire inchangé)."""
    me = load_my_club_row(session)
    row = _my_player(session, me, player_id, Squad.PRO)
    if row.age > YOUTH_MAX_AGE:
        raise HTTPException(
            status_code=400, detail=f"Trop âgé pour les espoirs ({YOUTH_MAX_AGE} ans au plus)"
        )
    if row.loaned_from is not None:
        raise HTTPException(status_code=400, detail="Un joueur prêté reste chez les pros")
    if row.id in joker_ids(session, me.id):
        raise HTTPException(status_code=400, detail="Un joker médical reste chez les pros")
    if squad_count(session, me) <= SQUAD_MIN:
        raise HTTPException(
            status_code=400, detail=f"Effectif pro minimum atteint ({SQUAD_MIN} joueurs)"
        )
    row.squad = Squad.YOUTH.value
    session.commit()
    return _overview(session, me)
