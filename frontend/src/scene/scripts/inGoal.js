import * as THREE from "three";

import { TOUCH } from "../field.js";
import { cheer, crouch, dejected, dive, ground, kick, mixPose, ready, run, signal, tackle, tryAward } from "../rig.js";
import { FACE_LINE, broadcast, carried, grubber, headingTo, keys, lerp, lob, reaction, route, runner, smooth, span, tumble } from "./common.js";

// Carrière de joueur, « Ballon dans l'en-but » (in_goal) : leur coup de pied rasant roule
// vers notre en-but (la ligne z = 0, le ballon mort en z = -10), leur ailier à la hauteur
// du joueur incarné. Plonger dessus, le pousser en ballon mort, ou le dégager au pied.
//
// Les échecs suivent l'effet tiré : essai encaissé, ballon perdu, ou (`none`) le ballon
// échappe à l'ailier et sort, ou le joueur se jette dessus au dernier moment.

const v = (x, y, z) => new THREE.Vector3(x, y, z);
const aim = (x, z, options) => {
  const shot = broadcast(x, z, options);
  shot.look[0] = x;
  return shot;
};

export function buildInGoal(world, data) {
  const rng = world.rng;
  const s = rng() < 0.5 ? -1 : 1;
  const hx = s * (12 + rng() * 6); // assez loin des poteaux
  const T = 1.5;
  const heroNo = data.hero ?? 15;
  const hero = world.player("us", heroNo, { hero: true });
  const mate = world.player("us", heroNo === 14 ? 15 : 14);
  const wing = world.player("them", s > 0 ? 14 : 11);
  const second = world.player("them", 13);
  const ref = world.player("ref");

  const hAt = [hx, 3.2];
  const wAt = [hx + 2.4, 3.4];
  const secondAt = [hx + 6, 14];
  const mateAt = [hx - 4, 7];
  const refAt = [hx + 9, 6];
  const bx = hx + 1;
  const ball = new THREE.Vector3();
  const shot = aim(hx + 1, -0.2, { far: 0.92, fov: 33, y: -0.9 });
  const camera = keys([
    [0, [hx - 34, 18, 34, hx * 0.8, 0, 8, 42]],
    [T, [...shot.pos, ...shot.look, shot.fov]],
  ]);

  // Le ballon qui roule : `u`, le temps depuis le choix (négatif avant). Il ralentit et
  // s'arrêterait juste avant le ballon mort, si personne n'y touchait.
  const rolled = (u) => {
    const c = Math.min(u, 10 / 3);
    return 5 * c - 0.75 * c * c;
  };
  const dir = v(0, 0, -1);
  function rolling(u) {
    const d = rolled(u);
    const speed = Math.max(0, 5 - 1.5 * Math.min(u, 10 / 3));
    const y = 0.13 + Math.abs(Math.sin(d * 1.4)) * 0.26 * Math.min(1, speed / 7);
    world.ballAt(ball.set(bx, y, -1.5 - d), tumble(dir, d * 2.6));
  }

  function setupFrame(t) {
    runner(hero, route([[hx - 0.4, 16], hAt]), t, 0, T, { from: 1, to: 1, speed: 1 });
    runner(wing, route([[wAt[0] + 0.4, 16.2], wAt]), t, 0, T, { from: 1, to: 1, speed: 1 });
    runner(second, route([[secondAt[0], 26], secondAt]), t, 0, T, { from: 0.9, to: 0.9, speed: 0.85 });
    runner(mate, route([[mateAt[0], 18], mateAt]), t, 0, T, { from: 0.9, to: 0.9, speed: 0.9 });
    runner(ref, route([[refAt[0], 17], refAt]), t, 0, T, { from: 0.8, to: 0.8, speed: 0.6 });
    if (ref.card) ref.card.visible = false;
    rolling(t - T);
    const [cx, cy, cz, lx, ly, lz, fov] = camera(t);
    return { pos: [cx, cy, cz], look: [lx, ly, lz], fov };
  }

  const setup = {
    duration: T,
    frame: setupFrame,
    cues: [{ at: 0.1, run: () => world.crowd("standing") }],
  };

  // Les tracés.
  const stopped = -1.5 - rolled(0.95); // où on rattrape le ballon
  const lift = [hx + 0.9, stopped + 0.55];
  const turnWay = [lift, [hx + 2, stopped - 0.8], [hx + 3.6, stopped - 0.6]];
  const kickFrom = turnWay[2];
  const clearTo = v(s * (TOUCH + 1.5), 0.13, 34);
  const wide = { pos: [hx - 34, 28, 34], look: [lerp(hx, clearTo.x, 0.4), -2, 11], fov: 46 };

  function preview(key) {
    const draw = world.draw;
    if (key === "pounce") return [draw.path([hAt, [hx + 0.8, stopped + 1.6]]), draw.mark([bx, stopped], 0.75)];
    if (key === "dead") return [draw.path([hAt, [hx + 0.7, stopped + 0.5]]), draw.path([[bx, stopped], [bx, -10.8]]), draw.mark([bx, -11], 0.9)];
    const from = v(kickFrom[0], 0.4, kickFrom[1]);
    const arc = [];
    for (let i = 0; i <= 14; i++) arc.push(lob(from, clearTo, 16, i / 14).toArray());
    return [draw.path([hAt, ...turnWay]), draw.arc(arc), draw.mark([clearTo.x - s * 1.5, clearTo.z])];
  }

  const refTry = (t, at, x, z) => ref.place(x + 6.5, z, -Math.PI / 2).set(tryAward(smooth(span(t, at, at + 0.35))));
  const grounded = (player, out = ball) => player.local(0, 0.14, 1.5, out);

  function outcomeFor(key, result) {
    const { success: good, effect } = result;
    const scores = !good && effect === "try_conceded";
    const cues = [];
    let duration = 3;
    let frame;
    const secondRun = (t, end, until = 2.4) => runner(second, route([secondAt, end]), t, 0, until, { from: 0.9, to: 0.3, speed: 0.8 });
    const mateRun = (t, end, until = 1.9) => {
      runner(mate, route([mateAt, end]), t, 0, until, { from: 0.9, to: 0.3, speed: 0.9 });
      if (t >= until) mate.set(ready(0.3));
    };
    const refWhistle = (t, at, spot) => {
      runner(ref, route([refAt, spot]), t, 0, at, { from: 0.7, to: 0.2, speed: 0.7 });
      ref.root.rotation.y = ref.heading = -Math.PI / 2;
      if (t >= at) ref.set(signal(1, smooth(span(t, at, at + 0.3))));
    };

    if (key === "pounce") {
      // Le plongeon, à qui posera la main le premier.
      const touch = 0.95;
      const end = stopped + 1.5;
      const out = v(bx + 0.6, 0.13, -11.2);
      const whistleAt = good ? 1.3 : scores ? touch + 0.25 : 1.8;
      duration = good ? 2.9 : scores ? 3.6 : 3;
      cues.push({ at: touch, run: () => world.sound("impact") }, { at: whistleAt, run: () => world.sound("whistle", scores) });
      if (good) cues.push({ at: whistleAt + 0.1, run: () => reaction(world, true) });
      else if (scores) cues.push({ at: whistleAt + 0.1, run: () => reaction(world, false) });
      else cues.push({ at: whistleAt + 0.1, run: () => world.crowd("standing") });
      frame = (t) => {
        // Le premier, il aplatit le ballon ; l'autre arrive à côté.
        const first = good ? hero : wing;
        const other = good ? wing : hero;
        const firstFrom = good ? hAt : wAt;
        const otherFrom = good ? wAt : hAt;
        const fx = bx;
        const ox = good ? hx + 2.9 : hx - 0.1;
        const k1 = span(t, 0.5, 1);
        first.place(lerp(firstFrom[0], fx, smooth(span(t, 0, 1))), lerp(firstFrom[1], end, smooth(span(t, 0.05, 1))), FACE_LINE).set(k1 > 0 ? dive(k1) : run(t * 3.6, 1));
        const k2 = span(t, 0.72, 1.25);
        other.place(lerp(otherFrom[0], ox, smooth(span(t, 0, 1.2))), lerp(otherFrom[1], end + 0.9, smooth(span(t, 0, 1.22))), FACE_LINE).set(k2 > 0 ? (k2 < 1 ? tackle(k2) : ground()) : run(t * 3.6, 1));
        if (t > 1.6 && good) wing.set(ground());
        if (t < touch) rolling(t);
        else if (good) grounded(hero);
        else if (scores) grounded(wing);
        else if (t < 1.7) grubber(v(bx, 0.15, stopped), out, span(t, touch, 1.7), 3, ball);
        else ball.copy(out);
        if (t >= touch) world.ballAt(ball, good || scores ? v(1, 0, 0) : v(1, 0.3, Math.sin(t * 8)));
        if (scores) {
          if (t > 2.5) wing.place(fx, end, FACE_LINE).set(cheer(t * 1.5));
          if (t > 2.5) world.ballAt(ball.set(fx, 0.14, end - 1.5), v(1, 0, 0));
          if (t > whistleAt) refTry(t, whistleAt, fx, end + 1);
        } else refWhistle(t, whistleAt, [hx + 7, -1.6]);
        mateRun(t, [hx - 2, -1]);
        secondRun(t, [hx + 5, 2]);
        return aim(hx + 1, lerp(-0.2, -2.8, smooth(span(t, 0, 1.1))), { far: 0.9, fov: 33, y: -0.9 });
      };
    } else if (key === "dead") {
      // Il court à côté du ballon, l'ailier sur l'épaule, et le pousse d'une main.
      const touch = 0.95;
      const slap = [hx + 0.65, stopped + 0.55];
      const dead = v(bx, 0.13, -11.2); // dehors
      const short = v(bx, 0.13, -8.9); // il s'arrête à un mètre
      const stops = 2;
      const end = good ? dead : short;
      const whistleAt = good ? 1.8 : scores ? 2.25 : 2.3;
      duration = good ? 2.9 : scores ? 4 : 3.3;
      cues.push({ at: touch, run: () => world.sound("kick") });
      if (good) cues.push({ at: whistleAt, run: () => world.sound("whistle") }, { at: whistleAt + 0.1, run: () => reaction(world, true) });
      else if (scores) cues.push({ at: whistleAt, run: () => (world.sound("whistle", true), reaction(world, false)) });
      else cues.push({ at: 2, run: () => world.sound("impact") }, { at: whistleAt, run: () => world.sound("whistle") }, { at: whistleAt + 0.1, run: () => world.crowd("standing") });
      frame = (t) => {
        runner(hero, route([hAt, slap]), t, 0, touch - 0.1, { from: 1, to: 0.8, speed: 1 });
        if (t >= touch - 0.25 && t < touch + 0.15) hero.set(crouch(0.55));
        if (t < touch) rolling(t);
        else if (t < stops) world.ballAt(grubber(v(bx, 0.15, stopped), end, span(t, touch, good ? 1.75 : stops), good ? 4 : 3, ball), tumble(dir, t * 9));
        else world.ballAt(ball.copy(end), v(1, 0, 0.2));

        if (good) {
          // Le ballon sort : l'ailier s'arrête, résigné ; lui reste entre les deux.
          runner(hero, route([slap, [hx + 0.6, -8.4]]), t, touch + 0.15, 1.8, { from: 0.7, to: 0.05, speed: 0.6 });
          if (t >= 1.8) hero.set(t > 2.4 ? cheer(t * 1.4) : ready(0.3));
          runner(wing, route([wAt, [hx + 2.6, -4.8], [hx + 2.5, -6.8]]), t, 0, 1.55, { from: 1, to: 0.04, speed: 0.9 });
          if (t >= 1.55) wing.set(t > 2.2 ? dejected() : ready(0.3));
          refWhistle(t, whistleAt, [hx + 8, -2.5]);
        } else if (scores) {
          // Le ballon s'arrête, il l'a dépassé : l'ailier plonge dessus.
          const way = [hx + 2, -6.6];
          const diveEnd = [bx, -7.4];
          runner(hero, route([slap, [hx - 0.4, -8.6]]), t, touch + 0.15, 1.8, { from: 0.7, to: 0.05, speed: 0.6 });
          if (t >= 1.8) hero.place(hx - 0.4, -8.6, headingTo(hx - 0.4, -8.6, bx, -8.9)).set(t > 2.5 ? dejected() : ready(0.4));
          runner(wing, route([wAt, way]), t, 0, 1.75, { from: 1, to: 0.8, speed: 0.95 });
          if (t >= 1.75) {
            const k = span(t, 1.75, 2.2);
            wing.place(lerp(way[0], diveEnd[0], smooth(k)), lerp(way[1], diveEnd[1], smooth(k)), FACE_LINE).set(t > 3.2 ? cheer(t * 1.4) : dive(k));
          }
          if (t >= 2.1) world.ballAt(ball.copy(short), v(1, 0, 0));
          if (t > 2.25) refTry(t, 2.25, bx, -5.5);
          else refWhistle(t, 2.25, [hx + 8, -3]);
        } else {
          // Le ballon s'arrête : il se retourne et s'y jette, l'ailier lui tombe dessus.
          const back = [bx, -7.4];
          runner(hero, route([slap, [hx + 0.4, -5.6]]), t, touch + 0.15, 1.5, { from: 0.7, to: 0.8, speed: 0.7 });
          if (t >= 1.5) {
            const k = span(t, 1.5, 1.95);
            hero.place(lerp(hx + 0.4, back[0], smooth(k)), lerp(-5.6, back[1], smooth(k)), FACE_LINE).set(dive(k));
          }
          runner(wing, route([wAt, [hx + 2.3, -5.6]]), t, 0, 1.75, { from: 1, to: 0.8, speed: 0.9 });
          if (t >= 1.75) {
            const k = span(t, 1.75, 2.2);
            wing.place(hx + 2.3, lerp(-5.6, -6.6, smooth(k)), FACE_LINE - 0.35).set(k < 1 ? tackle(k) : ground());
          }
          refWhistle(t, whistleAt, [hx + 8, -3]);
        }
        mateRun(t, [hx - 2.4, -1.5]);
        secondRun(t, [hx + 5, 1.5]);
        const follow = smooth(span(t, 0, 1.5));
        return aim(hx + 1, lerp(-0.2, -5, follow), { far: 0.9, fov: 33, y: -0.9 });
      };
    } else {
      // Il ramasse à pleine vitesse, pivote et dégage : loin en touche, ou dévissé.
      const lifted = 0.85;
      const turned = 1.25;
      const strike = 1.34;
      const heading = headingTo(kickFrom[0], kickFrom[1], clearTo.x, clearTo.z);
            const arrive = good ? 3.7 : 2.1;
      const catchSpot = [hx + 8.5, 7.5];
      const lineEnd = [catchSpot[0] - 1, -0.3];
      const tackled = [catchSpot[0] - 1, 3.4];
      const runEnd = scores ? arrive + 7.9 / 8.5 : arrive + 0.45;
      const whistleAt = runEnd + 0.4;
      duration = good ? 4.3 : scores ? whistleAt + 1.9 : runEnd + 1.5;
      cues.push({ at: strike, run: () => world.sound("kick") });
      if (good) cues.push({ at: 2.1, run: () => reaction(world, true) }, { at: arrive, run: () => world.sound("whistle") });
      else {
        cues.push({ at: arrive, run: () => reaction(world, false) });
        if (scores) cues.push({ at: whistleAt, run: () => (world.sound("whistle", true), reaction(world, false)) });
        else cues.push({ at: runEnd, run: () => world.sound("impact") });
      }
      frame = (t) => {
        runner(hero, route([hAt, lift]), t, 0, lifted, { from: 1, to: 0.8, speed: 1 });
        if (t >= lifted - 0.15 && t < lifted + 0.12) hero.set(crouch(0.65));
        if (t >= lifted + 0.12 && t < turned) runner(hero, route(turnWay), t, lifted + 0.12, turned, { from: 0.8, to: 0.5, speed: 0.8, carry: "two" });
        if (t >= turned) {
          hero.place(kickFrom[0], kickFrom[1], heading).set(mixPose(kick(span(t, turned, strike + 0.4)), t > 2.3 && !good ? ready(0.3) : t > 2.7 ? ready(0.15) : kick(1), smooth(span(t, 1.8, 2.3))));
          if (!good && t > arrive + 0.3) hero.set(dejected());
          if (good && t > 2.7) hero.set(cheer(t * 1.4));
        }
        if (!good) {
          runner(second, route([secondAt, catchSpot]), t, 0, arrive, { from: 0.9, to: 0.3, speed: 0.75 });
          if (t >= arrive) runner(second, route([catchSpot, scores ? lineEnd : tackled]), t, arrive, runEnd, { from: 0.3, to: 1, speed: 1, carry: "one" });
        }
        // Le ballon : roulant, ramassé, frappé.
        if (t < lifted) rolling(t);
        else if (t < strike) world.ballAt(carried(hero, t < lifted + 0.12 ? "low" : "two", ball), v(1, 0, 0));
        else {
          const from = v(kickFrom[0] + Math.sin(heading) * 0.55, 0.42, kickFrom[1] + Math.cos(heading) * 0.55);
          const target = good ? clearTo : carried(second, "two", new THREE.Vector3());
          if (t < arrive) world.ballAt(lob(from, target, good ? 16 : 4, span(t, strike, arrive), ball), tumble(v(0, 0, 1), t * 11));
          else if (good) world.ballAt(ball.copy(clearTo), v(1, 0, 0.3));
        }
        // L'ailier, dépassé, plonge trop tard sur le dégagement.
        const wEnd = [hx + 2.4, stopped - 0.2];
        const k = span(t, 1.15, 1.7);
        runner(wing, route([wAt, wEnd]), t, 0, 1.15, { from: 1, to: 0.8, speed: 1 });
        if (t >= 1.15) wing.place(wEnd[0], lerp(wEnd[1], wEnd[1] - 0.3, k), headingTo(wEnd[0], wEnd[1], kickFrom[0], kickFrom[1])).set(k < 1 ? tackle(k) : ground());

        if (good) {
          secondRun(t, [hx + 6.5, 4], 2.2);
          if (t >= 2.2) second.set(dejected());
          mateRun(t, [hx - 1.5, 1.5]);
          const k2 = smooth(span(t, strike, 2.1));
          const base = aim(hx + 2.4, lerp(-0.2, -3, smooth(span(t, 0, 1))), { far: 0.9, fov: 33, y: -0.9 });
          return {
            pos: base.pos.map((value, i) => lerp(value, wide.pos[i], k2)),
            look: base.look.map((value, i) => lerp(value, wide.look[i], k2)),
            fov: lerp(base.fov, wide.fov, k2),
          };
        }
        // Dévissé : leur 13 le récupère à portée.
        if (t >= arrive) {
          if (t >= runEnd && scores) {
            const k3 = span(t, runEnd, runEnd + 0.45);
            second.place(lineEnd[0], lerp(lineEnd[1], lineEnd[1] - 1, smooth(k3)), FACE_LINE).set(t > whistleAt + 1.1 ? cheer(t * 1.4) : dive(k3));
          } else if (t >= runEnd) {
            const k3 = span(t, runEnd, runEnd + 0.45);
            second.place(tackled[0], tackled[1], FACE_LINE).set(k3 < 1 ? tackle(k3 * 0.6) : ground());
          }
          if (t < runEnd) world.ballAt(carried(second, "one", ball), v(0, 0, -1));
          else if (scores) world.ballAt(ball.set(lineEnd[0], lerp(1.05, 0.14, smooth(span(t, runEnd, runEnd + 0.4))), lerp(lineEnd[1], lineEnd[1] - 2.5, smooth(span(t, runEnd, runEnd + 0.4)))), v(1, 0, 0));
          else world.ballAt(ball.lerpVectors(carried(second, "one", new THREE.Vector3()), second.local(0, 0.3, 1.05, new THREE.Vector3()), smooth(span(t, runEnd, runEnd + 0.4))), v(1, 0, 0));
        }
        // Notre partenaire arrive : à temps (ballon perdu, plaqué), ou trop tard.
        if (scores) {
          runner(mate, route([mateAt, [hx + 4, 3.2]]), t, 0, runEnd, { from: 0.6, to: 1, speed: 0.9 });
          if (t >= runEnd) mate.set(ready(0.3));
          if (t > whistleAt) refTry(t, whistleAt, lineEnd[0], 3);
        } else {
          const meet = [tackled[0] - 1.5, tackled[1] - 0.2];
          runner(mate, route([mateAt, meet]), t, 0, runEnd, { from: 0.6, to: 1, speed: 0.9 });
          if (t >= runEnd) mate.place(meet[0], meet[1], Math.PI / 2).set(tackle(span(t, runEnd, runEnd + 0.45)));
        }
        const k2 = smooth(span(t, strike, arrive));
        return aim(lerp(hx + 2.4, second.root.position.x - 1, k2), lerp(lerp(-0.2, -3, smooth(span(t, 0, 1))), Math.max(second.root.position.z - 0.5, -0.5), k2), { far: 0.92, fov: 34, y: -0.9 });
      };
    }
    return {
      duration,
      cues,
      frame(t) {
        setupFrame(T);
        return frame(t);
      },
    };
  }

  return { setup, preview, previewShot: (key) => (key === "clear" ? wide : null), outcome: outcomeFor };
}
