"""Télécharge les blasons et les couleurs des vrais clubs depuis TheSportsDB.

Les images vont dans frontend/public/clubs/ ; la table nom du club -> blason et
couleurs (primaire, secondaire) dans frontend/src/clubLogos.json, que l'interface
lit pour les blasons et pour teinter l'accent aux couleurs du club choisi.
Un club introuvable (ou inventé) garde l'écusson à initiales, et ses couleurs
sont tirées de son nom (frontend/src/clubs.js). `COLORS` corrige les couleurs
absentes ou fausses chez TheSportsDB. Un blason presque blanc (invisible sur le
fond clair) est marqué `light` : l'interface le pose sur une pastille du club.

Usage (depuis le dossier backend/) :
    uv run python -m scripts.fetch_club_logos
    uv run python -m scripts.fetch_club_logos --force   # retélécharge tout
"""

import argparse
import json
import re
import struct
import time
import unicodedata
import urllib.parse
import urllib.request
import zlib
from pathlib import Path

from data.leagues import LEAGUES

# Championnats de rugby à XIII, à écarter (des homonymes y jouent).
THIRTEEN = re.compile(r"rugby league|super league|\bnrl\b")
API = "https://www.thesportsdb.com/api/v1/json/3/searchteams.php?t="
FRONTEND = Path(__file__).resolve().parents[2] / "frontend"
LOGO_DIR = FRONTEND / "public" / "clubs"
MANIFEST = FRONTEND / "src" / "clubLogos.json"

# Nom recherché quand celui du jeu ne donne rien chez TheSportsDB.
ALIASES = {
    "Union Bordeaux-Bègles": ["Bordeaux Begles", "Union Bordeaux Begles"],
    "RC Toulon": ["Toulon", "RC Toulonnais"],
    "Stade Rochelais": ["La Rochelle"],
    "ASM Clermont Auvergne": ["Clermont Auvergne", "Clermont"],
    "Racing 92": ["Racing 92", "Racing Metro 92"],
    "Aviron Bayonnais": ["Bayonne"],
    "Castres Olympique": ["Castres"],
    "Section Paloise": ["Pau"],
    "Stade Français Paris": ["Stade Francais", "Stade Français"],
    "LOU Rugby": ["Lyon OU", "Lyon"],
    "Montpellier Hérault Rugby": ["Montpellier"],
    "USA Perpignan": ["Perpignan"],
    "US Montauban": ["Montauban"],
    "RC Vannes": ["Vannes"],
    "FC Grenoble": ["Grenoble"],
    "Oyonnax Rugby": ["Oyonnax"],
    "Provence Rugby": ["Provence"],
    "CA Brive": ["Brive"],
    "Colomiers Rugby": ["Colomiers"],
    "SU Agen": ["Agen"],
    "AS Béziers Hérault": ["Beziers"],
    "Biarritz Olympique": ["Biarritz"],
    "Valence Romans Drôme Rugby": ["Valence Romans"],
    "Stade Aurillacois": ["Aurillac"],
    "Stade Montois": ["Mont-de-Marsan", "Stade Montois"],
    "USON Nevers": ["Nevers"],
    "US Dax": ["Dax"],
    "Soyaux Angoulême XV": ["Soyaux Angouleme", "Angouleme"],
    "US Carcassonne": ["Carcassonne"],
    "Bath Rugby": ["Bath"],
    "Northampton Saints": ["Northampton"],
    "Leicester Tigers": ["Leicester"],
    "Bristol Bears": ["Bristol"],
    "Sale Sharks": ["Sale"],
    "Gloucester Rugby": ["Gloucester"],
    "Exeter Chiefs": ["Exeter"],
    "Newcastle Red Bulls": ["Newcastle Falcons", "Newcastle"],
    "Leinster Rugby": ["Leinster"],
    "Munster Rugby": ["Munster"],
    "Ulster Rugby": ["Ulster"],
    "Connacht Rugby": ["Connacht"],
    "Glasgow Warriors": ["Glasgow"],
    "Edinburgh Rugby": ["Edinburgh"],
    "Benetton Rugby": ["Benetton", "Benetton Treviso"],
    "Zebre Parma": ["Zebre"],
    "Bulls": ["Vodacom Bulls", "Blue Bulls"],
    "Stormers": ["DHL Stormers", "Western Province"],
    "Sharks": ["Hollywoodbets Sharks", "Cell C Sharks"],
    "Lions": ["Emirates Lions", "Golden Lions"],
    "Queensland Reds": ["Reds"],
    "Highlanders": ["Highlanders Super Rugby"],
    "NSW Waratahs": ["Waratahs"],
    "Fijian Drua": ["Fijian Drua", "Drua"],
}


def slug(name: str) -> str:
    """'Union Bordeaux-Bègles' -> 'union-bordeaux-begles'."""
    ascii_name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", ascii_name.lower()).strip("-")


def get(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "rugby-game/1.0"})
    for attempt in range(6):
        try:
            with urllib.request.urlopen(request, timeout=20) as response:
                return response.read()
        except urllib.error.HTTPError as error:
            if error.code != 429 or attempt == 5:
                raise
            time.sleep(20 * (attempt + 1))  # la clé gratuite limite le débit
        except (TimeoutError, urllib.error.URLError):
            if attempt == 5:
                raise
            time.sleep(3)
    raise RuntimeError("inaccessible")


def find_team(name: str, country_hint: str) -> dict | None:
    """Fiche TheSportsDB du club de rugby (à XV) le plus proche de ce nom."""
    for query in [name, *ALIASES.get(name, [])]:
        data = json.loads(get(API + urllib.parse.quote(query)))
        teams = [
            t for t in data.get("teams") or []
            if t.get("strSport") == "Rugby" and t.get("strBadge")
            and not THIRTEEN.search((t.get("strLeague") or "").lower())
        ]  # fmt: skip
        time.sleep(2.5)  # 30 requêtes par minute avec la clé gratuite
        if teams:
            # Préfère une équipe senior du bon pays (pas les -20 ans ni les féminines).
            def score(t):
                label = f"{t['strTeam']} {t.get('strLeague') or ''}".lower()
                junior = any(w in label for w in ("women", "u20", "u21", "u18", "féminin"))
                return (junior, country_hint.lower() not in (t.get("strCountry") or "").lower())

            return sorted(teams, key=score)[0]
    return None


# Couleurs (primaire, secondaire) des maillots : TheSportsDB ne les donne presque jamais.
# L'interface prend la première assez foncée pour un bouton à texte blanc.
COLORS = {
    # Top 14
    "Stade Toulousain": ["#D00F16", "#000000"],
    "Union Bordeaux-Bègles": ["#5C1530", "#FFFFFF"],
    "RC Toulon": ["#E2001A", "#000000"],
    "Stade Rochelais": ["#FFD200", "#000000"],
    "ASM Clermont Auvergne": ["#FFD100", "#002B5C"],
    "Racing 92": ["#7CC4EA", "#0A1F44"],
    "Aviron Bayonnais": ["#6CACE4", "#FFFFFF"],
    "Castres Olympique": ["#0055A4", "#FFFFFF"],
    "Section Paloise": ["#00843D", "#FFFFFF"],
    "Stade Français Paris": ["#E5007E", "#00205B"],
    "LOU Rugby": ["#E30613", "#000000"],
    "Montpellier Hérault Rugby": ["#0A2D6E", "#6EC1E4"],
    "USA Perpignan": ["#C8102E", "#FFC72C"],
    "US Montauban": ["#006B3F", "#000000"],
    # Pro D2
    "RC Vannes": ["#003C71", "#FFFFFF"],
    "FC Grenoble": ["#E30613", "#0055A4"],
    "Oyonnax Rugby": ["#D50032", "#000000"],
    "Provence Rugby": ["#1B3E8E", "#F5C400"],
    "CA Brive": ["#000000", "#FFFFFF"],
    "Colomiers Rugby": ["#0050A0", "#FFFFFF"],
    "SU Agen": ["#0072CE", "#FFFFFF"],
    "AS Béziers Hérault": ["#C8102E", "#002B7F"],
    "Biarritz Olympique": ["#D50032", "#FFFFFF"],
    "Valence Romans Drôme Rugby": ["#00447C", "#FFFFFF"],
    "Stade Aurillacois": ["#E30613", "#003A70"],
    "Stade Montois": ["#FFD200", "#000000"],
    "USON Nevers": ["#C8102E", "#FFC72C"],
    "US Dax": ["#D50032", "#FFFFFF"],
    "Soyaux Angoulême XV": ["#003A70", "#FFFFFF"],
    "US Carcassonne": ["#FFD200", "#000000"],
    # Premiership
    "Bath Rugby": ["#00539F", "#000000"],
    "Northampton Saints": ["#00703C", "#C9A227"],
    "Leicester Tigers": ["#006A4E", "#C8102E"],
    "Bristol Bears": ["#13294B", "#FFFFFF"],
    "Saracens": ["#000000", "#D00F16"],
    "Sale Sharks": ["#0B1F4B", "#00A5DF"],
    "Harlequins": ["#C8006A", "#00A9E0"],
    "Gloucester Rugby": ["#CE0E2D", "#FFFFFF"],
    "Exeter Chiefs": ["#000000", "#FFFFFF"],
    "Newcastle Red Bulls": ["#DB0A40", "#001E62"],
    # URC
    "Leinster Rugby": ["#0055A4", "#FFFFFF"],
    "Munster Rugby": ["#C8102E", "#002B5C"],
    "Ulster Rugby": ["#FFFFFF", "#C8102E"],
    "Connacht Rugby": ["#00843D", "#FFFFFF"],
    "Glasgow Warriors": ["#002D72", "#6EC1E4"],
    "Edinburgh Rugby": ["#000000", "#B5121B"],
    "Benetton Rugby": ["#006241", "#FFFFFF"],
    "Zebre Parma": ["#000000", "#FFFFFF"],
    "Bulls": ["#009FDB", "#002B5C"],
    "Stormers": ["#002B5C", "#FFFFFF"],
    "Sharks": ["#000000", "#FFFFFF"],
    "Lions": ["#DA291C", "#FFFFFF"],
    # Super Rugby
    "Crusaders": ["#D00F16", "#000000"],
    "Chiefs": ["#FFC72C", "#000000"],
    "Hurricanes": ["#FFD100", "#000000"],
    "Blues": ["#002B7F", "#6CACE4"],
    "Brumbies": ["#002B5C", "#FFC72C"],
    "Highlanders": ["#1B2A6B", "#8A1538"],
    "Queensland Reds": ["#C8102E", "#FFFFFF"],
    "NSW Waratahs": ["#3EA6E8", "#002B5C"],
    "Western Force": ["#002B5C", "#0072CE"],
    "Fijian Drua": ["#0072CE", "#FFFFFF"],
    "Moana Pasifika": ["#00A0AF", "#000000"],
}

COUNTRIES = {
    "top14": "France",
    "prod2": "France",
    "premiership": "England",
    "urc": "",
    "super_rugby": "",
}


def is_light(png: bytes) -> bool:
    """Vrai si les pixels visibles du blason sont presque tous blancs.

    Lit les PNG RGBA 8 bits non entrelacés (ceux de TheSportsDB) ; un autre format
    est réputé foncé.
    """
    width, height, depth, color_type, _, _, interlace = struct.unpack(">IIBBBBB", png[16:29])
    if (depth, color_type, interlace) != (8, 6, 0):
        return False
    data, pos = b"", 8
    while pos < len(png):
        (length,) = struct.unpack(">I", png[pos : pos + 4])
        if png[pos + 4 : pos + 8] == b"IDAT":
            data += png[pos + 8 : pos + 8 + length]
        pos += 12 + length
    raw, stride = zlib.decompress(data), width * 4
    previous, light, visible = bytearray(stride), 0, 0
    for y in range(height):
        row_start = y * (stride + 1)
        kind, row = raw[row_start], bytearray(raw[row_start + 1 : row_start + 1 + stride])
        for x in range(stride):  # défiltrage PNG (Sub, Up, Average, Paeth)
            a = row[x - 4] if x >= 4 else 0
            b = previous[x]
            c = previous[x - 4] if x >= 4 else 0
            if kind == 1:
                row[x] = (row[x] + a) & 255
            elif kind == 2:
                row[x] = (row[x] + b) & 255
            elif kind == 3:
                row[x] = (row[x] + (a + b) // 2) & 255
            elif kind == 4:
                p = a + b - c
                pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
                row[x] = (row[x] + (a if pa <= pb and pa <= pc else b if pb <= pc else c)) & 255
        for x in range(0, stride, 4):
            if row[x + 3] > 128:
                visible += 1
                light += min(row[x : x + 3]) > 215
        previous = row
    return visible > 0 and light / visible > 0.9


def colors_of(team: dict) -> list[str]:
    """Couleurs primaire et secondaire déclarées par TheSportsDB (hex, majuscules)."""
    found = [team.get(k) or "" for k in ("strColour1", "strColour2", "strColour3")]
    found = [c.upper() for c in found if re.fullmatch(r"#[0-9A-Fa-f]{6}", c.strip())]
    return found[:2]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--force", action="store_true", help="retélécharge les blasons présents")
    args = parser.parse_args()

    LOGO_DIR.mkdir(parents=True, exist_ok=True)
    manifest = json.loads(MANIFEST.read_text()) if MANIFEST.exists() else {}
    missing = []
    for league in LEAGUES:
        for club in league.clubs:
            entry = manifest.get(club.name, {})
            filename = f"{slug(club.name)}.png"
            path = LOGO_DIR / filename
            team = None
            if args.force or not path.exists():
                team = find_team(club.name, COUNTRIES.get(league.code, ""))
                if team:
                    # /small : vignette de 250 px, bien assez pour l'écusson.
                    path.write_bytes(get(f"{team['strBadge']}/small"))
            if path.exists():
                entry["logo"] = f"/clubs/{filename}"
                entry["light"] = is_light(path.read_bytes())
            else:
                missing.append(club.name)
            colors = COLORS.get(club.name) or (colors_of(team) if team else entry.get("colors"))
            if colors:
                entry["colors"] = colors
            manifest[club.name] = entry
            if team or not path.exists():
                print(f"  {'ok' if path.exists() else '- '}  {club.name}")
            # Écrit à chaque club : un arrêt en route ne perd rien.
            text = json.dumps(dict(sorted(manifest.items())), ensure_ascii=False, indent=2)
            MANIFEST.write_text(text + "\n")

    print(f"\n{len(manifest)} clubs, {len(missing)} sans blason : {', '.join(missing) or 'aucun'}")


if __name__ == "__main__":
    main()
