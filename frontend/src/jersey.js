import { clubInfo, inkOn } from "./clubs.js";

// Maillots du club, par tenue (domicile, extérieur, third) : un motif et trois couleurs
// (fond, motif, col et manches). Enregistrés par l'API (PUT /facilities/jerseys/{tenue}) ;
// sans maillot enregistré, celui aux couleurs du club. Le third s'achète avant de
// pouvoir être dessiné. Les sponsors (src/sponsors.js) sont communs aux trois tenues. Le dessin se fait sur un canevas déroulé autour du torse :
// la moitié gauche est le devant, la moitié droite le dos (vus de face tous les deux),
// le haut du canevas est le col. Le même canevas sert de texture au maillot en 3D
// (JerseyStudio) et d'aperçu à plat (JerseyFlat).

export const PATTERNS = [
  { kind: "plain", label: "Uni" },
  { kind: "hoops", label: "Cerceaux" },
  { kind: "stripes", label: "Rayures" },
  { kind: "band", label: "Bande" },
  { kind: "halves", label: "Moitiés" },
  { kind: "quarters", label: "Quartiers" },
  { kind: "sash", label: "Écharpe" },
  { kind: "chevron", label: "Chevron" },
  { kind: "yoke", label: "Épaules" },
];

// Couleurs proposées en plus de celles du club.
export const PALETTE = [
  "#FFFFFF", "#16181B", "#7A1F2B", "#C8102E", "#E35205", "#F2C230",
  "#1F5C3A", "#0E6E73", "#6CACE4", "#0B3D91", "#0B1F44", "#5B2A86",
]; // prettier-ignore

export const SPONSOR_MAX = 14;

export const KITS = [
  { kind: "home", label: "Domicile" },
  { kind: "away", label: "Extérieur" },
  { kind: "third", label: "Third" },
];

// Maillot aux couleurs du club pour une tenue : uni dans la première couleur à
// domicile, dans la seconde à l'extérieur ; le third sur un fond neutre (noir, ou blanc
// si le club joue déjà en sombre) avec le col aux couleurs du club.
export function defaultJersey(clubName, kind = "home") {
  const [primary, secondary = "#FFFFFF"] = clubInfo(clubName).colors;
  if (kind === "away") return { pattern: "plain", base: secondary, motif: primary, trim: primary };
  if (kind === "third") {
    const base = ["#16181B", "#FFFFFF"].find((c) => distance(c, primary) > 80 && distance(c, secondary) > 80) ?? "#16181B";
    const trim = distance(primary, base) > 80 ? primary : secondary;
    return { pattern: "plain", base, motif: trim, trim };
  }
  return { pattern: "plain", base: primary, motif: secondary, trim: secondary };
}

// Écart entre deux couleurs (0 : identiques, 441 : noir et blanc).
export function distance(a, b) {
  const channels = (color) => [1, 3, 5].map((i) => parseInt(color.slice(i, i + 2), 16));
  const [x, y] = [channels(a), channels(b)];
  return Math.hypot(x[0] - y[0], x[1] - y[1], x[2] - y[2]);
}

export function sameJersey(a, b) {
  return ["pattern", "base", "motif", "trim"].every(
    (key) => String(a[key]).toUpperCase() === String(b[key]).toUpperCase(),
  );
}

// Taille du canevas déroulé : 2 de large (devant + dos) pour 1 de haut.
export const TEXTURE_WIDTH = 1024;
export const TEXTURE_HEIGHT = 512;

// Hauteur (de 0, en bas, à 1, au col) où le torse s'arrête et les épaules commencent.
export const SHOULDER_LINE = 0.84;

// Dessine le maillot sur `canvas`. `crest` : image du blason déjà chargée (ou null) ;
// `scale` réduit le canevas (aperçus à plat) ; `marks: false` laisse le maillot nu
// (sans blason, logos ni numéro : vignettes des motifs). `logos` : les logos des
// sponsors et leur emplacement (src/sponsors.js, `placedLogos`).
export function paintJersey(
  canvas,
  jersey,
  { crest = null, clubName = "", number = "10", scale = 1, marks = true, logos = [] } = {},
) {
  canvas.width = Math.round(TEXTURE_WIDTH * scale);
  canvas.height = Math.round(TEXTURE_HEIGHT * scale);
  const ctx = canvas.getContext("2d");
  ctx.scale(scale, scale);
  const W = TEXTURE_WIDTH;
  const H = TEXTURE_HEIGHT;
  const half = W / 2;
  const { base, motif, trim } = jersey;

  ctx.fillStyle = base;
  ctx.fillRect(0, 0, W, H);
  ctx.fillStyle = motif;

  // Chaque moitié (devant, dos) reçoit le motif, dessiné dans son propre repère.
  for (const side of ["front", "back"]) {
    ctx.save();
    ctx.translate(side === "front" ? 0 : half, 0);
    ctx.beginPath();
    ctx.rect(0, 0, half, H);
    ctx.clip();
    drawPattern(ctx, jersey.pattern, side, half, H);
    ctx.restore();
  }

  // Liseré du col, sur le haut des épaules.
  ctx.fillStyle = trim;
  ctx.fillRect(0, 0, W, H * 0.025);

  if (marks) paintMarks(ctx, jersey, { crest, clubName, number, logos });
  return canvas;
}

// Où se posent les logos des sponsors sur le canevas : centre et taille maximale.
// (La manche est sur son propre canevas, voir JerseyStudio et JerseyFlat.)
const LOGO_SPOTS = {
  chest: { x: 0.25, y: 0.49, w: 0.45, h: 0.115 },
  belly: { x: 0.25, y: 0.78, w: 0.34, h: 0.085 },
  back: { x: 0.75, y: 0.215, w: 0.43, h: 0.11 },
};

// Blason sur le cœur (à droite vu de face), logos des sponsors à leur place, numéro
// dans le dos. Dans le repère du canevas déroulé (TEXTURE_WIDTH × TEXTURE_HEIGHT).
export function paintMarks(
  ctx,
  jersey,
  { crest = null, clubName = "", number = "10", logos = [] } = {},
) {
  const half = TEXTURE_WIDTH / 2;
  const H = TEXTURE_HEIGHT;
  drawCrest(ctx, crest, clubName, half * 0.7, H * 0.3, H * 0.13, jersey);
  for (const { placement, image } of logos) {
    const spot = LOGO_SPOTS[placement];
    if (spot) drawLogo(ctx, image, spot.x * TEXTURE_WIDTH, spot.y * H, spot.w * half, spot.h * H);
  }
  drawLabel(ctx, number, half * 1.5, H * 0.52, half * 0.5, H * 0.34, jersey);
}

// Un logo (image déjà chargée) centré en (x, y), dans une boîte de w × h au plus.
export function drawLogo(ctx, image, x, y, w, h) {
  const ratio = image.naturalWidth / image.naturalHeight || 4;
  const [width, height] = w / h > ratio ? [h * ratio, h] : [w, w / ratio];
  ctx.drawImage(image, x - width / 2, y - height / 2, width, height);
}

function drawPattern(ctx, pattern, side, w, h) {
  // Les côtés du maillot sont aux bords de chaque moitié : x = 0 côté gauche vu de face
  // pour le devant, côté gauche vu de dos pour le dos.
  const torso = h * (1 - SHOULDER_LINE); // haut des épaules
  switch (pattern) {
    case "hoops": {
      const count = 7;
      const step = h / count;
      for (let i = 1; i < count; i += 2) ctx.fillRect(0, i * step, w, step);
      break;
    }
    case "stripes": {
      const count = 9;
      const step = w / count;
      for (let i = 1; i < count; i += 2) ctx.fillRect(i * step, 0, step, h);
      break;
    }
    case "band":
      ctx.fillRect(0, h * 0.3, w, h * 0.18);
      break;
    case "halves":
    case "quarters": {
      // Vu de dos, la moitié qui était à droite de face passe à gauche.
      const left = side === "back";
      ctx.fillRect(left ? 0 : w / 2, 0, w / 2, pattern === "halves" ? h : h / 2);
      if (pattern === "quarters") ctx.fillRect(left ? w / 2 : 0, h / 2, w / 2, h / 2);
      break;
    }
    case "sash": {
      // De l'épaule gauche (à droite vu de face) à la hanche droite ; dans le dos, en miroir.
      const width = h * 0.17;
      const [from, to] = side === "front" ? [w * 1.05, -w * 0.05] : [-w * 0.05, w * 1.05];
      ctx.beginPath();
      ctx.moveTo(from, torso - width);
      ctx.lineTo(from, torso + width);
      ctx.lineTo(to, h + width * 0.2);
      ctx.lineTo(to, h - width * 1.8);
      ctx.closePath();
      ctx.fill();
      break;
    }
    case "chevron": {
      const width = h * 0.13;
      const top = h * 0.2;
      const tip = h * 0.5;
      ctx.beginPath();
      ctx.moveTo(-1, top);
      ctx.lineTo(w / 2, tip);
      ctx.lineTo(w + 1, top);
      ctx.lineTo(w + 1, top + width);
      ctx.lineTo(w / 2, tip + width);
      ctx.lineTo(-1, top + width);
      ctx.closePath();
      ctx.fill();
      break;
    }
    case "yoke": {
      // Épaules et haut de poitrine, bord en pointe vers le bas.
      ctx.beginPath();
      ctx.moveTo(0, 0);
      ctx.lineTo(w, 0);
      ctx.lineTo(w, h * 0.3);
      ctx.lineTo(w / 2, h * 0.38);
      ctx.lineTo(0, h * 0.3);
      ctx.closePath();
      ctx.fill();
      break;
    }
    default:
      break;
  }
}

// Couleur de la manche, à gauche ou à droite vu de face : celle du motif là où il la touche.
export function sleeveColor(jersey, right) {
  const { pattern, base, motif } = jersey;
  if (pattern === "yoke") return motif;
  if (pattern === "halves" || pattern === "quarters") return right ? motif : base;
  return base;
}

// Les cerceaux continuent sur les manches.
export function sleeveHoops(jersey) {
  return jersey.pattern === "hoops";
}

// Texte posé sur le maillot (le numéro) : dans la couleur la plus lisible sur le
// fond, cerné de l'autre pour rester lisible par-dessus le motif.
function drawLabel(ctx, text, x, y, maxWidth, size, jersey) {
  const fill = labelColor(jersey);
  ctx.save();
  ctx.font = `700 ${size}px "Barlow Condensed", "Arial Narrow", sans-serif`;
  ctx.textAlign = "center";
  ctx.textBaseline = "middle";
  const width = ctx.measureText(text).width;
  if (width > maxWidth) {
    ctx.translate(x, y);
    ctx.scale(maxWidth / width, 1);
    ctx.translate(-x, -y);
  }
  ctx.lineJoin = "round";
  ctx.lineWidth = size * 0.12;
  ctx.strokeStyle = fill === "#FFFFFF" ? "rgba(22,24,27,0.55)" : "rgba(255,255,255,0.55)";
  ctx.strokeText(text, x, y);
  ctx.fillStyle = fill;
  ctx.fillText(text, x, y);
  ctx.restore();
}

function labelColor({ pattern, base, motif, trim }) {
  // Sur un motif qui couvre la poitrine, on prend la couleur du col si elle tranche.
  const covered = ["stripes", "hoops", "halves", "quarters"].includes(pattern);
  if (covered && trim.toUpperCase() !== base.toUpperCase() && trim.toUpperCase() !== motif.toUpperCase()) {
    return trim;
  }
  return inkOn(base) === "#FFFFFF" ? "#FFFFFF" : "#16181B";
}

function drawCrest(ctx, crest, clubName, x, y, size, jersey) {
  ctx.save();
  if (crest) {
    const ratio = crest.naturalWidth / crest.naturalHeight || 1;
    const [w, h] = ratio > 1 ? [size, size / ratio] : [size * ratio, size];
    ctx.drawImage(crest, x - w / 2, y - h / 2, w, h);
  } else {
    // Sans blason : un écusson à initiales, aux couleurs du col.
    ctx.fillStyle = jersey.trim;
    ctx.beginPath();
    ctx.moveTo(x - size * 0.4, y - size * 0.45);
    ctx.lineTo(x + size * 0.4, y - size * 0.45);
    ctx.lineTo(x + size * 0.4, y + size * 0.05);
    ctx.quadraticCurveTo(x + size * 0.4, y + size * 0.4, x, y + size * 0.55);
    ctx.quadraticCurveTo(x - size * 0.4, y + size * 0.4, x - size * 0.4, y + size * 0.05);
    ctx.closePath();
    ctx.fill();
    ctx.fillStyle = inkOn(jersey.trim);
    ctx.font = `700 ${size * 0.36}px "Barlow Condensed", "Arial Narrow", sans-serif`;
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    ctx.fillText(initials(clubName), x, y);
  }
  ctx.restore();
}

function initials(name) {
  return name
    .split(/[\s-]+/)
    .filter(Boolean)
    .map((word) => word[0])
    .join("")
    .slice(0, 3)
    .toUpperCase();
}

// Charge le blason du club (null s'il n'en a pas ou s'il ne se charge pas).
export function loadCrest(clubName) {
  const { logo } = clubInfo(clubName);
  if (!logo) return Promise.resolve(null);
  return new Promise((resolve) => {
    const image = new Image();
    image.onload = () => resolve(image);
    image.onerror = () => resolve(null);
    image.src = logo;
  });
}
