# Direction visuelle

Maquette validée : https://claude.ai/artifact/DfB5aRKnoPWwc7Wacqy9xs
(écrans « Club » et « Effectif »).

## Intention

Sobre et éditoriale, façon journal sportif : pas de personnages, pas de dégradés,
pas d'étoiles ni d'emoji. L'information d'abord, la typographie fait le style.

## Couleurs

| Rôle | Valeur |
|---|---|
| Fond de page | `#EDEDE8` |
| Surface (cartes, tableaux) | `#F7F7F4` |
| Texte principal | `#16181B` |
| Texte secondaire | `#5E6168` |
| Traits / séparateurs | `#D6D6D0`, `#E2E2DC` |
| Neutre (barres adverses, nul) | `#8A8D93`, `#A9ABB0` |
| Accent club (un seul usage fort : bouton principal, barre « nous ») | `#7A1F2B` |
| Terrain | `#2E4A38` |

- Un seul accent à la fois : la couleur du club choisi. Chaque club a une couleur
  primaire et une secondaire (`src/clubLogos.json` pour les vrais clubs, tirées du nom
  pour les inventés, `src/clubs.js`). L'accent (`--accent`) prend la première assez
  foncée pour un bouton à texte blanc (contraste 4,5:1), sinon la primaire foncée ;
  l'autre devient `--accent-2`, visible seulement dans le liseré sous l'en-tête.
  L'accent bordeaux `#7A1F2B` reste celui des écrans sans club (parties) ; au choix du
  club, l'interface prend ses couleurs dès qu'on le sélectionne, et chaque partie montre
  son bouton « Continuer » à la couleur de son club.
- Dans les pastilles de forme (V / N / D), victoire / nul / défaite se distinguent par
  la forme (plein noir, gris, contour). Dans la colonne « Résultat » de l'onglet Saison
  du calendrier, un simple rond de couleur : vert (`--win`), gris (`--draw`), rouge
  (`--loss`), avec le libellé en info-bulle.

## Typographie

- **Barlow Condensed** (500/600/700) : titres en capitales, scores, notes, numéros.
- **Instrument Sans** (400/500/600) : tout le reste.
- Libellés de section : 12 px, capitales, interlettrage 0.12em, couleur secondaire.
- Chiffres en `tabular-nums` dans les tableaux.

## Composants

- Blason (`ClubCrest`) : l'image du club téléchargée depuis TheSportsDB
  (`backend/scripts/fetch_club_logos.py`, dans `public/clubs/`) ; un blason blanc
  est posé sur une pastille ronde de la couleur du club ; sans blason (club inventé ou
  introuvable), un écusson à initiales aux couleurs du club. Partout où un club est
  nommé : en-tête, choix du club, parties, prochain match, rapport de force,
  classements, affiches, calendrier, match en direct, marché des transferts.
- Photo de joueur (`PlayerAvatar`) : ronde, cadrée sur le haut (le visage). La photo
  du vrai joueur quand Wikimedia Commons en a une (`player.photo`), sinon (joueur
  inventé, pas de photo, hors ligne) une silhouette grise sur fond clair. Devant le nom
  dans l'effectif, la formation, le médical et les transferts ; en grand (96 px) sur la
  fiche joueur.
- Navigation latérale (Club, Effectif, Match, Calendrier, Classement, Recrutement),
  élément actif à la couleur du club.
- Tout ce qui est sélectionné ou « à nous » prend la couleur du club (`--accent`, texte
  blanc) : onglet actif du menu, pastilles choisies (vues du calendrier, filtres), club
  choisi à l'écran de départ, ligne de notre club dans les classements, nos matchs dans
  le calendrier.
- En-tête : club + classement à gauche, prochain match + « Simuler » (contour)
  + « Jouer le match » (accent) à droite.
- Cartes : fond surface, bordure 1 px, rayon 10 px, pas d'ombre.
- Rapport de force : 5 lignes (conquête, paquet, attaque, défense, buteur), notes
  sur 20 issues directement du moteur (`TeamStrength`).
- Page Club (ordinateur) : une seule carte en tête, séparée par des filets : le prochain
  match, puis le rapport de force, puis la vie du club en discret à droite, les trois
  titres sur la même ligne. En dessous, sur toute la hauteur qui reste, trois cartes :
  classement (plus large), journal, transferts. Fenêtre étroite (≤ 1400 px) : rapport de
  force et vie du club gardent leurs chiffres seuls, sans barres. La dernière journée
  n'a plus sa carte sur ordinateur (elle garde son onglet sur téléphone).
- Journal de la page Club : un article à la fois parmi les quatre plus lourds, flèches
  et pastilles au pied de la carte ; carte assez haute, les autres titres sont listés
  sous l'article et y mènent d'un clic. « Tout le journal » ouvre la page Journal.
- Transferts de la page Club : nos fins de contrat (ce que le joueur demande pour
  prolonger, ou son départ déjà acté), puis les prochaines signatures (accords en
  attente de l'intersaison, négociations en cours). Deux zones dans la carte, chacune
  défile sous son titre ; les signatures gardent leur hauteur, jusqu'à la moitié.
- Classement de la page Club : toutes les équipes visibles sans défilement, quel que
  soit leur nombre. La taille du texte se calcule d'après la hauteur de la carte et le
  nombre de lignes (`.standings`, unités `cqh`), entre 9 et 16 px ; les noms de clubs
  se coupent plutôt que de passer à la ligne. Pas de note sous le tableau.
- Vie du club (page Club, à droite du rapport de force) : 5 lignes (moral, cohésion,
  fraîcheur, direction, supporters), chacune avec son libellé et son palier, une barre
  par match joué de la saison (gris, la dernière en accent, pointillé à la note de
  départ) et la note sur 20 à droite. L'objectif de la direction en tête de carte.
  Calculs dans `engine/` (`morale.py`, `cohesion.py`, `freshness.py`, `board.py`,
  `supporters.py`).
  Sous le seuil d'alerte, le palier de la direction devient « Poste menacé » en accent.
- Rapport de force : dernière ligne « Forme du jour », l'effet en % de moral, cohésion
  et fraîcheur sur les notes du match (détail au survol), sans barre.
- Limogeage : la page de choix du club s'ouvre sur « Limogé le … / Rebondis ailleurs »,
  le nom du manager prérempli et l'ancien club grisé.
- Bilan de fin de saison : grande fenêtre (`Modal`) qui s'ouvre après la finale (ou par
  « Bilan de la saison »), en trois étapes repérées par des pastilles : résultats (titre
  en capitales, chiffres clés, meilleurs marqueurs), vie du club (les lignes de la carte
  « Vie du club », plus début → fin de saison et paliers), contrats (pros et espoirs en
  fin de contrat : durée + « Prolonger », « Signé ailleurs », retraite, « Passer pro »).
  En pied : pros sous contrat la saison prochaine, en accent sous le minimum, et
  « Lancer la saison » (désactivé tant que l'effectif est insuffisant).
- Affaires entre deux matchs : fenêtre étroite (`Modal compact`) qui s'ouvre après
  la journée simulée. Catégorie et date en libellé, titre en capitales, la situation,
  puis une réponse par ligne. Après la réponse : la réaction (filet accent à gauche)
  et les effets, note par note (hausse en noir, baisse en gris). Tant qu'une affaire
  attend, le bouton « Simuler la journée » devient « 1 affaire à régler ».
- Simuler plusieurs journées : « Simuler la journée » est un bouton en deux parties
  (`SplitButton`), l'action à gauche, une flèche à droite. La flèche ouvre un menu
  « Simuler jusqu'à… » (bordure noire, pas d'ombre ; au-dessus du bouton si la place manque
  en bas) : une date à choisir, la fin de la phase aller, de la saison régulière, de la
  saison. Chaque choix ouvre la fenêtre de simulation (`Simulation`, `Modal compact`) :
  la date (champ, raccourcis en pastilles, ou clic sur une journée de la liste), la liste
  des journées à venir (celles d'après la date en retrait) et le sort des affaires (« Le
  staff tranche » par défaut, ou « M'arrêter »). Pendant la simulation : barre de progression
  en accent, la journée en cours sur fond gris, notre résultat à droite de chaque ligne
  jouée (pastille V / N / D, notre score d'abord), « Arrêter » finit la journée en cours.
  Le fond de la fenêtre est à peine assombri (`light`) : derrière, la page Club se met à
  jour à chaque journée (classement, vie du club, journal, transferts). À la fin : bilan,
  classement avant → après, blessés, signés ailleurs, sélections, affaires tranchées par
  le staff ; le bouton mène à l'affaire en attente ou au bilan de la saison s'il y en a.
- Staff : sous les étoiles de chaque titulaire et de chaque candidat, ce que le poste apporte
  (« +5 % conquête et paquet », « −4,5 pts de réussite au pied », « Sans effet » à 3 étoiles),
  en vert (victoire) quand il aide, en rouge quand il coûte ; un poste vacant affiche aussi son manque.
- Infrastructures : chaque carte a un bouton « Voir » qui ouvre une grande fenêtre
  (`Modal`) : à gauche la scène 3D (`Scene3D.jsx`, transformations CSS, pas de
  bibliothèque ; on glisse pour tourner, « Recentrer » remet la vue), à droite le panneau.
  Le stade (`StadiumView`) : terrain, quatre tribunes en béton clair dont la profondeur,
  la hauteur et le nombre de gradins suivent la capacité (toit à partir de 16 000 places,
  angles fermés à partir de 25 000). Une tribune cliquée se teinte et se borde en accent ;
  le panneau montre ses emplacements (pleins : bordure noire, libres : pointillés) puis le
  catalogue (panneau sponsor, buvette, boutique, loges, écran géant) avec effet, coût et
  « Installer ». Dans la scène : panneaux en accent au bord du terrain, buvettes et
  boutique derrière la tribune, loges en bandeau sombre, écran noir au sommet. Les centres
  (`CampusView`) : les installations apparaissent niveau par niveau, et le panneau les
  liste avec « Améliorer ».
- Maillots (carte sous les infrastructures) : les trois tenues côte à côte, domicile,
  extérieur et third, chacune de face et de dos à plat (`JerseyFlat`) avec son motif et
  « Personnaliser ». Par défaut, domicile uni dans la première couleur du club, extérieur
  dans la seconde, third sur fond neutre (noir, ou blanc si le club joue en sombre) avec
  le col aux couleurs du club. Le third est verrouillé au départ : maillot en filigrane,
  prix, bouton « Déverrouiller » (accent) qui passe par la fenêtre de confirmation
  (`THIRD_KIT_COST`, `engine/economy.py`, opération « Maillot third » dans les finances).
  Sous les tenues, la ligne « Sponsors » : les logos en place avec leur emplacement, le
  total par match et l'effet sur la ferveur.
  « Personnaliser » ouvre l'éditeur (`JerseyEditor`, même fenêtre que « Voir », titre
  « Maillot domicile / extérieur / third ») : à gauche le maillot en 3D (`JerseyStudio`, three.js chargé seulement
  à l'ouverture ; on glisse pour tourner, « Face » / « Dos »), à droite les neuf motifs en
  vignettes, les couleurs (Fond, Motif, Col : une pastille par pièce, puis une palette
  commune — couleurs du club d'abord — et « + » pour une couleur libre) et les sponsors :
  quatre emplacements (poitrine ×1, dos ×0,6, manche ×0,4, ventre ×0,5 du budget),
  trois logos au plus, « Choisir » ouvre la bibliothèque (`engine/sponsors.py` : seize
  marques inventées, logo dessiné par `src/sponsors.js` — forme, pictogramme, nom — en
  vignette sur fond clair, en patch sur fond plein sur le maillot ; chaque ligne est le
  bouton de choix, avec secteur, image — Mal vu… Adoré — et gain par match). Sous la liste :
  total par match et effet sur la ferveur des supporters (image des marques, malus
  « sapin de Noël » à trois logos), qui règle l'affluence. Les sponsors sont les mêmes
  sur les trois tenues et paient à chaque match (ligne « Sponsors du maillot » dans les
  finances). Blason sur le cœur, numéro 10 dans le dos. Les motifs se
  dessinent dans `src/jersey.js` sur un canevas déroulé (devant, puis dos), qui sert de
  texture en 3D et d'image à plat. Gratuit ; « Couleurs du club » revient au maillot uni.
  En 3D : torse à plis, manches rapportées, col côtelé à encolure ouverte, patte de
  boutonnage à deux boutons (couleur du col), coutures et ourlet ; tissu en maille
  (relief procédural, voile textile léger), impressions plus brillantes que le tissu ;
  lumière d'une pièce virtuelle plus une lampe (ombre des manches sur le torse), halo
  d'ombre au sol, tone mapping Neutral pour garder les couleurs exactes.
- Match en direct (page `/match`, ouverte par « Jouer le match » ; pas d'entrée dans le menu) :
  en haut le tableau d'affichage (une carte) : nom de chaque club en capitales (le nôtre en
  accent) et ses essais, score en très grand, au centre le chrono `MM:SS` dont les secondes
  défilent entre deux minutes de jeu, la période (1re mi-temps, mi-temps, prolongation…),
  puis les commandes : « Coup d'envoi / Pause / Reprendre » (accent), vitesse ×1 à ×8 en
  pastilles, « Terminer » (le staff finit le match). Le match se met de lui-même en pause à
  la mi-temps et sur une blessure ou un carton de notre équipe (motif affiché sous les
  commandes). Juste sous le tableau, une rangée : « Plan de jeu » (le plan en cours en
  résumé) et « Discours » (le moment : vestiaire avant le coup d'envoi, vestiaire à la pause,
  bord du terrain, ou la minute où l'on pourra reparler) — chacun met le match en pause et
  ouvre sa fenêtre ; au vestiaire, le bouton Discours porte un liseré accent. À droite, l'élan
  donné par les discours (« +6 % », en rouge s'il est négatif) et l'humeur du groupe
  (nerveuse, survoltée, sereine). La fenêtre Plan de jeu montre les trois curseurs en
  pastilles, avec l'effet du choix en cours dessous ; la fenêtre Discours liste les discours
  du moment (libellé, ce que fait le manager, chances en mots : « Bonnes chances · sans
  risque », en accent quand c'est quitte ou double), puis l'issue (Ça porte en vert, Sans
  effet, Ça se retourne en rouge) avec une phrase et l'effet sur l'élan.
  En dessous, deux colonnes, domicile à gauche, extérieur à droite : les faits de
  jeu de chaque équipe (les plus récents en haut ; minute, repère — rond accent pour un
  essai, noir pour un coup de pied réussi, contour pour un raté, carton jaune ou rouge —,
  libellé, joueur, puis les points marqués à sa suite), puis sa composition : les 15 places dans l'ordre des numéros
  avec le joueur qui l'occupe, son poste, son énergie (barre verticale qui se vide au fil
  du match, noire, en accent sous 30 %, grise pour un joueur hors du terrain, le pourcentage
  à côté) et sa note sur 10 (gras à partir de 7,5), puis le banc (sortis en gris avec la minute). Notre carte accepte les remplacements en pause : on
  clique un joueur du terrain, puis « Faire entrer » sur un remplaçant. Les deux rangées
  défilent dans leur carte ; la page tient dans l'écran.
- Météo (`WeatherIcon`) : pictogramme au trait dans la couleur du texte (soleil, nuage et
  pluie, rafales, thermomètre), libellé et effet en info-bulle. Sous le score de chaque
  affiche (`MatchList`, la prévision pour un match à venir), dans la colonne « Météo » de
  l'onglet Saison du calendrier, sous la date dans le tableau d'affichage du match en direct.
- Public : « 17 715 spectateurs · Chaudron » (paliers : Stade clairsemé, Tiède, Bonne
  ambiance, Bouillant, Chaudron), l'effet sur le match en info-bulle. Dans le tableau
  d'affichage du match en direct, à la suite de la météo ; dans la fiche d'un match, sous
  la météo, avec l'avantage du terrain (« ×1,3 »). Rien sur terrain neutre.
  En direct, l'ambiance suit le score, et une ligne en capitales sous la météo dit ce
  que fait le stade (« Le stade s'enflamme · Section Paloise », pousse, s'éteint, se
  tait) : noir, en accent quand c'est notre public qui pousse, gris quand il s'éteint.
- Fiche d'un match joué (`MatchReport`, grande fenêtre) : un score se clique dans les
  affiches et dans l'onglet Saison (pas pour les matchs internationaux). En tête la
  journée et la date, les deux clubs en capitales (blasons côté score, le nôtre en
  accent), le score en très grand, le temps qu'il faisait. Deux pastilles : « Le match » —
  à gauche les statistiques face à face (essais, pénalités, ballons portés, franchissements,
  plaquages réussis et manqués, ballons grattés, touches, cartons : les deux chiffres, le
  meilleur en noir, et une barre partagée, la nôtre en accent, sinon noir contre gris), à
  droite l'homme du match (meilleure note) et les faits de jeu ; « Les joueurs » — une
  pastille par équipe, puis le tableau triable (numéro, minutes, note, sept statistiques ;
  « R » pour un remplaçant). Les deux zones défilent dans la fenêtre.
- Capitaine : un « C » cerclé après le nom (effectif, compositions du match en direct, en
  accent dans notre XV) et « (C) » sur le terrain de l'effectif. Liste déroulante
  « Capitaine » sous la phrase de composition : « Choix du staff · nom », puis les pros du
  plus grand au plus petit meneur (sur 20). Le meneur a aussi sa barre dans les notes du
  moteur de la fiche joueur.
- Suspension : étiquette rouge « Suspendu 2 matchs » après le nom (effectif, fiche
  joueur) ; un suspendu ne s'aligne pas et n'apparaît pas dans le choix d'une place.
  Le journal la publie sous la rubrique « Discipline », filtre « Absences » (avec les
  blessures).
- Match en direct : la pastille « Statistiques » de chaque composition remplace la
  colonne d'énergie par ballons portés, plaquages, plaquages manqués et franchissements.
  La fenêtre Plan de jeu propose trois choix de pénalité : au pied, en touche, jouées.
- Fiche joueur, carte « Notes du moteur » : la saison en trois colonnes (matchs,
  minutes, note moyenne, essais, points, puis les statistiques relevées à chaque match).
- Progression : colonnes « Pot. » (potentiel estimé, une fourchette « 14-16 » plus
  étroite pour nos joueurs que pour les autres) et « Prog. » (points d'attributs gagnés
  cette saison, « +3 ») dans l'effectif et au centre de formation ; sur la fiche joueur,
  « potentiel estimé » parmi les chiffres de l'en-tête, « Progrès » dans sa saison.
- Entraînement (page `/entrainement`, entrée du menu sous Effectif ; volet « Plus » sur
  téléphone) : à gauche, le rythme de la semaine en trois cartes (Légère, Normale,
  Intense : progression, fraîcheur, blessures, l'effet en vert quand il aide, en rouge
  quand il coûte) puis le thème en six cartes (attributs travaillés, effet sur le match
  suivant) ; la carte retenue est bordée et titrée en accent. À droite, « Qui progresse » :
  pros et espoirs, potentiel estimé et progrès de la saison, les plus grands progrès d'abord.
- Tableau d'effectif : 9 attributs (dont l'endurance, qui règle la barre d'énergie en match),
  gras à partir de 15, gris à 8 et moins.
- Boutons et liens cliquables : 44 px de haut minimum.
- Fiche joueur (page entière, depuis une ligne de l'effectif) : radar des 9 attributs
  en accent ; sous lui, un essaim par métrique clé du poste (`KEY_ATTRIBUTES`) : lui en
  accent, ses coéquipiers en noir, les autres joueurs du poste en gris, et son percentile ;
  terrain avec sa note à chaque place, son poste naturel en accent.

- Sélections nationales : chacune a son blason, téléchargé comme ceux des clubs
  (`fetch_club_logos.py`, rangé dans `public/clubs/` et `clubLogos.json` sous son nom
  français, avec ses deux couleurs) ; un blason blanc (la fougère néo-zélandaise) est posé
  sur une pastille sombre. L'interface prend les couleurs de la sélection pour un
  sélectionneur, comme pour un club.
- Choix de la carrière : deux pastilles sous le nom, « Manager d'un club » et
  « Sélectionneur national » (absentes dans un monde sans sélections). Les sélections se
  choisissent comme les clubs : nom, niveau du XV, rendez-vous de la saison en petit.
- Carrière de sélectionneur : quatre entrées dans la barre du téléphone (Sélection,
  Liste, Le XV, Calendrier), plus le Journal (dans le menu ; volet « Plus » sur téléphone).
  - Sélection (accueil) : même charpente que la page Club. L'affiche dit ce qui attend
    le sélectionneur : « Annonce ta liste » (bouton vers la liste), l'adversaire du jour
    (« Simuler le match » en contour, « Jouer le match » en accent), ou le prochain
    rendez-vous avec « Avancer jusqu'au prochain rendez-vous », qui enchaîne les jours
    de match et affiche la date en cours, « Arrêter » à la place du bouton. À sa droite,
    « Le groupe » : bilan, rendez-vous, état de la liste. En dessous, trois cartes : la
    fenêtre internationale (`WindowBoard` : classement d'un tournoi, puis les matchs
    jour par jour, liste déroulante pour changer de fenêtre), « Notre saison » (nos
    matchs, résultat en rond de couleur) et le dernier jour joué avec les blessés du groupe.
  - Liste : titre, compteur « 38 / 42 » en accent tant que le compte n'y est pas, puis
    « Proposition du staff », « Tout retirer » et « Annoncer la liste » (accent, avec
    fenêtre de confirmation). Une pastille par poste avec joueurs cochés / nombre que
    retient le staff, en accent sous le minimum ; « Dans la liste » et une recherche.
    Le tableau reprend celui de l'effectif (case à cocher, club, note, note au poste,
    titularisations, 9 attributs) ; les joueurs non cochés en gris. On coche en touchant
    la ligne, le nom ouvre la fiche. Le brouillon survit à un aller-retour sur une fiche.
    Une fois annoncée : lecture seule, « Forfait » à côté d'un blessé pour le remplacer.
  - Le XV : la page Effectif, avec le club du joueur à la place de valeur, salaire et contrat.
  - Calendrier : une pastille par fenêtre ; à gauche ses matchs (et son classement), à
    droite la liste de 42 d'une sélection au choix.
- Coupe du monde (`WindowBoard`) : le tableau final en tête, le tour le plus avancé
  d'abord (finale, demies, quarts), puis un classement par poule avec un filet sous les
  deux qualifiés, puis les matchs de poule. Sur terrain neutre : « Terrain neutre » à la
  place de domicile / extérieur.
- Calendrier du club et sélections : la colonne « Sélections » de l'onglet Saison porte,
  sur une journée jouée un samedi international, l'étiquette « Doublon » (contour), la
  fenêtre et le nombre de nos absents une fois les listes annoncées (leurs noms en
  info-bulle), sinon le libellé du jour (« Journée 2 », « Quarts de finale »). Les samedis
  où seules les sélections jouent s'intercalent en gris : « Pas de match de championnat ».
  Onglet Mois : sous le match du club, une case à contour avec la fenêtre (et « Doublon »
  si nous jouons). Onglet Semaine : une ligne « Doublon » en tête de la journée avec les
  noms des absents, puis les matchs internationaux de la semaine dans leur propre carte.
- Carrière de club : entrée « Sélections » dans le menu (volet « Plus » sur téléphone),
  même page que le calendrier du sélectionneur, nos joueurs en gras dans les listes.
  Sous l'affiche du prochain match, une ligne « Doublon » (étiquette contour) : combien
  de joueurs en sélection, leurs noms, lien vers le XV ; pas de carte en plus. Dans
  l'effectif, après le nom : code de la sélection (étiquette grise) pour un joueur de la
  liste, « En sélection » (contour) s'il manque le prochain match, « Espoir » pour un
  jeune monté le temps du doublon. À l'annonce des listes, la carte « Journée simulée »
  s'ouvre sur nos retenus, sélection par sélection, et les dates de doublon.
- Fiche joueur : nationalité après l'âge ; « Hors championnats » pour un joueur
  sélectionnable sans club dans le jeu.
- Journal (page `/journal`, entrée « Journal » sous l'accueil dans les deux carrières ;
  volet « Plus » sur téléphone) : la une d'un journal sportif, sans image. Titre de page
  et date d'édition, puis sept rubriques en pastilles (À la une, Mon club ou Ma sélection,
  Résultats, À venir, Transferts, Infirmerie, Sélections) qui filtrent les articles.
  Une grille qui tient dans l'écran : la une sur deux colonnes (rubrique en libellé,
  étiquette « À la une » en accent, grand titre en capitales dont la taille suit la
  largeur de la carte, brève, illustration à droite derrière un filet), des articles en
  cartes autour d'elle (illustration en tête, titre, brève, date), « Le fil » (toutes les
  autres brèves, les plus lourdes d'abord, blason ou photo devant), puis deux cartes l'une
  sous l'autre : « Matchs » (liste déroulante de la compétition, pastilles Résultats /
  À venir, affiches en `MatchList`) et « Transferts » (derniers mouvements, puis « À
  suivre sur le marché » : fins de contrat et agents libres, avec leur note). Cinq
  colonnes à partir de 1700 px (cinq articles autour de la une, dont deux brèves
  empilées), quatre à partir de 1280 px (deux articles), deux en dessous (aucun : tout
  passe dans le fil). Illustrations : feuille de score d'un match (une ligne par équipe,
  blason, nom en capitales, score à droite, le battu en gris ; avant le match, le jour à
  la place du score), portrait du joueur avec le blason de son club, trajet d'un
  mouvement (blason de départ, flèche, blason d'arrivée, un rond en pointillé pour « sans
  club », l'indemnité ou la nature dessous), ou blasons seuls. Ce qui touche notre équipe
  porte un point de la couleur du club devant sa rubrique, et son nom en accent dans les
  transferts. Un titre mène à la fiche du joueur quand l'article en a un. Les cartes
  d'article sont des conteneurs de taille (`@container`) : quand la hauteur manque, la
  brève raccourcit, puis disparaît, puis l'illustration ; une grande carte grossit son
  texte. Les cartes à en-tête fixe (`.panel`) défilent dans leur corps.
  Sur téléphone : les rubriques défilent sur une ligne ; la une, deux articles, puis le
  fil. La carte des matchs n'apparaît que sous « Résultats » et « À venir » (la rubrique
  choisit ce qu'elle montre), celle des transferts sous « Transferts ».

## Hauteur d'écran

- Aucune page ne dépasse 100 % de la hauteur de la fenêtre : jamais de défilement
  de la page vers le bas.
- Ce qui ne tient pas (listing de l'effectif, calendrier, opérations financières…)
  défile **à l'intérieur de sa carte**, dont la hauteur est bornée par celle de la fenêtre.
  Exception : le classement de la page Club réduit ses lignes pour tout montrer.
- L'en-tête, la navigation et le titre de page restent toujours visibles.
- Mise en œuvre (`styles.css`, section « Structure ») : `.app` est une grille à la
  hauteur de la fenêtre, `.main` une colonne flex sans débordement. Dans chaque page,
  le bloc qui absorbe la hauteur restante porte la classe `fill` (section, `club-grid`,
  `two-col` ou carte) ; sa carte reçoit `overflow: auto` et les en-têtes de tableau
  restent collés en haut. Deux blocs `fill` se partagent la place ; `fill--main` en
  donne deux tiers à l'un.
- Sur téléphone (voir « Version mobile »), le cadre reste à la hauteur de l'écran mais
  le contenu principal défile sous l'en-tête ; les cartes `fill` sont bornées à 70 % de
  la hauteur de l'écran et défilent dedans.

## Version mobile

- Seuil : 960 px de large ou moins (`PHONE_QUERY`, `src/hooks/useMediaQuery.js`, le
  même que les règles `@media` « téléphone » de `styles.css`). Une fenêtre d'ordinateur
  réduite y passe donc aussi : avec la colonne de 232 px, le contenu n'a plus la place
  en dessous. `Layout` pose alors `.app--phone`.
- Plus de colonne de navigation ni de marque « XV Rugby Manager » : l'en-tête compact
  (blason 40 px, nom du club, championnat, liseré) reste collé en haut, le contenu
  défile dessous.
- Barre d'onglets en bas de l'écran (`.tabbar`, hauteur `--tabbar-h`, zone sûre du
  téléphone comprise) : cinq onglets, pictogramme au trait (`NavIcon`) et libellé en
  capitales de 10 px. Club, Calendrier, Effectif, Transferts (`primary` dans
  `NAV_ITEMS`), puis « Plus ». L'onglet actif : pastille de la couleur du club derrière
  le pictogramme, libellé en accent.
- « Plus » ouvre un volet (`.sheet`) posé sur la barre, le reste de l'écran assombri :
  les autres pages en vignettes (Journal, Médical, Formation, Staff, Infrastructures, Finances ;
  la page courante en accent), puis manager, numéro de partie et « Quitter la partie ».
  Il se ferme au changement de page, par Échap ou en touchant le fond ; « Plus » reste
  marqué actif tant que l'on est sur l'une de ses pages.
- Titres de page et affiches (`.title`, `.hero__title`) à 40 px.
- Match en direct sur téléphone : le tableau d'affichage inchangé ; puis une seule carte
  de faits de jeu pour les deux équipes, dans l'ordre du match, ceux du club à domicile
  calés à gauche et ceux de l'extérieur à droite (minute et repère vers le bord), une
  dizaine de lignes visibles, la liste calée sur les derniers et l'on remonte pour les
  précédents ; puis deux pastilles centrées (blason + « Notre XV » / nom de l'adversaire)
  qui choisissent la composition affichée, la nôtre par défaut.
- Situation d'un joueur (`StatusBadge`, sur le marché et dans l'effectif, ordinateur et
  téléphone) : pastille à pictogramme au trait, fond teinté à 12 %, libellé court.
  Libre (cadenas ouvert, vert), fin de contrat (sablier, accent), transfert et son
  indemnité (flèche de sortie, noir), prêt (aller-retour, bleu), réserviste (banc, gris),
  ne discute plus (bulle barrée, rouge), intransférable (cadenas fermé, gris), joker
  médical (croix, accent). « Déjà engagé » (cadenas fermé, gris) : il a signé un
  pré-contrat avec un autre club, seul un prêt reste possible.
- Transferts sur téléphone : sans le paragraphe d'introduction, les trois chiffres en
  ligne, puis deux pastilles « Recruter » / « Vendre ». Recruter : négociations et joker
  s'il y en a, puis le marché avec un tri (liste déroulante), les voies en pastilles
  qui défilent sur une ligne, poste et championnat en deux listes déroulantes, et les
  joueurs en liste (`.market-list`) : photo, nom, poste · âge · club, puis ses pastilles de
  situation, note et valeur à droite ; on touche la ligne pour approcher. Trente joueurs
  à la fois, « Voir 30 joueurs de plus ». Vendre : l'effectif dans la même liste, valeur
  et bouton « Vendre » à droite.
- Page Club sur téléphone : quatre pastilles en tête. « Club » : le prochain match et le
  classement seulement. « Vie du club », « Dernière journée » et « Rapport de force » :
  chacune sa carte, seule dans son onglet (avec un mot si rien à montrer : aucune journée
  jouée, club qui ne joue pas).
