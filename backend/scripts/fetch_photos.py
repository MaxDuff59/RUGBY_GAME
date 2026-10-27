"""Complète les photos des joueurs de data/rosters.json, depuis Wikimedia Commons.

fetch_rosters ne trouve la photo que des joueurs dont l'effectif Wikipédia donne
l'article, et seulement l'image de leur fiche Wikidata. Ce script cherche celle des
autres, toujours parmi les fichiers libres de Commons :

1. La fiche Wikidata du joueur, retrouvée par son nom (libellés et alias) parmi tous
   les joueurs de rugby à XV, en une requête. La date de naissance départage les
   homonymes ; sans elle, on écarte ceux nés avant 1980. Un nom encore ambigu est
   laissé de côté : mieux vaut la silhouette qu'une photo d'un autre.
2. Sa photo : l'image de sa fiche (P18), sinon une photo de Commons qui le
   « représente » (P180) sans autre joueur, sinon la première photo de sa catégorie
   Commons (P373).

Seuls les joueurs sans photo changent ; on relance le script après fetch_rosters.
Une photo choisie se corrige depuis le backoffice (fiche du joueur).

Usage (depuis le dossier backend/) :
    uv run python -m scripts.fetch_photos
    uv run python -m scripts.fetch_photos --dry-run   # affiche sans écrire
"""

import argparse
import json
import re
import unicodedata
import urllib.parse

from scripts.fetch_rosters import ROSTERS, get_json

SPARQL = "https://query.wikidata.org/sparql"
COMMONS = "https://commons.wikimedia.org/w/api.php"
PLAYERS_QUERY = """
SELECT ?player ?label ?born ?image ?category WHERE {
  ?player wdt:P106 wd:Q14089670 .
  { ?player rdfs:label ?label } UNION { ?player skos:altLabel ?label }
  FILTER(LANG(?label) IN ("en", "fr", "it", "es", "de", "mul"))
  OPTIONAL { ?player wdt:P569 ?born }
  OPTIONAL { ?player wdt:P18 ?image }
  OPTIONAL { ?player wdt:P373 ?category }
}
"""
PHOTO_FILE = re.compile(r"\.(jpe?g|png|webp)$", re.I)
# Joueurs cherchés à la fois parmi les fichiers qui « représentent » quelqu'un.
DEPICTS_CHUNK = 20


def key(name: str) -> str:
    """'Nelson Épée' -> 'nelson epee' : sans accents, tirets ni apostrophes."""
    plain = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode().lower()
    return " ".join(re.sub(r"[^a-z ]", "", re.sub(r"[-.]", " ", plain)).split())


# --- Fiches Wikidata ---------------------------------------------------------------------


def wikidata_players() -> tuple[dict[str, set[str]], dict[str, dict]]:
    """Nom -> identifiants Wikidata, et identifiant -> {born, image, category}."""
    query = urllib.parse.urlencode({"query": PLAYERS_QUERY, "format": "json"})
    rows = get_json(f"{SPARQL}?{query}")["results"]["bindings"]
    names: dict[str, set[str]] = {}
    facts: dict[str, dict] = {}
    for row in rows:
        qid = row["player"]["value"].rsplit("/", 1)[-1]
        names.setdefault(key(row["label"]["value"]), set()).add(qid)
        fact = facts.setdefault(qid, {"born": set()})
        if "born" in row:
            fact["born"].add(row["born"]["value"][:10])
        if "image" in row:
            image = urllib.parse.unquote(row["image"]["value"].rsplit("/", 1)[-1])
            fact.setdefault("image", image)
        if "category" in row:
            fact.setdefault("category", row["category"]["value"])
    return names, facts


def identify(entry: dict, names: dict[str, set[str]], facts: dict[str, dict]) -> str | None:
    """L'identifiant Wikidata du joueur, s'il n'y a pas de doute."""
    found = names.get(key(entry["name"]), set())
    born = entry.get("born")
    if born:
        found = {q for q in found if born in facts[q]["born"] or not facts[q]["born"]}
    else:
        found = {q for q in found if not facts[q]["born"] or max(facts[q]["born"]) >= "1980"}
    return next(iter(found)) if len(found) == 1 else None


# --- Photos sur Commons ------------------------------------------------------------------


def depicting(qids: list[str], players: set[str]) -> dict[str, list[str]]:
    """Identifiant -> photos de Commons qui le représentent sans autre joueur connu."""
    found: dict[str, list[str]] = {}
    for start in range(0, len(qids), DEPICTS_CHUNK):
        chunk = qids[start : start + DEPICTS_CHUNK]
        statement = "|".join(f"P180={q}" for q in chunk)
        params = {
            "action": "query",
            "list": "search",
            "srnamespace": 6,
            "srsearch": f"haswbstatement:{statement}",
            "srlimit": 500,
            "srprop": "",
            "format": "json",
        }
        hits = get_json(f"{COMMONS}?{urllib.parse.urlencode(params)}")["query"]["search"]
        files = {f"M{hit['pageid']}": hit["title"] for hit in hits if PHOTO_FILE.search(hit["title"])}
        ids = list(files)
        for first in range(0, len(ids), 50):
            params = {
                "action": "wbgetentities",
                "ids": "|".join(ids[first : first + 50]),
                "props": "claims",
                "format": "json",
            }
            entities = get_json(f"{COMMONS}?{urllib.parse.urlencode(params)}").get("entities", {})
            for mid, entity in entities.items():
                statements = entity.get("statements") or entity.get("claims") or {}
                shown = {
                    s["mainsnak"]["datavalue"]["value"]["id"]
                    for s in statements.get("P180", [])
                    if "datavalue" in s["mainsnak"]
                } & players
                if len(shown) == 1 and shown & set(chunk):
                    title = files[mid].removeprefix("File:")
                    found.setdefault(next(iter(shown)), []).append(title)
    return found


def category_photo(category: str, name: str) -> str | None:
    """La photo de la catégorie Commons du joueur, de préférence à son nom."""
    params = {
        "action": "query",
        "list": "categorymembers",
        "cmtitle": f"Category:{category}",
        "cmtype": "file",
        "cmlimit": 50,
        "format": "json",
    }
    members = get_json(f"{COMMONS}?{urllib.parse.urlencode(params)}")["query"]["categorymembers"]
    photos = [m["title"].removeprefix("File:") for m in members if PHOTO_FILE.search(m["title"])]
    surname = key(name).split()[-1]
    named = [p for p in photos if surname in key(p).split()]
    return (named or photos or [None])[0]


def best(photos: list[str], name: str) -> str:
    """Parmi les photos qui le représentent : celle à son nom, la plus récente d'abord."""
    surname = key(name).split()[-1]
    return max(photos, key=lambda p: (surname in key(p).split(), re.findall(r"\b20\d\d\b", p)))


# --- Programme ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="affiche sans écrire")
    args = parser.parse_args()

    rosters = json.loads(ROSTERS.read_text())
    missing = [
        (club, entry)
        for club, roster in rosters.items()
        for entry in [*roster["pros"], *roster["youths"]]
        if not entry.get("photo") and not entry.get("photo_id")
    ]
    print(f"{len(missing)} joueurs sans photo")

    names, facts = wikidata_players()
    print(f"{len(facts)} joueurs de rugby à XV sur Wikidata")
    qids = {id(entry): identify(entry, names, facts) for _, entry in missing}
    # Une fiche reconnue dans deux effectifs : on ne sait pas lequel est le bon.
    seen: dict[str, int] = {}
    for qid in qids.values():
        if qid:
            seen[qid] = seen.get(qid, 0) + 1
    qids = {k: q for k, q in qids.items() if q and seen[q] == 1}
    print(f"{len(qids)} retrouvés sans doute possible")

    without_image = sorted(q for q in qids.values() if "image" not in facts[q])
    shown = depicting(without_image, set(facts))
    found = {"fiche": 0, "représenté": 0, "catégorie": 0}
    for club, entry in missing:
        qid = qids.get(id(entry))
        if not qid:
            continue
        fact = facts[qid]
        if "image" in fact:
            photo, source = fact["image"], "fiche"
        elif qid in shown:
            photo, source = best(shown[qid], entry["name"]), "représenté"
        elif "category" in fact:
            photo, source = category_photo(fact["category"], entry["name"]), "catégorie"
        else:
            continue
        if not photo:
            continue
        found[source] += 1
        entry["photo"] = photo
        print(f"  {club} · {entry['name']} ({source}) : {photo}")

    print(f"\n{sum(found.values())} photos trouvées : " + ", ".join(f"{n} {s}" for s, n in found.items()))
    if not args.dry_run:
        text = json.dumps(dict(sorted(rosters.items())), ensure_ascii=False, indent=1)
        ROSTERS.write_text(text + "\n")


if __name__ == "__main__":
    main()
