import * as THREE from "three";

import { distance } from "../jersey.js";
import { inkOn } from "../clubs.js";

// Les joueurs des scènes de match : des personnages low-poly en boîtes articulées
// (bassin, buste, tête, bras et jambes en deux morceaux), aux couleurs de leur club,
// numéro dans le dos. Ils ne savent que prendre une pose (`Pose`, des angles) à une
// place (`place`) ; les scènes (scripts/) les animent en calculant leur pose à chaque
// instant, avec les poses de base ci-dessous (course, plaquage, plongeon, passe, coup
// de pied, saut en touche, poussée en mêlée, gestes de l'arbitre).
//
// Un joueur regarde vers +z dans son repère ; sa gauche est en +x.

const HIP_HEIGHT = 0.98;
const THIGH = 0.45;
const SHIN = 0.42;

// Une pose : angles en radians (positifs vers l'avant pour les bras, les jambes et le
// buste ; positifs vers l'extérieur pour l'écart des bras), `y` : le bassin monte ou
// descend, `pitch` et `roll` : tout le corps bascule (plongeon, plaquage, au sol).
export const REST = {
  y: 0,
  pitch: 0,
  roll: 0,
  lift: 0, // tout le corps monte (soulevé en touche, saut)
  lean: 0,
  twist: 0,
  nod: 0,
  turn: 0,
  armL: 0,
  armR: 0,
  abL: 0.08,
  abR: 0.08,
  elL: 0.2,
  elR: 0.2,
  legL: 0,
  legR: 0,
  knL: 0.05,
  knR: 0.05,
};

export const pose = (fields = {}) => ({ ...REST, ...fields });

export function mixPose(a, b, k) {
  const out = {};
  for (const key in REST) out[key] = a[key] + (b[key] - a[key]) * k;
  return out;
}

// --- Poses de base ---------------------------------------------------------------

// Debout, prêt : genoux fléchis, bras mi-tendus.
export const ready = (depth = 0.5) =>
  pose({ y: -0.12 * depth, lean: 0.25 * depth, legL: 0.35 * depth, legR: 0.3 * depth, knL: 0.6 * depth, knR: 0.55 * depth, armL: 0.5 * depth, armR: 0.5 * depth, elL: 0.9, elR: 0.9 });

// Course : `phase` en tours de foulée, `speed` de 0 (trot) à 1 (sprint). `carry` :
// "none", "one" (ballon sous le bras droit), "two" (à deux mains, prêt à passer).
export function run(phase, speed = 0.7, carry = "none") {
  const s = Math.sin(phase * Math.PI * 2);
  const c = Math.cos(phase * Math.PI * 2);
  const stride = 0.45 + 0.5 * speed;
  const p = pose({
    y: -0.04 - 0.05 * Math.abs(c) * speed,
    lean: 0.18 + 0.22 * speed,
    legL: s * stride,
    legR: -s * stride,
    knL: 0.3 + Math.max(0, -s) * (0.9 + speed) + 0.2,
    knR: 0.3 + Math.max(0, s) * (0.9 + speed) + 0.2,
    armL: -s * stride * 0.9,
    armR: s * stride * 0.9,
    elL: 1.3,
    elR: 1.3,
    twist: s * 0.12 * speed,
  });
  if (carry === "one") Object.assign(p, { armR: 0.35, elR: 1.9, abR: 0.15 });
  if (carry === "two") Object.assign(p, { armL: 0.75, armR: 0.75, elL: 1.1, elR: 1.1, abL: -0.15, abR: -0.15, twist: 0 });
  return p;
}

// Plaquage : `k` de 0 (élan) à 1 (au sol, bras serrés).
export function tackle(k) {
  const dive = Math.min(1, k * 1.4);
  return pose({
    pitch: 1.35 * dive,
    y: -0.55 * dive,
    lean: 0.5 - 0.3 * dive,
    armL: 1.2 + 0.4 * dive,
    armR: 1.2 + 0.4 * dive,
    abL: -0.25,
    abR: -0.25,
    elL: 0.8,
    elR: 0.8,
    legL: 0.4 - 0.9 * dive,
    legR: -0.5 * dive,
    knL: 0.7 - 0.4 * dive,
    knR: 0.5,
    nod: -0.4 * dive,
  });
}

// Plongeon pour aplatir : `k` de 0 (dernière foulée) à 1 (couché, ballon au sol).
export function dive(k) {
  const d = Math.min(1, k * 1.25);
  return pose({
    pitch: 1.5 * d,
    y: -0.62 * d,
    lift: Math.sin(Math.min(1, k * 1.6) * Math.PI) * 0.45,
    lean: 0.3 * (1 - d),
    armL: 0.6 + 2.2 * d,
    armR: 0.6 + 2.2 * d,
    abL: -0.2,
    abR: -0.2,
    elL: 0.3,
    elR: 0.3,
    legL: -0.3 * d,
    legR: -0.5 * d,
    knL: 0.3,
    knR: 0.5,
    nod: -0.6 * d,
  });
}

// Au sol, face contre terre (plaqué), ou sur le dos.
export const ground = (back = false) =>
  pose({ pitch: back ? -1.5 : 1.52, y: -0.8, armL: back ? 0.2 : 2.6, armR: back ? 0.4 : 2.3, abL: 0.3, abR: 0.3, legL: -0.1, legR: 0.15, knL: 0.3, knR: 0.1, nod: back ? 0.3 : -0.5 });

// Passe : `k` de 0 (ballon armé sur la hanche opposée) à 1 (bras tendus vers la cible),
// `side` : 1 vers sa gauche, -1 vers sa droite.
export function pass(k, side = 1) {
  const swing = Math.sin(k * Math.PI * 0.5);
  return pose({
    y: -0.08,
    lean: 0.3,
    twist: side * (-0.6 + 1.3 * swing),
    armL: 0.9,
    armR: 0.9,
    abL: -0.2 + (side > 0 ? 0.6 * swing : 0),
    abR: -0.2 + (side < 0 ? 0.6 * swing : 0),
    elL: 0.9 - 0.7 * swing,
    elR: 0.9 - 0.7 * swing,
    legL: 0.35,
    legR: -0.25,
    knL: 0.5,
    knR: 0.4,
    turn: side * 0.5 * swing,
  });
}

// Coup de pied (jambe droite) : `k` de 0 (pied d'appui posé, jambe armée) à 1 (fin du
// geste, jambe haute). `drop` : le ballon lâché des deux mains, plus droit.
export function kick(k, drop = false) {
  const back = Math.max(0, 0.35 - k) / 0.35; // jambe armée
  const through = Math.max(0, k - 0.35) / 0.65; // jambe lancée
  return pose({
    y: -0.05,
    lean: drop ? 0.15 : -0.1 + 0.25 * back,
    legL: 0.1,
    knL: 0.25,
    legR: -0.9 * back + 1.7 * through,
    knR: 1.2 * back + 0.1 * (1 - through),
    armL: drop ? 0.6 * back : 0.3,
    armR: drop ? 0.6 * back : -0.3,
    abL: drop ? 0.3 : 1.1,
    abR: drop ? 0.3 : 0.6,
    elL: 0.3,
    elR: 0.3,
    nod: 0.35,
    twist: -0.15 * through,
  });
}

// Saut en touche : bras tendus au-dessus de la tête (`k` de 0 à 1 : bras levés).
export const jump = (k) => pose({ armL: 3 * k, armR: 3 * k, abL: -0.1, abR: -0.1, elL: 0.1, elR: 0.1, legL: 0.1, legR: -0.05, knL: 0.2 + 0.4 * (1 - k), knR: 0.3 });

// Lifteur : il porte le sauteur, bras levés en appui sous lui.
export const lifter = (k) => pose({ y: -0.2 * (1 - k), lean: 0.3 * (1 - k), armL: 2.6 * k + 0.6, armR: 2.6 * k + 0.6, abL: -0.3, abR: -0.3, elL: 0.6, elR: 0.6, legL: 0.3 * (1 - k), legR: 0.3 * (1 - k), knL: 0.7 * (1 - k), knR: 0.7 * (1 - k) });

// Liés en mêlée ou en maul : buste à l'horizontale, jambes fléchies en poussée. `drive`
// fait pousser les jambes à tour de rôle.
export function bind(phase = 0, drive = 0, low = 1) {
  const s = Math.sin(phase * Math.PI * 2) * drive;
  return pose({
    y: -0.32 * low,
    lean: 1.25 * low,
    armL: 1.5,
    armR: 1.5,
    abL: 0.45,
    abR: 0.45,
    elL: 0.6,
    elR: 0.6,
    legL: 0.95 * low + s * 0.35,
    legR: 0.95 * low - s * 0.35,
    knL: 1.1 * low - s * 0.4,
    knR: 1.1 * low + s * 0.4,
    nod: -0.6 * low,
  });
}

// Accroupi au-dessus du ballon (ruck, demi de mêlée qui ramasse).
export const crouch = (k = 1) =>
  pose({ y: -0.42 * k, lean: 1.0 * k, legL: 1.2 * k, legR: 0.9 * k, knL: 1.8 * k, knR: 1.6 * k, armL: 1.3 * k, armR: 1.3 * k, elL: 0.3, elR: 0.3, nod: -0.3 * k });

// Joie : bras levés ; `phase` le fait sauter sur place.
export const cheer = (phase = 0) =>
  pose({ lift: Math.max(0, Math.sin(phase * Math.PI * 2)) * 0.18, armL: 2.9, armR: 2.7, abL: 0.35, abR: 0.35, elL: 0.15, elR: 0.25, knL: 0.2, knR: 0.2 });

// Déception : mains sur les hanches, tête basse.
export const dejected = () => pose({ armL: -0.2, armR: -0.2, abL: 0.5, abR: 0.5, elL: 1.9, elR: 1.9, nod: 0.55 });

// Arbitre : le sifflet à la bouche, le bras levé pour une pénalité (vers sa gauche ou
// sa droite), ou tendu vers le ciel avec le carton.
export const whistle = (k = 1) => pose({ armR: 1.6 * k, abR: -0.35 * k, elR: 2.2 * k, nod: -0.05 });
export const signal = (side = 1, k = 1) =>
  side > 0 ? pose({ armL: 2.0 * k, abL: 0.7 * k, elL: 0.05 }) : pose({ armR: 2.0 * k, abR: 0.7 * k, elR: 0.05 });
export const card = (k = 1) => pose({ armR: 3.05 * k, abR: 0.1, elR: 0.05, nod: -0.25 * k });
export const tryAward = (k = 1) => pose({ armR: 3.1 * k, abR: 0.05, elR: 0, nod: -0.1 });

// --- Maillots ---------------------------------------------------------------------

const canvasOf = (width, height) => Object.assign(document.createElement("canvas"), { width, height });

// Le motif d'un maillot sur un pan du buste : cerceaux, rayures, moitiés...
function paintPattern(ctx, jersey, w, h, side) {
  ctx.fillStyle = jersey.base;
  ctx.fillRect(0, 0, w, h);
  ctx.fillStyle = jersey.motif;
  switch (jersey.pattern) {
    case "hoops":
      for (let y = 0; y < h; y += h / 4) ctx.fillRect(0, y, w, h / 8);
      break;
    case "stripes":
      for (let x = 0; x < w; x += w / 4) ctx.fillRect(x, 0, w / 8, h);
      break;
    case "band":
      ctx.fillRect(0, h * 0.38, w, h * 0.22);
      break;
    case "halves":
    case "quarters":
      if (side === "front") ctx.fillRect(w / 2, 0, w / 2, h);
      else ctx.fillRect(0, 0, w / 2, h);
      break;
    case "sash":
      ctx.beginPath();
      ctx.moveTo(0, h * 0.1);
      ctx.lineTo(w * 0.25, 0);
      ctx.lineTo(w, h * 0.75);
      ctx.lineTo(w * 0.75, h);
      ctx.closePath();
      ctx.fill();
      break;
    case "chevron":
      ctx.beginPath();
      ctx.moveTo(0, h * 0.2);
      ctx.lineTo(w / 2, h * 0.5);
      ctx.lineTo(w, h * 0.2);
      ctx.lineTo(w, h * 0.42);
      ctx.lineTo(w / 2, h * 0.72);
      ctx.lineTo(0, h * 0.42);
      ctx.fill();
      break;
    case "yoke":
      ctx.fillRect(0, 0, w, h * 0.28);
      break;
    default:
      break;
  }
  ctx.fillStyle = jersey.trim;
  ctx.fillRect(w * 0.3, 0, w * 0.4, h * 0.07); // col
}

const textureOf = (canvas) => {
  const texture = new THREE.CanvasTexture(canvas);
  texture.colorSpace = THREE.SRGBColorSpace;
  texture.magFilter = THREE.NearestFilter;
  texture.minFilter = THREE.NearestFilter;
  return texture;
};

// Le maillot d'une équipe : ses matières (buste, manches, short, chaussettes), le dos
// numéroté se dessine joueur par joueur.
export function createKit(jersey, { shorts, socks } = {}) {
  const lambert = (color) => new THREE.MeshLambertMaterial({ color, flatShading: true });
  const front = canvasOf(32, 32);
  paintPattern(front.getContext("2d"), jersey, 32, 32, "front");
  const side = canvasOf(32, 32);
  paintPattern(side.getContext("2d"), jersey, 32, 32, "side");
  const shortsColor = shorts ?? (distance(jersey.trim, jersey.base) > 60 ? jersey.trim : "#16181B");
  return {
    jersey,
    front: new THREE.MeshLambertMaterial({ map: textureOf(front), flatShading: true }),
    side: new THREE.MeshLambertMaterial({ map: textureOf(side), flatShading: true }),
    sleeve: lambert(jersey.pattern === "plain" ? jersey.trim : jersey.base),
    shorts: lambert(shortsColor),
    socks: lambert(socks ?? jersey.base),
    backs: new Map(), // numéro -> matière du dos
  };
}

function backMaterial(kit, number) {
  if (kit.backs.has(number)) return kit.backs.get(number);
  const canvas = canvasOf(32, 32);
  const ctx = canvas.getContext("2d");
  paintPattern(ctx, kit.jersey, 32, 32, "back");
  if (number) {
    // Le numéro sur une pastille du fond quand le motif le rendrait illisible.
    if (kit.jersey.pattern !== "plain") {
      ctx.fillStyle = kit.jersey.base;
      ctx.fillRect(7, 8, 18, 18);
    }
    ctx.fillStyle = inkOn(kit.jersey.base);
    ctx.font = '700 18px "Barlow Condensed", "Arial Narrow", sans-serif';
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    ctx.fillText(String(number), 16, 18);
  }
  const material = new THREE.MeshLambertMaterial({ map: textureOf(canvas), flatShading: true });
  kit.backs.set(number, material);
  return material;
}

// --- Le personnage ------------------------------------------------------------------

const SKINS = ["#E8C4A8", "#D6A585", "#B9825C", "#8A5A3C", "#F0D2BC", "#6E452E"];
const HAIRS = ["#2A211B", "#4A3426", "#1B1B1B", "#8A6A45", "#3A2A20"];

const box = (w, h, d, y = 0, z = 0) => {
  const geometry = new THREE.BoxGeometry(w, h, d);
  geometry.translate(0, y, z);
  return geometry;
};

// Les formes, partagées par tous les joueurs.
const SHAPES = {
  pelvis: box(0.36, 0.2, 0.22),
  torso: box(0.46, 0.56, 0.26, 0.3),
  head: box(0.22, 0.25, 0.24, 0.14),
  hair: box(0.235, 0.08, 0.25, 0.27, -0.005),
  upperArm: box(0.13, 0.32, 0.13, -0.15),
  forearm: box(0.1, 0.3, 0.1, -0.15),
  thigh: box(0.18, THIGH, 0.19, -THIGH / 2),
  shin: box(0.13, SHIN, 0.14, -SHIN / 2),
  boot: box(0.12, 0.08, 0.27, -SHIN - 0.02, 0.05),
};

const shadowGeometry = new THREE.CircleGeometry(0.42, 12).rotateX(-Math.PI / 2);
const ringGeometry = new THREE.RingGeometry(0.5, 0.68, 20).rotateX(-Math.PI / 2);
const cardGeometry = box(0.12, 0.17, 0.02); // grossi : il doit se voir de la tribune

export class Player {
  // `kit` : createKit ; `number` : dans le dos ; `seed` : peau et cheveux ; `marker` :
  // couleur du repère au sol (le joueur incarné).
  constructor({ kit, number = null, seed = 0, marker = null, shared }) {
    const skin = shared.skin(SKINS[seed % SKINS.length]);
    const hair = shared.skin(HAIRS[(seed * 7 + 3) % HAIRS.length]);
    const boots = shared.skin("#16181B");
    const mesh = (geometry, material) => new THREE.Mesh(geometry, material);

    this.root = new THREE.Group();
    this.body = new THREE.Group(); // bascule entière (plongeon, plaquage)
    this.hips = new THREE.Group();
    this.hips.position.y = HIP_HEIGHT;
    this.spine = new THREE.Group();
    this.spine.position.y = 0.06;
    this.neck = new THREE.Group();
    this.neck.position.y = 0.6;
    const torsoMaterials = [kit.side, kit.side, kit.side, kit.side, kit.front, backMaterial(kit, number)];
    this.spine.add(mesh(SHAPES.torso, torsoMaterials), this.neck);
    this.neck.add(mesh(SHAPES.head, skin), mesh(SHAPES.hair, hair));

    const limb = (x, y, upper, lower, upperMaterial, lowerMaterial, parent, extra) => {
      const joint = new THREE.Group();
      joint.position.set(x, y, 0);
      const bend = new THREE.Group();
      bend.position.y = upper === SHAPES.thigh ? -THIGH : -0.31;
      joint.add(mesh(upper, upperMaterial), bend);
      bend.add(mesh(lower, lowerMaterial));
      if (extra) bend.add(mesh(extra, boots));
      parent.add(joint);
      return [joint, bend];
    };
    [this.shL, this.elbowL] = limb(0.3, 0.5, SHAPES.upperArm, SHAPES.forearm, kit.sleeve, skin, this.spine);
    [this.shR, this.elbowR] = limb(-0.3, 0.5, SHAPES.upperArm, SHAPES.forearm, kit.sleeve, skin, this.spine);
    [this.hipL, this.kneeL] = limb(0.1, -0.04, SHAPES.thigh, SHAPES.shin, kit.shorts, kit.socks, this.hips, SHAPES.boot);
    [this.hipR, this.kneeR] = limb(-0.1, -0.04, SHAPES.thigh, SHAPES.shin, kit.shorts, kit.socks, this.hips, SHAPES.boot);
    this.hips.add(mesh(SHAPES.pelvis, kit.shorts), this.spine);
    this.body.add(this.hips);

    // Carton jaune, dans la main de l'arbitre quand il le sort.
    this.card = mesh(cardGeometry, shared.skin("#F2C230"));
    this.card.position.set(0, -0.32, 0.03);
    this.card.visible = false;
    this.elbowR.add(this.card);

    this.shadow = mesh(shadowGeometry, shared.shadow);
    this.shadow.position.y = 0.012;
    this.root.add(this.body, this.shadow);
    if (marker) {
      this.marker = mesh(ringGeometry, new THREE.MeshBasicMaterial({ color: marker }));
      this.marker.position.y = 0.02;
      this.root.add(this.marker);
    }
    this.heading = 0;
    this.current = pose();
    this.root.traverse((object) => {
      object.matrixAutoUpdate = true;
    });
  }

  // À sa place (x, z), tourné vers `heading` (0 : vers +z ; π : vers la ligne d'essai).
  place(x, z, heading = this.heading) {
    this.root.position.set(x, 0, z);
    this.root.rotation.y = heading;
    this.heading = heading;
    return this;
  }

  // Un point du joueur dans le repère du terrain (x à sa gauche, y en haut, z devant).
  local(x, y, z, out = new THREE.Vector3()) {
    const c = Math.cos(this.heading);
    const s = Math.sin(this.heading);
    const { position } = this.root;
    return out.set(position.x + x * c + z * s, y + this.current.lift, position.z - x * s + z * c);
  }

  // Pose et respiration (`breath` : le temps, pour la poitrine qui se soulève).
  set(p, breath = null) {
    this.current = p;
    this.body.position.y = p.lift;
    this.body.rotation.set(p.pitch, 0, p.roll);
    // Basculé, le corps pivote autour des pieds : on le garde au-dessus du sol.
    this.body.position.y += Math.sin(Math.abs(p.pitch)) * 0.14;
    this.hips.position.y = HIP_HEIGHT + p.y;
    this.spine.rotation.set(p.lean, p.twist, 0);
    this.neck.rotation.set(p.nod, p.turn, 0);
    this.shL.rotation.set(-p.armL, 0, p.abL);
    this.shR.rotation.set(-p.armR, 0, -p.abR);
    this.elbowL.rotation.x = -p.elL;
    this.elbowR.rotation.x = -p.elR;
    this.hipL.rotation.x = -p.legL;
    this.hipR.rotation.x = -p.legR;
    this.kneeL.rotation.x = p.knL;
    this.kneeR.rotation.x = p.knR;
    if (breath !== null) {
      const b = Math.sin(breath * 2.4 + this.root.position.x) * 0.5 + 0.5;
      this.spine.scale.set(1 + b * 0.025, 1, 1 + b * 0.05);
      this.spine.rotation.x += b * 0.03;
    } else {
      this.spine.scale.set(1, 1, 1);
    }
    // L'ombre rétrécit quand le joueur décolle.
    const air = Math.max(0, p.lift);
    this.shadow.scale.setScalar(Math.max(0.5, 1 - air * 0.5) * (Math.abs(p.pitch) > 0.8 ? 1.6 : 1));
    return this;
  }

  set visible(value) {
    this.root.visible = value;
  }
}

// Matières communes à tous les joueurs d'une scène (peaux, ombres), à libérer avec elle.
export function sharedMaterials() {
  const cache = new Map();
  return {
    skin(color) {
      if (!cache.has(color)) cache.set(color, new THREE.MeshLambertMaterial({ color, flatShading: true }));
      return cache.get(color);
    },
    shadow: new THREE.MeshBasicMaterial({ color: 0x0b120d, transparent: true, opacity: 0.38, depthWrite: false }),
  };
}

// La tenue de l'arbitre : une couleur qu'aucune des deux équipes ne porte, le jaune en
// dernier (le carton doit se détacher sur le maillot).
export function refereeJersey(kits) {
  const candidates = ["#16181B", "#5B2A86", "#6CACE4", "#E35205", "#F2C230"];
  const far = candidates.find((c) => kits.every((kit) => distance(c, kit.base) > 140 && distance(c, kit.motif) > 110));
  const base = far ?? "#5B2A86";
  return { pattern: "plain", base, motif: base, trim: base === "#16181B" ? "#F2C230" : "#16181B" };
}
