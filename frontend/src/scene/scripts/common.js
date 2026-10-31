import * as THREE from "three";

import { BAR, GAP, UP, advanceBall, flyingBall } from "../ball.js";
import { ready, run } from "../rig.js";

// Outils des scènes : le temps (avancement d'un instant à un autre, lissé), les
// trajets des coureurs, les vols du ballon (passe, coup de pied à suivre, coup de pied
// au but rejoué par la physique de ball.js et réglé pour donner l'issue déjà tirée).

export const clamp = (x, a = 0, b = 1) => Math.min(b, Math.max(a, x));
export const smooth = (k) => {
  const c = clamp(k);
  return c * c * (3 - 2 * c);
};
// Où en est `s` entre `a` et `b`, de 0 à 1.
export const span = (s, a, b) => clamp((s - a) / (b - a));
export const lerp = (a, b, k) => a + (b - a) * k;
export const mix = (a, b, k) => a.map((value, i) => lerp(value, b[i], k));
// Le cap d'un joueur qui va de (x1, z1) vers (x2, z2).
export const headingTo = (x1, z1, x2, z2) => Math.atan2(x2 - x1, z2 - z1);
export const FACE_LINE = Math.PI; // tourné vers la ligne d'essai (z = 0)
export const FACE_FIELD = 0;

// Des images clés lissées : [[instant, [valeurs]], ...] -> valeurs à l'instant `s`.
export function keys(frames) {
  return (s) => {
    if (s <= frames[0][0]) return frames[0][1];
    for (let i = 1; i < frames.length; i++) {
      const [t1, v1] = frames[i];
      if (s <= t1) {
        const [t0, v0] = frames[i - 1];
        return mix(v0, v1, smooth((s - t0) / (t1 - t0)));
      }
    }
    return frames[frames.length - 1][1];
  };
}

// Un trajet en ligne brisée [[x, z], ...] : la position et le cap à une distance.
export function route(points) {
  const lengths = [0];
  for (let i = 1; i < points.length; i++) {
    lengths.push(lengths[i - 1] + Math.hypot(points[i][0] - points[i - 1][0], points[i][1] - points[i - 1][1]));
  }
  const total = lengths[lengths.length - 1];
  return {
    points,
    total,
    at(distance) {
      const d = clamp(distance, 0, total);
      let i = 1;
      while (i < points.length - 1 && lengths[i] < d) i++;
      const [x0, z0] = points[i - 1];
      const [x1, z1] = points[i];
      const k = (d - lengths[i - 1]) / Math.max(1e-6, lengths[i] - lengths[i - 1]);
      return { x: lerp(x0, x1, k), z: lerp(z0, z1, k), heading: headingTo(x0, z0, x1, z1) };
    },
  };
}

// Un coureur sur son trajet entre les instants `t0` et `t1` : il part à `from` de
// vitesse (0 : de l'arrêt, 1 : lancé) et finit à `to`. Il prend la pose de course
// (foulée réglée sur la distance parcourue) ; avant t0 il attend au départ, après t1 il
// est à l'arrivée. Rend sa position.
export function runner(player, path, s, t0, t1, { carry = "none", speed = 0.8, from = 1, to = 1, still } = {}) {
  const k = clamp((s - t0) / (t1 - t0));
  // Distance parcourue : vitesse qui passe de `from` à `to` (intégrée).
  const area = (u) => from * u + ((to - from) * u * u) / 2;
  const d = (path.total * area(k)) / Math.max(1e-6, area(1));
  const spot = path.at(d);
  player.place(spot.x, spot.z, spot.heading);
  const moving = s > t0 && (s < t1 || to > 0.05);
  if (moving) player.set(run(d / 2.3, speed, carry));
  else if (still) player.set(still);
  return spot;
}

// Le ballon porté par un joueur : sous le bras (`one`), à deux mains (`two`), au sol.
export function carried(player, kind = "one", out = new THREE.Vector3()) {
  if (kind === "two") return player.local(0, 1.12, 0.42, out);
  if (kind === "low") return player.local(0, 0.25, 0.55, out);
  return player.local(-0.24, 1.08, 0.18, out);
}

// Un vol en cloche de `a` à `b` (Vector3), qui monte de `height` au-dessus de la corde.
export function lob(a, b, height, k, out = new THREE.Vector3()) {
  out.lerpVectors(a, b, k);
  out.y += 4 * height * k * (1 - k);
  return out;
}

// Un coup de pied rasant qui rebondit : `bounces` rebonds de plus en plus bas.
export function grubber(a, b, k, bounces = 4, out = new THREE.Vector3()) {
  out.lerpVectors(a, b, 1 - (1 - k) * (1 - k) * 0.6 - 0.4 * (1 - k));
  const phase = k * bounces;
  const n = Math.floor(phase);
  out.y = 0.12 + Math.abs(Math.sin((phase - n) * Math.PI)) * 0.9 * 0.55 ** n;
  return out;
}

// La direction de la pointe d'un ballon en vol (il culbute autour de `axis`).
export function tumble(direction, angle) {
  const axis = new THREE.Vector3().crossVectors(direction, UP).normalize();
  return direction.clone().applyAxisAngle(axis, angle);
}

// --- Coups de pied rejoués par la physique ------------------------------------------

const RATE = 60;

// Tirage rejouable (mulberry32).
export function seeded(seed) {
  let a = seed >>> 0;
  return () => {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

// Le vol d'un ballon frappé de `from` à `velocity`, échantillonné 60 fois par seconde.
function simulate(from, velocity, wind, rng, limit = 4.5) {
  const ball = flyingBall(from, velocity);
  ball.spinAxis.crossVectors(velocity.clone().setY(0).normalize(), UP).normalize();
  ball.spin = Math.PI * 2 * 6;
  const samples = [ball.pos.clone()];
  const turns = [new THREE.Quaternion()];
  let cross = null;
  let land = null;
  const q = new THREE.Quaternion();
  for (let i = 1; i <= limit * RATE; i++) {
    advanceBall(ball, wind, 1 / RATE, {
      random: rng,
      onCross: (x, y) => (cross ??= { x, y, t: i / RATE, hit: ball.hit }),
      onLand: () => (land ??= i / RATE),
    });
    q.premultiply(new THREE.Quaternion().setFromAxisAngle(ball.spinAxis, ball.spin / RATE));
    samples.push(ball.pos.clone());
    turns.push(q.clone());
    if (land !== null && i / RATE > land + 1.2) break;
  }
  return { samples, turns, cross, land };
}

// Un coup de pied au but (pénalité, drop) qui donne l'issue voulue : entre les perches
// (`made`), ou à côté (`made` faux : à gauche ou à droite, selon `rng`). La frappe est
// réglée par essais : la hauteur au-dessus de la barre par la vitesse, l'écart par la
// direction (le vent dévie le ballon). `elevation` en degrés.
export function goalKick(from, wind, made, rng, { elevation = 33 } = {}) {
  const side = rng() < 0.5 ? -1 : 1;
  const aimX = made ? 0 : side * (GAP + 1.3 + rng() * 1.8);
  const angle = THREE.MathUtils.degToRad(elevation);
  // Rebonds rejouables : le même tirage à chaque essai.
  const seed = Math.floor(rng() * 4294967296);
  const bounces = () => seeded(seed);
  // On vise un point de la ligne d'essai, déplacé pour rattraper la dérive du vent.
  let target = aimX;
  let speed = 26;
  const velocity = () => {
    const yaw = Math.atan2(target - from.x, -from.z);
    return new THREE.Vector3(Math.sin(yaw) * Math.cos(angle), Math.sin(angle), Math.cos(yaw) * Math.cos(angle)).multiplyScalar(speed);
  };
  let flight = null;
  for (let pass = 0; pass < 3; pass++) {
    // La vitesse : passer la ligne d'essai 3 m au-dessus de la barre.
    let low = 12;
    let high = 36;
    for (let i = 0; i < 14; i++) {
      speed = (low + high) / 2;
      flight = simulate(from, velocity(), wind, bounces(), 4.5);
      if (flight.cross && flight.cross.y > BAR + 3) high = speed;
      else low = speed;
    }
    speed = high;
    flight = simulate(from, velocity(), wind, bounces(), 6);
    if (!flight.cross) break;
    // La direction : corriger la dérive du vent.
    target -= flight.cross.x - aimX;
  }
  // Sans rien de sûr (vent contraire trop fort), un ballon qui tombe court.
  if (made && !(flight.cross && Math.abs(flight.cross.x) < GAP - 0.3 && flight.cross.y > BAR)) {
    target = 0;
    speed = 34;
    flight = simulate(from, velocity(), wind, bounces(), 6);
  }
  return {
    duration: (flight.samples.length - 1) / RATE,
    crossAt: flight.cross?.t ?? flight.land ?? 2,
    // La position et l'orientation du ballon `t` secondes après la frappe.
    at(t, position, quaternion, rest) {
      const f = clamp(t * RATE, 0, flight.samples.length - 1);
      const i = Math.floor(f);
      const j = Math.min(i + 1, flight.samples.length - 1);
      position.lerpVectors(flight.samples[i], flight.samples[j], f - i);
      quaternion.copy(rest).premultiply(flight.turns[i]);
    },
    // Quelques points de la trajectoire, pour l'aperçu.
    points(until = 1.15) {
      const end = Math.min(flight.samples.length - 1, Math.round((flight.cross?.t ?? 2) * until * RATE));
      const out = [];
      for (let i = 0; i <= end; i += 6) out.push(flight.samples[i].toArray());
      return out;
    },
  };
}

// --- Le reste de la scène -------------------------------------------------------------

// Le plan de retransmission sur un point du terrain : en hauteur, de biais, depuis la
// tribune d'en face (côté -x). `far` éloigne la caméra.
export function broadcast(x, z, { far = 1, fov = 31, y = 0.6 } = {}) {
  return { pos: [x - 24 * far, 9.5 * far, z + 12 * far], look: [x * 0.85, y, z], fov };
}

// Un joueur d'une scène précédente qui n'a plus de rôle : il finit sa course en
// ralentissant (au sol, il y reste). `start` : sa place et son cap au début.
export function trail(player, s, start, until = 1.6) {
  if (start.down) return;
  const k = clamp(s / until);
  const d = start.speed * until * (k - (k * k) / 2);
  player.place(start.x + Math.sin(start.heading) * d, start.z + Math.cos(start.heading) * d, start.heading);
  player.set(k < 1 ? run(d / 2.3, 0.6 * (1 - k)) : ready(0.15));
}

// Où en est un joueur : de quoi le faire continuer (`trail`).
export const snapshot = (player, speed = 6) => ({
  x: player.root.position.x,
  z: player.root.position.z,
  heading: player.heading,
  speed,
  down: Math.abs(player.current.pitch) > 0.8,
});

// Le public et le son quand une action tourne pour nous (`good`) ou contre nous.
export function reaction(world, good) {
  if (good) {
    world.crowd("cheer", "us");
    world.sound(world.homeIsUs ? "roar" : "groan");
  } else {
    world.crowd(world.homeIsUs ? "seated" : "cheer", world.homeIsUs ? "us" : "them");
    world.sound(world.homeIsUs ? "groan" : "roar");
  }
}

// Une pénalité sifflée contre `team` ("us" ou "them") : son public la siffle s'il reçoit.
export function penaltyAgainst(world, team) {
  const home = (team === "us") === world.homeIsUs;
  world.sound("whistle", true);
  if (home) {
    world.crowd("boo", team);
    world.sound("boo");
  } else {
    world.crowd("standing");
  }
}
