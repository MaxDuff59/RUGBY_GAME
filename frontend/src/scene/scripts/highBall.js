import * as THREE from "three";

import { crouch, dejected, ground, jump, mixPose, pose, ready, run, signal, tackle } from "../rig.js";
import { FACE_FIELD, FACE_LINE, broadcast, carried, grubber, headingTo, keys, lerp, lob, reaction, route, runner, smooth, span } from "./common.js";

// Carrière de joueur, « Chandelle adverse » (high_ball) : la chandelle redescend sur le
// joueur incarné dans ses 22 (il défend la ligne z = 0), leurs chasseurs arrivent lancés.
// La prendre de volée (il saute plus haut que leur 13, ou le ballon lui échappe au contact
// et ils ramassent), la laisser rebondir (il part dans le dos des chasseurs, ou le rebond
// le trahit et l'un d'eux ramasse), ou l'arrêt de volée (« Marque ! », ou il relâche le
// ballon sous la charge : en-avant sifflé).

// En attente sous le ballon : la tête levée, les bras qui montent.
const WAIT = pose({ ...ready(0.45), armL: 1.3, armR: 1.3, elL: 0.8, elR: 0.8, abL: -0.1, abR: -0.1, nod: -0.55 });
// Les bras levés pour cueillir le ballon, les pieds au sol.
const CATCH = pose({ y: -0.05, armL: 2.35, armR: 2.35, abL: -0.14, abR: -0.14, elL: 0.35, elR: 0.35, legL: 0.3, knL: 0.5, legR: -0.1, knR: 0.3, nod: -0.5 });
// Le ballon serré à deux mains.
const HOLD = pose({ ...ready(0.3), armL: 0.75, armR: 0.75, elL: 1.1, elR: 1.1, abL: -0.15, abR: -0.15 });

const v = (x, y, z) => new THREE.Vector3(x, y, z);
// Le plan de retransmission, le point visé juste sur l'action (`y` bas : l'action haute).
const aim = (x, z, options) => {
  const shot = broadcast(x, z, options);
  shot.look[0] = x;
  return shot;
};

export function buildHighBall(world, data) {
  const rng = world.rng;
  const s = rng() < 0.5 ? -1 : 1;
  const hx = s * (5 + rng() * 7);
  const hz = 13;
  const T = 1.6;
  const heroNo = data.hero ?? 15;
  const hero = world.player("us", heroNo, { hero: true });
  const mate = world.player("us", heroNo === 14 ? 15 : 14);
  const lead = world.player("them", 13);
  const right = world.player("them", 11);
  const left = world.player("them", 7);
  const ref = world.player("ref");

  const H = [hx, hz];
  const leadAt = [hx + 0.8, hz + 6];
  const rightAt = [hx + 6, hz + 8.5];
  const leftAt = [hx - 2, hz + 9];
  const mateAt = [hx + 7, hz - 4];
  const refAt = [hx + 11, hz + 3];
  const refFace = -Math.PI / 2;

  // La chandelle : à 5,4 m au-dessus de lui au moment du choix, sur le fond de la pelouse
  // où elle se lit (plus haut, elle se perd dans la tribune). Son ombre dit où elle tombe.
  const kickFrom = v(hx * 0.5, 1, hz + 26);
  const F = v(hx + 0.1, 5.4, hz + 1.6);
  const ball = new THREE.Vector3();
  const shot = aim(hx + 0.5, hz + 0.8, { fov: 34, y: 2.4 });
  const camera = keys([
    [0, [hx - 38, 24, hz + 42, hx * 0.7, 6, hz + 12, 46]],
    [T, [...shot.pos, ...shot.look, shot.fov]],
  ]);
  const axis = (a) => v(Math.sin(a), 1, 0);
  const shade = world.add(new THREE.Mesh(new THREE.CircleGeometry(0.3, 12).rotateX(-Math.PI / 2), new THREE.MeshBasicMaterial({ color: 0x0b120d, transparent: true, opacity: 0.45, depthWrite: false })));
  const shadeBall = () => {
    const { x, y, z } = world.ball.position;
    shade.position.set(x, 0.016, z);
    shade.visible = y > 1.4; // tant qu'il vole : porté, le joueur a déjà son ombre
  };

  function setupFrame(t) {
    runner(hero, route([[hx - 1, hz - 6], H]), t, 0, T, { from: 0.8, to: 0.04, speed: 0.5 });
    hero.root.rotation.y = hero.heading = FACE_FIELD;
    hero.set(mixPose(run(t * 2, 0.5), WAIT, smooth(span(t, 0.9, 1.35))));
    runner(mate, route([[mateAt[0] + 1, mateAt[1] - 3], mateAt]), t, 0, T, { from: 0.6, to: 0.3, speed: 0.4 });
    for (const [player, at] of [[lead, leadAt], [right, rightAt], [left, leftAt]]) {
      runner(player, route([[at[0], at[1] + 12], at]), t, 0, T, { from: 0.9, to: 1, speed: 1 });
    }
    ref.place(refAt[0], refAt[1], refFace).set(ready(0.1));
    if (ref.card) ref.card.visible = false;
    world.ballAt(lob(kickFrom, F, 14, (t + 2) / (T + 2), ball), axis(t * 6));
    shadeBall();
    const [cx, cy, cz, lx, ly, lz, fov] = camera(t);
    return { pos: [cx, cy, cz], look: [lx, ly, lz], fov };
  }

  const setup = {
    duration: T,
    frame: setupFrame,
    cues: [
      { at: 0.1, run: () => world.crowd(world.pressure > 1 ? "standing" : "seated") },
    ],
  };

  // Les tracés : le ballon jusqu'aux mains du joueur, ou jusqu'au sol et son rebond.
  const land = [hx + 1, hz + 2.6]; // où il rebondit, s'il le laisse faire
  const takeAt = [hx + 2.6, hz + 0.4];
  const breakLine = [takeAt, [hx + 6.5, hz + 4.5], [hx + 8.5, hz + 15]];
  const chord = (a, b, height, steps = 8) => {
    const out = [];
    for (let i = 0; i <= steps; i++) out.push(lob(a, b, height, i / steps).toArray());
    return out;
  };

  function preview(key) {
    const draw = world.draw;
    if (key === "full") return [draw.arc(chord(F, v(hx, 2.8, hz + 0.9), 0), 0.08), draw.path([H, [hx, hz + 0.9]]), draw.mark([hx, hz + 0.9], 0.8)];
    if (key === "bounce") {
      const floor = v(land[0], 0.15, land[1]);
      return [draw.arc([...chord(F, floor, 0, 5), ...chord(floor, v(takeAt[0], 1.1, takeAt[1]), 1.5, 6).slice(1)], 0.08), draw.path([H, takeAt, ...breakLine.slice(1)]), draw.mark(land, 0.6)];
    }
    return [draw.arc(chord(F, v(hx, 2, hz + 0.35), 0), 0.08), draw.mark(H, 1.15)];
  }

  // Le ballon descend : il accélère un peu sur la fin.
  const CATCH_AT = 0.55;
  const fall = (t, target) => {
    const u = span(t, 0, CATCH_AT);
    world.ballAt(ball.lerpVectors(F, target, u * (0.7 + 0.3 * u)), axis(T * 6 + t * 6));
  };

  function outcomeFor(key, result) {
    const good = result.success;
    const cues = [];
    let duration = 3;
    let frame;

    if (key === "full") {
      // De volée : il s'élève, leur 13 aussi ; le plus haut garde le ballon.
      const spot = [hx, hz + 0.9];
      const rival = [hx + 0.35, hz + 2];
      const pick = [hx + 1.8, hz + 5.2];
      const air = (u, top) => Math.sin(span(u, 0.2, 1) * Math.PI) * top;
      const heroTop = good ? 0.95 : 0.5;
      const rivalTop = good ? 0.5 : 0.85;
      duration = 3;
      cues.push({ at: CATCH_AT, run: () => world.sound("impact") }, { at: CATCH_AT + 0.35, run: () => reaction(world, good) });
      frame = (t) => {
        runner(hero, route([H, spot]), t, 0, 0.25, { from: 0.3, to: 0.6, speed: 0.5 });
        if (t >= 0.2) hero.place(spot[0], spot[1], FACE_FIELD).set({ ...jump(1), lift: air(t, heroTop), nod: -0.5 });
        runner(lead, route([leadAt, rival]), t, 0, 0.3, { from: 1, to: 0.8, speed: 1 });
        if (t >= 0.25) {
          const flat = { ...jump(1), lift: air(t, rivalTop), nod: -0.5 };
          const k = smooth(span(t, 0.8, 1.2));
          lead.place(rival[0] + 0.3 * k, rival[1] + 0.9 * k, FACE_LINE).set(good ? mixPose(flat, ground(true), k) : flat);
        }
        if (t < CATCH_AT) fall(t, hero.local(0, 2.15, 0.1, new THREE.Vector3()));
        if (good) {
          // Il retombe, le ballon serré, et repart avec son partenaire.
          if (t >= 1 && t < 1.35) hero.set(mixPose({ ...jump(1), lift: 0 }, HOLD, smooth(span(t, 1, 1.25))));
          if (t >= 1.35) runner(hero, route([spot, [hx - 1.6, hz + 3.5], [hx - 1.6, hz + 7]]), t, 1.35, duration, { from: 0.3, to: 0.7, speed: 0.6, carry: "two" });
          if (t >= CATCH_AT) {
            const high = hero.local(0, 2.15, 0.1, new THREE.Vector3());
            const low = carried(hero, "two", new THREE.Vector3());
            world.ballAt(ball.lerpVectors(high, low, smooth(span(t, 0.85, 1.25))), v(1, 0, 0));
          }
          runner(mate, route([mateAt, [hx + 3.4, hz + 0.6]]), t, 0, 2, { from: 0.4, to: 0.3, speed: 0.6 });
          runner(right, route([rightAt, [hx + 3.6, hz + 4.8]]), t, 0, 0.9, { from: 1, to: 0.04, speed: 0.8 });
          runner(left, route([leftAt, [hx - 4.5, hz + 5.8]]), t, 0, 0.9, { from: 1, to: 0.04, speed: 0.8 });
          if (t >= 0.9) [right, left].forEach((player) => player.set(t > 1.8 ? dejected() : ready(0.3)));
          ref.place(refAt[0], refAt[1], refFace);
          return aim(lerp(hx + 0.5, hero.root.position.x, 0.8), lerp(hz + 2.5, hero.root.position.z, 0.5), { fov: 33, y: lerp(2.2, -0.9, smooth(span(t, 0.6, 1.3))) });
        }
        // Le ballon lui échappe : il part vers l'avant, leur 11 ramasse et file.
        if (t >= 1) {
          const k = smooth(span(t, 1, 1.4));
          hero.place(spot[0], spot[1] - 0.3 * k, FACE_FIELD).set(mixPose({ ...jump(1), lift: 0 }, ground(true), k));
        }
        const touched = v(spot[0], 2.15 + air(CATCH_AT, heroTop), spot[1] + 0.1);
        const floor = v(pick[0], 0.13, pick[1]);
        if (t >= 1.05) runner(lead, route([rival, [hx + 1.4, hz + 1.6], [hx + 1.6, hz - 2]]), t, 1.05, duration, { from: 0.2, to: 0.5, speed: 0.6 });
        runner(right, route([rightAt, [pick[0] + 0.2, pick[1] + 0.55]]), t, 0, 1.15, { from: 0.9, to: 0.5, speed: 0.8 });
        if (t >= 1.05 && t < 1.3) right.set(crouch(smooth(span(t, 1.05, 1.15))));
        if (t >= 1.3) runner(right, route([[pick[0] + 0.2, pick[1] + 0.55], [hx + 3.4, hz - 2.5]]), t, 1.3, duration, { from: 0.4, to: 0.9, speed: 0.9, carry: "one" });
        if (t >= CATCH_AT && t < 1.15) world.ballAt(lob(touched, floor, 1.3, span(t, CATCH_AT, 1.15), ball), axis(t * 9));
        else if (t >= 1.15) world.ballAt(ball.lerpVectors(floor, carried(right, "one", new THREE.Vector3()), smooth(span(t, 1.15, 1.42))), v(0, 0, -1));
        runner(mate, route([mateAt, [hx + 4.2, hz - 6.5]]), t, 0, 1.8, { from: 0.4, to: 0.3, speed: 0.6 });
        if (t >= 1.8) mate.place(hx + 4.2, hz - 6.5, FACE_FIELD).set(ready(0.8));
        runner(left, route([leftAt, [hx - 3.8, hz + 3]]), t, 0, 2.2, { from: 1, to: 0.3, speed: 0.7 });
        const follow = smooth(span(t, 1.1, 2.1));
        return aim(lerp(hx + 0.8, right.root.position.x, follow), lerp(hz + 2.5, right.root.position.z + 1, follow), { fov: 33, y: lerp(2.2, -0.9, smooth(span(t, 0.6, 1.3))) });
      };
    } else if (key === "bounce") {
      // Laisser rebondir : le ballon touche le sol devant lui.
      if (good) {
        const floor = v(land[0], 0.15, land[1]);
        duration = 2.9;
        cues.push({ at: CATCH_AT, run: () => world.sound("kick") }, { at: 1.25, run: () => reaction(world, true) });
        frame = (t) => {
          if (t < CATCH_AT) fall(t, floor);
          // Il s'écarte du point de chute, cueille le rebond, et part en contournant.
          if (t < 1.05) {
            runner(hero, route([H, takeAt]), t, 0, 1.05, { from: 0.4, to: 0.8, speed: 0.6 });
            hero.root.rotation.y = hero.heading = lerp(hero.heading, headingTo(takeAt[0], takeAt[1], land[0], land[1]), 0.65);
          } else runner(hero, route(breakLine), t, 1.05, duration, { from: 0.7, to: 1, speed: 1, carry: "one" });
          if (t >= CATCH_AT && t < 1.05) world.ballAt(lob(floor, carried(hero, "two", new THREE.Vector3()), 1.5, span(t, CATCH_AT, 1.05), ball), axis(t * 8));
          if (t >= 1.05) world.ballAt(carried(hero, "one", ball), v(0, 0, 1));
          // Les chasseurs filent sur le point de chute : le premier plonge dans le vide.
          runner(lead, route([leadAt, [hx + 0.2, hz + 3.1]]), t, 0, 0.48, { from: 1, to: 1, speed: 1 });
          if (t >= 0.42) {
            const k = span(t, 0.42, 1);
            lead.place(hx + 0.2, hz + 3.1 - 0.5 * smooth(k), FACE_LINE).set(k < 1 ? tackle(k) : ground());
          }
          runner(right, route([rightAt, [hx + 2.4, hz + 3.6]]), t, 0, 1, { from: 1, to: 0.04, speed: 0.9 });
          runner(left, route([leftAt, [hx - 2, hz + 4]]), t, 0, 1, { from: 1, to: 0.04, speed: 0.9 });
          if (t >= 1) {
            const { x, z } = hero.root.position;
            right.place(hx + 2.4, hz + 3.6, headingTo(hx + 2.4, hz + 3.6, x, z)).set(ready(0.5));
            left.place(hx - 2, hz + 4, headingTo(hx - 2, hz + 4, x, z)).set(t > 1.9 ? dejected() : ready(0.3));
          }
          runner(mate, route([mateAt, [hx + 5.5, hz + 5]]), t, 0.5, duration, { from: 0.4, to: 0.9, speed: 0.8 });
          const follow = smooth(span(t, 0.9, 2.1));
          return aim(lerp(hx + 1, hero.root.position.x, follow), lerp(hz + 2.5, hero.root.position.z, follow), { fov: 33, y: lerp(2.2, -0.9, smooth(span(t, 0.6, 1.3))) });
        };
      } else {
        // Le rebond part de l'autre côté : leur 7 le cueille à pleine course.
        const floor = v(hx + 0.4, 0.15, hz + 3);
        const away = v(hx - 2.4, 0.95, hz + 5.5);
        const wrong = [hx + 1.8, hz + 0.6];
        const lunge = [hx + 0.5, hz + 2.1];
        const taken = [hx - 2.6, hz + 6.05];
        duration = 3;
        cues.push({ at: CATCH_AT, run: () => world.sound("kick") }, { at: 1.15, run: () => reaction(world, false) });
        frame = (t) => {
          if (t < CATCH_AT) fall(t, floor);
          else if (t < 1.1) world.ballAt(lob(floor, away, 1.2, span(t, CATCH_AT, 1.1), ball), axis(t * 8));
          runner(hero, route([H, wrong]), t, 0, 0.7, { from: 0.4, to: 0.6, speed: 0.5 });
          if (t >= 0.7) {
            // Il revient, plonge, trop court.
            const k = span(t, 0.7, 1.2);
            hero.place(lerp(wrong[0], lunge[0], smooth(k)), lerp(wrong[1], lunge[1], smooth(k)), headingTo(wrong[0], wrong[1], away.x, away.z)).set(k < 1 ? tackle(k) : ground());
          }
          runner(left, route([leftAt, taken]), t, 0, 1.1, { from: 0.9, to: 0.7, speed: 0.85 });
          if (t >= 1.1) runner(left, route([taken, [hx - 1.7, hz - 2.6]]), t, 1.1, duration, { from: 0.6, to: 1, speed: 1, carry: "one" });
          if (t >= 1.1) world.ballAt(carried(left, "one", ball), v(0, 0, -1));
          runner(lead, route([leadAt, [hx + 1.3, hz + 4]]), t, 0, 0.7, { from: 1, to: 0.04, speed: 0.8 });
          if (t >= 0.7) lead.set(ready(0.4));
          runner(right, route([rightAt, [hx + 3.5, hz + 3.5]]), t, 0, 1.6, { from: 1, to: 0.3, speed: 0.7 });
          runner(mate, route([mateAt, [hx - 0.8, hz - 6.2]]), t, 0.3, 2.4, { from: 0.4, to: 0.3, speed: 0.8 });
          if (t >= 2.4) mate.place(hx - 0.8, hz - 6.2, FACE_FIELD).set(ready(0.8));
          const follow = smooth(span(t, 1.1, 2.2));
          return aim(lerp(hx + 0.5, left.root.position.x, follow), lerp(hz + 3, left.root.position.z + 1, follow), { fov: 33, y: lerp(2.2, -0.9, smooth(span(t, 0.6, 1.3))) });
        };
      }
    } else {
      // Arrêt de volée : il attend, les pieds plantés.
      const pick = [hx - 0.4, hz + 4.2];
      duration = good ? 2.9 : 3.2;
      const refNear = [hx + 5.6, hz + 3];
      const SHAKE_AT = 0.68;
      if (good) {
        cues.push(
          { at: CATCH_AT + 0.1, run: () => world.sound("whistle") },
          { at: CATCH_AT + 0.3, run: () => reaction(world, true) },
        );
      } else {
        cues.push(
          { at: SHAKE_AT, run: () => world.sound("impact") },
          { at: 1.35, run: () => world.sound("whistle") },
          { at: 1.45, run: () => reaction(world, false) },
        );
      }
      frame = (t) => {
        const high = hero.local(0, 2, 0.35, new THREE.Vector3());
        const low = v(hx, 1.1, hz + 0.4);
        const signalAt = good ? 0.95 : 1.45;
        runner(ref, route([refAt, refNear]), t, 0, signalAt, { from: 0.5, to: 0.1, speed: 0.5 });
        ref.root.rotation.y = ref.heading = refFace;
        if (t >= signalAt) ref.set(signal(1, smooth(span(t, signalAt, signalAt + 0.3))));
        if (good) {
          // « Marque ! » : les chasseurs s'arrêtent net devant lui.
          hero.place(H[0], H[1], FACE_FIELD).set(mixPose(CATCH, HOLD, smooth(span(t, 1, 1.4))));
          if (t < CATCH_AT) fall(t, high);
          else world.ballAt(ball.lerpVectors(high, low, smooth(span(t, 1, 1.4))), v(1, 0, 0));
          runner(lead, route([leadAt, [hx + 0.7, hz + 2.3]]), t, 0, 0.85, { from: 1, to: 0.04, speed: 0.8 });
          runner(right, route([rightAt, [hx + 4.4, hz + 4.8]]), t, 0, 1, { from: 1, to: 0.04, speed: 0.8 });
          runner(left, route([leftAt, [hx - 3, hz + 5.2]]), t, 0, 1, { from: 1, to: 0.04, speed: 0.8 });
          if (t >= 0.85) lead.set(t > 1.7 ? dejected() : ready(0.4));
          if (t >= 1) [right, left].forEach((player) => player.set(t > 1.9 ? dejected() : ready(0.3)));
          runner(mate, route([mateAt, [hx + 3.1, hz - 1.3]]), t, 0, 1.6, { from: 0.4, to: 0.1, speed: 0.5 });
          if (t >= 1.6) mate.set(ready(0.15));
        } else {
          // Il l'a dans les mains, leur 13 arrive dessus : le ballon tombe en avant.
          const k = smooth(span(t, SHAKE_AT, 1.1));
          hero.place(H[0], H[1] - 0.5 * k, FACE_FIELD).set(mixPose(CATCH, ground(true), k));
          runner(lead, route([leadAt, [hx + 0.25, hz + 1]]), t, 0, SHAKE_AT, { from: 1, to: 1, speed: 1 });
          if (t >= SHAKE_AT) lead.place(hx + 0.25, hz + 1 - 0.5 * k, FACE_LINE).set(mixPose(run(1.3, 1), t > 2.2 ? ready(0.2) : ready(0.7), k));
          // Leur 7 ramasse le ballon : la mêlée sera pour eux.
          const near = [pick[0], pick[1] + 0.55];
          runner(left, route([leftAt, near]), t, 0, 1.95, { from: 0.9, to: 0.06, speed: 0.7 });
          if (t >= 1.75) left.set(t < 2.2 ? crouch(smooth(span(t, 1.75, 2))) : HOLD);
          const hands = v(hx, 2, hz + 0.35);
          const first = v(hx + 0.4, 0.13, hz + 2.7);
          const last = v(pick[0], 0.13, pick[1]);
          if (t < CATCH_AT) fall(t, hands);
          else if (t < SHAKE_AT) world.ballAt(ball.copy(hands), v(1, 0, 0));
          else if (t < 1.1) world.ballAt(lob(hands, first, 0.7, span(t, SHAKE_AT, 1.1), ball), axis(t * 9));
          else if (t < 1.95) world.ballAt(grubber(first, last, span(t, 1.1, 1.95), 3, ball), axis(t * 7));
          else world.ballAt(ball.lerpVectors(carried(left, "low", new THREE.Vector3()), carried(left, "two", new THREE.Vector3()), smooth(span(t, 2.05, 2.25))), v(1, 0, 0));
          runner(right, route([rightAt, [hx + 3.6, hz + 4.2]]), t, 0, 1.2, { from: 1, to: 0.04, speed: 0.8 });
          if (t >= 1.2) right.set(ready(0.2));
          runner(mate, route([mateAt, [hx + 2.6, hz - 2.2]]), t, 0.3, 2, { from: 0.4, to: 0.05, speed: 0.6 });
          if (t >= 2) mate.set(dejected());
        }
        return aim(hx + 0.8, hz + 2.2, { fov: 32, y: lerp(2.2, -0.9, smooth(span(t, 0.6, 1.3))) });
      };
    }
    return {
      duration,
      cues,
      frame(t) {
        setupFrame(T);
        const view = frame(t);
        shadeBall();
        return view;
      },
    };
  }

  return {
    setup,
    // La chandelle reste suspendue le temps du choix : elle tourne encore sur elle-même.
    hold(time) {
      world.ballAt(F, axis(T * 6 + time * 0.8));
    },
    preview,
    outcome: outcomeFor,
  };
}
