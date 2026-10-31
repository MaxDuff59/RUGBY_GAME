import * as THREE from "three";

import { cheer, dejected, dive, ground, pass, ready, run, signal, tackle, tryAward } from "../rig.js";
import {
  FACE_FIELD,
  FACE_LINE,
  broadcast,
  carried,
  clamp,
  grubber,
  keys,
  lerp,
  lob,
  reaction,
  route,
  runner,
  smooth,
  snapshot,
  span,
  trail,
} from "./common.js";

// Carrière de joueur, « Deux contre un » (two_on_one), toujours enchaîné sur un
// franchissement : le joueur incarné file, un partenaire à sa hauteur, un seul
// défenseur devant. Finir seul (il contourne le défenseur), la feinte de passe (le
// défenseur mord, il rentre), ou servir le partenaire.
//
// Enchaînée dans la même scène (`handover`) : le joueur incarné et son soutien
// repartent d'où ils sont, l'arbitre suit, les autres finissent leur course.

export function buildTwoOnOne(world, data, handover) {
  const previous = handover?.cast ?? [];
  let hero = previous.find((player) => player.role === "hero");
  const leftovers = new Map();
  if (hero) {
    world.keep(hero);
  } else {
    hero = world.player("us", data.hero ?? 13, { hero: true });
    hero.place(4, 24, Math.PI);
  }
  const h0 = [hero.root.position.x, hero.root.position.z];
  // Le soutien : le plus proche des nôtres, s'il est à portée ; sinon un ailier arrive.
  const mates = previous.filter((player) => player.team === "us" && player !== hero && Math.abs(player.current.pitch) < 0.8);
  mates.sort((a, b) => a.root.position.distanceTo(hero.root.position) - b.root.position.distanceTo(hero.root.position));
  let support = mates[0] && mates[0].root.position.distanceTo(hero.root.position) < 9 ? world.keep(mates[0]) : null;
  const side = support ? Math.sign(support.root.position.x - h0[0]) || 1 : h0[0] > 0 ? -1 : 1;
  if (!support) {
    support = world.player("us", data.hero === 14 ? 11 : 14);
    support.place(h0[0] + side * 4.5, h0[1] + 3, Math.PI);
  }
  const s0 = [support.root.position.x, support.root.position.z];
  let ref = previous.find((player) => player.team === "ref");
  ref = ref ? world.keep(ref) : world.player("ref");
  const r0 = [ref.root.position.x, ref.root.position.z];
  for (const player of previous) {
    if (player === hero || player === support || player === ref) continue;
    leftovers.set(world.keep(player), snapshot(player, player.team === "them" ? 6.5 : 5));
  }
  const defender = world.player("them", 15);

  // La course jusqu'à l'arrêt sur image, en gardant de quoi finir avant la ligne.
  const run1 = Math.min(6, Math.max(0, h0[1] - 9));
  const hx = h0[0] + side * -0.4;
  const fz = h0[1] - run1;
  const sup = [hx + side * 4, fz + 0.8];
  const gap = Math.min(5.5, fz - 1.5);
  const def = [hx + side * 1.6, fz - gap];
  const d0 = [def[0] - side * 0.5, Math.max(def[1] - 6, -2)];
  const ball = new THREE.Vector3();
  const from = new THREE.Vector3();
  const to = new THREE.Vector3();
  const shot = broadcast(hx + side * 1.5, fz - 2.5, { far: 0.95 });
  const startShot = broadcast(h0[0], h0[1] - 1.5);
  const camera = keys([
    [0, [...startShot.pos, ...startShot.look, startShot.fov]],
    [1.2, [...shot.pos, ...shot.look, shot.fov]],
  ]);

  function setupFrame(t) {
    runner(hero, route([h0, [hx, fz]]), t, 0, 1.2, { from: 1, to: 0.9, speed: 0.95, carry: "one" });
    runner(support, route([s0, sup]), t, 0, 1.2, { from: 1, to: 0.9, speed: 0.95 });
    runner(defender, route([d0, def]), t, 0, 1.2, { from: 0.5, to: 0.6, speed: 0.6 });
    defender.root.rotation.y = defender.heading = FACE_FIELD;
    if (t >= 1.2) defender.set(ready(0.6));
    runner(ref, route([r0, [hx - side * 7, fz + 3]]), t, 0, 1.2, { from: 0.8, to: 0.6, speed: 0.6 });
    leftovers.forEach((start, player) => trail(player, t, start));
    world.ballAt(carried(hero, "one", ball), new THREE.Vector3(0, 0, 1));
    const [cx, cy, cz, lx, ly, lz, fov] = camera(t);
    return { pos: [cx, cy, cz], look: [lx, ly, lz], fov };
  }

  const setup = {
    duration: 1.2,
    frame: setupFrame,
    cues: [{ at: 0.05, run: () => world.crowd("standing") }],
  };

  // Les trajets : par l'extérieur du défenseur, en rentrant après la feinte, le soutien.
  const lineZ = -1.3;
  const around = [[hx, fz], [hx - side * 2.2, def[1] + 1], [hx - side * 2.4, lineZ]];
  const inside = [[hx, fz], [hx + side * 0.7, fz - gap * 0.45], [hx - side * 0.8, def[1] - 0.5], [hx - side * 0.6, lineZ]];
  const supportLine = [sup, [sup[0] + side * 0.3, lineZ]];

  function preview(key) {
    const draw = world.draw;
    if (key === "finish") return [draw.path(around), draw.mark(around[2])];
    if (key === "dummy") return [draw.path(inside), draw.mark(def, 0.7), draw.mark(inside[3])];
    const a = carried(hero, "two", new THREE.Vector3());
    const b = carried(support, "two", new THREE.Vector3());
    const arc = [];
    for (let i = 0; i <= 10; i++) arc.push(lob(a, b, 0.35, i / 10).toArray());
    return [draw.arc(arc, 0.08), draw.path(supportLine), draw.mark(supportLine[1])];
  }

  // Un coureur qui va jusqu'à la ligne et aplatit, ou est plaqué en route (`caughtAt` :
  // la part du trajet où le défenseur le prend).
  function finishRun(player, path, t, t0, speed, { caughtAt = null, carry = "one" } = {}) {
    const r = route(path);
    const length = caughtAt === null ? r.total : r.total * caughtAt;
    const tEnd = t0 + length / speed;
    const sub = route([path[0], ...path.slice(1)]);
    if (t < tEnd) {
      const spot = sub.at(((t - t0) / (tEnd - t0)) * length);
      player.place(spot.x, spot.z, spot.heading).set(run((spot.z - path[0][1]) / -2.3, 1, carry));
      if (t < t0) player.set(run(t * 3, 1, carry));
      return { tEnd, spot, done: false };
    }
    const spot = sub.at(length);
    const k = span(t, tEnd, tEnd + 0.45);
    if (caughtAt === null) {
      player.place(spot.x, lerp(spot.z + 0.6, spot.z, smooth(k)), FACE_LINE).set(t > tEnd + 1.1 ? cheer(t * 1.6) : dive(k));
    } else {
      player.place(spot.x, spot.z - 0.6 * k, spot.heading).set(k < 1 ? tackle(k * 0.6) : ground());
    }
    return { tEnd, spot, done: true };
  }

  function outcomeFor(key, good) {
    const speed = 7.8;
    // Où le défenseur prend le porteur, quand il le prend.
    const caughtAt = good ? null : key === "give" ? null : 0.55;
    const carrierPath = key === "finish" ? around : key === "dummy" ? inside : supportLine;
    const release = 0.2;
    const arrive = 0.55;
    const t0 = key === "give" ? arrive : 0;
    // Passe en avant : le ballon file devant le partenaire et tombe.
    const forward = key === "give" && !good;
    const length = route(carrierPath).total * (caughtAt ?? 1);
    const tEnd = t0 + length / speed;
    const duration = forward ? 2.6 : tEnd + 1.9;
    const scoreAt = tEnd + 0.4;
    const fallBall = new THREE.Vector3(sup[0] + side * 0.3, 0.12, sup[1] - 4);
    const bounce = new THREE.Vector3(fallBall.x, 0.12, fallBall.z - 2);
    return {
      duration,
      cues: forward
        ? [
            { at: 0.9, run: () => world.sound("whistle") },
            { at: 1.0, run: () => reaction(world, false) },
          ]
        : [
            ...(caughtAt === null ? [] : [{ at: tEnd, run: () => world.sound("impact") }]),
            {
              at: caughtAt === null ? scoreAt : tEnd + 0.3,
              run: () => {
                if (caughtAt === null) world.sound("whistle", true);
                reaction(world, caughtAt === null);
              },
            },
          ],
      frame(t) {
        setupFrame(1.2);
        leftovers.forEach((start, player) => trail(player, 1.2 + t, start));
        const carrier = key === "give" ? support : hero;
        if (key === "give") {
          // La passe, puis le joueur incarné suit et se fait plaquer après coup.
          hero.place(hx, fz - Math.min(t, 0.5) * 3, FACE_LINE).set(t < release + 0.3 ? pass(span(t, release - 0.1, release + 0.25), side > 0 ? 1 : -1) : run(t * 3, 0.5));
          if (t > 0.7) {
            const k = span(t, 0.7, 1.2);
            hero.set(k < 1 ? ready(0.4) : t > scoreAt + 0.5 && good ? cheer(t * 1.6) : dejected());
          }
          carried(hero, "two", from);
          if (!forward) {
            const done = finishRun(support, carrierPath, t, t0, speed);
            if (t < release) world.ballAt(from, new THREE.Vector3(1, 0, 0));
            else if (t < arrive) world.ballAt(lob(from, carried(support, "two", to), 0.35, span(t, release, arrive), ball), new THREE.Vector3(1, 0, 0));
            else world.ballAt(carried(support, done.done ? "low" : "one", ball), new THREE.Vector3(0, 0, 1));
          } else {
            runner(support, route([sup, [sup[0], sup[1] - 3.5]]), t, 0, 1.0, { from: 0.9, to: 0.1, speed: 0.6 });
            if (t > 1.0) support.set(dejected());
            if (t < release) world.ballAt(from, new THREE.Vector3(1, 0, 0));
            else if (t < 0.75) world.ballAt(lob(from, fallBall, 0.6, span(t, release, 0.75), ball), new THREE.Vector3(1, 0, 0));
            else world.ballAt(grubber(fallBall, bounce, span(t, 0.75, 1.4), 2, ball), new THREE.Vector3(Math.sin(t * 10), 0.3, 1));
          }
          // Le défenseur hésite, puis plaque le joueur incarné (sans ballon) ou ramasse.
          const k = span(t, 0, 0.7);
          defender.place(lerp(def[0], hx + side * 0.4, smooth(k)), lerp(def[1], fz - 2, smooth(k)), FACE_FIELD).set(k < 1 ? run(t * 3, 0.6) : tackle(span(t, 0.7, 1.1) * 0.5));
        } else {
          const done = finishRun(hero, carrierPath, t, 0, speed, { caughtAt });
          world.ballAt(carried(hero, done.done && caughtAt === null ? "low" : "one", ball), new THREE.Vector3(0, 0, 1));
          if (key === "dummy") {
            // La feinte : le buste tourné vers le soutien, sans lâcher le ballon.
            if (t > 0.15 && t < 0.5) hero.set({ ...pass(span(t, 0.15, 0.45) * 0.6, side > 0 ? 1 : -1), legL: hero.current.legL, legR: hero.current.legR });
          }
          // Le défenseur : il mord (feinte réussie), plonge dans le vide, ou plaque.
          const meet = caughtAt === null ? null : route(carrierPath).at(route(carrierPath).total * caughtAt);
          if (meet) {
            runner(defender, route([def, [meet.x + side * 0.3, meet.z - 0.5]]), t, 0, tEnd, { from: 0.6, to: 1, speed: 0.8 });
            if (t >= tEnd) defender.place(meet.x + side * 0.3, meet.z - 0.8, FACE_FIELD).set(tackle(span(t, tEnd, tEnd + 0.45)));
          } else {
            const target = key === "dummy" ? [sup[0] - side * 0.5, def[1] + 0.5] : [hx - side * 1.6, def[1] + 0.8];
            const k = span(t, 0, 0.6);
            defender.place(lerp(def[0], target[0], smooth(k)), lerp(def[1], target[1], smooth(k)), FACE_FIELD + side * 0.4);
            defender.set(k < 1 ? run(t * 3, 0.7) : t < 1.1 ? tackle(span(t, 0.6, 1.1)) : ground());
          }
          if (good) runner(support, route([sup, [sup[0], 2]]), t, 0, tEnd, { from: 0.9, to: 0.4, speed: 0.7 });
          else runner(support, route([sup, [sup[0] - side * 1, fz - 4]]), t, 0, 1.4, { from: 0.9, to: 0.1, speed: 0.6 });
          if (t > tEnd + 0.8) support.set(good ? cheer(t * 1.4) : dejected());
        }
        // L'arbitre arrive sur l'action et accorde l'essai (ou siffle l'en-avant).
        const r = [hx - side * 7, fz + 3];
        const target = [lerp(r[0], hx - side * 3, 0.7), clamp(fz - 6, 1.5, 30)];
        runner(ref, route([r, target]), t, 0, Math.max(1, tEnd), { from: 0.6, to: 0.4, speed: 0.6 });
        if (!forward && caughtAt === null && t > scoreAt) ref.set(tryAward(smooth(span(t, scoreAt, scoreAt + 0.35))));
        if (forward && t > 1) ref.set(signal(side, smooth(span(t, 1, 1.3))));
        const focus = carrier.root.position;
        return broadcast(lerp(hx, focus.x, 0.8), Math.max(focus.z - 1.5, 1));
      },
    };
  }

  return {
    setup,
    preview,
    outcome(key, result) {
      return outcomeFor(key, result.success);
    },
  };
}
