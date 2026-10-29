"""Le match libre : deux équipes au choix, clubs ou sélections, hors de toute carrière.

Les équipes viennent d'un monde de référence partagé par tous les comptes : une partie
rangée sous un compte qui n'existe pas (`REFERENCE`), créée au premier match libre avec
les vrais effectifs et les renforts des sélections, puis jamais modifiée. Le match en
cours, lui, est rangé avec le compte qui le joue (`FriendlyRow`, à côté des comptes) :
un joueur sans partie, ou un invité, peut en jouer un, et aucune carrière n'est touchée.

Entre deux requêtes, l'état complet du moteur dort dans la ligne, comme pour le match
en direct d'une carrière (api/live.py) ; les équipes se reconstruisent à chaque fois
depuis le monde de référence (le club entier, ou la liste de la sélection).
"""

import datetime
import itertools
import random
import threading
from dataclasses import dataclass

from sqlalchemy import JSON, Date, DateTime, Engine, Integer, delete, func, inspect, select, text
from sqlalchemy.orm import Mapped, Session, mapped_column

import accounts
import database
from api import internationals
from api.deps import load_clubs
from api.live import Live
from data.derbies import derby
from data.leagues import LEAGUES, league_config
from data.nations import NATIONS, NATIONS_BY_ID
from engine import internationals as rules
from engine.match_engine import SLOT_POSITIONS, LiveMatch, Tactics, staff_tactics, team_strength
from engine.weather import forecast
from models import Club, Squad, Stage
from models.orm import ClubRow, PlayerRow

# Le monde de référence : (compte, emplacement). Aucun compte n'a l'identifiant 0.
REFERENCE = (0, 1)
REFERENCE_SEED = 0
# Un match libre abandonné depuis plus longtemps est effacé.
KEEP_DAYS = 7
# Code de « championnat » du match libre, pour l'API (jamais une coupe).
LEAGUE = "friendly"

_reference_lock = threading.Lock()
# La base des comptes où la table des matchs libres a été créée (elle change en test).
_table_engine: Engine | None = None


class FriendlyRow(accounts.AccountsBase):
    """Le match libre en cours d'un compte (un seul à la fois)."""

    __tablename__ = "friendly_matches"

    user_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    home_id: Mapped[int]
    away_id: Mapped[int]
    my_id: Mapped[int]
    date: Mapped[datetime.date] = mapped_column(Date)
    # Liste de chaque sélection du match (identifiants de joueurs du monde de référence).
    squads: Mapped[dict] = mapped_column(JSON, default=dict)
    # XV composé par le joueur avant le coup d'envoi, place par place (vide : le staff).
    lineup: Mapped[list | None] = mapped_column(JSON, default=list)
    # État du moteur une fois le coup d'envoi donné (vide avant).
    state: Mapped[dict] = mapped_column(JSON, default=dict)
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime)

    # Ce que live_out lit d'un match du calendrier.
    matchday = 0
    neutral = False
    stage = Stage.REGULAR.value
    league = LEAGUE

    @property
    def id(self) -> int:
        return self.user_id

    @property
    def started(self) -> bool:
        return bool(self.state)


def _accounts_session() -> Session:
    """Une session sur la base des comptes, la table des matchs libres créée au besoin."""
    global _table_engine
    engine = accounts.engine()
    if _table_engine is not engine:
        FriendlyRow.__table__.create(engine, checkfirst=True)
        # Colonne venue après la table : les bases qui l'ont déjà la reçoivent ici.
        if "lineup" not in {c["name"] for c in inspect(engine).get_columns("friendly_matches")}:
            with engine.begin() as connection:
                connection.execute(text("ALTER TABLE friendly_matches ADD COLUMN lineup JSON"))
        _table_engine = engine
    return Session(engine, expire_on_commit=False)


def _forget(session: Session, user_ids: list[int]) -> None:
    """Efface le match libre des invités partis (accounts.purge_guests)."""
    if inspect(session.get_bind()).has_table("friendly_matches"):
        session.execute(delete(FriendlyRow).where(FriendlyRow.user_id.in_(user_ids)))


accounts.ON_PURGE.append(_forget)


# --- Le monde de référence ---------------------------------------------------------------


def reference() -> Session:
    """Une session sur le monde de référence, créé au premier appel (quelques secondes).
    Un monde resté à moitié fait (création interrompue) est refait de zéro."""
    with _reference_lock:
        if not _complete():
            try:
                database.new_slot(*REFERENCE, seed=REFERENCE_SEED)
                with database.open_slot(*REFERENCE) as session:
                    _add_reinforcements(session)
            except Exception:
                database.delete_slot(*REFERENCE)
                raise
    return database.open_slot(*REFERENCE)


def _complete() -> bool:
    """Le monde de référence existe-t-il, renforts des sélections compris (la dernière
    étape de sa création) ?"""
    if not database.slot_exists(*REFERENCE):
        return False
    with database.open_slot(*REFERENCE) as session:
        away = select(PlayerRow.id).where(PlayerRow.squad == Squad.AWAY.value).limit(1)
        return session.scalar(away) is not None


def _add_reinforcements(session: Session) -> None:
    """Les joueurs que chaque sélection va chercher hors des championnats du jeu,
    comme au premier calendrier international d'une partie."""
    rng = random.Random(f"{REFERENCE_SEED}-friendly")
    player_ids = itertools.count((session.scalar(select(func.max(PlayerRow.id))) or 0) + 1)
    pool = internationals.eligible_players(session)
    year = database.FIRST_SEASON_YEAR
    for nation in NATIONS:
        for player in rules.reinforcements(nation, pool[nation.code], player_ids, rng, year):
            session.add(PlayerRow.from_domain(player))
    session.commit()


@dataclass
class Group:
    """Un championnat et ses clubs, ou les sélections nationales."""

    code: str
    name: str
    teams: list[tuple[int, str]]


def groups(session: Session) -> list[Group]:
    """Les équipes que l'on peut choisir : les clubs par championnat (dans l'ordre de
    data/leagues.py, Top 14 en tête), puis les sélections."""
    clubs: dict[str, list[tuple[int, str]]] = {}
    for club_id, name, league in session.execute(
        select(ClubRow.id, ClubRow.name, ClubRow.league).order_by(ClubRow.name)
    ):
        clubs.setdefault(league, []).append((club_id, name))
    order = {league.code: index for index, league in enumerate(LEAGUES)}
    out = [
        Group(code, league_config(code).name, clubs[code])
        for code in sorted(clubs, key=lambda code: order.get(code, len(order)))
    ]
    if internationals.has_nations(session):
        nations = sorted(((n.id, n.name) for n in NATIONS), key=lambda team: team[1])
        out.append(Group("nations", "Sélections nationales", nations))
    return out


def names(session: Session) -> dict[int, str]:
    return {
        **dict(session.execute(select(ClubRow.id, ClubRow.name)).all()),
        **{nation.id: nation.name for nation in NATIONS},
    }


# --- Les équipes du match ----------------------------------------------------------------


def _squad(session: Session, nation_id: int, opponent: int, day: datetime.date) -> list[int]:
    """La liste du staff de la sélection, sans les joueurs du club adverse (un
    international de Toulouse ne joue pas contre son club)."""
    nation = NATIONS_BY_ID[nation_id]
    pool = internationals.eligible_players(session, {nation.code})[nation.code]
    pool = [p for p in pool if p.club_id != opponent]
    return [p.id for p in rules.pick_squad(pool, day)]


def _teams(session: Session, row: FriendlyRow) -> tuple[Club, Club]:
    """Les deux équipes du match, reconstruites depuis le monde de référence."""
    ids = (row.home_id, row.away_id)
    clubs = load_clubs(session, [team for team in ids if team not in NATIONS_BY_ID])
    wanted = [player_id for team in ids for player_id in row.squads.get(str(team), [])]
    players = {
        p.id: p.to_domain()
        for p in session.scalars(select(PlayerRow).where(PlayerRow.id.in_(wanted)))
    }
    teams = []
    for team in ids:
        if team in NATIONS_BY_ID:
            squad = [players[i] for i in row.squads[str(team)] if i in players]
            teams.append(rules.national_team(NATIONS_BY_ID[team], squad))
        else:
            teams.append(clubs[team])
        # Le XV composé par le joueur ; celui de l'adversaire reste au staff.
        if team == row.my_id:
            teams[-1].lineup_choice = list(row.lineup or [])
    return teams[0], teams[1]


def prepare(session: Session, user_id: int, home_id: int, away_id: int, my_id: int) -> FriendlyRow:
    """Prépare le match libre du compte (et remplace celui qu'il avait) : l'affiche et la
    liste de chaque sélection. Le joueur compose ensuite son XV (`set_lineup`), puis
    donne le coup d'envoi (`kick_off`)."""
    if home_id == away_id:
        raise ValueError("Choisis deux équipes différentes")
    if my_id not in (home_id, away_id):
        raise ValueError("Tu diriges une des deux équipes du match")
    known = names(session)
    if home_id not in known or away_id not in known:
        raise ValueError("Équipe inconnue")
    day = datetime.date.today()
    squads = {
        str(team): _squad(session, team, other, day)
        for team, other in ((home_id, away_id), (away_id, home_id))
        if team in NATIONS_BY_ID
    }
    now = accounts._now()
    row = FriendlyRow(
        user_id=user_id,
        home_id=home_id,
        away_id=away_id,
        my_id=my_id,
        date=day,
        squads=squads,
        lineup=[],
        state={},
        updated_at=now,
    )
    with _accounts_session() as accounts_session:
        stale = now - datetime.timedelta(days=KEEP_DAYS)
        accounts_session.execute(
            delete(FriendlyRow).where(
                (FriendlyRow.user_id == user_id) | (FriendlyRow.updated_at < stale)
            )
        )
        accounts_session.add(row)
        accounts_session.commit()
    return row


def setup(user_id: int) -> FriendlyRow | None:
    """Le match libre du compte, lancé ou non (None s'il n'en a pas)."""
    with _accounts_session() as accounts_session:
        return accounts_session.get(FriendlyRow, user_id)


def my_team(session: Session, row: FriendlyRow) -> Club:
    """L'équipe du joueur, avec le XV qu'il a composé (le staff pourvoit le reste)."""
    home, away = _teams(session, row)
    return home if home.id == row.my_id else away


def set_lineup(session: Session, row: FriendlyRow, lineup: list[int | None]) -> FriendlyRow:
    """Le XV voulu par le joueur, place par place (vide : le staff compose)."""
    if row.started:
        raise ValueError("Le match a commencé : les changements se font depuis le banc")
    squad = {player.id for player in my_team(session, row).players}
    if len(lineup) > len(SLOT_POSITIONS):
        raise ValueError(f"Un XV compte {len(SLOT_POSITIONS)} places")
    chosen = [player_id for player_id in lineup if player_id is not None]
    if any(player_id not in squad for player_id in chosen) or len(set(chosen)) < len(chosen):
        raise ValueError("Un joueur du XV n'est pas dans ton effectif")
    with _accounts_session() as accounts_session:
        stored = accounts_session.get(FriendlyRow, row.user_id)
        stored.lineup = list(lineup)
        stored.updated_at = accounts._now()
        accounts_session.commit()
        return stored


def kick_off(session: Session, row: FriendlyRow) -> Live:
    """Coup d'envoi : le XV de chaque équipe (celui du joueur, sinon celui du staff) et
    la tactique du staff adverse. Un match déjà lancé est repris tel quel."""
    if row.started:
        return load(session, row.user_id)
    home, away = _teams(session, row)
    known = names(session)
    opponent = away if home.id == row.my_id else home
    opponent_tactics = staff_tactics(team_strength(opponent, row.date))
    match = LiveMatch(
        home,
        away,
        rng=random.Random(),
        day=row.date,
        home_tactics=opponent_tactics if home is opponent else Tactics(),
        away_tactics=opponent_tactics if away is opponent else Tactics(),
        auto={opponent.id},
        # Une sélection n'a pas de stade dans le jeu : temps sec chez elle.
        weather=forecast(home, row.date if home.id not in NATIONS_BY_ID else None),
        derby=derby(known[row.home_id], known[row.away_id]) is not None,
    )
    live = Live(row=row, match=match, match_row=row)
    save(live)
    return live


def replay(user_id: int) -> FriendlyRow | None:
    """Remet le match libre du compte avant le coup d'envoi : mêmes équipes, mêmes
    sélections, même XV composé (None s'il n'en a pas)."""
    with _accounts_session() as accounts_session:
        stored = accounts_session.get(FriendlyRow, user_id)
        if stored is None:
            return None
        stored.state = {}
        stored.updated_at = accounts._now()
        accounts_session.commit()
        return stored


def load(session: Session, user_id: int) -> Live | None:
    """Le match libre en cours du compte (None s'il n'en a pas, ou pas encore lancé)."""
    row = setup(user_id)
    if row is None or not row.started:
        return None
    home, away = _teams(session, row)
    match = LiveMatch.from_state(home, away, row.state)
    return Live(row=row, match=match, match_row=row)


def save(live: Live) -> None:
    """Enregistre où en est le match."""
    live.save()
    with _accounts_session() as accounts_session:
        row = accounts_session.get(FriendlyRow, live.row.user_id)
        row.state = live.row.state
        row.updated_at = accounts._now()
        accounts_session.commit()


def drop(user_id: int) -> None:
    """Oublie le match libre du compte."""
    with _accounts_session() as accounts_session:
        accounts_session.execute(delete(FriendlyRow).where(FriendlyRow.user_id == user_id))
        accounts_session.commit()
