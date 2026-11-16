"""Dessine les blasons des clubs et des sélections, et les inscrit au manifeste.

Tous les blasons du jeu sont inventés : aucun n'est celui d'un vrai club ou d'une
fédération. Un club reçoit un écu à ses couleurs (forme et partition tirées de son nom,
toujours les mêmes) et ses initiales ; une sélection, un médaillon rond au code de son
pays. Les couleurs viennent du manifeste (frontend/src/clubLogos.json), qui reste leur
source : on y change une couleur, ou on y ajoute une équipe, puis on relance.
Les SVG vont dans frontend/public/clubs/. Les équipes de légende ont leur propre blason
(scripts/draw_legend_crests.py).

Usage (depuis le dossier backend/) :
    uv run python -m scripts.draw_crests
"""

import hashlib
import json
import re
import unicodedata
from pathlib import Path

from data.leagues import LEAGUES
from data.nations import NATIONS

FRONTEND = Path(__file__).resolve().parents[2] / "frontend"
LOGO_DIR = FRONTEND / "public" / "clubs"
MANIFEST = FRONTEND / "src" / "clubLogos.json"

# Initiales d'un club quand celles de son nom ne conviennent pas.
CODES = {
    "Goélands de La Rochelle": "GLR",
    "Cape Town Tempest": "CTT",
}
# Mots du nom qui ne donnent pas d'initiale.
SMALL_WORDS = {"de", "du", "des", "d", "la", "le", "les"}

SHIELDS = (
    "M50 4 L93 15 V52 C93 81 74 100 50 112 C26 100 7 81 7 52 V15 Z",
    "M8 8 H92 V58 C92 86 72 102 50 112 C28 102 8 86 8 58 Z",
    "M50 4 L92 24 V84 L50 112 L8 84 V24 Z",
    "M8 6 Q50 20 92 6 V60 C92 86 72 102 50 112 C28 102 8 86 8 60 Z",
)
ROUND = "M50 8 A50 50 0 1 1 49.99 8 Z"
# Partitions de l'écu, dessinées dans la seconde couleur (elles sont rognées à sa forme).
PATTERNS = (
    '<rect x="0" y="0" width="100" height="36" fill="{c}"/>',
    '<rect x="50" y="0" width="50" height="116" fill="{c}"/>',
    '<polygon points="0,0 34,0 100,84 100,116 66,116 0,32" fill="{c}"/>',
    '<polygon points="0,96 50,58 100,96 100,116 50,80 0,116" fill="{c}"/>'
    '<polygon points="0,36 50,0 100,36 100,16 50,-20 0,16" fill="{c}"/>',
    '<rect x="0" y="22" width="100" height="14" fill="{c}"/>'
    '<rect x="0" y="84" width="100" height="14" fill="{c}"/>',
    '<rect x="20" y="0" width="12" height="116" fill="{c}"/>'
    '<rect x="68" y="0" width="12" height="116" fill="{c}"/>',
    '<rect x="0" y="0" width="50" height="58" fill="{c}"/>'
    '<rect x="50" y="58" width="50" height="58" fill="{c}"/>',
)


def slug(name: str) -> str:
    """'Goélands de La Rochelle' -> 'goelands-de-la-rochelle'."""
    ascii_name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", ascii_name.lower()).strip("-")


def dump(manifest: dict) -> str:
    """La table telle qu'elle est rangée dans le dépôt : triée par nom, un champ par
    ligne dans le même ordre, les deux couleurs sur une seule ligne."""
    ordered = {
        name: {key: entry[key] for key in ("logo", "colors", "light") if key in entry}
        for name, entry in sorted(manifest.items())
    }
    text = json.dumps(ordered, ensure_ascii=False, indent=2)
    inline = re.sub(
        r"\[\s+(.*?)\s+\]",
        lambda array: "[" + re.sub(r",\s+", ", ", array.group(1)) + "]",
        text,
        flags=re.DOTALL,
    )
    return inline + "\n"


def initials(name: str) -> str:
    """'Capitouls de Toulouse' -> 'CT', 'Lynx d'Oyonnax' -> 'LO'."""
    if name in CODES:
        return CODES[name]
    words = [w for w in re.split(r"[\s'’-]+", name) if w and w.lower() not in SMALL_WORDS]
    plain = unicodedata.normalize("NFKD", "".join(w[0] for w in words))
    return plain.encode("ascii", "ignore").decode().upper()[:3]


def _luminance(color: str) -> float:
    channels = [int(color[i : i + 2], 16) / 255 for i in (1, 3, 5)]
    linear = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in channels]
    return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]


def contrast(a: str, b: str) -> float:
    high, low = sorted((_luminance(a), _luminance(b)), reverse=True)
    return (high + 0.05) / (low + 0.05)


def _ink(fill: str, other: str) -> str:
    """La couleur des lettres sur ce fond : blanc, ou sur un fond clair l'autre couleur de
    l'équipe si elle s'y lit bien, noir sinon."""
    if contrast(fill, "#FFFFFF") >= 3:
        return "#FFFFFF"
    return other if contrast(fill, other) >= 4.5 else "#111111"


def _edge(primary: str, secondary: str) -> str:
    """Le liseré : une couleur de l'équipe qui se voit sur fond clair comme sur fond sombre."""
    for color in (secondary, primary):
        if 0.03 <= _luminance(color) <= 0.6:
            return color
    return "#8A8F98"


def _text(code: str, y: float, size: float, ink: str) -> str:
    return (
        f'<text x="50" y="{y}" text-anchor="middle" font-family="Georgia, '
        f'\'Times New Roman\', serif" font-weight="700" font-size="{size}" '
        f'fill="{ink}">{code}</text>'
    )


def club_crest(name: str, primary: str, secondary: str) -> str:
    """L'écu d'un club : forme et partition viennent de l'empreinte de son nom."""
    digest = hashlib.sha256(name.encode()).digest()
    shield = SHIELDS[digest[0] % len(SHIELDS)]
    pattern = PATTERNS[digest[1] % len(PATTERNS)].format(c=secondary)
    code = initials(name)
    edge = _edge(primary, secondary)
    size = 22 if len(code) <= 2 else 16.5
    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 116" \
width="200" height="232">
<clipPath id="s"><path d="{shield}"/></clipPath>
<path d="{shield}" fill="{primary}"/>
<g clip-path="url(#s)">{pattern}</g>
<path d="{shield}" fill="none" stroke="{edge}" stroke-width="5" stroke-linejoin="round"/>
<circle cx="50" cy="57" r="24" fill="{primary}" stroke="{edge}" stroke-width="3"/>
{_text(code, 57 + size * 0.35, size, _ink(primary, secondary))}
</svg>
"""


def nation_crest(code: str, primary: str, secondary: str) -> str:
    """Le médaillon d'une sélection : rond, cerclé, au code du pays."""
    edge = _edge(primary, secondary)
    ink = _ink(primary, secondary)
    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 116" \
width="200" height="232">
<path d="{ROUND}" fill="{primary}" stroke="{edge}" stroke-width="5"/>
<circle cx="50" cy="58" r="40" fill="none" stroke="{ink}" stroke-width="1.6"/>
{_text(code, 66, 23, ink)}
<rect x="36" y="74" width="28" height="3" rx="1.5" fill="{ink}"/>
</svg>
"""


def main() -> None:
    LOGO_DIR.mkdir(parents=True, exist_ok=True)
    manifest = json.loads(MANIFEST.read_text())
    teams = [(club.name, None) for league in LEAGUES for club in league.clubs]
    teams += [(nation.name, nation.code) for nation in NATIONS]
    for name, code in teams:
        colors = manifest.get(name, {}).get("colors")
        if not colors:
            print(f"{name} : pas de couleurs dans le manifeste, blason à initiales")
            continue
        primary, secondary = colors[0], colors[-1]
        svg = nation_crest(code, primary, secondary) if code else club_crest(name, *colors[:2])
        (LOGO_DIR / f"{slug(name)}.svg").write_text(svg)
        manifest[name] = {"logo": f"/clubs/{slug(name)}.svg", "colors": colors, "light": False}
    MANIFEST.write_text(dump(manifest))
    print(f"{len(teams)} blasons dessinés")


if __name__ == "__main__":
    main()
