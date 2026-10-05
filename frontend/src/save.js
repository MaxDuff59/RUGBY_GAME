// Partie choisie dans cet onglet. Le serveur retient la partie chargée ; ce
// repère-ci fait passer par l'écran des parties à chaque ouverture du jeu.
const KEY = "rugby.slot";

export function chosenSlot() {
  try {
    return sessionStorage.getItem(KEY);
  } catch {
    return null;
  }
}

export function chooseSlot(slot) {
  try {
    sessionStorage.setItem(KEY, String(slot));
  } catch {
    // Stockage indisponible : on repassera par l'écran des parties.
  }
}

// Quitter la partie : l'onglet repasse par l'écran des parties. Rien à enregistrer,
// chaque action l'a déjà été ; le serveur la garde comme « dernière jouée ».
export function leaveSlot() {
  try {
    sessionStorage.removeItem(KEY);
  } catch {
    // Stockage indisponible : il n'y avait rien de retenu.
  }
}
