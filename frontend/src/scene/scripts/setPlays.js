import * as THREE from "three";

import { TOUCH } from "../field.js";
import { bind, cheer, crouch, dejected, dive, ground, jump, lifter, pass, pose, ready, run, signal, tryAward } from "../rig.js";
import { FACE_FIELD, FACE_LINE, broadcast, carried, keys, lerp, lob, penaltyAgainst, reaction, route, runner, smooth, span } from "./common.js";
import { halfBack, maul, scrum } from "./setPieces.js";

// Carrière de joueur : les phases arrêtées où le joueur incarné est dans le paquet.
// La mêlée (scrum : faire reculer, ou stabiliser), la touche où il saute (lineout : maul
// ou sauter devant), la touche qu'il lance (throw : au fond, devant pour le maul, ou
// devant). Notre équipe attaque vers la ligne d'essai (z = 0).

// Le paquet : nos avants 1 à 8, le joueur incarné à son numéro (ou à `slot` s'il n'est
// pas avant), et sept des leurs.
function packs(world, heroNo, slot) {
  const ours = {};
  const at = heroNo >= 1 && heroNo <= 8 ? heroNo : slot;
  for (let n = 1; n <= 8; n++) ours[n] = world.player("us", n === at ? heroNo : n, { hero: n === at });
  const theirs = {};
  for (let n = 1; n <= 8; n++) theirs[n] = world.player("them", n);
  return { ours, theirs, hero: ours[at] };
}

// --- Mêlée ----------------------------------------------------------------------------

export function buildScrum(world, data) {
  const rng = world.rng;
  const sx = (rng() - 0.5) * 24;
  const cz = 30;
  const { ours, theirs, hero } = packs(world, data.hero ?? 3, 8);
  const nine = world.player("us", 9);
  const ten = world.player("us", 10);
  const theirNine = world.player("them", 9);
  const ref = world.player("ref");
  const feeder = [sx - 1.1, cz + 0.2];
  const ball = new THREE.Vector3();
  const shot = broadcast(sx, cz + 0.5, { far: 0.75, fov: 30, y: 0.3 });
  const camera = keys([
    [0, [sx - 50, 24, cz + 30, sx * 0.6, 0, cz, 44]],
    [1.4, [...shot.pos, ...shot.look, shot.fov]],
  ]);
  const refAt = (mx, mz) => ref.place(mx + 2.7, mz + 0.4, -Math.PI / 2);

  function setupFrame(t) {
    // « Flexion, liez, jeu » : les packs s'approchent, se lient, l'impact.
    const engage = smooth(span(t, 0.5, 0.95));
    scrum(ours, theirs, sx, cz, { engage, phase: t });
    nine.place(...feeder, Math.PI / 2).set(t > 1 ? halfBack : ready(0.3));
    // L'ouvreur de l'autre côté de la mêlée : hors du champ entre la caméra et le paquet.
    ten.place(sx + 8, cz + 4, FACE_LINE).set(ready(0.3));
    theirNine.place(sx - 1, cz - 1.2, FACE_FIELD).set(ready(0.4));
    refAt(sx, cz).set(ready(0.1));
    world.ballAt(carried(nine, t > 1 ? "low" : "two", ball), new THREE.Vector3(0, 0, 1));
    const [cx, cy, cz2, lx, ly, lz, fov] = camera(t);
    return { pos: [cx, cy, cz2], look: [lx, ly, lz], fov };
  }

  const setup = {
    duration: 1.4,
    frame: setupFrame,
    cues: [
      { at: 0.1, run: () => world.crowd(world.pressure > 1 ? "standing" : "seated") },
      { at: 0.95, run: () => world.sound("impact") },
    ],
  };

  function preview(key) {
    const draw = world.draw;
    if (key === "drive") return [draw.arrow([sx, cz + 2.6], [sx, cz - 3], 3)];
    return [draw.path([[feeder[0] + 0.5, feeder[1]], [sx, cz + 0.6], [sx, cz + 2.3]], { width: 0.3 }), draw.mark([sx, cz + 2.4], 0.6)];
  }

  function outcomeFor(key, result) {
    const { success, effect } = result;
    const feedAt = 0.3;
    const callAt = 1.7;
    const penalty = key === "drive" && (success || effect === "penalty_conceded");
    return {
      duration: 3.2,
      cues: [
        {
          at: callAt,
          run: () => {
            if (penalty) penaltyAgainst(world, success ? "them" : "us");
            else reaction(world, success);
          },
        },
      ],
      frame(t) {
        setupFrame(1.4);
        const drive = span(t, 0.4, 1.6);
        let push = 0;
        let wheel = 0;
        if (key === "drive") push = success ? 2.6 * smooth(drive) : -1.6 * smooth(drive);
        else push = success ? 0.2 * smooth(drive) : -1.4 * smooth(drive);
        if (!success) wheel = 0.35 * smooth(span(t, 1.0, 1.7));
        const [mx, mz] = scrum(ours, theirs, sx, cz, { push, wheel, drive: 1, phase: t * 1.3 });
        // Le pack qui recule s'écroule.
        if (key === "drive" && t > 1.5) Object.values(success ? theirs : ours).forEach((player) => player.set(ground()));
        nine.place(feeder[0], feeder[1] - push, Math.PI / 2).set(halfBack);
        // Le ballon : introduit, talonné jusqu'au pied du 8, puis sorti (ou perdu).
        const no8 = success ? [mx, mz + 2.3] : [mx, mz - 2.3];
        if (t < feedAt) world.ballAt(carried(nine, "low", ball), new THREE.Vector3(0, 0, 1));
        else if (t < feedAt + 0.6) world.ballAt(ball.set(lerp(feeder[0] + 0.5, mx, span(t, feedAt, feedAt + 0.3)), 0.12, lerp(feeder[1], no8[1], span(t, feedAt + 0.2, feedAt + 0.6))), new THREE.Vector3(1, 0, 0));
        else if (key === "steady" && success && t > 1.6) {
          // Le 9 ramasse au pied du 8 et sert l'ouvreur.
          nine.place(mx - 0.6, mz + 2.6, Math.PI / 2 - 0.6).set(t < 1.9 ? crouch(1) : pass(span(t, 1.9, 2.2), -1));
          const from = carried(nine, "two", new THREE.Vector3());
          const to = carried(ten, "two", new THREE.Vector3());
          if (t < 1.9) world.ballAt(ball.set(no8[0], 0.12, no8[1]), new THREE.Vector3(1, 0, 0));
          else if (t < 2.4) world.ballAt(lob(from, to, 0.5, span(t, 1.9, 2.4), ball), new THREE.Vector3(1, 0, 0));
          else world.ballAt(carried(ten, "two", ball), new THREE.Vector3(1, 0, 0));
          if (t > 2.4) runner(ten, route([[sx + 8, cz + 4], [sx + 10, cz - 1]]), t, 2.4, 3.2, { from: 0.4, to: 0.7, speed: 0.7, carry: "two" });
        } else if (!success && !penalty && t > 1.7) {
          // Leur 9 récupère au pied de leur 8.
          theirNine.place(no8[0] + 0.5, no8[1] - 0.4, FACE_FIELD).set(t < 2.0 ? crouch(1) : ready(0.2));
          world.ballAt(t < 2.0 ? ball.set(no8[0], 0.12, no8[1]) : carried(theirNine, "two", ball), new THREE.Vector3(1, 0, 0));
        } else world.ballAt(ball.set(no8[0], 0.12, no8[1]), new THREE.Vector3(1, 0, 0));
        if (t > callAt + 0.4 && success) hero.set(key === "drive" ? cheer(t * 1.5) : hero.current);
        // L'arbitre, face à la mêlée (vers -x) : bras gauche vers +z (eux), droit vers -z (nous).
        refAt(mx, mz);
        ref.set(penalty && t > callAt ? signal(success ? -1 : 1, smooth(span(t, callAt, callAt + 0.3))) : ready(0.1));
        return shot;
      },
    };
  }

  return { setup, preview, outcome: outcomeFor };
}

// --- Touche -----------------------------------------------------------------------------

// Les places dans l'alignement, en mètres depuis la touche : trois groupes (devant, au
// milieu, au fond), chacun un sauteur entre deux lifteurs.
const OURS = { 1: 5.5, 6: 6.5, 3: 7.5, 4: 9, 5: 10, 7: 11, 8: 13.5 };
const THEIRS = { 1: 5.8, 6: 6.8, 3: 7.8, 4: 9.3, 5: 10.3, 7: 11.3, 8: 13.8 };
const PODS = { front: { jumper: 6, lifters: [1, 3] }, middle: { jumper: 5, lifters: [4, 7] }, back: { jumper: 8, lifters: [7, 4] } };

// `kind` : "lineout" (il saute, au milieu) ou "throw" (il lance, talonneur).
export function buildLineout(world, data, kind) {
  // Toujours la touche d'en face : le lanceur, face à la caméra, reste visible.
  const s = 1;
  const zl = kind === "lineout" ? 10 : 15;
  const heroNo = data.hero ?? (kind === "throw" ? 2 : 5);
  const { ours, theirs, hero } = packs(world, heroNo, kind === "throw" ? 2 : 5);
  const thrower = ours[2];
  const nine = world.player("us", 9);
  const twelve = world.player("us", 12);
  const theirTen = world.player("them", 10);
  const ref = world.player("ref");
  const face = (s * Math.PI) / 2;
  const spot = (depth, z) => [s * (TOUCH - depth), z];
  const home = {};
  for (const [n, depth] of Object.entries(OURS)) home[n] = spot(depth, zl + 0.55);
  const away = {};
  for (const [n, depth] of Object.entries(THEIRS)) away[n] = spot(depth, zl - 0.55);
  const throwFrom = [s * (TOUCH + 0.7), zl];
  const ball = new THREE.Vector3();
  const from = new THREE.Vector3();
  const to = new THREE.Vector3();
  const focus = [s * (TOUCH - 9), zl];
  const shot = broadcast(focus[0], focus[1] + 0.5, { far: 0.8, fov: 31, y: 1 });
  const camera = keys([
    [0, [focus[0] - 50, 24, zl + 32, focus[0] * 0.7, 0, zl + 4, 44]],
    [1.3, [...shot.pos, ...shot.look, shot.fov]],
  ]);
  const THROWING = pose({ armL: 2.9, armR: 2.9, elL: 0.9, elR: 0.9, lean: -0.15 });

  function setupFrame(t) {
    // Les avants trottent jusqu'à l'alignement, le lanceur prend le ballon au-dessus de sa tête.
    const k = smooth(span(t, 0, 1.0));
    for (let n = 1; n <= 8; n++) {
      if (n === 2) continue;
      const [x, z] = home[n];
      ours[n].place(lerp(x - s * 2, x, k), lerp(z + 3, z, k), face).set(k < 1 ? run(t * 2.5, 0.3) : ready(0.3));
      if (theirs[n] && away[n]) {
        const [ax, az] = away[n];
        theirs[n].place(lerp(ax - s * 2, ax, k), lerp(az - 3, az, k), face).set(k < 1 ? run(t * 2.5 + 0.3, 0.3) : ready(0.3));
      }
    }
    theirs[2].place(s * (TOUCH + 0.4), zl - 4.5, -face).set(ready(0.2));
    thrower.place(...throwFrom, -face).set(t > 0.8 ? THROWING : ready(0.1));
    nine.place(s * (TOUCH - 10), zl + 3.5, face).set(ready(0.4));
    twelve.place(s * (TOUCH - 22), zl + 8, FACE_LINE).set(ready(0.3));
    theirTen.place(s * (TOUCH - 21), zl - 9, FACE_FIELD).set(ready(0.4));
    ref.place(s * (TOUCH - 9), zl - 4, FACE_FIELD).set(ready(0.1));
    world.ballAt(thrower.local(0, t > 0.8 ? 2.25 : 1.1, 0.25, ball), new THREE.Vector3(0, 1, 0));
    const [cx, cy, cz, lx, ly, lz, fov] = camera(t);
    return { pos: [cx, cy, cz], look: [lx, ly, lz], fov };
  }

  const setup = {
    duration: 1.3,
    frame: setupFrame,
    cues: [{ at: 0.1, run: () => world.crowd(world.pressure > 1 ? "standing" : "seated") }],
  };

  const podOf = (key) => (key === "front" ? PODS.front : key === "back" ? PODS.back : PODS.middle);
  // Le joueur incarné qui saute prend la place du sauteur visé.
  const jumperOf = (pod) => (kind === "lineout" ? hero : ours[pod.jumper]);

  function preview(key) {
    const draw = world.draw;
    const pod = podOf(key);
    const target = spot(OURS[pod.jumper], zl);
    const a = new THREE.Vector3(throwFrom[0], 2.4, throwFrom[1]);
    const b = new THREE.Vector3(target[0], 3.4, target[1]);
    const arc = [];
    for (let i = 0; i <= 12; i++) arc.push(lob(a, b, 1.2, i / 12).toArray());
    const drawn = [draw.arc(arc, 0.08), draw.mark(target, 0.8)];
    if (key === "maul") drawn.push(draw.arrow([target[0], zl + 2], [target[0], -0.8], 2.6));
    if (key === "back") drawn.push(draw.path([[target[0], zl + 1], spot(22, zl + 6), spot(24, zl - 6)]));
    return drawn;
  }

  function outcomeFor(key, result) {
    const { success } = result;
    const pod = podOf(key);
    const jumper = jumperOf(pod);
    const [lA, lB] = pod.lifters.map((n) => ours[n]);
    const target = spot(OURS[pod.jumper], zl + 0.55);
    const throwAt = 0.3;
    const catchAt = key === "back" ? 0.85 : 0.7;
    const maulAt = 1.0;
    const driveAt = 1.35;
    const groundAt = driveAt + 1.6;
    const starts = new Map();
    const thief = theirs[pod.jumper] ?? theirs[5];
    const thiefSpot = spot(THEIRS[pod.jumper] ?? 10.3, zl - 0.55);
    const scoring = key === "maul" && success;
    const duration = key === "maul" ? groundAt + 1.8 : 3;
    const cues = [];
    if (key === "maul") {
      cues.push({ at: driveAt, run: () => world.sound("impact") });
      cues.push({
        at: groundAt + 0.3,
        run: () => {
          if (scoring) world.sound("whistle", true);
          reaction(world, scoring);
        },
      });
    } else cues.push({ at: catchAt + 0.2, run: () => (success ? key === "back" && world.crowd("standing") : reaction(world, false)) });
    if (key === "back" && success) cues.push({ at: 2.1, run: () => reaction(world, true) });
    return {
      duration,
      cues,
      frame(t) {
        setupFrame(1.3);
        // Le sauteur visé monte entre ses lifteurs (le joueur incarné rejoint son groupe).
        const up = smooth(span(t, throwAt - 0.1, throwAt + 0.25)) * (1 - smooth(span(t, catchAt + 0.15, catchAt + 0.5)));
        const stolen = !success && key !== "maul";
        const theirUp = smooth(span(t, throwAt, throwAt + 0.3)) * (1 - smooth(span(t, catchAt + 0.15, catchAt + 0.5))) * (stolen ? 1.15 : 0.6);
        if (kind === "lineout" && pod.jumper !== 5) {
          // Il court se placer devant ; leur 6 et le nôtre s'écartent.
          const k = smooth(span(t, 0, throwAt));
          hero.place(lerp(home[5][0], target[0], k), target[1], face);
          ours[6].place(lerp(home[6][0], home[5][0], k), home[6][1], face);
        } else jumper.place(target[0], target[1], face);
        jumper.set({ ...jump(up), lift: up * 1.6 });
        lA.place(target[0] + s * 0.9, home[pod.lifters[0]][1], face).set(lifter(up));
        lB.place(target[0] - s * 0.9, home[pod.lifters[1]][1], face).set(lifter(up));
        thief.place(thiefSpot[0], thiefSpot[1], face).set({ ...jump(theirUp), lift: theirUp * 1.6 });
        thrower.place(...throwFrom, -face).set(t < throwAt ? THROWING : pose({ armL: 1.6, armR: 1.6, lean: 0.2 }));
        const hands = jumper.local(0, 2.25 + up * 1.6, 0.15, to);
        const thiefHands = thief.local(0, 2.25 + theirUp * 1.6, 0.15, new THREE.Vector3());
        thrower.local(0, 2.25, 0.1, from);
        const catcher = stolen ? thiefHands : hands;
        if (t < throwAt) world.ballAt(from, new THREE.Vector3(0, 1, 0));
        else if (t < catchAt) world.ballAt(lob(from, catcher, 1.2, span(t, throwAt, catchAt), ball), new THREE.Vector3(1, 0.2, 0));
        else if (stolen) {
          world.ballAt(t < catchAt + 0.5 ? thiefHands : carried(theirs[9] ?? thief, "two", ball), new THREE.Vector3(1, 0, 0));
          if (t > catchAt + 0.5) Object.values(ours).forEach((player) => player !== thrower && player.set(dejected()));
        } else if (key === "maul") {
          // Le maul : formé autour du sauteur, il pousse jusqu'à la ligne (ou s'arrête).
          if (t < maulAt) {
            world.ballAt(hands, new THREE.Vector3(1, 0, 0));
            for (const team of [ours, theirs]) Object.values(team).forEach((player) => starts.set(player, [player.root.position.x, player.root.position.z]));
          } else {
            const k = span(t, maulAt, driveAt);
            const drive = span(t, driveAt, groundAt);
            const end = scoring ? -0.6 : zl - 4;
            const front = lerp(zl, end + 2.4, scoring ? smooth(drive) : Math.sqrt(drive));
            const center = [target[0] - s * 0.6, front - 0.4];
            const mauled = { ...ours, 5: jumper };
            maul(mauled, theirs, starts, center, k, t * 1.4, 1);
            const carrier = ours[8];
            if (scoring && t > groundAt) {
              const g = span(t, groundAt, groundAt + 0.4);
              carrier.place(center[0], lerp(center[1] + 2.1, -0.4, smooth(g)), FACE_LINE).set(dive(g));
              Object.values(mauled).forEach((player) => player !== carrier && player.set(cheer(t * 1.5 + player.root.position.x)));
            } else if (!scoring && t > groundAt) {
              Object.values(mauled).forEach((player) => player.set(dejected()));
            }
            thrower.place(lerp(throwFrom[0], center[0], smooth(k)), lerp(throwFrom[1], center[1] + 2.9, smooth(k)), FACE_LINE).set(bind(t, 1, 0.75));
            world.ballAt(carried(carrier, scoring && t > groundAt ? "low" : "two", ball), new THREE.Vector3(1, 0, 0));
          }
          ref.place(target[0] - s * 4, lerp(zl - 4, 1, smooth(span(t, maulAt, groundAt))), face);
          ref.set(scoring && t > groundAt + 0.3 ? tryAward(smooth(span(t, groundAt + 0.3, groundAt + 0.6))) : ready(0.2));
          return broadcast(target[0], lerp(zl, 2, smooth(span(t, maulAt, groundAt))), { far: 0.8, fov: 31, y: 0.8 });
        } else {
          // Ballon propre : le sauteur le remet au 9, qui sert ; au fond, le 12 perce.
          const tap = catchAt + 0.25;
          const nineAt = carried(nine, "two", new THREE.Vector3());
          nine.place(s * (TOUCH - 10) + (key === "back" ? -s * 3 : 0), zl + 2.5, face).set(t > tap + 0.4 ? pass(span(t, tap + 0.4, tap + 0.7), s > 0 ? 1 : -1) : ready(0.4));
          if (t < tap) world.ballAt(hands, new THREE.Vector3(1, 0, 0));
          else if (t < tap + 0.35) world.ballAt(lob(hands, nineAt, 0.2, span(t, tap, tap + 0.35), ball), new THREE.Vector3(1, 0, 0));
          else if (t < tap + 0.7) world.ballAt(nineAt, new THREE.Vector3(1, 0, 0));
          else {
            const gap = key === "back" ? spot(24, zl - 6) : spot(22, zl + 5);
            runner(twelve, route([spot(22, zl + 8), spot(22, zl + 6), gap]), t, tap + 0.3, 3, { from: 0.5, to: 1, speed: 0.95, carry: t > tap + 1.1 ? "two" : "none" });
            const catchTwelve = carried(twelve, "two", new THREE.Vector3());
            if (t < tap + 1.1) world.ballAt(lob(nineAt, catchTwelve, 0.5, span(t, tap + 0.7, tap + 1.1), ball), new THREE.Vector3(1, 0, 0));
            else world.ballAt(carried(twelve, "two", ball), new THREE.Vector3(1, 0, 0));
            if (key === "back") theirTen.place(s * (TOUCH - 21), zl - 9 + span(t, tap, 3) * 2, FACE_FIELD).set(t > 2.2 ? ground() : run(t * 3, 0.6));
          }
          ref.place(s * (TOUCH - 9), zl - 4, FACE_FIELD).set(ready(0.1));
        }
        return shot;
      },
    };
  }

  return { setup, preview, outcome: outcomeFor };
}

export const buildThrow = (world, data) => buildLineout(world, data, "throw");
export const buildLineoutJump = (world, data) => buildLineout(world, data, "lineout");
