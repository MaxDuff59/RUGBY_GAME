"""Récupère les vrais effectifs (pros et espoirs) des clubs depuis Wikipédia.

Pour chaque club, l'article Wikipédia anglais donne l'effectif (section « Current
squad ») et souvent les espoirs (« Academy squad », « Espoirs squad »…) : nom, poste,
nationalité et international ou non (`cap=y`). Wikidata donne la date de naissance
et la photo (fichier libre de Wikimedia Commons) des joueurs qui ont un article,
seulement s'il s'agit bien d'un joueur de rugby.

Le résultat va dans data/rosters.json, que le générateur lit pour créer les joueurs
des vrais clubs (data/generator.py) ; un club absent du fichier garde des joueurs
inventés. Les attributs restent calculés par le jeu (niveau du club, international,
âge) : Wikipédia ne note pas les joueurs.

Usage (depuis le dossier backend/) :
    uv run python -m scripts.fetch_rosters
    uv run python -m scripts.fetch_rosters --club "Stade Toulousain"   # un seul club
    uv run python -m scripts.fetch_rosters --missing                   # clubs pas encore récupérés
"""

import argparse
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date
from pathlib import Path

from data.leagues import LEAGUES

ROSTERS = Path(__file__).resolve().parents[1] / "data" / "rosters.json"
USER_AGENT = "rugby-manager-game/1.0 (jeu personnel ; effectifs pour un jeu de gestion)"

# Article Wikipédia (anglais) de chaque club, quand son nom diffère de celui du jeu.
ARTICLES = {
    "Union Bordeaux-Bègles": "Union Bordeaux Bègles",
    "Stade Français Paris": "Stade Français",
    "LOU Rugby": "Lyon OU",
    "Colomiers Rugby": "US Colomiers",
    "Stade Aurillacois": "Stade Aurillacois Cantal Auvergne",
    "USON Nevers": "USON Nevers Rugby",
    "Soyaux Angoulême XV": "Soyaux Angoulême XV Charente",
    "Saracens": "Saracens F.C.",
    "Harlequins": "Harlequin F.C.",
    "Bulls": "Bulls (rugby union)",
    "Stormers": "Stormers",
    "Sharks": "Sharks (rugby union)",
    "Lions": "Lions (United Rugby Championship)",
    "Crusaders": "Crusaders (rugby union)",
    "Chiefs": "Chiefs (rugby union)",
    "Hurricanes": "Hurricanes (rugby union)",
    "Blues": "Blues (Super Rugby)",
    "Brumbies": "ACT Brumbies",
    "Highlanders": "Highlanders (rugby union)",
    "Queensland Reds": "Queensland Reds",
    "NSW Waratahs": "New South Wales Waratahs",
}

# Intitulés de section : effectif pro, puis espoirs.
SENIOR_SECTIONS = re.compile(
    r"^(current|senior|first[- ]team)?\s*squad$|^current (playing )?squad", re.I
)
YOUTH_SECTIONS = re.compile(r"academy|espoirs|development|youth|\bu-?2[01]\b|reserves?", re.I)
# Sous-section espoirs glissée dans la section de l'effectif pro.
YOUTH_SUBSECTION = re.compile(r"^={3,4}.*(academy|espoirs|development).*=+\s*$", re.I | re.M)

# Intertitre de l'effectif -> poste du jeu (voir models.Position).
POSITION_HEADINGS = [
    (r"prop", "prop"),
    (r"hooker", "hooker"),
    (r"lock|second.row", "lock"),
    (r"back.row|flanker|number.?8|no\.? ?8|loose.forward|forwards? back", "back_row"),
    (r"scrum.hal|half.?back", "scrum_half"),
    (r"fly.hal|first.five|out.?hal|stand.off", "fly_half"),
    (r"centre|center|midfield|second.five", "centre"),
    (r"wing", "wing"),
    (r"full.?back", "fullback"),
    (r"outside back|utility back|back three", "wing"),
]
# Abréviations du paramètre `pos=` de certains modèles.
POSITION_CODES = {
    "PR": "prop", "P": "prop", "LHP": "prop", "THP": "prop",
    "HK": "hooker", "H": "hooker",
    "LK": "lock", "L": "lock",
    "FL": "back_row", "F": "back_row", "N8": "back_row", "BR": "back_row", "LF": "back_row",
    "SH": "scrum_half", "HB": "scrum_half",
    "FH": "fly_half", "FE": "fly_half", "OH": "fly_half",
    "CE": "centre", "C": "centre", "IC": "centre", "OC": "centre",
    "WG": "wing", "W": "wing", "UB": "wing",
    "FB": "fullback",
}  # fmt: skip

RUGBY_UNION = "Q5849"
RUGBY_UNION_PLAYER = "Q14089670"


def get_json(url: str) -> dict:
    """GET JSON poli : une requête toutes les deux secondes, et on patiente quand le
    serveur le demande."""
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    for attempt in range(8):
        time.sleep(2)
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                return json.loads(response.read())
        except urllib.error.HTTPError as error:
            if error.code != 429 and error.code < 500 or attempt == 7:
                raise
            wait = int(error.headers.get("Retry-After") or 0) or 20 * (attempt + 1)
            print(f"      (le serveur demande d'attendre {wait} s)")
            time.sleep(wait)
        except (TimeoutError, urllib.error.URLError):
            if attempt == 7:
                raise
            time.sleep(5 * (attempt + 1))
    raise RuntimeError("inaccessible")


def wikitext(title: str, lang: str = "en") -> str | None:
    query = urllib.parse.urlencode(
        {
            "action": "parse",
            "page": title,
            "prop": "wikitext",
            "redirects": 1,
            "format": "json",
            "formatversion": 2,
        }
    )
    data = get_json(f"https://{lang}.wikipedia.org/w/api.php?{query}")
    return data.get("parse", {}).get("wikitext")


def sections(text: str) -> list[tuple[str, str]]:
    """(titre, contenu) de chaque section, sous-sections incluses dans leur parente."""
    heads = list(re.finditer(r"^(={2,4})\s*(.*?)\s*\1\s*$", text, re.M))
    result = []
    for i, head in enumerate(heads):
        level = len(head.group(1))
        end = next((h.start() for h in heads[i + 1 :] if len(h.group(1)) <= level), len(text))
        result.append((head.group(2), text[head.end() : end]))
    return result


def templates(text: str, name_pattern: str):
    """Modèles {{...}} dont le nom correspond, avec leur position dans le texte."""
    for match in re.finditer(r"\{\{\s*(" + name_pattern + r")\s*\|", text, re.I):
        depth, i = 2, match.end()
        while i < len(text) and depth:
            if text.startswith("{{", i):
                depth, i = depth + 2, i + 2
            elif text.startswith("}}", i):
                depth, i = depth - 2, i + 2
            else:
                i += 1
        yield match.start(), text[match.end() : i - 2]


def split_params(body: str) -> tuple[list[str], dict[str, str]]:
    """Paramètres d'un modèle, sans couper dans les liens [[a|b]] ni les modèles imbriqués."""
    parts, depth, current = [], 0, ""
    for i, char in enumerate(body):
        pair = body[i : i + 2]
        if pair in ("[[", "{{"):
            depth += 1
        elif pair in ("]]", "}}"):
            depth -= 1
        if char == "|" and depth <= 0:
            parts.append(current)
            current = ""
        else:
            current += char
    parts.append(current)
    positional, named = [], {}
    for part in parts:
        key, sep, value = part.partition("=")
        if sep and re.fullmatch(r"\s*[a-zA-Z_ ]+\s*", key) and "[[" not in key:
            named[key.strip().lower()] = value.strip()
        else:
            positional.append(part.strip())
    return positional, named


def clean_name(raw: str) -> tuple[str, str | None, str]:
    """'[[:fr:Paul Graou|Paul Graou]]' -> ('Paul Graou', 'Paul Graou', 'fr')."""
    # {{ill|Titre anglais|fr|Titre français|lt=Libellé}} : lien vers un autre Wikipédia.
    ill = next(templates(raw, r"ill|interlanguage link"), None)
    if ill:
        positional, named = split_params(ill[1])
        title = positional[0] if positional else ""
        label = named.get("lt") or title
        lang = next((p for p in positional[1:] if re.fullmatch(r"[a-z]{2}", p)), "en")
        index = positional.index(lang) if lang in positional else -1
        target = positional[index + 1] if 0 <= index < len(positional) - 1 else title
        return re.sub(r"\s*\(.*\)$", "", label).strip(), target, lang
    raw = re.sub(r"<ref[^>]*/>|<ref.*?</ref>|\{\{.*?\}\}|'''?", "", raw, flags=re.S).strip()
    link = re.search(r"\[\[(:?([a-z]{2}):)?([^|\]]+)(?:\|([^\]]+))?\]\]", raw)
    if link:
        lang = link.group(2) or "en"
        target = link.group(3).strip()
        label = (link.group(4) or target).strip()
        label = re.sub(r"\s*\(.*\)$", "", label)
        return label, target, lang
    name = re.sub(r"\s+", " ", raw).strip()
    return name, name, "en"


def heading_position(line: str) -> str | None:
    """Poste annoncé par un intertitre ('''Props''', ;Hookers, ==Locks==…)."""
    title = re.fullmatch(r"\s*(?:'''(.+?)'''|;\s*(.+)|={3,5}\s*(.+?)\s*=+)\s*", line)
    if not title:
        return None
    label = next(g for g in title.groups() if g).lower()
    for pattern, position in POSITION_HEADINGS:
        if re.search(pattern, label):
            return position
    return None


def parse_squad(text: str) -> list[dict]:
    """Joueurs d'une section d'effectif : nom, poste, nationalité, international."""
    players, position = [], None
    for line in text.splitlines():
        position = heading_position(line) or position
        for _, body in templates(line, r"(?:RU|Rugby(?: union)?) squad player\d?"):
            positional, named = split_params(body)
            nat = named.get("nat") or (positional[0] if positional else "")
            raw = named.get("name") or (positional[1] if len(positional) > 1 else "")
            code = (named.get("pos") or "").upper().strip()
            pos = POSITION_CODES.get(code) or position
            if not raw or not pos:
                continue
            name, target, lang = clean_name(raw)
            if named.get("link"):
                target, lang = named["link"], "en"
            if not name:
                continue
            players.append(
                {
                    "name": name,
                    "position": pos,
                    "nationality": nat.strip().upper()[:3],
                    "international": named.get("cap", "").lower() in ("y", "yes"),
                    "link": target,
                    "lang": lang,
                    "nolink": named.get("nolink", "").lower() in ("y", "yes"),
                }
            )
    return players


def club_squads(title: str) -> tuple[list[dict], list[dict], str]:
    """(pros, espoirs, titre de l'article) d'un club."""
    text = wikitext(title)
    if not text:
        return [], [], title
    seniors, youths = [], []
    for heading, body in sections(text):
        is_youth = bool(YOUTH_SECTIONS.search(heading))
        if not is_youth and not SENIOR_SECTIONS.search(heading.strip()):
            continue
        # La section pro contient parfois les espoirs en sous-section : on les écarte.
        if not is_youth:
            body = YOUTH_SUBSECTION.split(body)[0]
        squad = parse_squad(body)
        if is_youth:
            youths.extend(p for p in squad if p["name"] not in {y["name"] for y in youths})
        elif not seniors:
            seniors = squad
    return seniors, youths, title


# --- Date de naissance et photo (Wikidata) ----------------------------------------------


def wikidata_ids(titles: list[str], lang: str) -> dict[str, str]:
    """Titre d'article -> identifiant Wikidata (redirections suivies)."""
    found = {}
    for start in range(0, len(titles), 50):
        chunk = titles[start : start + 50]
        query = urllib.parse.urlencode(
            {
                "action": "query",
                "titles": "|".join(chunk),
                "prop": "pageprops",
                "ppprop": "wikibase_item",
                "redirects": 1,
                "format": "json",
                "formatversion": 2,
            }
        )
        data = get_json(f"https://{lang}.wikipedia.org/w/api.php?{query}")["query"]
        alias = {t: t for t in chunk}
        for step in ("normalized", "redirects"):
            for item in data.get(step, []):
                for source, target in list(alias.items()):
                    if target == item["from"]:
                        alias[source] = item["to"]
        items = {
            page["title"]: page.get("pageprops", {}).get("wikibase_item")
            for page in data.get("pages", [])
        }
        for source, target in alias.items():
            if items.get(target):
                found[source] = items[target]
    return found


def wikidata_facts(ids: list[str]) -> dict[str, dict]:
    """Identifiant Wikidata -> {born: AAAA-MM-JJ, photo: fichier Commons}, pour les joueurs
    de rugby à XV seulement (un homonyme est ignoré)."""
    found = {}
    for start in range(0, len(ids), 50):
        chunk = ids[start : start + 50]
        query = urllib.parse.urlencode(
            {"action": "wbgetentities", "ids": "|".join(chunk), "props": "claims", "format": "json"}
        )
        entities = get_json(f"https://www.wikidata.org/w/api.php?{query}").get("entities", {})
        for qid, entity in entities.items():
            claims = entity.get("claims", {})

            def values(prop, claims=claims):
                return [
                    c["mainsnak"].get("datavalue", {}).get("value")
                    for c in claims.get(prop, [])
                    if c["mainsnak"].get("datavalue")
                ]

            sports = {v.get("id") for v in values("P641") if isinstance(v, dict)}
            jobs = {v.get("id") for v in values("P106") if isinstance(v, dict)}
            if RUGBY_UNION not in sports and RUGBY_UNION_PLAYER not in jobs:
                continue  # homonyme qui n'est pas un joueur de rugby
            facts = {}
            born = [v["time"] for v in values("P569") if isinstance(v, dict) and "time" in v]
            if born and re.match(r"\+\d{4}-\d{2}-\d{2}", born[0]):
                day = born[0][1:11].replace("-00", "-01")
                if 1980 <= int(day[:4]) <= date.today().year - 15:
                    facts["born"] = day
            photos = [v for v in values("P18") if isinstance(v, str)]
            if photos:
                facts["photo"] = photos[0]
            if facts:
                found[qid] = facts
    return found


def add_wikidata_facts(players: list[dict]) -> None:
    for lang in ("en", "fr"):
        titles = sorted(
            {p["link"] for p in players if p["lang"] == lang and p["link"] and not p.get("born")}
        )
        ids = wikidata_ids(titles, lang)
        dates = wikidata_facts(sorted(set(ids.values())))
        for player in players:
            qid = ids.get(player["link"]) if player["lang"] == lang else None
            if qid and qid in dates:
                player.update(dates[qid])


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--club", help="ne récupère que ce club (nom du jeu)")
    parser.add_argument("--missing", action="store_true", help="seulement les clubs absents")
    args = parser.parse_args()

    rosters = json.loads(ROSTERS.read_text()) if ROSTERS.exists() else {}
    for league in LEAGUES:
        for club in league.clubs:
            if args.club and club.name != args.club:
                continue
            if args.missing and club.name in rosters:
                continue
            title = ARTICLES.get(club.name, club.name)
            try:
                pros, youths, title = club_squads(title)
                add_wikidata_facts(pros + youths)
            except (urllib.error.URLError, TimeoutError) as error:
                print(f"  !   {club.name} : {error}")
                continue
            if not pros:
                print(f"  -   {club.name} : pas d'effectif trouvé ({title})")
                continue
            keep = ("name", "position", "nationality", "international", "born", "photo")
            rosters[club.name] = {
                "source": f"https://en.wikipedia.org/wiki/{title.replace(' ', '_')}",
                "pros": [{k: p[k] for k in keep if k in p} for p in pros],
                "youths": [{k: p[k] for k in keep if k in p} for p in youths],
            }
            dated = sum("born" in p for p in pros + youths)
            print(f"  ok  {club.name} : {len(pros)} pros, {len(youths)} espoirs, {dated} âges")
            text = json.dumps(dict(sorted(rosters.items())), ensure_ascii=False, indent=1)
            ROSTERS.write_text(text + "\n")

    print(f"\n{len(rosters)} clubs avec leur effectif réel")


if __name__ == "__main__":
    main()
