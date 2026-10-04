# Rugby Manager (prototype)

Jeu de gestion de rugby à XV, dans l'esprit de Football Manager : on incarne
le manager d'un club et on le mène à travers les saisons. Pas d'interface
graphique pour l'instant.

## Organisation

```
backend/    API FastAPI, moteur de simulation, modèles, données fictives (Python 3.12)
frontend/   Interface React + Vite (voir frontend/README.md)
```

## Jouer

Deux terminaux : l'API, puis l'interface.

```bash
cd backend && uv run uvicorn api.main:app --reload     # terminal 1
cd frontend && npm install && npm run dev               # terminal 2, puis http://localhost:5173
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
Au premier démarrage, la base `backend/rugby.db` est créée et remplie de 14 clubs
fictifs ; supprime ce fichier pour repartir d'un monde neuf (obligatoire aussi quand
le schéma de la base change : l'API le signale au démarrage).

| Route | Rôle |
|---|---|
| `GET /clubs`, `GET /clubs/{id}` | Clubs, effectif complet et notes collectives du XV |
| `POST /career`, `GET /career` | Choisir son club (tire aussi le calendrier de la 1re saison) |
| `GET /seasons/current` | Calendrier daté, classement, prochaine journée, phases finales |
| `POST /seasons/current/play` | Joue la journée suivante (matchs, billetterie, sponsors, salaires) |
| `POST /seasons/next` | Intersaison : âges, retraites, jeunes, nouveau calendrier |
| `GET /matches/{id}`, `POST /matches/simulate` | Détail d'un match joué ; match amical |
| `GET /finances` | Trésorerie, masse salariale et toutes les opérations |
| `GET /staff`, `POST /staff/hire/{id}`, `POST /staff/{id}/fire` | Staff : voir, embaucher, licencier |
| `GET /facilities`, `POST /facilities/{kind}/upgrade` | Stade, centre d'entraînement, formation |
| `GET /transfers`, `POST /transfers/buy/{id}`, `POST /transfers/sell/{id}` | Marché des transferts |
| `GET /medical`, `POST /medical/{id}/protocol/{protocol}` | Infirmerie : blessés, protocole de soins, dossier médical |

## Blessures

Chaque journée, la semaine d'entraînement puis les matchs peuvent blesser des
joueurs (événement `injury` du match). Une blessure est **légère** (1 à 3
semaines), **modérée** (4 à 8) ou **grave** (3 à 9 mois) ; le blessé sort du XV
jusqu'à sa date de retour. Pour son club, le manager choisit un protocole de
soins, définitif pour cette blessure :

| Protocole | Durée | Rechute (par match, 4 semaines après le retour) | Coût |
|---|---|---|---|
| Prudent | × 1,3 | 1 % | – |
| Normal (par défaut) | × 1 | 4 % | – |
| Retour anticipé | × 0,65 | 12 % | 15 k€ / 50 k€ / 150 k€ selon la gravité |

Un bon kinésithérapeute raccourcit la convalescence (jusqu'à −20 %), un bon
médecin réduit le risque de rechute (jusqu'à −40 %). Une rechute reproduit la
même blessure. Règles dans `backend/engine/medical.py`.

## Principe d'architecture

Le moteur de simulation (`backend/engine/`) ne travaille que sur des objets
Python simples (`backend/models/domain.py`). Il ne connaît ni FastAPI ni la base
de données, ce qui permet de le tester et de l'utiliser seul (script CLI, tests).
La persistance SQLAlchemy (`backend/models/orm.py`) est une couche à part qui
convertit ses lignes en objets du domaine. Le frontend ne parle qu'à l'API.
