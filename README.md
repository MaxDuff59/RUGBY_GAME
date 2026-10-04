# Rugby Manager (prototype)

Jeu de gestion de rugby à XV, dans l'esprit de Football Manager : on incarne
le manager d'un club et on le mène à travers les saisons. Pas d'interface
graphique pour l'instant.

## Organisation

```
backend/    API FastAPI, moteur de simulation, modèles, données fictives (Python 3.12)
frontend/   Interface React + Vite (phase 2, vide pour l'instant)
```

## Démarrage rapide (backend)

Prérequis : [uv](https://docs.astral.sh/uv/).

```bash
cd backend
uv sync                 # crée .venv et installe les dépendances
uv run ruff check .     # lint
uv run pytest           # tests
```

Toutes les commandes se lancent **depuis `backend/`**.

### Simuler une saison dans le terminal

```bash
uv run python -m scripts.run_season                              # 10 clubs, ton club au hasard
uv run python -m scripts.run_season --clubs 14 --club 3 --seed 42
```

### Lancer l'API

```bash
uv run uvicorn api.main:app --reload
```

Puis ouvrir http://localhost:8000/docs pour tester les routes dans le navigateur.
Au premier démarrage, la base `backend/rugby.db` est créée et remplie de 10 clubs
fictifs ; supprime ce fichier pour repartir d'un monde neuf.

| Route | Rôle |
|---|---|
| `GET /clubs` | Liste des clubs et leur niveau |
| `GET /clubs/{id}` | Effectif complet + notes collectives du XV de départ |
| `POST /matches/simulate` | Simule un match entre deux clubs (`seed` optionnel) |
| `POST /career`, `GET /career` | Choisir / consulter le club que tu diriges |
| `POST /seasons`, `GET /seasons/{year}` | Simuler une saison complète / son classement |

## Principe d'architecture

Le moteur de simulation (`backend/engine/`) ne travaille que sur des objets
Python simples (`backend/models/domain.py`). Il ne connaît ni FastAPI ni la base
de données, ce qui permet de le tester et de l'utiliser seul (script CLI, tests).
La persistance SQLAlchemy (`backend/models/orm.py`) est une couche à part qui
convertit ses lignes en objets du domaine.
