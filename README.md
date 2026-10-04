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
uv run python -m scripts.run_season --top14 --club 1                 # les vrais clubs
```

### Lancer l'API

```bash
uv run uvicorn api.main:app --reload
```

Puis ouvrir http://localhost:8000/docs pour tester les routes dans le navigateur.
Au premier démarrage, la base `backend/rugby.db` est créée avec les 14 clubs du
Top 14 (saison 2025-26 ; voir `backend/data/top14.py`), leurs vrais stades, et des
joueurs et un staff inventés à leur niveau. Supprime ce fichier pour repartir d'un
monde neuf (obligatoire aussi quand le schéma de la base change : l'API le signale
au démarrage).

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
| `GET /transfers`, `GET /transfers/{id}`, `POST /transfers/{id}/open` | Marché, approche d'un joueur, ouverture d'une négociation |
| `POST /transfers/negotiations/{id}/offer`, `DELETE /transfers/negotiations/{id}` | Offre pour l'étape en cours ; quitter la table |
| `POST /transfers/sell/{id}` | Vendre un de ses joueurs |
| `GET /medical`, `POST /medical/{id}/protocol/{protocol}` | Infirmerie : blessés, protocole de soins, dossier médical |

## Recrutement

Chaque joueur a un contrat (fin de saison indiquée). Trois voies, règles dans
`backend/engine/transfers.py` :

| Voie | Quand | Étapes | Arrivée |
|---|---|---|---|
| Pré-contrat | dernière année de contrat | salaire avec le joueur | intersaison |
| Transfert | en cours de contrat (rare, cher) | indemnité avec le club, puis salaire avec le joueur | immédiate |
| Prêt | non-titulaire chez lui | le joueur accepte s'il gagne du temps de jeu | immédiate, retour en fin de saison, salaire à ta charge |

Le club demande une indemnité qui grandit avec les saisons de contrat restantes
et l'importance du joueur ; un grand club (note collective ≥ 15) ne vend pas ses
titulaires. Le joueur pèse le prestige du club d'arrivée, son temps de jeu
attendu et le salaire : un remplaçant d'un gros club ne descend que pour un
salaire XXL (ou en prêt), un titulaire d'un petit club vient volontiers dans
un grand. Une offre refusée mais sérieuse (≥ 85 % de la demande) fait baisser
la demande de 5 % ; au quatrième refus, l'autre partie quitte la table. Les
contrats arrivés à terme sont renouvelés automatiquement pour l'instant.

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
