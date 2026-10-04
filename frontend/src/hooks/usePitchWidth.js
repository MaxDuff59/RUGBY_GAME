import { useLayoutEffect, useState } from "react";

import { PITCH_RATIO } from "../lineup.js";

// Largeur à donner au terrain (élément `.pitch`) pour qu'il remplisse la hauteur
// restante de son conteneur (colonne flex), proportions conservées. `ready`
// relance la mesure quand le conteneur apparaît. Null sur téléphone : le
// terrain garde alors la largeur de la page.
export function usePitchWidth(ref, ready = true) {
  const [width, setWidth] = useState(null);
  useLayoutEffect(() => {
    const container = ref.current;
    if (!ready || !container) return undefined;
    const measure = () => {
      if (window.matchMedia("(max-width: 720px)").matches) {
        setWidth(null);
        return;
      }
      const style = getComputedStyle(container);
      const gap = parseFloat(style.rowGap) || 0;
      const children = [...container.children];
      const others = children.filter((child) => !child.classList.contains("pitch"));
      const taken =
        parseFloat(style.paddingTop) +
        parseFloat(style.paddingBottom) +
        others.reduce((sum, child) => sum + child.getBoundingClientRect().height, 0) +
        gap * (children.length - 1);
      const available = container.clientHeight - taken;
      setWidth(Math.max(200, Math.floor(available * PITCH_RATIO)));
    };
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(container);
    return () => observer.disconnect();
  }, [ref, ready]);
  return width;
}
