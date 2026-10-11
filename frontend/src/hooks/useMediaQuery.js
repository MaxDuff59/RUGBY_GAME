import { useEffect, useState } from "react";

// Seuil de la version mobile : en dessous, la navigation latérale laisse place à la
// barre d'onglets en bas de l'écran (même seuil que les règles `@media` de styles.css).
// 960 px : une fenêtre d'ordinateur réduite y passe aussi, la colonne de 232 px ne
// laissant plus assez de place au contenu.
export const PHONE_QUERY = "(max-width: 960px)";

// Vrai quand la fenêtre correspond à la requête média, et suit ses changements.
export function useMediaQuery(query) {
  const [matches, setMatches] = useState(() => window.matchMedia(query).matches);
  useEffect(() => {
    const list = window.matchMedia(query);
    const update = () => setMatches(list.matches);
    update();
    list.addEventListener("change", update);
    return () => list.removeEventListener("change", update);
  }, [query]);
  return matches;
}
