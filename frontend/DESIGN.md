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

- Un seul accent à la fois ; il deviendra la couleur du club choisi.
- Victoire / nul / défaite se distinguent par la forme (plein noir, gris, contour),
  pas par le rouge et le vert.

## Typographie

- **Barlow Condensed** (500/600/700) : titres en capitales, scores, notes, numéros.
- **Instrument Sans** (400/500/600) : tout le reste.
- Libellés de section : 12 px, capitales, interlettrage 0.12em, couleur secondaire.
- Chiffres en `tabular-nums` dans les tableaux.

## Composants

- Navigation latérale (Club, Effectif, Match, Calendrier, Classement, Recrutement),
  élément actif sur fond noir.
- En-tête : club + classement à gauche, prochain match + « Simuler » (contour)
  + « Jouer le match » (accent) à droite.
- Cartes : fond surface, bordure 1 px, rayon 10 px, pas d'ombre.
- Rapport de force : 5 lignes (conquête, paquet, attaque, défense, buteur), notes
  sur 20 issues directement du moteur (`TeamStrength`).
- Vie du club (page Club, à droite du prochain match) : 5 lignes (moral, cohésion,
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
- Match en direct (page `/match`, ouverte par « Jouer le match » ; pas d'entrée dans le menu) :
  en haut le tableau d'affichage (une carte) : nom de chaque club en capitales (le nôtre en
  accent) et ses essais, score en très grand, au centre le chrono `MM:SS` dont les secondes
  défilent entre deux minutes de jeu, la période (1re mi-temps, mi-temps, prolongation…),
  puis les commandes : « Coup d'envoi / Pause / Reprendre » (accent), vitesse ×1 à ×8 en
  pastilles, « Terminer » (le staff finit le match). Le match se met de lui-même en pause à
  la mi-temps et sur une blessure ou un carton de notre équipe (motif affiché sous les
  commandes). En dessous, deux colonnes, domicile à gauche, extérieur à droite : les faits de
  jeu de chaque équipe (les plus récents en haut ; minute, repère — rond accent pour un
  essai, noir pour un coup de pied réussi, contour pour un raté, carton jaune ou rouge —,
  libellé, joueur, points), puis sa composition : les 15 places dans l'ordre des numéros
  avec le joueur qui l'occupe, son poste, son énergie (barre verticale qui se vide au fil
  du match, noire, en accent sous 30 %, grise pour un joueur hors du terrain, le pourcentage
  à côté) et sa note sur 10 (gras à partir de 7,5), puis le banc (sortis en gris avec la minute). Notre carte porte en tête trois listes déroulantes
  de tactique (plan de jeu, défense, pénalités) et accepte les remplacements en pause : on
  clique un joueur du terrain, puis « Faire entrer » sur un remplaçant. Les deux rangées
  défilent dans leur carte ; la page tient dans l'écran.
- Tableau d'effectif : 8 attributs, gras à partir de 15, gris à 8 et moins.
- Boutons et liens cliquables : 44 px de haut minimum.
- Fiche joueur (page entière, depuis une ligne de l'effectif) : radar des 8 attributs
  en accent ; sous lui, un essaim par métrique clé du poste (`KEY_ATTRIBUTES`) : lui en
  accent, ses coéquipiers en noir, les autres joueurs du poste en gris, et son percentile ;
  terrain avec sa note à chaque place, son poste naturel en accent.

## Hauteur d'écran

- Aucune page ne dépasse 100 % de la hauteur de la fenêtre : jamais de défilement
  de la page vers le bas.
- Ce qui ne tient pas (listing de l'effectif, calendrier, opérations financières…)
  défile **à l'intérieur de sa carte**, dont la hauteur est bornée par celle de la fenêtre.
- L'en-tête, la navigation et le titre de page restent toujours visibles.
- Mise en œuvre (`styles.css`, section « Structure ») : `.app` est une grille à la
  hauteur de la fenêtre, `.main` une colonne flex sans débordement. Dans chaque page,
  le bloc qui absorbe la hauteur restante porte la classe `fill` (section, `club-grid`,
  `two-col` ou carte) ; sa carte reçoit `overflow: auto` et les en-têtes de tableau
  restent collés en haut. Deux blocs `fill` se partagent la place ; `fill--main` en
  donne deux tiers à l'un.
- Sur téléphone (≤ 720 px), le cadre reste à la hauteur de l'écran mais le contenu
  principal défile sous la navigation.
