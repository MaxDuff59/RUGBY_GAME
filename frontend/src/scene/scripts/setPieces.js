import { TOUCH } from "../field.js";
import { bind, crouch, jump, lifter, pose } from "../rig.js";
import { FACE_FIELD, FACE_LINE, clamp, lerp, smooth, span } from "./common.js";

// Mêlée, touche et maul : où se tient chacun, et comment le groupe pousse. Notre équipe
// attaque vers la ligne d'essai (z = 0) : notre pack est du côté +z.

// Mêlée centrée en (cx, cz), introduite de notre côté. Par numéro, le décalage au
// centre (en travers, en profondeur) : piliers, talonneur, deuxièmes lignes, troisième
// ligne. Notre gauche, face à la ligne, est vers -x.
const SCRUM = {
  1: [-0.52, 0.78, 1],
  2: [0, 0.78, 1],
  3: [0.52, 0.78, 1],
  4: [-0.27, 1.62, 0.95],
  5: [0.27, 1.62, 0.95],
  6: [-0.88, 1.5, 0.85],
  7: [0.88, 1.5, 0.85],
  8: [0, 2.45, 0.9],
};

// Place les deux packs (`ours`, `theirs` : numéro -> joueur) liés en mêlée. `push` :
// de combien la mêlée a avancé vers la ligne (négatif : reculé) ; `wheel` : elle
// tourne (radians) ; `drive` : les jambes poussent (0 à 1) ; `phase` : le temps.
export function scrum(ours, theirs, cx, cz, { push = 0, wheel = 0, drive = 0, phase = 0, engage = 1 } = {}) {
  const c = Math.cos(wheel);
  const s = Math.sin(wheel);
  const at = (dx, dz) => [cx + dx * c + dz * s, cz - push + -dx * s + dz * c];
  // Avant l'impact, les packs se tiennent un pas en arrière.
  const gap = (1 - engage) * 0.6;
  for (const [number, [dx, dz, low]] of Object.entries(SCRUM)) {
    const n = Number(number);
    const mine = ours[n];
    if (mine) {
      const [x, z] = at(dx, dz + gap);
      mine.place(x, z, FACE_LINE + wheel).set(bind(phase + n * 0.13, drive, low * (0.6 + 0.4 * engage)));
    }
    const other = theirs[n];
    if (other) {
      const [x, z] = at(-dx, -dz - gap);
      other.place(x, z, FACE_FIELD + wheel).set(bind(phase + n * 0.17 + 0.5, drive * 0.8, low * (0.6 + 0.4 * engage)));
    }
  }
  return at(0, 0);
}

// La touche : le long de la ligne d'en face (côté `side`, ±1), à `zl` de la ligne
// d'essai. Nos joueurs côté +z, les leurs côté -z, tous tournés vers la touche.
const LINE = { 6: 6, 1: 7, 5: 8, 4: 9, 8: 11, 7: 12.5 };

export function lineoutSpots(side, zl) {
  const spots = { ours: {}, theirs: {} };
  for (const [number, depth] of Object.entries(LINE)) {
    spots.ours[number] = [side * (TOUCH - depth), zl + 0.55];
    spots.theirs[number] = [side * (TOUCH - depth + 0.4), zl - 0.55];
  }
  spots.thrower = [side * (TOUCH + 0.7), zl];
  spots.jumper = [side * (TOUCH - 8), zl];
  return spots;
}

// La touche à l'instant `s` (de 0 : alignés, à 1 : le sauteur retombe) : le lancer part
// à `throwAt`, le sauteur monte, attrape, redescend. Rend la hauteur des mains du
// sauteur (où le ballon arrive).
export function lineout(ours, theirs, spots, side, s, { throwAt = 0.3, catchAt = 0.75 } = {}) {
  const face = (side * Math.PI) / 2;
  for (const [number, [x, z]] of Object.entries(spots.ours)) {
    const player = ours[number];
    if (!player) continue;
    player.place(x, z, face);
  }
  for (const [number, [x, z]] of Object.entries(spots.theirs)) {
    const player = theirs[number];
    if (!player) continue;
    player.place(x, z, face);
  }
  // Le sauteur (5) monte, porté par le 1 et le 4 ; en face, leur 5 saute un peu après.
  const up = smooth(span(s, throwAt - 0.15, throwAt + 0.2)) * (1 - smooth(span(s, catchAt + 0.1, catchAt + 0.45)));
  const theirUp = smooth(span(s, throwAt, throwAt + 0.3)) * (1 - smooth(span(s, catchAt, catchAt + 0.3))) * 0.7;
  ours[5]?.set({ ...jump(up), lift: up * 1.6 });
  ours[1]?.set(lifter(up));
  ours[4]?.set(lifter(up));
  theirs[5]?.set({ ...jump(theirUp), lift: theirUp * 1.1 });
  theirs[1]?.set(lifter(theirUp));
  theirs[4]?.set(lifter(theirUp));
  for (const n of [6, 7, 8]) {
    ours[n]?.set(pose({ y: -0.1, lean: 0.2, knL: 0.4, knR: 0.4, legL: 0.2, legR: 0.2, armL: 0.6, armR: 0.6, elL: 1 }));
    theirs[n]?.set(pose({ y: -0.1, lean: 0.2, knL: 0.4, knR: 0.4, legL: 0.2, legR: 0.2, armL: 0.6, armR: 0.6, elL: 1 }));
  }
  return 1.6 * up + 2.25;
}

// Le maul : groupés derrière le porteur, nos avants poussent vers la ligne, les leurs
// reculent en face. `from` : où chacun était (joueur -> [x, z]) ; `center` : [x, z] de
// l'avant du maul ; `k` : formé (0 à 1).
const MAUL_OURS = { 5: [0, 0.35], 1: [-0.6, 0.6], 4: [0.6, 0.6], 6: [-0.45, 1.45], 7: [0.45, 1.45], 8: [0, 2.1], 2: [0.1, 2.9] };
const MAUL_THEIRS = { 1: [-0.5, -0.45], 5: [0.5, -0.45], 4: [0, -1.25], 6: [-0.9, -1.1], 7: [0.9, -1.2], 8: [0, -2] };

export function maul(ours, theirs, from, center, k, phase, drive = 1) {
  const place = (player, [dx, dz], heading, offset) => {
    if (!player) return;
    const start = from.get(player) ?? [center[0] + dx, center[1] + dz];
    const x = lerp(start[0], center[0] + dx, smooth(k));
    const z = lerp(start[1], center[1] + dz, smooth(k));
    player.place(x, z, heading).set(bind(phase + offset, drive * clamp(k * 2 - 1), 0.75));
  };
  Object.entries(MAUL_OURS).forEach(([n, offset], i) => place(ours[n], offset, FACE_LINE, i * 0.21));
  Object.entries(MAUL_THEIRS).forEach(([n, offset], i) => place(theirs[n], offset, FACE_FIELD, i * 0.19 + 0.5));
}

// Le demi de mêlée accroupi au ras du ballon.
export const halfBack = crouch(0.8);
