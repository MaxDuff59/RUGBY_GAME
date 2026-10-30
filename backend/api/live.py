"""Le match en direct du club dirigé : sauvegarde, reprise et lecture.

Le moteur (`engine.match_engine.LiveMatch`) joue minute par minute ; entre deux
requêtes, son état complet dort dans `LiveMatchRow`. Ce module le charge, le
sauvegarde et le met en forme pour l'API. La semaine d'entraînement qui précède
la journée est enregistrée ici aussi, car elle a lieu avant le coup d'envoi : la
journée (`api/routers/seasons.py`) ne la rejoue pas si un match en direct l'a
déjà faite.
"""

import random
from dataclasses import dataclass
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from api import internationals
from api.cup import CUP_SQUAD, CUPS
from api.schemas import (
    ClubRef,
    CrowdOut,
    CrunchOptionOut,
    CrunchOut,
    DilemmaOptionOut,
    DilemmaOut,
    LiveEventOut,
    LiveHeroOut,
    LiveOut,
    LivePlayerOut,
    LiveSideOut,
    OutcomeOut,
    PlayerMatchStatsOut,
    TacticsOut,
    TalkHeardOut,
    TalkOptionOut,
    TalkOut,
)
from data.derbies import derby
from engine import dilemmas, europe
from engine.form import Form
from engine.match_engine import (
    HALF_TIME,
    SLOT_NUMBERS,
    LiveMatch,
    Side,
)
from engine.matchday import training_week
from engine.team_talk import TALKS
from models import MATCH_STAT_NAMES, Club, EventType, Injury, Stage
from models.orm import (
    InjuryRow,
    InternationalRow,
    LiveInternationalRow,
    LiveMatchRow,
    MatchRow,
    SeasonRow,
)


@dataclass
class Live:
    """Un match en direct chargé : sa ligne de sauvegarde, le moteur et le match du
    calendrier (un match de clubs, ou un match international pour un sélectionneur)."""

    row: LiveMatchRow | LiveInternationalRow
    match: LiveMatch
    match_row: MatchRow | InternationalRow

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


def load_live_test(session: Session) -> Live | None:
    """Le match international que le sélectionneur joue en direct, reconstruit avec la
    liste de chaque sélection (None s'il n'y en a pas)."""
    row = session.scalars(select(LiveInternationalRow)).first()
    if row is None:
        return None
    match_row = session.get(InternationalRow, row.match_id)
    if match_row is None or match_row.is_played:
        session.delete(row)
        session.commit()
        return None
    season = session.get(SeasonRow, match_row.season_id)
    teams, _ = internationals.national_teams(session, season, [match_row], {})
    live = LiveMatch.from_state(teams[match_row.home_id], teams[match_row.away_id], row.state)
    return Live(row=row, match=live, match_row=match_row)


def live_match_row(session: Session) -> MatchRow | None:
    """Le match du calendrier joué en direct en ce moment (None s'il n'y en a pas)."""
    row = session.scalars(select(LiveMatchRow)).first()
    return session.get(MatchRow, row.match_id) if row is not None else None


def live_club_ids(session: Session) -> set[int]:
    """Les deux clubs du match en direct en cours (aucun s'il n'y en a pas)."""
    match_row = live_match_row(session)
    return {match_row.home_club_id, match_row.away_club_id} if match_row is not None else set()


def run_training_week(
    session: Session,
    clubs: dict[int, Club],
    forms: dict[int, Form],
    day: date,
    rng: random.Random,
    my_club_id: int | None,
) -> list[tuple[InjuryRow, Injury]]:
    """Semaine d'entraînement de tous les clubs, avant les matchs du jour
    (engine/matchday.py). Les blessures sont enregistrées ; celles du club dirigé
    sont renvoyées (le manager choisit leur protocole).
    """
    mine: list[tuple[InjuryRow, Injury]] = []
    ordered = sorted(clubs.values(), key=lambda club: club.id)
    for club_id, injury in training_week(ordered, forms, day, rng, my_club_id):
        injury_row = InjuryRow.from_domain(injury)
        session.add(injury_row)
        if club_id == my_club_id:
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
    stats = None
    if player.id in side.entered_at:
        line = {**dict.fromkeys(MATCH_STAT_NAMES, 0), **side.stats.get(player.id, {})}
        minutes = side.off.get(player.id, minute) - side.entered_at[player.id]
        stats = PlayerMatchStatsOut(minutes=max(0, minutes), rating=round(rating, 1), **line)
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
        stats=stats,
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
        captain_id=side.captain_id,
        strength={
            "set_piece": round(ratings.set_piece, 1),
            "pack": round(ratings.pack, 1),
            "attack": round(ratings.attack, 1),
            "defense": round(ratings.defense, 1),
        },
        spirit=round(side.spirit, 3),
        heat=round(side.heat, 2),
        talks=[TalkHeardOut(**heard.to_dict()) for heard in side.talks],
    )


def _talk_out(live: LiveMatch, club_id: int) -> TalkOut:
    """Les discours que le manager peut tenir maintenant, avec leurs chances."""
    moment = live.talk_moment(club_id)
    options = []
    if moment is not None:
        for talk in TALKS.values():
            if moment in talk.moments:
                success, backfire = live.talk_odds(club_id, talk)
                options.append(
                    TalkOptionOut(
                        key=talk.key, success=round(success, 2), backfire=round(backfire, 2)
                    )
                )
    return TalkOut(moment=moment, options=options, next_at=live.next_talk(club_id))


def _crunch_out(live: LiveMatch, club_id: int) -> CrunchOut | None:
    """Le choix crucial qui attend le manager, avec les chances de chaque voie."""
    if live.crunch is None or live.crunch.club_id != club_id:
        return None
    odds = live.penalty_odds(club_id)
    return CrunchOut(
        minute=live.crunch.minute,
        options=[
            CrunchOptionOut(key=option.value, success=round(success, 2))
            for option, success in odds.items()
        ],
        conversion=round(live.conversion_odds(club_id), 2),
    )


def _hero_out(live: LiveMatch) -> LiveHeroOut | None:
    """Le joueur incarné (carrière de joueur) et ses dilemmes déjà tranchés."""
    side = live.hero_side()
    if side is None:
        return None
    return LiveHeroOut(
        player_id=live.hero,
        club_id=side.club.id,
        outcomes=[OutcomeOut(**outcome.to_dict()) for outcome in live.outcomes],
        entry=live.hero_entry,
        confidence=round(live.hero_confidence, 2),
        hurt=live.hero_hurt,
    )


def _dilemma_out(live: LiveMatch) -> DilemmaOut | None:
    """Le dilemme qui attend le joueur incarné, avec les chances de chaque voie."""
    if live.dilemma is None:
        return None
    situation = dilemmas.SITUATIONS_BY_KEY[live.dilemma.situation]
    odds = live.dilemma_odds()
    return DilemmaOut(
        minute=live.dilemma.minute,
        situation=situation.key,
        options=[
            DilemmaOptionOut(
                key=option.key,
                success=odds[option.key],
                reward=live.dilemma_reward(option),
                cost=live.dilemma_cost(option),
            )
            for option in situation.options
        ],
        pressure=live.dilemma.pressure,
        chained=live.dilemma.chained,
    )


def live_out(live: Live, names: dict[int, str], my_club_id: int) -> LiveOut:
    match = live.match
    # Un match de sélection (`InternationalRow`) n'a pas d'effectif : jamais de coupe.
    in_cup = getattr(live.match_row, "squad", None) == CUP_SQUAD
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
        derby=derby(names[match.home.club.id], names[match.away.club.id]),
        cup=in_cup,
        competition=CUPS[live.match_row.league].short_name if in_cup else None,
        pool_rounds=europe.FORMATS[live.match_row.league].pool_rounds if in_cup else None,
        my_club_id=my_club_id,
        minute=match.minute,
        last_minute=match.last_minute,
        half_time=HALF_TIME,
        extra_time=match.extra_time,
        finished=match.finished,
        weather=match.weather,
        # Le public du moment : son ambiance suit le score.
        crowd=CrowdOut.of(match.crowd.spectators, match.atmosphere, match.mood)
        if match.crowd
        else None,
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
        momentum=match.momentum,
        talk=_talk_out(match, my_club_id),
        crunch=_crunch_out(match, my_club_id),
        hero=_hero_out(match),
        dilemma=_dilemma_out(match),
    )
