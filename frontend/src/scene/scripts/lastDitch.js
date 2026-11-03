import * as THREE from "three";

import { TOUCH } from "../field.js";
import { cheer, crouch, dejected, dive, ground, mixPose, pose, ready, run, signal, tackle, tryAward } from "../rig.js";
import { FACE_LINE, broadcast, carried, keys, lerp, lob, reaction, route, runner, smooth, span } from "./common.js";

// Carrière de joueur, « La dernière chance » (last_ditch) : leur ailier a percé le long de
// la touche et file vers notre ligne (z = 0), le joueur incarné revient de l'intérieur à
// toute allure. Plonger aux jambes (il le fauche à la cheville, ou sa main glisse), le
// pousser en touche (à un mètre de la ligne, ou l'ailier résiste), ou le ceinturer pour
// l'empêcher d'aplatir (tenu dans l'en-but, ou il s'arrache et plonge).
//
// Les échecs suivent l'effet tiré : essai encaissé, ou plaquage manqué sans points : un
// partenaire revenu de derrière le rattrape in extremis, déséquilibré par le contact.

// Face à face, on se dispute le ballon.
const WRESTLE = pose({ y: -0.1, lean: 0.45, armL: 1.3, armR: 1.4, abL: -0.35, abR: -0.35, elL: 1.0, elR: 0.9, legL: 0.4, legR: -0.2, knL: 0.6, knR: 0.4 });

const v = (x, y, z) => new THREE.Vector3(x, y, z);
const aim = (x, z, options) => {
  const shot = broadcast(x, z, options);
  shot.look[0] = x;
  return shot;
};

export function buildLastDitch(world, data) {
  const rng = world.rng;
  const s = rng() < 0.5 ? -1 : 1; // la touche
  const T = 1.4;
  const heroNo = data.hero ?? 14;
  const hero = world.player("us", heroNo, { hero: true });
  const cover = world.player("us", heroNo === 13 ? 12 : 13);
  const wing = world.player("them", s > 0 ? 14 : 11);
  const support = world.player("them", 13);
  const ref = world.player("ref");

  const hAt = [s * 28.5, 12.2];
  const wAt = [s * 31, 11];
  const coverAt = [s * 24, 16];
  const supportAt = [s * 25, 25];
  const refAt = [s * 21.5, 29];
  const ball = new THREE.Vector3();
  // Le long de la touche d'en face, ou de celle qui passe sous la caméra (s < 0).
  const near = s > 0 ? 0 : -2.5;
  const lookX = s * 29.5 + near;
  const shot = aim(lookX, 9.5, { far: 0.95, fov: 33, y: -0.8 });
  const camera = keys([
    [0, [s * 26 - 34, 18, 44, s * 28, 0, 18, 42]],
    [T, [...shot.pos, ...shot.look, shot.fov]],
  ]);

  function setupFrame(t) {
    runner(hero, route([[s * 24, 25.2], hAt]), t, 0, T, { from: 1, to: 1, speed: 1 });
    runner(wing, route([[s * 31.2, 24], wAt]), t, 0, T, { from: 1, to: 1, speed: 1, carry: "one" });
    runner(cover, route([[s * 21.5, 29], coverAt]), t, 0, T, { from: 0.9, to: 1, speed: 0.95 });
    runner(support, route([[s * 24, 36], supportAt]), t, 0, T, { from: 0.8, to: 0.8, speed: 0.8 });
    runner(ref, route([[s * 20.5, 39], refAt]), t, 0, T, { from: 0.7, to: 0.7, speed: 0.6 });
    if (ref.card) ref.card.visible = false;
    world.ballAt(carried(wing, "one", ball), v(0, 0, -1));
    const [cx, cy, cz, lx, ly, lz, fov] = camera(t);
    return { pos: [cx, cy, cz], look: [lx, ly, lz], fov };
  }

  const setup = {
    duration: T,
    frame: setupFrame,
    cues: [{ at: 0.1, run: () => world.crowd("standing") }],
  };

  const ankleAt = [s * 31, 7.6];
  const pushAt = [s * 30.2, 4.4];
  const holdAt = [s * 30.2, 3.9];

  function preview(key) {
    const draw = world.draw;
    if (key === "ankle") return [draw.path([hAt, ankleAt]), draw.mark([wAt[0], 5.5], 0.7)];
    if (key === "push_touch") return [draw.path([hAt, pushAt]), draw.arrow([s * 31, 3.9], [s * (TOUCH + 0.6), 1.4], 1.6), draw.mark([s * TOUCH, 1.1], 0.8)];
    return [draw.path([hAt, holdAt]), draw.mark([wAt[0], -1.2], 1)];
  }

  // Le ballon aplati, tenu au sol par un joueur couché, ses bras devant lui.
  const under = (player, out = ball) => player.local(0, 0.3, 1.05, out);
  const grounded = (player, out = ball) => player.local(0, 0.14, 1.5, out);

  // Il plonge à l'essai depuis `from` (lancé), à `at`. Le ballon finit dans l'en-but.
  function tryDive(t, from, at, end = [from[0], from[1] - 2.4]) {
    const k = span(t, at, at + 0.45);
    wing.place(end[0], lerp(from[1], end[1], smooth(k)), FACE_LINE).set(t > at + 1.3 ? cheer(t * 1.5) : dive(k));
    const low = t > at + 1.3 ? null : grounded(wing, new THREE.Vector3());
    const rest = v(end[0], 0.14, end[1] - 1.5);
    const carriedAt = v(end[0] + 0.1, 1.05, from[1] - 0.3);
    world.ballAt(ball.lerpVectors(carriedAt, low ?? rest, smooth(span(t, at, at + 0.4))), v(1, 0, 0));
  }

  // La fin de l'essai : l'arbitre l'accorde au point de chute.
  const refTry = (t, at, x) => ref.place(x - s * 6.5, 2.8, (s * Math.PI) / 2).set(tryAward(smooth(span(t, at, at + 0.35))));

  // Le partenaire arrive de côté et l'emporte : plaquage in extremis (sans points).
  function coverHit(t, at, spot) {
    const meet = [spot[0] - s * 1.5, spot[1] + 0.1];
    runner(cover, route([coverAt, meet]), t, 0, at, { from: 0.9, to: 1, speed: 1 });
    if (t >= at) cover.place(meet[0], meet[1], (s * Math.PI) / 2).set(tackle(span(t, at, at + 0.45)));
    return span(t, at, at + 0.45);
  }

  function outcomeFor(key, result) {
    const { success: good, effect } = result;
    const scores = !good && effect === "try_conceded";
    const cues = [];
    let duration = 3;
    let frame;
    const supportRun = (t, end = [s * 28, 6.5]) => runner(support, route([supportAt, end]), t, 0, Math.min(duration, 2.8), { from: 0.8, to: 0.4, speed: 0.75 });
    const coverLate = (t, until) => {
      const late = [s * 27.2, 2.2];
      runner(cover, route([coverAt, late]), t, 0, until, { from: 0.9, to: 0.3, speed: 0.95 });
      if (t >= until) cover.set(t > until + 0.7 ? dejected() : ready(0.3));
    };

    if (key === "ankle") {
      // Le plongeon : ses mains arrivent sur la cheville de l'ailier.
      const hit = 0.62;
      const heel = [wAt[0], 5.5];
      duration = good ? 2.9 : scores ? 3.7 : 3.4;
      const lands = 1.25; // l'essai
      const hitAt = 1.55; // le partenaire
      cues.push({ at: hit, run: () => world.sound("impact") });
      if (good) cues.push({ at: hit + 0.35, run: () => reaction(world, true) });
      else if (scores) cues.push({ at: lands + 0.4, run: () => (world.sound("whistle", true), reaction(world, false)) });
      else cues.push({ at: hit + 0.1, run: () => world.sound("groan") }, { at: hitAt, run: () => world.sound("impact") }, { at: hitAt + 0.35, run: () => world.crowd("standing") });
      frame = (t) => {
        runner(hero, route([hAt, [wAt[0] - s * 0.2, 8.1]]), t, 0, 0.45, { from: 1, to: 1, speed: 1 });
        if (t >= 0.4) {
          const k = span(t, 0.4, 0.82);
          hero.place(lerp(wAt[0] - s * 0.2, ankleAt[0], smooth(k)), lerp(8.1, ankleAt[1], smooth(k)), FACE_LINE).set(k < 1 ? tackle(k) : ground());
        }
        runner(wing, route([wAt, heel]), t, 0, hit, { from: 1, to: 0.9, speed: 1, carry: "one" });
        if (t < hit) world.ballAt(carried(wing, "one", ball), v(0, 0, -1));
        if (good) {
          // Fauché : il s'écroule avant la ligne, sans lâcher le ballon.
          if (t >= hit) {
            const k = smooth(span(t, hit, hit + 0.5));
            wing.place(heel[0], lerp(heel[1], 3.4, k), FACE_LINE).set(mixPose(run(1.5, 1, "one"), ground(), k));
            world.ballAt(ball.lerpVectors(carried(wing, "one", new THREE.Vector3()), under(wing, new THREE.Vector3()), k), v(1, 0, 0));
          }
          const onIt = [wAt[0] - s * 1.4, 2.8];
          runner(cover, route([coverAt, onIt]), t, 0, 1.75, { from: 0.9, to: 0.4, speed: 0.9 });
          cover.root.rotation.y = cover.heading = (s * Math.PI) / 2;
          if (t >= 1.75) cover.set(crouch(0.8));
          supportRun(t);
        } else if (scores) {
          // Sa main glisse : l'ailier reprend ses appuis et plonge.
          const near = [heel[0], 0.9];
          if (t >= hit && t < lands) {
            runner(wing, route([heel, near]), t, hit, lands, { from: 0.7, to: 1, speed: 1, carry: "one" });
            world.ballAt(carried(wing, "one", ball), v(0, 0, -1));
          }
          if (t >= lands) tryDive(t, near, lands);
          coverLate(t, 1.7);
          if (t > lands + 0.4) refTry(t, lands + 0.4, near[0]);
          supportRun(t);
        } else {
          // Déséquilibré, il perd sa vitesse : le partenaire revient et le prend.
          const slow = [heel[0], 3];
          if (t >= hit) {
            runner(wing, route([heel, slow]), t, hit, hitAt, { from: 0.5, to: 0.25, speed: 0.6, carry: "one" });
            if (t < hitAt) wing.set({ ...wing.current, roll: -s * 0.18, lean: 0.75 });
          }
          const k = coverHit(t, hitAt, slow);
          if (t >= hitAt) wing.place(slow[0], slow[1], FACE_LINE + s * 0.35).set(mixPose(run(1.5, 1, "one"), ground(), smooth(k)));
          if (t >= hit && t < hitAt) world.ballAt(carried(wing, "one", ball), v(0, 0, -1));
          if (t >= hitAt) world.ballAt(ball.lerpVectors(carried(wing, "one", new THREE.Vector3()), under(wing, new THREE.Vector3()), smooth(k)), v(1, 0, 0));
          supportRun(t);
        }
        const follow = smooth(span(t, 0.3, 1.3));
        return aim(lerp(lookX, s * 30 + near, follow), lerp(9.5, 4.2, follow), { far: 0.92, fov: 33, y: lerp(-0.8, -0.9, follow) });
      };
    } else if (key === "push_touch") {
      // L'épaule dans le flanc : l'ailier part vers la touche.
      const hit = good ? 0.85 : 0.75;
      const wMeet = good ? [s * 31.3, 3.7] : [s * 31.2, 4.7];
      const hMeet = good ? [s * 30.3, 4.4] : [s * 30.2, 5.4];
      duration = good ? 3 : scores ? 3.8 : 3.4;
      const lands = 1.4;
      const hitAt = 1.55;
      cues.push({ at: hit, run: () => world.sound("impact") });
      if (good) cues.push({ at: hit + 0.35, run: () => world.sound("whistle") }, { at: hit + 0.45, run: () => reaction(world, true) });
      else if (scores) cues.push({ at: lands + 0.4, run: () => (world.sound("whistle", true), reaction(world, false)) });
      else cues.push({ at: hit + 0.2, run: () => world.sound("groan") }, { at: hitAt, run: () => world.sound("impact") }, { at: hitAt + 0.35, run: () => world.crowd("standing") });
      frame = (t) => {
        runner(hero, route([hAt, hMeet]), t, 0, hit, { from: 1, to: 1, speed: 1 });
        runner(wing, route([wAt, wMeet]), t, 0, hit, { from: 1, to: 1, speed: 1, carry: "one" });
        if (t < hit) world.ballAt(carried(wing, "one", ball), v(0, 0, -1));
        if (good) {
          // Il l'envoie dehors à un mètre de la ligne, et reste, lui, dans le terrain.
          const k = smooth(span(t, hit, hit + 0.5));
          const out = [s * (TOUCH + 1), 1.1];
          if (t >= hit) {
            wing.place(lerp(wMeet[0], out[0], k), lerp(wMeet[1], out[1], k), s * lerp(Math.PI, Math.PI / 2, k)).set(mixPose(run(1.5, 1, "one"), ground(), k));
            hero.place(lerp(hMeet[0], s * 33.4, k), lerp(hMeet[1], 3.4, k), s * lerp(Math.PI, Math.PI * 0.7, k)).set(t > hit + 0.9 ? cheer(t * 1.5) : mixPose(run(1.5, 1), ready(0.4), k));
            world.ballAt(ball.lerpVectors(carried(wing, "one", new THREE.Vector3()), under(wing, new THREE.Vector3()), k), v(1, 0, 0));
          }
          runner(cover, route([coverAt, [s * 29.5, 6]]), t, 0, 2, { from: 0.9, to: 0.1, speed: 0.8 });
          if (t >= 2) cover.set(ready(0.15));
          supportRun(t, [s * 28, 11]);
          const refTo = [s * 26.2, 4];
          runner(ref, route([refAt, refTo]), t, 0, hit + 0.8, { from: 0.7, to: 0.1, speed: 0.7 });
          ref.root.rotation.y = ref.heading = (s * Math.PI) / 2;
          if (t >= hit + 0.8) ref.set(signal(s > 0 ? 1 : -1, smooth(span(t, hit + 0.8, hit + 1.1))));
          return aim(lerp(lookX, s * 32 + near, smooth(span(t, 0.2, 1.2))), lerp(9.5, 3.8, smooth(span(t, 0.2, 1.2))), { far: 0.92, fov: 33, y: lerp(-0.8, -0.9, smooth(span(t, 0.2, 1.2))) });
        }
        // Il résiste : le joueur rebondit au sol, l'ailier chancelle et reste dedans.
        if (t >= hit) {
          const k = span(t, hit, hit + 0.45);
          hero.place(lerp(hMeet[0], hMeet[0] - s * 0.3, k), hMeet[1], s * (Math.PI - 0.5)).set(k < 1 ? tackle(k * 0.8) : ground());
        }
        const staggered = [s * 33.2, 3.1];
        if (scores) {
          const near = [s * 33.1, 0.9];
          if (t >= hit && t < lands) {
            runner(wing, route([wMeet, near]), t, hit, lands, { from: 0.7, to: 1, speed: 1, carry: "one" });
            world.ballAt(carried(wing, "one", ball), v(0, 0, -1));
          }
          if (t >= lands) tryDive(t, near, lands);
          coverLate(t, 1.7);
          if (t > lands + 0.4) refTry(t, lands + 0.4, near[0]);
        } else {
          if (t >= hit && t < hitAt) {
            runner(wing, route([wMeet, staggered]), t, hit, hitAt, { from: 0.5, to: 0.35, speed: 0.6, carry: "one" });
            wing.set({ ...wing.current, roll: s * 0.16 });
            world.ballAt(carried(wing, "one", ball), v(0, 0, -1));
          }
          const k = coverHit(t, hitAt, staggered);
          if (t >= hitAt) {
            wing.place(staggered[0], staggered[1], FACE_LINE + s * 0.35).set(mixPose(run(1.5, 1, "one"), ground(), smooth(k)));
            world.ballAt(ball.lerpVectors(carried(wing, "one", new THREE.Vector3()), under(wing, new THREE.Vector3()), smooth(k)), v(1, 0, 0));
          }
        }
        supportRun(t);
        const follow = smooth(span(t, 0.3, 1.3));
        return aim(lerp(lookX, s * 31 + near, follow), lerp(9.5, 3.4, follow), { far: 0.92, fov: 33, y: lerp(-0.8, -0.9, follow) });
      };
    } else if (good) {
      // Ceinturé : ils franchissent la ligne ensemble, le ballon ne touche jamais le sol.
      const hit = 0.85;
      const over = 1.55;
      const wMeet = [s * 31, 3.4];
      const wEnd = [s * 31, -1.2];
      const hEnd = [s * 30.3, -0.65];
      const sink = (t) => smooth(span(t, over, over + 0.6));
      const whistleAt = over + 0.55;
      duration = 3.8;
      const refTo = [s * 25.5, -1.2];
      cues.push({ at: hit, run: () => world.sound("impact") }, { at: whistleAt, run: () => world.sound("whistle") }, { at: whistleAt + 0.1, run: () => reaction(world, true) });
      frame = (t) => {
        runner(hero, route([hAt, holdAt]), t, 0, hit, { from: 1, to: 1, speed: 1 });
        runner(wing, route([wAt, wMeet]), t, 0, hit, { from: 1, to: 1, speed: 1, carry: "one" });
        if (t < hit) world.ballAt(carried(wing, "one", ball), v(0, 0, -1));
        if (t >= hit) {
          const k = smooth(span(t, hit, over));
          const d = sink(t);
          const wobble = Math.sin((t - hit) * 16) * 0.08 * (1 - d);
          wing.place(wMeet[0], lerp(wMeet[1], wEnd[1], k), FACE_LINE + wobble).set(mixPose(WRESTLE, crouch(0.72), d));
          hero.place(lerp(holdAt[0], hEnd[0], k), lerp(holdAt[1], hEnd[1], k), s * (Math.PI - 0.9) - wobble).set(mixPose(WRESTLE, t > whistleAt + 0.95 ? cheer(t * 1.4) : crouch(0.5), t > whistleAt + 0.95 ? 1 : d));
          // Tenu haut, sur ses bras : au plus bas à 70 cm du sol.
          world.ballAt(wing.local(-0.05, lerp(1.15, 0.72, d), 0.32, ball), v(1, 0, 0));
        }
        runner(cover, route([coverAt, [s * 28.3, 0.4]]), t, 0, 2.2, { from: 0.9, to: 0.1, speed: 0.8 });
        if (t >= 2.2) cover.set(t > whistleAt + 0.9 ? cheer(t * 1.3) : ready(0.3));
        supportRun(t, [s * 28.5, 5.5]);
        runner(ref, route([refAt, refTo]), t, 0, whistleAt, { from: 0.7, to: 0.2, speed: 0.8 });
        ref.root.rotation.y = ref.heading = (s * Math.PI) / 2;
        if (t >= whistleAt) ref.set(signal(s > 0 ? 1 : -1, smooth(span(t, whistleAt, whistleAt + 0.3))));
        const follow = smooth(span(t, 0.3, 1.5));
        return aim(lerp(lookX, s * 30 + near, follow), lerp(9.5, 1, follow), { far: 0.92, fov: 33, y: lerp(-0.8, -0.9, follow) });
      };
    } else {
      // Il s'arrache de la prise et plonge : à l'essai, ou le partenaire le percute en l'air.
      const hit = 0.75;
      const tear = 1.25;
      const wMeet = [s * 31, 4.7];
      const wTorn = [s * 31, 3.6];
      const hMeet = [s * 30.2, 5.1];
      const whistleAt = 2.2;
      duration = scores ? 3.8 : 3.7;
      cues.push({ at: hit, run: () => world.sound("impact") }, { at: tear, run: () => world.sound("groan") });
      if (scores) cues.push({ at: tear + 0.45, run: () => (world.sound("whistle", true), reaction(world, false)) });
      else cues.push({ at: 1.55, run: () => world.sound("impact") }, { at: whistleAt, run: () => world.sound("whistle") }, { at: whistleAt + 0.1, run: () => world.crowd("standing") });
      frame = (t) => {
        runner(hero, route([hAt, hMeet]), t, 0, hit, { from: 1, to: 1, speed: 1 });
        runner(wing, route([wAt, wMeet]), t, 0, hit, { from: 1, to: 1, speed: 1, carry: "one" });
        if (t < hit) world.ballAt(carried(wing, "one", ball), v(0, 0, -1));
        if (t >= hit) {
          const k = span(t, hit, tear);
          const fall = span(t, tear, tear + 0.55);
          if (t < tear) hero.place(hMeet[0], lerp(hMeet[1], 4, k), s * (Math.PI - 0.9)).set(WRESTLE);
          else hero.place(hMeet[0], 4, s * (Math.PI - 0.7)).set(fall < 1 ? tackle(fall) : ground());
        }
        if (t >= hit && t < tear) {
          const k = span(t, hit, tear);
          wing.place(wMeet[0], lerp(wMeet[1], wTorn[1], k), FACE_LINE + Math.sin((t - hit) * 16) * 0.1).set(WRESTLE);
          world.ballAt(carried(wing, "one", ball), v(0, 0, -1));
        }
        if (scores) {
          if (t >= tear) tryDive(t, wTorn, tear, [wTorn[0], 0.4]);
          coverLate(t, 1.9);
          if (t > tear + 0.45) refTry(t, tear + 0.45, wTorn[0]);
        } else {
          // Percuté en plein vol, il lâche le ballon, qui file dans l'en-but : pas d'essai.
          const bump = 1.55;
          const short = [wTorn[0], 1.5];
          if (t >= tear) {
            const k = span(t, tear, tear + 0.55);
            wing.place(short[0], lerp(wTorn[1], short[1], smooth(k)), FACE_LINE).set(k < 1 ? dive(k) : ground());
          }
          const hands = v(short[0] + 0.05, 0.75, 0.4);
          const out = v(short[0] + s * 0.7, 0.14, -3.2);
          if (t >= tear && t < bump) world.ballAt(ball.lerpVectors(carried(wing, "two", new THREE.Vector3()), hands, span(t, tear, bump)), v(1, 0, 0));
          else if (t >= bump && t < 2.1) world.ballAt(lob(hands, out, 0.7, span(t, bump, 2.1), ball), v(1, 0, Math.sin(t * 9)));
          else if (t >= 2.1) world.ballAt(ball.copy(out), v(1, 0, 0.3));
          coverHit(t, bump, short);
          const refTo = [s * 25.4, 1.6];
          runner(ref, route([refAt, refTo]), t, 0, whistleAt, { from: 0.7, to: 0.2, speed: 0.8 });
          ref.root.rotation.y = ref.heading = (s * Math.PI) / 2;
          if (t >= whistleAt) ref.set(signal(s > 0 ? 1 : -1, smooth(span(t, whistleAt, whistleAt + 0.3))));
        }
        supportRun(t);
        const follow = smooth(span(t, 0.3, 1.4));
        return aim(lerp(lookX, s * 30.3 + near, follow), lerp(9.5, 1.8, follow), { far: 0.92, fov: 33, y: lerp(-0.8, -0.9, follow) });
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

  return { setup, preview, outcome: outcomeFor };
}
