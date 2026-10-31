import * as THREE from "three";

import { bind, cheer, crouch, dejected, ground, pass, pose, ready, signal, tackle } from "../rig.js";
import { FACE_FIELD, FACE_LINE, broadcast, carried, keys, lerp, lob, penaltyAgainst, reaction, route, runner, smooth, span } from "./common.js";

// Carrière de joueur, « Ballon au sol » (ruck) : un porteur adverse vient d'être plaqué,
// le joueur incarné arrive le premier. Gratter le ballon (les mains dessus, debout sur
// ses appuis : ballon récupéré, ou nettoyé et pénalisé), le contre-ruck (lié à un
// partenaire, il pousse par-dessus le ballon), ou se replacer en défense.
//
// Ici l'adversaire attaque vers la ligne d'essai (z = 0) : nous défendons.

const JACKAL = pose({ y: -0.3, lean: 1.15, legL: 0.9, legR: 0.7, knL: 1.3, knR: 1.1, armL: 1.6, armR: 1.6, elL: 0.2, elR: 0.2, abL: -0.2, abR: -0.2, nod: -0.4 });

export function buildRuck(world, data) {
  const rng = world.rng;
  const s = rng() < 0.5 ? -1 : 1;
  const rx = s * (4 + rng() * 8);
  const rz = 20;
  const heroNo = data.hero ?? 7;
  const hero = world.player("us", heroNo, { hero: true });
  const tackler = world.player("us", heroNo === 6 ? 8 : 6);
  const mate = world.player("us", heroNo === 4 ? 5 : 4);
  const line = [world.player("us", heroNo === 12 ? 13 : 12), world.player("us", heroNo === 10 ? 9 : 10)];
  const carrier = world.player("them", 8);
  const cleaners = [world.player("them", 4), world.player("them", 5)];
  const nine = world.player("them", 9);
  const runnerB = world.player("them", 12);
  const ref = world.player("ref");

  const ball = new THREE.Vector3(rx, 0.12, rz + 0.9);
  const over = [rx, rz + 0.25]; // où se tient le gratteur
  const start = {
    hero: [rx - s * 3.5, rz - 4.5],
    mate: [rx - s * 6, rz - 5.5],
    cleanA: [rx + s * 2.5, rz + 6],
    cleanB: [rx - s * 1, rz + 7],
    nine: [rx + s * 4, rz + 9],
    runnerB: [rx + s * 7, rz + 9],
  };
  const end = {
    hero: [over[0], over[1] - 0.6],
    mate: [rx - s * 2.6, rz - 2.4],
    cleanA: [rx + s * 1.4, rz + 3.4],
    cleanB: [rx - s * 0.5, rz + 4.2],
    nine: [rx + s * 2.2, rz + 5.5],
    runnerB: [rx + s * 5.5, rz + 7],
  };
  const shot = broadcast(rx, rz + 0.5, { far: 0.6, fov: 30, y: 0.4 });
  const camera = keys([
    [0, [rx - 50, 24, rz + 30, rx * 0.6, 0, rz + 2, 44]],
    [1.3, [...shot.pos, ...shot.look, shot.fov]],
  ]);
  const lineSpots = [[rx - s * 7, rz - 4], [rx + s * 6, rz - 4.5]];
  const refSpot = [rx - s * 5, rz + 2];

  function setupFrame(t) {
    // Le plaquage qui fait le ruck : le porteur tombe, notre plaqueur avec lui.
    const k = span(t, 0, 0.5);
    carrier.place(rx, lerp(rz - 1.5, rz + 1.6, 0), FACE_LINE).set(k < 1 ? tackle(k * 0.5) : ground());
    carrier.place(rx, rz + 1.6 - 0.6 * smooth(k), FACE_LINE);
    tackler.place(rx + s * 0.5, rz - 0.2, FACE_FIELD + s * 0.3).set(k < 1 ? tackle(0.5 + k * 0.5) : ground());
    runner(hero, route([start.hero, end.hero]), t, 0, 1.3, { from: 0.9, to: 0.4, speed: 0.8 });
    if (t >= 1.25) hero.place(end.hero[0], end.hero[1], FACE_FIELD).set(crouch(0.6));
    runner(mate, route([start.mate, end.mate]), t, 0, 1.3, { from: 0.8, to: 0.5, speed: 0.7 });
    runner(cleaners[0], route([start.cleanA, end.cleanA]), t, 0, 1.3, { from: 0.9, to: 0.7, speed: 0.8 });
    runner(cleaners[1], route([start.cleanB, end.cleanB]), t, 0, 1.3, { from: 0.9, to: 0.7, speed: 0.8 });
    runner(nine, route([start.nine, end.nine]), t, 0, 1.3, { from: 0.9, to: 0.6, speed: 0.8 });
    runner(runnerB, route([start.runnerB, end.runnerB]), t, 0, 1.3, { from: 0.6, to: 0.5, speed: 0.6 });
    line.forEach((player, i) => player.place(...lineSpots[i], FACE_FIELD).set(ready(0.4)));
    ref.place(refSpot[0], refSpot[1], (s * Math.PI) / 2).set(ready(0.1));
    // Le ballon, placé par le porteur à son pied.
    world.ballAt(k < 1 ? carried(carrier, "one", new THREE.Vector3()) : ball, new THREE.Vector3(1, 0, 0));
    const [cx, cy, cz, lx, ly, lz, fov] = camera(t);
    return { pos: [cx, cy, cz], look: [lx, ly, lz], fov };
  }

  const setup = {
    duration: 1.3,
    frame: setupFrame,
    cues: [
      { at: 0.25, run: () => world.sound("impact") },
      { at: 0.4, run: () => world.crowd(world.pressure > 1 ? "standing" : "seated") },
    ],
  };

  const fold = [rx - s * 2.5, rz - 4.5];
  function preview(key) {
    const draw = world.draw;
    if (key === "jackal") return [draw.path([end.hero, over]), draw.mark([ball.x, ball.z], 0.6)];
    if (key === "counter") return [draw.arrow([rx, rz - 0.8], [rx, rz + 3.2], 1.8)];
    return [draw.path([end.hero, fold]), draw.mark(fold)];
  }

  function outcomeFor(key, result) {
    const { success, effect } = result;
    const callAt = 1.2;
    const cues = [];
    if (key === "jackal") {
      cues.push({ at: 0.55, run: () => world.sound("impact") });
      cues.push({ at: callAt, run: () => (success ? penaltyAgainst(world, "them") : effect === "penalty_conceded" ? penaltyAgainst(world, "us") : world.sound("groan")) });
    } else if (key === "counter") {
      cues.push({ at: 0.45, run: () => world.sound("impact") });
      cues.push({ at: 1.3, run: () => reaction(world, success) });
    } else {
      cues.push({ at: 1.5, run: () => world.sound(success ? "impact" : "groan") });
    }
    const passFrom = new THREE.Vector3();
    const passTo = new THREE.Vector3();
    return {
      duration: 3,
      cues,
      frame(t) {
        setupFrame(1.3);
        if (key === "jackal") {
          // Les mains sur le ballon ; leurs avants arrivent pour le déloger.
          hero.place(over[0], over[1], FACE_FIELD).set(t < 0.3 ? crouch(0.6 + t) : JACKAL);
          const hit = 0.55;
          cleaners.forEach((player, i) => {
            const target = [over[0] + (i ? -0.3 : 0.4) * s, over[1] + 0.9];
            runner(player, route([[end.cleanA, end.cleanB][i], target]), t, 0, hit, { from: 0.7, to: 0.6, speed: 0.7 });
            if (t >= hit) player.place(...target, FACE_LINE).set(bind(t, success ? 0.3 : 1, 0.8));
          });
          if (!success && t > hit) {
            // Délogé : il part en arrière et finit au sol.
            const k = span(t, hit, hit + 0.5);
            hero.place(over[0], over[1] - 1.4 * smooth(k), FACE_FIELD).set(k < 1 ? ready(0.4) : ground(true));
          }
          if (success && t > 1.6) {
            // Ballon gagné : il se relève avec, le public de son côté.
            hero.place(over[0], over[1] - 0.6 * span(t, 1.6, 2.2), FACE_LINE).set(ready(0.2));
            world.ballAt(carried(hero, "two", passFrom), new THREE.Vector3(1, 0, 0));
          } else if (!success && effect !== "penalty_conceded" && t > 1.5) {
            nine.place(ball.x + s * 0.4, ball.z + 0.6, FACE_LINE).set(t < 1.8 ? crouch(1) : pass(span(t, 1.8, 2.1), s));
            world.ballAt(t < 1.8 ? ball : carried(nine, "two", passFrom), new THREE.Vector3(1, 0, 0));
          } else world.ballAt(ball, new THREE.Vector3(1, 0, 0));
          ref.place(refSpot[0], refSpot[1], (s * Math.PI) / 2);
          // Pour nous : le bras vers notre attaque (+z, nous défendions) ; contre nous : vers -z.
          const whose = success ? (s > 0 ? -1 : 1) : s > 0 ? 1 : -1;
          ref.set(t > callAt && (success || effect === "penalty_conceded") ? signal(whose, smooth(span(t, callAt, callAt + 0.3))) : ready(0.1));
        } else if (key === "counter") {
          // Lié à un partenaire, il pousse par-dessus le ballon.
          const hit = 0.45;
          const gain = success ? 2.8 * smooth(span(t, hit, 1.3)) : 0.4 * smooth(span(t, hit, 1.0));
          runner(mate, route([end.mate, [rx - s * 0.6, rz - 0.4]]), t, 0, hit, { from: 0.5, to: 0.6, speed: 0.6 });
          hero.place(rx + s * 0.4, rz - 0.4 + gain, FACE_FIELD).set(t < hit ? crouch(0.6) : bind(t * 1.2, 1, 0.85));
          if (t >= hit) mate.place(rx - s * 0.6, rz - 0.4 + gain, FACE_FIELD).set(bind(t * 1.2 + 0.4, 1, 0.85));
          cleaners.forEach((player, i) => {
            const target = [rx + (i ? -0.5 : 0.6) * s, rz + 1.4];
            runner(player, route([[end.cleanA, end.cleanB][i], target]), t, 0, hit, { from: 0.7, to: 0.6, speed: 0.7 });
            if (t >= hit) player.place(target[0], target[1] + gain, FACE_LINE).set(success && t > 1.2 ? ground(true) : bind(t * 1.1, 1, 0.85));
          });
          // Ballon dégagé derrière nous : notre 6 ou 8 (le plaqueur relevé) le ramasse.
          if (success && t > 1.4) {
            tackler.place(ball.x - s * 0.3, ball.z - 0.4, FACE_FIELD).set(t < 1.7 ? crouch(1) : ready(0.2));
            world.ballAt(t < 1.7 ? ball : carried(tackler, "two", passFrom), new THREE.Vector3(1, 0, 0));
            if (t > 1.9) [hero, mate].forEach((player, i) => player.set(cheer(t * 1.4 + i)));
          } else if (!success && t > 1.2) {
            nine.place(ball.x + s * 0.4, ball.z + 0.7, FACE_LINE).set(t < 1.5 ? crouch(1) : pass(span(t, 1.5, 1.8), s));
            carried(nine, "two", passFrom);
            carried(runnerB, "two", passTo);
            if (t < 1.5) world.ballAt(ball, new THREE.Vector3(1, 0, 0));
            else if (t < 1.9) world.ballAt(lob(passFrom, passTo, 0.4, span(t, 1.5, 1.9), new THREE.Vector3()), new THREE.Vector3(1, 0, 0));
            else world.ballAt(carried(runnerB, "two", passFrom), new THREE.Vector3(1, 0, 0));
            if (t > 1.5) runner(runnerB, route([end.runnerB, [end.runnerB[0] - s * 1.5, rz - 3]]), t, 1.5, 3, { from: 0.4, to: 0.8, speed: 0.8, carry: t > 1.9 ? "two" : "none" });
          } else world.ballAt(ball, new THREE.Vector3(1, 0, 0));
          ref.place(refSpot[0], refSpot[1], (s * Math.PI) / 2).set(ready(0.1));
        } else {
          // Il se replace : leur 9 sert, leur 12 attaque l'intervalle.
          runner(hero, route([end.hero, fold]), t, 0, 0.9, { from: 0.4, to: 0.3, speed: 0.6 });
          if (t >= 0.9) hero.place(fold[0], fold[1], FACE_FIELD).set(ready(0.6));
          nine.place(ball.x + s * 0.4, ball.z + 0.6, FACE_LINE).set(t < 0.5 ? crouch(1) : pass(span(t, 0.5, 0.8), s > 0 ? -1 : 1));
          carried(nine, "two", passFrom);
          const gapTarget = success ? [fold[0] + s * 0.4, fold[1] + 0.8] : [fold[0] - s * 2.6, fold[1] - 4];
          runner(runnerB, route([end.runnerB, [rx - s * 1.5, rz - 1.5], gapTarget]), t, 0.3, 1.5, { from: 0.6, to: 1, speed: 0.9, carry: t > 0.9 ? "two" : "none" });
          carried(runnerB, "two", passTo);
          if (t < 0.5) world.ballAt(ball, new THREE.Vector3(1, 0, 0));
          else if (t < 0.9) world.ballAt(lob(passFrom, passTo, 0.4, span(t, 0.5, 0.9), new THREE.Vector3()), new THREE.Vector3(1, 0, 0));
          else world.ballAt(carried(runnerB, "two", passFrom), new THREE.Vector3(1, 0, 0));
          if (success && t >= 1.5) {
            // Bien replacé, il le prend de face.
            hero.set(tackle(span(t, 1.5, 1.9)));
            runnerB.place(gapTarget[0], gapTarget[1] - 0.6 * span(t, 1.5, 2.0), FACE_LINE).set(ground());
          } else if (!success && t >= 1.5) {
            runner(runnerB, route([gapTarget, [gapTarget[0], gapTarget[1] - 6]]), t, 1.5, 3, { from: 1, to: 0.6, speed: 0.9, carry: "one" });
            hero.set(dejected());
          }
          ref.place(refSpot[0], refSpot[1], (s * Math.PI) / 2).set(ready(0.1));
          return broadcast(lerp(rx, fold[0], 0.5), rz - 2, { far: 0.85 });
        }
        return shot;
      },
    };
  }

  return { setup, preview, outcome: outcomeFor };
}
