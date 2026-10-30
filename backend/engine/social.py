"""Les réseaux sociaux du joueur incarné (carrière de joueur) : ce qu'on dit de lui.

Trois voix : les médias (comptes de rédaction, factuels), les journalistes (un avis
signé) et les supporters (de son club, et parfois de l'adversaire). Tous parlent de ce
que le jeu sait : sa signature, chacun de ses matchs (le score, ses minutes, sa note,
ses essais), ses premières fois (premier match, première titularisation, premier
essai) et ses actions marquantes en direct (engine/dilemmas.py). Un match où il n'a
pas joué fait parfois réagir les supporters.

Le ton suit sa note : une grande performance fait s'enflammer tout le monde, un
match raté fait grincer. Ses abonnés (`followers`) montent avec ses matchs, ses
notes et ses essais ; les mentions et les partages suivent sa notoriété.

Rien n'est tiré au hasard d'un appel à l'autre : le même parcours donne le même fil.
Médias et journalistes sont inventés.
"""

import datetime
import random
from dataclasses import dataclass, field
from enum import StrEnum

from engine.journal import cap, note, of
from models import Position


class Voice(StrEnum):
    MEDIA = "media"
    JOURNALIST = "journalist"
    FAN = "fan"
    RIVAL = "rival"  # supporter de l'adversaire


class Tone(StrEnum):
    PRAISE = "praise"
    NEUTRAL = "neutral"
    CRITIC = "critic"


@dataclass(frozen=True)
class Author:
    name: str
    handle: str
    voice: Voice
    verified: bool = False


MEDIA = (
    Author("Ovalie Matin", "ovaliematin", Voice.MEDIA, True),
    Author("La Gazette de l'Ovale", "gazetteovale", Voice.MEDIA, True),
    Author("Terre d'Essais", "terredessais", Voice.MEDIA, True),
)
JOURNALISTS = (
    Author("Julien Marcillac", "jmarcillac", Voice.JOURNALIST, True),
    Author("Sophie Larrieu", "sophielarrieu_rugby", Voice.JOURNALIST, True),
    Author("Hugo Bastide", "hbastide", Voice.JOURNALIST, True),
    Author("Claire Etcheverry", "c_etche", Voice.JOURNALIST, True),
)
FAN_NAMES = (
    "Mathieu", "Laura", "Kévin", "Pauline", "Seb", "Manon", "Thomas", "Julie", "Xabi",
    "Camille", "Nico", "Inès", "Bastien", "Léa", "Romain", "Chloé", "Maïté", "Fred",
)  # fmt: skip

POSITIONS = {
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

# Abonnés : au départ, puis par match joué, par point de note au-dessus de 6, par essai.
FOLLOWERS_START = 120
FOLLOWERS_PER_MATCH = 25
FOLLOWERS_PER_RATING_POINT = 90
FOLLOWERS_PER_TRY = 180
FOLLOWERS_PER_START = 40  # titularisation
# Part des matchs sans lui qui font réagir un supporter.
ABSENT_REACTION = 0.35

# Paliers de note : (à partir de, palier), du meilleur au moins bon.
TIERS = ((8.0, "star"), (7.0, "good"), (6.0, "fair"), (5.0, "poor"), (0.0, "bad"))

# Une action marquante en direct, en quelques mots : réussie, puis ratée.
MOMENT_WON = {
    "step": "ce crochet", "fend": "ce raffût", "pass": "cette passe au soutien",
    "dive": "cet essai en force", "offload": "cette passe décisive",
    "recycle": "ce ballon conservé près de la ligne", "smash": "ce plaquage offensif",
    "hold": "ce plaquage à deux", "ball": "ce ballon arraché", "jackal": "ce grattage",
    "counter": "ce contre-ruck", "fold": "ce replacement", "drive": "cette mêlée conquérante",
    "steady": "cette mêlée solide", "maul": "cet essai au bout du maul",
    "front": "cette touche propre", "drop": "ce drop", "grubber": "ce petit par-dessus",
    "hands": "ce ballon bien joué", "cross": "cette transversale au pied",
    "flat": "cette passe dans l'intervalle", "touch": "cette touche trouvée",
    "box": "cette chandelle parfaite", "snipe": "ce départ au ras", "serve": "ce service propre",
    "outside": "ce débordement", "inside": "ce repiqué", "chip": "ce petit par-dessus",
    "run": "cette relance", "up_and_under": "cette chandelle", "back": "ce lancer au fond",
    "hit_back": "ce coup de sang impuni", "referee": "ce calme face à la provocation",
    "walk_away": "ce sang-froid", "finish": "ce finish", "dummy": "cette feinte de passe",
    "give": "cette passe décisive",
}  # fmt: skip
MOMENT_LOST = {
    "step": "ce crochet qui ne passe pas", "fend": "ce raffût contré",
    "pass": "cette passe dans les pieds", "dive": "ce ballon perdu sur la ligne",
    "offload": "cette passe interceptée", "recycle": "ce ballon ralenti",
    "smash": "ce plaquage manqué", "hold": "ce plaquage raté", "ball": "ce plaquage haut",
    "jackal": "cette pénalité au sol", "counter": "ce contre-ruck pour rien",
    "fold": "ce replacement en retard", "drive": "cette mêlée qui craque",
    "steady": "cette mêlée qui tourne", "maul": "ce maul stoppé",
    "front": "ce lancer contré", "drop": "ce drop à côté", "grubber": "ce coup de pied perdu",
    "hands": "cet en-avant", "cross": "cette transversale perdue",
    "flat": "cette passe interceptée", "touch": "cette touche manquée",
    "box": "cette chandelle trop longue", "snipe": "ce départ au ras stoppé",
    "serve": "ce service raté", "outside": "ce débordement avorté",
    "inside": "ce repiqué contré", "chip": "ce petit par-dessus raté",
    "run": "cette relance hasardeuse", "up_and_under": "cette chandelle perdue",
    "back": "ce lancer au fond intercepté", "hit_back": "ce coup de sang",
    "referee": "ces protestations", "walk_away": "ce moment d'absence",
    "finish": "ce ballon perdu à l'essai", "dummy": "cette feinte qui ne prend pas",
    "give": "cette passe en avant",
}  # fmt: skip


@dataclass(frozen=True)
class Hero:
    first_name: str
    last_name: str
    position: Position
    club: str  # son club d'aujourd'hui

    @property
    def name(self) -> str:
        return f"{self.first_name} {self.last_name}"


@dataclass(frozen=True)
class Appearance:
    """Un match de son club : ce qu'il y a fait (`minutes` à 0 s'il n'a pas joué)."""

    match_id: int
    date: datetime.date
    club: str
    opponent: str
    score_for: int
    score_against: int
    minutes: int
    rating: float | None
    tries: int
    started: bool
    moments: list[dict] = field(default_factory=list)  # `Outcome.to_dict()`

    @property
    def played(self) -> bool:
        return self.minutes > 0

    @property
    def result(self) -> str:
        if self.score_for > self.score_against:
            return "win"
        return "draw" if self.score_for == self.score_against else "loss"


@dataclass(frozen=True)
class Post:
    date: datetime.date
    time: str  # « 22:14 »
    author: Author
    text: str
    tone: Tone
    likes: int
    reposts: int
    match_id: int | None = None


@dataclass
class Feed:
    followers: int
    gain: int  # abonnés gagnés au dernier match
    posts: list[Post]  # du plus récent au plus ancien


def tier(rating: float | None) -> str:
    value = rating if rating is not None else 6.0
    return next(name for floor, name in TIERS if value >= floor)


def _tag(club: str) -> str:
    """Un mot du club pour les pseudos des supporters : « Biarritz Olympique » -> biarritz."""
    words = [w for w in club.replace("-", " ").split() if len(w) > 3 and w[0].isupper()]
    word = (words[0] if words else club.split()[0]).lower()
    plain = str.maketrans("éèêëàâäîïôöûüç'", "eeeeaaaiioouuc_")
    return word.translate(plain)


def _fan(club: str, rng: random.Random, voice: Voice = Voice.FAN) -> Author:
    first = rng.choice(FAN_NAMES)
    tag = _tag(club)
    handle = rng.choice(
        (
            f"{first.lower()}_{tag}",
            f"allez_{tag}{rng.randint(1, 99)}",
            f"{tag}_ultra{rng.randint(1, 9)}",
        )
    )
    plain = str.maketrans("éèêëàâäîïôöûüç", "eeeeaaaiioouuc")
    return Author(f"{first} · {club}", handle.translate(plain), voice)


def _engagement(fame: int, weight: float, rng: random.Random) -> tuple[int, int]:
    """Mentions « j'aime » et partages d'une publication, à la mesure de sa notoriété."""
    likes = max(1, round((8 + fame * 0.04) * weight * rng.uniform(0.6, 1.4)))
    return likes, max(0, round(likes * rng.uniform(0.08, 0.22)))


def _clock(hour: int, rng: random.Random) -> str:
    return f"{hour:02d}:{rng.randint(0, 59):02d}"


def _score(a: Appearance) -> str:
    return f"{a.club} {a.score_for}-{a.score_against} {a.opponent}"


def _moment(a: Appearance, success: bool) -> dict | None:
    """L'action la plus marquante du match, réussie ou ratée (la plus grosse variation)."""
    chosen = [m for m in a.moments if m["success"] == success]
    if not chosen:
        return None
    return max(chosen, key=lambda m: abs(m["delta"]))


def _media(hero: Hero, a: Appearance, firsts: list[str], rng: random.Random) -> tuple[str, Tone]:
    level = tier(a.rating)
    who = f"{hero.name} ({POSITIONS[hero.position]})"
    role = "titulaire" if a.started else f"entré en jeu ({a.minutes} min)"
    tries = f", {a.tries} essai{'s' if a.tries > 1 else ''}" if a.tries else ""
    if "debut" in firsts:
        text = f"Premiers pas en pro pour {who} : {role}{tries}. {_score(a)}."
    elif "first_try" in firsts:
        text = f"Premier essai chez les pros pour {who} ! {_score(a)}."
    elif "first_start" in firsts:
        rating = note(a.rating or 6)
        text = f"Première titularisation pour {who}. Note du match : {rating}. {_score(a)}."
    else:
        verdict = {
            "star": "homme du match",
            "good": "solide",
            "fair": "dans le rythme",
            "poor": "discret",
            "bad": "en difficulté",
        }[level]
        text = rng.choice(
            (
                f"{_score(a)}. {who}, {role}{tries} : {verdict}, {note(a.rating or 6)}/10.",
                f"Les notes : {hero.name} {note(a.rating or 6)} ({verdict}){tries}. {_score(a)}.",
            )
        )
    tone = (
        Tone.PRAISE
        if level in ("star", "good")
        else Tone.CRITIC
        if level == "bad"
        else Tone.NEUTRAL
    )
    return text, tone


def _journalist(hero: Hero, a: Appearance, rng: random.Random) -> tuple[str, Tone] | None:
    level = tier(a.rating)
    last = hero.last_name
    best, worst = _moment(a, True), _moment(a, False)
    if level in ("star", "good"):
        lines = [
            f"{last} a {rng.choice(('du culot', 'des cannes', 'le sens du jeu'))}. "
            f"À suivre de très près.",
            f"Ce {last}, quel match. {cap(hero.club)} tient peut-être une pépite.",
            f"On parlera de {last} dans les mois qui viennent, notez-le.",
        ]
        if best:
            lines.append(
                f"Revoyez {MOMENT_WON[best['option']]} de {last} ({best['minute']}e). Tout est dit."
            )
        return rng.choice(lines), Tone.PRAISE
    if level in ("poor", "bad"):
        lines = [
            f"Soirée compliquée pour {last}. L'apprentissage du haut niveau, ça se paie.",
            f"{last} a encore du chemin. Le staff devra être patient.",
        ]
        if worst:
            lost = cap(MOMENT_LOST[worst["option"]])
            lines.append(f"{lost} de {last} ({worst['minute']}e) : il apprendra.")
        return rng.choice(lines), Tone.CRITIC
    if best and rng.random() < 0.6:
        return (
            f"Match correct de {last}, et {MOMENT_WON[best['option']]} ({best['minute']}e).",
            Tone.NEUTRAL,
        )
    return None


def _fan_line(hero: Hero, a: Appearance, rng: random.Random) -> tuple[str, Tone]:
    level = tier(a.rating)
    last = hero.last_name
    won = a.result == "win"
    if a.tries:
        return rng.choice(
            (
                f"ESSAI DE {last.upper()} !!! 🔥🔥",
                f"{last} qui aplatit, le stade qui explose. Magique.",
                f"Je l'avais dit pour {last}. Je l'avais DIT.",
            )
        ), Tone.PRAISE
    if level in ("star", "good"):
        return rng.choice(
            (
                f"{last} titulaire la semaine prochaine, on ne discute pas.",
                f"Quel match du petit {last} 👏",
                f"Maillot floqué {last} commandé. Voilà.",
                f"{last} a mis le feu ce soir{', et on gagne !' if won else '.'}",
            )
        ), Tone.PRAISE
    if level == "fair":
        return rng.choice(
            (
                f"{last} propre, sans plus. Laissez-le grandir.",
                f"Pas mal {last}, il a sa place dans ce groupe.",
                f"{'Belle victoire' if won else 'Dommage'}, et {last} a fait le job.",
            )
        ), Tone.NEUTRAL
    return rng.choice(
        (
            f"{last} complètement à côté ce soir... 😬",
            f"Faut le sortir de là {last}, il n'est pas prêt.",
            f"Dur pour {last}. On reste derrière lui quand même.",
        )
    ), Tone.CRITIC


def _rival_line(hero: Hero, a: Appearance, rng: random.Random) -> tuple[str, Tone]:
    last = hero.last_name
    if tier(a.rating) in ("star", "good") or a.tries:
        return rng.choice(
            (
                f"Ce {last} nous a fait mal... on le veut chez nous.",
                f"Respect à {last}, il nous a pris de vitesse.",
            )
        ), Tone.PRAISE
    return rng.choice(
        (
            f"C'est ça la pépite {of(hero.club)} ? 😂",
            f"{last}, on l'a pas vu. Merci pour le cadeau.",
        )
    ), Tone.CRITIC


@dataclass(frozen=True)
class Move:
    """Un mouvement du joueur : un transfert ou un prêt (`kind`), et quand."""

    date: datetime.date
    kind: str  # transfer, loan ou extend
    origin: str
    club: str


def _moves(hero: Hero, moves: list[Move], fame: int) -> list[Post]:
    posts = []
    for move in moves:
        rng = random.Random(f"social:move:{move.date}:{hero.name}")
        if move.kind == "extend":
            text = f"{hero.name} prolonge à {move.club}. Le club croit en lui."
        elif move.kind == "loan":
            text = f"Officiel : {hero.name} prêté par {move.origin} à {move.club} pour une saison."
        else:
            text = f"Officiel : {hero.name} quitte {move.origin} et s'engage avec {move.club}."
        posts.append(
            Post(move.date, _clock(10, rng), rng.choice(MEDIA), text, Tone.NEUTRAL,
                 *_engagement(fame, 1.6, rng))
        )  # fmt: skip
        if move.kind != "extend":
            posts.append(
                Post(move.date, _clock(13, rng), _fan(move.club, rng),
                     rng.choice((f"Bienvenue chez nous {hero.first_name} ! 🙌",
                                 f"Grosse recrue, {hero.last_name}. Hâte de le voir avec nous.")),
                     Tone.PRAISE, *_engagement(fame, 0.5, rng))
            )  # fmt: skip
    return posts


def _rumours(hero: Hero, day: datetime.date, clubs: list[str], fame: int) -> list[Post]:
    """Les clubs qui le veulent, à la fin de la saison : ce que la presse en sait."""
    posts = []
    for club in clubs:
        rng = random.Random(f"social:rumour:{day}:{club}:{hero.name}")
        author = rng.choice((*MEDIA, *JOURNALISTS))
        text = rng.choice(
            (
                f"Selon nos informations, {club} s'intéresse de près à {hero.name}.",
                f"Mercato : {club} a pris contact avec l'entourage de {hero.last_name}.",
                f"{hero.last_name} vers {club} ? Les discussions sont avancées.",
            )
        )
        posts.append(
            Post(day, _clock(rng.choice((9, 10, 11)), rng), author, text, Tone.NEUTRAL,
                 *_engagement(fame, 1.3, rng))
        )  # fmt: skip
    return posts


@dataclass(frozen=True)
class CallUp:
    """Sa sélection sur une liste : le jour de l'annonce, sa sélection, la fenêtre."""

    date: datetime.date
    nation: str
    window: str
    first: bool  # sa première liste


# Une sélection marque : abonnés en plus à chaque liste, et par match international.
FOLLOWERS_PER_CALL_UP = 400
FOLLOWERS_PER_CAP = 250


def _call_ups(hero: Hero, call_ups: list[CallUp], fame: int) -> list[Post]:
    posts = []
    for call_up in call_ups:
        rng = random.Random(f"social:callup:{call_up.date}:{hero.name}")
        if call_up.first:
            text = f"🚨 Première convocation pour {hero.name} ! {call_up.nation}, {call_up.window}."
        else:
            text = f"{call_up.nation} · {call_up.window} : {hero.name} fait partie de la liste."
        posts.append(
            Post(call_up.date, _clock(12, rng), rng.choice(MEDIA), text, Tone.PRAISE,
                 *_engagement(fame, 2.5 if call_up.first else 1.5, rng))
        )  # fmt: skip
        posts.append(
            Post(call_up.date, _clock(13, rng), _fan(hero.club, rng),
                 rng.choice((f"Un des nôtres avec {call_up.nation} ! Fierté 🙌",
                             f"{hero.last_name} en sélection, on l'avait vu venir.")),
                 Tone.PRAISE, *_engagement(fame, 0.8, rng))
        )  # fmt: skip
    return posts


def _test_posts(hero: Hero, a: Appearance, nation: str, fame: int) -> list[Post]:
    """Un match international : la presse, et les supporters de la sélection."""
    rng = random.Random(f"social:test:{a.match_id}:{hero.name}")
    level = tier(a.rating)
    tries = f", {a.tries} essai{'s' if a.tries > 1 else ''}" if a.tries else ""
    verdict = {"star": "énorme", "good": "convaincant", "fair": "solide",
               "poor": "discret", "bad": "en difficulté"}[level]  # fmt: skip
    score = f"{nation} {a.score_for}-{a.score_against} {a.opponent}"
    posts = [
        Post(a.date, _clock(22, rng), rng.choice(MEDIA),
             f"{score}. {hero.name} {verdict} sous le maillot de la sélection "
             f"({note(a.rating or 6)}/10{tries}).",
             Tone.PRAISE if level in ("star", "good") else Tone.NEUTRAL,
             *_engagement(fame, 2.0, rng), a.match_id)
    ]  # fmt: skip
    line = (
        f"{hero.last_name} avec {nation}, quel bonheur de le voir à ce niveau 👏"
        if level in ("star", "good", "fair")
        else f"Pas son jour à {hero.last_name} avec {nation}. Il reviendra plus fort."
    )
    posts.append(
        Post(a.date, _clock(23, rng), _fan(hero.club, rng), line,
             Tone.PRAISE if level in ("star", "good", "fair") else Tone.CRITIC,
             *_engagement(fame, 0.9, rng), a.match_id)
    )  # fmt: skip
    return posts


def feed(
    hero: Hero,
    appearances: list[Appearance],
    signed_on: datetime.date | None,
    moves: list[Move] = (),
    rumours: list[tuple[datetime.date, list[str]]] = (),
    call_ups: list[CallUp] = (),
    tests: list[tuple[Appearance, str]] = (),
) -> Feed:
    """Le fil du joueur, du plus récent au plus ancien, et ses abonnés : ses matchs, ses
    mouvements (`moves`), les clubs qui le veulent en fin de saison (`rumours`), ses
    listes en sélection (`call_ups`) et ses matchs internationaux (`tests` : le match
    et le nom de sa sélection)."""
    posts: list[Post] = []
    followers = FOLLOWERS_START
    gain = 0
    if signed_on is not None:
        rng = random.Random(f"social:signing:{hero.name}")
        media = rng.choice(MEDIA)
        likes, reposts = _engagement(followers, 1.0, rng)
        posts.append(
            Post(
                signed_on,
                _clock(11, rng),
                media,
                f"Officiel : {hero.club} engage {hero.name}, 18 ans, "
                f"{POSITIONS[hero.position]}. Un pari sur l'avenir.",
                Tone.NEUTRAL,
                likes,
                reposts,
            )
        )
        fan = _fan(hero.club, rng)
        posts.append(
            Post(
                signed_on,
                _clock(12, rng),
                fan,
                rng.choice(
                    (
                        f"Qui l'a déjà vu jouer, ce {hero.last_name} ? 👀",
                        f"Bienvenue {hero.first_name} ! Mouille le maillot et on t'adoptera.",
                    )
                ),
                Tone.NEUTRAL,
                *_engagement(followers, 0.3, rng),
            )
        )

    played_before = started_before = scored_before = False
    for a in sorted(appearances, key=lambda a: (a.date, a.match_id)):
        rng = random.Random(f"social:{a.match_id}:{hero.name}")
        if not a.played:
            if rng.random() < ABSENT_REACTION:
                fan = _fan(a.club, rng)
                text = rng.choice(
                    (
                        f"Toujours pas de {hero.last_name} sur le terrain... on veut le voir !",
                        f"{a.score_for}-{a.score_against}. Et {hero.last_name}, il joue quand ?",
                    )
                )
                posts.append(
                    Post(
                        a.date,
                        _clock(23, rng),
                        fan,
                        text,
                        Tone.NEUTRAL,
                        *_engagement(followers, 0.2, rng),
                        a.match_id,
                    )
                )
            continue

        firsts = []
        if not played_before:
            firsts.append("debut")
        if a.started and not started_before:
            firsts.append("first_start")
        if a.tries and not scored_before:
            firsts.append("first_try")
        played_before = True
        started_before = started_before or a.started
        scored_before = scored_before or a.tries > 0

        gain = (
            FOLLOWERS_PER_MATCH
            + round(FOLLOWERS_PER_RATING_POINT * max(0.0, (a.rating or 6.0) - 6.0))
            + FOLLOWERS_PER_TRY * a.tries
            + (FOLLOWERS_PER_START if a.started else 0)
        )
        followers += gain
        buzz = {"star": 2.2, "good": 1.5, "fair": 1.0, "poor": 0.9, "bad": 1.1}[tier(a.rating)]
        buzz *= 1.4 if firsts else 1.0

        text, tone = _media(hero, a, firsts, rng)
        posts.append(
            Post(
                a.date,
                _clock(22, rng),
                rng.choice(MEDIA),
                text,
                tone,
                *_engagement(followers, buzz, rng),
                a.match_id,
            )
        )
        opinion = _journalist(hero, a, rng)
        if opinion is not None:
            posts.append(
                Post(
                    a.date,
                    _clock(23, rng),
                    rng.choice(JOURNALISTS),
                    opinion[0],
                    opinion[1],
                    *_engagement(followers, buzz * 0.8, rng),
                    a.match_id,
                )
            )
        fans = 1 + (tier(a.rating) in ("star", "bad")) + (a.tries > 0)
        for _ in range(fans):
            line, fan_tone = _fan_line(hero, a, rng)
            posts.append(
                Post(
                    a.date,
                    _clock(rng.choice((21, 22, 23)), rng),
                    _fan(a.club, rng),
                    line,
                    fan_tone,
                    *_engagement(followers, buzz * 0.5, rng),
                    a.match_id,
                )
            )
        if tier(a.rating) in ("star", "bad") or a.tries:
            line, rival_tone = _rival_line(hero, a, rng)
            posts.append(
                Post(
                    a.date,
                    _clock(23, rng),
                    _fan(a.opponent, rng, Voice.RIVAL),
                    line,
                    rival_tone,
                    *_engagement(followers, buzz * 0.4, rng),
                    a.match_id,
                )
            )

    followers += FOLLOWERS_PER_CALL_UP * len(call_ups) + FOLLOWERS_PER_CAP * len(tests)
    posts += _call_ups(hero, list(call_ups), followers)
    for test, nation in tests:
        posts += _test_posts(hero, test, nation, followers)
    posts += _moves(hero, list(moves), followers)
    for day, clubs in rumours:
        posts += _rumours(hero, day, clubs, followers)

    # Sans doublon de texte d'un match à l'autre : le plus ancien reste.
    seen: set[str] = set()
    unique = []
    for post in sorted(posts, key=lambda p: (p.date, p.time)):
        if post.text not in seen:
            seen.add(post.text)
            unique.append(post)
    unique.reverse()
    return Feed(followers=followers, gain=gain, posts=unique)
