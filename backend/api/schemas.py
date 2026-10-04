"""Formats des requêtes et réponses de l'API (modèles Pydantic).

Ils sont séparés des objets du domaine : on choisit ce qu'on expose au frontend
sans contraindre le moteur.
"""

import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from engine.economy import FacilityKind, TransactionCategory, market_value
from engine.match_engine import TeamStrength
from engine.transfers import DealKind
from models import (
    EventType,
    Injury,
    InjurySeverity,
    InjurySource,
    Match,
    Player,
    Position,
    Protocol,
    Squad,
    StaffRole,
    Stage,
)

# --- Clubs et joueurs ----------------------------------------------------------------


class ClubRef(BaseModel):
    """Juste de quoi nommer un club."""

    id: int
    name: str


class InjuryOut(BaseModel):
    """Une blessure et son état à la date du jour dans le jeu."""

    id: int
    player_id: int
    severity: InjurySeverity
    kind: str
    source: InjurySource
    occurred_on: datetime.date
    return_date: datetime.date
    fragile_until: datetime.date
    weeks_total: int  # durée prévue d'indisponibilité
    weeks_left: int  # semaines restantes (0 si revenu)
    protocol: Protocol
    protocol_chosen: bool
    relapse: bool
    relapse_risk: float  # par match, pendant la période de fragilité
    # active : indisponible ; fragile : revenu, risque de rechute ; healed : guéri.
    status: Literal["active", "fragile", "healed"]

    @classmethod
    def from_injury(cls, injury: Injury, day: datetime.date) -> "InjuryOut":
        if injury.is_active(day):
            status = "active"
        elif injury.is_fragile(day):
            status = "fragile"
        else:
            status = "healed"
        return cls(
            id=injury.id,
            player_id=injury.player_id,
            severity=injury.severity,
            kind=injury.kind,
            source=injury.source,
            occurred_on=injury.occurred_on,
            return_date=injury.return_date,
            fragile_until=injury.fragile_until,
            weeks_total=(injury.return_date - injury.occurred_on).days // 7,
            weeks_left=injury.weeks_left(day),
            protocol=injury.protocol,
            protocol_chosen=injury.protocol_chosen,
            relapse=injury.relapse,
            relapse_risk=injury.relapse_risk,
            status=status,
        )


class PlayerOut(BaseModel):
    # Permet de construire le schéma directement depuis un `Player` du domaine.
    model_config = ConfigDict(from_attributes=True)

    id: int
    first_name: str
    last_name: str
    name: str
    age: int
    position: Position
    pace: int
    power: int
    handling: int
    passing: int
    kicking: int
    tackling: int
    scrum: int
    lineout: int
    overall: float
    wage: int
    value: int
    contract_until: int  # dernière saison sous contrat (2026 = jusqu'à la fin de 2026-27)
    loaned_from: int | None  # club propriétaire si le joueur est prêté
    squad: Squad
    loaned_from_name: str | None = None
    # Blessure en cours ou période de fragilité ; None si le joueur est apte.
    injury: InjuryOut | None = None

    @classmethod
    def from_player(
        cls,
        player: Player,
        day: datetime.date | None = None,
        club_names: dict[int, str] | None = None,
    ) -> "PlayerOut":
        # Tous les champs viennent du joueur, sauf ceux qui se calculent.
        computed = {"value", "injury", "loaned_from_name"}
        fields = {name: getattr(player, name) for name in cls.model_fields if name not in computed}
        injury = None
        if day is not None and (player.is_injured(day) or player.is_fragile(day)):
            injury = InjuryOut.from_injury(player.injury, day)
        owner = (club_names or {}).get(player.loaned_from) if player.loaned_from else None
        return cls(**fields, value=market_value(player), injury=injury, loaned_from_name=owner)


class StrengthOut(BaseModel):
    """Notes collectives sur 20, calculées par le moteur sur le XV de départ."""

    set_piece: float
    pack: float
    attack: float
    defense: float
    kicking: int
    kicker_id: int
    lineup_ids: list[int]

    @classmethod
    def from_team(cls, team: TeamStrength) -> "StrengthOut":
        return cls(
            set_piece=round(team.set_piece, 1),
            pack=round(team.pack, 1),
            attack=round(team.attack, 1),
            defense=round(team.defense, 1),
            kicking=team.kicker.kicking,
            kicker_id=team.kicker.id,
            lineup_ids=[p.id for p in team.lineup],
        )


class ClubSummary(BaseModel):
    id: int
    name: str
    player_count: int
    # Moyenne des 4 notes collectives : un indicateur rapide du niveau.
    level: float


class FacilitiesOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    stadium_capacity: int
    training_level: int
    academy_level: int


class ClubDetail(BaseModel):
    id: int
    name: str
    balance: int
    facilities: FacilitiesOut
    strength: StrengthOut
    players: list[PlayerOut]


# --- Matchs --------------------------------------------------------------------------


class SimulateMatchIn(BaseModel):
    home_club_id: int
    away_club_id: int
    # Graine optionnelle pour rejouer exactement le même match.
    seed: int | None = None


class MatchEventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    minute: int
    type: EventType
    club_id: int
    player_id: int | None
    points: int


class MatchOut(BaseModel):
    """Un match avec le détail de ses événements."""

    id: int | None
    home_club_id: int
    away_club_id: int
    matchday: int
    stage: Stage
    date: datetime.date | None
    neutral: bool
    home_score: int
    away_score: int
    home_tries: int
    away_tries: int
    events: list[MatchEventOut]

    @classmethod
    def from_match(cls, match: Match) -> "MatchOut":
        return cls(
            id=match.id,
            home_club_id=match.home_club_id,
            away_club_id=match.away_club_id,
            matchday=match.matchday,
            stage=match.stage,
            date=match.date,
            neutral=match.neutral,
            home_score=match.home_score,
            away_score=match.away_score,
            home_tries=match.tries_for(match.home_club_id),
            away_tries=match.tries_for(match.away_club_id),
            events=[MatchEventOut.model_validate(e) for e in match.events],
        )


class MatchSummary(BaseModel):
    """Une affiche du calendrier, avec son score si elle a été jouée."""

    id: int
    matchday: int
    stage: Stage
    date: datetime.date
    neutral: bool
    home: ClubRef
    away: ClubRef
    home_score: int | None
    away_score: int | None


class MatchdayOut(BaseModel):
    matchday: int
    stage: Stage
    date: datetime.date
    matches: list[MatchSummary]


# --- Carrière ------------------------------------------------------------------------


class CareerIn(BaseModel):
    manager_name: str = Field(min_length=1, max_length=100)
    club_id: int


class CareerOut(BaseModel):
    id: int
    manager_name: str
    club_id: int
    club_name: str


# --- Saisons -------------------------------------------------------------------------


class StandingOut(BaseModel):
    rank: int
    club_id: int
    club_name: str
    played: int
    won: int
    drawn: int
    lost: int
    points_for: int
    points_against: int
    points_difference: int
    tries_for: int
    offensive_bonus: int
    defensive_bonus: int
    league_points: int


class SeasonOut(BaseModel):
    year: int
    # regular : journées à jouer ; playoffs : phases finales en cours ; finished : finale jouée.
    phase: Literal["regular", "playoffs", "finished"]
    regular_matchdays: int
    club_count: int
    playoff_qualifiers: int
    next_matchday: MatchdayOut | None
    standings: list[StandingOut]  # saison régulière seulement
    matches: list[MatchSummary]  # tout le calendrier, phases finales comprises
    champion: ClubRef | None


class PlayOut(BaseModel):
    played: MatchdayOut
    season: SeasonOut
    # Blessés de la journée (matchs et entraînement) dans le club dirigé.
    injuries: list["InjuryCase"]


# --- Finances, staff, infrastructures, transferts (club du joueur) ---------------------


class TransactionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    date: datetime.date
    matchday: int | None
    category: TransactionCategory
    label: str
    amount: int
    balance_after: int


class FinancesOut(BaseModel):
    balance: int
    player_wages: int  # masse salariale des pros, par saison
    youth_wages: int  # espoirs
    staff_wages: int
    squad_value: int
    squad_size: int
    transactions: list[TransactionOut]  # de la plus récente à la plus ancienne


class StaffMemberOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    role: StaffRole
    level: int
    wage: int


class StaffSlotOut(BaseModel):
    role: StaffRole
    member: StaffMemberOut | None
    severance: int | None  # indemnité si on licencie le titulaire


class StaffOverview(BaseModel):
    balance: int
    slots: list[StaffSlotOut]
    candidates: list[StaffMemberOut]


class UpgradeOut(BaseModel):
    kind: FacilityKind
    current: int  # capacité du stade, ou niveau
    next: int | None  # None = maximum atteint
    cost: int | None
    affordable: bool


class FacilitiesOverview(BaseModel):
    balance: int
    facilities: FacilitiesOut
    upgrades: list[UpgradeOut]


class ListingOut(BaseModel):
    """Un joueur d'un autre club et les voies possibles pour le recruter."""

    player: PlayerOut
    club_id: int
    club_name: str
    club_level: float
    years_left: int  # saisons de contrat restantes, celle en cours comprise
    playing_time: str  # titulaire, remplaçant, réserviste (dans son club)
    transfer_fee: int | None  # indemnité demandée à l'ouverture ; None = intransférable
    loanable: bool
    precontract: bool  # dernière année de contrat : négociable sans indemnité
    talks_closed_until: datetime.date | None  # il ne veut plus discuter avant cette date


class NegotiationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    player_id: int
    player_name: str
    club_name: str  # club actuel du joueur
    kind: DealKind
    stage: Literal["club", "player", "agreed", "done", "failed"]
    opened_on: datetime.date
    rounds: int
    patience: int  # de 6 (serein) à 0 (il s'en va)
    fee_demand: int | None
    fee: int | None
    wage_demand: int | None
    wage: int | None
    years: int | None
    message: str
    closed_by: Literal["them", "me"] | None
    cooldown_until: datetime.date | None


class TransfersOverview(BaseModel):
    balance: int
    season_year: int
    squad_size: int
    squad_min: int
    squad_max: int
    my_level: float
    listings: list[ListingOut]
    negotiations: list[NegotiationOut]  # en cours, et pré-contrats en attente de l'intersaison


class DealOption(BaseModel):
    """Une voie de recrutement : possible ou non, et pourquoi."""

    kind: DealKind
    available: bool
    reason: str
    fee_demand: int | None = None  # transfert : indemnité demandée par le club (son ouverture)
    wage_demand: int | None = None  # transfert, pré-contrat : salaire demandé (son ouverture)
    wage: int | None = None  # prêt : salaire actuel, à ta charge


class TransferTargetOut(BaseModel):
    """Approche d'un joueur : sa situation et ce qu'il attend."""

    player: PlayerOut
    club: ClubRef
    club_level: float
    my_level: float
    years_left: int
    playing_time_now: str
    playing_time_here: str
    preferred_years: tuple[int, int]  # durée de contrat qu'il recherche (min, max)
    talks_closed_until: datetime.date | None  # rupture récente : pas de discussion avant
    grudges: int  # ruptures passées de son fait : il sera plus exigeant et moins patient
    options: list[DealOption]
    negotiation: NegotiationOut | None


class OpenNegotiationIn(BaseModel):
    kind: DealKind


class OfferIn(BaseModel):
    fee: int | None = Field(default=None, ge=0)  # étape club
    wage: int | None = Field(default=None, ge=0)  # étape joueur
    years: int = Field(default=2, ge=1, le=5)  # durée de contrat proposée (transfert, pré-contrat)


class OfferOut(BaseModel):
    accepted: bool  # l'offre de cette étape est acceptée
    concluded: bool  # l'accord est complet (joueur arrivé, ou pré-contrat signé)
    message: str
    negotiation: NegotiationOut
    overview: TransfersOverview


# --- Centre de formation -------------------------------------------------------------


class AcademyOverview(BaseModel):
    academy_level: int
    intake_per_year: int  # jeunes qui entrent à chaque intersaison
    youth_max_age: int  # au-delà, un pro ne redescend plus chez les espoirs
    youth_exit_age: int  # un espoir non promu à cet âge quitte le centre
    squad_size: int  # effectif pro
    squad_min: int
    squad_max: int
    youths: list[PlayerOut]
    eligible_pros: list[PlayerOut]  # pros assez jeunes pour redescendre
    strength: StrengthOut  # XV espoirs
    standings: list[StandingOut]
    matches: list[MatchSummary]
    next_matchday: MatchdayOut | None
    last_matchday: MatchdayOut | None


# --- Médical -------------------------------------------------------------------------


class PlayerRef(BaseModel):
    id: int
    name: str
    position: Position
    age: int
    overall: float


class ProtocolOption(BaseModel):
    """Ce que donnerait un protocole pour une blessure dont le protocole reste à choisir."""

    protocol: Protocol
    return_date: datetime.date
    weeks: int
    relapse_risk: float
    cost: int
    affordable: bool


class InjuryCase(BaseModel):
    player: PlayerRef
    injury: InjuryOut
    options: list[ProtocolOption]  # vide une fois le protocole fixé


class MedicalOverview(BaseModel):
    balance: int
    today: datetime.date
    squad_size: int
    available: int  # joueurs aptes
    physio_level: int  # 0 = poste vacant
    doctor_level: int
    fragile_weeks: int
    injured: list[InjuryCase]  # indisponibles
    fragile: list[InjuryCase]  # revenus, sous surveillance
    history: list[InjuryCase]  # blessures guéries, de la plus récente à la plus ancienne
