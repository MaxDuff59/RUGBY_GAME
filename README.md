# Rugby Manager (prototype)

Jeu de gestion de rugby à XV, dans l'esprit de Football Manager : on incarne
le manager d'un club et on le mène à travers les saisons. Interface web
dans `frontend/`.

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
uv run python -m scripts.run_season --league top14 --club 1          # les vrais clubs d'un championnat
uv run python -m scripts.run_season --league top14 --seasons 10 --seed 1   # dix saisons d'affilée
```

La simulation tourne sans base de données avec les règles du jeu (`engine/world.py`) :
forme, blessures, phases finales, argent, puis l'intersaison. Avec `--seasons`, un
tableau suit le niveau, l'âge et la taille des effectifs et la trésorerie des clubs,
saison après saison. La même graine (`--seed`) rejoue la même histoire.

### Vrais effectifs

```bash
uv run python -m scripts.fetch_rosters            # pros et espoirs de chaque club (Wikipédia)
uv run python -m scripts.fetch_rosters --missing  # seulement les clubs pas encore récupérés
uv run python -m scripts.fetch_rosters --club "Stade Toulousain"
```

Le résultat va dans `backend/data/rosters.json` (nom, poste, international, date de
naissance et photo via Wikidata). Une nouvelle partie le lit pour créer les joueurs des
vrais clubs ; un club absent du fichier, ou un poste vide, reçoit des joueurs inventés.
Les notes restent calculées par le jeu (niveau du club, international, âge). Les parties
déjà commencées gardent leurs joueurs.

### Blasons et couleurs des clubs et des sélections

```bash
uv run python -m scripts.fetch_club_logos          # blasons manquants (TheSportsDB) et couleurs
uv run python -m scripts.fetch_club_logos --force  # retélécharge tous les blasons
```

Les blasons vont dans `frontend/public/clubs/`, la table nom → blason et couleurs dans
`frontend/src/clubLogos.json`. Les couleurs se corrigent dans `COLORS`, en tête du script.
Les seize sélections nationales y sont aussi, sous leur nom français.

### Lancer l'API

```bash
uv run uvicorn api.main:app --reload
```

Puis ouvrir http://localhost:8000/docs pour tester les routes dans le navigateur.

Le jeu s'ouvre sur la connexion (`backend/accounts.py`, routes `/auth`) : un
compte par joueur, e-mail et mot de passe (scrypt), session par cookie. Les
comptes vivent dans `backend/saves/users.db`. Puis l'écran des parties : trois
emplacements par compte, chacun avec son propre monde dans
`backend/saves/u<compte>/partie-N.db` (`database.py` ; ou un schéma Postgres
par partie avec `RUGBY_DATABASE_URL`, voir « Mise en production »). « Nouvelle carrière »
crée le monde dans un emplacement libre, puis on choisit le championnat et le
club ; « Continuer » recharge une partie. Il n'y a pas de bouton
« Sauvegarder » : chaque action est enregistrée aussitôt dans le fichier de la
partie chargée. Les routes du jeu répondent 401 sans compte connecté et 409 tant
qu'aucune partie n'est chargée ; la partie chargée est retenue sur le compte,
d'un navigateur à l'autre.

Les photos des vrais joueurs (`GET /photos/{nom}`) viennent de Wikimedia
Commons mais passent par l'API : récupérées une fois, gardées dans
`backend/saves/photos/`, puis servies de là.

Une nouvelle partie est créée avec les 63 clubs de
cinq championnats (saison 2025-26 ; voir `backend/data/leagues.py`), leurs vrais
stades, et des joueurs (pros et espoirs) et un staff inventés à leur niveau :

| Championnat | Clubs | Saison régulière | Phases finales |
|---|---|---|---|
| Top 14 | 14 | 26 journées, septembre-avril | barrages 3-6 et 4-5, demies, finale sur terrain neutre |
| Pro D2 | 16 | 30 journées, dès fin août | même formule ; le champion monte en Top 14, le dernier du Top 14 descend |
| Premiership (Angleterre) | 10 | 18 journées | demies 1-4 et 2-3, finale sur terrain neutre |
| URC (Irlande, Écosse, Italie, Afrique du Sud) | 12 | 22 journées | quarts 1-8, 2-7, 3-6, 4-5, demies selon le tableau, finale chez le mieux classé |
| Super Rugby Pacific | 11 | 22 journées, de février à juillet | qualifications 1-6, 2-5, 3-4, demies avec le meilleur perdant repêché, finale chez le mieux classé |

Chaque championnat se joue en aller-retour avec son propre calendrier
(`engine/calendar.py`) : jouer la journée joue d'abord, date par date, les
matchs des autres championnats tombés avant (ou le même jour). Les objectifs de
la direction, l'affluence et le classement se comptent dans le championnat du
club. L'intersaison peut se lancer dès la fin du championnat du club dirigé :
les autres finissent d'abord leur saison, puis la montée et la descente
s'appliquent. Les plus grands stades (Afrique du Sud, Super Rugby) sont ramenés
à 35 000 places, le plus grand stade constructible. Quand le schéma de la base
change, une partie à l'ancien format est signalée sur l'écran des parties et
doit être supprimée (les colonnes ajoutées après coup, comme l'endurance des
joueurs, sont créées et remplies automatiquement par `database.py`). L'ancien
fichier unique `backend/rugby.db` ne sert plus. `RUGBY_SAVES_DIR` range les
parties ailleurs (ex. pour une instance de test).

| Route | Rôle |
|---|---|
| `GET /clubs`, `GET /clubs/{id}` | Clubs, effectif complet et notes collectives du XV |
| `PUT /clubs/{id}/captain` | Choisir le capitaine (`null` : le staff donne le brassard au meneur du XV) |
| `GET /clubs/{id}/notes` | Vie du club sur 20 (moral, cohésion, fraîcheur, confiance de la direction, ferveur des supporters) et forme du jour |
| `GET /career/dismissal` | Dernier limogeage, tant qu'aucune nouvelle carrière n'a commencé |
| `GET /players/{id}` | Fiche d'un joueur : comparaison à son poste, note à chaque poste, saison (statistiques comprises), blessures |
| `POST /career`, `GET /career` | Choisir son club, ou sa sélection (`nation`) ; tire aussi le calendrier de la 1re saison |
| `POST /auth/register`, `POST /auth/login`, `POST /auth/logout`, `GET /auth/me` | Compte : s'inscrire, se connecter (cookie de session), se déconnecter, qui suis-je |
| `GET /saves`, `POST /saves/{n}/load`, `POST /saves/{n}/new`, `DELETE /saves/{n}` | Parties sauvegardées du compte : lister, charger, créer un monde neuf, supprimer |
| `GET /photos/{nom}` | Photo d'un vrai joueur, depuis notre copie |
| `GET /leagues` | Les championnats et leur formule |
| `GET /seasons/current?league=` | Calendrier daté, classement, prochaine journée, phases finales (du championnat du club dirigé par défaut) |
| `POST /seasons/current/play` | Joue la journée suivante (matchs, billetterie, sponsors, salaires) |
| `POST /seasons/next` | Intersaison : âges, retraites, jeunes, nouveau calendrier |
| `GET /matches/{id}`, `POST /matches/simulate` | Détail d'un match joué (météo, statistiques de chaque joueur) ; match amical |
| `POST /live`, `GET /live` | Lancer (ou reprendre) le match du club dirigé en direct, minute par minute |
| `POST /live/advance`, `POST /live/tactics`, `POST /live/substitute` | Avancer le chrono ; changer la tactique ; faire un remplacement |
| `POST /live/finish` | Finir la journée avec ce match (le staff joue les minutes restantes) |
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
| `GET /internationals`, `GET /internationals/nations`, `GET /internationals/{fenêtre}/{nation}` | Calendrier international de la saison ; sélections à diriger ; liste d'une sélection |
| `GET /selection`, `POST /selection/advance` | Sélectionneur : où il en est ; jouer le prochain jour de match du monde |
| `GET /selection/pool`, `POST /selection/list`, `POST /selection/replace` | Joueurs sélectionnables ; annoncer la liste de 42 ; remplacer un blessé |
| `GET /selection/team`, `PUT` / `DELETE /selection/lineup` | Le groupe et son XV ; composer ; rendre la main au staff |
| `GET /journal` | Le journal du monde, pour toute carrière : articles, matchs de chaque compétition, mouvements de joueurs |

## Sélections nationales

Seize sélections (`backend/data/nations.py`) et trois fenêtres par saison, un match
par samedi comme les championnats :

| Fenêtre | Quand | Qui |
|---|---|---|
| Rugby Championship | 15 août – début octobre, 6 samedis | Nouvelle-Zélande, Afrique du Sud, Australie, Argentine, aller-retour |
| Tournées d'automne | mi-novembre, 3 samedis | les six nations du Tournoi reçoivent celles du Sud, les Fidji et la Géorgie (les adversaires tournent d'une saison à l'autre) |
| Tournoi des Six Nations | février-mars, 5 samedis | France, Angleterre, Irlande, Écosse, Galles, Italie ; qui reçoit s'inverse chaque saison |

**Coupe du monde.** Une saison sur quatre (2027, 2031...), elle remplace le Rugby
Championship et les tournées d'automne : seize nations, quatre poules de quatre (une
nation de chacun des quatre chapeaux, le tirage tourne d'une édition à l'autre), puis
quarts, demies et finale, sur terrain neutre, en six samedis à partir de la
mi-septembre. Un match à élimination directe ne finit pas sur un nul (prolongation,
tirs au but). Quatre nations n'ont pas d'autre rendez-vous (Japon, Samoa, Tonga,
Portugal) : on ne les dirige pas. Cette saison-là les clubs décalent leur calendrier
(`backend/engine/calendar.py`) : aucun match avant le dernier samedi des poules, et plus
de trêve en novembre. Le Top 14 démarre trois samedis plus tard et finit à la même
date ; ses quatre premières journées sont des doublons, de moins en moins lourds : fin
des poules (les seize listes), puis quarts, demies et finale (les sélections encore en
course seulement).

Un joueur garde la nationalité de sa fiche (`rosters.json`) ; un joueur inventé prend
celle du pays de son club, les jeunes du centre de formation aussi. Un monde de clubs
inventés n'a ni pays ni sélections. L'Angleterre, l'Irlande et la Nouvelle-Zélande ne
retiennent que les joueurs de leurs clubs. Une sélection à court de monde à un poste
(aucun club gallois dans le jeu, peu de piliers fidjiens...) appelle des joueurs
« hors championnats » : inventés, sans club dans le jeu et hors du marché.

**Listes.** Deux semaines avant le premier match d'une fenêtre, chaque sélection annonce
42 joueurs (6 piliers, 4 talonneurs, 5 deuxièmes lignes, 8 troisièmes lignes, 4 demis
de mêlée, 3 ouvreurs, 5 centres, 4 ailiers, 3 arrières quand c'est le staff qui
compose, sans les blessés).

**Doublons.** Le jour où sa sélection joue, un joueur de la liste manque à son club ;
les autres samedis de la fenêtre il lui est rendu, avec la fatigue de ses matchs (les
matchs internationaux comptent dans la fraîcheur). Le club complète sa feuille de match
avec ses meilleurs espoirs aux postes dégarnis. Avec les trêves actuelles, le Top 14
a un doublon en novembre et trois pendant le Tournoi, plus quatre en septembre-octobre
pour ses joueurs du Rugby Championship ; la Premiership, aux trêves plus longues, en a
moitié moins. Le manager
est prévenu à l'annonce des listes, la page Club signale le doublon du prochain match,
la page Effectif marque les absents, et le calendrier du club montre les samedis
internationaux et les doublons, journée par journée. Une titularisation promise à un joueur parti en
sélection attend son retour. Un blessé en sélection revient à son club avec sa blessure.

**Carrière de sélectionneur.** Au choix de la carrière, « Sélectionneur national » :
pas de club (les 63 sont menés par leur staff), quatre pages. Le monde avance un jour
de match à la fois ; il s'arrête tant que la liste due n'est pas annoncée, puis à
chaque match de la sélection, à simuler ou à jouer en direct avec le XV composé parmi
les 42. Une liste annoncée ne bouge plus, sauf pour remplacer un blessé. La saison
suivante se lance quand tous les championnats ont fini.

Règles dans `backend/engine/internationals.py` (calendrier, listes, doublons, matchs),
branchement en base dans `backend/api/internationals.py`. Les matchs internationaux
ont leur table (`internationals`), les listes aussi (`call_ups`), la carrière de
sélectionneur la sienne (`selectors`). Une partie d'avant les sélections s'ouvre
toujours : la nationalité des joueurs et le tour des matchs internationaux sont ajoutés
à l'ouverture, et sa saison en cours ne reçoit que les fenêtres pas encore commencées
(ni son calendrier de clubs, déjà tiré, le décalage d'une année de Coupe du monde). Le
niveau des sélections vient de celui de leurs joueurs, donc de leurs clubs ; le moteur
laisse beaucoup de place au hasard d'un match : sur 200 Coupes du monde simulées, les
cinq favoris la gagnent chacun entre 9 et 16 fois sur 100.

## Journal

Onglet « Journal », dans une carrière de club comme de sélectionneur : les nouvelles
du monde en un écran. Des articles (résultats de la dernière journée de chaque
championnat et de chaque fenêtre internationale, affiches à venir, point sur les
classements, transferts, joueurs à suivre sur le marché, blessures, listes des
sélections), les matchs joués et à venir de la compétition de son choix, et les
derniers mouvements de joueurs.

Rien n'est inventé ni tiré au hasard : chaque article part d'un fait du jeu, et le
même monde donne le même journal. Les titres, les brèves et leur poids (ce qui fait
la une) s'écrivent dans `backend/engine/journal.py` ; `backend/api/routers/journal.py`
lit les faits en base et ne garde, par compétition, que ce qui touche le joueur et
les articles les plus lourds. Ce qui concerne son club ou sa sélection passe devant ;
une nouvelle s'efface avec le temps, sauf pendant une trêve ou une intersaison.

Les mouvements de joueurs sont inscrits au moment où ils ont lieu dans la table
`moves` (`backend/api/moves.py`) : transferts, prêts, signatures d'agents libres et
jokers du club dirigé, puis à l'intersaison les pré-contrats exécutés, les fins de
contrat, les recrues des clubs IA et les retraites. Les parties commencées avant ce
registre le reçoivent vide (la table est créée à l'ouverture) : le journal y reprend
les arrivées déjà négociées, puis il se remplit au fil des semaines : les clubs IA
traitent entre eux toute la saison (voir « Le marché des clubs IA »).

## Jouer le match

Le match du club dirigé peut se jouer en direct (`engine/match_engine.py`,
classe `LiveMatch` ; routes dans `api/routers/live.py`). `POST /live` joue
d'abord la semaine d'entraînement de tous les clubs, puis fige le XV et le banc
(8 remplaçants : talonneur, 2 piliers, 2e ligne, 3e ligne, demi de mêlée,
ouvreur, un arrière) de chaque équipe ; l'état complet du moteur est sauvegardé
en base (`live_matches`) à chaque minute, donc le match reprend où on l'a laissé.
À tout moment on peut changer la **tactique** (plan de jeu au pied / équilibré /
à la main ; défense prudente / normale / agressive ; pénalités tentées au pied
ou jouées à la main) ou faire un **remplacement** (8 au plus, un sortant ne
revient pas). L'adversaire est géré par son staff : il adapte son plan de jeu à
ses forces et remplace ses joueurs usés entre la 50e et la 74e minute.

Ce que le moteur ajoute au match :

- l'**énergie** : chaque joueur commence entre 60 % (fraîcheur nulle) et 100 %
  (tout frais) et en perd à chaque minute selon son **endurance** (9e attribut,
  sur 20 : 1,4 % par minute à 4, 1 % à 12, 0,6 % à 20) ; son apport aux notes
  collectives va de 100 % de ses moyens (énergie pleine) à 60 % (vide), d'où
  l'intérêt des remplaçants frais et des joueurs increvables ; les faits de jeu
  pèsent dessus : à 14 ou 13 après un carton, ceux qui restent s'usent 25 % plus
  vite par joueur manquant (le puni, lui, souffle), et une défense agressive
  coûte 10 % d'énergie en plus ;
- les **cartons** : ~0,3 jaune (10 minutes à 14, 12 % de force en moins par
  joueur manquant) et ~0,03 rouge par équipe et par match, chaque carton donnant
  une pénalité à l'adversaire ; une défense agressive en prend plus ;
- les **blessés** sortent et sont remplacés d'office s'il reste un changement ;
- une **note sur 10** par joueur, qui part de 6 et bouge avec ses actions
  (essai +1, coup de pied réussi ou raté, carton −1 / −2) et la domination de sa
  ligne minute après minute.

`POST /live/finish` (ou « Simuler la journée ») joue ce qu'il reste par le staff
et termine la journée comme d'habitude : autres matchs, billetterie, salaires,
affaires. `simulate_match` (journées simulées, matchs amicaux) utilise le même
moteur, les deux bancs gérés par le staff.

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

### Le marché des clubs IA

Les clubs IA traitent aussi entre eux, chaque jour de match, avec les mêmes règles
(`backend/engine/market.py`, branché en base dans `backend/api/market.py`, appelé à
la fin de la journée dans `api/routers/seasons.py`). Le club dirigé n'en fait pas
partie : il recrute lui-même, et ses fins de contrat sont approchées à part.

| Voie | Quand | Qui |
|---|---|---|
| Pré-contrat | phase retour et phases finales de son championnat | un joueur en dernière année de contrat ; les meilleurs d'un effectif sont les plus convoités, deux fois moins souvent que ceux du club dirigé |
| Joker médical | saison régulière en cours | un club à court de joueurs valides à un poste, sur une blessure de plus de trois mois : le meilleur agent libre du poste |
| Prêt | saison régulière en cours | le même club, sans longue blessure : le meilleur réserviste qu'un autre club peut lâcher |
| Agent libre | saison régulière en cours | à défaut de prêt possible |

Un joueur approché choisit parmi ses trois meilleures offres : des clubs de son
championnat et quatre autres tirés au sort, où il serait au moins remplaçant, qui
n'augmentent pas son salaire de plus de 30 %, et qui n'ont pas déjà signé quatre
pré-contrats. Un international d'une fédération qui ne retient que les joueurs du
pays (Angleterre, Irlande, Nouvelle-Zélande) y reste. Un club est « à court » à un
poste quand il y compte moins de joueurs valides que ses titulaires plus une
doublure, un absent de plus d'un mois ne comptant pas ; il agit une semaine sur deux.
Il n'emprunte qu'un réserviste dont le club garde de quoi jouer (plus de 28 pros)
et qui serait au moins remplaçant chez lui, et ne signe un agent libre que s'il vaut
à peu près sa doublure ; l'un comme l'autre restent jusqu'à la fin de la saison.

Un pré-contrat entre clubs IA est une négociation signée comme celles du manager,
exécutée à l'intersaison. Sur le marché, le joueur porte alors « Déjà engagé » : on
ne peut plus ni l'acheter ni le signer, seulement l'emprunter jusqu'à la fin de la
saison. Un joueur en discussion avec le manager n'est pas approché. Tous ces
mouvements paraissent dans le Journal. Sur une saison à 63 clubs : une cinquantaine
de renforts et autant de pré-contrats.

## Fins de contrat

Règles dans `engine/contracts.py`, routes dans `api/routers/contracts.py`.
Un contrat n'est plus renouvelé d'office : en dernière année, un joueur de ton
club (pro ou espoir) peut être prolongé au salaire qu'il demande (selon sa valeur
et son temps de jeu ; un vétéran accepte une baisse) et pour une durée qui
dépend de son âge. Sinon il part libre à l'intersaison et signe dans le club le
moins fourni. Pendant la phase retour, les concurrents signent des pré-contrats
avec tes joueurs en fin de contrat (les meilleurs de l'effectif sont les plus
convoités) : ceux-là sont perdus. Les clubs IA prolongent leurs propres joueurs,
quand un autre club IA ne les a pas signés avant (voir « Le marché des clubs IA »).
L'intersaison est refusée si moins de 25 pros restent sous contrat.

Le bilan de fin de saison (`GET /seasons/current/review`, puis `GET /contracts`)
s'ouvre après la finale, en trois étapes : résultats, vie du club, contrats.
`GET /contracts` donne aussi les prochaines signatures du club (`signings` : accords en
attente de l'intersaison, négociations en cours) : la carte « Transferts » de la page
Club les montre sous les fins de contrat.

## Centre de formation

Chaque club a un effectif espoirs (16 à 21 ans) à côté des pros. Les espoirs
jouent le championnat espoirs de leur championnat, mêmes affiches et mêmes jours que les pros
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

## Mise en production

Deux services : l'API sur Railway (image Docker, `Dockerfile`), l'interface sur
Vercel (`frontend/vercel.json`). Vercel relaie `/api/*` vers l'API, comme Vite
en développement : le navigateur ne parle qu'au domaine Vercel, donc pas de
CORS ni de cookie inter-sites. Les parties, les comptes et les photos vivent
dans `/data` sur Railway, monté sur un volume persistant.

```bash
railway up --service rugby --ci     # l'API (projet rugby-manager, service rugby, volume /data)
cd frontend && vercel --prod        # l'interface (Root Directory : frontend)
```

Si le domaine Railway change, le reporter dans `frontend/vercel.json`.

### Données sur Postgres

Sans réglage, les parties sont des fichiers SQLite sur le disque de l'API. Avec
`RUGBY_DATABASE_URL`, tout va dans un serveur Postgres : les comptes et le
registre des parties dans le schéma `public`, et chaque partie dans son propre
schéma (`save_u<compte>_s<n>`) avec les mêmes tables qu'en SQLite. Le moteur et
les routes ne voient pas la différence (`database.py`). L'URL peut être celle
que donne l'hébergeur (`postgres://` ou `postgresql://`) : le pilote psycopg est
ajouté automatiquement.

En production, la base est le service Postgres du projet Railway, dans le même
centre de données que l'API : `RUGBY_DATABASE_URL=${{Postgres.DATABASE_URL}}`
(référence Railway, réseau privé). Une base distante marche aussi, par exemple
Supabase avec son **Session pooler** (joignable en IPv4), mais chaque journée
jouée fait quelques centaines de requêtes : à 15 ms d'aller-retour, c'est 6 s
par journée contre moins d'une seconde en local.

```
RUGBY_DATABASE_URL=postgresql://postgres.<ref>:<mot de passe>@aws-0-<région>.pooler.supabase.com:5432/postgres
```

Le disque de l'API ne garde alors que les photos (`RUGBY_SAVES_DIR/photos`), qui
se retéléchargent si on le perd. Les tests peuvent tourner sur un Postgres
jetable, vidé avant chaque cas :

```bash
RUGBY_TEST_DATABASE_URL=postgresql+psycopg://rugby@127.0.0.1:5499/rugby_test uv run pytest
```

Variables d'environnement de l'API :

| Variable | Rôle | Dans l'image |
|---|---|---|
| `RUGBY_DATABASE_URL` | Serveur Postgres pour les comptes et les parties (sinon SQLite par fichier) | — |
| `RUGBY_SAVES_DIR` | Dossier des parties SQLite, des comptes (sans Postgres) et des photos | `/data/saves` |
| `RUGBY_USERS_DB_URL` | Base des comptes à part (sinon celle des parties, ou `users.db` dans le dossier des parties) | — |
| `RUGBY_COOKIE_SECURE` | `1` derrière HTTPS (cookie de session marqué Secure) | `1` |
| `RUGBY_STATIC_DIR` | Optionnel : un `dist/` de Vite servi par l'API elle-même (`api.main:site`, tout sur un seul port) | — |
| `PORT` | Port d'écoute | `8000` |

En SQLite, une seule machine d'API à la fois (les parties sont des fichiers) ;
avec Postgres, plusieurs instances peuvent tourner. Pas de réinitialisation de
mot de passe (il faudrait un envoi d'e-mail).

## Principe d'architecture

Le moteur de simulation (`backend/engine/`) ne travaille que sur des objets
Python simples (`backend/models/domain.py`). Il ne connaît ni FastAPI ni la base
de données, ce qui permet de le tester et de l'utiliser seul (script CLI, tests).
La persistance SQLAlchemy (`backend/models/orm.py`) est une couche à part qui
convertit ses lignes en objets du domaine. Le frontend ne parle qu'à l'API.
