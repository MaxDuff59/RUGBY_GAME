"""Formats des requêtes et réponses de l'API (modèles Pydantic).

Ils sont séparés des objets du domaine : on choisit ce qu'on expose au frontend
sans contraindre le moteur.
"""

import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from engine.economy import FacilityKind, TransactionCategory, market_value
from engine.match_engine import TeamStrength
from engine.notes import Note
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


class PlayerSeasonStats(BaseModel):
    """Statistiques individuelles sur la saison en cours (matchs où il était titulaire)."""

    year: int | None
    matches: int
    tries: int
    conversions: int
    penalties: int
    drops: int
    points: int


class PeerOut(BaseModel):
    """Un joueur du même poste (et du même groupe) dans le championnat, pour les comparaisons."""

    id: int
    club_id: int
    name: str
    overall: float
    position_rating: float  # note au poste, critère de sélection du moteur
    pace: int
    power: int
    handling: int
    passing: int
    kicking: int
    tackling: int
    scrum: int
    lineout: int


class PlayerDetail(BaseModel):
    """Fiche complète d'un joueur : identité, comparaison au poste, notes, saison, blessures."""

    player: PlayerOut
    club: ClubRef | None
    # Identifiants du XV de départ de son club (vide s'il n'a pas de club).
    lineup_ids: list[int]
    starter: bool
    # Notes du moteur (sur 20) : mêlée, touche, portage, attaque, défense.
    ratings: dict[str, float]
    # Sa note à chaque poste, selon le critère de sélection du moteur.
    position_ratings: dict[Position, float]
    # Comparaison aux joueurs du même poste (et du même groupe : pros ou espoirs)
    # dans tous les clubs : part de ceux qu'il devance, par attribut et en note générale.
    better_than: dict[str, float]
    # Ces joueurs, lui compris, avec leurs attributs et leur note au poste.
    peers: list[PeerOut]
    season: PlayerSeasonStats
    # Toutes ses blessures, de la plus récente à la plus ancienne.
    injuries: list[InjuryOut]


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


class NoteStepOut(BaseModel):
    """Une note juste après un match (juste avant, pour la fraîcheur)."""

    matchday: int
    stage: Stage
    date: datetime.date | None
    opponent: ClubRef
    result: Literal["V", "N", "D"]
    scored: int
    conceded: int
    change: float
    value: float


class NoteOut(BaseModel):
    """Une note sur 20 et son évolution, match par match, sur la saison en cours."""

    value: float
    history: list[NoteStepOut]

    @classmethod
    def from_note(
        cls, note: Note, club_id: int, names: dict[int, str], season_match_ids: set[int]
    ) -> "NoteOut":
        steps = []
        for step in note.history:
            m = step.match
            if m.id not in season_match_ids:
                continue
            home = m.home_club_id == club_id
            opponent_id = m.away_club_id if home else m.home_club_id
            scored, conceded = (
                (m.home_score, m.away_score) if home else (m.away_score, m.home_score)
            )
            steps.append(
                NoteStepOut(
                    matchday=m.matchday,
                    stage=m.stage,
                    date=m.date,
                    opponent=ClubRef(id=opponent_id, name=names[opponent_id]),
                    result={1: "V", 0: "N", -1: "D"}[m.result_for(club_id)],
                    scored=scored,
                    conceded=conceded,
                    change=round(step.change, 1),
                    value=round(step.value, 1),
                )
            )
        return cls(value=round(note.value, 1), history=steps)


class ObjectiveOut(BaseModel):
    label: str
    target_rank: int
    expected_rank: int


class FormOut(BaseModel):
    """Forme du jour (engine/form.py) : effet de chaque note sur les notes collectives
    du XV probable, en fraction (0,03 = +3 %)."""

    morale: float
    cohesion: float
    freshness: float
    total: float


class ClubNotesOut(BaseModel):
    """Notes de vie du club, sur 20 (engine/notes.py et ses voisins)."""

    morale: NoteOut
    cohesion: NoteOut
    freshness: NoteOut
    board: NoteOut
    supporters: NoteOut
    objective: ObjectiveOut | None  # objectif de la direction pour la saison en cours
    form: FormOut  # effet sur le prochain match
    sack_threshold: float  # sous cette confiance, la direction limoge le manager
    sack_warning: float  # sous celle-ci, elle le fait savoir


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
    extra_time: bool  # prolongation jouée (phases finales)
    # Tirs au but réussis, si la prolongation n'a pas suffi.
    home_shootout: int | None
    away_shootout: int | None
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
            extra_time=match.went_to_extra_time,
            home_shootout=shootout_score(match, match.home_club_id),
            away_shootout=shootout_score(match, match.away_club_id),
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
    extra_time: bool = False  # prolongation jouée (phases finales)
    # Tirs au but réussis, si la prolongation n'a pas suffi.
    home_shootout: int | None = None
    away_shootout: int | None = None

    @classmethod
    def from_match(cls, match: Match, names: dict[int, str]) -> "MatchSummary":
        return cls(
            id=match.id,
            matchday=match.matchday,
            stage=match.stage,
            date=match.date,
            neutral=match.neutral,
            home=ClubRef(id=match.home_club_id, name=names[match.home_club_id]),
            away=ClubRef(id=match.away_club_id, name=names[match.away_club_id]),
            home_score=match.home_score,
            away_score=match.away_score,
            extra_time=match.went_to_extra_time,
            home_shootout=shootout_score(match, match.home_club_id),
            away_shootout=shootout_score(match, match.away_club_id),
        )


def shootout_score(match: Match, club_id: int) -> int | None:
    """Tirs au but réussis par un club, ou None s'il n'y a pas eu de séance."""
    return match.shootout_for(club_id) if match.went_to_shootout else None


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


class DismissalOut(BaseModel):
    """Limogeage du manager par la direction (engine/board.py)."""

    model_config = ConfigDict(from_attributes=True)

    manager_name: str
    club_id: int
    club_name: str
    date: datetime.date
    confidence: float


class PlayOut(BaseModel):
    played: MatchdayOut
    season: SeasonOut
    # Blessés de la journée (matchs et entraînement) dans le club dirigé.
    injuries: list["InjuryCase"]
    # Renseigné si la direction vient de limoger le manager : la carrière est terminée.
    dismissal: DismissalOut | None = None
    # Affaires à régler avant la journée suivante (engine/affairs.py).
    affairs: list["AffairOut"] = []
    # Joueurs du club dirigé en fin de contrat qu'un concurrent vient de signer.
    signings: list["ContractOut"] = []


# --- Affaires entre deux matchs (engine/affairs.py) -----------------------------------


class AffairOptionOut(BaseModel):
    key: str
    label: str


class AffairOut(BaseModel):
    """Une affaire : en attente (`options`), ou réglée (réponse, réaction et effets)."""

    id: int
    scenario: str
    category: str
    category_label: str
    title: str
    text: str
    date: datetime.date
    player_id: int | None
    options: list[AffairOptionOut]
    answered: bool
    choice: str | None  # vide une fois réglée : pas de réponse avant le match suivant
    choice_label: str | None
    outcome: str
    effects: dict[str, float]  # moral, cohésion, fraîcheur, direction, supporters
    money: int  # positif = recette
    promise: Literal["start", "win"] | None


class AffairsOverview(BaseModel):
    pending: list[AffairOut]
    recent: list[AffairOut]  # dernières affaires réglées, de la plus récente à la plus ancienne


class AnswerIn(BaseModel):
    choice: str


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


# --- Fins de contrat et bilan de saison ------------------------------------------------


class ContractOut(BaseModel):
    """Un joueur du club dirigé dont l'avenir se joue à l'intersaison (engine/contracts.py).

    Statuts : open (à prolonger, sinon il part libre), extended (prolongé cette
    saison), signed_elsewhere (un concurrent l'a signé), retiring (raccroche),
    leaving_academy (espoir trop âgé pour le centre : à passer pro).
    """

    player: PlayerOut
    status: Literal["open", "extended", "signed_elsewhere", "retiring", "leaving_academy"]
    playing_time: str  # titulaire, remplaçant, réserviste (pros)
    # Prolongation possible (open) : ce qu'il demande.
    wage_demand: int | None = None
    years_min: int | None = None
    years_max: int | None = None
    # Prolongé ou signé ailleurs : le nouveau contrat.
    new_club: ClubRef | None = None
    new_wage: int | None = None
    new_years: int | None = None
    signed_on: datetime.date | None = None


class ContractsOverview(BaseModel):
    season_year: int
    pros: list[ContractOut]
    youths: list[ContractOut]
    # Pros sous contrat la saison prochaine (arrivées sous pré-contrat comprises).
    squad_next: int
    squad_min: int
    squad_max: int


class ExtendIn(BaseModel):
    years: int = Field(ge=1, le=5)


class ScorerOut(BaseModel):
    player_id: int
    name: str
    points: int
    tries: int


class SeasonReviewOut(BaseModel):
    """Bilan sportif de la saison du club dirigé, une fois la finale jouée."""

    year: int
    club: ClubRef
    champion: ClubRef
    club_count: int
    playoff_qualifiers: int
    rank: int  # saison régulière
    played: int
    won: int
    drawn: int
    lost: int
    points_for: int
    points_against: int
    tries_for: int
    league_points: int
    # none : pas qualifié ; barrage, semi, final : éliminé à ce tour ; champion.
    playoffs: Literal["none", "barrage", "semi", "final", "champion"]
    objective: ObjectiveOut | None
    objective_met: bool | None
    youth_rank: int | None  # championnat espoirs
    balance_start: int
    balance_end: int
    scorers: list[ScorerOut]  # meilleurs marqueurs pros, trois au plus
