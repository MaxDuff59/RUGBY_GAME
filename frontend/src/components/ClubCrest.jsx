import { useState } from "react";
import { clubInfo, clubTheme, inkOn } from "../clubs.js";

// Blason d'un club : l'image téléchargée (scripts/fetch_club_logos.py) pour les vrais
// clubs, sinon un écusson à initiales aux couleurs du club (clubs inventés, blason
// manquant ou cassé).
export default function ClubCrest({ name, size = 24, className = "" }) {
  const [broken, setBroken] = useState(false);
  const { logo, light, colors } = clubInfo(name);
  const style = { width: size, height: size };
  if (logo && !broken && light) {
    // Blason blanc : posé sur une pastille de la couleur du club, sinon invisible sur le fond clair.
    return (
      <span className={`club-crest club-crest--disc ${className}`} style={{ ...style, background: clubTheme(name).accent }}>
        <img src={logo} alt="" onError={() => setBroken(true)} />
      </span>
    );
  }
  if (logo && !broken) {
    return <img className={`club-crest ${className}`} src={logo} alt="" style={style} onError={() => setBroken(true)} />;
  }
  return (
    <span
      className={`club-crest club-crest--blank ${className}`}
      style={{ ...style, background: colors[0], color: inkOn(colors[0]), fontSize: Math.max(8, Math.round(size * 0.34)) }}
      aria-hidden="true"
    >
      {initials(name ?? "")}
    </span>
  );
}

// "Entente Port-Miremire" -> "EPM"
function initials(name) {
  return name
    .split(/[\s-]+/)
    .filter(Boolean)
    .map((word) => word[0])
    .join("")
    .slice(0, 3)
    .toUpperCase();
}
