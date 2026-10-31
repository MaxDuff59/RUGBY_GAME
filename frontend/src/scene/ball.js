import * as THREE from "three";

// Le ballon, son tee et les poteaux, communs au coup de pied de la page de connexion
// (KickScene) et aux scènes de match (src/scene) : les mesures, le cuir, et la
// physique du vol (freiné par l'air, poussé par le vent, renvoyé par les montants et
// la barre, rebonds de travers sur l'herbe).
//
// Repère : x vers la droite, y en haut ; la ligne d'essai est en z = 0 et le terrain
// s'étend vers +z. Les longueurs sont en mètres.

export const GAP = 2.8; // demi-écart intérieur des poteaux (5,6 m)
export const BAR = 3; // dessus de la barre
export const POST_HEIGHT = 16;
export const POST_R = 0.065;
export const PAD_R = 0.3;
export const PAD_H = 2;

export const BALL_A = 0.15; // demi-longueur du ballon
export const BALL_B = 0.095; // demi-largeur
export const BALL_R = 0.12; // rayon retenu pour les chocs
export const TEE_TOP = 0.062;

export const G = 9.81;
export const DRAG = 0.012; // ½ ρ Cx S / m : un ballon frappé à 33 m/s retombe vers 55 m
export const STEP = 1 / 240;

export const UP = new THREE.Vector3(0, 1, 0);

const canvasOf = (width, height) => Object.assign(document.createElement("canvas"), { width, height });

// Cuir du ballon, déplié (largeur : le tour du ballon, hauteur : d'une pointe à
// l'autre) : quatre panneaux cousus et, sur chacun, une vague bleu nuit liserée d'or
// qui s'effile vers les pointes. Le relief (picots, coutures creusées) à part.
export function ballCanvases() {
  const width = 1024;
  const height = 512;
  const color = canvasOf(width, height);
  const bump = canvasOf(width, height);
  const ctx = color.getContext("2d");
  const relief = bump.getContext("2d");
  ctx.fillStyle = "#f1ede3";
  ctx.fillRect(0, 0, width, height);
  relief.fillStyle = "#808080";
  relief.fillRect(0, 0, width, height);

  const panel = width / 4;
  for (let p = 0; p < 4; p++) {
    for (let y = 0; y < height; y++) {
      const s = (y / (height - 1)) * 2 - 1;
      const half = 24 * (1 - (s / 0.8) ** 4);
      if (half <= 0) continue;
      const center = p * panel + panel / 2 + Math.sin(s * 3.2 + p * 1.9) * 46;
      if (p & 1) {
        ctx.fillStyle = "#c8a35c";
        ctx.fillRect(center - half * 0.55, y, half * 1.1, 1);
      } else {
        ctx.fillStyle = "#c8a35c";
        ctx.fillRect(center - half - 5, y, half * 2 + 10, 1);
        ctx.fillStyle = "#1d2b45";
        ctx.fillRect(center - half, y, half * 2, 1);
      }
    }
  }
  relief.fillStyle = "#a6a6a6";
  for (let y = 4; y < height; y += 9) {
    for (let x = (y % 18 === 4 ? 0 : 4.5); x < width; x += 9) {
      relief.beginPath();
      relief.arc(x, y, 2.2, 0, Math.PI * 2);
      relief.fill();
    }
  }
  for (let p = 0; p <= 4; p++) {
    const x = p * panel;
    ctx.fillStyle = "#5c5954";
    ctx.fillRect(x - 2, 0, 4, height);
    relief.fillStyle = "#2a2a2a";
    relief.fillRect(x - 4, 0, 8, height);
  }
  return { color, bump };
}

// Ballon : une sphère étirée, aux pointes plus effilées qu'un ellipsoïde ; normales
// calculées d'après la forme exacte (celles d'un maillage seraient fausses aux pointes).
// `segments` : 72 × 48 en gros plan, bien moins dans une scène vue de loin.
export function ballGeometry(widthSegments = 72, heightSegments = 48) {
  const E = 0.68;
  const geometry = new THREE.SphereGeometry(1, widthSegments, heightSegments);
  const position = geometry.attributes.position;
  const normal = geometry.attributes.normal;
  for (let i = 0; i < position.count; i++) {
    const y = position.getY(i);
    const ring = Math.sqrt(Math.max(0, 1 - y * y));
    const cos = ring > 1e-6 ? position.getX(i) / ring : 0;
    const sin = ring > 1e-6 ? position.getZ(i) / ring : 0;
    const base = Math.max(0, 1 - y * y);
    const rho = base ** E;
    position.setXYZ(i, cos * rho * BALL_B, y * BALL_A, sin * rho * BALL_B);
    if (base < 1e-6) {
      normal.setXYZ(i, 0, Math.sign(y), 0);
    } else {
      const slope = -2 * E * y * base ** (E - 1);
      const n = new THREE.Vector3(cos * BALL_A, -slope * BALL_B, sin * BALL_A).normalize();
      normal.setXYZ(i, n.x, n.y, n.z);
    }
  }
  return geometry;
}

// Tee de buteur en plastique : un socle évasé, une coupelle où se pose la pointe.
export function teeGeometry() {
  const profile = [
    [0, 0],
    [0.075, 0],
    [0.076, 0.006],
    [0.056, 0.012],
    [0.031, 0.045],
    [0.035, 0.06],
    [0.045, 0.069],
    [0.041, 0.072],
    [0.026, 0.064],
    [0, TEE_TOP],
  ].map(([x, y]) => new THREE.Vector2(x, y));
  return new THREE.LatheGeometry(profile, 40);
}

// Un ballon en vol : position, vitesse, rotation (axe et vitesse angulaire), s'il a
// touché un montant ou la barre, et s'il est déjà retombé.
export function flyingBall(pos, vel) {
  return {
    pos: pos.clone(),
    vel: vel.clone(),
    spinAxis: new THREE.Vector3(1, 0, 0),
    spin: 0,
    hit: null, // "poteau" | "barre"
    landed: false,
  };
}

// Choc contre un cylindre vertical (montant, protection) ou contre la barre.
function bounceOff(ball, nx, ny, nz, depth, random) {
  const { pos, vel } = ball;
  const vn = vel.x * nx + vel.y * ny + vel.z * nz;
  pos.x += nx * depth;
  pos.y += ny * depth;
  pos.z += nz * depth;
  if (vn >= 0) return;
  vel.x -= 1.5 * vn * nx;
  vel.y -= 1.5 * vn * ny;
  vel.z -= 1.5 * vn * nz;
  vel.multiplyScalar(0.85);
  ball.spinAxis.set(random() - 0.5, random() - 0.5, random() - 0.5).normalize();
}

function collide(ball, random) {
  const p = ball.pos;
  for (const side of [-1, 1]) {
    const x = side * (GAP + POST_R);
    for (const [radius, top] of [
      [POST_R, POST_HEIGHT],
      [PAD_R, PAD_H],
    ]) {
      if (p.y > top + BALL_R) continue;
      const dx = p.x - x;
      const dz = p.z;
      const distance = Math.hypot(dx, dz);
      const reach = radius + BALL_R;
      if (distance < reach && distance > 0) {
        bounceOff(ball, dx / distance, 0, dz / distance, reach - distance, random);
        ball.hit = "poteau";
      }
    }
  }
  if (Math.abs(p.x) < GAP + POST_R) {
    const dy = p.y - (BAR - POST_R);
    const dz = p.z;
    const distance = Math.hypot(dy, dz);
    const reach = POST_R + BALL_R;
    if (distance < reach && distance > 0) {
      bounceOff(ball, 0, dy / distance, dz / distance, reach - distance, random);
      ball.hit = "barre";
    }
  }
}

// Fait voler le ballon pendant `dt` secondes, par pas de STEP. `onCross(x, y)` : il
// passe la ligne d'essai (à cette hauteur, à cet écart du milieu des poteaux) ;
// `onLand()` : il touche l'herbe pour la première fois. `boards(ball)` : les panneaux
// du stade qui le renvoient. `random` : le hasard des rebonds (Math.random, ou un
// tirage rejouable).
export function advanceBall(ball, wind, dt, { onCross, onLand, boards, random = Math.random } = {}) {
  const relative = new THREE.Vector3();
  const before = new THREE.Vector3();
  for (let t = 0; t < dt; t += STEP) {
    before.copy(ball.pos);
    relative.copy(ball.vel).sub(wind);
    const drag = DRAG * relative.length();
    ball.vel.addScaledVector(relative, -drag * STEP);
    ball.vel.y -= G * STEP;
    ball.pos.addScaledVector(ball.vel, STEP);
    collide(ball, random);
    boards?.(ball);
    if (before.z > 0 && ball.pos.z <= 0 && !ball.landed) {
      const k = before.z / (before.z - ball.pos.z);
      onCross?.(before.x + (ball.pos.x - before.x) * k, before.y + (ball.pos.y - before.y) * k);
    }
    // Rebond sur l'herbe, de travers comme un ballon ovale ; posé, il roule.
    if (ball.pos.y < BALL_B && ball.vel.y < 0) {
      if (!ball.landed) onLand?.();
      ball.landed = true;
      ball.pos.y = BALL_B;
      if (ball.vel.y > -1) {
        ball.vel.y = 0;
      } else {
        ball.vel.y = -ball.vel.y * 0.45;
        const turn = (random() - 0.5) * 0.9;
        const { x, z } = ball.vel;
        ball.vel.x = (x * Math.cos(turn) - z * Math.sin(turn)) * 0.7;
        ball.vel.z = (x * Math.sin(turn) + z * Math.cos(turn)) * 0.7;
        ball.spin *= 0.6;
        ball.spinAxis.set(random() - 0.5, random() - 0.5, random() - 0.5).normalize();
      }
    }
    if (ball.landed && ball.pos.y <= BALL_B + 1e-4) {
      ball.vel.x *= 1 - 1.2 * STEP;
      ball.vel.z *= 1 - 1.2 * STEP;
      ball.spin *= 1 - 2 * STEP;
    }
  }
}
