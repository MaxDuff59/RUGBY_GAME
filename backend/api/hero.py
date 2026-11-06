"""Carrière de joueur (engine/hero.py) : le joueur incarné, son club, sa progression.

Le joueur est un joueur du monde comme un autre (`PlayerRow`), suivi par `HeroRow`.
Son club, comme tous les autres, est mené par son staff : il n'y a ni `CareerRow` ni
`SelectorRow`. Le club suivi par le calendrier et les journées
(api/routers/seasons.py) est le sien, où qu'il joue (prêt, transfert).

Après chaque journée de son club, il gagne de l'expérience (`reward`) ; il ne
progresse pas tout seul (api/routers/seasons.py l'écarte de la progression des
autres). Le club le garde sous contrat d'une saison à l'autre (`keep_signed`).
"""

import datetime
import random
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from api import cup, internationals
from api.deps import load_club
from api.ledger import game_date
from api.moves import delete_player, log_move
from api.schemas import (
    ClubRef,
    CoachNoteOut,
    HeroAttributeOut,
    HeroAwardOut,
    HeroCareerOut,
    HeroMatchOut,
    HeroOut,
    HeroRewardOut,
    HeroSeasonOut,
    HeroTestOut,
    HeroTitleOut,
    SocialOut,
    SocialPostOut,
)
from data.leagues import league_config
from data.nations import NATIONS_BY_CODE, NATIONS_BY_ID, WINDOWS_BY_CODE, WORLD_CUP
from engine import dilemmas, social
from engine import hero as rules
from engine.freshness import daily_recovery, player_freshness
from engine.journal import MoveKind
from engine.match_engine import FORMATION, MATCH_MINUTES, RATING_FOR_POSITION, select_lineup
from engine.season import champion
from models import (
    ATTRIBUTE_NAMES,
    OVERALL_WEIGHTS,
    Club,
    EventType,
    Position,
    StaffRole,
    Stage,
)
from models.orm import (
    AwardRow,
    ClubRow,
    HeroRow,
    InjuryRow,
    InternationalRow,
    MatchRow,
    PlayerRow,
    SeasonRow,
)

# Ce que l'entraîneur a dit dernièrement au joueur : les plus récents seulement.
COACH_NOTES_KEPT = 5


def hero(session: Session) -> HeroRow | None:
    """La carrière de joueur en cours (None : une autre carrière, ou aucune)."""
    return session.scalars(select(HeroRow)).first()


def hero_club_id(session: Session) -> int | None:
    """Le club du joueur incarné (None hors carrière de joueur, ou s'il a raccroché)."""
    row = hero(session)
    if row is None:
        return None
    return session.get(PlayerRow, row.player_id).club_id


def hero_player_id(session: Session) -> int | None:
    row = hero(session)
    return row.player_id if row is not None else None


def keep_signed(session: Session, season_year: int) -> None:
    """Le club garde le joueur incarné : jamais en dernière année de contrat (ni libéré
    à l'intersaison, ni approché par un concurrent)."""
    row = hero(session)
    if row is None:
        return
    player = session.get(PlayerRow, row.player_id)
    player.contract_until = max(player.contract_until, season_year + rules.START_CONTRACT_YEARS)


def record_moments(session: Session, match_id: int, outcomes: list) -> None:
    """Garde les actions du joueur incarné dans un match joué en direct."""
    row = hero(session)
    if row is None or not outcomes:
        return
    row.moments = {**(row.moments or {}), str(match_id): [o.to_dict() for o in outcomes]}


def _club_matches(season: SeasonRow, club_id: int) -> list[MatchRow]:
    return [
        m
        for m in [*season.matches, *season.cup_matches]
        if m.is_played and club_id in (m.home_club_id, m.away_club_id)
    ]


def _match_out(row: MatchRow, player_id: int, club_id: int, names: dict[int, str]) -> HeroMatchOut:
    """Un match vu du club du joueur (`club_id` ; s'il en a changé depuis, celui de sa
    feuille de match)."""
    if club_id in (row.home_club_id, row.away_club_id):
        is_home = club_id == row.home_club_id
    else:
        is_home = player_id in (row.home_lineup or [])
    line = (row.stats or {}).get(str(player_id), {})
    opponent = row.away_club_id if is_home else row.home_club_id
    tries = sum(
        1
        for e in row.events or []
        if e.get("type") == EventType.TRY.value and e.get("player_id") == player_id
    )
    return HeroMatchOut(
        match_id=row.id,
        date=row.date,
        opponent=ClubRef(id=opponent, name=names[opponent]),
        home=is_home,
        score_for=row.home_score if is_home else row.away_score,
        score_against=row.away_score if is_home else row.home_score,
        minutes=line.get("minutes", 0),
        rating=line.get("rating"),
        tries=tries,
    )


def reward(session: Session, season: SeasonRow) -> HeroRewardOut | None:
    """L'expérience des journées de son club pas encore comptées : l'entraînement de la
    semaine, et le match s'il l'a joué. Les points gagnés s'ajoutent à placer."""
    row = hero(session)
    club_id = hero_club_id(session)
    if row is None or club_id is None:
        return None
    done = set(row.rewarded or [])
    fresh = [m for m in _club_matches(season, club_id) if m.id not in done]
    xp = _reward_tests(row)
    if not fresh and not xp:
        return None
    names = dict(session.execute(select(ClubRow.id, ClubRow.name)).all())
    last = None
    for match_row in sorted(fresh, key=lambda m: (m.date, m.id)):
        line = (match_row.stats or {}).get(str(row.player_id), {})
        xp += rules.TRAINING_XP + rules.match_xp(line.get("minutes", 0), line.get("rating"))
        if line.get("minutes", 0) > 0:
            last = _match_out(match_row, row.player_id, club_id, names)
        _after_match(session, row, match_row, line)
    total = row.xp + xp
    points = total // rules.XP_PER_POINT
    row.xp = total % rules.XP_PER_POINT
    row.points += points
    row.rewarded = sorted(done | {m.id for m in fresh})
    out = HeroRewardOut(match=last, xp=xp, points=points)
    row.last_reward = out.model_dump(mode="json")
    return out


def _note(row: HeroRow, day, kind: str) -> None:
    """Ce que l'entraîneur dit au joueur ; les plus récents d'abord, les derniers seulement."""
    row.coach_notes = [{"date": day.isoformat(), "kind": kind}, *(row.coach_notes or [])][
        :COACH_NOTES_KEPT
    ]


def _after_match(session: Session, row: HeroRow, match_row: MatchRow, line: dict) -> None:
    """Après un match de son club : sa confiance, celle de l'entraîneur, ce que celui-ci
    lui en dit, et la blessure s'il a joué diminué."""
    played = line.get("minutes", 0) > 0
    rating = line.get("rating") if played else None
    carded = any(
        e.get("type") in (EventType.YELLOW_CARD.value, EventType.RED_CARD.value)
        and e.get("player_id") == row.player_id
        for e in match_row.events or []
    )
    moments = (row.moments or {}).get(str(match_row.id), [])
    risky = sum(
        1
        for m in moments
        if not m["success"]
        and m["option"] != dilemmas.safest(dilemmas.SITUATIONS_BY_KEY[m["situation"]]).key
    )
    before = row.trust
    row.confidence = rules.next_confidence(row.confidence, rating)
    row.trust = rules.next_trust(row.trust, rating, carded, risky)
    if carded:
        _note(row, match_row.date, "card")
    elif risky >= rules.RISKY_FAILURES:
        _note(row, match_row.date, "risks")
    elif rating is not None and rating >= rules.PRAISE_FROM:
        _note(row, match_row.date, "praise")
    if before < rules.TRUST_START <= row.trust:
        _note(row, match_row.date, "starter")
    elif before >= rules.ENTRY_BY_TRUST[1][0] > row.trust:
        _note(row, match_row.date, "doubt")
    elif before >= rules.TRUST_KEEP_PLACE > row.trust:
        _note(row, match_row.date, "dropped")

    if row.hurt_match_id == match_row.id:
        # Il a joué blessé : la blessure peut s'aggraver.
        row.hurt_match_id = None
        rng = random.Random(f"aggravation:{match_row.id}:{row.player_id}")
        injury = session.scalars(
            select(InjuryRow)
            .where(InjuryRow.player_id == row.player_id)
            .order_by(InjuryRow.return_date.desc())
        ).first()
        if injury is not None and rng.random() < rules.AGGRAVATION_CHANCE:
            weeks = rng.randint(*rules.AGGRAVATION_WEEKS)
            injury.return_date += datetime.timedelta(weeks=weeks)
            _note(row, match_row.date, "aggravated")
        else:
            _note(row, match_row.date, "brave")


def train(session: Session, attribute: str) -> None:
    """Place des points dans un attribut (ValueError si impossible)."""
    row = hero(session)
    if attribute not in ATTRIBUTE_NAMES:
        raise ValueError(f"Attribut « {attribute} » inconnu")
    player = session.get(PlayerRow, row.player_id)
    price = rules.cost(getattr(player, attribute))
    if price is None:
        raise ValueError("Cet attribut est déjà au maximum")
    if row.points < price:
        raise ValueError(f"Il faut {price} point{'s' if price > 1 else ''} pour cet attribut")
    row.points -= price
    setattr(player, attribute, getattr(player, attribute) + 1)


@dataclass(frozen=True)
class LineupCall:
    """Ce que décide l'entraîneur pour le prochain match du joueur incarné."""

    chance: float  # ses chances d'être titulaire, de 0 à 1 (engine/hero.py)
    starts: bool  # titulaire (sinon sur le banc)
    first_choice: bool  # titulaire d'office : s'il ne l'est pas, il souffle
    dropped: bool  # le meilleur à son poste, mis sur le banc après ses mauvais matchs


def lineup_call(
    session: Session,
    season: SeasonRow | None,
    club: Club,
    player_id: int,
    trust: float,
    fixture: MatchRow | None,
) -> LineupCall:
    """Titulaire ou remplaçant au match `fixture` de son club (None : aucun en vue, il
    est titulaire s'il l'est d'office). Le tirage tient au match : la fiche annonce ce
    que fera le coup d'envoi (api/routers/live.py)."""
    day = fixture.date if fixture is not None else game_date(session)
    me = next(p for p in club.players if p.id == player_id)
    club.forced_starters, club.rested = set(), set()
    best = any(p.id == player_id for p in select_lineup(club, day))
    dropped = best and trust < rules.TRUST_KEEP_PLACE
    first_choice = trust >= rules.TRUST_START or (best and not dropped)
    rating = RATING_FOR_POSITION[me.position]
    ahead = sum(1 for p in club.players if p.position == me.position and rating(p) > rating(me))
    behind = ahead + 1 - FORMATION[Position(me.position)]
    chance = rules.start_chance(
        first_choice,
        trust,
        _freshness(session, season, club, player_id, day),
        behind,
        fixture is not None and Stage(fixture.stage).is_playoff,
    )
    if fixture is None:
        starts = first_choice
    else:
        starts = random.Random(f"rotation:{fixture.id}:{player_id}").random() < chance
    return LineupCall(chance=chance, starts=starts, first_choice=first_choice, dropped=dropped)


def _freshness(
    session: Session, season: SeasonRow | None, club: Club, player_id: int, day: datetime.date
) -> float:
    """Sa fraîcheur sur 20 (engine/freshness.py) : ses titularisations de la saison, en
    club et en sélection."""
    if season is None:
        return rules.FRESHNESS_FULL
    tests = internationals.test_rows(session, season)
    starts = [
        m.date
        for m in [*season.matches, *season.cup_matches, *tests]
        if m.home_score is not None
        and player_id in [*(m.home_lineup or []), *(m.away_lineup or [])]
    ]
    rate = daily_recovery(club.staff_level(StaffRole.FITNESS_COACH))
    return player_freshness(starts, day, rate)


def _national_chance(
    session: Session, season: SeasonRow | None, player, club_name: str | None, listed: bool
) -> tuple[str | None, bool, float | None]:
    """Son pays, s'il peut y être retenu, et ses chances d'être sur sa prochaine liste
    (engine/hero.py) ; (None, False, None) si son pays ne joue pas dans ce monde."""
    nation = NATIONS_BY_CODE.get(player.nationality)
    if (
        nation is None
        or nation not in internationals.rules.participants()
        or not internationals.has_nations(session)
    ):
        return None, False, None
    if not internationals.rules.is_eligible(player, nation, club_name):
        return nation.name, False, 0.0
    if listed:
        return nation.name, True, 1.0
    # Le staff classe un poste comme pour sa liste : note, forme, temps de jeu, continuité.
    pool = internationals.eligible_players(session, {nation.code})[nation.code]
    found = internationals.records(session, season, pool, nation.code)

    def score(p) -> float:
        return internationals.rules.selection_score(p, found.get(p.id))

    rivals = sorted(
        (score(p) for p in pool if p.position == player.position and p.id != player.id),
        reverse=True,
    )
    quota = internationals.rules.SQUAD_QUOTA[Position(player.position)]
    if len(rivals) < quota:
        return nation.name, True, rules.SELECTION_BOUNDS[1]
    me = next((p for p in pool if p.id == player.id), player)
    return nation.name, True, rules.call_up_chance(score(me) - rivals[quota - 1])


def hero_out(session: Session, season: SeasonRow | None) -> HeroOut:
    row = hero(session)
    player_row = session.get(PlayerRow, row.player_id)
    player = player_row.to_domain()
    position = Position(player.position)
    weights = OVERALL_WEIGHTS[position]
    attributes = [
        HeroAttributeOut(
            key=name,
            value=getattr(player, name),
            cost=rules.cost(getattr(player, name)),
            weight=weights.get(name, 0.0),
        )
        for name in ATTRIBUTE_NAMES
    ]
    club_ref = league_name = None
    status, rank, at_position, injury_weeks = "retired", 1, 1, 0
    first_choice = dropped = False
    matches: list[HeroMatchOut] = []
    if player.club_id is not None:
        # api/routers/seasons.py importe ce module : son prochain match se lit ici.
        from api.routers.seasons import next_fixture

        club = load_club(session, player.club_id)
        club_ref = ClubRef(id=club.id, name=club.name)
        league_name = league_config(club.league).name
        day = game_date(session)
        me = next((p for p in club.players if p.id == player.id), player)
        injury_weeks = me.injury.weeks_left(day) if me.is_injured(day) else 0
        if me.is_injured(day):
            status = "injured"
        elif me.is_suspended:
            status = "suspended"
        else:
            fixture = next_fixture(session, season) if season is not None else None
            if fixture is not None:
                # Doublon : comme au coup d'envoi, ses coéquipiers en sélection manquent.
                away = internationals.absentees_on(session, season, fixture.date)
                internationals.rules.release(club, away, fixture.date)
            call = lineup_call(session, season, club, player.id, row.trust, fixture)
            status = "starter" if call.starts else "bench"
            first_choice, dropped = call.first_choice, call.dropped and not call.starts
        rating = RATING_FOR_POSITION[position]
        rivals = sorted(
            (p for p in club.players if p.position == position), key=rating, reverse=True
        )
        rank = next((i for i, p in enumerate(rivals, start=1) if p.id == player.id), len(rivals))
        at_position = len(rivals)
        if season is not None:
            names = dict(session.execute(select(ClubRow.id, ClubRow.name)).all())
            played = [
                m
                for m in season.matches + season.cup_matches
                if m.is_played and str(player.id) in (m.stats or {})
            ]
            # Ses matchs en sélection s'y glissent à leur date.
            matches = sorted(
                [
                    *(_match_out(m, player.id, club.id, names) for m in played),
                    *season_tests(session, season, row),
                ],
                key=lambda m: (m.date, m.international, m.match_id),
                reverse=True,
            )
    test = called_up(session, season) if player.club_id is not None else None
    nation, eligible, call_up_chance = (
        _national_chance(session, season, player, club_ref.name, test is not None)
        if club_ref is not None
        else (None, False, None)
    )
    return HeroOut(
        player_id=player.id,
        first_name=player.first_name,
        last_name=player.last_name,
        age=player.age,
        position=position,
        club=club_ref,
        league_name=league_name,
        overall=round(player.overall, 1),
        level=round(player.level, 1),
        rank=rank,
        at_position=at_position,
        status=status,
        first_choice=first_choice,
        dropped=dropped,
        points=row.points,
        xp=row.xp,
        xp_per_point=rules.XP_PER_POINT,
        attributes=attributes,
        matches=matches,
        last_reward=HeroRewardOut.model_validate(row.last_reward) if row.last_reward else None,
        confidence=row.confidence,
        trust=row.trust,
        entry=rules.entry_minute(row.trust),
        coach_notes=[CoachNoteOut(**note) for note in row.coach_notes or []],
        injury_weeks=injury_weeks,
        play_hurt=row.play_hurt,
        wage=player.wage,
        contract_until=player.contract_until,
        loaned_from=_ref(session, player.loaned_from),
        choice=row.choice,
        called_up=test,
        nation=nation,
        nation_id=getattr(NATIONS_BY_CODE.get(player.nationality), "id", None) if nation else None,
        eligible=eligible,
        call_up_chance=call_up_chance,
        caps=caps(session, player.id),
    )


def _ref(session: Session, club_id: int | None) -> ClubRef | None:
    club = session.get(ClubRow, club_id) if club_id is not None else None
    return ClubRef(id=club.id, name=club.name) if club else None


def social_out(session: Session, wanted_by: list[int] = ()) -> SocialOut:
    """Le fil des réseaux du joueur incarné : sa signature, puis chaque match de son club
    depuis (`HeroRow.rewarded`), avec ses actions en direct quand il les a jouées."""
    row = hero(session)
    player = session.get(PlayerRow, row.player_id)
    names = dict(session.execute(select(ClubRow.id, ClubRow.name)).all())
    club_id = player.club_id
    me = social.Hero(
        first_name=player.first_name,
        last_name=player.last_name,
        position=Position(player.position),
        club=names[club_id] if club_id is not None else "son ancien club",
    )
    matches = session.scalars(select(MatchRow).where(MatchRow.id.in_(row.rewarded or [])))
    appearances = []
    for match_row in matches:
        seen = _match_out(match_row, player.id, club_id, names)
        mine = match_row.home_club_id if seen.home else match_row.away_club_id
        lineup = match_row.home_lineup if seen.home else match_row.away_lineup
        appearances.append(
            social.Appearance(
                match_id=match_row.id,
                date=match_row.date,
                club=names[mine],
                opponent=seen.opponent.name,
                score_for=seen.score_for,
                score_against=seen.score_against,
                minutes=seen.minutes,
                rating=seen.rating,
                tries=seen.tries,
                started=player.id in (lineup or []),
                moments=(row.moments or {}).get(str(match_row.id), []),
            )
        )
    moves = [
        social.Move(
            date=datetime.date.fromisoformat(move["date"]),
            kind=move["kind"],
            origin=names.get(move["from"], "son club"),
            club=names.get(move["to"], "son club"),
        )
        for move in row.history or []
        if move["kind"] != "rumour"
    ]
    # Les clubs qui le veulent : ceux des fins de saison passées, et ceux d'aujourd'hui.
    by_day: dict[datetime.date, list[str]] = {}
    for move in row.history or []:
        if move["kind"] == "rumour":
            by_day.setdefault(datetime.date.fromisoformat(move["date"]), []).append(
                names[move["to"]]
            )
    if wanted_by and appearances:
        last = max(a.date for a in appearances) + datetime.timedelta(days=1)
        by_day.setdefault(last, []).extend(names[club_id] for club_id in wanted_by)
    rumours = sorted(by_day.items())
    listed = sorted(
        (
            call_up
            for season in session.scalars(select(SeasonRow))
            for call_up in internationals.call_up_rows(session, season)
            if player.id in call_up.player_ids
        ),
        key=lambda call_up: call_up.announced_on,
    )
    call_ups = [
        social.CallUp(
            date=call_up.announced_on,
            nation=NATIONS_BY_CODE[call_up.nation].name,
            window=WINDOWS_BY_CODE.get(call_up.competition, WORLD_CUP).name,
            first=index == 0,
        )
        for index, call_up in enumerate(listed)
    ]
    tests = []
    for key, line in (row.tests or {}).items():
        test = session.get(InternationalRow, int(key))
        if test is None or not test.is_played:
            continue
        seen = _test_out(test, player.id, line["nation"], line)
        tests.append(
            (
                social.Appearance(
                    match_id=-test.id,  # à part des matchs de club
                    date=test.date,
                    club=seen.nation,
                    opponent=seen.opponent,
                    score_for=seen.score_for,
                    score_against=seen.score_against,
                    minutes=line["minutes"],
                    rating=line["rating"],
                    tries=line["tries"],
                    started=False,
                    moments=line.get("moments", []),
                ),
                seen.nation,
            )
        )
    found = social.feed(me, appearances, row.signed_on, moves, rumours, call_ups, tests)
    return SocialOut(
        name=me.name,
        handle=f"{player.first_name}{player.last_name}".lower().replace(" ", ""),
        followers=found.followers,
        gain=found.gain,
        posts=[
            SocialPostOut(
                date=post.date,
                time=post.time,
                author=post.author.name,
                handle=post.author.handle,
                voice=post.author.voice.value,
                verified=post.author.verified,
                text=post.text,
                tone=post.tone.value,
                likes=post.likes,
                reposts=post.reposts,
                match_id=post.match_id,
            )
            for post in found.posts
        ],
    )


def set_play_hurt(session: Session, play: bool) -> None:
    """Blessé, il jouera (ou non) le prochain match de son club."""
    hero(session).play_hurt = play


# Confiance de l'entraîneur à l'arrivée dans un club, selon le rôle promis.
TRUST_ON_ARRIVAL = {"starter": 70.0, "rotation": 50.0, "prospect": 40.0}


def apply_choice(session: Session, year: int, day: datetime.date) -> None:
    """L'offre choisie à la fin de la saison, appliquée à l'intersaison (après la fin des
    prêts) : prolongation, transfert ou prêt d'une saison."""
    row = hero(session)
    if row is None:
        return
    choice, offers, row.choice, row.offers = row.choice, row.offers, None, None
    # Les clubs qui le voulaient restent dans son histoire : la presse en a parlé.
    wanted = [o for o in (offers or {}).get("list", []) if o["kind"] == "transfer"]
    if wanted:
        row.history = [
            *(row.history or []),
            *({"date": day.isoformat(), "kind": "rumour", "from": None, "to": o["club_id"]}
              for o in wanted),
        ]  # fmt: skip
    if not choice:
        return
    player = session.get(PlayerRow, row.player_id)
    origin = player.club_id
    if choice["kind"] == "extend":
        player.wage = choice["wage"]
        player.contract_until = max(player.contract_until, year + choice["years"] - 1)
    elif choice["kind"] == "transfer":
        player.club_id, player.loaned_from = choice["club_id"], None
        player.wage = choice["wage"]
        player.contract_until = year + choice["years"] - 1
    else:
        player.club_id, player.loaned_from = choice["club_id"], origin
    if player.club_id != origin:
        # Un nouveau club, un nouvel entraîneur : sa confiance se gagne de nouveau.
        row.trust = TRUST_ON_ARRIVAL[choice.get("role", "prospect")]
        row.coach_notes = []
    row.history = [
        *(row.history or []),
        {"date": day.isoformat(), "kind": choice["kind"], "from": origin, "to": player.club_id},
    ]


def career_out(session: Session) -> HeroCareerOut:
    """Son palmarès : chaque saison (clubs, matchs, essais, notes), ses titres (le club
    avec lequel il a joué au moins un match de la compétition l'a gagnée), ses trophées
    individuels et ses sélections."""
    row = hero(session)
    player = session.get(PlayerRow, row.player_id)
    names = dict(session.execute(select(ClubRow.id, ClubRow.name)).all())
    seasons = list(session.scalars(select(SeasonRow).order_by(SeasonRow.year.desc())))
    lines, titles = [], []
    for season in seasons:
        played = [
            m
            for m in [*season.matches, *season.cup_matches]
            if m.is_played and (m.stats or {}).get(str(player.id), {}).get("minutes", 0) > 0
        ]
        if not played:
            continue
        sides = {m.id: _side_of(m, player.id) for m in played}
        ratings = [m.stats[str(player.id)].get("rating") or 6.0 for m in played]
        lines.append(
            HeroSeasonOut(
                year=season.year,
                clubs=[
                    ClubRef(id=c, name=names[c]) for c in dict.fromkeys(sides[m.id] for m in played)
                ],
                matches=len(played),
                starts=sum(1 for m in played if player.id in _lineup(m, sides[m.id])),
                tries=sum(_tries(m, player.id) for m in played),
                average=round(sum(ratings) / len(ratings), 2),
                best=max(ratings),
            )
        )
        for code, club_id in {(m.league, sides[m.id]) for m in played}:
            if code in cup.CUPS:
                winner, label = cup.champion(session, season, code), cup.CUPS[code].short_name
            else:
                winner = champion(m.to_domain() for m in season.matches if m.league == code)
                label = league_config(code).name
            if winner == club_id:
                titles.append(
                    HeroTitleOut(
                        year=season.year,
                        competition=label,
                        club=ClubRef(id=club_id, name=names[club_id]),
                    )
                )
    awards = [
        HeroAwardOut(
            year=award.year,
            league_name=league_config(award.league).name,
            kind=award.kind,
            value=award.value,
        )
        for award in session.scalars(
            select(AwardRow).where(AwardRow.player_id == player.id).order_by(AwardRow.year.desc())
        )
    ]
    all_ratings = [(s.average or 6.0, s.matches) for s in lines]
    matches = sum(s.matches for s in lines)
    return HeroCareerOut(
        seasons=lines,
        titles=titles,
        awards=awards,
        matches=matches,
        tries=sum(s.tries for s in lines),
        average=round(sum(a * n for a, n in all_ratings) / matches, 2) if matches else None,
        best=max((s.best for s in lines if s.best is not None), default=None),
        caps=caps(session, player.id),
        retired=False,
    )


def caps(session: Session, player_id: int) -> int:
    """Ses sélections : les matchs internationaux joués, titulaire ou entré en jeu."""
    played = session.scalars(
        select(InternationalRow).where(InternationalRow.home_score.is_not(None))
    )
    return sum(1 for match_row in played if _took_part(match_row, player_id))


def _took_part(match_row, player_id: int) -> bool:
    if player_id in [*(match_row.home_lineup or []), *(match_row.away_lineup or [])]:
        return True
    return any(
        e.get("type") == EventType.SUBSTITUTION.value and e.get("other_player_id") == player_id
        for e in match_row.events or []
    )


def _side_of(match_row: MatchRow, player_id: int) -> int:
    """Le club pour lequel il a joué ce match : celui de sa feuille de match (titulaire),
    sinon celui dont il porte le maillot (remplaçant)."""
    if player_id in (match_row.away_lineup or []):
        return match_row.away_club_id
    if player_id in (match_row.home_lineup or []):
        return match_row.home_club_id
    subs = [
        e for e in match_row.events or []
        if e.get("type") == EventType.SUBSTITUTION.value and e.get("other_player_id") == player_id
    ]  # fmt: skip
    return subs[0]["club_id"] if subs else match_row.home_club_id


def _lineup(match_row: MatchRow, club_id: int) -> list[int]:
    return (
        match_row.home_lineup if club_id == match_row.home_club_id else match_row.away_lineup
    ) or []


def _tries(match_row: MatchRow, player_id: int) -> int:
    return sum(
        1
        for e in match_row.events or []
        if e.get("type") == EventType.TRY.value and e.get("player_id") == player_id
    )


def retire(session: Session, day: datetime.date) -> HeroCareerOut:
    """Il raccroche : son bilan, puis il quitte le monde comme tout joueur qui prend sa
    retraite (le monde continue, sans carrière en cours). Renvoie le bilan."""
    row = hero(session)
    career = career_out(session).model_copy(update={"retired": True})
    player = session.get(PlayerRow, row.player_id)
    log_move(session, MoveKind.RETIREMENT, player, day, origin=player.loaned_from or player.club_id)
    session.delete(row)
    session.flush()
    delete_player(session, player)
    return career


# --- Sélection nationale ---------------------------------------------------------------------


def next_test(session: Session, season: SeasonRow | None) -> InternationalRow | None:
    """Son prochain match en sélection : il figure sur la liste de sa sélection pour la
    fenêtre, et le match n'est pas joué."""
    row = hero(session)
    if row is None or season is None:
        return None
    lists = {
        (call_up.competition, NATIONS_BY_CODE[call_up.nation].id)
        for call_up in internationals.call_up_rows(session, season)
        if row.player_id in call_up.player_ids
    }
    upcoming = [
        test
        for test in internationals.test_rows(session, season)
        if not test.is_played
        and ((test.competition, test.home_id) in lists or (test.competition, test.away_id) in lists)
    ]
    return upcoming[0] if upcoming else None


def _test_out(test: InternationalRow, player_id: int, nation_id: int, line: dict) -> HeroTestOut:
    home = test.home_id == nation_id
    return HeroTestOut(
        match_id=test.id,
        date=test.date,
        competition=WINDOWS_BY_CODE.get(test.competition, WORLD_CUP).name,
        nation=NATIONS_BY_ID[nation_id].name,
        opponent=NATIONS_BY_ID[test.away_id if home else test.home_id].name,
        home=home,
        score_for=test.home_score if home else test.away_score,
        score_against=test.away_score if home else test.home_score,
        minutes=line.get("minutes"),
        rating=line.get("rating"),
    )


def called_up(session: Session, season: SeasonRow | None) -> HeroTestOut | None:
    test = next_test(session, season)
    if test is None:
        return None
    player_id = hero(session).player_id
    lists = internationals.squads(session, season)
    nation_id = (
        test.home_id
        if player_id in lists.get((test.competition, test.home_id), [])
        else test.away_id
    )
    return _test_out(test, player_id, nation_id, {})


def record_test(session: Session, live) -> None:
    """Un match international qu'il a joué en direct : minutes, note, essais, actions."""
    row = hero(session)
    match = live.match
    side = match.hero_side()
    if row is None or side is None or row.player_id not in side.entered_at:
        return
    player_id = row.player_id
    minutes = side.off.get(player_id, match.minute) - side.entered_at[player_id]
    row.tests = {
        **(row.tests or {}),
        str(live.match_row.id): {
            "nation": side.club.id,
            "minutes": max(0, minutes),
            "rating": round(side.ratings.get(player_id, 6.0), 1),
            "tries": sum(
                1 for e in match.events if e.type == EventType.TRY and e.player_id == player_id
            ),
            "moments": [o.to_dict() for o in match.outcomes],
            "rewarded": False,
        },
    }


def record_tests(session: Session, matches: list) -> None:
    """Ses matchs internationaux simulés du jour : minutes, note, essais, comme en direct
    (sans ses actions). Celui joué en direct est déjà gardé (`record_test`). Ils ne
    rapportent pas d'expérience : seul le direct en donne."""
    row = hero(session)
    if row is None or not matches:
        return
    tests = dict(row.tests or {})
    for match in matches:
        line = match.stats.get(row.player_id)
        if line is None or str(match.id) in tests:
            continue
        tests[str(match.id)] = {
            "nation": _nation_of(match, row.player_id),
            "minutes": line.minutes,
            "rating": line.rating,
            "tries": sum(
                1 for e in match.events if e.type == EventType.TRY and e.player_id == row.player_id
            ),
            "moments": [],
            "rewarded": True,
        }
    row.tests = tests


def _nation_of(match, player_id: int) -> int:
    """La sélection pour laquelle il a joué ce match du moteur (`_side_of` pour une ligne
    de la base)."""
    if player_id in match.home_lineup:
        return match.home_club_id
    if player_id in match.away_lineup:
        return match.away_club_id
    return next(
        (
            e.club_id
            for e in match.events
            if e.type == EventType.SUBSTITUTION and e.other_player_id == player_id
        ),
        match.home_club_id,
    )


def _test_minutes(test: InternationalRow, player_id: int) -> int:
    """Ses minutes dans un match international d'avant `record_tests` : du coup d'envoi
    ou de son entrée jusqu'à sa sortie, ou au coup de sifflet."""
    subs = [e for e in test.events or [] if e.get("type") == EventType.SUBSTITUTION.value]
    end = max([MATCH_MINUTES, *(e.get("minute", 0) for e in test.events or [])])
    entered = 0 if player_id in [*(test.home_lineup or []), *(test.away_lineup or [])] else None
    if entered is None:
        entered = next((e["minute"] for e in subs if e.get("other_player_id") == player_id), end)
    left = next((e["minute"] for e in subs if e.get("player_id") == player_id), end)
    return max(0, left - entered)


def season_tests(session: Session, season: SeasonRow, row: HeroRow) -> list[HeroMatchOut]:
    """Ses matchs internationaux de la saison, joués, vus de sa sélection."""
    out = []
    for test in internationals.test_rows(session, season):
        if not test.is_played or not _took_part(test, row.player_id):
            continue
        line = (row.tests or {}).get(str(test.id))
        nation_id = line["nation"] if line else _side_of(test, row.player_id)
        home = nation_id == test.home_id
        opponent = NATIONS_BY_ID[test.away_id if home else test.home_id]
        out.append(
            HeroMatchOut(
                match_id=test.id,
                date=test.date,
                opponent=ClubRef(id=opponent.id, name=opponent.name),
                home=home,
                score_for=test.home_score if home else test.away_score,
                score_against=test.away_score if home else test.home_score,
                minutes=line["minutes"] if line else _test_minutes(test, row.player_id),
                rating=line["rating"] if line else None,
                tries=line["tries"] if line else _tries(test, row.player_id),
                international=True,
                competition=WINDOWS_BY_CODE.get(test.competition, WORLD_CUP).short_name,
            )
        )
    return out


def _reward_tests(row: HeroRow) -> int:
    """L'expérience (et la confiance) de ses matchs internationaux pas encore comptés."""
    xp = 0
    tests = dict(row.tests or {})
    for key, line in tests.items():
        if line.get("rewarded"):
            continue
        xp += rules.match_xp(line["minutes"], line["rating"])
        row.confidence = rules.next_confidence(row.confidence, line["rating"])
        tests[key] = {**line, "rewarded": True}
    row.tests = tests
    return xp
