import { useEffect } from "react";
import manifest from "./clubLogos.json";

// Blason et couleurs d'un club. Les vrais clubs ont les leurs (clubLogos.json, rempli par
// backend/scripts/fetch_club_logos.py) ; un club inventé reçoit deux couleurs tirées de
// son nom, toujours les mêmes, et l'écusson à initiales.

// Couleurs de maillot pour les clubs inventés : [primaire, secondaire].
const INVENTED_COLORS = [
  ["#7A1F2B", "#FFFFFF"],
  ["#0B3D91", "#FFFFFF"],
  ["#1F5C3A", "#F2C230"],
  ["#111111", "#C8102E"],
  ["#5B2A86", "#FFFFFF"],
  ["#C8102E", "#0B1F44"],
  ["#0E6E73", "#111111"],
  ["#B5541C", "#111111"],
  ["#1D4E89", "#7CC4EA"],
  ["#4A4F55", "#E8B10F"],
];

export function clubInfo(name) {
  const entry = (name && manifest[name]) || {};
  return {
    logo: entry.logo ?? null,
    light: Boolean(entry.light),
    colors: entry.colors?.length ? entry.colors : INVENTED_COLORS[hash(name ?? "") % INVENTED_COLORS.length],
  };
}

// Accent de l'interface aux couleurs du club : la première couleur assez foncée pour un
// bouton à texte blanc (contraste 4,5:1), sinon la primaire foncée jusqu'à l'être.
// `accent2` est l'autre couleur, pour le liseré du club.
export function clubTheme(name) {
  const [primary, secondary = primary] = clubInfo(name).colors;
  const readable = [primary, secondary].find((color) => contrast(color, "#FFFFFF") >= 4.5);
  const accent = readable ?? darken(primary);
  return { accent, accent2: accent === primary ? secondary : primary };
}

// Teinte l'interface (variables CSS --accent et --accent-2) aux couleurs du club ;
// sans club, on revient à l'accent par défaut de la feuille de style.
export function useClubTheme(name) {
  useEffect(() => {
    const root = document.documentElement.style;
    if (!name) return undefined;
    const { accent, accent2 } = clubTheme(name);
    root.setProperty("--accent", accent);
    root.setProperty("--accent-2", accent2);
    return () => {
      root.removeProperty("--accent");
      root.removeProperty("--accent-2");
    };
  }, [name]);
}

// Texte lisible (blanc ou encre) sur un fond de cette couleur.
export function inkOn(color) {
  return contrast(color, "#FFFFFF") >= 3 ? "#FFFFFF" : "#16181B";
}

function hash(text) {
  let h = 0;
  for (const char of text) h = (h * 31 + char.charCodeAt(0)) >>> 0;
  return h;
}

function darken(color) {
  let [r, g, b] = rgb(color);
  while (contrast(hex(r, g, b), "#FFFFFF") < 4.5) {
    [r, g, b] = [r * 0.9, g * 0.9, b * 0.9];
  }
  return hex(r, g, b);
}

function rgb(color) {
  const value = parseInt(color.slice(1), 16);
  return [(value >> 16) & 255, (value >> 8) & 255, value & 255];
}

function hex(r, g, b) {
  return `#${[r, g, b].map((c) => Math.round(c).toString(16).padStart(2, "0")).join("")}`;
}

// Contraste WCAG entre deux couleurs.
function contrast(a, b) {
  const [la, lb] = [luminance(a), luminance(b)];
  return (Math.max(la, lb) + 0.05) / (Math.min(la, lb) + 0.05);
}

function luminance(color) {
  const [r, g, b] = rgb(color).map((c) => {
    const s = c / 255;
    return s <= 0.03928 ? s / 12.92 : ((s + 0.055) / 1.055) ** 2.4;
  });
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}
