# Football Manager (prototype)

Jeu de gestion de football, sans interface graphique pour l'instant.

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

## Principe d'architecture

Le moteur de simulation (`backend/engine/`) ne travaille que sur des objets
Python simples (`backend/models/domain.py`). Il ne connaît ni FastAPI ni la base
de données, ce qui permet de le tester et de l'utiliser seul (script CLI, tests).
La persistance SQLAlchemy (`backend/models/orm.py`) est une couche à part qui
convertit ses lignes en objets du domaine.
