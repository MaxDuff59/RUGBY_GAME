import * as THREE from "three";

import { cheer, crouch, dejected, jump, kick, pass, pose, ready, run, tackle, tryAward } from "../rig.js";
import { FACE_FIELD, FACE_LINE, carried, goalKick, grubber, headingTo, keys, lerp, lob, route, runner, seeded, smooth, span } from "./common.js";

// Carrière de joueur, « Le pied ou la main » (kick) : le joueur incarné reçoit le ballon
// à 35 m de la ligne, la défense monte. Le drop (la physique de ball.js, réglée sur
// l'issue tirée), le petit coup de pied à suivre dans l'intervalle (rattrapé : il
// franchit, et l'action s'enchaîne), ou la passe au centre.
//
// `data.hero` : son numéro. Le résultat : `success`, `effect` (engine/dilemmas.py).

const HOLD = pose({ armL: 0.75, armR: 0.75, elL: 1.1, elR: 1.1, abL: -0.15, abR: -0.15, lean: 0.15, y: -0.05, knL: 0.2, knR: 0.2 });

export function buildKick(world, data) {
  const rng = world.rng;
  const s = rng() < 0.5 ? -1 : 1;
  const hx = s * 4;
  const hz = 35.5;
  const ruck = [hx + s * 5, 38];
  const heroNo = data.hero ?? 10;
  const hero = world.player("us", heroNo, { hero: true });
  const nine = heroNo === 9 ? null : world.player("us", 9);
  const twelve = world.player("us", heroNo === 12 ? 13 : 12);
  const thirteen = world.player("us", heroNo === 13 || heroNo === 12 ? 14 : 13);
  const ruckOurs = world.player("us", 7);
  const ruckGround = world.player("us", 4);
  const ruckTheirs = world.player("them", 6);
  const line = {
    9: [ruck[0] - s * 0.5, 33.5],
    7: [hx + s * 2.2, 28],
    10: [hx - s * 0.3, 27.6],
    12: [hx - s * 5, 28.3],
    13: [hx - s * 10.5, 28.8],
  };
  const defenders = {};
  for (const n of Object.keys(line)) defenders[n] = world.player("them", Number(n));
  const fullback = world.player("them", 15);
  const ref = world.player("ref");
  const rush = 3.6; // de combien la ligne monte pendant la mise en place

  const heroPath = nine
    ? route([[hx + s * 1.2, 39.5], [hx, hz]])
    : route([[ruck[0] - s * 0.6, ruck[1] + 0.9], [hx, hz]]);
  const ball = new THREE.Vector3();
  const from = new THREE.Vector3();
  const to = new THREE.Vector3();
  const camera = keys([
    [0, [hx - 62, 28, 64, hx * 0.6, 0.5, 33, 44]],
    [1.4, [hx - 30, 10, 45, hx * 0.6, 1.2, 31.5, 31]],
  ]);
  const passAt = [0.35, 0.8];

  function setupFrame(t) {
    // Le ruck : un des nôtres au sol, un de chaque côté lié par-dessus.
    ruckGround.place(ruck[0], ruck[1] - 0.6, FACE_LINE + s * 0.4).set(pose({ pitch: 1.52, y: -0.8, armL: 2.6, armR: 2.2 }));
    ruckOurs.place(ruck[0], ruck[1] + 0.3, FACE_LINE).set(crouch(0.9));
    ruckTheirs.place(ruck[0] + 0.2, ruck[1] - 1.5, FACE_FIELD).set(crouch(0.9));
    if (nine) {
      nine.place(ruck[0] - s * 0.4, ruck[1] + 1.0, headingTo(ruck[0], ruck[1], hx, hz)).set(t < passAt[0] - 0.15 ? crouch(1) : pass(span(t, passAt[0] - 0.15, passAt[0] + 0.15), s > 0 ? -1 : 1));
      runner(hero, heroPath, t, 0, 1.4, { from: 0.6, to: 0.7, speed: 0.5, carry: t > passAt[1] ? "two" : "none" });
      if (t < passAt[0]) world.ballAt(carried(nine, "low", ball), new THREE.Vector3(1, 0, 0));
      else if (t < passAt[1]) {
        carried(nine, "two", from);
        carried(hero, "two", to);
        world.ballAt(lob(from, to, 0.4, span(t, passAt[0], passAt[1]), ball), new THREE.Vector3(to.x - from.x, 0, to.z - from.z));
      } else world.ballAt(carried(hero, "two", ball), new THREE.Vector3(1, 0, 0));
    } else {
      // Demi de mêlée lui-même : il ramasse au pied du ruck et s'écarte.
      if (t < 0.4) hero.place(ruck[0] - s * 0.6, ruck[1] + 0.9, headingTo(ruck[0], ruck[1], hx, hz)).set(crouch(1 - span(t, 0.2, 0.4)));
      else runner(hero, heroPath, t, 0.4, 1.4, { from: 0.3, to: 0.7, speed: 0.5, carry: "two" });
      world.ballAt(carried(hero, t < 0.3 ? "low" : "two", ball), new THREE.Vector3(1, 0, 0));
    }
    runner(twelve, route([[hx - s * 6, 39], [hx - s * 6.5, hz + 0.8]]), t, 0, 1.4, { from: 0.5, to: 0.6, speed: 0.45 });
    runner(thirteen, route([[hx - s * 12, 40], [hx - s * 12.5, hz + 1.5]]), t, 0, 1.4, { from: 0.5, to: 0.6, speed: 0.45 });
    // La ligne de défense monte d'un bloc.
    for (const [n, [x, z]] of Object.entries(line)) {
      runner(defenders[n], route([[x, z - rush], [x - s * 0.6, z]]), t, 0, 1.4, { from: 0.7, to: 0.95, speed: 0.75 });
    }
    fullback.place(hx * 0.3, 13, FACE_FIELD).set(ready(0.4));
    ref.place(ruck[0] + s * 3, ruck[1] - 1.5, headingTo(ruck[0] + s * 3, ruck[1], hx, hz)).set(ready(0.1));
    const [cx, cy, cz, lx, ly, lz, fov] = camera(t);
    return { pos: [cx, cy, cz], look: [lx, ly, lz], fov };
  }

  const setup = {
    duration: 1.4,
    frame: setupFrame,
    cues: [{ at: 0.1, run: () => world.crowd(world.pressure > 1 ? "standing" : "seated") }],
  };

  // Le point de chute du drop, juste devant lui ; l'intervalle dans la ligne, entre leur
  // 10 et leur 12, où file le petit coup de pied.
  const dropPoint = new THREE.Vector3(hx, 0.18, hz - 0.5);
  const gapX = hx - s * 2.6;
  const regather = [hx - s * 3, 19.5];
  let aimed = null;

  function preview(key) {
    const draw = world.draw;
    if (key === "drop") {
      aimed ??= goalKick(dropPoint, world.wind, true, seeded(5), { elevation: 30 });
      const points = aimed.points(1.1);
      // La courbe dans l'air, et son ombre sur la pelouse jusqu'aux perches.
      return [draw.arc(points), draw.path(points.map(([x, , z]) => [x, z]), { width: 0.3 }), draw.mark([0, 0], 1.2)];
    }
    if (key === "grubber") {
      return [draw.path([[hx, hz - 0.8], [gapX, 29], [regather[0], regather[1] + 1]]), draw.mark(regather)];
    }
    const a = carried(hero, "two", new THREE.Vector3());
    const b = carried(twelve, "two", new THREE.Vector3());
    const arc = [];
    for (let i = 0; i <= 10; i++) arc.push(lob(a, b, 0.35, i / 10).toArray());
    const tx = twelve.root.position.x;
    const tz = twelve.root.position.z;
    return [draw.arc(arc, 0.08), draw.path([[tx, tz], [tx - s * 0.6, tz - 6]]), draw.mark([tx - s * 0.6, tz - 6.5])];
  }

  const celebrate = (good, big = true) => {
    if (good) {
      world.crowd("cheer", "us");
      world.sound(world.homeIsUs ? (big ? "roar" : "roar") : "groan");
    } else {
      world.crowd(world.homeIsUs ? "seated" : "cheer", world.homeIsUs ? "us" : "them");
      world.sound(world.homeIsUs ? "groan" : "roar");
    }
  };

  // Les défenseurs continuent leur montée après l'arrêt sur image.
  const pressOn = (t, until = 1.2) => {
    for (const [n, [x, z]] of Object.entries(line)) {
      runner(defenders[n], route([[x - s * 0.6, z], [x - s * 0.9, z + 3]]), t, 0, until, { from: 0.95, to: 0.4, speed: 0.75 });
    }
  };

  function dropOutcome(result) {
    const made = result.success;
    const flight = goalKick(dropPoint, world.wind, made, rng, { elevation: 30 });
    const kickAt = 0.42;
    const crossAt = kickAt + flight.crossAt;
    const rest = new THREE.Quaternion();
    const q = new THREE.Quaternion();
    const charger = defenders[10];
    return {
      duration: crossAt + 2,
      cues: [
        { at: kickAt, run: () => world.sound("kick") },
        { at: crossAt, run: () => celebrate(made) },
      ],
      frame(t) {
        setupFrame(1.4);
        pressOn(t, 1);
        // Leur 10 se jette pour contrer, bras levés, trop tard.
        const leap = span(t, 0.25, 0.75);
        charger.place(lerp(line[10][0] - s * 0.6, hx + s * 0.4, smooth(leap)), lerp(line[10][1], hz - 1.6, smooth(leap)), FACE_FIELD).set({ ...jump(Math.sin(leap * Math.PI)), lift: Math.sin(leap * Math.PI) * 0.5 });
        hero.place(hx, hz, headingTo(hx, hz, 0, 0)).set(t < 0.2 ? HOLD : kick(span(t, 0.2, kickAt + 0.35), true));
        if (t < 0.25) world.ballAt(carried(hero, "two", ball), new THREE.Vector3(0, 1, 0));
        else if (t < kickAt) world.ballAt(lerpBall(carried(hero, "two", from), dropPoint, span(t, 0.25, kickAt)), new THREE.Vector3(0, 1, 0));
        else {
          flight.at(t - kickAt, ball, q, rest);
          world.ball.position.copy(ball);
          world.ball.quaternion.copy(q);
        }
        if (t > crossAt && made) ref.set(tryAward(smooth(span(t, crossAt, crossAt + 0.4))));
        if (t > crossAt + 0.3) [hero, twelve, thirteen].forEach((player, i) => player.set(made ? cheer(t * 1.6 + i) : dejected()));
        const follow = smooth(span(t, kickAt, kickAt + 0.8));
        const fx = lerp(hx * 0.6, ball.x, follow);
        const fz = lerp(31.5, Math.max(0, ball.z), follow);
        const fy = lerp(1.2, Math.min(ball.y, 8), follow);
        const settle = smooth(span(t, crossAt + 0.2, crossAt + 1.2));
        return {
          pos: [lerp(hx - 30, fx - 34, follow), lerp(10, 11, follow), lerp(45, fz + 22, follow)],
          look: [lerp(fx, 0, settle), lerp(fy, 4, settle), lerp(fz, 0, settle)],
          fov: lerp(31, 34, follow),
        };
      },
    };
  }

  function grubberOutcome(result) {
    const kickAt = 0.3;
    const won = result.success;
    const stop = won ? [regather[0], regather[1]] : [line[12][0] - s * 0.5, 30.4];
    const rollEnd = won ? 1.75 : 0.95;
    const kickFrom = new THREE.Vector3(hx, 0.25, hz - 0.6);
    const stopPoint = new THREE.Vector3(stop[0], 0.15, stop[1]);
    const heroRun = route([[hx, hz], [gapX + s * 0.3, 29.5], [regather[0], regather[1] + 0.3], [regather[0] - s * 0.3, 15]]);
    const thief = defenders[12];
    const runBack = route([stop, [stop[0] + s * 2, 40]]);
    const duration = won ? 3.0 : 2.6;
    return {
      duration,
      cues: [
        { at: kickAt, run: () => world.sound("kick") },
        { at: rollEnd, run: () => (won ? celebrate(true, false) : world.sound("groan")) },
      ],
      frame(t) {
        setupFrame(1.4);
        pressOn(t, 0.8);
        if (t < kickAt + 0.25) hero.place(hx, hz, FACE_LINE).set(t < 0.1 ? HOLD : kick(span(t, 0.1, kickAt + 0.25)));
        else if (won) runner(hero, heroRun, t, kickAt + 0.25, duration, { from: 0.6, to: 1, speed: 1, carry: t > rollEnd ? "one" : "none" });
        else {
          const k = span(t, kickAt + 0.25, 1.4);
          hero.place(hx - s * 1.2 * smooth(k), hz - 2.5 * smooth(k), FACE_LINE).set(k < 1 ? run(k * 2, 0.5) : dejected());
        }
        // Les défenseurs se retournent pour courir après.
        if (won) {
          for (const n of [10, 12, 7]) {
            const [x, z] = line[n];
            runner(defenders[n], route([[x - s * 0.6, z], [x - s * 0.6, z + 1], [regather[0] + (n - 10) * 0.6, 21]]), t, 0.6, duration, { from: 0.2, to: 0.9, speed: 0.9 });
          }
        }
        // Le ballon roule : jusqu'à lui, ou dans les bras de leur 12.
        if (t < kickAt) world.ballAt(carried(hero, "two", ball), new THREE.Vector3(1, 0, 0));
        else if (t < rollEnd) world.ballAt(grubber(kickFrom, stopPoint, span(t, kickAt, rollEnd), won ? 5 : 3, ball), new THREE.Vector3(Math.sin(t * 14), 0.3, Math.cos(t * 14)));
        else if (won) world.ballAt(carried(hero, "one", ball), new THREE.Vector3(0, 0, 1));
        else {
          if (t < rollEnd + 0.35) thief.place(stop[0], stop[1] + 0.4, FACE_LINE).set(crouch(1));
          else runner(thief, runBack, t, rollEnd + 0.35, duration, { from: 0.3, to: 0.9, speed: 0.8, carry: "one" });
          world.ballAt(carried(thief, t < rollEnd + 0.35 ? "low" : "one", ball), new THREE.Vector3(0, 0, 1));
        }
        const fx = ball.x;
        const fz = ball.z;
        return { pos: [fx - 30, 10.5, fz + 13], look: [fx * 0.8, 1, fz - 1], fov: 32 };
      },
    };
  }

  function handsOutcome(result) {
    const good = result.success;
    const releaseAt = 0.25;
    const arriveAt = 0.6;
    const start = [twelve.root.position.x, twelve.root.position.z];
    const charge = route([start, [start[0] - s * 0.6, 31.5]]);
    const marker = defenders[12];
    // Où tombe une passe ratée, et où elle finit de rebondir.
    const feet = new THREE.Vector3(start[0] - s * 0.5, 0.12, 32.4);
    const loose = new THREE.Vector3(feet.x - s * 0.8, 0.12, feet.z - 1.6);
    const duration = good ? 2.6 : 2.4;
    return {
      duration,
      cues: [
        { at: good ? 1.45 : 0.62, run: () => world.sound(good ? "impact" : "groan") },
      ],
      frame(t) {
        setupFrame(1.4);
        pressOn(t, 1.4);
        hero.place(hx, hz, FACE_LINE).set(t < releaseAt + 0.2 ? pass(span(t, releaseAt - 0.1, releaseAt + 0.2), s > 0 ? 1 : -1) : ready(0.2));
        if (t > releaseAt + 0.2) runner(hero, route([[hx, hz], [hx - s * 3, hz - 3]]), t, releaseAt + 0.3, duration, { from: 0.3, to: 0.5, speed: 0.5 });
        carried(hero, "two", from);
        if (good) {
          runner(twelve, charge, t, 0, 1.45, { from: 0.6, to: 1, speed: 0.85, carry: t > arriveAt ? "two" : "none" });
          if (t > 1.45) twelve.set(run(t * 2.4, 0.4, "one"));
          const [mx, mz] = line[12];
          if (t < 1.45) runner(marker, route([[mx - s * 0.6, mz], [start[0] - s * 0.6, 30.8]]), t, 0, 1.45, { from: 0.9, to: 0.6, speed: 0.75 });
          else marker.place(start[0] - s * 0.6, 30.8, FACE_FIELD).set(tackle(0.35));
          if (t < releaseAt) world.ballAt(from, new THREE.Vector3(1, 0, 0));
          else if (t < arriveAt) world.ballAt(lob(from, carried(twelve, "two", to), 0.35, span(t, releaseAt, arriveAt), ball), new THREE.Vector3(1, 0, 0));
          else world.ballAt(carried(twelve, t > 1.45 ? "one" : "two", ball), new THREE.Vector3(0, 0, 1));
        } else {
          // La passe tombe dans les pieds, rebondit, et leur 12 plonge dessus.
          runner(twelve, charge, t, 0, 0.9, { from: 0.6, to: 0.2, speed: 0.7 });
          if (t > 0.9) twelve.set(crouch(0.6));
          if (t < releaseAt) world.ballAt(from, new THREE.Vector3(1, 0, 0));
          else if (t < arriveAt) world.ballAt(lob(from, feet, 0.25, span(t, releaseAt, arriveAt), ball), new THREE.Vector3(1, 0, 0));
          else world.ballAt(grubber(feet, loose, span(t, arriveAt, 1.3), 2, ball), new THREE.Vector3(Math.sin(t * 11), 0.2, 1));
          const [mx, mz] = line[12];
          if (t < 1.3) runner(marker, route([[mx - s * 0.6, mz], [loose.x, loose.z - 0.6]]), t, 0, 1.3, { from: 0.9, to: 0.8, speed: 0.8 });
          else marker.place(loose.x, loose.z - 0.4, FACE_FIELD).set(crouch(1));
        }
        const fx = lerp(hx, twelve.root.position.x, 0.6);
        return { pos: [fx - 28, 9.5, 44], look: [fx * 0.8, 1, 32], fov: 30 };
      },
    };
  }

  const wide = { pos: [hx - 34, 26, 50], look: [hx * 0.5, -2, 22], fov: 42 };

  return {
    setup,
    preview,
    previewShot: (key) => (key === "hands" ? null : wide),
    outcome(key, result) {
      if (key === "drop") return dropOutcome(result);
      if (key === "grubber") return grubberOutcome(result);
      return handsOutcome(result);
    },
  };
}

// Le ballon lâché des mains vers le sol (le drop).
function lerpBall(a, b, k) {
  return a.lerp(b, k * k);
}
