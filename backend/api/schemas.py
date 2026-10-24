"""Formats des requêtes et réponses de l'API (modèles Pydantic).

Ils sont séparés des objets du domaine : on choisit ce qu'on expose au frontend
sans contraindre le moteur.
"""

import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from engine.awards import AwardKind
from engine.crowd import Crowd
from engine.development import OTHER_UNCERTAINTY, estimate
from engine.difficulty import Difficulty
from engine.economy import FacilityKind, TransactionCategory, market_value
from engine.journal import Kind as ArticleKind
from engine.journal import MoveKind
from engine.match_engine import (
    Defence,
    GamePlan,
    PenaltyChoice,
    TeamStrength,
    captain_of,
    leadership,
)
from engine.notes import Note
from engine.regulations import is_jiff, jiff_min
from engine.sponsors import Placement
from engine.team_talk import Moment, Outcome
from engine.training import Intensity, Theme
from engine.transfers import DealKind
from engine.weather import Weather, forecast_at
from models import (
    AmenityKind,
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
    StandSide,
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


class NationOut(BaseModel):
    """Une sélection nationale (data/nations.py)."""

    model_config = ConfigDict(from_attributes=True)

    id: int  # identifiant d'équipe dans les matchs internationaux
    code: str
    name: str


class DutyOut(BaseModel):
    """Le joueur figure dans la liste de sa sélection pour une fenêtre en cours."""

    nation: NationOut
    competition: str  # nom de la fenêtre
    # Doublons à venir : les jours où sa sélection joue en même temps que son club.
    dates: list[datetime.date]
    away: bool  # dont le prochain match de son club : il le manquera


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
    stamina: int
    overall: float
    wage: int
    value: int
    contract_until: int  # dernière saison sous contrat (2026 = jusqu'à la fin de 2026-27)
    loaned_from: int | None  # club propriétaire si le joueur est prêté
    squad: Squad
    photo: str | None = None  # URL de la photo (vrais joueurs), None sinon
    nationality: str | None = None  # trois lettres (data/nations.py), None si inconnue
    club_id: int | None = None  # None : agent libre, ou hors des championnats du jeu
    club_name: str | None = None
    loaned_from_name: str | None = None
    # Blessure en cours ou période de fragilité ; None si le joueur est apte.
    injury: InjuryOut | None = None
    # Retenu en sélection (renseigné sur l'effectif d'un club) ; None sinon.
    duty: DutyOut | None = None
    # Discipline (engine/discipline.py) : matchs de suspension à purger, jaunes de la saison.
    suspended_matches: int = 0
    yellow_cards: int = 0
    # Ascendant sur le groupe, sur 20 (expérience et niveau) : l'étoffe d'un capitaine.
    leadership: float = 0.0
    jiff: bool = False  # issu des filières de formation françaises (engine/regulations.py)
    # Ce que le club sait de lui (api/scouting.py) : own (notre joueur), report
    # (supervisé), pending (rapport attendu), estimate (attributs estimés), all (sélectionneur).
    scouting: Literal["own", "report", "pending", "estimate", "all"] = "own"
    report_on: datetime.date | None = None  # supervision demandée ce jour-là
    # Potentiel estimé par le club (engine/development.py) : une fourchette de note
    # générale, d'autant plus étroite que le club connaît le joueur ; le vrai reste caché.
    potential_low: float = 0.0
    potential_high: float = 0.0
    season_gain: int = 0  # points d'attributs gagnés depuis le début de la saison

    @classmethod
    def from_player(
        cls,
        player: Player,
        day: datetime.date | None = None,
        club_names: dict[int, str] | None = None,
        duty: DutyOut | None = None,
        uncertainty: float = OTHER_UNCERTAINTY,
        scouting: str = "own",
        report_on: datetime.date | None = None,
    ) -> "PlayerOut":
        """`uncertainty` : ce que le club sait du joueur (api/scouting.py), en points de
        note de part et d'autre de son estimation du potentiel."""
        # Tous les champs viennent du joueur, sauf ceux qui se calculent.
        computed = {
            "value",
            "injury",
            "loaned_from_name",
            "duty",
            "club_name",
            "leadership",
            "potential_low",
            "potential_high",
            "jiff",
            "scouting",
            "report_on",
        }
        fields = {name: getattr(player, name) for name in cls.model_fields if name not in computed}
        injury = None
        if day is not None and (player.is_injured(day) or player.is_fragile(day)):
            injury = InjuryOut.from_injury(player.injury, day)
        owner = (club_names or {}).get(player.loaned_from) if player.loaned_from else None
        low, high = estimate(player, uncertainty)
        return cls(
            **fields,
            value=market_value(player),
            injury=injury,
            club_name=(club_names or {}).get(player.club_id),
            loaned_from_name=owner,
            duty=duty,
            leadership=round(20 * leadership(player), 1),
            potential_low=low,
            potential_high=high,
            jiff=is_jiff(player),
            scouting=scouting,
            report_on=report_on,
        )


class PlayerSeasonStats(BaseModel):
    """Statistiques individuelles sur la saison en cours (matchs où il était titulaire,
    ou entré en jeu pour les matchs qui comptent les statistiques)."""

    year: int | None
    matches: int
    tries: int
    conversions: int
    penalties: int
    drops: int
    points: int
    minutes: int = 0
    rating: float | None = None  # note moyenne sur 10, sur les matchs qui en ont une
    carries: int = 0
    line_breaks: int = 0
    tackles: int = 0
    missed_tackles: int = 0
    turnovers: int = 0
    lineouts_won: int = 0
    lineout_steals: int = 0
    yellow_cards: int = 0
    red_cards: int = 0


class PeerOut(BaseModel):
    """Un joueur du même poste (et du même groupe) dans le championnat, pour les comparaisons."""

    id: int
    club_id: int | None
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
    stamina: int


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
    # Championnat de la comparaison (celui de son club, ou du club dirigé pour un agent libre).
    league: str | None
    # Comparaison aux joueurs du même poste (et du même groupe : pros ou espoirs)
    # de ce championnat : part de ceux qu'il devance, par attribut et en note générale.
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
    captain_id: int | None = None  # capitaine du XV : celui du manager s'il est titulaire
    bench_ids: list[int] = []  # les 8 remplaçants
    # JIFF sur la feuille de match (les 23) et le minimum du championnat (0 : sans règle).
    jiff: int = 0
    jiff_min: int = 0

    @classmethod
    def from_team(cls, team: TeamStrength) -> "StrengthOut":
        captain = captain_of(team.club, team.lineup)
        return cls(
            set_piece=round(team.set_piece, 1),
            pack=round(team.pack, 1),
            attack=round(team.attack, 1),
            defense=round(team.defense, 1),
            kicking=team.kicker.kicking,
            kicker_id=team.kicker.id,
            lineup_ids=[p.id for p in team.lineup],
            captain_id=captain.id if captain else None,
            bench_ids=[p.id for p in team.bench],
            jiff=sum(is_jiff(p) for p in team.lineup + team.bench),
            jiff_min=jiff_min(team.club),
        )


class ClubSummary(BaseModel):
    id: int
    name: str
    league: str  # code du championnat (voir LeagueOut)
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
    # XV choisi par le manager (sinon composé par le staff).
    lineup_custom: bool = False
    # Capitaine choisi par le manager (None : le staff désigne le meneur du XV).
    captain_choice: int | None = None


class LineupIn(BaseModel):
    """XV voulu par le manager : un joueur (ou null) par place, dans l'ordre de lineup_ids."""

    player_ids: list[int | None]


class IntensityOptionOut(BaseModel):
    key: Intensity
    pace: float  # multiplicateur de la progression
    freshness: float  # points de fraîcheur (sur 20) au coup d'envoi
    injuries: float  # multiplicateur du risque de blessure à l'entraînement


class ThemeOptionOut(BaseModel):
    key: Theme
    focus: list[str]  # attributs travaillés en priorité


class TrainingOut(BaseModel):
    """La semaine d'entraînement du club dirigé (engine/training.py)."""

    intensity: Intensity
    theme: Theme
    intensities: list[IntensityOptionOut]
    themes: list[ThemeOptionOut]
    training_level: int  # centre d'entraînement (progression des pros)
    academy_level: int  # centre de formation (progression des espoirs)
    players: list["PlayerOut"]  # pros puis espoirs, avec potentiel estimé et progrès


class TrainingIn(BaseModel):
    """Changement de la semaine : seuls les champs renseignés changent."""

    intensity: Intensity | None = None
    theme: Theme | None = None


class CaptainIn(BaseModel):
    """Capitaine voulu par le manager ; null rend le choix au staff."""

    player_id: int | None


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


class PlayerMatchStatsOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    minutes: int
    rating: float | None
    carries: int
    line_breaks: int
    tackles: int
    missed_tackles: int
    turnovers: int
    lineouts_won: int
    lineout_steals: int


class CrowdOut(BaseModel):
    """Le public de l'équipe qui reçoit (engine/crowd.py)."""

    spectators: int
    atmosphere: float  # de 0 à 1
    label: str  # « Chaudron », « Bouillant », « Bonne ambiance », « Tiède », « Stade clairsemé »
    advantage: float  # multiplicateur du territoire de l'équipe qui reçoit
    # En direct, ce que fait le stade : roaring (il s'enflamme), tense (il pousse, fin de
    # match serrée), subdued (il s'éteint), silent (il se tait) ; None sinon.
    mood: str | None = None

    @classmethod
    def of(
        cls, spectators: int | None, atmosphere: float | None, mood: str | None = None
    ) -> "CrowdOut | None":
        if spectators is None or atmosphere is None:
            return None
        crowd = Crowd(spectators, 0, atmosphere)
        return cls(
            spectators=spectators,
            atmosphere=round(atmosphere, 2),
            label=crowd.label,
            advantage=round(crowd.advantage, 2),
            mood=mood,
        )


class MatchPlayerOut(BaseModel):
    """Un joueur entré en jeu et ce qu'il a fait du match."""

    id: int
    name: str | None  # None : joueur parti à la retraite depuis
    position: Position | None
    club_id: int
    number: int | None  # maillot des titulaires (1 à 15), None pour un remplaçant
    stats: PlayerMatchStatsOut


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
    weather: Weather | None = None  # None : match joué avant la météo
    crowd: CrowdOut | None = None  # None : terrain neutre, ou match joué avant le public
    # Joueurs entrés en jeu, avec leurs statistiques (vide pour un match d'avant).
    players: list[MatchPlayerOut] = []
    # Une barre par minute, positive quand l'équipe qui reçoit menace (engine/momentum.py) ;
    # vide pour un match joué avant le graphique.
    momentum: list[int] = []

    @classmethod
    def from_match(cls, match: Match, players: list[MatchPlayerOut] | None = None) -> "MatchOut":
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
            weather=match.weather,
            crowd=CrowdOut.of(match.spectators, match.atmosphere),
            players=players or [],
            momentum=match.momentum,
        )


# --- Match en direct (engine/match_engine.py : LiveMatch) --------------------------------


class TacticsOut(BaseModel):
    game_plan: GamePlan
    defence: Defence
    penalties: PenaltyChoice


class TacticsIn(BaseModel):
    """Changement de tactique : seuls les champs renseignés changent."""

    game_plan: GamePlan | None = None
    defence: Defence | None = None
    penalties: PenaltyChoice | None = None


class LivePlayerOut(BaseModel):
    """Un joueur de la feuille de match et son état à la minute en cours."""

    id: int
    name: str
    last_name: str
    position: Position  # poste naturel
    number: int  # maillot : 1 à 15 pour les titulaires, 16 à 23 pour le banc
    slot_number: int | None  # place occupée sur le terrain (1 à 15), None s'il n'y est pas
    slot: Position | None  # poste occupé sur le terrain
    # field : sur le terrain ; sin_bin : banc des pénalités ; sent_off : exclu ;
    # injured : blessé, sorti ; replaced : remplacé ; bench : sur le banc, peut entrer.
    status: Literal["field", "sin_bin", "sent_off", "injured", "replaced", "bench"]
    rating: float | None  # note sur 10, None s'il n'a pas joué
    yellow: int
    red: bool
    since: int | None  # minute d'entrée sur le terrain
    until: int | None  # minute de sortie (remplacé, blessé, exclu)
    back_at: int | None  # banc des pénalités : minute du retour
    overall: float
    kicking: int
    # Énergie de 0 à 1 : celle du coup d'envoi (selon sa fraîcheur) moins ses minutes
    # de jeu ; figée à sa sortie. Un remplaçant sur le banc montre celle qu'il aurait.
    energy: float
    # Ballons portés, plaquages, touches... depuis son entrée (None s'il n'a pas joué).
    stats: PlayerMatchStatsOut | None = None


class TalkHeardOut(BaseModel):
    minute: int
    key: str
    outcome: Outcome
    spirit: float  # élan gagné (ou perdu)
    heat: float  # nervosité ajoutée (ou retirée)


class TalkOptionOut(BaseModel):
    key: str
    success: float  # chance que le discours porte
    backfire: float  # chance qu'il se retourne contre le manager


class TalkOut(BaseModel):
    """Ce que le manager peut dire à son équipe maintenant."""

    moment: Moment | None  # None : pas maintenant
    options: list[TalkOptionOut]
    next_at: int | None  # minute à partir de laquelle il pourra reparler du bord du terrain


class LiveSideOut(BaseModel):
    club: ClubRef
    score: int
    tries: int
    shootout: int | None  # tirs au but réussis, si séance
    tactics: TacticsOut
    players: list[LivePlayerOut]  # titulaires (1 à 15) puis le banc (16 à 23)
    substitutions_left: int
    missing: int  # joueurs en moins sur le terrain (cartons, blessés sans remplaçant)
    kicker_id: int | None  # buteur du moment
    captain_id: int | None  # capitaine du XV (il ne compte que sur le terrain)
    strength: dict[str, float]  # notes collectives du moment : set_piece, pack, attack, defense
    spirit: float  # élan donné par les discours (+0,05 = notes collectives +5 %)
    heat: float  # nervosité (+0,5 = 50 % de cartons en plus)
    talks: list[TalkHeardOut]  # discours tenus, dans l'ordre


class LiveEventOut(BaseModel):
    minute: int
    type: EventType
    club_id: int
    player_id: int | None
    player_name: str | None
    other_player_id: int | None  # remplacement : le joueur qui entre
    other_player_name: str | None
    points: int


class LiveOut(BaseModel):
    """Le match en direct du club dirigé, tel qu'il en est."""

    match_id: int
    matchday: int
    stage: Stage
    date: datetime.date
    neutral: bool
    knockout: bool
    cup: bool  # un match de coupe d'Europe (sinon, du championnat)
    competition: str | None = None  # la coupe : « Coupe d'Europe », « Challenge européen »
    pool_rounds: int | None = None  # ses journées de poule
    my_club_id: int
    minute: int  # dernière minute jouée (0 avant le coup d'envoi)
    last_minute: int  # 80, ou 100 si la prolongation est engagée
    half_time: int
    extra_time: bool
    finished: bool
    weather: Weather
    crowd: "CrowdOut | None"  # public de l'équipe qui reçoit (None sur terrain neutre)
    home: LiveSideOut
    away: LiveSideOut
    events: list[LiveEventOut]  # dans l'ordre du match
    # Une barre par minute jouée, de -100 à 100 : positive quand l'équipe qui reçoit
    # menace, négative quand c'est l'autre (engine/momentum.py).
    momentum: list[int]
    talk: TalkOut  # discours possibles du club dirigé


class AdvanceIn(BaseModel):
    minutes: int = Field(default=1, ge=1, le=100)


class TalkIn(BaseModel):
    key: str


class SubstituteIn(BaseModel):
    player_out: int
    player_in: int


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
    # Le temps du match ; pour un match à venir, la prévision (qui ne se trompe pas).
    weather: Weather | None = None

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
            weather=match.weather
            if match.is_played
            else forecast_at(
                match.home_club_id, names[match.home_club_id], match.league, match.date
            ),
        )


def shootout_score(match: Match, club_id: int) -> int | None:
    """Tirs au but réussis par un club, ou None s'il n'y a pas eu de séance."""
    return match.shootout_for(club_id) if match.went_to_shootout else None


class MatchdayOut(BaseModel):
    matchday: int
    stage: Stage
    date: datetime.date
    matches: list[MatchSummary]
    cup: bool = False  # une journée de coupe d'Europe (sinon, du championnat)
    competition: str | None = None  # la coupe : « Coupe d'Europe », « Challenge européen »
    pool_rounds: int | None = None  # ses journées de poule


# --- Carrière ------------------------------------------------------------------------


class CareerIn(BaseModel):
    """Manager d'un club (`club_id`) ou sélectionneur d'une nation (`nation`, son code)."""

    manager_name: str = Field(min_length=1, max_length=100)
    club_id: int | None = None
    nation: str | None = None
    difficulty: Difficulty = Difficulty.NORMAL  # carrière de club (engine/difficulty.py)


class CareerOut(BaseModel):
    id: int
    manager_name: str
    # nation : carrière de sélectionneur. `club_id` et `club_name` sont alors ceux de
    # la sélection (son identifiant d'équipe, son nom), `nation` son code.
    kind: Literal["club", "nation"] = "club"
    club_id: int
    club_name: str
    league: str
    league_name: str
    nation: str | None = None
    difficulty: Difficulty = Difficulty.NORMAL
    # Carrière de club : année où commence la dernière saison du contrat du manager.
    contract_until: int | None = None


# --- Championnats ----------------------------------------------------------------------


class LeagueOut(BaseModel):
    code: str
    name: str
    short_name: str
    country: str
    club_count: int
    # Tours des phases finales, dans l'ordre (ex. barrage, semi, final).
    playoff_stages: list[Stage]


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


class CupRowOut(BaseModel):
    """Une ligne du classement d'une poule de la Coupe d'Europe."""

    club: ClubRef
    played: int
    won: int
    points_difference: int
    league_points: int


class CupPoolOut(BaseModel):
    pool: str  # A, B, C, D
    table: list[CupRowOut]  # du premier au dernier


class CupOut(BaseModel):
    """Une coupe d'Europe de la saison (engine/europe.py) : la Coupe d'Europe ou le
    Challenge européen."""

    code: str
    name: str
    pool_rounds: int  # journées de poule
    pools: list[CupPoolOut]
    matches: list[MatchSummary]  # poules puis phases finales, dans l'ordre des dates
    # pools : poules en cours ; knockout : phases finales ; finished : finale jouée.
    phase: Literal["pools", "knockout", "finished"]
    champion: ClubRef | None


class SeasonOut(BaseModel):
    year: int
    league: LeagueOut  # le championnat affiché
    leagues: list[LeagueOut]  # tous ceux de la saison, pour en changer
    # regular : journées à jouer ; playoffs : phases finales en cours ; finished : finale jouée.
    phase: Literal["regular", "playoffs", "finished"]
    regular_matchdays: int
    club_count: int
    playoff_qualifiers: int
    next_matchday: MatchdayOut | None
    # Le prochain match du club dirigé, avec les autres affiches du jour de sa compétition :
    # la journée du championnat, ou un week-end de Coupe d'Europe qui tombe avant.
    next_match: MatchdayOut | None = None
    standings: list[StandingOut]  # saison régulière seulement
    matches: list[MatchSummary]  # tout le calendrier, phases finales comprises
    champion: ClubRef | None
    # Les coupes d'Europe (Coupe d'Europe, puis Challenge), dans un monde qui en a.
    cups: list[CupOut] = []


class SaveOut(BaseModel):
    """Un emplacement de sauvegarde : vide, ou une partie et où elle en est."""

    slot: int
    empty: bool
    active: bool  # la partie chargée
    outdated: bool = False  # ancien format : ne s'ouvre plus, à supprimer
    manager_name: str | None = None  # None : carrière à choisir (nouvelle partie, limogeage)
    club_name: str | None = None
    league_name: str | None = None
    season_year: int | None = None
    game_date: datetime.date | None = None  # date du jour dans le jeu
    saved_at: datetime.datetime | None = None  # dernière sauvegarde (automatique)


class ManagerSeasonOut(BaseModel):
    """Une saison du manager, dans le club qu'il dirigeait."""

    year: int
    club: ClubRef
    rank: int | None  # saison régulière (None : saison en cours)
    expected: int | None  # rang attendu par la direction
    playoffs: bool
    champion: bool


class SpellOut(BaseModel):
    club: ClubRef
    start: datetime.date
    end: datetime.date | None  # None : il y est encore
    reason: Literal["dismissed", "left", "nation", "resigned", "expired", "quit"] | None


class JobOfferOut(BaseModel):
    """Un club (ou une sélection) qui veut le manager, à la fin de la saison
    (engine/career.py)."""

    # nation : une sélection ; `club` est alors son identifiant d'équipe et son nom.
    kind: Literal["club", "nation"] = "club"
    club: ClubRef
    nation: str | None = None  # code de la sélection
    league: str
    league_name: str
    level: float  # niveau du XV, sur 20
    balance: int | None  # sa trésorerie (None pour une sélection)
    seasons: int | None  # durée du contrat proposé (None pour une sélection)
    indemnity: int  # versée au club du manager s'il part encore sous contrat


class ManagerContractOut(BaseModel):
    """Le contrat du manager et ce qu'en pense la direction (engine/manager_contract.py)."""

    club: ClubRef
    until: int  # année où commence sa dernière saison
    seasons_left: int  # saisons encore à jouer (0 : il s'achève avec la saison finie)
    expiring: bool
    board: float  # confiance de la direction, sur 20
    supporters: float
    # En fin de contrat, les saisons que la direction propose d'elle-même (0 : elle ne
    # le renouvelle pas) ; None en cours de contrat, où il faut demander.
    renewal: int | None
    max_ask: int  # saisons demandables d'un coup
    blocked: Literal["too_long", "too_soon", "refused"] | None
    matches_needed: int
    retry_on: datetime.date | None
    indemnity: int  # ce que verserait un club qui le recruterait maintenant
    # Réputation perdue à partir de soi-même maintenant (0 en fin de contrat).
    resign_cost: float


class ExtensionIn(BaseModel):
    seasons: int = Field(ge=1, le=3)


class ExtensionOut(BaseModel):
    outcome: Literal["accepted", "countered", "refused"]
    seasons: int  # accordées, ou proposées par la direction
    contract: ManagerContractOut


class CareerHistoryOut(BaseModel):
    manager_name: str
    reputation: float  # de 0 à 100
    label: str  # « Espoir du banc »... « Star du banc »
    seasons: list[ManagerSeasonOut]  # de la plus récente à la plus ancienne
    spells: list[SpellOut]
    offers: list[JobOfferOut]  # une fois la saison du championnat finie
    contract_until: int


class InboxItemOut(BaseModel):
    """Ce qui attend une décision du manager (api/routers/inbox.py)."""

    kind: Literal[
        "affair", "medical", "transfer", "discipline", "finances", "contract", "academy", "career"
    ]
    title: str
    detail: str
    link: str  # la page où le régler
    urgent: bool = False  # à régler avant la prochaine journée


class InboxOut(BaseModel):
    items: list[InboxItemOut]  # le plus pressant d'abord


class DismissalOut(BaseModel):
    """Départ du manager sans autre club : limogé par la direction (engine/board.py),
    parti de lui-même ou au bout de son contrat."""

    model_config = ConfigDict(from_attributes=True)

    manager_name: str
    club_id: int
    club_name: str
    date: datetime.date
    confidence: float
    reason: Literal["dismissed", "resigned", "expired"] = "dismissed"
    # Les clubs qu'il peut reprendre (engine/career.py) ; None : tous.
    reachable: list[int] | None = None


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
    # Listes des sélections annoncées depuis la journée précédente : nos joueurs retenus.
    call_ups: list["CallUpNotice"] = []


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
    salary_cap: int | None = None  # plafond salarial du championnat (engine/regulations.py)
    transactions: list[TransactionOut]  # de la plus récente à la plus ancienne


class StaffMemberOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    role: StaffRole
    level: int
    wage: int
    effect: float = 0.0  # ce qu'il apporte (engine/coaching.py `effect`)


class StaffSlotOut(BaseModel):
    role: StaffRole
    member: StaffMemberOut | None
    severance: int | None  # indemnité si on licencie le titulaire
    effect: float  # ce que le poste apporte aujourd'hui (vacant compris)


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


class AmenityOut(BaseModel):
    """Un aménagement du catalogue des tribunes, et s'il peut être installé."""

    kind: AmenityKind
    label: str
    cost: int
    effect: str
    installed: int  # déjà installés dans tout le stade
    stadium_max: int | None


class StandOut(BaseModel):
    side: StandSide
    label: str
    slots: int  # emplacements de la tribune (dépend de la taille du stade)
    amenities: list[AmenityKind]  # installés, dans l'ordre des emplacements


class StadiumOut(BaseModel):
    capacity: int
    stands: list[StandOut]
    catalogue: list[AmenityOut]


# Motifs de maillot proposés (dessinés par frontend/src/jersey.js).
JerseyPattern = Literal[
    "plain", "hoops", "stripes", "halves", "quarters", "sash", "chevron", "band", "yoke"
]
HexColor = Annotated[str, Field(pattern=r"^#[0-9A-Fa-f]{6}$")]


class Jersey(BaseModel):
    """Maillot dessiné par le manager : un motif et trois couleurs (les sponsors sont
    communs aux trois tenues, voir SponsorsOut)."""

    pattern: JerseyPattern
    base: HexColor  # fond du maillot
    motif: HexColor  # bandes, rayures, écharpe…
    trim: HexColor  # col et bords des manches


class SponsorOut(BaseModel):
    """Une marque de la bibliothèque (engine/sponsors.py)."""

    id: str
    name: str
    sector: str
    budget: int  # par match, sur la poitrine
    image: int  # 1 (mal vu) à 5 (adoré)
    image_label: str
    mood: float  # effet sur la ferveur des supporters
    logo: dict


class DealIn(BaseModel):
    sponsor: str
    placement: Placement


class DealOut(DealIn):
    revenue: int  # par match


class DealsIn(BaseModel):
    deals: list[DealIn]


class SponsorsOut(BaseModel):
    """Les contrats en cours, la bibliothèque, et ce qu'en pensent les supporters."""

    deals: list[DealOut]
    library: list[SponsorOut]
    placements: dict[Placement, str]  # libellés
    shares: dict[Placement, float]  # part du budget versée selon l'emplacement
    max_deals: int
    revenue: int  # par match, en tout
    mood: float  # effet sur la ferveur des supporters
    crowded_mood: float  # malus quand le maillot est couvert de logos


JerseyKind = Literal["home", "away", "third"]


class JerseysOut(BaseModel):
    """Les trois tenues (None : maillot aux couleurs du club) et l'achat du third."""

    home: Jersey | None = None
    away: Jersey | None = None
    third: Jersey | None = None
    third_kit: bool  # third acheté : on peut le dessiner
    third_kit_cost: int
    third_kit_affordable: bool


class FacilitiesOverview(BaseModel):
    balance: int
    facilities: FacilitiesOut
    upgrades: list[UpgradeOut]
    stadium: StadiumOut
    jerseys: JerseysOut
    sponsors: SponsorsOut


class AmenityIn(BaseModel):
    kind: AmenityKind


class ListingOut(BaseModel):
    """Un joueur d'un autre club, ou un agent libre, et les voies possibles pour le recruter."""

    player: PlayerOut
    club_id: int | None  # None = agent libre
    club_name: str | None
    club_level: float | None
    league: str | None  # nom court du championnat du club (None = agent libre)
    years_left: int  # saisons de contrat restantes, celle en cours comprise (0 sans contrat)
    playing_time: str  # titulaire, remplaçant, réserviste (dans son club), sans club
    transfer_fee: int | None  # indemnité demandée à l'ouverture ; None = intransférable
    loanable: bool
    precontract: bool  # dernière année de contrat : négociable sans indemnité
    talks_closed_until: datetime.date | None  # il ne veut plus discuter avant cette date
    free_agent: bool = False  # sans club ni contrat : il signe sans indemnité, tout de suite
    wage_demand: int | None = None  # agent libre : salaire demandé à l'ouverture
    # Club avec qui il a signé un pré-contrat : il n'est plus à vendre, seulement à prêter.
    signed_with: str | None = None


class NegotiationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    player_id: int
    player_name: str
    club_name: str  # club actuel du joueur (« Agent libre » s'il n'en a pas)
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
    payroll: int = 0  # masse salariale des pros, par saison
    salary_cap: int | None = None  # plafond de son championnat (engine/regulations.py)
    leagues: list[str]  # noms courts des championnats du marché, dans l'ordre
    listings: list[ListingOut]
    negotiations: list[NegotiationOut]  # en cours, et pré-contrats en attente de l'intersaison
    joker_slots: list["JokerSlotOut"]  # blessures qui autorisent un joker médical
    jokers: list["JokerOut"]  # jokers en pige (hors effectif, non compris dans squad_size)


class DealOption(BaseModel):
    """Une voie de recrutement : possible ou non, et pourquoi."""

    kind: DealKind
    available: bool
    reason: str
    fee_demand: int | None = None  # transfert : indemnité demandée par le club (son ouverture)
    wage_demand: int | None = None  # transfert, pré-contrat, agent libre : salaire demandé
    wage: int | None = None  # prêt : salaire actuel, à ta charge
    # Joker médical : la blessure qu'il compense, le blessé et son retour prévu.
    injury_id: int | None = None
    injured_name: str | None = None
    until: datetime.date | None = None


class TransferTargetOut(BaseModel):
    """Approche d'un joueur : sa situation et ce qu'il attend."""

    player: PlayerOut
    club: ClubRef | None  # None = agent libre
    club_level: float | None
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
    injury_id: int | None = None  # joker médical : la blessure qu'il compense


class OfferIn(BaseModel):
    fee: int | None = Field(default=None, ge=0)  # étape club
    wage: int | None = Field(default=None, ge=0)  # étape joueur
    # Durée de contrat proposée (transfert, pré-contrat, agent libre ; ignorée pour un joker).
    years: int = Field(default=2, ge=1, le=5)


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


class JokerSlotOut(BaseModel):
    """Une longue blessure qui autorise un joker médical, en plus de l'effectif."""

    injury_id: int
    player: PlayerRef  # le blessé
    kind: str
    return_date: datetime.date


class JokerOut(BaseModel):
    """Un joker médical en pige : jusqu'au retour du blessé, au plus tard la fin de saison."""

    player: PlayerRef
    injured: PlayerRef
    until: datetime.date
    status: str  # active (en pige), ending (pige finie, décision attendue)


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
    joker_allowed: bool = False  # absence de plus de 3 mois, pas encore de joker
    joker: PlayerRef | None = None  # le joker médical recruté pour cette blessure


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


class SigningOut(BaseModel):
    """Un recrutement du club dirigé en vue : négociation en cours (`club`, `player`),
    ou accord signé qui attend l'intersaison (`agreed`)."""

    id: int
    player: PlayerOut
    club: ClubRef | None  # son club actuel ; None : agent libre
    kind: DealKind
    stage: Literal["club", "player", "agreed"]
    wage: int | None  # salaire convenu
    years: int | None  # durée convenue


class ContractsOverview(BaseModel):
    season_year: int
    pros: list[ContractOut]
    youths: list[ContractOut]
    signings: list[SigningOut]  # accords signés d'abord, puis négociations en cours
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
    league: LeagueOut
    # none : pas qualifié ; quarter, barrage, semi, final : éliminé à ce tour ; champion.
    playoffs: Literal["none", "quarter", "barrage", "semi", "final", "champion"]
    # Montée en Top 14 (champion de Pro D2) ou descente en Pro D2 (dernier du Top 14).
    movement: Literal["promoted", "relegated"] | None = None
    objective: ObjectiveOut | None
    objective_met: bool | None
    youth_rank: int | None  # championnat espoirs
    balance_start: int
    balance_end: int
    scorers: list[ScorerOut]  # meilleurs marqueurs pros, trois au plus


# --- Palmarès, trophées et records (api/routers/honours.py) ---------------------------


class AwardOut(BaseModel):
    """Un trophée de fin de saison (engine/awards.py)."""

    kind: AwardKind
    slot: Position | None = None  # équipe type : la place
    player_id: int
    name: str
    position: Position
    club: ClubRef
    value: float  # note moyenne, essais, points ou plaquages
    active: bool  # le joueur a encore une fiche (il n'a pas raccroché)


class SeasonHonoursOut(BaseModel):
    year: int
    champion: ClubRef | None  # None : saison pas finie
    runner_up: ClubRef | None
    final: MatchSummary | None
    awards: list[AwardOut]


class TitlesOut(BaseModel):
    club: ClubRef
    titles: int
    years: list[int]


class LeagueHonoursOut(BaseModel):
    code: str
    name: str
    short_name: str
    titles: list[TitlesOut]  # les clubs titrés, du plus titré au moins titré
    seasons: list[SeasonHonoursOut]  # de la plus récente à la plus ancienne


class ClubSeasonOut(BaseModel):
    """Une saison du club dirigé."""

    year: int
    league: str
    league_name: str
    rank: int | None  # saison régulière (None tant qu'elle n'a pas commencé)
    club_count: int
    # none : pas de phases finales ; quarter, barrage, semi, final : éliminé à ce tour ;
    # champion ; running : saison en cours.
    playoffs: Literal["none", "quarter", "barrage", "semi", "final", "champion", "running"]
    played: int
    won: int
    points_for: int
    points_against: int


class RecordLineOut(BaseModel):
    player_id: int
    name: str
    club: ClubRef | None
    value: int
    year: int | None = None  # record d'une saison : laquelle
    active: bool


class RecordMatchOut(BaseModel):
    match: MatchSummary
    year: int
    league: str


class RecordsOut(BaseModel):
    """Les records de tous les championnats, depuis la première saison."""

    tries: list[RecordLineOut]  # essais en carrière
    points: list[RecordLineOut]  # points en carrière
    season_tries: list[RecordLineOut]  # essais en une saison
    season_points: list[RecordLineOut]  # points en une saison
    biggest_wins: list[RecordMatchOut]  # plus larges victoires
    seasons: int  # saisons comptées


class HonoursOut(BaseModel):
    club: ClubRef | None  # le club dirigé
    league: str | None  # son championnat (celui qu'on montre d'abord)
    leagues: list[LeagueHonoursOut]
    club_history: list[ClubSeasonOut]
    records: RecordsOut


# --- Sélections nationales (engine/internationals.py) -----------------------------------


class NationSummary(NationOut):
    """Une sélection au choix du sélectionneur : son vivier et le niveau de son XV."""

    player_count: int  # joueurs sélectionnables
    level: float  # moyenne des 4 notes collectives du XV que composerait le staff
    competitions: list[str]  # ses rendez-vous de la saison


class CalledPlayer(BaseModel):
    player: PlayerRef
    nation: NationOut
    competition: str | None = None  # nom de la fenêtre
    # Doublons à venir : les jours où sa sélection joue en même temps que son club.
    dates: list[datetime.date] = []


class CallUpNotice(BaseModel):
    """Les joueurs du club dirigé retenus pour une fenêtre internationale."""

    competition: str  # nom de la fenêtre
    players: list[CalledPlayer]
    # Doublons : les jours où le club joue pendant qu'au moins l'un d'eux est en sélection.
    doublons: list[datetime.date]


class PoolTableOut(BaseModel):
    """Une poule de la Coupe du monde et son classement."""

    name: str
    standings: list[StandingOut]


class WindowOut(BaseModel):
    """Une fenêtre internationale de la saison : ses matchs, son classement s'il y en a un."""

    code: str
    name: str
    short_name: str
    has_table: bool
    announce_by: datetime.date  # date limite d'annonce des listes
    announced: bool  # les listes des sélections gérées par leur staff sont publiées
    # Tous ses samedis, y compris ceux des tours de Coupe du monde pas encore tirés.
    dates: list[datetime.date]
    nations: list[NationOut]
    matches: list[MatchSummary]
    standings: list[StandingOut]  # vide pour une tournée et pour la Coupe du monde
    pools: list[PoolTableOut] = []  # Coupe du monde : un classement par poule
    finished: bool
    champion: ClubRef | None = None


class InternationalsOut(BaseModel):
    year: int
    today: datetime.date
    windows: list[WindowOut]
    # Dans une carrière de club : nos joueurs retenus en ce moment.
    my_players: list[CalledPlayer] = []


class SquadPlayerOut(BaseModel):
    """Un joueur sélectionnable, ou retenu, vu par un sélectionneur."""

    player: PlayerOut
    club: ClubRef | None  # None : il évolue hors des championnats du jeu
    position_rating: float  # note à son poste, critère du staff
    starts: int  # titularisations cette saison, club et sélection


class NationSquadOut(BaseModel):
    """La liste d'une sélection pour une fenêtre."""

    nation: NationOut
    competition: str
    announced_on: datetime.date | None  # None : pas encore annoncée
    players: list[SquadPlayerOut]


class RecordOut(BaseModel):
    played: int
    won: int
    drawn: int
    lost: int


class SelectionOut(BaseModel):
    """Où en est le sélectionneur : ce qui l'attend avant de pouvoir avancer."""

    nation: NationOut
    year: int
    today: datetime.date
    # list : la liste doit être annoncée ; match : notre match est le prochain jour joué ;
    # wait : rien pour nous ce jour-là ; finished : la saison est terminée.
    phase: Literal["list", "match", "wait", "finished"]
    # La fenêtre en cours ou à venir de notre sélection (None : plus aucune cette saison).
    window: WindowOut | None
    list_announced: bool  # notre liste pour cette fenêtre est annoncée
    next_match: MatchSummary | None
    next_day: datetime.date | None  # prochain jour de match dans le monde, clubs compris
    record: RecordOut  # nos matchs de la saison
    squad_size: int  # taille d'une liste


class PoolOut(BaseModel):
    """Tous les joueurs sélectionnables pour la prochaine liste, et celle du staff."""

    nation: NationOut
    window: WindowOut | None  # None : plus de fenêtre cette saison
    announced: bool
    size: int
    quota: dict[Position, int]  # la répartition que suit le staff
    minimum: dict[Position, int]  # ce qu'une liste doit au moins compter
    selected: list[int]  # la liste annoncée (vide sinon)
    suggested: list[int]  # la proposition du staff
    players: list[SquadPlayerOut]


class SquadListIn(BaseModel):
    player_ids: list[int]


class ReplaceIn(BaseModel):
    player_out: int
    player_in: int


class AdvanceOut(BaseModel):
    """Un jour de match joué par le monde pendant une carrière de sélectionneur."""

    date: datetime.date
    tests: list[MatchSummary]  # matchs internationaux du jour
    club_matches: int  # matchs de clubs joués ce jour-là
    injuries: list["InjuryCase"]  # blessés de notre liste, en sélection ou en club
    selection: SelectionOut


# --- Journal (engine/journal.py) -----------------------------------------------------------


class JournalPlayer(BaseModel):
    """Un joueur cité par le journal. `id` à None : il n'a plus de fiche (retraite)."""

    id: int | None
    name: str
    position: Position
    age: int
    overall: float
    photo: str | None = None


class MoveOut(BaseModel):
    """Un mouvement de joueur : d'où il vient, où il va."""

    id: str
    kind: MoveKind
    date: datetime.date
    player: JournalPlayer
    origin: ClubRef | None  # None : il était sans club
    destination: ClubRef | None  # None : il part sans club, ou raccroche
    fee: int | None = None
    pending: bool = False  # pré-contrat signé : il arrivera à l'intersaison
    mine: bool = False


class ProspectOut(BaseModel):
    """Un joueur à suivre sur le marché : en dernière année de contrat (`club` : le
    sien), ou sans club."""

    player: JournalPlayer
    club: ClubRef | None
    mine: bool = False


class ArticleOut(BaseModel):
    """Un article : son titre, sa brève, et de quoi l'illustrer (équipes, joueur, match)."""

    id: str
    kind: ArticleKind
    date: datetime.date
    title: str
    body: str
    competition: str | None = None
    international: bool = False
    mine: bool = False  # concerne le club ou la sélection du joueur
    teams: list[ClubRef] = []
    player: JournalPlayer | None = None
    match: MatchSummary | None = None
    move: MoveOut | None = None


class RoundOut(BaseModel):
    """Les matchs d'une compétition un même jour."""

    label: str  # « Journée 12 », « Finale », « Test 2 »
    date: datetime.date
    matches: list[MatchSummary]


class CompetitionOut(BaseModel):
    """Un championnat ou une fenêtre internationale : sa dernière journée, la prochaine."""

    code: str
    name: str
    international: bool = False
    last: RoundOut | None
    next: RoundOut | None


class JournalOut(BaseModel):
    year: int
    today: datetime.date
    # Du sujet le plus lourd au plus léger ; les six premiers font la une.
    articles: list[ArticleOut]
    competitions: list[CompetitionOut]
    focus: str | None  # la compétition du joueur, à montrer d'abord
    moves: list[MoveOut]  # les plus récents d'abord
    # À suivre sur le marché, les mieux notés d'abord : fins de contrat, puis agents libres.
    prospects: list[ProspectOut]
