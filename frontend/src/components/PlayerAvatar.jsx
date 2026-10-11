import { useState } from "react";

import { BASE_URL } from "../api.js";

// Photo de profil d'un joueur : celle du vrai joueur quand on l'a (servie par l'API,
// `/photos/...`), sinon (joueur inventé, photo introuvable ou hors ligne) une
// silhouette vide.
export default function PlayerAvatar({ src: photo, size = 28, className = "" }) {
  // Adresse dont le chargement a échoué (un autre joueur, une autre adresse, on réessaie).
  const [broken, setBroken] = useState(null);
  const style = { width: size, height: size };
  const src = photo?.startsWith("/") ? BASE_URL + photo : photo;
  if (src && src !== broken) {
    return (
      <img
        className={`player-avatar ${className}`}
        src={src}
        alt=""
        style={style}
        loading="lazy"
        onError={() => setBroken(src)}
      />
    );
  }
  return (
    <span className={`player-avatar player-avatar--blank ${className}`} style={style} aria-hidden="true">
      <svg viewBox="0 0 32 32" width="100%" height="100%">
        <circle cx="16" cy="12.5" r="5.5" />
        <path d="M5 30c0-6.5 4.9-10.5 11-10.5S27 23.5 27 30z" />
      </svg>
    </span>
  );
}
