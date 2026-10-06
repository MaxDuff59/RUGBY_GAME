# ruff: noqa: E501  (la bibliothèque, une marque par ligne)
"""Sponsors du maillot : une bibliothèque de marques inventées, chacune avec son budget
et son image auprès du public.

Le club place jusqu'à MAX_DEALS logos sur le maillot (poitrine, dos, manche, ventre) ;
chaque sponsor paie à chaque match une part de son budget qui dépend de l'emplacement.
Les supporters, eux, jugent le maillot : une marque mal vue (paris, pétrole, crypto…)
pèse sur leur ferveur, et trois logos font un maillot « sapin de Noël ». La ferveur
règle l'affluence (engine/economy.py) : un sponsor qui paie bien peut coûter des
spectateurs. Les logos sont dessinés par l'interface (frontend/src/sponsors.js) à partir
de `logo`.
"""

from dataclasses import dataclass
from enum import StrEnum


class Placement(StrEnum):
    CHEST = "chest"  # poitrine : le sponsor principal
    BACK = "back"  # haut du dos, au-dessus du numéro
    SLEEVE = "sleeve"  # manche gauche
    BELLY = "belly"  # bas du devant


PLACEMENT_LABELS = {
    Placement.CHEST: "Poitrine",
    Placement.BACK: "Dos",
    Placement.SLEEVE: "Manche",
    Placement.BELLY: "Ventre",
}

# Part du budget du sponsor versée à chaque match, selon la visibilité de l'emplacement.
PLACEMENT_SHARE = {
    Placement.CHEST: 1.0,
    Placement.BACK: 0.6,
    Placement.BELLY: 0.5,
    Placement.SLEEVE: 0.4,
}

MAX_DEALS = 3

# Effet sur la ferveur des supporters (engine/supporters.py, note sur 20) de l'image
# d'un sponsor (1 : mal vu, 5 : adoré), et d'un maillot couvert de logos.
IMAGE_MOOD = {1: -1.0, 2: -0.5, 3: 0.0, 4: 0.15, 5: 0.3}
IMAGE_LABELS = {1: "Mal vu", 2: "Discuté", 3: "Neutre", 4: "Apprécié", 5: "Adoré"}
CROWDED_DEALS = 3
CROWDED_MOOD = -0.6


@dataclass(frozen=True)
class Sponsor:
    id: str
    name: str
    sector: str
    budget: int  # par match, sur la poitrine
    image: int  # 1 (mal vu) à 5 (adoré)
    logo: dict  # forme, couleurs et pictogramme (frontend/src/sponsors.js)


def _logo(shape: str, bg: str, fg: str, glyph: str) -> dict:
    return {"shape": shape, "bg": bg, "fg": fg, "glyph": glyph}


SPONSORS = {
    sponsor.id: sponsor
    for sponsor in (
        Sponsor("occitane", "Banque Occitane", "Banque", 35_000, 3, _logo("square", "#0B1F44", "#F2C230", "coin")),
        Sponsor("volt", "Volt Énergie", "Électricité", 30_000, 3, _logo("disc", "#F2C230", "#16181B", "bolt")),
        Sponsor("pic", "Brasserie du Pic", "Bière", 28_000, 4, _logo("shield", "#8A4B1F", "#F7E7C6", "hop")),
        Sponsor("fastbet", "FastBet", "Paris en ligne", 60_000, 1, _logo("pill", "#1F8A3C", "#FFFFFF", "dice")),
        Sponsor("petrosud", "PétroSud", "Pétrole", 55_000, 1, _logo("hex", "#16181B", "#E35205", "flame")),
        Sponsor("cryptobulle", "CryptoBulle", "Cryptomonnaie", 65_000, 1, _logo("diamond", "#5B2A86", "#FFFFFF", "chip")),
        Sponsor("royal", "Burger Royal", "Restauration rapide", 32_000, 2, _logo("disc", "#C8102E", "#F2C230", "crown")),
        Sponsor("vignes", "Mutuelle des Vignes", "Assurance", 25_000, 4, _logo("shield", "#1F5C3A", "#FFFFFF", "shield")),
        Sponsor("castel", "Cassoulet Castel", "Alimentation", 18_000, 4, _logo("disc", "#7A1F2B", "#F7E7C6", "pot")),
        Sponsor("aeromidi", "Aéro Midi", "Aéronautique", 40_000, 3, _logo("pill", "#0B3D91", "#FFFFFF", "plane")),
        Sponsor("lauragais", "Ferme du Lauragais", "Agriculture bio", 8_000, 5, _logo("disc", "#4F7A28", "#F7E7C6", "wheat")),
        Sponsor("garonne", "Vélo Garonne", "Cycles", 10_000, 5, _logo("disc", "#0E6E73", "#FFFFFF", "wheel")),
        Sponsor("pyrenees", "Eau des Pyrénées", "Eau minérale", 20_000, 4, _logo("hex", "#6CACE4", "#FFFFFF", "drop")),
        Sponsor("zenith", "Zénith Télécom", "Télécoms", 38_000, 3, _logo("square", "#B5176B", "#FFFFFF", "wave")),
        Sponsor("nova", "Pharma Nova", "Laboratoire", 36_000, 2, _logo("square", "#FFFFFF", "#0B3D91", "cross")),
        Sponsor("martin", "Garage Martin", "Automobile", 9_000, 4, _logo("pill", "#4A4F55", "#FFFFFF", "wrench")),
    )
}  # fmt: skip


@dataclass(frozen=True)
class Deal:
    """Un sponsor à un emplacement du maillot."""

    sponsor: str  # identifiant dans SPONSORS
    placement: Placement

    def revenue(self) -> int:
        """Ce que le sponsor verse à chaque match."""
        return round(SPONSORS[self.sponsor].budget * PLACEMENT_SHARE[self.placement])


def deals_from(raw: list[dict]) -> list[Deal]:
    return [Deal(item["sponsor"], Placement(item["placement"])) for item in raw or []]


def deal_refusal(deals: list[Deal]) -> str | None:
    """Pourquoi ces contrats ne sont pas acceptables (None : ils le sont)."""
    if len(deals) > MAX_DEALS:
        return f"{MAX_DEALS} sponsors au maximum sur le maillot"
    if len({d.sponsor for d in deals}) < len(deals):
        return "Un sponsor n'apparaît qu'une fois sur le maillot"
    if len({d.placement for d in deals}) < len(deals):
        return "Un seul sponsor par emplacement"
    unknown = next((d.sponsor for d in deals if d.sponsor not in SPONSORS), None)
    if unknown is not None:
        return f"Sponsor inconnu : {unknown}"
    return None


def jersey_revenue(deals: list[Deal]) -> int:
    """Ce que les sponsors du maillot versent à chaque match, en tout."""
    return sum(deal.revenue() for deal in deals)


def sponsor_mood(deals: list[Deal]) -> float:
    """Ce que les supporters pensent du maillot, en points de ferveur : tant que les
    contrats sont en place, la ferveur est décalée d'autant."""
    mood = sum(IMAGE_MOOD[SPONSORS[d.sponsor].image] for d in deals)
    if len(deals) >= CROWDED_DEALS:
        mood += CROWDED_MOOD
    return round(mood, 2)
