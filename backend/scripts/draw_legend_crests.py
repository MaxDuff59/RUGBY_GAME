"""Dessine les blasons des équipes de légende (data/legends.py) et les inscrit au manifeste.

Un blason inventé pour chaque équipe, pas celui de sa fédération ou de son club : un écu
aux couleurs du pays ou du club, liseré, étoiles et laurier dorés, le code du pays ou les
initiales du club, et un bandeau « LÉGENDES ».
Les SVG vont dans frontend/public/clubs/legendes/, le nom → blason et couleurs dans
frontend/src/clubLogos.json, comme les autres blasons (scripts/fetch_club_logos.py).
Une nouvelle équipe de légende reçoit ses couleurs dans `COLORS` (un club dans
`CLUB_COLORS`), puis on relance.

Usage (depuis le dossier backend/) :
    uv run python -m scripts.draw_legend_crests
"""

import json
import math

from data.legends import LEGENDS, SUFFIX
from scripts.fetch_club_logos import LOGO_DIR, MANIFEST, dump, slug

GOLD = "#D9A93A"
# Pays -> (fond, code du pays[, ornements]) ; les ornements sont dorés, sauf pour
# l'Australie, déjà en or, ornée de vert.
COLORS = {
    "FRA": ("#0B2A6F", "#FFFFFF"),
    "NZL": ("#111111", "#FFFFFF"),
    "RSA": ("#0B5A3C", "#F2C230"),
    "ENG": ("#C8102E", "#FFFFFF"),
    "AUS": ("#F0B323", "#0B5A3C", "#0B5A3C"),
    "IRE": ("#0E7C4A", "#FFFFFF"),
    "WAL": ("#B5121B", "#FFFFFF"),
}
# Club -> (fond, initiales[, ornements]), même règle.
CLUB_COLORS = {
    "Racing 92": ("#0A1F44", "#8FD0F2"),
    "Stade Toulousain": ("#111111", "#E30613"),
    "RC Toulon": ("#C8102E", "#FFFFFF", "#111111"),
    "ASM Clermont Auvergne": ("#002B5C", "#FFD100", "#FFD100"),
    "Stade Français Paris": ("#E4007C", "#FFFFFF", "#0A1F5C"),
    "Leinster Rugby": ("#0055A4", "#FFFFFF"),
    "Munster Rugby": ("#C8102E", "#FFFFFF"),
    "Saracens": ("#111111", "#FFFFFF", "#E4002B"),
    "Leicester Tigers": ("#00553B", "#FFFFFF"),
    "Crusaders": ("#D00F16", "#FFFFFF", "#111111"),
    "Blues": ("#002B7F", "#6CACE4"),
}
SHIELD = "M50 4 L93 15 V52 C93 81 74 100 50 112 C26 100 7 81 7 52 V15 Z"
FOLDER = LOGO_DIR / "legendes"


def _star(cx: float, cy: float, r: float, color: str) -> str:
    points = []
    for i in range(10):
        angle = -math.pi / 2 + i * math.pi / 5
        radius = r if i % 2 == 0 else r * 0.45
        points.append(f"{cx + radius * math.cos(angle):.2f},{cy + radius * math.sin(angle):.2f}")
    return f'<polygon points="{" ".join(points)}" fill="{color}"/>'


def _laurel(side: int, color: str) -> str:
    """Une branche de laurier, à gauche (-1) ou à droite (1) du code, de bas en haut."""
    cx, cy, r = 50, 58, 35
    leaves = []
    for i in range(7):
        angle = math.pi / 2 - side * (0.62 + i * 0.105) * math.pi / 2 * 1.05
        x, y = cx + r * math.cos(angle), cy + r * math.sin(angle)
        tilt = math.degrees(angle) + 90 + side * 35
        leaves.append(
            f'<ellipse cx="{x:.2f}" cy="{y:.2f}" rx="4.6" ry="1.9" '
            f'transform="rotate({tilt:.1f} {x:.2f} {y:.2f})" fill="{color}"/>'
        )
    return "".join(leaves)


def crest(code: str, fill: str, ink: str, gold: str = GOLD) -> str:
    """Le SVG du blason ; deux initiales gardent leur largeur, trois remplissent l'écu."""
    width = ' textLength="42" lengthAdjust="spacingAndGlyphs"' if len(code) > 2 else ""
    stars = _star(34, 25, 5.5, gold) + _star(50, 21, 7, gold) + _star(66, 25, 5.5, gold)
    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 116" \
width="200" height="232">
<path d="{SHIELD}" fill="{fill}" stroke="{gold}" stroke-width="6" stroke-linejoin="round"/>
{stars}
{_laurel(-1, gold)}{_laurel(1, gold)}
<text x="50" y="65" text-anchor="middle" font-family="Georgia, 'Times New Roman', serif" \
font-weight="700" font-size="21"{width} fill="{ink}">{code}</text>
<rect x="21" y="80" width="58" height="12" rx="2" fill="{gold}"/>
<text x="50" y="89" text-anchor="middle" font-family="Helvetica, Arial, sans-serif" \
font-weight="700" font-size="7.6" letter-spacing="1.2" fill="{fill}">LÉGENDES</text>
</svg>
"""


def main() -> None:
    FOLDER.mkdir(parents=True, exist_ok=True)
    manifest = json.loads(MANIFEST.read_text())
    for team in LEGENDS:
        fill, ink, *ornament = CLUB_COLORS[team.club] if team.club else COLORS[team.nation]
        gold = ornament[0] if ornament else GOLD
        name = slug(team.name.removesuffix(SUFFIX))
        (FOLDER / f"{name}.svg").write_text(crest(team.code or team.nation, fill, ink, gold))
        manifest[team.name] = {
            "logo": f"/clubs/legendes/{name}.svg",
            # La seconde couleur : celle du code sur fond blanc, l'or sinon.
            "colors": [fill, ink if ink != "#FFFFFF" else gold],
            "light": False,
        }
        print(f"{team.name} : {name}.svg")
    MANIFEST.write_text(dump(manifest))


if __name__ == "__main__":
    main()
