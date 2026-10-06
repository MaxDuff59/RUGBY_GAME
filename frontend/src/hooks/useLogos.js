import { useEffect, useState } from "react";

import { loadLogos } from "../sponsors.js";

// Les images des logos de ces sponsors (Map id → Image), une fois chargées ; une Map
// vide en attendant. `sponsors` : la bibliothèque de l'API.
export function useLogos(sponsors) {
  const [images, setImages] = useState(() => new Map());
  const key = sponsors.map((s) => s.id).join(",");
  useEffect(() => {
    let cancelled = false;
    if (!sponsors.length) return undefined;
    loadLogos(sponsors).then((loaded) => !cancelled && setImages(loaded));
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key]);
  return images;
}
