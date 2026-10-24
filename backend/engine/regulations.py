"""Les règlements des championnats : plafond salarial et JIFF.

Plafond salarial (Top 14, Pro D2, Premiership) : la masse salariale des pros d'un
club ne peut pas le dépasser. Le manager ne peut pas signer, prolonger ni promouvoir
un joueur si sa masse salariale passait au-dessus. L'URC et le Super Rugby n'en ont pas.
Les clubs gérés par le jeu le respectent aussi : ils ne signent (agent libre, joker,
prêt, pré-contrat) que si le salaire y tient, et à l'intersaison un club au-dessus
(un promu, un relégué, un monde tiré trop riche) laisse partir ses fins de contrat,
puis renégocie les salaires de tous ses pros (`fit_under_cap`).

JIFF (« joueurs issus des filières de formation », Top 14 et Pro D2) : une feuille
de match (les 23) compte au moins `JIFF_MIN` JIFF. Le jeu tient pour JIFF un joueur
de nationalité française : formé en France, le plus souvent. Quand la feuille n'en
compte pas assez, le staff fait monter sur le banc, puis dans le XV, les meilleurs
JIFF disponibles à la place des étrangers les moins indispensables.
"""

from collections.abc import Callable

from engine.economy import WAGE_MIN
from models import Club, Player, Position

SALARY_CAP = {"top14": 7_800_000, "prod2": 2_300_000, "premiership": 5_000_000}
JIFF_MIN = {"top14": 14, "prod2": 14}
JIFF_NATION = "FRA"


def salary_cap(league: str) -> int | None:
    return SALARY_CAP.get(league)


def payroll(club: Club) -> int:
    """La masse salariale des pros (prêtés compris), par saison."""
    return sum(p.wage for p in club.players)


def cap_room(club: Club) -> int | None:
    """Ce qu'il reste sous le plafond (négatif s'il est déjà dépassé), None sans plafond."""
    cap = salary_cap(club.league)
    return None if cap is None else cap - payroll(club)


def cap_breach(club: Club, extra: int) -> tuple[int, int] | None:
    """(masse salariale après, plafond) si `extra` euros de salaires en plus feraient
    dépasser le plafond du championnat du club ; None sinon."""
    cap = salary_cap(club.league)
    after = payroll(club) + extra
    return (after, cap) if cap is not None and extra > 0 and after > cap else None


def committed_payroll(club: Club, season_year: int) -> int:
    """La masse salariale déjà engagée pour la saison qui suit `season_year` : les pros
    sous contrat au-delà (les prêtés rentrent chez eux)."""
    return sum(
        p.wage for p in club.players if p.loaned_from is None and p.contract_until > season_year
    )


def fits_next_season(club: Club, season_year: int, wage: int, incoming: int = 0) -> bool:
    """Un pré-contrat à `wage` tient-il sous le plafond la saison suivante, avec la masse
    déjà engagée et les salaires des joueurs qui doivent arriver (`incoming`) ?"""
    cap = salary_cap(club.league)
    return cap is None or committed_payroll(club, season_year) + incoming + wage <= cap


# Un club au-dessus du plafond revient à cette part du plafond : de quoi compléter son effectif.
CAP_MARGIN = 0.97


def fit_under_cap(club: Club) -> list[Player]:
    """Un club au-dessus du plafond renégocie : le salaire de chacun de ses pros baisse
    d'autant, pour revenir sous le plafond avec un peu de marge. Renvoie les joueurs
    dont le salaire a changé (aucun si le club était sous le plafond)."""
    cap = salary_cap(club.league)
    total = payroll(club)
    if cap is None or total <= cap:
        return []
    ratio = cap * CAP_MARGIN / total
    for player in club.players:
        player.wage = max(WAGE_MIN, int(player.wage * ratio / 1_000) * 1_000)
    return list(club.players)


def is_jiff(player: Player) -> bool:
    return player.nationality == JIFF_NATION


def jiff_min(club: Club) -> int:
    """Le minimum de JIFF sur la feuille de match d'un club (0 hors Top 14 et Pro D2, et
    pour une équipe sans staff : sélection, espoirs)."""
    if not club.staff:
        return 0
    return JIFF_MIN.get(club.league, 0)


def comply(
    club: Club,
    lineup: list[Player],
    bench: list[Player],
    available: list[Player],
    slots: list[Position],
    rating: Callable[[Position, Player], float],
) -> tuple[list[Player], list[Player]]:
    """La feuille de match (XV puis banc) rendue conforme au minimum de JIFF, si
    l'effectif le permet : un étranger du banc, puis du XV, cède sa place au meilleur
    JIFF disponible. `slots` : le poste de chaque place du XV ; au banc, chacun garde
    le sien. `rating(poste, joueur)` : la note d'un joueur à une place."""
    needed = jiff_min(club)
    lineup, bench = list(lineup), list(bench)
    sheet = {p.id for p in lineup + bench}
    reserves = [p for p in available if p.id not in sheet and is_jiff(p)]
    groups = ((bench, [p.position for p in bench]), (lineup, list(slots)))
    for group, places in groups:
        while sum(is_jiff(p) for p in lineup + bench) < needed and reserves:
            foreigners = [i for i, p in enumerate(group) if not is_jiff(p)]
            if not foreigners:
                break
            # L'étranger le moins utile à sa place, remplacé par le meilleur JIFF à cette place.
            index = min(foreigners, key=lambda i: rating(places[i], group[i]))
            incoming = max(reserves, key=lambda p: rating(places[index], p))
            reserves.remove(incoming)
            group[index] = incoming
    return lineup, bench
