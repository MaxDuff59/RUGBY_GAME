"""Tables SQLAlchemy et conversion vers/depuis les objets du domaine.

Le moteur ne voit jamais ces classes : l'API charge des lignes, les convertit
avec `to_domain()`, appelle le moteur, puis sauvegarde le résultat.
"""

import datetime

from sqlalchemy import JSON, Date, ForeignKey, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from models.domain import (
    AmenityKind,
    Career,
    Club,
    EventType,
    Facilities,
    Injury,
    InjurySeverity,
    InjurySource,
    Match,
    MatchEvent,
    Player,
    Position,
    Protocol,
    Squad,
    StaffMember,
    StaffRole,
    Stage,
    StandSide,
)


class Base(DeclarativeBase):
    pass


class ClubRow(Base):
    __tablename__ = "clubs"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True)
    # Championnat (data/leagues.py) ; change à l'intersaison en cas de montée ou de descente.
    league: Mapped[str] = mapped_column(String(12), default="top14")
    balance: Mapped[int] = mapped_column(default=0)
    stadium_capacity: Mapped[int] = mapped_column(default=4000)
    training_level: Mapped[int] = mapped_column(default=1)
    academy_level: Mapped[int] = mapped_column(default=1)
    # Aménagements des tribunes : {"north": ["sponsor", "buvette"], ...}. À réassigner
    # en entier pour que SQLAlchemy voie le changement.
    stands: Mapped[dict] = mapped_column(JSON, default=dict)
    # XV choisi par le manager : un identifiant de joueur (ou null) par place, dans
    # l'ordre de SLOT_POSITIONS (engine/match_engine.py). Vide : le staff compose.
    lineup_choice: Mapped[list] = mapped_column(JSON, default=list)
    # Maillots dessinés par le manager, par tenue : {"home": {...}, "away": {...},
    # "third": {...}} (motif, trois couleurs, sponsor). Une tenue absente prend le maillot
    # aux couleurs du club, que l'interface compose elle-même. À réassigner en entier.
    jerseys: Mapped[dict] = mapped_column(JSON, default=dict)
    # Le maillot third s'achète (engine/economy.py) avant de pouvoir être dessiné.
    third_kit: Mapped[bool] = mapped_column(default=False)
    # Sponsors du maillot (engine/sponsors.py) : [{"sponsor": "volt", "placement": "chest"}].
    # À réassigner en entier.
    sponsors: Mapped[list] = mapped_column(JSON, default=list)

    # Pros et espoirs sont dans la même table, séparés par `squad`.
    # lazy="selectin" : les listes se chargent en une requête par lot, pas une par
    # ligne ; indispensable quand la base est sur un serveur distant (Postgres).
    players: Mapped[list["PlayerRow"]] = relationship(
        primaryjoin="and_(PlayerRow.club_id == ClubRow.id, PlayerRow.squad == 'pro')",
        foreign_keys="PlayerRow.club_id",
        overlaps="youths,club",
        order_by="PlayerRow.id",
        lazy="selectin",
    )
    youths: Mapped[list["PlayerRow"]] = relationship(
        primaryjoin="and_(PlayerRow.club_id == ClubRow.id, PlayerRow.squad == 'youth')",
        foreign_keys="PlayerRow.club_id",
        overlaps="players,club",
        order_by="PlayerRow.id",
        lazy="selectin",
    )
    staff: Mapped[list["StaffRow"]] = relationship(
        back_populates="club", order_by="StaffRow.id", lazy="selectin"
    )

    def to_domain(self) -> Club:
        return Club(
            id=self.id,
            name=self.name,
            players=[p.to_domain() for p in self.players],
            youths=[p.to_domain() for p in self.youths],
            staff=[s.to_domain() for s in self.staff],
            balance=self.balance,
            facilities=self.facilities(),
            league=self.league,
            lineup_choice=list(self.lineup_choice or []),
        )

    def facilities(self) -> Facilities:
        return Facilities(
            stadium_capacity=self.stadium_capacity,
            training_level=self.training_level,
            academy_level=self.academy_level,
            stands={
                StandSide(side): [AmenityKind(kind) for kind in kinds]
                for side, kinds in (self.stands or {}).items()
            },
        )

    def save_facilities(self, facilities: Facilities) -> None:
        self.stadium_capacity = facilities.stadium_capacity
        self.training_level = facilities.training_level
        self.academy_level = facilities.academy_level
        self.stands = {
            side.value: [kind.value for kind in kinds]
            for side, kinds in facilities.stands.items()
            if kinds
        }

    @classmethod
    def from_domain(cls, club: Club) -> "ClubRow":
        return cls(
            id=club.id,
            name=club.name,
            league=club.league,
            balance=club.balance,
            stadium_capacity=club.facilities.stadium_capacity,
            training_level=club.facilities.training_level,
            academy_level=club.facilities.academy_level,
            stands={
                side.value: [kind.value for kind in kinds]
                for side, kinds in club.facilities.stands.items()
                if kinds
            },
            players=[PlayerRow.from_domain(p) for p in club.players],
            youths=[PlayerRow.from_domain(p) for p in club.youths],
            staff=[StaffRow.from_domain(s) for s in club.staff],
        )


class PlayerRow(Base):
    __tablename__ = "players"

    id: Mapped[int] = mapped_column(primary_key=True)
    first_name: Mapped[str] = mapped_column(String(50))
    last_name: Mapped[str] = mapped_column(String(50))
    age: Mapped[int]
    position: Mapped[str] = mapped_column(String(12))
    pace: Mapped[int]
    power: Mapped[int]
    handling: Mapped[int]
    passing: Mapped[int]
    kicking: Mapped[int]
    tackling: Mapped[int]
    scrum: Mapped[int]
    lineout: Mapped[int]
    stamina: Mapped[int] = mapped_column(server_default="12")
    wage: Mapped[int] = mapped_column(default=0)
    contract_until: Mapped[int] = mapped_column(default=0)
    club_id: Mapped[int | None] = mapped_column(ForeignKey("clubs.id"))
    loaned_from: Mapped[int | None] = mapped_column(ForeignKey("clubs.id"))
    squad: Mapped[str] = mapped_column(String(5), default=Squad.PRO.value)
    photo: Mapped[str | None] = mapped_column(String(300))
    # Nationalité sportive (data/nations.py), None si elle est inconnue.
    nationality: Mapped[str | None] = mapped_column(String(3))

    club: Mapped[ClubRow | None] = relationship(
        foreign_keys=[club_id], overlaps="players,youths", viewonly=True
    )
    # Dossier médical complet ; le domaine ne garde que la blessure la plus récente.
    injuries: Mapped[list["InjuryRow"]] = relationship(
        back_populates="player",
        cascade="all, delete-orphan",
        order_by="InjuryRow.id",
        lazy="selectin",
    )

    @property
    def latest_injury(self) -> "InjuryRow | None":
        return max(self.injuries, key=lambda i: (i.occurred_on, i.id), default=None)

    def to_domain(self) -> Player:
        latest = self.latest_injury
        return Player(
            id=self.id,
            first_name=self.first_name,
            last_name=self.last_name,
            age=self.age,
            position=Position(self.position),
            pace=self.pace,
            power=self.power,
            handling=self.handling,
            passing=self.passing,
            kicking=self.kicking,
            tackling=self.tackling,
            scrum=self.scrum,
            lineout=self.lineout,
            stamina=self.stamina,
            club_id=self.club_id,
            wage=self.wage,
            injury=latest.to_domain() if latest is not None else None,
            contract_until=self.contract_until,
            loaned_from=self.loaned_from,
            squad=Squad(self.squad),
            photo=self.photo,
            nationality=self.nationality,
        )

    @classmethod
    def from_domain(cls, player: Player) -> "PlayerRow":
        return cls(
            id=player.id,
            first_name=player.first_name,
            last_name=player.last_name,
            age=player.age,
            position=player.position.value,
            club_id=player.club_id,
            wage=player.wage,
            contract_until=player.contract_until,
            loaned_from=player.loaned_from,
            squad=player.squad.value,
            photo=player.photo,
            nationality=player.nationality,
            **player.attributes,
        )


class InjuryRow(Base):
    """Une blessure, en cours ou passée (voir engine/medical.py)."""

    __tablename__ = "injuries"

    id: Mapped[int] = mapped_column(primary_key=True)
    player_id: Mapped[int] = mapped_column(ForeignKey("players.id"))
    severity: Mapped[str] = mapped_column(String(10))
    kind: Mapped[str] = mapped_column(String(100))
    source: Mapped[str] = mapped_column(String(10))
    occurred_on: Mapped[datetime.date] = mapped_column(Date)
    base_weeks: Mapped[int]
    return_date: Mapped[datetime.date] = mapped_column(Date)
    protocol: Mapped[str] = mapped_column(String(12), default=Protocol.STANDARD.value)
    protocol_chosen: Mapped[bool] = mapped_column(default=True)
    relapse: Mapped[bool] = mapped_column(default=False)
    relapse_risk: Mapped[float] = mapped_column(default=0.0)

    player: Mapped[PlayerRow] = relationship(back_populates="injuries")

    def to_domain(self) -> Injury:
        return Injury(
            id=self.id,
            player_id=self.player_id,
            severity=InjurySeverity(self.severity),
            kind=self.kind,
            source=InjurySource(self.source),
            occurred_on=self.occurred_on,
            base_weeks=self.base_weeks,
            return_date=self.return_date,
            protocol=Protocol(self.protocol),
            protocol_chosen=self.protocol_chosen,
            relapse=self.relapse,
            relapse_risk=self.relapse_risk,
        )

    @classmethod
    def from_domain(cls, injury: Injury) -> "InjuryRow":
        return cls(
            id=injury.id,
            player_id=injury.player_id,
            severity=injury.severity.value,
            kind=injury.kind,
            source=injury.source.value,
            occurred_on=injury.occurred_on,
            base_weeks=injury.base_weeks,
            return_date=injury.return_date,
            protocol=injury.protocol.value,
            protocol_chosen=injury.protocol_chosen,
            relapse=injury.relapse,
            relapse_risk=injury.relapse_risk,
        )

    def update_from(self, injury: Injury) -> None:
        """Recopie les champs qui changent avec le protocole."""
        self.protocol = injury.protocol.value
        self.protocol_chosen = injury.protocol_chosen
        self.return_date = injury.return_date
        self.relapse_risk = injury.relapse_risk


class StaffRow(Base):
    __tablename__ = "staff"

    id: Mapped[int] = mapped_column(primary_key=True)
    first_name: Mapped[str] = mapped_column(String(50))
    last_name: Mapped[str] = mapped_column(String(50))
    role: Mapped[str] = mapped_column(String(20))
    level: Mapped[int]
    wage: Mapped[int]
    # NULL = disponible sur le marché.
    club_id: Mapped[int | None] = mapped_column(ForeignKey("clubs.id"))

    club: Mapped[ClubRow | None] = relationship(back_populates="staff")

    def to_domain(self) -> StaffMember:
        return StaffMember(
            id=self.id,
            first_name=self.first_name,
            last_name=self.last_name,
            role=StaffRole(self.role),
            level=self.level,
            wage=self.wage,
            club_id=self.club_id,
        )

    @classmethod
    def from_domain(cls, member: StaffMember) -> "StaffRow":
        return cls(
            id=member.id,
            first_name=member.first_name,
            last_name=member.last_name,
            role=member.role.value,
            level=member.level,
            wage=member.wage,
            club_id=member.club_id,
        )


class SeasonRow(Base):
    """Une saison : les matchs de tous les championnats, chacun avec son calendrier."""

    __tablename__ = "seasons"

    id: Mapped[int] = mapped_column(primary_key=True)
    year: Mapped[int] = mapped_column(unique=True)
    # Graine du hasard de la saison (engine/season.py, `rng_for`) : avec elle, une
    # journée rejouée dans le même état donne le même résultat. None : saison
    # d'avant ce champ, qui en tire une à sa prochaine journée.
    seed: Mapped[int | None] = mapped_column(default=None)

    # Le classement n'est pas stocké : il se recalcule à partir des matchs.
    # Les matchs des pros et ceux des espoirs partagent la table, séparés par `squad`.
    matches: Mapped[list["MatchRow"]] = relationship(
        primaryjoin="and_(MatchRow.season_id == SeasonRow.id, MatchRow.squad == 'pro')",
        overlaps="youth_matches,season",
        order_by="MatchRow.id",
        lazy="selectin",
    )
    youth_matches: Mapped[list["MatchRow"]] = relationship(
        primaryjoin="and_(MatchRow.season_id == SeasonRow.id, MatchRow.squad == 'youth')",
        overlaps="matches,season",
        order_by="MatchRow.id",
        lazy="selectin",
    )


def _events_from_json(events: list[dict]) -> list[MatchEvent]:
    return [
        MatchEvent(
            minute=e["minute"],
            type=EventType(e["type"]),
            club_id=e["club_id"],
            player_id=e.get("player_id"),
            other_player_id=e.get("other_player_id"),
        )
        for e in events
    ]


def _events_to_json(events: list[MatchEvent]) -> list[dict]:
    return [
        {
            "minute": e.minute,
            "type": e.type.value,
            "club_id": e.club_id,
            "player_id": e.player_id,
            "other_player_id": e.other_player_id,
        }
        for e in events
    ]


class MatchRow(Base):
    __tablename__ = "matches"

    id: Mapped[int] = mapped_column(primary_key=True)
    # Pas de saison pour un match amical.
    season_id: Mapped[int | None] = mapped_column(ForeignKey("seasons.id"))
    # Championnat du match (les clubs peuvent en changer d'une saison à l'autre).
    league: Mapped[str] = mapped_column(String(12), default="top14")
    matchday: Mapped[int] = mapped_column(default=0)
    home_club_id: Mapped[int] = mapped_column(ForeignKey("clubs.id"))
    away_club_id: Mapped[int] = mapped_column(ForeignKey("clubs.id"))
    home_score: Mapped[int | None]
    away_score: Mapped[int | None]
    stage: Mapped[str] = mapped_column(String(10), default=Stage.REGULAR.value)
    date: Mapped[datetime.date | None] = mapped_column(Date)
    neutral: Mapped[bool] = mapped_column(default=False)
    squad: Mapped[str] = mapped_column(String(5), default=Squad.PRO.value)
    # Événements stockés en JSON : suffisant tant qu'on ne fait pas de requêtes dessus.
    events: Mapped[list[dict]] = mapped_column(JSON, default=list)
    # XV de départ (identifiants de joueurs), pour les statistiques individuelles.
    home_lineup: Mapped[list[int]] = mapped_column(JSON, default=list)
    away_lineup: Mapped[list[int]] = mapped_column(JSON, default=list)

    season: Mapped[SeasonRow | None] = relationship(overlaps="matches,youth_matches", viewonly=True)

    @property
    def is_played(self) -> bool:
        return self.home_score is not None

    def to_domain(self) -> Match:
        return Match(
            id=self.id,
            home_club_id=self.home_club_id,
            away_club_id=self.away_club_id,
            matchday=self.matchday,
            home_score=self.home_score,
            away_score=self.away_score,
            stage=Stage(self.stage),
            date=self.date,
            neutral=self.neutral,
            events=_events_from_json(self.events),
            home_lineup=list(self.home_lineup or []),
            away_lineup=list(self.away_lineup or []),
            league=self.league,
        )

    @classmethod
    def from_domain(cls, match: Match, season_id: int | None = None) -> "MatchRow":
        return cls(
            id=match.id,
            season_id=season_id,
            league=match.league,
            matchday=match.matchday,
            home_club_id=match.home_club_id,
            away_club_id=match.away_club_id,
            home_score=match.home_score,
            away_score=match.away_score,
            stage=match.stage.value,
            date=match.date,
            neutral=match.neutral,
            events=_events_to_json(match.events),
            home_lineup=list(match.home_lineup),
            away_lineup=list(match.away_lineup),
        )


class LiveMatchRow(Base):
    """Le match du club dirigé en train d'être joué minute par minute (un seul à la fois).

    `state` : tout l'état du moteur (`LiveMatch.to_state`), pour reprendre le match
    à la minute où on l'a laissé, même après un redémarrage de l'API. La semaine
    d'entraînement de la journée a déjà eu lieu quand ce match commence :
    `my_injuries` garde les blessés à l'entraînement du club dirigé, pour les
    annoncer avec ceux du match.
    """

    __tablename__ = "live_matches"

    id: Mapped[int] = mapped_column(primary_key=True)
    match_id: Mapped[int] = mapped_column(ForeignKey("matches.id"), unique=True)
    my_injuries: Mapped[list[int]] = mapped_column(JSON, default=list)
    state: Mapped[dict] = mapped_column(JSON, default=dict)


class InternationalRow(Base):
    """Un match international (engine/internationals.py), dans sa propre table : les
    équipes y sont des sélections (`Nation.id`, data/nations.py), pas des clubs."""

    __tablename__ = "internationals"

    id: Mapped[int] = mapped_column(primary_key=True)
    season_id: Mapped[int] = mapped_column(ForeignKey("seasons.id"))
    # Code de la fenêtre (data/nations.py) ; `matchday` : numéro du match dans la fenêtre.
    competition: Mapped[str] = mapped_column(String(20))
    matchday: Mapped[int] = mapped_column(default=0)
    # Tour à élimination directe de la Coupe du monde, « regular » pour tout le reste.
    stage: Mapped[str] = mapped_column(
        String(10), default=Stage.REGULAR.value, server_default=Stage.REGULAR.value
    )
    home_id: Mapped[int]
    away_id: Mapped[int]
    home_score: Mapped[int | None]
    away_score: Mapped[int | None]
    date: Mapped[datetime.date] = mapped_column(Date)
    neutral: Mapped[bool] = mapped_column(default=False)
    events: Mapped[list[dict]] = mapped_column(JSON, default=list)
    home_lineup: Mapped[list[int]] = mapped_column(JSON, default=list)
    away_lineup: Mapped[list[int]] = mapped_column(JSON, default=list)

    @property
    def is_played(self) -> bool:
        return self.home_score is not None

    # Mêmes noms que `MatchRow`, pour ce qui lit l'un ou l'autre (match en direct).
    @property
    def home_club_id(self) -> int:
        return self.home_id

    @property
    def away_club_id(self) -> int:
        return self.away_id

    def to_domain(self) -> Match:
        return Match(
            id=self.id,
            home_club_id=self.home_id,
            away_club_id=self.away_id,
            matchday=self.matchday,
            home_score=self.home_score,
            away_score=self.away_score,
            stage=Stage(self.stage),
            date=self.date,
            neutral=self.neutral,
            events=_events_from_json(self.events),
            home_lineup=list(self.home_lineup or []),
            away_lineup=list(self.away_lineup or []),
            league=self.competition,
        )

    @classmethod
    def from_domain(cls, match: Match, season_id: int) -> "InternationalRow":
        return cls(
            id=match.id,
            season_id=season_id,
            competition=match.league,
            matchday=match.matchday,
            stage=match.stage.value,
            home_id=match.home_club_id,
            away_id=match.away_club_id,
            home_score=match.home_score,
            away_score=match.away_score,
            date=match.date,
            neutral=match.neutral,
            events=_events_to_json(match.events),
            home_lineup=list(match.home_lineup),
            away_lineup=list(match.away_lineup),
        )

    def write_result(self, match: Match) -> None:
        self.home_score, self.away_score = match.home_score, match.away_score
        self.events = _events_to_json(match.events)
        self.home_lineup, self.away_lineup = list(match.home_lineup), list(match.away_lineup)


class CallUpRow(Base):
    """La liste d'une sélection pour une fenêtre internationale : annoncée deux semaines
    avant son premier match, par le staff ou par le sélectionneur."""

    __tablename__ = "call_ups"

    id: Mapped[int] = mapped_column(primary_key=True)
    season_id: Mapped[int] = mapped_column(ForeignKey("seasons.id"))
    competition: Mapped[str] = mapped_column(String(20))
    nation: Mapped[str] = mapped_column(String(3))
    # Identifiants des joueurs retenus. À réassigner en entier.
    player_ids: Mapped[list[int]] = mapped_column(JSON, default=list)
    announced_on: Mapped[datetime.date] = mapped_column(Date)


class LiveInternationalRow(Base):
    """Le match international que le sélectionneur joue en direct (voir `LiveMatchRow`)."""

    __tablename__ = "live_internationals"

    id: Mapped[int] = mapped_column(primary_key=True)
    match_id: Mapped[int] = mapped_column(ForeignKey("internationals.id"), unique=True)
    state: Mapped[dict] = mapped_column(JSON, default=dict)


class SelectorRow(Base):
    """Partie sauvegardée d'un sélectionneur : la sélection nationale qu'il dirige.

    À part de `CareerRow` : tout ce qui gère un club (finances, transferts, staff...)
    ne voit alors aucune carrière, et tous les clubs sont menés par leur staff.
    """

    __tablename__ = "selectors"

    id: Mapped[int] = mapped_column(primary_key=True)
    manager_name: Mapped[str] = mapped_column(String(100))
    nation: Mapped[str] = mapped_column(String(3))
    # XV choisi, place par place, comme `ClubRow.lineup_choice`. À réassigner en entier.
    lineup_choice: Mapped[list] = mapped_column(JSON, default=list)


class CareerRow(Base):
    """Partie sauvegardée : le club dirigé par le joueur."""

    __tablename__ = "careers"

    id: Mapped[int] = mapped_column(primary_key=True)
    manager_name: Mapped[str] = mapped_column(String(100))
    club_id: Mapped[int] = mapped_column(ForeignKey("clubs.id"))

    def to_domain(self) -> Career:
        return Career(id=self.id, manager_name=self.manager_name, club_id=self.club_id)

    @classmethod
    def from_domain(cls, career: Career) -> "CareerRow":
        return cls(id=career.id, manager_name=career.manager_name, club_id=career.club_id)


class NegotiationRow(Base):
    """Négociation du club dirigé avec un joueur d'un autre club (api/routers/transfers.py).

    Étapes : `club` (indemnité à convenir), `player` (salaire à convenir),
    `agreed` (accord conclu ; un pré-contrat attend l'intersaison), `done`
    (joueur arrivé), `failed` (rompue).
    """

    __tablename__ = "negotiations"

    id: Mapped[int] = mapped_column(primary_key=True)
    club_id: Mapped[int] = mapped_column(ForeignKey("clubs.id"))
    player_id: Mapped[int] = mapped_column(ForeignKey("players.id"))
    kind: Mapped[str] = mapped_column(String(12))
    stage: Mapped[str] = mapped_column(String(8))
    opened_on: Mapped[datetime.date] = mapped_column(Date)
    rounds: Mapped[int] = mapped_column(default=0)  # offres refusées à l'étape en cours
    patience: Mapped[int] = mapped_column(default=6)  # à zéro, l'autre partie s'en va
    last_offer: Mapped[int | None]  # ta dernière offre à cette étape
    fee_demand: Mapped[int | None]  # indemnité demandée par le club (visible)
    fee_floor: Mapped[int | None]  # objectif du club (secret)
    fee: Mapped[int | None]  # indemnité convenue
    wage_demand: Mapped[int | None]  # salaire demandé par le joueur (visible)
    wage_floor: Mapped[int | None]  # objectif du joueur (secret)
    wage: Mapped[int | None]  # salaire convenu
    years: Mapped[int | None]  # durée du contrat convenue
    message: Mapped[str] = mapped_column(String(300), default="")  # dernière réponse
    # Rupture : qui a quitté la table ("them" ou "me"), et jusqu'à quand on ne rediscute pas.
    closed_by: Mapped[str | None] = mapped_column(String(4))
    cooldown_until: Mapped[datetime.date | None] = mapped_column(Date)

    player: Mapped[PlayerRow] = relationship()


class JokerRow(Base):
    """Joker médical du club dirigé : un agent libre recruté pour la durée d'une
    longue blessure (voir api/jokers.py).

    Statuts : `talks` (négociation en cours, voir `negotiation_id`), `active`
    (pige en cours), `ending` (pige terminée, le manager doit décider), `kept`
    (il a signé un vrai contrat), `left` (il est reparti).
    """

    __tablename__ = "jokers"

    id: Mapped[int] = mapped_column(primary_key=True)
    club_id: Mapped[int] = mapped_column(ForeignKey("clubs.id"))
    player_id: Mapped[int] = mapped_column(ForeignKey("players.id"))
    injury_id: Mapped[int] = mapped_column(ForeignKey("injuries.id"))
    negotiation_id: Mapped[int | None] = mapped_column(ForeignKey("negotiations.id"))
    status: Mapped[str] = mapped_column(String(8))
    signed_on: Mapped[datetime.date | None] = mapped_column(Date)

    player: Mapped[PlayerRow] = relationship()
    injury: Mapped[InjuryRow] = relationship()
    negotiation: Mapped["NegotiationRow | None"] = relationship()


class MoveRow(Base):
    """Un mouvement de joueur (transfert, prêt, signature, départ, retraite), inscrit
    au moment où il a lieu (api/moves.py) pour le journal (api/routers/journal.py).

    Le nom, le poste, l'âge et la note sont recopiés : le joueur peut ne plus avoir
    de ligne ensuite (retraite), d'où `player_id` sans clé étrangère.
    """

    __tablename__ = "moves"

    id: Mapped[int] = mapped_column(primary_key=True)
    date: Mapped[datetime.date] = mapped_column(Date)
    kind: Mapped[str] = mapped_column(String(12))  # `MoveKind`, engine/journal.py
    player_id: Mapped[int]
    player_name: Mapped[str] = mapped_column(String(101))
    position: Mapped[str] = mapped_column(String(12))
    age: Mapped[int]
    overall: Mapped[float]
    # None : sans club (agent libre avant, ou après).
    from_club_id: Mapped[int | None] = mapped_column(ForeignKey("clubs.id"))
    to_club_id: Mapped[int | None] = mapped_column(ForeignKey("clubs.id"))
    fee: Mapped[int | None]  # indemnité de transfert


class TransactionRow(Base):
    """Une opération financière d'un club (voir api/ledger.py)."""

    __tablename__ = "transactions"

    id: Mapped[int] = mapped_column(primary_key=True)
    club_id: Mapped[int] = mapped_column(ForeignKey("clubs.id"))
    date: Mapped[datetime.date] = mapped_column(Date)
    matchday: Mapped[int | None]  # journée concernée, s'il y en a une
    category: Mapped[str] = mapped_column(String(20))
    label: Mapped[str] = mapped_column(String(200))
    amount: Mapped[int]  # positif = recette, négatif = dépense
    balance_after: Mapped[int]


class PreseasonRankRow(Base):
    """Rang attendu d'un club avant une saison (niveau de son XV parmi les clubs de son
    championnat).

    Figé au tirage du calendrier : c'est lui qui fixe l'objectif de la direction
    (engine/board.py), même si l'effectif change en cours de saison.
    """

    __tablename__ = "preseason_ranks"

    id: Mapped[int] = mapped_column(primary_key=True)
    season_id: Mapped[int] = mapped_column(ForeignKey("seasons.id"))
    club_id: Mapped[int] = mapped_column(ForeignKey("clubs.id"))
    rank: Mapped[int]


class DismissalRow(Base):
    """Limogeage d'un manager par la direction de son club (engine/board.py).

    La carrière est supprimée ; le dernier limogeage s'affiche au choix du club suivant.
    """

    __tablename__ = "dismissals"

    id: Mapped[int] = mapped_column(primary_key=True)
    manager_name: Mapped[str] = mapped_column(String(100))
    club_id: Mapped[int] = mapped_column(ForeignKey("clubs.id"))
    date: Mapped[datetime.date] = mapped_column(Date)
    confidence: Mapped[float]

    club: Mapped[ClubRow] = relationship()

    @property
    def club_name(self) -> str:
        return self.club.name


class AffairRow(Base):
    """Une affaire entre deux matchs (engine/affairs.py) et la réponse du manager.

    En attente tant que `answered_on` est vide. Une fois réglée, ses `effects`
    s'ajoutent aux notes du club à la date `anchor` (dernier match joué à ce
    moment-là ; voir engine/notes.py, `Boost`). `choice` vide une fois réglée :
    le manager n'a pas répondu avant le match suivant.
    """

    __tablename__ = "affairs"

    id: Mapped[int] = mapped_column(primary_key=True)
    club_id: Mapped[int] = mapped_column(ForeignKey("clubs.id"))
    season_id: Mapped[int] = mapped_column(ForeignKey("seasons.id"))
    scenario: Mapped[str] = mapped_column(String(40))
    created_on: Mapped[datetime.date] = mapped_column(Date)
    context: Mapped[dict] = mapped_column(JSON, default=dict)  # variables des textes
    answered_on: Mapped[datetime.date | None] = mapped_column(Date)
    choice: Mapped[str | None] = mapped_column(String(40))
    outcome: Mapped[str] = mapped_column(String(300), default="")
    effects: Mapped[dict] = mapped_column(JSON, default=dict)  # note -> variation
    money: Mapped[int] = mapped_column(default=0)
    anchor: Mapped[datetime.date | None] = mapped_column(Date)
    # Promesse faite en répondant (« start » ou « win ») ; tranchée au match suivant.
    promise: Mapped[str | None] = mapped_column(String(8))
    promise_settled: Mapped[bool] = mapped_column(default=False)
