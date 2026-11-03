import * as THREE from "three";

import { BALL_A, BAR, GAP, TEE_TOP } from "../ball.js";
import { TOUCH } from "../field.js";
import { cheer, crouch, dejected, ground, kick, mixPose, pose, ready, run, signal, tackle, tryAward } from "../rig.js";
import { FACE_FIELD, FACE_LINE, broadcast, carried, goalKick, grubber, headingTo, keys, lerp, lob, reaction, route, runner, seeded, smooth, span } from "./common.js";

// Carrière de joueur, « Pénalité lointaine » (long_penalty) : pénalité pour nous à 45 m,
// le joueur incarné a le ballon, la défense recule de dix mètres, le dos tourné. Viser
// les perches (la physique de ball.js ; raté, le ballon retombe court, devant elles),
// jouer la touche (dans leurs 22, ou le ballon reste en jeu), ou la jouer vite (ils
// ont le dos tourné : il file, et l'action s'enchaîne sur le deux contre un).
//
// Ratée, la touche se joue selon l'effet tiré : `lost` (leur ailier relance), sinon notre
// ailier récupère un ballon mal placé.

const v = (x = 0, y = 0, z = 0) => new THREE.Vector3(x, y, z);
const ARC = (a, b, height, steps = 16) => {
  const out = [];
  for (let i = 0; i <= steps; i++) out.push(lob(a, b, height, i / steps).toArray());
  return out;
};
// Le ballon qui passe du sol à ses mains (`k` de 0 à 1), ou l'inverse, sans à-coup.
const lift = (player, how, k, out) => out.lerpVectors(carried(player, "low", new THREE.Vector3()), carried(player, how, new THREE.Vector3()), smooth(k));
const HOLD = pose({ armL: 0.75, armR: 0.75, elL: 1.1, elR: 1.1, abL: -0.15, abR: -0.15, lean: 0.15, y: -0.05, knL: 0.2, knR: 0.2 });
const STAND = pose({ knL: 0.1, knR: 0.1 });

// Un coup réussi : goalKick, relevé si le vent de face le ferait tomber court ; sans rien
// de sûr, une cloche réglée à la main (le texte dit « entre les perches »).
function sureKick(from, wind, rng) {
  const p = v();
  const q = new THREE.Quaternion();
  const rest = new THREE.Quaternion();
  for (const elevation of [33, 39, 45]) {
    const flight = goalKick(from, wind, true, rng, { elevation });
    flight.at(flight.crossAt, p, q, rest);
    if (Math.abs(p.x) < GAP - 0.2 && p.y > BAR + 0.5) return flight;
  }
  const beyond = v((-from.x * 9) / from.z, 0.15, -9);
  const air = 3;
  return {
    crossAt: (air * from.z) / (from.z + 9),
    at(t, position, quaternion, start) {
      lob(from, beyond, 12, Math.min(1, t / air), position);
      quaternion.setFromAxisAngle(new THREE.Vector3(1, 0, 0), t * 12).multiply(start);
    },
  };
}

export function buildLongPenalty(world, data) {
  const rng = world.rng;
  const s = rng() < 0.5 ? -1 : 1; // la touche la plus proche, celle qu'il viserait
  const x0 = s * (7 + rng() * 6);
  const z0 = Math.sqrt(45 * 45 - x0 * x0); // à 45 m des perches
  const heroNo = data.hero ?? 10;
  const other = (n, alt) => (n === heroNo ? alt : n);
  const hero = world.player("us", heroNo, { hero: true });
  const twelve = world.player("us", other(12, 13));
  const nine = world.player("us", other(9, 10));
  const lock = world.player("us", other(4, 5));
  const wing = world.player("us", other(s > 0 ? 14 : 11, 15));
  // Leur ligne recule, avec un trou devant lui ; leur ailier couvre sa touche, un autre
  // garde l'en-but (pas leur 15 : le deux contre un enchaîné amène le sien).
  const lineZ = z0 - 9;
  const line = [[7, -3.6], [12, 3.6], [6, -10], [13, 10]].map(([n, dx]) => ({ player: world.player("them", n), x: x0 + s * dx }));
  const theirWing = world.player("them", s > 0 ? 11 : 14);
  const deep = world.player("them", s > 0 ? 14 : 11);
  const ref = world.player("ref");

  const mark = [x0, z0 + 0.4];
  const spots = {
    twelve: [x0 - s * 4.5, z0 + 2],
    nine: [x0 + s * 3.5, z0 + 3],
    lock: [x0 - s * 8.5, z0 + 1],
    wing: [s * 25, z0 + 1.5],
  };
  const wingAt = [s * 27, 31];
  const deepAt = [s * 2.5, 2.5];
  const refAt = [x0 + 7, z0 - 2.5];
  const ball = new THREE.Vector3();
  const shot = broadcast(x0, z0 - 3);
  const camera = keys([
    [0, [x0 - 52, 24, z0 + 30, x0 * 0.6, 0.5, z0 - 2, 44]],
    [1.5, [...shot.pos, ...shot.look, shot.fov]],
  ]);

  function setupFrame(t) {
    world.tee.visible = false;
    runner(hero, route([[x0 - s * 3.5, z0 + 5.5], mark]), t, 0, 1.3, { from: 0.7, to: 0.1, speed: 0.35, carry: "two" });
    if (t >= 1.3) hero.place(mark[0], mark[1], FACE_LINE).set(HOLD);
    runner(twelve, route([[spots.twelve[0], spots.twelve[1] + 3], spots.twelve]), t, 0, 1.5, { from: 0.5, to: 0.2, speed: 0.3 });
    runner(nine, route([[spots.nine[0], spots.nine[1] + 3], spots.nine]), t, 0, 1.5, { from: 0.5, to: 0.2, speed: 0.3 });
    runner(lock, route([[spots.lock[0], spots.lock[1] + 3], spots.lock]), t, 0, 1.5, { from: 0.5, to: 0.2, speed: 0.3 });
    runner(wing, route([[spots.wing[0], spots.wing[1] + 3], spots.wing]), t, 0, 1.5, { from: 0.5, to: 0.2, speed: 0.3 });
    // Ils reculent de dix mètres, le dos tourné : le trou et la tentation de la jouer vite.
    line.forEach(({ player, x }) => runner(player, route([[x, lineZ + 5.5], [x, lineZ]]), t, 0, 1.5, { from: 0.9, to: 0.5, speed: 0.35 }));
    runner(theirWing, route([[wingAt[0], wingAt[1] + 3], wingAt]), t, 0, 1.5, { from: 0.8, to: 0.4, speed: 0.35 });
    deep.place(...deepAt, FACE_FIELD).set(ready(0.2));
    // L'arbitre, le bras tendu vers notre attaque.
    ref.place(refAt[0], refAt[1], Math.PI / 2).set(signal(1, smooth(span(t, 0.15, 0.55))));
    world.ballAt(carried(hero, "two", ball), v(1, 0, 0));
    const [cx, cy, cz, lx, ly, lz, fov] = camera(t);
    return { pos: [cx, cy, cz], look: [lx, ly, lz], fov };
  }

  const setup = {
    duration: 1.5,
    frame: setupFrame,
    cues: [
      { at: 0.05, run: () => world.sound("whistle") },
      { at: 0.1, run: () => world.crowd(world.pressure > 1 ? "standing" : "seated") },
    ],
  };

  // Les voies : le tee sur la marque, le point de sortie en touche, le trou dans leur ligne.
  const teePoint = v(x0, TEE_TOP * 1.4 + BALL_A * 1.1, z0);
  const touchOut = v(s * (TOUCH + 2), 0.4, 14);
  const tapEnd = 25.5;
  const tapLine = [mark, [x0 + s * 0.3, lineZ + 3], [x0, lineZ], [x0, tapEnd]];
  const wide = { pos: [x0 * 0.6 - 34, 26, z0 + 14], look: [x0 * 0.4, -3.5, z0 * 0.5], fov: 44 };
  let aimed = null;

  function preview(key) {
    const draw = world.draw;
    if (key === "posts") {
      aimed ??= goalKick(teePoint, world.wind, true, seeded(7));
      const points = aimed.points(1.1);
      // La courbe dans l'air, et son ombre sur la pelouse jusqu'aux perches.
      return [draw.arc(points), draw.path(points.map(([x, , z]) => [x, z]), { width: 0.3 }), draw.mark([0, 0], 1.2)];
    }
    if (key === "touch_kick") {
      const from = v(mark[0], 1.1, mark[1]);
      return [draw.arc(ARC(from, touchOut, 13)), draw.mark([s * TOUCH, touchOut.z], 1.2)];
    }
    return [draw.path(tapLine), draw.mark([x0, tapEnd + 1])];
  }

  // Ceux de la mise en place finissent de reculer et se retournent pour regarder.
  const lookBack = (player, x, z, t) => {
    const k = span(t, 0.1, 0.8);
    player.place(x, z - 0.8 * smooth(k), lerp(FACE_LINE, FACE_FIELD, smooth(k))).set(k < 1 ? run(t * 1.2, 0.1) : ready(0.15));
  };
  const lineWatches = (t) => {
    line.forEach(({ player, x }) => lookBack(player, x, lineZ, t));
  };
  const refDown = (t) => ref.set(signal(1, 1 - smooth(span(t, 0, 0.4))));

  // --- Les perches ---------------------------------------------------------------------
  function postsOutcome(result) {
    const made = result.success;
    const flight = made ? sureKick(teePoint, world.wind, rng) : null;
    const kickAt = 2.35;
    // Raté : un lob court qui retombe à quelques mètres de la ligne, et rebondit.
    const shortAir = 2.15;
    const lands = v(x0 * 0.14, 0.12, 6.5);
    const rolls = v(x0 * 0.1, 0.12, 2.6);
    const gatherAt = kickAt + shortAir + 0.75;
    const crossAt = kickAt + (made ? flight.crossAt : shortAir);
    const back = v(x0, 0, z0).normalize();
    const spotAt = [x0 + back.x * 0.6, z0 + back.z * 0.6];
    const stepBack = [x0 + back.x * 3.4 - s * back.z * 1.2, z0 + back.z * 3.4 + s * back.x * 1.2];
    const toBall = route([stepBack, [x0 + back.x * 0.35, z0 + back.z * 0.35]]);
    const aim = headingTo(x0, z0, 0, 0);
    const rest = new THREE.Quaternion().setFromUnitVectors(new THREE.Vector3(0, 1, 0), v(-back.x * 0.2, 1, -back.z * 0.2).normalize());
    const q = new THREE.Quaternion();
    // Derrière le buteur, de biais et en hauteur ; la caméra le suit vers les perches.
    const camBehind = [x0 + back.x * 17 - back.z * 3, 5, z0 + back.z * 17 + back.x * 3];
    const camNear = [x0 * 0.4 - 4, 6.5, 24];
    const duration = crossAt + (made ? 2.2 : 2.3);
    const cues = [
      { at: kickAt, run: () => world.sound("kick") },
      { at: crossAt, run: () => reaction(world, made) },
    ];
    return {
      duration,
      cues,
      frame(t) {
        setupFrame(1.5);
        lineWatches(t);
        refDown(t);
        // Les partenaires s'écartent de sa course.
        [[twelve, spots.twelve, -7], [nine, spots.nine, 6.5], [lock, spots.lock, -11]].forEach(([player, at, dx]) => {
          runner(player, route([at, [x0 + s * dx, z0 + 1]]), t, 0.1, 1.2, { from: 0.3, to: 0, speed: 0.3 });
          if (t > 1.2) player.set(ready(0.1));
        });
        if (t < 0.7) {
          const k = smooth(span(t, 0, 0.7));
          hero.place(lerp(mark[0], spotAt[0], k), lerp(mark[1], spotAt[1], k), aim).set(HOLD);
        } else if (t < 1.15) {
          hero.place(spotAt[0], spotAt[1], aim).set(crouch(smooth(span(t, 0.7, 0.88)) * (1 - smooth(span(t, 1.0, 1.15)))));
        } else if (t < 1.55) {
          const k = smooth(span(t, 1.15, 1.55));
          hero.place(lerp(spotAt[0], stepBack[0], k), lerp(spotAt[1], stepBack[1], k), headingTo(stepBack[0], stepBack[1], x0, z0)).set(STAND);
        } else if (t < 1.9) {
          hero.place(stepBack[0], stepBack[1], headingTo(stepBack[0], stepBack[1], x0, z0)).set(ready(0.12));
        } else if (t < kickAt) {
          runner(hero, toBall, t, 1.9, kickAt, { from: 0.4, to: 0.9, speed: 0.6 });
        } else {
          const end = toBall.at(toBall.total);
          hero.place(end.x, end.z, aim).set(mixPose(kick(span(t, kickAt - 0.12, kickAt + 0.4)), ready(0.12), smooth(span(t, kickAt + 0.55, kickAt + 0.95))));
        }
        // Le dernier de la défense, sous les perches : il ramasse le ballon tombé court.
        if (!made) {
          runner(deep, route([deepAt, [rolls.x - 0.4, rolls.z - 0.5]]), t, crossAt - 0.8, gatherAt, { from: 0.3, to: 0.1, speed: 0.5 });
          if (t >= gatherAt - 0.15) deep.place(rolls.x - 0.4, rolls.z - 0.5, FACE_FIELD).set(t < gatherAt + 0.25 ? crouch(0.9) : HOLD);
        }
        if (t >= crossAt + 0.4) [hero, twelve, nine, lock].forEach((player, i) => player.set(made ? cheer(t * 1.6 + i * 0.3) : dejected()));
        if (made && t >= crossAt) ref.set(tryAward(smooth(span(t, crossAt, crossAt + 0.4))));

        world.tee.visible = t > 0.85;
        world.tee.position.set(x0, 0, z0);
        if (t < 0.7) world.ballAt(carried(hero, "two", ball), v(1, 0, 0));
        else if (t < 0.9) world.ballAt(ball.lerpVectors(carried(hero, "two", v()), teePoint, smooth(span(t, 0.7, 0.9))), v(0.3, 1, 0));
        else if (t < kickAt) world.ballAt(ball.copy(teePoint), v(-back.x * 0.2, 1, -back.z * 0.2));
        else if (made) {
          flight.at(t - kickAt, ball, q, rest);
          world.ball.position.copy(ball);
          world.ball.quaternion.copy(q);
        } else if (t < crossAt) {
          world.ballAt(lob(teePoint, lands, 15, span(t, kickAt, crossAt), ball), v(0, 1, 0), (t - kickAt) * 13, v(1, 0, 0));
        } else if (t < gatherAt) {
          world.ballAt(grubber(lands, rolls, span(t, crossAt, gatherAt), 3, ball), v(Math.sin(t * 9), 0.3, 1));
        } else world.ballAt(lift(deep, "two", span(t, gatherAt, gatherAt + 0.25), ball), v(1, 0, 0));

        // La caméra suit le ballon à moitié, puis se pose sur les perches.
        const move = smooth(span(t, kickAt + 0.1, crossAt));
        const follow = smooth(span(t, kickAt, kickAt + 0.6)) * (1 - smooth(span(t, crossAt + 0.2, crossAt + 1.1)));
        const settle = smooth(span(t, crossAt + 0.2, crossAt + 1.1));
        return {
          pos: [lerp(camBehind[0], camNear[0], move), lerp(camBehind[1], camNear[1], move), lerp(camBehind[2], camNear[2], move)],
          look: [
            lerp(lerp(x0 * 0.3, ball.x * 0.6, follow), made ? 0 : rolls.x, settle),
            lerp(lerp(1, Math.min(ball.y, 10) * 0.6, follow), made ? 4.5 : 1.8, settle),
            lerp(lerp(z0 * 0.45, ball.z * 0.6, follow), made ? 0 : 3, settle),
          ],
          fov: 32,
        };
      },
    };
  }

  // --- La touche -------------------------------------------------------------------------
  function touchOutcome(result) {
    const { success: good, effect } = result;
    const kickAt = 0.5;
    const stolen = !good && effect === "lost";
    const aim = good ? touchOut : stolen ? v(wingAt[0], 1.12, 20) : v(s * 25, 0.12, 27);
    const air = good ? 2.1 : 1.85;
    const arrive = kickAt + air;
    const rest = v(s * (TOUCH + 3), 0.12, 12);
    const rollEnd = v(s * 27.5, 0.12, 22.8); // resté en jeu, il roule encore un peu
    const gatherAt = arrive + 0.8;
    const duration = good ? arrive + 2 : stolen ? arrive + 2 : gatherAt + 1.4;
    const from = v();
    const catchSpot = [aim.x, aim.z - 0.42];
    const backTo = [wingAt[0] - s * 4, 40];
    return {
      duration,
      cues: [
        { at: kickAt, run: () => world.sound("kick") },
        { at: arrive, run: () => (good ? (world.sound("whistle"), reaction(world, true)) : reaction(world, false)) },
      ],
      frame(t) {
        setupFrame(1.5);
        lineWatches(t);
        refDown(t);
        hero.place(mark[0], mark[1], headingTo(mark[0], mark[1], aim.x, aim.z)).set(t < kickAt - 0.3 ? HOLD : mixPose(kick(span(t, kickAt - 0.3, kickAt + 0.35), true), ready(0.1), smooth(span(t, kickAt + 0.5, kickAt + 0.9))));
        carried(hero, "two", from);
        if (t > arrive + 0.5) [hero, twelve, nine].forEach((player, i) => player.set(good ? cheer(t * 1.5 + i * 0.3) : dejected()));

        if (good) {
          // Personne n'y peut rien : leur ailier regarde le ballon sortir.
          runner(theirWing, route([wingAt, [s * (TOUCH - 3), 16.5]]), t, 0.3, arrive + 0.2, { from: 0.4, to: 0.1, speed: 0.8 });
          if (t > arrive + 0.2) theirWing.set(dejected());
          runner(wing, route([spots.wing, [s * (TOUCH - 4), 24]]), t, 0.3, duration, { from: 0.5, to: 0.8, speed: 0.75 });
        } else if (stolen) {
          // Leur ailier le prend de volée et relance dans notre camp.
          runner(theirWing, route([wingAt, catchSpot]), t, 0.2, arrive - 0.25, { from: 0.4, to: 0.1, speed: 0.7 });
          if (t >= arrive - 0.25) theirWing.place(catchSpot[0], catchSpot[1], FACE_FIELD).set(HOLD);
          if (t >= arrive + 0.2) runner(theirWing, route([catchSpot, backTo]), t, arrive + 0.2, duration, { from: 0.3, to: 0.95, speed: 0.9, carry: "one" });
          runner(wing, route([spots.wing, [s * 23, 34]]), t, 0.5, duration, { from: 0.4, to: 0.8, speed: 0.75 });
        } else {
          // Il rebondit en jeu, loin de la ligne : notre ailier revient le chercher.
          runner(wing, route([spots.wing, [rollEnd.x - s * 0.4, rollEnd.z + 0.4]]), t, 0.2, gatherAt - 0.1, { from: 0.5, to: 0.2, speed: 0.85 });
          if (t >= gatherAt - 0.15) wing.place(rollEnd.x - s * 0.4, rollEnd.z + 0.4, FACE_LINE).set(t < gatherAt + 0.25 ? crouch(1 - span(t, gatherAt, gatherAt + 0.25)) : HOLD);
          runner(theirWing, route([wingAt, [s * 29.5, 18]]), t, 0.3, gatherAt + 0.3, { from: 0.4, to: 0.1, speed: 0.6 });
          if (t >= gatherAt + 0.3) theirWing.place(s * 29.5, 18, FACE_FIELD).set(ready(0.5));
        }

        if (t < kickAt) world.ballAt(ball.copy(from), v(1, 0, 0));
        else if (t < arrive) world.ballAt(lob(v(mark[0], 1.05, mark[1]), aim, good ? 13 : 11, span(t, kickAt, arrive), ball), v(Math.sin(t * 9), Math.cos(t * 9), 0.3));
        else if (good) world.ballAt(grubber(touchOut, rest, span(t, arrive, arrive + 0.8), 2, ball), v(1, 0.2, 0.4));
        else if (stolen) world.ballAt(carried(theirWing, t < arrive + 0.2 ? "two" : "one", ball), v(0, 0, 1));
        else if (t < gatherAt) world.ballAt(grubber(aim, rollEnd, span(t, arrive, gatherAt), 3, ball), v(Math.sin(t * 9), 0.3, 1));
        else world.ballAt(lift(wing, "two", span(t, gatherAt, gatherAt + 0.25), ball), v(1, 0, 0));

        const follow = smooth(span(t, kickAt, arrive));
        if (good) {
          // Le point de sortie au centre de l'image, de quelque côté qu'il soit.
          const end = { pos: [s * (TOUCH - 2) - 26, 11.5, 31], look: [s * (TOUCH - 2), 0.6, 18], fov: 33 };
          return { pos: shot.pos.map((value, i) => lerp(value, end.pos[i], follow)), look: shot.look.map((value, i) => lerp(value, end.look[i], follow)), fov: lerp(shot.fov, end.fov, follow) };
        }
        const fx = (stolen ? theirWing : wing).root.position.x;
        const fz = stolen ? theirWing.root.position.z : rollEnd.z;
        return broadcast(lerp(x0, fx, follow), lerp(z0 - 3, fz + 2.5, follow), { far: lerp(1, 1.05, follow), fov: 33 });
      },
    };
  }

  // --- La jouer vite ---------------------------------------------------------------------
  function tapOutcome(result) {
    const good = result.success;
    const tapAt = 0.28;
    const go = 0.42;
    const duration = 2.9;
    const low = v();
    const hands = v();
    const heroRun = route(tapLine);
    // Le petit coup du pied, à ses pieds, avant de repartir à la main.
    const tap = (t) => {
      hero.local(-0.08, 0.32, 0.45, low);
      carried(hero, "two", hands);
      if (t < tapAt) ball.lerpVectors(hands, low, smooth(span(t, 0.05, tapAt)));
      else ball.lerpVectors(low, hands, smooth(span(t, tapAt, go)));
      world.ballAt(ball, v(0.2, 1, 0.2));
    };

    if (good) {
      return {
        duration,
        cues: [
          { at: tapAt, run: () => world.sound("kick") },
          { at: 1.35, run: () => reaction(world, true) },
        ],
        frame(t) {
          setupFrame(1.5);
          refDown(t);
          if (t < go) hero.place(mark[0], mark[1], FACE_LINE).set(kick(span(t, 0.05, go) * 0.55));
          else runner(hero, heroRun, t, go, duration, { from: 0.35, to: 1, speed: 1, carry: "two" });
          if (t > go + 0.5) hero.set(run((mark[1] - hero.root.position.z) / 2.3, 1, "one"));
          if (t < go) tap(t);
          else world.ballAt(carried(hero, t > go + 0.5 ? "one" : "two", ball), v(0, 0, 1));
          // Le soutien part avec lui, à sa hauteur ; le reste suit.
          runner(twelve, route([spots.twelve, [spots.twelve[0], tapEnd + 1.5]]), t, 0.15, duration, { from: 0.4, to: 1, speed: 0.95 });
          runner(nine, route([spots.nine, [spots.nine[0] + s * 0.5, tapEnd + 7]]), t, 0.3, duration, { from: 0.3, to: 0.8, speed: 0.75 });
          runner(lock, route([spots.lock, [spots.lock[0], spots.lock[1] - 9]]), t, 0.4, duration, { from: 0.3, to: 0.6, speed: 0.6 });
          runner(wing, route([spots.wing, [spots.wing[0], tapEnd + 4]]), t, 0.2, duration, { from: 0.4, to: 0.8, speed: 0.8 });
          // Ils ont le dos tourné, ne le voient qu'une fois passé.
          line.forEach(({ player, x }, i) => {
            runner(player, route([[x, lineZ], [x, lineZ - 1.2 - 2.5 * (i < 2 ? 1 : 0.6)]]), t, 0, duration, { from: 0.5, to: 1, speed: 0.45 });
          });
          runner(theirWing, route([wingAt, [wingAt[0] - s * 1.5, 25]]), t, 0.8, duration, { from: 0.4, to: 0.9, speed: 0.8 });
          runner(deep, route([deepAt, [-s * 14, 5]]), t, 0.3, duration, { from: 0.3, to: 0.7, speed: 0.6 });
          runner(ref, route([refAt, [x0 + 7, tapEnd + 3]]), t, 0.3, duration, { from: 0.3, to: 0.7, speed: 0.6 });
          if (t < 0.4) ref.set(signal(1, 1 - smooth(span(t, 0, 0.4))));
          const focus = hero.root.position;
          return broadcast(focus.x, focus.z - 1.5);
        },
      };
    }

    // Ils étaient en place : la ligne se retourne à temps, monte, et le prend.
    const meet = 1.55;
    const tackled = [x0 + s * 0.4, lineZ + 4.2];
    const tackler = line[0].player;
    const thief = line[1].player;
    const pickup = [tackled[0] + s * 0.9, tackled[1] - 1.9];
    const spill = v(pickup[0], 0.12, pickup[1] + 0.3);
    const hitRoute = route([mark, tackled]);
    const handsAt = v(tackled[0] + 0.2 * s, 1.08, tackled[1] - 0.1);
    const pickAt = meet + 0.75;
    const firstHit = v(tackled[0] + s * 0.4, 0.14, tackled[1] - 0.9);
    return {
      duration: 3.3,
      cues: [
        { at: tapAt, run: () => world.sound("kick") },
        { at: meet, run: () => world.sound("impact") },
        { at: meet + 0.35, run: () => reaction(world, false) },
      ],
      frame(t) {
        setupFrame(1.5);
        refDown(t);
        const k = span(t, meet - 0.12, meet + 0.4);
        if (t < go) hero.place(mark[0], mark[1], FACE_LINE).set(kick(span(t, 0.05, go) * 0.55));
        else if (t < meet) runner(hero, hitRoute, t, go, meet, { from: 0.3, to: 0.9, speed: 0.8, carry: "one" });
        else hero.place(tackled[0], tackled[1] + 0.3 * smooth(k), FACE_LINE).set(k < 1 ? tackle(k * 0.6) : ground());
        // Ils se retournent, et montent d'un bloc.
        line.forEach(({ player, x }, i) => {
          const turn = span(t, 0, 0.3);
          if (t < 0.3) {
            player.place(x, lineZ, lerp(FACE_LINE, FACE_FIELD, smooth(turn))).set(ready(0.3));
            return;
          }
          const to = i === 0 ? [tackled[0] - s * 0.25, tackled[1] - 0.9] : i === 1 ? [pickup[0] + s * 0.2, pickup[1] - 0.6] : [x - s * (i === 2 ? -2 : 2), lineZ + 5];
          runner(player, route([[x, lineZ], to]), t, 0.3, i === 0 ? meet : i === 1 ? pickAt - 0.1 : 2.2, { from: 0.5, to: i > 1 ? 0.1 : 0.9, speed: 0.85 });
          if (i > 1 && t >= 2.2) player.set(ready(0.4));
        });
        if (t >= meet) tackler.place(tackled[0] - s * 0.25, tackled[1] - 0.9, FACE_FIELD).set(tackle(k));
        // Le ballon s'échappe, leur 12 le ramasse et repart.
        if (t < go) tap(t);
        else if (t < meet) world.ballAt(carried(hero, "one", ball), v(0, 0, 1));
        else if (t < meet + 0.25) world.ballAt(lob(handsAt, firstHit, 0.25, span(t, meet, meet + 0.25), ball), v(1, 0.3, 0));
        else if (t < pickAt) world.ballAt(grubber(firstHit, spill, span(t, meet + 0.25, pickAt), 2, ball), v(1, 0.3, 0));
        else {
          if (t < pickAt + 0.25) thief.place(pickup[0] + s * 0.2, pickup[1] - 0.6, FACE_FIELD).set(crouch(1));
          else runner(thief, route([[pickup[0] + s * 0.2, pickup[1] - 0.6], [pickup[0] + s * 1.5, pickup[1] + 7]]), t, pickAt + 0.25, 3.3, { from: 0.3, to: 0.9, speed: 0.8, carry: "one" });
          world.ballAt(lift(thief, "one", span(t, pickAt, pickAt + 0.25), ball), v(0, 0, 1));
        }
        if (t > meet + 0.9) [twelve, nine].forEach((player) => player.set(dejected()));
        const zoom = smooth(span(t, 0.2, 1.2));
        return broadcast(x0, lerp(z0 - 3, tackled[1] - 0.5, zoom), { far: lerp(1, 0.92, zoom) });
      },
    };
  }

  return {
    setup,
    preview,
    previewShot: (key) => (key === "quick_tap" ? null : wide),
    outcome(key, result) {
      if (key === "posts") return postsOutcome(result);
      if (key === "touch_kick") return touchOutcome(result);
      return tapOutcome(result);
    },
  };
}
