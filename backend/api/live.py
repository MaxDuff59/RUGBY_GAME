"""Le match en direct du club dirigé : sauvegarde, reprise et lecture.

Le moteur (`engine.match_engine.LiveMatch`) joue minute par minute ; entre deux
requêtes, son état complet dort dans `LiveMatchRow`. Ce module le charge, le
sauvegarde et le met en forme pour l'API. La semaine d'entraînement qui précède
la journée est jouée ici aussi, car elle a lieu avant le coup d'envoi : la
journée (`api/routers/seasons.py`) ne la rejoue pas si un match en direct l'a
déjà faite.
"""

import random
from dataclasses import dataclass
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from api.schemas import (
    ClubRef,
    LiveEventOut,
    LiveOut,
    LivePlayerOut,
    LiveSideOut,
    TacticsOut,
)
from engine.form import Form
from engine.match_engine import (
    HALF_TIME,
    SLOT_NUMBERS,
    LiveMatch,
    Side,
)
from engine.medical import training_injuries
from models import Club, EventType, Injury, Stage
from models.orm import InjuryRow, LiveMatchRow, MatchRow


@dataclass
class Live:
    """Un match en direct chargé : sa ligne de sauvegarde, le moteur et le match du calendrier."""

    row: LiveMatchRow
    match: LiveMatch
    match_row: MatchRow

    def save(self) -> None:
        self.row.state = self.match.to_state()


def load_live(session: Session, clubs: dict[int, Club]) -> Live | None:
    """Le match en direct en cours, reconstruit avec les clubs fournis (None s'il n'y en a pas)."""
    row = session.scalars(select(LiveMatchRow)).first()
    if row is None:
        return None
    match_row = session.get(MatchRow, row.match_id)
    if match_row is None or match_row.is_played:
        # Match déjà joué par ailleurs : la sauvegarde ne sert plus.
        session.delete(row)
        session.commit()
        return None
    live = LiveMatch.from_state(
        clubs[match_row.home_club_id], clubs[match_row.away_club_id], row.state
    )
    return Live(row=row, match=live, match_row=match_row)


def run_training_week(
    session: Session,
    clubs: dict[int, Club],
    forms: dict[int, Form],
    day: date,
    rng: random.Random,
    my_club_id: int | None,
) -> list[tuple[InjuryRow, Injury]]:
    """Semaine d'entraînement de tous les clubs, avant les matchs du jour.

    Un blessé à l'entraînement manque le match du jour ; les joueurs fatigués se
    blessent plus. Les blessures sont enregistrées ; celles du club dirigé sont
    renvoyées (le manager choisit leur protocole).
    """
    mine: list[tuple[InjuryRow, Injury]] = []
    for club in clubs.values():
        risk = forms[club.id].injury_weight
        for injury in training_injuries(club, day, rng, club.id != my_club_id, risk):
            injury_row = InjuryRow.from_domain(injury)
            session.add(injury_row)
            if club.id == my_club_id:
                mine.append((injury_row, injury))
    return mine


# --- Mise en forme ----------------------------------------------------------------------


def _player_out(side: Side, index: int, minute: int) -> LivePlayerOut:
    """Le joueur d'indice `index` de la feuille de match (titulaires puis banc)."""
    player = [*side.lineup, *side.bench][index]
    slot = side.slot_of(player.id)
    slot_index = side.slots.index(slot) if slot is not None else None
    if player.id in side.reds:
        status = "sent_off"
    elif player.id in side.injured:
        status = "injured"
    elif slot is not None and not slot.present(minute):
        status = "sin_bin"
    elif slot is not None:
        status = "field"
    elif player.id in side.off:
        status = "replaced"
    else:
        status = "bench"
    rating = side.ratings.get(player.id)
    return LivePlayerOut(
        id=player.id,
        name=player.name,
        last_name=player.last_name,
        position=player.position,
        number=index + 1,
        slot_number=SLOT_NUMBERS[slot_index] if slot_index is not None else None,
        slot=slot.position if slot is not None else None,
        status=status,
        rating=round(rating, 1) if rating is not None else None,
        yellow=side.yellows.get(player.id, 0),
        red=player.id in side.reds,
        since=side.entered_at.get(player.id),
        until=side.off.get(player.id),
        back_at=slot.absent_until if status == "sin_bin" else None,
        overall=round(player.overall, 1),
        kicking=player.kicking,
        energy=round(side.energy(player), 2),
    )


def _side_out(live: LiveMatch, side: Side, name: str) -> LiveSideOut:
    minute = live.minute
    club_id = side.club.id
    ratings = side.collective(minute)
    kicker = side.kicker(minute)
    shootout = None
    if any(e.type in (EventType.SHOOTOUT_GOAL, EventType.SHOOTOUT_MISSED) for e in live.events):
        shootout = sum(
            1 for e in live.events if e.club_id == club_id and e.type == EventType.SHOOTOUT_GOAL
        )
    return LiveSideOut(
        club=ClubRef(id=club_id, name=name),
        score=live.score(club_id),
        tries=sum(1 for e in live.events if e.club_id == club_id and e.type == EventType.TRY),
        shootout=shootout,
        tactics=TacticsOut(**side.tactics.to_dict()),
        players=[_player_out(side, i, minute) for i in range(len(side.lineup) + len(side.bench))],
        substitutions_left=side.substitutions_left(),
        missing=side.missing(minute),
        kicker_id=kicker.id if kicker else None,
        strength={
            "set_piece": round(ratings.set_piece, 1),
            "pack": round(ratings.pack, 1),
            "attack": round(ratings.attack, 1),
            "defense": round(ratings.defense, 1),
        },
    )


def live_out(live: Live, names: dict[int, str], my_club_id: int) -> LiveOut:
    match = live.match
    players = {**match.home.players(), **match.away.players()}

    def name_of(player_id: int | None) -> str | None:
        player = players.get(player_id) if player_id is not None else None
        return player.name if player else None

    return LiveOut(
        match_id=live.match_row.id,
        matchday=live.match_row.matchday,
        stage=Stage(live.match_row.stage),
        date=live.match_row.date,
        neutral=live.match_row.neutral,
        knockout=match.knockout,
        my_club_id=my_club_id,
        minute=match.minute,
        last_minute=match.last_minute,
        half_time=HALF_TIME,
        extra_time=match.extra_time,
        finished=match.finished,
        home=_side_out(match, match.home, names[match.home.club.id]),
        away=_side_out(match, match.away, names[match.away.club.id]),
        events=[
            LiveEventOut(
                minute=e.minute,
                type=e.type,
                club_id=e.club_id,
                player_id=e.player_id,
                player_name=name_of(e.player_id),
                other_player_id=e.other_player_id,
                other_player_name=name_of(e.other_player_id),
                points=e.points,
            )
            for e in match.events
        ],
    )
