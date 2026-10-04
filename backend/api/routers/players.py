"""Fiche d'un joueur."""

from fastapi import APIRouter, HTTPException
from sqlalchemy import select

from api.deps import SessionDep
from api.ledger import current_season, game_date
from api.schemas import ClubRef, InjuryOut, PeerOut, PlayerDetail, PlayerOut, PlayerSeasonStats
from engine.match_engine import (
    RATING_FOR_POSITION,
    attacking_rating,
    carrying_rating,
    defending_rating,
    lineout_rating,
    scrum_rating,
    team_strength,
)
from models import ATTRIBUTE_NAMES, EventType, Player, Squad
from models.orm import ClubRow, PlayerRow

router = APIRouter(prefix="/players", tags=["joueurs"])

# Points par type d'événement marqué, pour le total individuel.
_SCORING = {
    EventType.TRY: "tries",
    EventType.CONVERSION: "conversions",
    EventType.PENALTY_GOAL: "penalties",
    EventType.DROP_GOAL: "drops",
}


def _ratings(player: Player) -> dict[str, float]:
    return {
        "scrum": round(scrum_rating(player), 1),
        "lineout": round(lineout_rating(player), 1),
        "carrying": round(carrying_rating(player), 1),
        "attack": round(attacking_rating(player), 1),
        "defense": round(defending_rating(player), 1),
    }


def _better_than(player: Player, peers: list[Player]) -> dict[str, float]:
    """Part des pairs qu'il devance, par attribut et en note générale."""
    keys = [*ATTRIBUTE_NAMES, "overall"]
    if not peers:
        return {k: 0.0 for k in keys}
    return {
        k: sum(1 for p in peers if getattr(p, k) < getattr(player, k)) / len(peers) for k in keys
    }


def _peer_out(peer: Player) -> PeerOut:
    return PeerOut(
        id=peer.id,
        club_id=peer.club_id,
        name=peer.name,
        overall=round(peer.overall, 2),
        position_rating=round(RATING_FOR_POSITION[peer.position](peer), 1),
        **peer.attributes,
    )


def _season_stats(session, player_id: int) -> PlayerSeasonStats:
    season = current_season(session)
    stats = PlayerSeasonStats(
        year=season.year if season else None,
        matches=0,
        tries=0,
        conversions=0,
        penalties=0,
        drops=0,
        points=0,
    )
    if season is None:
        return stats
    for row in [*season.matches, *season.youth_matches]:
        match = row.to_domain()
        if not match.is_played or not match.played_by(player_id):
            continue
        stats.matches += 1
        for event in match.events:
            if event.player_id == player_id and event.type in _SCORING:
                setattr(stats, _SCORING[event.type], getattr(stats, _SCORING[event.type]) + 1)
                stats.points += event.points
    return stats


@router.get("/{player_id}", response_model=PlayerDetail)
def get_player(player_id: int, session: SessionDep) -> PlayerDetail:
    """Fiche complète d'un joueur, pro ou espoir, de n'importe quel club."""
    row = session.get(PlayerRow, player_id)
    if row is None:
        raise HTTPException(status_code=404, detail=f"Joueur {player_id} introuvable")
    day = game_date(session)
    names = {club.id: club.name for club in session.scalars(select(ClubRow))}
    player = row.to_domain()

    lineup_ids: list[int] = []
    club = None
    if row.club is not None:
        club = ClubRef(id=row.club.id, name=row.club.name)
        domain_club = row.club.to_domain()
        team = domain_club.youth_team() if player.squad == Squad.YOUTH else domain_club
        lineup_ids = [p.id for p in team_strength(team, day).lineup]

    # Les joueurs de son poste dans tout le championnat, lui compris.
    peer_rows = session.scalars(
        select(PlayerRow).where(
            PlayerRow.position == row.position,
            PlayerRow.squad == row.squad,
            PlayerRow.club_id.is_not(None),
        )
    )
    everyone = [p.to_domain() for p in peer_rows]
    others = [p for p in everyone if p.id != player.id]

    return PlayerDetail(
        player=PlayerOut.from_player(player, day, names),
        club=club,
        lineup_ids=lineup_ids,
        starter=player.id in lineup_ids,
        ratings=_ratings(player),
        position_ratings={
            position: round(rating(player), 1) for position, rating in RATING_FOR_POSITION.items()
        },
        better_than=_better_than(player, others),
        peers=[_peer_out(p) for p in everyone],
        season=_season_stats(session, player.id),
        injuries=[
            InjuryOut.from_injury(injury.to_domain(), day)
            for injury in sorted(row.injuries, key=lambda i: (i.occurred_on, i.id), reverse=True)
        ],
    )
