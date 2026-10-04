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
- Tableau d'effectif : 8 attributs, gras à partir de 15, gris à 8 et moins.
- Boutons et liens cliquables : 44 px de haut minimum.
