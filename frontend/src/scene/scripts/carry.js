import * as THREE from "three";

import { bind, crouch, dejected, ground, mixPose, pass, pose, ready, run, signal, tackle } from "../rig.js";
import { FACE_FIELD, FACE_LINE, broadcast, carried, keys, lerp, lob, reaction, route, runner, smooth, span } from "./common.js";

// Carrière de joueur, « Charge au près » (carry) : le ballon sort pour le joueur incarné
// au ras du ruck, deux défenseurs montent. Nous attaquons vers z = 0. Tête baissée (il
// les fait reculer ; ou stoppé net), la passe après contact (la défense s'ouvre : il
// reprend le ballon en course, le deux contre un s'enchaîne ; ou le ballon tombe), la
// passe courte à l'ouvreur (le jeu continue ; ou en-avant).

// Dans le contact, debout : les jambes poussent, le ballon serré.
const DRIVE = (phase) => {
  const k = Math.sin(phase * Math.PI * 2);
  return pose({ y: -0.26, lean: 0.95, legL: 0.75 + k * 0.45, legR: 0.45 - k * 0.45, knL: 0.9 - k * 0.3, knR: 0.8 + k * 0.3, armL: 0.9, armR: 0.5, abL: 0.2, abR: 0.1, elL: 1.5, elR: 1.9, nod: -0.4 });
};
const GRIP = pose({ y: -0.18, lean: 0.75, armL: 1.45, armR: 1.5, abL: -0.2, abR: -0.2, elL: 0.75, elR: 0.75, legL: 0.5, legR: -0.25, knL: 0.8, knR: 0.5, nod: -0.25 });

export function buildCarry(world, data) {
  const rng = world.rng;
  const rx = 4 + rng() * 7; // le ruck vers la tribune, l'attaque côté caméra
  const rz = 26;
  const heroNo = data.hero ?? 8;
  const hero = world.player("us", heroNo, { hero: true });
  const numbers = [1, 2, 3, 4, 5, 6, 7, 8].filter((n) => n !== heroNo);
  const [supportNo, tackledNo, cleanA, cleanB] = [numbers[5], numbers[2], numbers[0], numbers[1]];
  const support = world.player("us", supportNo);
  const tackled = world.player("us", tackledNo);
  const cleaners = [world.player("us", cleanA), world.player("us", cleanB)];
  const nine = world.player("us", 9);
  const ten = world.player("us", 10);
  const d1 = world.player("them", 6);
  const d2 = world.player("them", 4);
  const guards = [world.player("them", 3), world.player("them", 5)];
  const wide = world.player("them", 12);
  const ref = world.player("ref");

  // Le ballon au pied du ruck, côté nous (+z).
  const foot = new THREE.Vector3(rx, 0.12, rz + 1);
  const nineStart = [rx - 0.75, rz + 1.55];
  // Le contact : le joueur incarné arrive au ras du ruck, côté caméra.
  const hx = rx - 3;
  const hz = rz - 1.5;
  const contactZ = hz - 2.4;
  const start = {
    hero: [hx - 1.2, rz + 6],
    support: [hx + 2.2, rz + 7],
    ten: [hx - 4.5, rz + 6],
    d1: [hx - 0.3, rz - 8],
    d2: [hx + 1.5, rz - 8.5],
    wide: [hx - 7, rz - 8],
  };
  const end = {
    hero: [hx, hz],
    support: [hx + 1.5, hz + 3],
    ten: [hx - 3.4, hz + 2.3],
    d1: [hx - 0.3, hz - 4.2],
    d2: [hx + 1.3, hz - 4.5],
    wide: [hx - 6.5, hz - 4.5],
  };
  const paths = Object.fromEntries(Object.keys(start).map((key) => [key, route([start[key], end[key]])]));
  const refSpot = [rx + 4, rz - 3];
  const SETUP = 1.5;
  const pickAt = 0.25;
  const passAt = 0.5;
  const catchAt = 0.95;
  const ball = new THREE.Vector3();
  const from = new THREE.Vector3();
  const to = new THREE.Vector3();
  const shot = broadcast(hx + 0.3, hz - 1, { far: 0.78, fov: 31, y: -0.9 });
  const camera = keys([
    [0, [hx - 50, 24, hz + 30, hx * 0.6, 0, hz + 2, 44]],
    [SETUP, [...shot.pos, ...shot.look, shot.fov]],
  ]);

  function setupFrame(t) {
    // Le ruck : le plaqué au sol, deux des nôtres et deux des leurs liés au-dessus de lui.
    tackled.place(rx, rz + 0.1, FACE_LINE).set(ground());
    cleaners[0].place(rx - 0.42, rz + 0.1, FACE_LINE).set(bind(t, 1, 0.8));
    cleaners[1].place(rx + 0.42, rz + 0.15, FACE_LINE).set(bind(t + 0.3, 1, 0.8));
    guards[0].place(rx - 0.42, rz - 1.05, FACE_FIELD).set(bind(t + 0.5, 1, 0.8));
    guards[1].place(rx + 0.42, rz - 1.05, FACE_FIELD).set(bind(t + 0.8, 1, 0.8));
    // Le 9 ramasse et sert, le joueur incarné arrive lancé.
    const nineFace = Math.atan2(end.hero[0] - nineStart[0], end.hero[1] - nineStart[1]);
    nine.place(...nineStart, nineFace);
    nine.set(t < pickAt ? crouch(1) : t < catchAt ? pass(span(t, pickAt, passAt + 0.15), -1) : ready(0.2));
    runner(hero, paths.hero, t, 0, SETUP, { from: 0.9, to: 0.85, speed: 0.75, carry: t > catchAt ? "two" : "none" });
    runner(support, paths.support, t, 0, SETUP, { from: 0.9, to: 0.8, speed: 0.75 });
    runner(ten, paths.ten, t, 0, SETUP, { from: 0.8, to: 0.7, speed: 0.6 });
    runner(d1, paths.d1, t, 0, SETUP, { from: 0.9, to: 0.8, speed: 0.75 });
    runner(d2, paths.d2, t, 0, SETUP, { from: 0.9, to: 0.8, speed: 0.75 });
    runner(wide, paths.wide, t, 0, SETUP, { from: 0.7, to: 0.5, speed: 0.5 });
    ref.place(...refSpot, -Math.PI / 2).set(ready(0.1));
    ref.card.visible = false;
    if (t < pickAt) world.ballAt(foot, new THREE.Vector3(1, 0, 0));
    else if (t < passAt) world.ballAt(ball.lerpVectors(foot, carried(nine, "two", to), span(t, pickAt, passAt)), new THREE.Vector3(1, 0, 0));
    else if (t < catchAt) world.ballAt(lob(carried(nine, "two", from), carried(hero, "two", to), 0.35, span(t, passAt, catchAt), ball), new THREE.Vector3(1, 0, 0));
    else world.ballAt(carried(hero, "two", ball), new THREE.Vector3(1, 0, 0));
    const [cx, cy, cz, lx, ly, lz, fov] = camera(t);
    return { pos: [cx, cy, cz], look: [lx, ly, lz], fov };
  }

  const setup = {
    duration: SETUP,
    frame: setupFrame,
    cues: [
      { at: 0.1, run: () => world.crowd(world.pressure > 1 ? "standing" : "seated") },
      { at: catchAt, run: () => world.crowd("standing") },
    ],
  };

  function preview(key) {
    const draw = world.draw;
    if (key === "charge") return [draw.arrow([hx, hz - 0.3], [hx + 0.3, contactZ - 2.2], 1.8)];
    if (key === "hit_offload") {
      const a = new THREE.Vector3(hx + 0.2, 1.1, contactZ);
      const b = new THREE.Vector3(hx + 1.6, 1.15, contactZ - 0.6);
      const arc = [];
      for (let i = 0; i <= 10; i++) arc.push(lob(a, b, 0.3, i / 10).toArray());
      return [draw.path([end.hero, [hx + 0.2, contactZ]]), draw.mark([hx + 0.2, contactZ], 0.6), draw.arc(arc, 0.08), draw.path([end.support, [hx + 1.6, contactZ - 0.6], [hx + 1.9, contactZ - 6]])];
    }
    const a = carried(hero, "two", new THREE.Vector3());
    const b = new THREE.Vector3(hx - 2.3, 1.1, hz - 1);
    const arc = [];
    for (let i = 0; i <= 10; i++) arc.push(lob(a, b, 0.3, i / 10).toArray());
    return [draw.arc(arc, 0.08), draw.path([end.ten, [hx - 2.3, hz - 1], [hx - 2.8, hz - 5]]), draw.mark([hx - 2.3, hz - 1], 0.6)];
  }

  function outcomeFor(key, result) {
    const { success, effect } = result;
    const ballLost = !success && effect === "lost";
    const hit = 0.42; // le contact
    const contact = [hx + 0.15, contactZ];
    const toContact = route([end.hero, contact]);
    const d1Hit = [contact[0] - 0.45, contact[1] - 0.72];
    const d2Hit = [contact[0] + 0.55, contact[1] - 0.72];
    const duration = key === "hit_offload" && success ? 3.2 : !success && key === "tip_on" ? 3.4 : 3.3;

    const cues = [];
    if (key !== "tip_on") cues.push({ at: hit, run: () => world.sound("impact") });
    if (key === "charge") cues.push({ at: success ? 1.4 : 1.1, run: () => reaction(world, success) });
    if (key === "charge" && ballLost) cues.push({ at: 2.1, run: () => world.sound("whistle") });
    if (key === "hit_offload") cues.push({ at: success ? 1.3 : hit + 0.25, run: () => (success ? world.crowd("standing") : reaction(world, false)) });
    if (key === "tip_on") cues.push(success ? { at: 1.05, run: () => world.crowd("standing") } : { at: 1.05, run: () => world.sound("whistle") });
    if (key === "tip_on" && !success) cues.push({ at: 1.3, run: () => reaction(world, false) });

    return {
      duration,
      cues,
      frame(t) {
        setupFrame(SETUP);
        ref.place(...refSpot, -Math.PI / 2).set(ready(0.1));
        let look = [hx + 0.3, hz - 1];
        let y = -0.2;
        const held = () => world.ballAt(carried(hero, "two", ball), new THREE.Vector3(1, 0, 0));
        // Les deux défenseurs ferment sur le contact.
        const closeIn = (a = hit) => {
          runner(d1, route([end.d1, d1Hit]), t, 0, a, { from: 0.9, to: 1, speed: 0.8 });
          runner(d2, route([end.d2, d2Hit]), t, 0, a, { from: 0.9, to: 1, speed: 0.8 });
        };
        // Le reste de l'équipe suit l'action.
        runner(ten, route([end.ten, [end.ten[0] - 0.4, end.ten[1] - 4]]), t, 0, duration, { from: 0.7, to: 0.3, speed: 0.5 });
        runner(wide, route([end.wide, [end.wide[0] + 1.5, end.wide[1] - 1.5]]), t, 0, duration, { from: 0.5, to: 0.2, speed: 0.4 });
        runner(support, route([end.support, [hx + 1.3, contactZ + 1.2]]), t, 0, 1.2, { from: 0.8, to: 0.4, speed: 0.7 });

        if (key === "charge") {
          closeIn();
          runner(hero, toContact, t, 0, hit, { from: 0.85, to: 1, speed: 0.9, carry: "two" });
          if (t < hit) held();
          else if (success) {
            // Il les fait reculer : trois mètres, jambes en action, puis il se pose vers l'avant.
            const k = smooth(span(t, hit, 1.5));
            const z = contact[1] - 3 * k;
            const down = span(t, 1.55, 1.95);
            hero.place(contact[0], z, FACE_LINE).set(down > 0 ? tackle(down) : DRIVE(t * 2.4));
            const fall = span(t, 1.45, 1.85);
            d1.place(d1Hit[0], d1Hit[1] - 3 * k - 0.5 * fall, FACE_FIELD).set(fall > 0 ? mixPose(GRIP, ground(true), smooth(fall)) : GRIP);
            d2.place(d2Hit[0], d2Hit[1] - 3 * k - 0.5 * fall, FACE_FIELD).set(fall > 0 ? mixPose(GRIP, ground(true), smooth(fall)) : GRIP);
            // Le soutien arrive sur lui, le ballon est posé en arrière.
            runner(support, route([end.support, [contact[0] + 0.5, contact[1] - 1.6]]), t, 0.2, 1.9, { from: 0.8, to: 0.5, speed: 0.8 });
            if (t > 1.9) support.place(contact[0] + 0.5, contact[1] - 1.6, FACE_LINE).set(bind(t, 1, 0.8));
            const lie = new THREE.Vector3(contact[0] + 0.05, 0.13, z + 0.85);
            if (down < 1) held();
            else world.ballAt(lie, new THREE.Vector3(1, 0, 0));
            if (t > 1.95) hero.set(ground());
            look = [contact[0], z + 0.6];
          } else {
            // Stoppé net : il ne gagne rien, les deux le mettent au sol sur place.
            const k = span(t, hit + 0.45, hit + 0.9);
            hero.place(contact[0], contact[1] + 0.25 * smooth(k), FACE_LINE).set(k > 0 ? mixPose(DRIVE(t * 1.2), ground(), smooth(k)) : DRIVE(t * 1.2));
            d1.place(d1Hit[0], d1Hit[1] + 0.2 * smooth(k), FACE_FIELD + 0.15).set(k > 0 ? tackle(0.5 + k * 0.5) : GRIP);
            d2.place(d2Hit[0], d2Hit[1] + 0.2 * smooth(k), FACE_FIELD - 0.15).set(k > 0 ? tackle(0.3 + k * 0.5) : GRIP);
            const placed = hit + 1.1;
            const lie = new THREE.Vector3(contact[0], 0.13, contact[1] + 1.25);
            // Le ballon ressort lentement ; s'il est perdu, leur 3 arrive et le prend.
            if (t < hit + 0.5) held();
            else if (t < placed) world.ballAt(ball.lerpVectors(carried(hero, "two", from), lie, span(t, hit + 0.5, placed)), new THREE.Vector3(1, 0, 0));
            else if (!ballLost) {
              world.ballAt(lie, new THREE.Vector3(1, 0, 0));
              // Notre 9, en retard, arrive enfin sur le ballon.
              runner(nine, route([nineStart, [lie.x - 0.5, lie.z + 0.5]]), t, placed - 0.6, placed + 1.1, { from: 0.4, to: 0.3, speed: 0.6 });
              if (t > placed + 1.1) nine.set(crouch(0.9));
            } else {
              const thief = guards[0];
              const pick = placed + 0.75;
              const spot = [lie.x - 0.65, lie.z - 0.35];
              if (t > placed) runner(thief, route([[rx - 0.42, rz - 1.05], spot]), t, placed - 0.1, pick, { from: 0.4, to: 0.5, speed: 0.7 });
              if (t >= pick) {
                const k2 = span(t, pick, pick + 0.25);
                thief.place(spot[0], spot[1], FACE_FIELD + 0.4).set(k2 < 1 ? crouch(1) : ready(0.25));
              }
              world.ballAt(t < pick + 0.2 ? lie : carried(thief, "two", ball), new THREE.Vector3(1, 0, 0));
              if (t > pick + 0.5) runner(thief, route([spot, [spot[0] - 2, spot[1] + 3.5]]), t, pick + 0.5, duration + 0.6, { from: 0.3, to: 0.7, speed: 0.7, carry: "two" });
            }
          }
        } else if (key === "hit_offload") {
          closeIn();
          runner(hero, toContact, t, 0, hit, { from: 0.85, to: 1, speed: 0.9, carry: "two" });
          if (t < hit) held();
          else if (success) {
            // Debout dans le contact, il libère ses bras : le soutien perce à côté de lui.
            const release = hit + 0.35;
            const caught = release + 0.28;
            const backAt = caught + 0.75; // il rend le ballon
            const backIn = backAt + 0.38;
            const breakLine = route([[hx + 1.3, contactZ + 1.2], [contact[0] + 1.6, contact[1] - 0.8], [contact[0] + 2.4, contact[1] - 7.5]]);
            runner(support, breakLine, t, 0.55, duration, { from: 0.6, to: 1, speed: 0.95, carry: t > caught ? "two" : "none" });
            // Le joueur incarné s'arrache des deux défenseurs et repart.
            const spinAt = caught + 0.1;
            const go = route([[contact[0], contact[1]], [contact[0] - 0.5, contact[1] - 1.8], [contact[0] - 0.2, contact[1] - 7.3]]);
            if (t < spinAt) {
              hero.place(contact[0], contact[1], FACE_LINE).set(t < release ? DRIVE(t * 2.4) : pass(span(t, release - 0.1, release + 0.15), 1));
            } else runner(hero, go, t, spinAt, duration, { from: 0.25, to: 1, speed: 0.95, carry: t > backIn ? "one" : "two" });
            // Les deux défenseurs, pris à contre-pied, tombent derrière lui.
            const k = span(t, spinAt, spinAt + 0.5);
            d1.place(d1Hit[0] - 0.5 * smooth(k), d1Hit[1], FACE_FIELD).set(t < spinAt ? GRIP : mixPose(GRIP, ground(), smooth(k)));
            d2.place(d2Hit[0] + 0.3 * smooth(k), d2Hit[1], FACE_FIELD).set(t < spinAt ? GRIP : mixPose(GRIP, ground(true), smooth(k)));
            // Le ballon : de ses mains à celles du soutien, et retour.
            if (t < release) held();
            else if (t < caught) world.ballAt(lob(carried(hero, "two", from), carried(support, "two", to), 0.22, span(t, release, caught), ball), new THREE.Vector3(1, 0, 0));
            else if (t < backAt) world.ballAt(carried(support, "two", ball), new THREE.Vector3(1, 0, 0));
            else if (t < backIn) world.ballAt(lob(carried(support, "two", from), carried(hero, "two", to), 0.25, span(t, backAt, backIn), ball), new THREE.Vector3(1, 0, 0));
            else world.ballAt(carried(hero, "one", ball), new THREE.Vector3(0, 0, 1));
            look = [lerp(contact[0], hero.root.position.x, 0.5) + 0.8, lerp(contact[1], hero.root.position.z, 0.7)];
          } else {
            // Le ballon lui échappe au contact : il tombe devant, leur 6 le ramasse et repart.
            const k = span(t, hit + 0.1, hit + 0.65);
            hero.place(contact[0], contact[1] + 0.3 * smooth(k), FACE_LINE).set(k > 0 ? mixPose(DRIVE(t), ground(), smooth(k)) : DRIVE(t * 2));
            d2.place(d2Hit[0], d2Hit[1] + 0.2 * smooth(k), FACE_FIELD - 0.2).set(k > 0 ? tackle(0.4 + k * 0.6) : GRIP);
            const lie = new THREE.Vector3(contact[0] - 0.75, 0.13, contact[1] - 0.75);
            const pick = hit + 0.95;
            const spot = [lie.x - 0.5, lie.z - 0.35];
            const spill = span(t, hit + 0.04, hit + 0.42);
            if (t < hit + 0.04) held();
            else if (t < pick) world.ballAt(spill < 1 ? lob(carried(hero, "two", from), lie, 0.35, spill, ball) : lie, new THREE.Vector3(1, 0.3, 0));
            else world.ballAt(carried(d1, "two", ball), new THREE.Vector3(1, 0, 0));
            if (t >= hit) {
              const j = smooth(span(t, hit, pick));
              d1.place(lerp(d1Hit[0], spot[0], j), lerp(d1Hit[1], spot[1], j), FACE_FIELD + 0.2).set(j < 1 ? crouch(0.5 + 0.5 * j) : ready(0.3));
              if (t > pick + 0.15) runner(d1, route([spot, [spot[0] - 2.5, spot[1] + 6]]), t, pick + 0.15, duration, { from: 0.3, to: 0.9, speed: 0.85, carry: "two" });
            }
            if (t > 1.8) support.set(mixPose(support.current, dejected(), smooth(span(t, 1.8, 2.2))));
            look = [contact[0] - 0.5, contact[1] + 0.3];
          }
        } else {
          // La passe courte : il fixe les deux, juste avant le contact, et sert l'ouvreur.
          const fixed = [hx + 0.05, hz - 1];
          const throwAt = 0.45;
          const tenCatch = [hx - 1.9, hz - 1.1];
          const tenFrom = end.ten;
          const catchIt = throwAt + 0.34;
          const tenRun = route([tenFrom, tenCatch, [hx - 2.7, hz - 8]]);
          runner(hero, route([end.hero, fixed]), t, 0, throwAt + 0.1, { from: 0.85, to: 0.5, speed: 0.7, carry: "two" });
          if (t >= throwAt) hero.set(pass(span(t, throwAt - 0.05, throwAt + 0.25), -1));
          if (t > throwAt + 0.7) runner(hero, route([fixed, [fixed[0] - 0.2, fixed[1] - 2.2]]), t, throwAt + 0.7, duration, { from: 0.3, to: 0.3, speed: 0.4 });
          runner(d1, route([end.d1, [fixed[0] - 0.4, fixed[1] - 2]]), t, 0, 1, { from: 0.9, to: 0.3, speed: 0.7 });
          runner(d2, route([end.d2, [fixed[0] + 1, fixed[1] - 2.1]]), t, 0, 1, { from: 0.9, to: 0.3, speed: 0.7 });
          if (t < throwAt) held();
          if (success) {
            // Le jeu continue : l'ouvreur prend la balle en course, les deux ont mordu.
            runner(ten, tenRun, t, 0, duration, { from: 0.8, to: 0.8, speed: 0.75, carry: t > catchIt ? "two" : "none" });
            if (t >= throwAt && t < catchIt) world.ballAt(lob(carried(hero, "two", from), carried(ten, "two", to), 0.2, span(t, throwAt, catchIt), ball), new THREE.Vector3(1, 0, 0));
            else if (t >= catchIt) world.ballAt(carried(ten, "two", ball), new THREE.Vector3(1, 0, 0));
            look = [hx - 0.8, lerp(hz - 1, hz - 4, smooth(span(t, 0.6, duration)))];
            // Le plaquage du large, sans ballon perdu : l'arrêt reste à jouer.
            if (t > 1) {
              runner(d1, route([[fixed[0] - 0.4, fixed[1] - 2], [hx - 2.5, hz - 7]]), t, 1, duration, { from: 0.3, to: 0.6, speed: 0.6 });
              runner(wide, route([end.wide, [hx - 4, hz - 7.5]]), t, 0, duration, { from: 0.6, to: 0.6, speed: 0.55 });
            }
          } else {
            // Trop courte : le ballon tombe devant l'ouvreur et roule vers leur ligne, en-avant.
            const miss = throwAt + 0.34;
            runner(ten, route([tenFrom, tenCatch]), t, 0, miss + 0.1, { from: 0.8, to: 0.2, speed: 0.7 });
            if (t > miss + 0.1) ten.place(tenCatch[0], tenCatch[1], FACE_LINE).set(t < miss + 0.5 ? crouch(0.45) : dejected());
            const bounce = new THREE.Vector3(tenCatch[0] + 0.1, 0.13, tenCatch[1] - 1.1);
            const rest = new THREE.Vector3(tenCatch[0] + 0.2, 0.13, tenCatch[1] - 2.3);
            const a = carried(hero, "two", from);
            if (t >= throwAt && t < miss) world.ballAt(lob(a, bounce, 0.1, span(t, throwAt, miss), ball), new THREE.Vector3(1, 0.3, 0));
            else if (t >= miss) {
              const k = span(t, miss, miss + 0.7);
              ball.lerpVectors(bounce, rest, 1 - (1 - k) * (1 - k));
              ball.y = 0.13 + Math.abs(Math.sin(k * Math.PI * 2)) * 0.45 * (1 - k);
              world.ballAt(ball, new THREE.Vector3(1, 0, 0), k * 9, new THREE.Vector3(1, 0, 0));
            }
            // L'arbitre arrête le jeu, bras tendu vers leur attaque : mêlée pour eux.
            const callAt = 1.05;
            ref.set(t > callAt ? signal(1, 0.85 * smooth(span(t, callAt, callAt + 0.3))) : ready(0.1));
            // Leur 6 ramasse le ballon mort.
            const pick = 2.05;
            const spot = [rest.x - 0.4, rest.z - 0.5];
            if (t > miss) {
              const j = smooth(span(t, 1, pick));
              d1.place(lerp(fixed[0] - 0.4, spot[0], j), lerp(fixed[1] - 2, spot[1], j), FACE_FIELD).set(j < 1 ? run(t * 2.5, 0.3) : t < pick + 0.2 ? crouch(1) : ready(0.2));
            }
            if (t >= pick + 0.2) world.ballAt(carried(d1, "two", ball), new THREE.Vector3(1, 0, 0));
            if (t > 1.4) {
              const k = smooth(span(t, 1.4, 1.9));
              hero.set(mixPose(hero.current, dejected(), k));
              support.set(mixPose(support.current, dejected(), k));
            }
            look = [hx - 0.8, hz - 2];
          }
        }
        return broadcast(look[0], look[1], { far: 0.78, fov: 31, y });
      },
    };
  }

  return { setup, preview, outcome: outcomeFor };
}
