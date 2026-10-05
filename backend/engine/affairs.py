# ruff: noqa: E501 (catalogue de textes : les phrases restent sur une ligne)
"""Affaires entre deux matchs : conférences de presse, tête-à-tête, vie du vestiaire.

Après une journée, le club dirigé reçoit parfois une affaire à régler : une
situation (tirée d'après les résultats, l'effectif, les notes) et trois ou quatre
réponses. Chaque réponse fait bouger les notes de vie du club (moral, cohésion,
fraîcheur, direction, supporters), parfois la trésorerie, et peut déclencher une
action (prolonger, vendre, promouvoir...) ou une promesse vérifiée au match suivant.

Les effets restent cachés jusqu'à la réponse. Pour fixer les ordres de grandeur :
une victoire vaut +1,3 de moral, une défaite à domicile −1,3 de supporters.

Ce module ne connaît ni la base ni l'API : `Situation` lui décrit le club,
`draw` choisit l'affaire, `Option` dit ce que la réponse change.
"""

import datetime
import random
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import StrEnum

from models import Position, StaffRole, Stage

NOTE_KEYS = ("morale", "cohesion", "freshness", "board", "supporters")

# Une affaire tous les 2 ou 3 matchs du club : jamais avant le 2e match depuis la
# précédente, une fois sur deux au 2e, à coup sûr au 3e. Un scénario ne tombe
# qu'une fois par saison ; un même joueur n'est pas sollicité deux fois de suite.
MIN_GAP, MAX_GAP = 2, 3
GAP_CHANCE = 0.5
PLAYER_COOLDOWN_DAYS = 28

# Réglages des actions.
RAISE_SHARE = 0.20  # augmentation de salaire
EXTENSION_YEARS, EXTENSION_RAISE = 2, 0.15
STAFF_RAISE_SHARE = 0.25


class Category(StrEnum):
    PRESS = "press"
    PLAYER = "player"
    SQUAD = "squad"
    BOARD = "board"
    FANS = "fans"
    MEDIA = "media"


class Action(StrEnum):
    """Ce qu'une réponse fait, en plus des notes et de l'argent."""

    RAISE_WAGE = "raise_wage"  # +20 % de salaire au joueur
    EXTEND = "extend"  # contrat prolongé de 2 saisons, +15 %
    SELL = "sell"  # vendu à sa valeur marchande
    PROMOTE = "promote"  # l'espoir passe chez les pros
    STAFF_RAISE = "staff_raise"  # +25 % au membre du staff
    STAFF_LEAVE = "staff_leave"  # le membre du staff quitte le club
    KEEP_JOKER = "keep_joker"  # le joker médical signe un vrai contrat
    RELEASE_JOKER = "release_joker"  # le joker médical repart, agent libre


class PromiseKind(StrEnum):
    START = "start"  # le joueur sera titulaire au prochain match
    WIN = "win"  # on gagnera le prochain match


@dataclass(frozen=True)
class Promise:
    """Promesse vérifiée au prochain match du club ; suites (scénarios) si tenue ou non."""

    kind: PromiseKind
    kept: str | None
    broken: str | None


def fx(mo: float = 0, co: float = 0, fr: float = 0, di: float = 0, su: float = 0) -> dict:
    """Effets sur les notes, sans les zéros : fx(mo=0.5, su=-0.3)."""
    values = dict(zip(NOTE_KEYS, (mo, co, fr, di, su), strict=True))
    return {key: value for key, value in values.items() if value}


@dataclass(frozen=True)
class Option:
    key: str
    label: str  # ce que dit ou fait le manager
    outcome: str  # la réaction, montrée après la réponse
    effects: dict[str, float] = field(default_factory=dict)
    money: int = 0  # positif = recette
    action: Action | None = None
    promise: Promise | None = None
    # Issue incertaine : (notes du club, hasard) -> (effets, réaction), à la place des fixes.
    gamble: Callable[[dict[str, float], random.Random], tuple[dict, str]] | None = None

    def resolve(self, notes: dict[str, float], rng: random.Random) -> tuple[dict, str]:
        if self.gamble is not None:
            return self.gamble(notes, rng)
        return self.effects, self.outcome


# --- Ce que le moteur sait du club -----------------------------------------------------


@dataclass(frozen=True)
class PlayerInfo:
    id: int
    name: str
    position: Position
    age: int
    overall: float
    starts: int = 0  # titularisations en championnat cette saison
    years_left: int = 2  # saisons de contrat, celle en cours comprise
    injured_weeks: int = 0  # semaines d'absence restantes
    youth: bool = False


@dataclass(frozen=True)
class StaffInfo:
    id: int
    name: str
    role: StaffRole
    level: int


@dataclass(frozen=True)
class Result:
    """Le dernier match du club."""

    opponent: str
    scored: int
    conceded: int
    at_home: bool
    stage: Stage = Stage.REGULAR

    @property
    def margin(self) -> int:
        return self.scored - self.conceded


@dataclass(frozen=True)
class Fixture:
    """Le prochain match du club."""

    opponent: str
    opponent_rank: int | None
    at_home: bool
    stage: Stage = Stage.REGULAR


@dataclass(frozen=True)
class PastChoice:
    """Une affaire déjà vécue (pour les délais, les récidives et les contradictions)."""

    scenario: str
    choice: str | None
    player_id: int | None
    day: datetime.date
    player_name: str | None = None
    this_season: bool = True


@dataclass
class Situation:
    club: str
    day: datetime.date
    rank: int | None = None
    club_count: int = 14
    target_rank: int | None = None  # objectif de la direction
    played: int = 0  # matchs de championnat joués par le club cette saison
    regular_rounds: int = 26
    last: Result | None = None
    streak: int = 0  # +n victoires de suite, −n défaites de suite
    next: Fixture | None = None
    notes: dict[str, float] = field(default_factory=dict)
    balance: int = 0
    academy_level: int = 1
    players: list[PlayerInfo] = field(default_factory=list)
    youths: list[PlayerInfo] = field(default_factory=list)
    staff: list[StaffInfo] = field(default_factory=list)
    past: list[PastChoice] = field(default_factory=list)
    # Matchs joués par le club depuis la dernière affaire (depuis le début de saison sinon).
    matches_since_affair: int = 0

    def note(self, key: str) -> float:
        return self.notes.get(key, 10.0)

    @property
    def fit_players(self) -> list[PlayerInfo]:
        return [p for p in self.players if p.injured_weeks == 0]

    @property
    def median_overall(self) -> float:
        levels = sorted(p.overall for p in self.players)
        return levels[len(levels) // 2] if levels else 0.0

    def best(self, count: int = 1) -> list[PlayerInfo]:
        return sorted(self.fit_players, key=lambda p: p.overall, reverse=True)[:count]

    @property
    def big_game(self) -> bool:
        nxt = self.next
        return nxt is not None and (
            nxt.stage != Stage.REGULAR or (nxt.opponent_rank is not None and nxt.opponent_rank <= 3)
        )


POSITION_LABELS = {
    Position.PROP: "pilier",
    Position.HOOKER: "talonneur",
    Position.LOCK: "deuxième ligne",
    Position.BACK_ROW: "troisième ligne",
    Position.SCRUM_HALF: "demi de mêlée",
    Position.FLY_HALF: "demi d'ouverture",
    Position.CENTRE: "centre",
    Position.WING: "ailier",
    Position.FULLBACK: "arrière",
}

STAFF_LABELS = {
    StaffRole.FORWARDS_COACH: "entraîneur des avants",
    StaffRole.ATTACK_COACH: "entraîneur de l'attaque",
    StaffRole.DEFENCE_COACH: "entraîneur de la défense",
    StaffRole.KICKING_COACH: "entraîneur du jeu au pied",
    StaffRole.FITNESS_COACH: "préparateur physique",
    StaffRole.ANALYST: "analyste vidéo",
    StaffRole.PHYSIO: "kiné",
    StaffRole.DOCTOR: "médecin",
}


def _rank(rank: int | None) -> str:
    if rank is None:
        return "?"
    return "1er" if rank == 1 else f"{rank}e"


def base_context(s: Situation) -> dict:
    """Variables communes à tous les textes."""
    ctx: dict = {"club": s.club, "rank": _rank(s.rank), "streak": abs(s.streak)}
    if s.target_rank is not None:
        ctx["target"] = _rank(s.target_rank)
    if s.last is not None:
        ctx["opponent"] = s.last.opponent
        ctx["score"] = f"{s.last.scored}-{s.last.conceded}"
    if s.next is not None:
        ctx["next"] = s.next.opponent
        ctx["venue"] = "à domicile" if s.next.at_home else "à l'extérieur"
    return ctx


def with_player(ctx: dict, player: PlayerInfo, suffix: str = "") -> dict:
    ctx[f"player{suffix}"] = player.name
    ctx[f"player{suffix}_id"] = player.id
    ctx[f"position{suffix}"] = POSITION_LABELS[player.position]
    ctx[f"age{suffix}"] = player.age
    return ctx


def render(text: str, ctx: dict) -> str:
    return text.format_map(ctx)


# --- Scénarios ---------------------------------------------------------------------------

Trigger = Callable[[Situation, random.Random], dict | None]


@dataclass(frozen=True)
class Scenario:
    key: str
    category: Category
    title: str
    text: str
    options: tuple[Option, ...]
    # Situation -> variables du texte (None : ne s'applique pas). Sans trigger, le
    # scénario n'arrive qu'en suite d'une promesse ou d'une décision passée.
    trigger: Trigger | None = None
    weight: float | Callable[[Situation], float] = 1.0
    urgent: bool = False  # passe avant le tirage au sort quand son trigger s'applique
    # Sans réponse avant le match suivant : cette réponse est prise d'office (sinon
    # la réaction « sans réponse » de la catégorie).
    default: str | None = None
    # Un avis d'événement (fin de pige...) ne compte pas dans le rythme des affaires.
    scheduled: bool = True

    def weight_for(self, s: Situation) -> float:
        return self.weight(s) if callable(self.weight) else self.weight


# Sans réponse avant le match suivant : la réponse « par défaut » de chaque catégorie.
IGNORED = {
    Category.PRESS: (
        fx(di=-0.2, su=-0.4),
        "Tu as séché la conférence de presse. Les journaux en font leurs titres.",
    ),
    Category.PLAYER: (
        fx(mo=-0.4),
        "Personne ne lui a répondu. Il le prend mal, et le vestiaire l'a remarqué.",
    ),
    Category.SQUAD: (
        fx(co=-0.3),
        "La question est restée sans réponse. Le groupe se sent un peu délaissé.",
    ),
    Category.BOARD: (fx(di=-0.6), "La direction n'a pas apprécié ton silence."),
    Category.FANS: (fx(su=-0.5), "Les supporters attendaient un geste. Il n'est pas venu."),
    Category.MEDIA: ({}, "Le projet tombe à l'eau, faute de réponse."),
}

CATEGORY_LABELS = {
    Category.PRESS: "Conférence de presse",
    Category.PLAYER: "Tête-à-tête",
    Category.SQUAD: "Vestiaire",
    Category.BOARD: "Direction",
    Category.FANS: "Supporters",
    Category.MEDIA: "Médias",
}


def _when(condition: Callable[[Situation], bool]) -> Trigger:
    """Trigger sans joueur : le contexte de base si la condition est remplie."""

    def trigger(s: Situation, rng: random.Random) -> dict | None:
        return base_context(s) if condition(s) else None

    return trigger


def _pick_player(
    choose: Callable[[Situation], list[PlayerInfo]], random_pick: bool = True
) -> Trigger:
    """Trigger avec un joueur : au hasard parmi `choose(s)` (ou le premier)."""

    def trigger(s: Situation, rng: random.Random) -> dict | None:
        candidates = choose(s)
        if not candidates:
            return None
        player = rng.choice(candidates) if random_pick else candidates[0]
        return with_player(base_context(s), player)

    return trigger


def _last(s: Situation) -> Result | None:
    return s.last


WIN_PROMISE_PRESS = Promise(
    PromiseKind.WIN, kept="press_promise_kept", broken="press_promise_broken"
)


def _resignation_gamble(notes: dict[str, float], rng: random.Random) -> tuple[dict, str]:
    """Quitte ou double : plus la direction te fait confiance, plus elle refuse ta démission."""
    chance = min(0.85, max(0.15, (notes.get("board", 10.0) - 3) / 6))
    if rng.random() < chance:
        return fx(
            di=1.5
        ), "Le président refuse ta démission et te renouvelle publiquement sa confiance."
    return fx(di=-2.0, mo=-0.3), "Le président « prend note ». L'ambiance est glaciale."


SCENARIOS: list[Scenario] = [
    # --- Conférences de presse ---------------------------------------------------------
    Scenario(
        key="press_big_win",
        category=Category.PRESS,
        title="Après la démonstration",
        text="Large victoire contre {opponent} ({score}). En conférence de presse, un journaliste se lance : « Ce {club}, il peut aller au bout ? »",
        trigger=_when(lambda s: s.last is not None and s.last.margin >= 15),
        weight=3,
        options=(
            Option(
                "humble",
                "« On reste humbles, rien n'est fait. »",
                "Le discours rassure : le groupe garde les pieds sur terre.",
                fx(mo=0.3, co=0.3, di=0.2),
            ),
            Option(
                "title",
                "« Oui. On a l'effectif pour être champions. »",
                "Les supporters s'enflamment. Il faudra confirmer dès le prochain match.",
                fx(mo=0.8, su=1.0, di=-0.3),
                promise=WIN_PROMISE_PRESS,
            ),
            Option(
                "players",
                "« Tout le mérite revient aux joueurs. »",
                "Les joueurs apprécient d'être mis en avant.",
                fx(mo=0.6, co=0.4),
            ),
        ),
    ),
    Scenario(
        key="press_heavy_loss",
        category=Category.PRESS,
        title="La claque",
        text="Lourde défaite contre {opponent} ({score}). La salle de presse est pleine : « Comment expliquez-vous ça ? »",
        trigger=_when(lambda s: s.last is not None and s.last.margin <= -15),
        weight=3,
        options=(
            Option(
                "own_it",
                "« J'assume. C'est ma responsabilité. »",
                "Tu protèges ton groupe. La direction aurait préféré un autre coupable.",
                fx(mo=0.5, co=0.3, di=-0.3),
            ),
            Option(
                "blame_players",
                "« Les joueurs n'ont pas respecté le plan de jeu. »",
                "La direction apprécie la fermeté. Le vestiaire, beaucoup moins.",
                fx(mo=-1.2, co=-0.8, di=0.3),
            ),
            Option(
                "referee",
                "« L'arbitrage nous a coûté le match. »",
                "Les supporters te suivent. La direction redoute une sanction de la ligue.",
                fx(mo=0.2, di=-0.6, su=0.6),
            ),
            Option(
                "no_comment",
                "« Pas de commentaire. »",
                "Tu quittes la salle au bout de deux minutes. Mauvaise image.",
                fx(di=-0.2, su=-0.5),
            ),
        ),
    ),
    Scenario(
        key="press_close_loss",
        category=Category.PRESS,
        title="Si près du but",
        text="Défaite de peu contre {opponent} ({score}). « Il a manqué quoi, aujourd'hui ? »",
        trigger=_when(lambda s: s.last is not None and -7 <= s.last.margin < 0),
        weight=2,
        options=(
            Option(
                "progress",
                "« On progresse. La victoire viendra. »",
                "Le groupe repart la tête haute.",
                fx(mo=0.6, co=0.3),
            ),
            Option(
                "killer",
                "« Il faut être plus tueurs. »",
                "Message reçu par les joueurs, un peu piqués.",
                fx(mo=-0.3, di=0.3),
            ),
            Option(
                "referee",
                "« Un arbitrage à sens unique. »",
                "Le public gronde avec toi ; la direction soupire.",
                fx(mo=0.3, di=-0.4, su=0.5),
            ),
        ),
    ),
    Scenario(
        key="press_job_threat",
        category=Category.PRESS,
        title="Sur la sellette",
        text="{streak} défaites de suite. La question tombe, sans détour : « Votre poste est-il menacé ? »",
        trigger=_when(lambda s: s.streak <= -3),
        weight=4,
        options=(
            Option(
                "fight",
                "« Je ne lâcherai rien. »",
                "Ton combat plaît dans les tribunes.",
                fx(mo=0.4, su=0.3),
            ),
            Option(
                "squad_behind",
                "« Le groupe est derrière moi. »",
                "Les joueurs se resserrent autour de toi. Le président trouve ça présomptueux.",
                fx(mo=0.3, co=0.5, di=-0.2),
            ),
            Option(
                "ask_president",
                "« Demandez au président. »",
                "La phrase passe très mal au siège du club.",
                fx(di=-0.8, su=-0.3),
            ),
            Option(
                "changes",
                "« Des changements vont arriver. »",
                "La direction approuve. Les joueurs se demandent qui va sauter.",
                fx(mo=-0.6, di=0.6),
            ),
        ),
    ),
    Scenario(
        key="press_winning_streak",
        category=Category.PRESS,
        title="La série continue",
        text="{streak} victoires de suite. « Quel est votre secret ? »",
        trigger=_when(lambda s: s.streak >= 3),
        weight=3,
        options=(
            Option(
                "training",
                "« Le travail à l'entraînement. »",
                "Le staff apprécie. La direction aussi.",
                fx(co=0.4, di=0.3),
            ),
            Option("crowd", "« Notre public nous porte. »", "Les supporters adorent.", fx(su=1.0)),
            Option(
                "players",
                "« Les joueurs, uniquement les joueurs. »",
                "Le vestiaire se sent reconnu.",
                fx(mo=0.7, co=0.3),
            ),
            Option(
                "no_streak",
                "« On ne regarde pas la série. »",
                "Discours sérieux, un peu froid pour le groupe.",
                fx(mo=-0.2, di=0.2),
            ),
        ),
    ),
    Scenario(
        key="press_big_game",
        category=Category.PRESS,
        title="Avant le choc",
        text="Prochain match : {next}, {venue}. « Comment abordez-vous ce choc ? »",
        trigger=_when(lambda s: s.big_game),
        weight=3,
        options=(
            Option(
                "nothing_to_lose",
                "« On n'a rien à perdre. »",
                "Le groupe joue libéré. La direction aurait aimé plus d'ambition.",
                fx(mo=0.5, di=-0.2),
            ),
            Option(
                "we_win",
                "« On va gagner. »",
                "Phrase choc, reprise partout. Tu n'as plus le droit de perdre.",
                fx(mo=0.5, su=0.8),
                promise=WIN_PROMISE_PRESS,
            ),
            Option(
                "respect",
                "« C'est la meilleure équipe du pays. »",
                "Respectueux, mais les joueurs se sentent petits.",
                fx(mo=-0.3, di=0.1, su=-0.2),
            ),
            Option(
                "fill_stadium",
                "« Venez nombreux, on aura besoin de vous. »",
                "L'appel est entendu.",
                fx(su=0.8),
            ),
        ),
    ),
    Scenario(
        key="press_rival_taunt",
        category=Category.PRESS,
        title="Le chambrage",
        text="L'entraîneur de {next} a déclaré cette semaine que ton équipe « ne fait peur à personne ». On attend ta réponse.",
        trigger=_when(lambda s: s.next is not None),
        options=(
            Option(
                "hit_back",
                "Répondre du tac au tac.",
                "La joute verbale fait le buzz. Le président aurait préféré plus de retenue.",
                fx(mo=0.4, di=-0.3, su=0.8),
            ),
            Option("classy", "Ignorer avec classe.", "Ta sobriété est saluée.", fx(di=0.3)),
            Option(
                "pitch",
                "« Le terrain parlera. »",
                "Le vestiaire est piqué au vif. Rendez-vous samedi.",
                fx(mo=0.6),
                promise=WIN_PROMISE_PRESS,
            ),
        ),
    ),
    Scenario(
        key="press_star_rumour",
        category=Category.PRESS,
        title="Rumeur de départ",
        text="La presse annonce que {player}, ton meilleur joueur, serait courtisé par un grand club. « Est-il à vendre ? »",
        trigger=_pick_player(lambda s: s.best(1), random_pick=False),
        weight=0.8,
        options=(
            Option(
                "not_for_sale",
                "« Il n'est pas à vendre. »",
                "Les supporters respirent. Ta parole est engagée.",
                fx(mo=0.3, su=0.6),
            ),
            Option(
                "price",
                "« Tout le monde a un prix. »",
                "La direction y voit du bon sens. Le vestiaire et les tribunes, une trahison.",
                fx(mo=-0.4, di=0.5, su=-0.6),
            ),
            Option(
                "no_rumours",
                "« Je ne commente pas les rumeurs. »",
                "Réponse attendue, sans conséquence.",
            ),
        ),
    ),
    Scenario(
        key="press_objective",
        category=Category.PRESS,
        title="L'objectif en question",
        text="{rank} du championnat, loin de l'objectif fixé ({target}). « L'objectif est-il encore réaliste ? »",
        trigger=_when(
            lambda s: (
                s.rank is not None
                and s.target_rank is not None
                and s.played >= s.regular_rounds / 3
                and s.rank >= s.target_rank + 3
            )
        ),
        weight=3,
        options=(
            Option(
                "believe",
                "« On y croit. »",
                "Message d'espoir, bien reçu.",
                fx(mo=0.2, di=0.2, su=0.3),
            ),
            Option(
                "lower",
                "« Il faut revoir nos ambitions. »",
                "Lucide, mais la direction n'a pas aimé l'entendre en public.",
                fx(mo=-0.2, di=-0.8, su=-0.5),
            ),
            Option(
                "judge_later", "« On jugera en fin de saison. »", "Réponse prudente, sans écho."
            ),
        ),
    ),
    # --- Suites des promesses faites en conférence de presse ----------------------------
    Scenario(
        key="press_promise_kept",
        category=Category.PRESS,
        title="Promesse tenue",
        text="Tu avais annoncé la couleur, l'équipe a suivi : victoire contre {opponent} ({score}). Les journaux te donnent raison.",
        options=(
            Option(
                "enjoy",
                "Savourer.",
                "Ta parole vaut de l'or, ce matin.",
                fx(mo=0.3, di=0.4, su=1.0),
            ),
        ),
    ),
    Scenario(
        key="press_promise_broken",
        category=Category.PRESS,
        title="La phrase qui revient",
        text="Tu avais promis la victoire. Résultat : {score} contre {opponent}. Les journalistes ressortent ta phrase.",
        options=(
            Option(
                "apologise",
                "Faire amende honorable.",
                "On salue ton honnêteté. L'épisode est vite oublié.",
                fx(di=-0.2, su=-0.4),
            ),
            Option(
                "better_team",
                "« On était meilleurs, le score ment. »",
                "Le vestiaire te suit ; les tribunes ricanent.",
                fx(mo=0.2, su=-0.8),
            ),
            Option(
                "silence",
                "Garder le silence.",
                "Le silence est interprété comme un aveu.",
                fx(su=-1.0),
            ),
        ),
    ),
    # --- Tête-à-tête avec les joueurs ---------------------------------------------------
    Scenario(
        key="playing_time",
        category=Category.PLAYER,
        title="Temps de jeu",
        text="{player} ({position}, {age} ans) frappe à ta porte : {starts} en {played} matchs. Il estime mériter mieux.",
        trigger=lambda s, rng: _playing_time(s),
        weight=3,
        options=(
            Option(
                "promise_start",
                "Lui promettre une place de titulaire au prochain match.",
                "Il repart regonflé. Il sera titulaire samedi, quoi qu'il arrive.",
                fx(mo=0.3),
                promise=Promise(PromiseKind.START, kept="start_kept", broken="start_broken"),
            ),
            Option(
                "earn_it",
                "« Gagne ta place à l'entraînement. »",
                "Il encaisse. Le reste du groupe apprécie ta cohérence.",
                fx(mo=-0.3, co=0.2),
            ),
            Option(
                "raise",
                "Augmenter son salaire de 20 % pour le garder motivé.",
                "Il accepte. La direction tique sur la masse salariale.",
                fx(mo=0.2, di=-0.3),
                action=Action.RAISE_WAGE,
            ),
            Option(
                "sell",
                "Le laisser partir : il est vendu.",
                "Il fait ses valises dans la journée. Le vestiaire est un peu secoué.",
                fx(mo=-0.2, co=-0.3, di=0.2),
                action=Action.SELL,
            ),
        ),
    ),
    Scenario(
        key="start_kept",
        category=Category.PLAYER,
        title="Promesse tenue",
        text="{player} a été titulaire comme promis. Il vient te remercier.",
        options=(
            Option(
                "carry_on",
                "« Continue comme ça. »",
                "Le vestiaire a vu que ta parole compte.",
                fx(mo=0.4, co=0.2),
            ),
        ),
    ),
    Scenario(
        key="start_broken",
        category=Category.PLAYER,
        title="Promesse non tenue",
        text="Tu avais promis à {player} une place de titulaire. Il n'a pas joué. Il est furieux.",
        options=(
            Option(
                "apologise",
                "S'excuser.",
                "Il accepte tes excuses, du bout des lèvres.",
                fx(mo=-0.3),
            ),
            Option(
                "competition",
                "« C'est la concurrence. »",
                "Il claque la porte. D'autres joueurs se demandent ce que vaut ta parole.",
                fx(mo=-0.6, co=-0.4),
            ),
            Option(
                "sell",
                "Le laisser partir.",
                "Il est vendu. Le vestiaire retient la leçon.",
                fx(mo=-0.3, co=-0.2),
                action=Action.SELL,
            ),
            Option(
                "raise",
                "Compenser par une augmentation.",
                "Il se calme. La direction, elle, s'agace.",
                fx(mo=-0.1, di=-0.3),
                action=Action.RAISE_WAGE,
            ),
        ),
    ),
    Scenario(
        key="contract_future",
        category=Category.PLAYER,
        title="Son avenir",
        text="{player} ({position}, {age} ans) est en fin de contrat en juin. Il veut être fixé sur son avenir.",
        trigger=_pick_player(
            lambda s: [
                p
                for p in s.players
                if p.years_left <= 1 and p.age <= 33 and p.overall >= s.median_overall
            ]
        ),
        weight=lambda s: 2 if s.played >= 3 else 0,
        options=(
            Option(
                "extend",
                "Prolonger de 2 saisons, avec 15 % d'augmentation.",
                "Il signe tout de suite. Un cadre de plus pour l'avenir.",
                fx(mo=0.4, co=0.3),
                action=Action.EXTEND,
            ),
            Option(
                "later",
                "« On en reparle en fin de saison. »",
                "Il aurait aimé une réponse. Il attendra.",
                fx(mo=-0.3),
            ),
            Option(
                "no",
                "« Pas de prolongation. »",
                "Il le prend très mal. La direction apprécie la rigueur.",
                fx(mo=-0.5, co=-0.4, di=0.3),
            ),
        ),
    ),
    Scenario(
        key="star_criticism",
        category=Category.PLAYER,
        title="Critique publique",
        text="Dans une interview, {player} remet en cause tes choix tactiques.",
        trigger=_pick_player(lambda s: s.best(3)),
        weight=lambda s: 2 if s.last is not None and s.last.margin < 0 else 0.7,
        options=(
            Option(
                "public",
                "Le recadrer publiquement.",
                "L'autorité est rétablie. Le vestiaire se crispe.",
                fx(mo=-0.3, co=-0.6, di=0.3),
            ),
            Option(
                "private",
                "En parler en privé.",
                "Discussion franche. Vous repartez sur de bonnes bases.",
                fx(co=0.3),
            ),
            Option(
                "agree",
                "Lui donner raison.",
                "Il se sent écouté. La direction se demande qui dirige.",
                fx(mo=0.4, di=-0.4),
            ),
            Option(
                "fine",
                "Lui infliger une amende.",
                "Il paie, sans un mot.",
                fx(mo=-0.4, co=0.2, di=0.2),
                money=5_000,
            ),
        ),
    ),
    Scenario(
        key="night_out",
        category=Category.PLAYER,
        title="Sortie nocturne",
        text="{player} a été aperçu en boîte de nuit à 3 heures du matin, à quelques jours du match. La photo circule.",
        trigger=_pick_player(lambda s: [p for p in s.fit_players if p.age <= 28]),
        weight=lambda s: 1.5 if s.last is not None and s.last.margin > 0 else 0.8,
        options=(
            Option(
                "fine",
                "Une amende.",
                "Il paie. Le message passe.",
                fx(mo=-0.2, co=0.3),
                money=3_000,
            ),
            Option(
                "private",
                "Un rappel à l'ordre en privé.",
                "Il promet que ça ne se reproduira pas.",
                fx(co=0.1),
            ),
            Option(
                "look_away",
                "Fermer les yeux.",
                "Les joueurs apprécient ta souplesse. La direction, moins. Et lui risque de recommencer.",
                fx(mo=0.3, co=-0.5, di=-0.3),
            ),
            Option(
                "group_run",
                "Footing collectif à 7 heures pour tout le monde.",
                "Le groupe souffre ensemble… et en veut un peu à {player}.",
                fx(mo=-0.5, co=0.5, fr=-2.0),
            ),
        ),
    ),
    Scenario(
        key="night_out_again",
        category=Category.PLAYER,
        title="Récidive",
        text="{player} s'est encore fait prendre en pleine nuit. La dernière fois, tu avais fermé les yeux. Le vestiaire attend ta réaction.",
        trigger=lambda s, rng: _repeat_offender(s),
        weight=3,
        options=(
            Option(
                "heavy_fine",
                "Une lourde amende.",
                "Il paie cher. Le groupe trouve que c'était le minimum.",
                fx(mo=-0.2, co=0.2),
                money=10_000,
            ),
            Option(
                "sell",
                "Le vendre.",
                "Il quitte le club. Un exemple pour tout le monde.",
                fx(mo=-0.3, co=0.4, di=0.3),
                action=Action.SELL,
            ),
            Option(
                "look_away",
                "Fermer les yeux, encore.",
                "Le vestiaire n'en peut plus du deux poids, deux mesures.",
                fx(co=-0.8, di=-0.5),
            ),
        ),
    ),
    Scenario(
        key="training_fight",
        category=Category.PLAYER,
        title="Bagarre à l'entraînement",
        text="{player} et {player2}, concurrents au poste de {position}, en sont venus aux mains à l'entraînement.",
        trigger=lambda s, rng: _rivals(s, rng),
        weight=0.8,
        options=(
            Option(
                "fine_both",
                "Les sanctionner tous les deux.",
                "Deux amendes, et l'affaire est close.",
                fx(co=0.2),
                money=4_000,
            ),
            Option(
                "meeting",
                "Une réunion à trois.",
                "Ils se serrent la main. Vraiment, cette fois.",
                fx(co=0.5),
            ),
            Option(
                "let_go",
                "« Le vestiaire réglera ça. »",
                "La tension persiste et déborde sur le groupe.",
                fx(mo=-0.2, co=-0.8),
            ),
            Option(
                "sell",
                "Vendre {player}, à l'origine de la bagarre.",
                "Radical. Le calme revient, au prix d'un joueur.",
                fx(mo=-0.3, co=0.3),
                action=Action.SELL,
            ),
        ),
    ),
    Scenario(
        key="newborn",
        category=Category.PLAYER,
        title="Heureux événement",
        text="{player} va être papa cette semaine. Il demande deux jours pour être auprès des siens.",
        trigger=_pick_player(lambda s: [p for p in s.fit_players if 25 <= p.age <= 34]),
        weight=0.6,
        options=(
            Option(
                "granted",
                "Accordé, évidemment.",
                "Il revient ému et reconnaissant.",
                fx(mo=0.4, co=0.2),
            ),
            Option("one_day", "Un jour seulement.", "Il comprend, sans enthousiasme.", fx(mo=-0.1)),
            Option(
                "refused",
                "Refusé : le match d'abord.",
                "Le vestiaire est choqué. La direction salue ta rigueur.",
                fx(mo=-0.6, co=-0.4, di=0.1),
            ),
        ),
    ),
    Scenario(
        key="youth_wants_chance",
        category=Category.PLAYER,
        title="Un espoir s'impatiente",
        text="{player} ({position}, {age} ans), le meilleur espoir du centre de formation, réclame sa chance chez les pros.",
        trigger=_pick_player(
            lambda s: sorted(s.youths, key=lambda p: p.overall, reverse=True)[:1], random_pick=False
        ),
        options=(
            Option(
                "promote",
                "Le promouvoir chez les pros.",
                "Il saute de joie. Quelques anciens voient arriver un concurrent.",
                fx(mo=0.2, co=-0.2, su=0.2),
                action=Action.PROMOTE,
            ),
            Option(
                "patience",
                "« Patience, tu progresses chez les espoirs. »",
                "Il est déçu, mais il comprend.",
                fx(mo=-0.1),
            ),
            Option(
                "train_with_pros",
                "L'inviter aux entraînements des pros.",
                "Il découvre le haut niveau. Le groupe l'adopte vite.",
                fx(co=0.2),
            ),
        ),
    ),
    Scenario(
        key="veteran_mentor",
        category=Category.PLAYER,
        title="Le grand frère",
        text="{player}, {age} ans, propose d'encadrer les plus jeunes du groupe.",
        trigger=_pick_player(lambda s: [p for p in s.players if p.age >= 32]),
        weight=0.8,
        options=(
            Option(
                "accept", "Accepter avec plaisir.", "Les jeunes boivent ses paroles.", fx(co=0.6)
            ),
            Option("decline", "Décliner : chacun son rôle.", "Il est un peu vexé.", fx(mo=-0.2)),
        ),
    ),
    Scenario(
        key="injured_blues",
        category=Category.PLAYER,
        title="Le moral du blessé",
        text="{player}, absent encore {weeks} semaines, déprime loin du groupe.",
        trigger=lambda s, rng: _long_injured(s, rng),
        weight=1.5,
        options=(
            Option(
                "travel",
                "Le faire voyager avec l'équipe.",
                "Il retrouve le sourire, et le groupe un supporter de plus.",
                fx(mo=0.2, co=0.4),
                money=-2_000,
            ),
            Option("rest", "Le laisser se soigner tranquillement.", "Il reste dans son coin."),
            Option(
                "call", "L'appeler chaque semaine.", "Un geste simple, qu'il apprécie.", fx(mo=0.1)
            ),
        ),
    ),
    Scenario(
        key="captain_talk",
        category=Category.PLAYER,
        title="Le capitaine veut parler",
        text="Après deux défaites, {player}, ton cadre le plus utilisé, demande à prendre la parole devant le groupe.",
        trigger=lambda s, rng: _captain(s) if s.streak <= -2 else None,
        weight=3,
        options=(
            Option(
                "let_him",
                "Le laisser parler.",
                "Discours fort. Le groupe se resserre.",
                fx(mo=0.4, co=0.6),
            ),
            Option(
                "myself",
                "Prendre la parole toi-même.",
                "Ton discours est entendu, la direction apprécie.",
                fx(mo=0.3, di=0.2),
            ),
            Option(
                "work",
                "« Pas de discours. Au travail. »",
                "Séance musclée. Le message est clair.",
                fx(co=0.2, fr=-1.0),
            ),
        ),
    ),
    # --- Vestiaire et staff -------------------------------------------------------------
    Scenario(
        key="squad_tired",
        category=Category.SQUAD,
        title="Le groupe est cuit",
        text="Ton préparateur physique tire la sonnette d'alarme : les organismes sont fatigués, les blessures guettent.",
        trigger=_when(lambda s: s.note("freshness") < 13),
        weight=4,
        options=(
            Option(
                "rest",
                "Deux jours de repos complet.",
                "Les jambes reviennent. La direction trouve ça un peu cher payé.",
                fx(fr=3.0, di=-0.2),
            ),
            Option("light", "Des séances allégées.", "Le groupe souffle un peu.", fx(fr=1.5)),
            Option(
                "keep_going",
                "Maintenir la charge.",
                "Le groupe serre les dents. Les organismes trinquent.",
                fx(mo=-0.3, co=0.3, fr=-1.0),
            ),
        ),
    ),
    Scenario(
        key="team_building",
        category=Category.SQUAD,
        title="Souder le groupe",
        text="Tes adjoints proposent d'emmener le groupe deux jours au Pays basque pour souder les liens.",
        trigger=_when(lambda s: True),
        weight=lambda s: 3 if s.note("cohesion") < 10 else 0.5,
        options=(
            Option(
                "trip",
                "Le séjour de deux jours.",
                "Rafting, pelote et grandes tablées : le groupe revient soudé et reposé.",
                fx(mo=0.5, co=1.2, fr=1.0),
                money=-25_000,
            ),
            Option(
                "dinner",
                "Un simple repas d'équipe.",
                "Une bonne soirée, sans excès.",
                fx(co=0.5),
                money=-4_000,
            ),
            Option("not_now", "« Pas le moment. »", "Le projet est rangé dans un tiroir."),
        ),
    ),
    Scenario(
        key="players_bonus",
        category=Category.SQUAD,
        title="La question des primes",
        text="Les cadres du vestiaire viennent te voir : ils voudraient une prime pour la suite.",
        trigger=_when(lambda s: s.streak >= 3 or s.big_game),
        weight=2,
        options=(
            Option(
                "pay_now",
                "Une prime exceptionnelle tout de suite.",
                "Le vestiaire exulte. La direction grince des dents.",
                fx(mo=1.0, di=-0.3),
                money=-30_000,
            ),
            Option(
                "if_win",
                "Une prime en cas de victoire au prochain match.",
                "Marché conclu. À eux de jouer.",
                fx(mo=0.4),
                promise=Promise(PromiseKind.WIN, kept="bonus_paid", broken=None),
            ),
            Option("refuse", "Refuser.", "Les cadres repartent déçus.", fx(mo=-0.5)),
        ),
    ),
    Scenario(
        key="bonus_paid",
        category=Category.SQUAD,
        title="Prime de victoire",
        text="Victoire contre {opponent} ({score}) : la prime promise est due.",
        options=(
            Option(
                "pay",
                "Verser la prime.",
                "Promesse tenue, le vestiaire est aux anges.",
                fx(mo=0.6, co=0.2),
                money=-20_000,
            ),
        ),
    ),
    Scenario(
        key="extra_video",
        category=Category.SQUAD,
        title="Séance vidéo",
        text="Après la défaite contre {opponent}, les joueurs proposent d'eux-mêmes une séance vidéo supplémentaire.",
        trigger=_when(lambda s: s.last is not None and s.last.margin < 0),
        options=(
            Option(
                "accept",
                "Accepter.",
                "Séance studieuse. Tout le monde a compris ce qui n'allait pas.",
                fx(co=0.4, fr=-0.8, di=0.2),
            ),
            Option("refuse", "« Coupez, reposez-vous. »", "Ils apprécient la coupure.", fx(mo=0.1)),
        ),
    ),
    Scenario(
        key="frozen_pitch",
        category=Category.SQUAD,
        title="Terrain gelé",
        text="Le terrain d'entraînement est gelé pour la semaine.",
        trigger=_when(lambda s: s.day.month in (12, 1, 2)),
        weight=1.5,
        options=(
            Option(
                "indoors",
                "Séances en salle.",
                "Moins de rugby, plus de récupération.",
                fx(co=-0.3, fr=1.0),
            ),
            Option(
                "move",
                "Délocaliser l'entraînement à 100 km.",
                "Organisation lourde, mais le travail est fait.",
                fx(co=0.3),
                money=-8_000,
            ),
            Option(
                "anyway",
                "S'entraîner quand même.",
                "Le sol est dur, les corps aussi.",
                fx(co=0.2, fr=-1.5),
            ),
        ),
    ),
    Scenario(
        key="staff_poached",
        category=Category.SQUAD,
        title="Ton adjoint courtisé",
        text="Un club anglais veut recruter {staff}, ton {role}.",
        trigger=lambda s, rng: _poached(s),
        weight=0.8,
        options=(
            Option(
                "keep",
                "Le retenir avec 25 % d'augmentation.",
                "Il reste. Le staff est rassuré.",
                fx(co=0.2),
                action=Action.STAFF_RAISE,
            ),
            Option(
                "let_go",
                "Le laisser partir.",
                "Il s'en va. La direction apprécie l'économie ; le poste est à pourvoir.",
                fx(co=-0.2, di=0.2),
                action=Action.STAFF_LEAVE,
            ),
        ),
    ),
    # --- Direction ----------------------------------------------------------------------
    Scenario(
        key="board_summons",
        category=Category.BOARD,
        title="Convocation",
        text="Le président te convoque dans son bureau. Il ne sourit pas.",
        trigger=_when(lambda s: s.note("board") < 8),
        weight=4,
        options=(
            Option(
                "plan",
                "Présenter un plan de redressement.",
                "Le président t'écoute. Les joueurs sentent la pression monter.",
                fx(mo=-0.2, di=0.8),
            ),
            Option(
                "time", "Demander du temps.", "« Du temps, tu n'en as plus beaucoup. »", fx(di=-0.2)
            ),
            Option(
                "blame",
                "Blâmer le recrutement.",
                "Le président a lui-même validé ces recrues. Mauvaise idée.",
                fx(co=-0.3, di=-0.8),
            ),
            Option(
                "resign",
                "Mettre ta démission dans la balance.",
                "Quitte ou double.",
                gamble=_resignation_gamble,
            ),
        ),
    ),
    Scenario(
        key="board_savings",
        category=Category.BOARD,
        title="Les comptes sont dans le rouge",
        text="La trésorerie est négative. La direction exige des économies.",
        trigger=_when(lambda s: s.balance < 0),
        weight=4,
        options=(
            Option(
                "cut_bonuses",
                "Baisser les primes des joueurs.",
                "La direction est rassurée. Le vestiaire grogne.",
                fx(mo=-0.8, di=0.8),
                money=15_000,
            ),
            Option(
                "refuse",
                "Refuser : on ne touche pas au sportif.",
                "Le vestiaire te soutient, la direction beaucoup moins.",
                fx(mo=0.2, di=-1.0),
            ),
            Option(
                "sell_promise",
                "Promettre de vendre un joueur.",
                "La direction prend note. À toi de passer par la page Transferts.",
                fx(di=0.3, su=-0.2),
            ),
        ),
    ),
    Scenario(
        key="sponsor_event",
        category=Category.BOARD,
        title="Soirée sponsor",
        text="Le principal sponsor organise une soirée mardi et souhaite la présence des joueurs.",
        trigger=_when(lambda s: True),
        options=(
            Option(
                "everyone",
                "Tout le groupe y va.",
                "Le sponsor est ravi. Les joueurs, fatigués.",
                fx(mo=-0.2, fr=-1.0, di=0.5),
                money=20_000,
            ),
            Option(
                "captain", "Seulement le capitaine.", "Compromis accepté.", fx(di=0.2), money=8_000
            ),
            Option(
                "refuse", "Refuser : semaine de match.", "La direction est contrariée.", fx(di=-0.4)
            ),
        ),
    ),
    Scenario(
        key="board_youth",
        category=Category.BOARD,
        title="La politique jeunes",
        text="Le président aimerait voir plus de jeunes du centre de formation chez les pros.",
        trigger=lambda s, rng: _best_youth(s),
        weight=lambda s: 1.5 if s.academy_level >= 3 else 0.7,
        options=(
            Option(
                "promote",
                "Promouvoir {player}, le meilleur espoir.",
                "Le président est ravi, les supporters aussi.",
                fx(di=0.6, su=0.3),
                action=Action.PROMOTE,
            ),
            Option(
                "best_play",
                "« Je fais jouer les meilleurs. »",
                "Les joueurs approuvent. Le président, non.",
                fx(mo=0.3, di=-0.4),
            ),
            Option(
                "later",
                "« Ils ne sont pas encore prêts. »",
                "Le président accepte, pour cette fois.",
                fx(di=-0.1),
            ),
        ),
    ),
    Scenario(
        key="board_delighted",
        category=Category.BOARD,
        title="Le président est ravi",
        text="Le président te félicite chaleureusement pour les résultats.",
        trigger=_when(lambda s: s.note("board") > 15 and s.streak >= 2),
        weight=2,
        options=(
            Option("thanks", "Le remercier.", "Relation au beau fixe.", fx(di=0.5)),
            Option(
                "budget",
                "En profiter pour demander un budget de recrutement.",
                "Il accepte, mais n'aime pas qu'on lui force la main.",
                fx(di=-0.5),
                money=150_000,
            ),
        ),
    ),
    # --- Supporters ---------------------------------------------------------------------
    Scenario(
        key="fans_banner",
        category=Category.FANS,
        title="Banderole hostile",
        text="Au dernier match, une banderole réclamait ton départ.",
        trigger=_when(lambda s: s.note("supporters") < 8),
        weight=4,
        options=(
            Option(
                "meet",
                "Aller à la rencontre des ultras.",
                "Échange musclé, mais respecté.",
                fx(di=-0.2, su=1.2),
            ),
            Option("letter", "Publier une lettre ouverte.", "Le ton est apprécié.", fx(su=0.6)),
            Option("ignore", "Ignorer.", "Le fossé se creuse.", fx(su=-0.6)),
            Option(
                "discount",
                "Places à prix réduit au prochain match.",
                "Le geste est apprécié, le stade se remplit.",
                fx(su=1.2),
                money=-15_000,
            ),
        ),
    ),
    Scenario(
        key="fans_away_trip",
        category=Category.FANS,
        title="Le grand déplacement",
        text="Les supporters organisent un grand déplacement pour le match chez {next}.",
        trigger=_when(lambda s: s.next is not None and not s.next.at_home),
        weight=lambda s: 2.5 if s.big_game else 0.7,
        options=(
            Option(
                "buses",
                "Payer la moitié des bus.",
                "Le parcage sera plein et bruyant.",
                fx(mo=0.3, su=1.0),
                money=-10_000,
            ),
            Option(
                "video",
                "Enregistrer un message vidéo de remerciement.",
                "Partagé des milliers de fois.",
                fx(su=0.4),
            ),
            Option("nothing", "Ne rien faire.", "Ils viendront quand même. Un peu déçus."),
        ),
    ),
    Scenario(
        key="fans_open_training",
        category=Category.FANS,
        title="Entraînement ouvert",
        text="Les associations de supporters demandent un entraînement ouvert au public.",
        trigger=_when(lambda s: True),
        options=(
            Option(
                "open",
                "Ouvrir les portes.",
                "Ambiance de fête, séance moins sérieuse.",
                fx(fr=-0.5, su=1.0),
            ),
            Option(
                "signing",
                "Une séance de dédicaces à la place.",
                "Les enfants repartent avec leurs autographes.",
                fx(fr=-0.3, su=0.6),
            ),
            Option(
                "closed",
                "Huis clos.",
                "Le groupe travaille tranquille. Les supporters boudent.",
                fx(co=0.3, su=-0.4),
            ),
        ),
    ),
    Scenario(
        key="hospital_visit",
        category=Category.FANS,
        title="Visite à l'hôpital",
        text="L'hôpital pédiatrique de la ville invite les joueurs à rendre visite aux enfants.",
        trigger=_when(lambda s: True),
        weight=lambda s: 3 if s.day.month == 12 else 0.6,
        options=(
            Option(
                "go",
                "Y aller avec tout le groupe.",
                "Des sourires partout. Le groupe en ressort grandi.",
                fx(mo=0.3, co=0.3, fr=-0.3, su=0.8),
            ),
            Option(
                "delegation",
                "Envoyer une délégation de cinq joueurs.",
                "Belle visite, bien relayée.",
                fx(su=0.4),
            ),
            Option(
                "decline", "Décliner : semaine chargée.", "La presse locale le relève.", fx(su=-0.3)
            ),
        ),
    ),
    # --- Médias -------------------------------------------------------------------------
    Scenario(
        key="documentary",
        category=Category.MEDIA,
        title="Caméras au vestiaire",
        text="Une plateforme de streaming veut tourner une série documentaire au cœur du club.",
        trigger=_when(lambda s: True),
        weight=0.6,
        options=(
            Option(
                "full",
                "Accès total.",
                "Gros chèque et belle visibilité. Les joueurs se sentent épiés.",
                fx(mo=-0.2, co=-0.6, su=0.8),
                money=40_000,
            ),
            Option(
                "limited",
                "Accès limité, hors vestiaire.",
                "Un compromis raisonnable.",
                fx(co=-0.2, su=0.3),
                money=15_000,
            ),
            Option("refuse", "Refuser.", "Le vestiaire reste un sanctuaire."),
        ),
    ),
    Scenario(
        key="pundit_criticism",
        category=Category.MEDIA,
        title="La critique d'un ancien",
        text="Un ancien joueur du club, consultant télé, a démoli ton équipe après la défaite contre {opponent}.",
        trigger=_when(lambda s: s.last is not None and s.last.margin < 0),
        weight=0.8,
        options=(
            Option(
                "reply",
                "Lui répondre sèchement.",
                "Les supporters aiment le panache, la direction moins.",
                fx(di=-0.3, su=0.3),
            ),
            Option(
                "invite",
                "L'inviter à l'entraînement.",
                "Il vient, il échange, il change de ton.",
                fx(co=0.2, su=0.5),
            ),
            Option("ignore", "Ignorer.", "La polémique s'éteint d'elle-même."),
        ),
    ),
    # --- Contradiction : une parole publique trahie ------------------------------------
    Scenario(
        key="contradiction",
        category=Category.PRESS,
        title="Parole trahie",
        text="Tu avais juré que {player} n'était pas à vendre. Il est parti. La presse ne l'a pas oublié.",
        trigger=lambda s, rng: _broken_word(s),
        urgent=True,
        options=(
            Option(
                "explain",
                "Expliquer les raisons du départ.",
                "On t'écoute, sans vraiment te croire.",
                fx(di=-0.3, su=-0.6),
            ),
            Option(
                "own_it",
                "« J'ai changé d'avis. C'est mon droit. »",
                "Franchise appréciée par la direction, pas par les tribunes.",
                fx(su=-1.0),
            ),
            Option("deflect", "Botter en touche.", "La polémique enfle.", fx(di=-0.3, su=-1.2)),
        ),
    ),
    # --- Avis : fin de pige d'un joker médical (api/jokers.py) -------------------------
    Scenario(
        key="joker_end",
        category=Category.PLAYER,
        title="Fin de pige",
        text="{reason} : la pige de {player}, ton joker médical, se termine. Il aimerait rester et demande {wage} par saison sur {years_label}. Lui proposer un vrai contrat ?",
        default="release",
        scheduled=False,
        options=(
            Option(
                "sign",
                "Lui proposer un contrat ({wage} par saison, {years_label}).",
                "{player} signe avec le club. Le vestiaire apprécie la fidélité.",
                fx(mo=0.2, co=0.3),
                action=Action.KEEP_JOKER,
            ),
            Option(
                "release",
                "Le remercier et le laisser partir.",
                "{player} quitte le club et redevient agent libre.",
                action=Action.RELEASE_JOKER,
            ),
        ),
    ),
]

CATALOGUE: dict[str, Scenario] = {scenario.key: scenario for scenario in SCENARIOS}


# --- Triggers qui demandent un peu de calcul ----------------------------------------------


def _playing_time(s: Situation) -> dict | None:
    """Un bon joueur, apte, titularisé dans moins de 20 % des matchs."""
    if s.played < 4:
        return None
    unhappy = [
        p
        for p in s.fit_players
        if p.age >= 21 and p.starts < 0.2 * s.played and p.overall >= s.median_overall
    ]
    if not unhappy:
        return None
    player = max(unhappy, key=lambda p: p.overall)
    ctx = with_player(base_context(s), player)
    starts = {0: "aucune titularisation", 1: "une seule titularisation"}
    ctx.update(
        starts=starts.get(player.starts, f"{player.starts} titularisations"), played=s.played
    )
    return ctx


def _repeat_offender(s: Situation) -> dict | None:
    """Un joueur sur qui tu as fermé les yeux après une sortie nocturne."""
    ids = {p.player_id for p in s.past if p.scenario == "night_out" and p.choice == "look_away"}
    candidates = [p for p in s.fit_players if p.id in ids]
    return with_player(base_context(s), candidates[0]) if candidates else None


def _rivals(s: Situation, rng: random.Random) -> dict | None:
    by_position: dict[Position, list[PlayerInfo]] = {}
    for player in s.fit_players:
        by_position.setdefault(player.position, []).append(player)
    pairs = [players for players in by_position.values() if len(players) >= 2]
    if not pairs:
        return None
    first, second = rng.sample(rng.choice(pairs), 2)
    return with_player(with_player(base_context(s), first), second, suffix="2")


def _long_injured(s: Situation, rng: random.Random) -> dict | None:
    injured = [p for p in s.players if p.injured_weeks >= 6]
    if not injured:
        return None
    player = rng.choice(injured)
    ctx = with_player(base_context(s), player)
    ctx["weeks"] = player.injured_weeks
    return ctx


def _captain(s: Situation) -> dict | None:
    """Le cadre le plus titularisé (le plus âgé à égalité)."""
    if not s.fit_players:
        return None
    captain = max(s.fit_players, key=lambda p: (p.starts, p.age))
    return with_player(base_context(s), captain)


def _poached(s: Situation) -> dict | None:
    good = [member for member in s.staff if member.level >= 4]
    if not good:
        return None
    member = max(good, key=lambda m: m.level)
    ctx = base_context(s)
    ctx.update(staff=member.name, staff_id=member.id, role=STAFF_LABELS[member.role])
    return ctx


def _best_youth(s: Situation) -> dict | None:
    if not s.youths:
        return None
    return with_player(base_context(s), max(s.youths, key=lambda p: p.overall))


def _broken_word(s: Situation) -> dict | None:
    """Un joueur dit « pas à vendre » cette saison, qui n'est plus au club."""
    present = {p.id for p in s.players}
    settled = {p.player_id for p in s.past if p.scenario == "contradiction"}
    for past in s.past:
        if (
            past.scenario == "press_star_rumour"
            and past.choice == "not_for_sale"
            and past.player_id not in present
            and past.player_id not in settled
            and (s.day - past.day).days <= 365
        ):
            ctx = base_context(s)
            ctx.update(player=past.player_name or "ton joueur", player_id=past.player_id)
            return ctx
    return None


# --- Tirage ------------------------------------------------------------------------------


@dataclass(frozen=True)
class Draft:
    """Une affaire tirée : le scénario et les variables de ses textes."""

    scenario: Scenario
    context: dict

    @property
    def player_id(self) -> int | None:
        return self.context.get("player_id")


def is_due(matches_since_affair: int, rng: random.Random) -> bool:
    """Le moment d'une nouvelle affaire est-il venu ? (tous les 2 ou 3 matchs)"""
    if matches_since_affair < MIN_GAP:
        return False
    return matches_since_affair >= MAX_GAP or rng.random() < GAP_CHANCE


def draw(s: Situation, rng: random.Random) -> Draft | None:
    """Affaire à régler après une journée, ou None.

    Seulement tous les 2 ou 3 matchs (`is_due`). Les affaires urgentes (parole
    trahie...) passent d'abord ; sinon, un scénario au hasard parmi ceux qui
    s'appliquent, pondéré. Un scénario déjà tombé cette saison ne revient pas, et
    un même joueur n'est pas sollicité deux fois de suite.
    """
    if not is_due(s.matches_since_affair, rng):
        return None
    asked = {p.scenario for p in s.past if p.this_season}
    busy = {
        p.player_id
        for p in s.past
        if p.player_id is not None and (s.day - p.day).days < PLAYER_COOLDOWN_DAYS
    }

    for scenario in SCENARIOS:
        if scenario.urgent and scenario.trigger is not None and scenario.key not in asked:
            ctx = scenario.trigger(s, rng)
            if ctx is not None:
                return Draft(scenario, ctx)

    candidates: list[tuple[Draft, float]] = []
    for scenario in SCENARIOS:
        if scenario.trigger is None or scenario.urgent or scenario.key in asked:
            continue
        weight = scenario.weight_for(s)
        if weight <= 0:
            continue
        ctx = scenario.trigger(s, rng)
        if ctx is None or ctx.get("player_id") in busy:
            continue
        candidates.append((Draft(scenario, ctx), weight))
    if not candidates:
        return None
    drafts, weights = zip(*candidates, strict=True)
    return rng.choices(drafts, weights=weights)[0]


def follow_up(key: str, context: dict, result: Result | None) -> Draft:
    """Suite d'une promesse : même joueur, et le score du match qui l'a tranchée."""
    ctx = dict(context)
    if result is not None:
        ctx["opponent"] = result.opponent
        ctx["score"] = f"{result.scored}-{result.conceded}"
    return Draft(CATALOGUE[key], ctx)


def promise_kept(kind: PromiseKind, player_id: int | None, lineup: list[int], won: bool) -> bool:
    if kind == PromiseKind.START:
        return player_id in lineup
    return won
