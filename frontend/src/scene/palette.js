// Palette des scènes de match : 64 couleurs, tirées en OKLab des couleurs de
// DESIGN.md (vert terrain, fonds clairs, encre, gris), de celles des deux clubs, et
// de ce qu'une pelouse et un stade demandent (peaux, ciel, béton, projecteurs). Chaque
// couleur de départ donne une rampe de clartés ; le rendu (render.js) ramène chaque
// pixel à la couleur la plus proche en OKLab.

export const PALETTE_SIZE = 64;

const srgbToLinear = (c) => (c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4);
const linearToSrgb = (c) => (c <= 0.0031308 ? c * 12.92 : 1.055 * c ** (1 / 2.4) - 0.055);
const clamp01 = (x) => Math.min(1, Math.max(0, x));

export function hexToLinear(hex) {
  const value = parseInt(hex.slice(1), 16);
  return [(value >> 16) & 255, (value >> 8) & 255, value & 255].map((c) => srgbToLinear(c / 255));
}

// OKLab (Björn Ottosson) depuis du sRGB linéaire, et retour.
export function linearToOklab([r, g, b]) {
  const l = Math.cbrt(0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b);
  const m = Math.cbrt(0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b);
  const s = Math.cbrt(0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b);
  return [
    0.2104542553 * l + 0.793617785 * m - 0.0040720468 * s,
    1.9779984951 * l - 2.428592205 * m + 0.4505937099 * s,
    0.0259040371 * l + 0.7827717662 * m - 0.808675766 * s,
  ];
}

export function oklabToLinear([L, a, b]) {
  const l = (L + 0.3963377774 * a + 0.2158037573 * b) ** 3;
  const m = (L - 0.1055613458 * a - 0.0638541728 * b) ** 3;
  const s = (L - 0.0894841775 * a - 1.291485548 * b) ** 3;
  return [
    clamp01(4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s),
    clamp01(-1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s),
    clamp01(-0.0041960863 * l - 0.7034186147 * m + 1.707614701 * s),
  ];
}

export const linearToHex = (rgb) =>
  `#${rgb.map((c) => Math.round(linearToSrgb(clamp01(c)) * 255).toString(16).padStart(2, "0")).join("")}`;

// Une rampe : `count` clartés autour de la couleur, de `dark` à `light` (en L d'OKLab),
// la teinte un peu désaturée aux extrêmes.
function ramp(hex, count, dark, light) {
  const [L, a, b] = linearToOklab(hexToLinear(hex));
  if (count === 1) return [[L, a, b]];
  const out = [];
  for (let i = 0; i < count; i++) {
    const k = i / (count - 1);
    const target = Math.max(0.08, Math.min(0.98, L + dark + (light - dark) * k));
    const chroma = 1 - Math.abs(k - 0.5) * 0.5;
    out.push([target, a * chroma, b * chroma]);
  }
  return out;
}

// Deux couleurs trop proches (en OKLab) gaspillent une place : on garde la première.
const close = (x, y) => Math.hypot(x[0] - y[0], x[1] - y[1], x[2] - y[2]) < 0.025;

// `clubs` : les couleurs des maillots en jeu (fond, motif, col, short), de la plus
// importante à la moins importante ; `extra` : des couleurs à garder telles quelles
// (l'accent du club du joueur, le repère au sol).
export function buildPalette({ clubs = [], extra = [], evening = false } = {}) {
  const seeds = [
    // DESIGN.md
    ["#2E4A38", 7, -0.16, 0.2], // terrain
    ["#EDEDE8", 3, -0.06, 0.04], // fond de page, surface, lignes du terrain
    ["#16181B", 2, -0.02, 0.06], // encre, contours
    ["#5E6168", 3, -0.14, 0.12], // texte secondaire, béton
    ["#8A8D93", 2, -0.04, 0.12], // neutres
    // Ciel, de jour ou de nuit ; projecteurs.
    evening ? ["#1C2A44", 3, -0.08, 0.12] : ["#9DB8D2", 3, -0.1, 0.08],
    ["#F2E6B8", 2, -0.05, 0.05],
    // Peaux, cheveux.
    ["#D9A988", 3, -0.16, 0.1],
    ["#8A5A3C", 2, -0.12, 0.04],
    ["#3A2A20", 1, 0, 0],
    // Ballon (cuir, liseré or), carton jaune, tee.
    ["#C8A35C", 1, 0, 0],
    ["#F2C230", 1, 0, 0],
    ["#E35205", 1, 0, 0],
  ];
  const colors = [];
  const push = (lab) => {
    if (colors.length < PALETTE_SIZE && !colors.some((c) => close(c, lab))) colors.push(lab);
  };
  for (const hex of extra) push(linearToOklab(hexToLinear(hex)));
  // Les clubs d'abord, pour qu'ils aient leurs ombres et leurs lumières.
  const clubSteps = [4, 4, 3, 3, 2, 2, 2, 2];
  clubs.forEach((hex, index) => ramp(hex, clubSteps[index] ?? 1, -0.14, 0.1).forEach(push));
  for (const [hex, count, dark, light] of seeds) ramp(hex, count, dark, light).forEach(push);
  // Ce qui reste : des verts et des gris intermédiaires, les plus présents à l'écran.
  for (let i = 0; colors.length < PALETTE_SIZE && i < 400; i++) {
    const green = linearToOklab(hexToLinear("#2E4A38"));
    const k = (i * 0.618) % 1;
    push(i % 3 === 2 ? [0.2 + k * 0.75, 0, 0] : [green[0] - 0.14 + k * 0.42, green[1] * (0.6 + k), green[2] * (0.6 + k)]);
  }
  while (colors.length < PALETTE_SIZE) colors.push(colors[colors.length - 1]);
  return colors;
}
