import {
  FORWARDS,
  MID_Y,
  WIDTH,
  clamp,
  clampX,
  clampY,
  dir,
  goalOf,
  keyOf,
  leftOf,
  numberOf,
  other,
  seeded,
  teamOf,
  wingOn,
} from "./geometry.js";

// Les placements du rugby, joueur par joueur, pour les deux équipes et l'arbitre. Chaque
// fonction rend { pos: { clé: [x, y] }, ball, down } ; `present` dit qui est sur le
// terrain ({ us: Set(1..15), them: Set(1..15) }) : une place vide (carton, blessé non
// remplacé) reste vide.
//
// Les repères du jeu : en attaque, le demi de mêlée au pied du ruck, les receveurs en
// profondeur et en escalier derrière lui (une passe va toujours vers l'arrière), des
// avants groupés en « pods » près du ruck, les trois-quarts au large, l'arrière derrière la
// ligne ; en défense, une ligne à plat sur la ligne de hors-jeu, un défenseur à chaque
// flanc du ruck, les avants au près et les trois-quarts au large, l'arrière en couverture.

class Shape {
  constructor(present) {
    this.present = present;
    this.pos = {};
  }

  has(team, n) {
    return this.present[team]?.has(n) ?? false;
  }

  set(team, n, x, y, margin = 0.9) {
    if (!this.has(team, n)) return null;
    const p = [clampX(x), clampY(y, margin)];
    this.pos[keyOf(team, n)] = p;
    return p;
  }

  setKey(key, p, margin = 0.9) {
    return this.set(teamOf(key), numberOf(key), p[0], p[1], margin);
  }
}

const rotate = (list, by) => (list.length ? [...list.slice(by % list.length), ...list.slice(0, by % list.length)] : list);

// Un défenseur ne recule pas au-delà de son en-but.
const inGoal = (att, x) => (dir(att) > 0 ? Math.min(x, goalOf(att) + 3) : Math.max(x, goalOf(att) - 3));

// --- Le jeu courant : un ruck --------------------------------------------------------------

// Le ruck en (bx, by), le ballon à `att`.
// - `ruck` : le joueur plaqué, au sol sur le ballon ;
// - `cleaners` : les deux attaquants qui protègent le ballon (les premiers arrivés) ;
// - `carrier` : le prochain porteur, placé là où il recevra ;
// - `tackler` : le défenseur qui l'attend, glissé dans son couloir ;
// - `rush` : la défense déjà montée de quelques mètres ; `squeeze` : resserrée (< 1) ;
// - `broken` : défense désorganisée (de 0 à 1), après une récupération ou un franchissement.
export function openPlay(present, opts) {
  const { att, ruck = null, cleaners = [], carrier = null, tackler = null, seed = 1, rush = 0, squeeze = 1, broken = 0 } = opts;
  const bx = clamp(opts.bx, 1.5, 98.5);
  const by = clamp(opts.by, 5, WIDTH - 5);
  const R = seeded(seed * 7919 + 13);
  const jit = (m) => (R() - 0.5) * 2 * m;
  const d = dir(att);
  const D = other(att);
  const o = by <= MID_Y ? 1 : -1; // le côté ouvert, le plus large
  const W = o > 0 ? WIDTH - by : by;
  const B = WIDTH - W;
  const s = clamp((W - 5) / 45, 0.3, 1.15);
  const sh = new Shape(present);
  const lat = (l) => clamp(l, -(B - 2), W - 2);
  const A = (n, depth, l, m = 0.35) => sh.set(att, n, bx - d * (depth + jit(m)), by + o * lat(l + jit(m)));
  const Dd = (n, depth, l, m = 0.3) => sh.set(D, n, inGoal(att, bx + d * (depth + jit(m))), by + o * lat(l + jit(m)));
  const used = new Set();
  const avail = (team, n) => sh.has(team, n) && !used.has(keyOf(team, n));
  const take = (key) => used.add(key);

  // Le ruck : le plaqué au sol, le ballon derrière lui, côté attaque.
  const down = [];
  if (ruck && sh.has(teamOf(ruck), numberOf(ruck))) {
    sh.setKey(ruck, [bx + d * (teamOf(ruck) === att ? 0.35 : 0.8), by + jit(0.3)]);
    down.push(ruck);
    take(ruck);
  }
  const ball = { at: [bx - d * 0.55, by] };

  // Le demi de mêlée au pied du ruck (un autre s'il est au sol ou absent).
  const nine = [9, 7, 10, 6].map((n) => keyOf(att, n)).find((key) => avail(att, numberOf(key)));
  if (nine) {
    sh.setKey(nine, [bx - d * 1.35, by + o * 0.6]);
    take(nine);
  }
  const carrierKey = carrier && teamOf(carrier) === att && avail(att, numberOf(carrier)) ? carrier : null;
  // Les deux premiers soutiens, liés sur le ballon.
  const binders = cleaners.filter((key) => teamOf(key) === att && avail(att, numberOf(key)) && key !== carrierKey).slice(0, 2);
  binders.forEach(take);
  let pool = rotate(
    FORWARDS.filter((n) => avail(att, n) && keyOf(att, n) !== carrierKey).map((n) => keyOf(att, n)),
    Math.floor(R() * 8),
  );
  while (binders.length < 2 && pool.length) {
    const key = pool.shift();
    binders.push(key);
    take(key);
  }
  binders.forEach((key, i) => sh.setKey(key, [bx + d * 0.15, by + (i ? 1 : -1) * 0.95 + jit(0.15)]));
  pool = pool.filter((key) => !used.has(key));

  // Les avants : un pod de trois au ras du ruck côté ouvert (le porteur en pointe s'il
  // est avant), deux plus au large, un côté fermé.
  const pod = [];
  if (carrierKey && numberOf(carrierKey) <= 8) {
    pod.push(carrierKey);
    take(carrierKey);
  }
  while (pod.length < 3 && pool.length) pod.push(pool.shift());
  const podSpots = [
    [3.0, 4.2],
    [4.5, 2.3],
    [4.5, 6.2],
  ];
  pod.forEach((key, i) => A(numberOf(key), ...podSpots[i], 0.15));
  pod.forEach(take);
  const wide = pool.splice(0, 2);
  wide.forEach((key, i) => A(numberOf(key), 5.4 + i * 1.0, Math.min(W - 6, (13.5 + i * 3.6) * s + 2)));
  wide.forEach(take);
  pool.forEach((key, i) => {
    const blind = 3.6 + i * 2.8;
    if (B >= blind + 2.5) A(numberOf(key), 3.0 + i * 1.1, -blind);
    else A(numberOf(key), 6.5 + i * 1.2, (23 + i * 3) * s);
    take(key);
  });

  // Les trois-quarts en escalier : chacun un peu plus profond que celui de l'intérieur.
  const back = (n, depth, l) => {
    if (!avail(att, n)) return;
    A(n, depth, l);
    take(keyOf(att, n));
  };
  back(10, 7.4, Math.max(8.5 * s, 6.5));
  back(12, 9.6, 15 * s + 1.5);
  back(13, 11.7, 21 * s + 2);
  const openWing = wingOn(att, o);
  const blindWing = wingOn(att, -o);
  back(openWing, 12.8, W - 4);
  if (B >= 13) {
    back(blindWing, 8, -(B - 4));
    back(15, 14.6, Math.min(27 * s + 2, W - 9));
  } else {
    // Pas de place côté fermé : l'ailier recule en couverture, l'arrière s'intercale.
    back(blindWing, 22, 0.25 * W);
    back(15, 13.8, Math.min(25 * s + 2, W - 10));
  }

  // La défense, à plat sur la ligne de hors-jeu.
  const line = 2.1 - rush;
  let dPool = rotate(
    FORWARDS.filter((n) => avail(D, n)).map((n) => keyOf(D, n)),
    Math.floor(R() * 8),
  );
  const dSpot = (key, depth, l) => {
    Dd(numberOf(key), depth, l);
    take(key);
  };
  const lineKeys = [];
  const guard = (depth, l) => {
    const key = dPool.shift();
    if (!key) return;
    dSpot(key, depth, l);
    lineKeys.push(key);
  };
  guard(line, 1.5); // le premier rideau, côté ouvert
  guard(line, -1.5); // côté fermé
  guard(line, 3.4);
  if (down.length) {
    const key = dPool.shift(); // celui qui conteste le ballon
    if (key) dSpot(key, 1.25, 0.1);
  }
  const blindDef = B >= 9 && dPool.length > 3 ? dPool.pop() : null;
  if (blindDef) {
    dSpot(blindDef, line, -Math.min(4.8, B - 2.5));
    lineKeys.push(blindDef);
  }
  // Au large : les avants qui restent, puis l'ouvreur, les centres et l'ailier.
  const open = [...dPool, ...[10, 12, 13].filter((n) => avail(D, n)).map((n) => keyOf(D, n))];
  const dOpenWing = keyOf(D, wingOn(D, o));
  const spacing = clamp(((W - 9) / Math.max(1, open.length + 0.5)) * squeeze, 2.2, 7.5);
  let l = 6.2;
  for (const key of open) {
    if (l > W - 4) {
      dSpot(key, line + 8, Math.min(W * 0.55, W - 6)); // plus de place : en second rideau
    } else {
      dSpot(key, line + 0.15 * (l / 10), l);
      lineKeys.push(key);
    }
    l += spacing;
  }
  if (avail(D, numberOf(dOpenWing))) {
    const wingLat = Math.min(W - 3, Math.max(l, W - 6.5));
    dSpot(dOpenWing, line + 2.5, wingLat);
    lineKeys.push(dOpenWing);
  }
  const dBlindWing = keyOf(D, wingOn(D, -o));
  if (avail(D, numberOf(dBlindWing))) {
    if (B >= 16) {
      dSpot(dBlindWing, line + 3.5, -(B - 6));
      lineKeys.push(dBlindWing);
    } else dSpot(dBlindWing, line + 15, -Math.min(B - 3, 2) + W * 0.1);
  }
  if (avail(D, 15)) dSpot(keyOf(D, 15), line + 19, 0.38 * W - 0.15 * B);
  if (avail(D, 9)) dSpot(keyOf(D, 9), line + 2.6, 0.9); // en balayeur derrière le ruck

  // Le défenseur du porteur à venir : dans son couloir.
  if (tackler && carrierKey && sh.pos[tackler] && sh.pos[carrierKey]) {
    const y = sh.pos[carrierKey][1];
    const facing = lineKeys
      .filter((key) => key !== tackler)
      .sort((a, b) => Math.abs(sh.pos[a][1] - y) - Math.abs(sh.pos[b][1] - y))[0];
    if (facing && Math.abs(sh.pos[facing][1] - y) < Math.abs(sh.pos[tackler][1] - y)) {
      [sh.pos[facing], sh.pos[tackler]] = [sh.pos[tackler], sh.pos[facing]];
    }
  }

  // Défense prise à revers : en désordre, à la course pour se replacer.
  if (broken > 0) {
    for (const key of Object.keys(sh.pos)) {
      if (teamOf(key) !== D || down.includes(key)) continue;
      const [x, y] = sh.pos[key];
      sh.pos[key] = [clampX(x + d * (R() - 0.25) * broken * 14), clampY(y + (R() - 0.5) * broken * 16)];
    }
  }

  // L'arbitre, sur le flanc du ruck.
  sh.pos.ref = [clampX(bx - d * 0.6), clampY(by - o * 3.4)];
  return { pos: sh.pos, ball, down, bound: binders, att, bx, by, o, W, B };
}

// --- La touche --------------------------------------------------------------------------

// Touche lancée par `thrower` à x0, le long de la touche `side` (0 ou 70). Les deux
// alignements face à face entre 5 et 15 m, le talonneur qui lance hors du terrain, les
// trois-quarts à dix mètres de part et d'autre.
const LINEOUT_ORDER = [1, 4, 3, 6, 5, 7, 8];
const LINEOUT_SPOTS = [5.5, 6.8, 8.1, 9.4, 10.7, 12.0, 13.3];

export function lineout(present, { thrower, x0: rawX, side }) {
  const T = thrower;
  const D = other(T);
  const d = dir(T);
  const x0 = clamp(rawX, 5.5, 94.5);
  const ts = side === 0 ? 1 : -1; // vers l'intérieur du terrain
  const yy = (m) => side + ts * m;
  const sh = new Shape(present);
  const slot = {};
  sh.set(T, 2, x0, yy(-1.1), -2);
  LINEOUT_ORDER.forEach((n, i) => {
    if (sh.set(T, n, x0 - d * 0.55, yy(LINEOUT_SPOTS[i]))) slot[keyOf(T, n)] = LINEOUT_SPOTS[i];
    if (sh.set(D, n, x0 + d * 0.55, yy(LINEOUT_SPOTS[i]))) slot[keyOf(D, n)] = LINEOUT_SPOTS[i];
  });
  sh.set(D, 2, x0 + d * 1.4, yy(2.6));
  sh.set(T, 9, x0 - d * 2.2, yy(15));
  sh.set(D, 9, x0 + d * 2.2, yy(15));
  const far = (team) => wingOn(team, ts);
  const near = (team) => wingOn(team, -ts);
  const T_ = (n, back, m) => sh.set(T, n, x0 - d * back, yy(m));
  const D_ = (n, back, m) => sh.set(D, n, inGoal(T, x0 + d * back), yy(m));
  T_(10, 11, 21);
  T_(12, 12.3, 28.5);
  T_(13, 13.5, 36);
  T_(far(T), 13.6, 54);
  T_(near(T), 15, 4);
  T_(15, 19, 39);
  D_(10, 10.5, 21);
  D_(12, 10.6, 28);
  D_(13, 10.7, 35.5);
  D_(far(D), 12, 50);
  D_(near(D), 20, 7);
  D_(15, 24, 34);
  sh.pos.ref = [clampX(x0), clampY(yy(17))];
  return { pos: sh.pos, ball: { holder: keyOf(T, 2) }, down: [], x0, side, ts, slot };
}

// Le maul : les avants de `team` liés derrière le sauteur, le ballon passé au dernier
// (`carrier`), face aux avants adverses ; en (x0, y0). Rend les positions des avants.
export function maulCluster(present, { team, x0, y0, carrier }) {
  const d = dir(team);
  const D = other(team);
  const pos = {};
  const ours = FORWARDS.map((n) => keyOf(team, n)).filter((key) => present[team].has(numberOf(key)) && key !== carrier);
  const spots = [
    [0.55, -0.55],
    [0.55, 0.55],
    [-0.15, -1.05],
    [-0.15, 0],
    [-0.15, 1.05],
    [-0.85, -0.55],
    [-0.85, 0.55],
    [-0.5, 1.6],
  ];
  ours.forEach((key, i) => {
    const [dx, dy] = spots[i % spots.length];
    pos[key] = [clampX(x0 + d * dx), clampY(y0 + dy)];
  });
  if (carrier) pos[carrier] = [clampX(x0 - d * 1.45), clampY(y0 + 0.2)];
  const theirs = FORWARDS.map((n) => keyOf(D, n)).filter((key) => present[D].has(numberOf(key)));
  const front = [
    [1.4, -0.75],
    [1.4, 0.75],
    [1.35, 0],
    [2.1, -0.5],
    [2.1, 0.5],
    [2.15, -1.4],
    [2.15, 1.4],
    [2.8, 0],
  ];
  theirs.forEach((key, i) => {
    const [dx, dy] = front[i % front.length];
    pos[key] = [clampX(x0 + d * dx), clampY(y0 + dy)];
  });
  return pos;
}

// --- La mêlée ---------------------------------------------------------------------------

// Mêlée introduite par `feed` en (x0, y0) : les deux paquets liés en 3-4-1, piliers
// gauches face aux piliers droits, le demi qui introduit côté gauche de son paquet, les
// trois-quarts à cinq mètres derrière le dernier pied.
export function scrum(present, { feed, x0: rawX, y0: rawY }) {
  const F = feed;
  const D = other(F);
  const d = dir(F);
  const x0 = clamp(rawX, 5, 95);
  const y0 = clamp(rawY, 15, WIDTH - 15);
  const L = leftOf(F);
  const sh = new Shape(present);
  const pack = (team, sign) => {
    const left = leftOf(team);
    const X = (m) => x0 - sign * d * m;
    sh.set(team, 1, X(0.55), y0 + left * 0.75);
    sh.set(team, 2, X(0.55), y0);
    sh.set(team, 3, X(0.55), y0 - left * 0.75);
    sh.set(team, 4, X(1.45), y0 + left * 0.38);
    sh.set(team, 5, X(1.45), y0 - left * 0.38);
    sh.set(team, 6, X(1.3), y0 + left * 1.3);
    sh.set(team, 7, X(1.3), y0 - left * 1.3);
    sh.set(team, 8, X(2.3), y0);
  };
  pack(F, 1);
  pack(D, -1);
  sh.set(F, 9, x0 - d * 0.1, y0 + L * 1.9);
  sh.set(D, 9, x0 + d * 0.5, y0 + L * 2.0);
  const o = y0 <= MID_Y ? 1 : -1;
  const W = o > 0 ? WIDTH - y0 : y0;
  const B = WIDTH - W;
  const F_ = (n, back, l) => sh.set(F, n, x0 - d * back, y0 + o * l);
  const D_ = (n, back, l) => sh.set(D, n, inGoal(F, x0 + d * back), y0 + o * l);
  F_(10, 8, 7);
  F_(12, 9.5, 13);
  F_(13, 11, 19.5);
  F_(wingOn(F, o), 11.5, W - 4);
  F_(15, 15, W * 0.5);
  if (B >= 13) F_(wingOn(F, -o), 9, -(B - 4));
  else F_(wingOn(F, -o), 20, W * 0.3);
  D_(10, 7.6, 7);
  D_(12, 7.7, 13);
  D_(13, 7.8, 19.5);
  D_(wingOn(D, o), 9, W - 5);
  if (B >= 13) D_(wingOn(D, -o), 8.5, -(B - 5));
  else D_(wingOn(D, -o), 18, W * 0.25);
  D_(15, 22, W * 0.4);
  sh.pos.ref = [clampX(x0 - d * 0.3), clampY(y0 + L * 3.3)];
  return { pos: sh.pos, ball: { holder: keyOf(F, 9) }, down: [], x0, y0, o };
}

// --- Coups de pied ----------------------------------------------------------------------

// Coup d'envoi de `kicker` (l'équipe) depuis le centre, vers le côté `ks` (+1 ou -1 sur y) :
// les chasseurs alignés derrière la ligne médiane, les avants du côté du coup de pied ;
// en face, les sauteurs et leurs lifteurs entre 10 et 22 m, les trois-quarts en profondeur.
export function kickoff(present, { kicker, ks }) {
  const K = kicker;
  const Rc = other(K);
  const d = dir(K);
  const sh = new Shape(present);
  const kickerNo = [10, 15, 12, 9].find((n) => sh.has(K, n));
  if (kickerNo) sh.set(K, kickerNo, 50 - d * 3.5, MID_Y - ks * 1.5);
  const chasers = [...FORWARDS, 9].filter((n) => n !== kickerNo && sh.has(K, n));
  chasers.forEach((n, i) => sh.set(K, n, 50 - d * 1.2, MID_Y + ks * (4.5 + i * 3.6)));
  [12, 13, wingOn(K, -ks), 11 + 14 - wingOn(K, -ks)]
    .filter((n) => n !== kickerNo && sh.has(K, n))
    .forEach((n, i) => sh.set(K, n, 50 - d * 1.2, MID_Y - ks * (5 + i * 7.5)));
  if (kickerNo !== 15) sh.set(K, 15, 50 - d * 24, MID_Y);
  const R_ = (n, m, l) => sh.set(Rc, n, 50 + d * m, MID_Y + ks * l);
  R_(4, 13, 17);
  R_(1, 12.4, 15.6);
  R_(3, 12.4, 18.4);
  R_(5, 16.5, 25);
  R_(2, 16, 23.6);
  R_(6, 16, 26.4);
  R_(7, 11.5, 8);
  R_(8, 19.5, 11);
  R_(9, 21, 17);
  R_(10, 27, -2);
  R_(12, 24, -11);
  R_(13, 24, -21);
  R_(wingOn(Rc, ks), 31, 29);
  R_(wingOn(Rc, -ks), 31, -29);
  R_(15, 40, 0);
  sh.pos.ref = [50 + d * 4, MID_Y + ks * 10];
  return { pos: sh.pos, ball: { at: [50, MID_Y] }, down: [], kicker: kickerNo ? keyOf(K, kickerNo) : null };
}

// Coup de pied au but de `team` (pénalité) : le ballon sur son tee à `mark`, le buteur
// en retrait pour son élan, ses partenaires derrière lui, la défense dans son en-but.
export function kickAtGoal(present, { team, mark, kicker, seed = 1 }) {
  const R = seeded(seed * 104729 + 7);
  const d = dir(team);
  const D = other(team);
  const goal = goalOf(team);
  const tee = [clampX(mark[0]), clamp(mark[1], 8, WIDTH - 8)];
  const sh = new Shape(present);
  const side = tee[1] < MID_Y ? -1 : 1;
  if (kicker) sh.setKey(kicker, [tee[0] - d * 3.4, tee[1] + side * 1.8]);
  for (const n of [...present[team]]) {
    const key = keyOf(team, n);
    if (key === kicker) continue;
    sh.set(team, n, tee[0] - d * (7 + R() * 15), tee[1] + (R() - 0.5) * 34);
  }
  for (const n of [...present[D]]) sh.set(D, n, goal + d * (1 + R() * 6.5), MID_Y + (R() - 0.5) * 46);
  sh.pos.ref = [clampX(tee[0] - d * 5), clampY(tee[1] - side * 7)];
  return { pos: sh.pos, ball: { at: tee }, down: [], tee };
}

// Transformation après un essai aplati à la hauteur `tryY` : le tee dans l'axe, d'autant
// plus loin que l'essai est excentré ; la défense sur sa ligne, prête à charger.
export function conversionSetup(present, { team, tryY, kicker, seed = 1 }) {
  const R = seeded(seed * 15485863 + 3);
  const d = dir(team);
  const D = other(team);
  const goal = goalOf(team);
  const y = clamp(tryY, 6, WIDTH - 6);
  const distance = 10 + Math.abs(y - MID_Y) * 0.35 + R() * 4;
  const tee = [goal - d * distance, y];
  const sh = new Shape(present);
  if (kicker) sh.setKey(kicker, [tee[0] - d * 3.2, tee[1] + (y < MID_Y ? -1.6 : 1.6)]);
  const defenders = [...present[D]];
  defenders.forEach((n, i) => {
    const spread = (i / Math.max(1, defenders.length - 1) - 0.5) * 30;
    sh.set(D, n, goal + d * (0.6 + R() * 1.4), MID_Y + spread + (R() - 0.5) * 2);
  });
  for (const n of [...present[team]]) {
    const key = keyOf(team, n);
    if (key === kicker) continue;
    sh.set(team, n, tee[0] - d * (8 + R() * 24), y + (R() - 0.5) * 36);
  }
  sh.pos.ref = [clampX(tee[0] - d * 2), clampY(y + (y < MID_Y ? 6 : -6))];
  return { pos: sh.pos, ball: { at: tee }, down: [], tee };
}

// Un ballon de coup de pied qui redescend sur `receiver` (de `team`) en `spot` : ses
// partenaires autour de lui ou qui reviennent, les chasseurs adverses lancés à `chase`
// mètres de lui.
export function underTheBall(present, { team, receiver, spot, chase = 14, seed = 1 }) {
  const R = seeded(seed * 3301 + 5);
  const d = dir(team);
  const K = other(team);
  const sh = new Shape(present);
  if (receiver) sh.setKey(receiver, spot);
  const [x0, y0] = spot;
  for (const n of [...present[team]]) {
    const key = keyOf(team, n);
    if (key === receiver) continue;
    if (n >= 9) sh.set(team, n, x0 + d * (2 + R() * 10), y0 + (R() - 0.5) * 34);
    else sh.set(team, n, x0 + d * (10 + R() * 16), y0 + (R() - 0.5) * 30);
  }
  const chasers = [...present[K]];
  chasers.forEach((n, i) => {
    const front = i < 9;
    sh.set(K, n, x0 + d * (front ? chase + R() * 3 : chase + 12 + R() * 14), y0 + (R() - 0.5) * (front ? 30 : 44));
  });
  sh.pos.ref = [clampX(x0 + d * (chase + 8)), clampY(y0 + 8)];
  return { pos: sh.pos, down: [] };
}
