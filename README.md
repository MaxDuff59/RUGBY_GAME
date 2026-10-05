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
joueurs (pros et espoirs) et un staff inventés à leur niveau. Supprime ce fichier pour repartir d'un
monde neuf (obligatoire aussi quand le schéma de la base change : l'API le signale
au démarrage).

| Route | Rôle |
|---|---|
| `GET /clubs`, `GET /clubs/{id}` | Clubs, effectif complet et notes collectives du XV |
| `GET /clubs/{id}/notes` | Vie du club sur 20 (moral, cohésion, fraîcheur, confiance de la direction, ferveur des supporters) et forme du jour |
| `GET /career/dismissal` | Dernier limogeage, tant qu'aucune nouvelle carrière n'a commencé |
| `GET /players/{id}` | Fiche d'un joueur : comparaison à son poste, note à chaque poste, saison, blessures |
| `POST /career`, `GET /career` | Choisir son club (tire aussi le calendrier de la 1re saison) |
| `GET /seasons/current` | Calendrier daté, classement, prochaine journée, phases finales |
| `POST /seasons/current/play` | Joue la journée suivante (matchs, billetterie, sponsors, salaires) |
| `POST /seasons/next` | Intersaison : âges, retraites, jeunes, nouveau calendrier |
| `GET /matches/{id}`, `POST /matches/simulate` | Détail d'un match joué ; match amical |
| `GET /finances` | Trésorerie, masse salariale et toutes les opérations |
| `GET /staff`, `POST /staff/hire/{id}`, `POST /staff/{id}/fire` | Staff : voir, embaucher, licencier |
| `GET /facilities`, `POST /facilities/{kind}/upgrade` | Stade, centre d'entraînement, formation |
| `POST /facilities/stadium/stands/{side}/amenities` | Installer un aménagement (panneau sponsor, buvette, boutique, loges, écran géant) dans une tribune ; il rapporte à chaque match |
| `GET /transfers`, `GET /transfers/{id}`, `POST /transfers/{id}/open` | Marché, approche d'un joueur, ouverture d'une négociation |
| `POST /transfers/negotiations/{id}/offer`, `DELETE /transfers/negotiations/{id}` | Offre pour l'étape en cours ; quitter la table |
| `POST /transfers/sell/{id}` | Vendre un de ses joueurs |
| `GET /medical`, `POST /medical/{id}/protocol/{protocol}` | Infirmerie : blessés, protocole de soins, dossier médical |
| `GET /academy`, `POST /academy/promote/{id}`, `POST /academy/demote/{id}` | Centre de formation : espoirs, championnat espoirs, promotions |
| `GET /affairs`, `POST /affairs/{id}/answer` | Affaires entre deux matchs : celles en attente, et la réponse (effets révélés) |

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
un grand. Le club et le joueur ont un objectif secret et ouvrent au-dessus
(25 % pour le club, 30 % pour le joueur). À chaque offre refusée ils comblent la
moitié de l'écart avec ton offre, jusqu'à leur objectif ; arrivés là, ils
campent, sauf si ton offre s'en approche à moins de 10 % : ils coupent alors
la poire en deux (dernier effort). Chacun a 6 points de patience : un refus en
coûte 1, une offre qui n'a pas bougé ou une offre dérisoire (sous 60 % de
l'objectif) en coûte 2 ; à zéro, il ne veut plus discuter. Le joueur a aussi
une durée de contrat en tête selon son âge (3 à 5 saisons pour les jeunes,
1 à 2 pour les plus de 32 ans) : hors de cette fourchette, il ne discute même
pas le salaire. Et il a de la mémoire : s'il quitte la table, il refuse toute
discussion pendant 8 semaines, puis revient en ouvrant 10 % plus haut et avec
un point de patience en moins par rupture passée. Quitter la table soi-même
ferme la porte 2 semaines, sans rancune.

## Fins de contrat

Règles dans `engine/contracts.py`, routes dans `api/routers/contracts.py`.
Un contrat n'est plus renouvelé d'office : en dernière année, un joueur de ton
club (pro ou espoir) peut être prolongé au salaire qu'il demande (selon sa valeur
et son temps de jeu ; un vétéran accepte une baisse) et pour une durée qui
dépend de son âge. Sinon il part libre à l'intersaison et signe dans le club le
moins fourni. Pendant la phase retour, les concurrents signent des pré-contrats
avec tes joueurs en fin de contrat (les meilleurs de l'effectif sont les plus
convoités) : ceux-là sont perdus. Les clubs IA prolongent leurs propres joueurs.
L'intersaison est refusée si moins de 25 pros restent sous contrat.

Le bilan de fin de saison (`GET /seasons/current/review`, puis `GET /contracts`)
s'ouvre après la finale, en trois étapes : résultats, vie du club, contrats.

## Centre de formation

Chaque club a un effectif espoirs (16 à 21 ans) à côté des pros. Les espoirs
jouent leur propre championnat, mêmes affiches et mêmes jours que les pros
(saison régulière seulement, sans blessures). Un espoir peut être promu chez
les pros à tout moment (il signe un salaire de pro) ; un pro de 23 ans ou moins
peut redescendre chez les espoirs. À l'intersaison : tous les joueurs
progressent selon leur âge (2 à 4 points d'attributs jusqu'à 20 ans, 1 à 3
jusqu'à 23, puis moins, et un déclin à partir de 33 ans), avec un bonus du
centre de formation pour les espoirs et du centre d'entraînement pour les pros
(+1 point à partir du niveau 3, +2 au niveau 5) ; les espoirs de 22 ans non
promus quittent le centre (les clubs IA promeuvent les leurs s'ils ont de la
place) ; 2 jeunes de 16-17 ans entrent, plus un par niveau du centre. Règles
dans `backend/engine/offseason.py`.

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

## Affaires entre deux matchs

Tous les 2 ou 3 matchs, le club dirigé reçoit une affaire à régler :
conférence de presse, joueur mécontent, vestiaire, direction, supporters, médias
(une quarantaine de scénarios, tirés d'après les résultats, l'effectif et les
notes). Une question déjà posée ne revient pas de la saison. Chaque réponse fait bouger le moral, la cohésion, la fraîcheur, la
confiance de la direction ou la ferveur des supporters (de ±0,1 à ±3 sur 20 ;
une victoire vaut +1,3 de moral), parfois la trésorerie, et peut prolonger,
augmenter, vendre ou promouvoir un joueur. Les effets restent cachés jusqu'à la
réponse.

Certaines réponses sont des promesses, tranchées au match suivant : une
titularisation promise impose le joueur dans le XV, une victoire annoncée doit
arriver. Tenue ou non, la promesse revient sous forme d'une nouvelle affaire.
Une affaire restée sans réponse est réglée d'office avant la journée suivante,
avec une petite pénalité. Le catalogue est dans `backend/engine/affairs.py`.

## Principe d'architecture

Le moteur de simulation (`backend/engine/`) ne travaille que sur des objets
Python simples (`backend/models/domain.py`). Il ne connaît ni FastAPI ni la base
de données, ce qui permet de le tester et de l'utiliser seul (script CLI, tests).
La persistance SQLAlchemy (`backend/models/orm.py`) est une couche à part qui
convertit ses lignes en objets du domaine. Le frontend ne parle qu'à l'API.
