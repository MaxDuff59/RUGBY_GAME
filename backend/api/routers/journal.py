"""Le journal : les nouvelles du monde, clubs et sélections.

Lisible depuis toute carrière. Les faits viennent de la base (matchs, registre des
mouvements, blessures, listes des sélections) ; les titres et leur poids, du moteur
(engine/journal.py). La route ne fait que lire : rien n'est enregistré.
"""

import datetime
import random
from collections import Counter
from dataclasses import dataclass

from fastapi import APIRouter, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from api import cup, internationals
from api.deps import SessionDep
from api.free_agents import free_agent_rows
from api.ledger import current_season, game_date
from api.routers.contracts import EXTENSION
from api.schemas import (
    ArticleOut,
    ClubRef,
    CompetitionOut,
    JournalOut,
    JournalPlayer,
    MatchSummary,
    MoveOut,
    ProspectOut,
    RoundOut,
)
from data.leagues import league_config, sort_codes
from data.nations import NATIONS, NATIONS_BY_CODE, WINDOWS_BY_CODE, Window
from engine import europe, journal
from engine import internationals as rules
from engine.free_agents import seasons_without_club
from engine.journal import Article, Move, MoveKind, Person, Team
from engine.offseason import RETIREMENT_AGE
from models import ATTRIBUTE_NAMES, EventType, Match, Position, Squad, Stage
from models.orm import (
    CallUpRow,
    CareerRow,
    ClubRow,
    DismissalRow,
    InjuryRow,
    MoveRow,
    NegotiationRow,
    PlayerRow,
    SeasonRow,
    SuspensionRow,
)

router = APIRouter(prefix="/journal", tags=["journal"])

# Combien de temps un fait reste une nouvelle, en jours.
RESULT_DAYS = 21
PREVIEW_DAYS = 9
MOVE_DAYS = 45
INJURY_DAYS = 14
SQUAD_DAYS = 21
DISMISSAL_DAYS = 30

# Par compétition : tout ce qui touche le joueur, et les plus lourds du reste.
RESULTS_KEPT = 3
PREVIEWS_KEPT = 2
PRESTIGE = 10.0  # ce qu'ajoute le championnat le mieux doté (`League.prize_factor`)
MOVES_SHOWN = 40
MOVE_ARTICLES = 14
SQUAD_ARTICLES = 4
INJURY_ARTICLES = 6
INJURY_MIN_DAYS = 21  # une blessure fait une nouvelle à partir de trois semaines d'absence
SUSPENSION_DAYS = 10
SUSPENSION_ARTICLES = 3
# Marché : on tire quelques noms parmi les mieux notés, pas les mêmes d'une semaine à l'autre.
CONTRACT_POOL, CONTRACT_ARTICLES = 12, 3
FREE_AGENT_POOL, FREE_AGENT_ARTICLES = 8, 2

_SCORING = {EventType.TRY, EventType.CONVERSION, EventType.PENALTY_GOAL, EventType.DROP_GOAL}


@dataclass(frozen=True)
class _Reader:
    """Pour qui le journal est écrit : son équipe et sa compétition passent devant."""

    team: int | None = None  # club dirigé, ou sélection du sélectionneur
    league: str | None = None  # championnat du club dirigé
    nation: str | None = None  # code de la sélection (carrière de sélectionneur)

    def plays(self, match: Match) -> bool:
        return self.team is not None and self.team in (match.home_club_id, match.away_club_id)

    def manages(self, club_id: int | None) -> bool:
        """Ce club est celui du joueur (jamais vrai pour un sélectionneur)."""
        return self.nation is None and self.team is not None and self.team == club_id

    def follows(self, competition: "_Competition") -> bool:
        if competition.international:
            return self.nation is not None
        return competition.code == self.league


@dataclass
class _Competition:
    code: str
    name: str
    matches: list[Match]
    window: Window | None = None  # fenêtre internationale ; None pour un championnat
    pools: dict[str, list[int]] | None = None  # Coupe d'Europe : ses poules (api/cup.py)

    @property
    def international(self) -> bool:
        return self.window is not None

    @property
    def last(self) -> list[Match]:
        """La dernière journée jouée."""
        played = [m for m in self.matches if m.is_played]
        day = max((m.date for m in played), default=None)
        return [m for m in played if m.date == day]

    @property
    def next(self) -> list[Match]:
        unplayed = [m for m in self.matches if not m.is_played]
        day = min((m.date for m in unplayed), default=None)
        return [m for m in unplayed if m.date == day]

    def round_label(self, match: Match) -> str:
        if match.stage != Stage.REGULAR:
            return journal.STAGE_TITLES[match.stage]
        if self.window is not None and not self.window.has_table:
            return f"Test {match.matchday}"
        if self.pools is not None:
            return f"Poules, journée {match.matchday}"
        return f"Journée {match.matchday}"


def _competitions(session: Session, season: SeasonRow) -> list[_Competition]:
    """Les championnats de la saison, puis ses fenêtres internationales."""
    by_league: dict[str, list[Match]] = {}
    for row in season.matches:
        by_league.setdefault(row.league, []).append(row.to_domain())
    out = [
        _Competition(code, league_config(code).short_name, by_league[code])
        for code in sort_codes(by_league)
    ]
    tests: dict[str, list[Match]] = {}
    for row in internationals.test_rows(session, season):
        tests.setdefault(row.competition, []).append(row.to_domain())
    for code in cup.codes(season):
        out.append(
            _Competition(
                code,
                cup.CUPS[code].short_name,
                cup.matches(season, code),
                pools=cup.pools(session, season, code),
            )
        )
    for code, matches in tests.items():
        window = WINDOWS_BY_CODE[code]
        out.append(_Competition(code, window.name, matches, window))
    for competition in out:
        competition.matches.sort(key=lambda m: (m.date, m.id))
    return out


def _person(row: PlayerRow) -> Person:
    overall = sum(getattr(row, name) for name in ATTRIBUTE_NAMES) / len(ATTRIBUTE_NAMES)
    return Person(
        row.id, f"{row.first_name} {row.last_name}", Position(row.position), row.age, overall
    )


def _keep(articles: list[Article], count: int) -> list[Article]:
    """Tout ce qui touche le joueur, et les `count` plus lourds du reste."""
    others = sorted((a for a in articles if not a.mine), key=lambda a: a.weight, reverse=True)
    return [a for a in articles if a.mine] + others[:count]


# --- Matchs --------------------------------------------------------------------------------


def _scorers(session: Session, matches: list[Match]) -> dict[int, str]:
    """Le nom des joueurs qui ont marqué dans ces matchs."""
    ids = {
        e.player_id
        for match in matches
        for e in match.events
        if e.type in _SCORING and e.player_id is not None
    }
    rows = session.execute(
        select(PlayerRow.id, PlayerRow.first_name, PlayerRow.last_name).where(PlayerRow.id.in_(ids))
    )
    return {player_id: f"{first} {last}" for player_id, first, last in rows}


def _match_articles(
    session: Session,
    competitions: list[_Competition],
    teams: dict[int, Team],
    reader: _Reader,
    today: datetime.date,
) -> list[Article]:
    """Résultats de la dernière journée de chaque compétition, affiches de la
    prochaine, et le point sur son classement."""
    recent = {
        c.code: c.last
        for c in competitions
        if c.last and (today - c.last[0].date).days <= RESULT_DAYS
    }
    people = _scorers(session, [m for matches in recent.values() for m in matches])
    articles: list[Article] = []
    for c in competitions:
        home = reader.follows(c)
        # Un grand championnat fait plus de bruit qu'un petit.
        config = cup.CUPS[c.code] if c.pools is not None else league_config(c.code)
        prestige = 0.0 if c.international else config.prize_factor * PRESTIGE
        world_cup = c.window is not None and c.window.format == "world_cup"
        # Pas de classement général pour une coupe à poules (coupes d'Europe, Mondial).
        has_table = (c.window is None and c.pools is None) or (
            c.window is not None and c.window.has_table and not world_cup
        )
        table = journal.table_of(c.matches) if has_table else None
        runs = journal.streaks(c.matches)

        results = [
            journal.favour(
                journal.result_article(m, teams, people, c.name, table, runs, c.international),
                reader.plays(m),
                home,
            )
            for m in recent.get(c.code, [])
        ]
        kept = _keep(results, len(results) if home else RESULTS_KEPT)

        upcoming = c.next
        if upcoming and (upcoming[0].date - today).days <= PREVIEW_DAYS:
            previews = [
                journal.favour(
                    journal.preview_article(m, teams, c.name, table, runs, c.international),
                    reader.plays(m),
                    home,
                )
                for m in upcoming
            ]
            kept += _keep(previews, PREVIEWS_KEPT)

        last = recent.get(c.code)
        if c.window is not None:
            winner = rules.champion(c.window, c.matches)
        elif c.pools is not None:
            winner = europe.champion(c.pools, c.matches)
        else:
            winner = None
        if winner is not None and last:
            write = journal.cup_title_article if c.pools is not None else journal.title_article
            crowned = write(c.code, c.name, teams[winner], last[0].date)
            kept.append(journal.favour(crowned, winner == reader.team, home))
        elif table is not None and last and last[0].stage == Stage.REGULAR:
            point = journal.table_article(
                c.code, c.name, table, teams, last[0].date, c.international
            )
            if point is not None:
                kept.append(journal.favour(point, point.teams[0].id == reader.team, home))
        for article in kept:
            article.weight += prestige
        articles += kept
    return articles


def _round(competition: _Competition, matches: list[Match], names: dict[int, str]) -> RoundOut:
    return RoundOut(
        label=competition.round_label(matches[0]),
        date=matches[0].date,
        matches=[MatchSummary.from_match(m, names) for m in matches],
    )


def _focus(competitions: list[_Competition], reader: _Reader) -> str | None:
    """La compétition du joueur : son championnat, ou la fenêtre où joue sa sélection
    (la prochaine, sinon la dernière)."""
    if reader.nation is None:
        return reader.league
    windows = [c for c in competitions if c.international]

    def days(competition: _Competition, played: bool) -> list[datetime.date]:
        return [m.date for m in competition.matches if m.is_played == played and reader.plays(m)]

    coming = [(min(days(c, False)), c.code) for c in windows if days(c, False)]
    if coming:
        return min(coming)[1]
    done = [(max(days(c, True)), c.code) for c in windows if days(c, True)]
    if done:
        return max(done)[1]
    return windows[0].code if windows else None


# --- Mouvements ----------------------------------------------------------------------------


def _moves(session: Session, teams: dict[int, Team]) -> list[Move]:
    """Les derniers mouvements : ceux du registre, les pré-contrats signés qui attendent
    l'intersaison, et les arrivées d'avant le registre (parties plus anciennes)."""
    rows = list(
        session.scalars(
            select(MoveRow)
            .order_by(MoveRow.date.desc(), MoveRow.overall.desc(), MoveRow.id.desc())
            .limit(MOVES_SHOWN * 2)
        )
    )
    moves = [
        Move(
            kind=MoveKind(row.kind),
            date=row.date,
            player=Person(
                row.player_id, row.player_name, Position(row.position), row.age, row.overall
            ),
            origin=teams.get(row.from_club_id),
            destination=teams.get(row.to_club_id),
            fee=row.fee,
            key=str(row.id),
        )
        for row in rows
    ]

    # Les accords dont le registre ne dit rien : pré-contrats en attente, arrivées d'avant lui.
    signed = session.execute(
        select(NegotiationRow.id, NegotiationRow.player_id, NegotiationRow.club_id).where(
            NegotiationRow.stage.in_(("agreed", "done")), NegotiationRow.kind != EXTENSION
        )
    ).all()
    logged = {
        (player_id, club_id)
        for player_id, club_id in session.execute(
            select(MoveRow.player_id, MoveRow.to_club_id).where(MoveRow.to_club_id.is_not(None))
        )
    }
    untold = [deal_id for deal_id, *where in signed if tuple(where) not in logged]
    deals = session.execute(
        select(NegotiationRow, PlayerRow)
        .join(PlayerRow, NegotiationRow.player_id == PlayerRow.id)
        .where(NegotiationRow.id.in_(untold))
    )
    for deal, player in deals:
        pending = deal.stage == "agreed"
        if pending and player.club_id == deal.club_id:
            continue
        # Une arrivée d'avant le registre : on ne sait plus d'où (sauf un prêt en cours).
        origin = player.club_id if pending else player.loaned_from
        moves.append(
            Move(
                kind=MoveKind(deal.kind),
                date=deal.opened_on,
                player=_person(player),
                origin=teams.get(origin),
                destination=teams.get(deal.club_id),
                fee=deal.fee,
                pending=pending,
                key=f"n{deal.id}",
            )
        )
    moves.sort(key=lambda move: (move.date, move.player.overall), reverse=True)
    return moves[:MOVES_SHOWN]


def _involves(move: Move, reader: _Reader) -> bool:
    return any(reader.manages(team.id) for team in (move.origin, move.destination) if team)


def _quiet_days(competitions: list[_Competition], moves: list[Move], today: datetime.date) -> int:
    """Jours écoulés depuis le dernier fait du monde (un match joué, un mouvement) :
    une intersaison ou une trêve ne vieillit pas les nouvelles qui la précèdent."""
    dates = [c.last[0].date for c in competitions if c.last]
    dates += [move.date for move in moves if move.date <= today]
    return max(0, (today - max(dates)).days) if dates else 0


def _move_articles(
    moves: list[Move], reader: _Reader, today: datetime.date, quiet: int
) -> list[Article]:
    articles = [
        journal.favour(journal.move_article(move), _involves(move, reader))
        for move in moves
        if (today - move.date).days - quiet <= MOVE_DAYS
    ]
    return _keep(articles, MOVE_ARTICLES)


@dataclass
class _Market:
    """Les joueurs à suivre, les mieux notés d'abord."""

    ending: list[tuple[Person, int]]  # en dernière année de contrat, avec leur club
    free: list[tuple[Person, int]]  # sans club, avec leurs saisons entières sans contrat


def _market(session: Session, season: SeasonRow) -> _Market:
    """Les joueurs en dernière année de contrat que rien n'engage encore ailleurs, et
    les agents libres."""
    signed = set(
        session.scalars(select(NegotiationRow.player_id).where(NegotiationRow.stage == "agreed"))
    )
    ending = [
        (_person(row), row.club_id)
        for row in session.scalars(
            select(PlayerRow).where(
                PlayerRow.squad == Squad.PRO.value,
                PlayerRow.club_id.is_not(None),
                PlayerRow.loaned_from.is_(None),
                PlayerRow.contract_until <= season.year,
                PlayerRow.age + 1 < RETIREMENT_AGE,
            )
        )
        if row.id not in signed
    ]
    ending.sort(key=lambda entry: entry[0].overall, reverse=True)
    free = [
        (_person(row), seasons_without_club(row.to_domain(), season.year))
        for row in free_agent_rows(session)
    ]
    free.sort(key=lambda entry: entry[0].overall, reverse=True)
    return _Market(ending[:CONTRACT_POOL], free[:FREE_AGENT_POOL])


def _market_articles(
    market: _Market,
    season: SeasonRow,
    teams: dict[int, Team],
    reader: _Reader,
    today: datetime.date,
) -> list[Article]:
    """Ce qui se prépare : quelques noms parmi les joueurs à suivre, tirés d'après la
    date (les mêmes tant que le jour ne change pas)."""
    rng = random.Random(f"journal:{season.year}:{today.isoformat()}")
    articles = [
        journal.favour(
            journal.contract_article(player, teams[club_id], today), reader.manages(club_id)
        )
        for player, club_id in rng.sample(market.ending, min(CONTRACT_ARTICLES, len(market.ending)))
    ]
    for player, out in rng.sample(market.free, min(FREE_AGENT_ARTICLES, len(market.free))):
        articles.append(journal.free_agent_article(player, out, today))
    return articles


# --- Infirmerie, sélections, coulisses -----------------------------------------------------


def _injury_articles(
    session: Session,
    teams: dict[int, Team],
    reader: _Reader,
    listed: set[int],
    today: datetime.date,
) -> list[Article]:
    """Les blessures récentes qui écartent un joueur plusieurs semaines. `listed` : les
    joueurs retenus par la sélection du sélectionneur."""
    rows = session.execute(
        select(InjuryRow, PlayerRow)
        .join(PlayerRow, InjuryRow.player_id == PlayerRow.id)
        .where(
            InjuryRow.occurred_on >= today - datetime.timedelta(days=INJURY_DAYS),
            InjuryRow.return_date > today,
            PlayerRow.squad != Squad.YOUTH.value,
        )
    )
    articles = []
    for injury, player in rows:
        if (injury.return_date - injury.occurred_on).days < INJURY_MIN_DAYS:
            continue
        mine = player.id in listed if reader.nation else player.club_id == reader.team
        article = journal.injury_article(
            _person(player), teams.get(player.club_id), injury.to_domain()
        )
        articles.append(journal.favour(article, mine and reader.team is not None))
    return _keep(articles, INJURY_ARTICLES)


def _suspension_articles(
    session: Session, teams: dict[int, Team], reader: _Reader, today: datetime.date
) -> list[Article]:
    """Les suspensions de la semaine passée (engine/discipline.py)."""
    rows = session.execute(
        select(SuspensionRow, PlayerRow)
        .join(PlayerRow, SuspensionRow.player_id == PlayerRow.id)
        .where(SuspensionRow.date >= today - datetime.timedelta(days=SUSPENSION_DAYS))
    )
    articles = []
    for suspension, player in rows:
        article = journal.suspension_article(
            suspension.id,
            _person(player),
            teams[suspension.club_id],
            suspension.matches,
            suspension.reason,
            suspension.date,
        )
        articles.append(journal.favour(article, reader.manages(suspension.club_id)))
    return _keep(articles, SUSPENSION_ARTICLES)


def _squad_articles(
    session: Session,
    calls: list[CallUpRow],
    names: dict[int, str],
    teams: dict[int, Team],
    reader: _Reader,
    today: datetime.date,
) -> list[Article]:
    """Les listes annoncées ces dernières semaines, avec les clubs les plus représentés."""
    recent = [row for row in calls if (today - row.announced_on).days <= SQUAD_DAYS]
    ids = [player_id for row in recent for player_id in row.player_ids]
    club_of = dict(
        session.execute(select(PlayerRow.id, PlayerRow.club_id).where(PlayerRow.id.in_(ids))).all()
    )
    articles = []
    for row in recent:
        nation = NATIONS_BY_CODE[row.nation]
        counts = Counter(club_of.get(player_id) for player_id in row.player_ids)
        counts.pop(None, None)
        cited = counts.most_common(3)
        article = journal.squad_article(
            row.competition,
            teams[nation.id],
            WINDOWS_BY_CODE[row.competition].name,
            len(row.player_ids),
            [(names[club_id], count) for club_id, count in cited],
            row.announced_on,
        )
        # À poids égal, les nations les mieux armées d'abord.
        article.weight += nation.level / 10
        # Pour un club : la liste le touche quand il est de ceux que l'article cite.
        mine = row.nation == reader.nation or (
            reader.nation is None and reader.team in (club_id for club_id, _ in cited)
        )
        articles.append(journal.favour(article, mine))
    return _keep(articles, SQUAD_ARTICLES)


def _dismissal_articles(
    session: Session, teams: dict[int, Team], today: datetime.date
) -> list[Article]:
    rows = session.scalars(
        select(DismissalRow).where(
            DismissalRow.date >= today - datetime.timedelta(days=DISMISSAL_DAYS)
        )
    )
    return [
        journal.dismissal_article(row.id, row.manager_name, teams[row.club_id], row.date)
        for row in rows
    ]


# --- Mise en forme -------------------------------------------------------------------------


def _player_out(player: Person, photos: dict[int, str | None]) -> JournalPlayer:
    known = player.id in photos
    return JournalPlayer(
        id=player.id if known else None,
        name=player.name,
        position=player.position,
        age=player.age,
        overall=round(player.overall, 1),
        photo=photos.get(player.id),
    )


def _club_ref(team: Team | None) -> ClubRef | None:
    return ClubRef(id=team.id, name=team.name) if team is not None else None


def _move_out(move: Move, photos: dict[int, str | None], reader: _Reader) -> MoveOut:
    return MoveOut(
        id=move.key,
        kind=move.kind,
        date=move.date,
        player=_player_out(move.player, photos),
        origin=_club_ref(move.origin),
        destination=_club_ref(move.destination),
        fee=move.fee,
        pending=move.pending,
        mine=_involves(move, reader),
    )


def _article_out(
    article: Article, names: dict[int, str], photos: dict[int, str | None], reader: _Reader
) -> ArticleOut:
    return ArticleOut(
        id=article.key,
        kind=article.kind,
        date=article.date,
        title=article.title,
        body=article.body,
        competition=article.competition,
        international=article.international,
        mine=article.mine,
        teams=[_club_ref(team) for team in article.teams],
        player=_player_out(article.player, photos) if article.player else None,
        match=MatchSummary.from_match(article.match, names) if article.match else None,
        move=_move_out(article.move, photos, reader) if article.move else None,
    )


@router.get("", response_model=JournalOut)
def get_journal(session: SessionDep) -> JournalOut:
    """Le journal du jour : articles (la une, puis le fil), dernière et prochaine journée
    de chaque compétition, derniers mouvements de joueurs."""
    season = current_season(session)
    if season is None:
        raise HTTPException(status_code=404, detail="Aucune saison : commence une carrière")
    today = game_date(session)

    clubs = session.execute(select(ClubRow.id, ClubRow.name, ClubRow.league)).all()
    names = {club_id: name for club_id, name, _ in clubs}
    teams = {club_id: journal.club_team(club_id, name) for club_id, name, _ in clubs}
    for nation in NATIONS:
        names[nation.id] = nation.name
        teams[nation.id] = journal.nation_team(nation.id, nation.code, nation.name)

    career = session.scalars(select(CareerRow)).first()
    human = internationals.selector(session)
    reader = _Reader()
    if career is not None:
        league = next(code for club_id, _, code in clubs if club_id == career.club_id)
        reader = _Reader(team=career.club_id, league=league)
    elif human is not None:
        reader = _Reader(team=NATIONS_BY_CODE[human.nation].id, nation=human.nation)

    competitions = _competitions(session, season)
    calls = internationals.call_up_rows(session, season)
    listed = {
        player_id for row in calls if row.nation == reader.nation for player_id in row.player_ids
    }
    moves = _moves(session, teams)
    market = _market(session, season)
    quiet = _quiet_days(competitions, moves, today)

    articles = [
        *_match_articles(session, competitions, teams, reader, today),
        *_move_articles(moves, reader, today, quiet),
        *_market_articles(market, season, teams, reader, today),
        *_injury_articles(session, teams, reader, listed, today),
        *_suspension_articles(session, teams, reader, today),
        *_squad_articles(session, calls, names, teams, reader, today),
        *_dismissal_articles(session, teams, today),
    ]
    articles = journal.edition(articles, today, quiet)

    # Photo des joueurs cités, et lesquels ont encore une fiche.
    cited = {a.player.id for a in articles if a.player} | {move.player.id for move in moves}
    cited |= {player.id for player, _ in (*market.ending, *market.free)}
    photos = dict(
        session.execute(select(PlayerRow.id, PlayerRow.photo).where(PlayerRow.id.in_(cited))).all()
    )

    return JournalOut(
        year=season.year,
        today=today,
        articles=[_article_out(article, names, photos, reader) for article in articles],
        competitions=[
            CompetitionOut(
                code=c.code,
                name=c.name,
                international=c.international,
                last=_round(c, c.last, names) if c.last else None,
                next=_round(c, c.next, names) if c.next else None,
            )
            for c in competitions
        ],
        focus=_focus(competitions, reader),
        moves=[_move_out(move, photos, reader) for move in moves],
        prospects=[
            *(
                ProspectOut(
                    player=_player_out(player, photos),
                    club=_club_ref(teams[club_id]),
                    mine=reader.manages(club_id),
                )
                for player, club_id in market.ending
            ),
            *(
                ProspectOut(player=_player_out(player, photos), club=None)
                for player, _ in market.free
            ),
        ],
    )
