import * as THREE from "three";

import { TOUCH } from "../field.js";
import { cheer, crouch, dejected, dive, ground, jump, kick, pass, ready, run, signal, tackle, tryAward } from "../rig.js";
import { FACE_FIELD, FACE_LINE, broadcast, carried, grubber, headingTo, keys, lerp, lob, penaltyAgainst, reaction, route, runner, smooth, span } from "./common.js";

// Carrière de joueur : le jeu au pied et les ballons qui tombent du ciel.
// - cross_kick : la défense monte en pointe, l'ailier est seul à l'opposé ; transversale
//   au pied (il aplatit), passe plate dans l'intervalle (franchissement, puis deux contre
//   un), ou trouver la touche.
// - box_kick : le ballon sort d'un ruck dans notre camp ; chandelle (récupérée au
//   contest), partir au ras (franchissement), ou servir l'ouvreur.
// - counter : réception d'un long coup de pied adverse dans nos 22 ; relancer
//   (franchissement), chandelle à suivre, ou trouver la touche.
// Notre équipe attaque vers la ligne d'essai (z = 0) ; nos 22 sont en z = 78.

const v = (x, y, z) => new THREE.Vector3(x, y, z);
const ARC = (a, b, height, steps = 14) => {
  const out = [];
  for (let i = 0; i <= steps; i++) out.push(lob(a, b, height, i / steps).toArray());
  return out;
};
// Le ballon entre deux mains, ou porté ; `flight` : [départ, arrivée, hauteur, t0, t1].
function placeBall(world, ball, t, flights, holder) {
  for (const [a, b, height, t0, t1] of flights) {
    if (t >= t0 && t < t1) return world.ballAt(lob(a(), b(), height, span(t, t0, t1), ball), v(Math.sin(t * 9), 0.4, Math.cos(t * 9)));
  }
  const [player, how] = holder(t);
  if (player) world.ballAt(carried(player, how, ball), v(1, 0, 0));
}

// --- Transversale -----------------------------------------------------------------------

export function buildCrossKick(world, data) {
  const rng = world.rng;
  const s = rng() < 0.5 ? -1 : 1; // le côté du joueur incarné ; l'ailier seul est à -s
  const hx = s * 8;
  const hz = 28;
  const hero = world.player("us", data.hero ?? 10, { hero: true });
  const nine = world.player("us", 9);
  const twelve = world.player("us", data.hero === 12 ? 13 : 12);
  const wing = world.player("us", s > 0 ? 11 : 14);
  const theirWing = world.player("them", s > 0 ? 14 : 11);
  const fullback = world.player("them", 15);
  const rush = [10, 12, 13, 7].map((n, i) => [world.player("them", n), [hx - s * (1 + i * 5.5), 21.5]]);
  const ref = world.player("ref");
  const ruck = [hx + s * 5, 31];
  const twelveAt = [hx - s * 5, hz + 1.5];
  const wingAt = [-s * 30, 31];
  const ball = new THREE.Vector3();
  const shot = broadcast(hx - s * 4, hz - 3, { far: 1.05, fov: 34 });
  const camera = keys([
    [0, [hx - 56, 26, 56, 0, 0, 28, 44]],
    [1.3, [...shot.pos, ...shot.look, shot.fov]],
  ]);
  const passAt = [0.3, 0.65];

  function setupFrame(t) {
    nine.place(ruck[0], ruck[1] + 0.6, headingTo(...ruck, hx, hz)).set(t < passAt[0] ? crouch(1) : pass(span(t, passAt[0] - 0.1, passAt[0] + 0.2), s > 0 ? 1 : -1));
    runner(hero, route([[hx + s * 1, hz + 4], [hx, hz]]), t, 0, 1.3, { from: 0.5, to: 0.5, speed: 0.5, carry: t > passAt[1] ? "two" : "none" });
    runner(twelve, route([[twelveAt[0], twelveAt[1] + 3], twelveAt]), t, 0, 1.3, { from: 0.5, to: 0.5, speed: 0.5 });
    runner(wing, route([[wingAt[0], wingAt[1] + 3], wingAt]), t, 0, 1.3, { from: 0.4, to: 0.4, speed: 0.4 });
    // La défense monte en pointe : leur ailier serre, il n'y a personne derrière.
    rush.forEach(([player, [x, z]]) => runner(player, route([[x, z - 3], [x, z + 3]]), t, 0, 1.3, { from: 0.7, to: 1, speed: 0.85 }));
    runner(theirWing, route([[-s * 22, 18], [-s * 21, 22]]), t, 0, 1.3, { from: 0.6, to: 0.9, speed: 0.8 });
    fullback.place(s * 4, 6, FACE_FIELD).set(ready(0.3));
    ref.place(hx + s * 8, hz + 2, -s * Math.PI * 0.5).set(ready(0.1));
    placeBall(world, ball, t, [[() => carried(nine, "two", v()), () => carried(hero, "two", v()), 0.35, ...passAt]], (u) => [u < passAt[0] ? nine : hero, u < passAt[0] ? "low" : "two"]);
    const [cx, cy, cz, lx, ly, lz, fov] = camera(t);
    return { pos: [cx, cy, cz], look: [lx, ly, lz], fov };
  }

  const setup = { duration: 1.3, frame: setupFrame, cues: [{ at: 0.1, run: () => world.crowd(world.pressure > 1 ? "standing" : "seated") }] };
  const land = [-s * 28, 8];
  const corner = [-s * 27.5, -1.3];
  const loopLine = [[hx, hz], [hx - s * 3.5, hz - 2], [hx - s * 3.8, 23], [hx - s * 4.2, 15]];
  const touchAt = [s * (TOUCH + 2), 7];
  const wide = { pos: [-38, 28, 44], look: [0, -2, 18], fov: 44 };

  function preview(key) {
    const draw = world.draw;
    const from = carried(hero, "two", v());
    if (key === "cross") return [draw.arc(ARC(from, v(land[0], 1.4, land[1]), 11)), draw.path([wingAt, land, corner]), draw.mark(corner)];
    if (key === "flat") return [draw.arc(ARC(from, carried(twelve, "two", v()), 0.25, 8), 0.08), draw.path(loopLine), draw.mark(loopLine[3])];
    return [draw.arc(ARC(from, v(touchAt[0], 0.5, touchAt[1]), 14)), draw.mark([s * TOUCH, touchAt[1]])];
  }

  function outcomeFor(key, result) {
    const good = result.success;
    const kickAt = 0.3;
    const cues = [{ at: kickAt, run: () => key !== "flat" && world.sound("kick") }];
    let duration = 3;
    let frame;
    const pressOn = (t) => rush.forEach(([player, [x, z]]) => runner(player, route([[x, z + 3], [x - s * 0.5, z + 7]]), t, 0, 1.2, { from: 1, to: 0.3, speed: 0.8 }));
    const kicking = (t) => hero.place(hx, hz, headingTo(hx, hz, ...(key === "cross" ? land : touchAt))).set(t < 0.1 ? ready(0.2) : kick(span(t, 0.1, kickAt + 0.4)));

    if (key === "cross") {
      const arrive = 1.9;
      const catchPoint = v(land[0], 1.4, land[1]);
      // Raté : le rebond l'emmène en touche (« le ballon file en touche »).
      const bounceTo = v(-s * (TOUCH + 2.5), 0.12, land[1] - 4);
      duration = good ? 3.6 : 3.2;
      cues.push({ at: good ? 2.8 : arrive + 0.2, run: () => (good ? (world.sound("whistle", true), reaction(world, true)) : reaction(world, false)) });
      frame = (t) => {
        pressOn(t);
        kicking(t);
        runner(wing, route([wingAt, [land[0], land[1] + 0.5], corner]), t, 0, good ? 2.5 : 2.2, { from: 0.6, to: 1, speed: 1, carry: good && t > arrive ? "one" : "none" });
        if (good && t > 2.5) {
          const k = span(t, 2.5, 2.9);
          wing.place(corner[0], lerp(corner[1] + 0.8, corner[1], smooth(k)), FACE_LINE).set(t > 3.2 ? cheer(t * 1.5) : dive(k));
        }
        // Raté : leur ailier se retourne et regarde le ballon sortir.
        if (!good) runner(theirWing, route([[-s * 21, 22], [-s * 29, land[1] - 2]]), t, 0.4, 2.6, { from: 0.3, to: 0.2, speed: 0.8 });
        const kickFrom = () => carried(hero, "two", v());
        if (t < kickAt) world.ballAt(kickFrom(), v(1, 0, 0));
        else if (t < arrive) world.ballAt(lob(kickFrom(), catchPoint, 11, span(t, kickAt, arrive), ball), v(Math.sin(t * 8), 1, 0));
        else if (good) world.ballAt(carried(wing, t > 2.5 ? "low" : "one", ball), v(0, 0, 1));
        else world.ballAt(grubber(v(land[0], 0.12, land[1]), bounceTo, span(t, arrive, 2.6), 3, ball), v(1, 0.3, 0));
        ref.place(hx + s * 8, hz + 2, -s * Math.PI * 0.5).set(good && t > 2.8 ? tryAward(smooth(span(t, 2.8, 3.1))) : ready(0.1));
        const follow = smooth(span(t, kickAt, arrive));
        return broadcast(lerp(hx, land[0], follow), lerp(hz - 3, land[1], follow), { far: lerp(1.05, 0.9, follow), fov: 34 });
      };
    } else if (key === "flat") {
      // La boucle : passe plate au 12, qui la lui rend dans l'intervalle.
      const out = [0.15, 0.4];
      const back = [0.65, 0.9];
      const thief = rush[1][0];
      duration = good ? 2.4 : 2.8;
      cues.push({ at: good ? 1.4 : 0.45, run: () => reaction(world, good) });
      frame = (t) => {
        pressOn(t);
        if (good) {
          runner(hero, route(loopLine), t, 0, duration, { from: 0.6, to: 1, speed: 0.95, carry: t > back[1] ? "one" : "none" });
          if (t < out[0] + 0.2) hero.set(pass(span(t, out[0] - 0.1, out[0] + 0.2), -s));
          runner(twelve, route([twelveAt, [twelveAt[0], twelveAt[1] - 2.5]]), t, 0, back[0], { from: 0.5, to: 0.7, speed: 0.7, carry: t > out[1] ? "two" : "none" });
          if (t >= back[0]) twelve.set(pass(span(t, back[0] - 0.1, back[0] + 0.2), s));
          if (t > 1.0) rush[1][0].set(tackle(span(t, 1.0, 1.5)));
          placeBall(world, ball, t, [
            [() => carried(hero, "two", v()), () => carried(twelve, "two", v()), 0.2, ...out],
            [() => carried(twelve, "two", v()), () => carried(hero, "two", v()), 0.2, ...back],
          ], (u) => [u < out[0] ? hero : u < back[0] ? twelve : hero, u < back[0] ? "two" : "one"]);
          return broadcast(hero.root.position.x, hero.root.position.z - 2, { far: 0.9 });
        }
        // Interceptée : leur 12 s'interpose et file à l'essai de l'autre côté.
        hero.place(hx, hz, FACE_LINE).set(t < out[0] + 0.3 ? pass(span(t, out[0] - 0.1, out[0] + 0.2), -s) : dejected());
        const cut = [lerp(hx, twelveAt[0], 0.5), hz - 0.6];
        if (t < out[1]) thief.place(lerp(rush[1][1][0], cut[0], smooth(span(t, 0, out[1]))), lerp(rush[1][1][1] + 3, cut[1], smooth(span(t, 0, out[1]))), FACE_FIELD).set(run(t * 3, 0.9));
        else runner(thief, route([cut, [cut[0] + s * 2, 50]]), t, out[1], duration, { from: 0.6, to: 1, speed: 1, carry: "one" });
        placeBall(world, ball, t, [[() => carried(hero, "two", v()), () => v(cut[0], 1.2, cut[1]), 0.2, ...out]], (u) => [u < out[0] ? hero : thief, u < out[0] ? "two" : "one"]);
        return broadcast(thief.root.position.x, Math.min(thief.root.position.z, 40) - 2, { far: 0.9 });
      };
    } else {
      // En touche, loin devant ; raté, leur arrière le prend avant la ligne.
      const arrive = 1.9;
      const catcher = [s * (TOUCH - 4), touchAt[1] + 1];
      const end = good ? v(touchAt[0], 0.4, touchAt[1]) : v(catcher[0], 1.3, catcher[1]);
      duration = 3;
      cues.push({ at: arrive, run: () => (good ? (world.sound("whistle"), world.crowd("standing")) : reaction(world, false)) });
      frame = (t) => {
        pressOn(t);
        kicking(t);
        runner(fullback, route([[s * 4, 6], catcher]), t, 0, arrive, { from: 0.4, to: 0.8, speed: 0.9 });
        if (!good && t > arrive) runner(fullback, route([catcher, [catcher[0] - s * 3, catcher[1] + 12]]), t, arrive, duration, { from: 0.3, to: 0.8, speed: 0.8, carry: "one" });
        const from = () => carried(hero, "two", v());
        if (t < kickAt) world.ballAt(from(), v(1, 0, 0));
        else if (t < arrive) world.ballAt(lob(from(), end, 14, span(t, kickAt, arrive), ball), v(Math.sin(t * 8), 1, 0));
        else if (good) world.ballAt(end, v(1, 0, 0));
        else world.ballAt(carried(fullback, "one", ball), v(0, 0, 1));
        ref.place(hx + s * 8, hz + 2, -s * Math.PI * 0.5).set(ready(0.1));
        const follow = smooth(span(t, kickAt, arrive));
        return broadcast(lerp(hx, touchAt[0] - s * 6, follow), lerp(hz - 3, touchAt[1] + 2, follow), { fov: 34 });
      };
    }
    return {
      duration,
      cues,
      frame(t) {
        setupFrame(1.3);
        return frame(t);
      },
    };
  }

  return { setup, preview, previewShot: () => wide, outcome: outcomeFor };
}

// --- Chandelle du demi de mêlée ----------------------------------------------------------

export function buildBoxKick(world, data) {
  const rng = world.rng;
  const s = rng() < 0.5 ? -1 : 1; // le côté fermé
  const rx = s * (6 + rng() * 6);
  const rz = 71;
  const hero = world.player("us", data.hero ?? 9, { hero: true });
  const ten = world.player("us", data.hero === 10 ? 12 : 10);
  const chaser = world.player("us", s > 0 ? 14 : 11);
  const ruckOurs = [world.player("us", 4), world.player("us", 7)];
  const ruckTheirs = world.player("them", 6);
  const guard = world.player("them", 7);
  const line = [-6, -1, 5].map((dx, i) => [world.player("them", [10, 12, 13][i]), [rx + dx * -s, rz - 7]]);
  const fullback = world.player("them", 15);
  const ref = world.player("ref");
  const ballAt = v(rx, 0.12, rz + 1.1);
  const heroAt = [rx - s * 0.4, rz + 1.6];
  const tenAt = [rx - s * 7, rz + 5];
  const chaserAt = [rx + s * 9, rz + 1];
  const land = [rx + s * 5, 52];
  const ball = new THREE.Vector3();
  const shot = broadcast(rx, rz - 1, { far: 0.85, fov: 32, y: 0.4 });
  const camera = keys([
    [0, [rx - 52, 25, rz + 32, rx * 0.6, 0, rz - 2, 44]],
    [1.2, [...shot.pos, ...shot.look, shot.fov]],
  ]);

  function setupFrame(t) {
    ruckOurs[0].place(rx, rz + 0.4, FACE_LINE).set(crouch(0.9));
    ruckOurs[1].place(rx + s * 0.6, rz + 0.5, FACE_LINE).set(crouch(0.9));
    ruckTheirs.place(rx + s * 0.2, rz - 0.9, FACE_FIELD).set(crouch(0.9));
    guard.place(rx + s * 2, rz - 1.2, FACE_FIELD).set(ready(0.6));
    runner(hero, route([[rx - s * 3, rz + 4], heroAt]), t, 0, 1.0, { from: 0.8, to: 0.2, speed: 0.6 });
    if (t >= 1.0) hero.place(...heroAt, headingTo(...heroAt, rx, rz)).set(crouch(0.9));
    ten.place(...tenAt, FACE_LINE).set(ready(0.3));
    chaser.place(...chaserAt, FACE_LINE).set(ready(0.4));
    line.forEach(([player, at]) => player.place(...at, FACE_FIELD).set(ready(0.5)));
    fullback.place(land[0] - s * 3, land[1] - 6, FACE_FIELD).set(ready(0.3));
    ref.place(rx - s * 5, rz - 1, (s * Math.PI) / 2).set(ready(0.1));
    world.ballAt(ballAt, v(1, 0, 0));
    const [cx, cy, cz, lx, ly, lz, fov] = camera(t);
    return { pos: [cx, cy, cz], look: [lx, ly, lz], fov };
  }

  const setup = { duration: 1.2, frame: setupFrame, cues: [{ at: 0.1, run: () => world.crowd(world.pressure > 1 ? "standing" : "seated") }] };
  const snipeLine = [heroAt, [rx + s * 2.8, rz - 1], [rx + s * 3.4, rz - 12]];
  const wide = { pos: [rx - 36, 28, rz + 14], look: [rx * 0.6, -2, 60], fov: 44 };

  function preview(key) {
    const draw = world.draw;
    if (key === "box") return [draw.arc(ARC(v(heroAt[0], 0.4, heroAt[1]), v(land[0], 2.4, land[1]), 18)), draw.path([chaserAt, land]), draw.mark(land)];
    if (key === "snipe") return [draw.path(snipeLine), draw.mark(snipeLine[2])];
    return [draw.arc(ARC(v(heroAt[0], 0.6, heroAt[1]), carried(ten, "two", v()), 0.5, 8), 0.08), draw.mark(tenAt, 0.7)];
  }

  function outcomeFor(key, result) {
    const good = result.success;
    const pick = 0.25;
    const cues = [];
    let duration = 3;
    let frame;
    if (key === "box") {
      const kickAt = 0.35;
      const arrive = 2.7;
      const top = v(land[0], 2.6, land[1]);
      duration = 3.6;
      cues.push({ at: kickAt, run: () => world.sound("kick") }, { at: arrive, run: () => (world.sound("impact"), reaction(world, good)) });
      frame = (t) => {
        hero.place(...heroAt, FACE_LINE + s * 0.3).set(t < pick ? crouch(1) : kick(span(t, pick, kickAt + 0.4), true));
        runner(chaser, route([chaserAt, [land[0] + s * 0.4, land[1] + 0.6]]), t, 0, arrive - 0.2, { from: 0.6, to: 1, speed: 1 });
        runner(fullback, route([[land[0] - s * 3, land[1] - 6], [land[0] - s * 0.3, land[1] - 0.6]]), t, 0.6, arrive - 0.2, { from: 0.3, to: 0.6, speed: 0.6 });
        // Le contest : les deux sautent, le plus haut prend le ballon.
        const air = span(t, arrive - 0.3, arrive + 0.3);
        const up = Math.sin(air * Math.PI);
        if (t > arrive - 0.3) {
          chaser.set({ ...jump(air < 1 ? 1 : 0.4), lift: up * (good ? 0.9 : 0.5) });
          fullback.set({ ...jump(air < 1 ? 1 : 0.4), lift: up * (good ? 0.5 : 0.9) });
        }
        const winner = good ? chaser : fullback;
        if (t > arrive + 0.5) {
          winner.set(ready(0.2));
          (good ? fullback : chaser).set(dejected());
        }
        if (t < kickAt) world.ballAt(t < pick ? ballAt : carried(hero, "two", ball), v(0, 1, 0));
        else if (t < arrive) world.ballAt(lob(carried(hero, "two", v()), top, 18, span(t, kickAt, arrive), ball), v(Math.sin(t * 7), 1, 0));
        else world.ballAt(winner.local(0, 2.2 + winner.current.lift, 0.2, ball), v(1, 0, 0));
        const follow = smooth(span(t, kickAt, arrive));
        return { ...broadcast(lerp(rx, land[0], follow), lerp(rz - 1, land[1], follow), { far: lerp(0.85, 0.95, follow), fov: 34 }) };
      };
    } else if (key === "snipe") {
      // Au ras du ruck, côté fermé : leur 7 plonge dans le vide, ou le prend.
      const meet = 0.75;
      duration = good ? 2.4 : 2.6;
      cues.push({ at: meet, run: () => world.sound(good ? "kick" : "impact") }, { at: meet + 0.5, run: () => reaction(world, good) });
      frame = (t) => {
        if (t < pick) hero.place(...heroAt, FACE_LINE).set(crouch(1));
        else if (good) runner(hero, route(snipeLine), t, pick, duration, { from: 0.4, to: 1, speed: 1, carry: "one" });
        else runner(hero, route(snipeLine.slice(0, 2)), t, pick, meet, { from: 0.4, to: 0.9, speed: 0.9, carry: "one" });
        const k = span(t, meet - 0.2, meet + 0.3);
        if (good) guard.place(rx + s * 2, rz - 1.2 - 0.6 * smooth(k), FACE_FIELD + s * 0.5).set(k < 1 ? tackle(k) : ground());
        else {
          guard.place(rx + s * 2.4, rz - 1.4, FACE_FIELD).set(tackle(k));
          if (t > meet) hero.place(rx + s * 2.8, rz - 1.4 - 0.4 * k, FACE_LINE).set(k < 1 ? tackle(k * 0.6) : ground());
        }
        const loose = v(rx + s * 3.5, 0.12, rz - 3.5);
        if (t < pick) world.ballAt(ballAt, v(1, 0, 0));
        else if (good || t < meet) world.ballAt(carried(hero, "one", ball), v(0, 0, 1));
        else world.ballAt(grubber(carried(hero, "one", v()), loose, span(t, meet, meet + 0.6), 2, ball), v(1, 0.3, 0));
        return broadcast(hero.root.position.x, hero.root.position.z - 1, { far: 0.85 });
      };
    } else {
      // Servir l'ouvreur : passe propre, ou dans les pieds (leur 7 plonge dessus).
      const out = [0.35, 0.75];
      const feet = v(tenAt[0] + s * 0.4, 0.12, tenAt[1] - 1);
      duration = 2.6;
      cues.push({ at: out[1], run: () => (good ? world.crowd(world.pressure > 1 ? "standing" : "seated") : reaction(world, false)) });
      frame = (t) => {
        hero.place(...heroAt, headingTo(...heroAt, ...tenAt)).set(t < pick ? crouch(1) : pass(span(t, pick, out[0] + 0.2), s > 0 ? -1 : 1));
        if (good) runner(ten, route([tenAt, [tenAt[0] - s * 1, tenAt[1] - 6]]), t, out[1] - 0.2, duration, { from: 0.4, to: 0.7, speed: 0.7, carry: t > out[1] ? "two" : "none" });
        else {
          ten.place(...tenAt, FACE_LINE).set(t > out[1] ? crouch(0.6) : ready(0.3));
          runner(guard, route([[rx + s * 2, rz - 1.2], [feet.x, feet.z - 0.6]]), t, out[0], 1.4, { from: 0.6, to: 0.8, speed: 0.8 });
          if (t > 1.4) guard.set(crouch(1));
        }
        if (t < pick) world.ballAt(ballAt, v(1, 0, 0));
        else if (t < out[0]) world.ballAt(carried(hero, "two", ball), v(1, 0, 0));
        else if (t < out[1]) world.ballAt(lob(carried(hero, "two", v()), good ? carried(ten, "two", v()) : feet, 0.4, span(t, ...out), ball), v(1, 0, 0));
        else world.ballAt(good ? carried(ten, "two", ball) : feet, v(1, 0, 0));
        return shot;
      };
    }
    return {
      duration,
      cues,
      frame(t) {
        setupFrame(1.2);
        return frame(t);
      },
    };
  }

  return { setup, preview, previewShot: (key) => (key === "box" ? wide : null), outcome: outcomeFor };
}

// --- Réception d'un long coup de pied ------------------------------------------------------

export function buildCounter(world, data) {
  const rng = world.rng;
  const s = rng() < 0.5 ? -1 : 1;
  const hx = s * (3 + rng() * 8);
  const hz = 82;
  const hero = world.player("us", data.hero ?? 15, { hero: true });
  const wings = [world.player("us", 11), world.player("us", 14)];
  const chasers = [-7, 0, 8].map((dx, i) => [world.player("them", [12, 13, 11][i]), [hx + dx, 58]]);
  const ref = world.player("ref");
  const kickFrom = v(hx * 0.3, 1.2, 36);
  const catchAt = 1.1;
  const ball = new THREE.Vector3();
  const shot = broadcast(hx, hz - 4, { far: 0.95, fov: 34 });
  const camera = keys([
    [0, [hx - 40, 30, 60, hx * 0.6, 8, 60, 50]],
    [1.4, [...shot.pos, ...shot.look, shot.fov]],
  ]);
  const wingsAt = [[hx - 11, hz - 3], [hx + 10, hz - 4]];
  const rushTo = (i) => [chasers[i][1][0] * 0.9, 72];

  function setupFrame(t) {
    runner(hero, route([[hx + s * 3, hz + 2], [hx, hz]]), t, 0, catchAt, { from: 0.6, to: 0.1, speed: 0.6 });
    if (t >= catchAt - 0.2) hero.place(hx, hz, FACE_LINE).set({ ...jump(0.6), armL: 1.4, armR: 1.4 });
    if (t >= catchAt + 0.1) hero.set(ready(0.3));
    wings.forEach((player, i) => player.place(...wingsAt[i], FACE_LINE).set(ready(0.3)));
    chasers.forEach(([player, at], i) => runner(player, route([at, rushTo(i)]), t, 0, 1.4, { from: 0.9, to: 1, speed: 1 }));
    ref.place(hx - s * 14, 70, (s * Math.PI) / 2).set(ready(0.1));
    const hands = hero.local(0, 1.7, 0.4, v());
    if (t < catchAt) world.ballAt(lob(kickFrom, hands, 24, (t + 2) / (catchAt + 2), ball), v(Math.sin(t * 6), 1, 0));
    else world.ballAt(carried(hero, "two", ball), v(1, 0, 0));
    const [cx, cy, cz, lx, ly, lz, fov] = camera(t);
    return { pos: [cx, cy, cz], look: [lx, ly, lz], fov };
  }

  const setup = { duration: 1.4, frame: setupFrame, cues: [{ at: 0.2, run: () => world.crowd(world.pressure > 1 ? "standing" : "seated") }] };
  const runLine = [[hx, hz], [hx + s * 2.5, 75], [hx + s * 1.5, 62]];
  const highLand = [hx + s * 2, 60];
  const touchAt = [s * (TOUCH + 2), 60];
  const wide = { pos: [hx - 36, 28, 96], look: [hx * 0.6, -2, 68], fov: 44 };

  function preview(key) {
    const draw = world.draw;
    const from = carried(hero, "two", v());
    if (key === "run") return [draw.path(runLine), draw.mark(runLine[2])];
    if (key === "up_and_under") return [draw.arc(ARC(from, v(highLand[0], 2.2, highLand[1]), 18)), draw.path([[hx, hz], highLand]), draw.mark(highLand)];
    return [draw.arc(ARC(from, v(touchAt[0], 0.5, touchAt[1]), 15)), draw.mark([s * TOUCH, touchAt[1]])];
  }

  function outcomeFor(key, result) {
    const { success: good, effect } = result;
    const cues = [];
    let duration = 3;
    let frame;
    const chase = (t, until, to = null) =>
      chasers.forEach(([player], i) => runner(player, route([rushTo(i), to ? [to[0] + (i - 1) * 2, to[1] - 2] : [rushTo(i)[0], 78]]), t, 0, until, { from: 1, to: 0.7, speed: 0.9 }));
    if (key === "run") {
      const meet = 0.5;
      const first = chasers[1][0];
      duration = good ? 2.4 : 3;
      cues.push({ at: meet, run: () => world.sound(good ? "kick" : "impact") });
      cues.push({ at: meet + 0.6, run: () => (good ? reaction(world, true) : effect === "penalty_conceded" ? penaltyAgainst(world, "us") : reaction(world, false)) });
      frame = (t) => {
        chase(t, meet);
        const k = span(t, meet - 0.2, meet + 0.3);
        if (good) {
          runner(hero, route(runLine), t, 0, duration, { from: 0.5, to: 1, speed: 1, carry: "one" });
          first.place(rushTo(1)[0] + s * 0.6, 74 + k, FACE_FIELD - s * 0.4).set(k < 1 ? tackle(k) : ground());
          wings.forEach((player, i) => runner(player, route([wingsAt[i], [wingsAt[i][0] * 0.8 + hx * 0.2, 64]]), t, 0, duration, { from: 0.5, to: 1, speed: 0.95 }));
          world.ballAt(carried(hero, "one", ball), v(0, 0, 1));
        } else {
          runner(hero, route(runLine.slice(0, 2)), t, 0, meet, { from: 0.5, to: 0.8, speed: 0.8, carry: "one" });
          if (t >= meet) hero.place(...runLine[1], FACE_LINE).set(k < 1 ? tackle(k * 0.6) : ground());
          first.place(runLine[1][0] + s * 0.3, runLine[1][1] - 0.8, FACE_FIELD).set(tackle(k));
          const loose = v(runLine[1][0], 0.12, runLine[1][1] - 2);
          if (t < meet) world.ballAt(carried(hero, "one", ball), v(0, 0, 1));
          else if (effect === "penalty_conceded") world.ballAt(carried(hero, "low", ball), v(1, 0, 0));
          else world.ballAt(grubber(carried(hero, "one", v()), loose, span(t, meet, meet + 0.6), 2, ball), v(1, 0.3, 0));
          // Tenu au sol sans lâcher : l'arbitre siffle contre nous (bras vers -z… leur attaque).
          const r = [hx - s * 14, 70];
          ref.place(lerp(r[0], hx - s * 4, smooth(span(t, meet, meet + 0.8))), lerp(r[1], 75, smooth(span(t, meet, meet + 0.8))), (s * Math.PI) / 2);
          if (effect === "penalty_conceded" && t > meet + 0.6) ref.set(signal(s > 0 ? -1 : 1, smooth(span(t, meet + 0.6, meet + 0.9))));
        }
        return broadcast(hero.root.position.x, hero.root.position.z - 3, { far: 0.9 });
      };
    } else {
      // Au pied : la chandelle à suivre (lui ou leur 13 au rebond), ou la touche.
      const kickAt = 0.3;
      const high = key === "up_and_under";
      const arrive = high ? 2.6 : 2.1;
      const target = high ? v(highLand[0], 2.2, highLand[1]) : good ? v(touchAt[0], 0.4, touchAt[1]) : v(s * (TOUCH - 5), 1.4, touchAt[1] + 1);
      const catcher = chasers[good ? 0 : 1][0];
      duration = 3.4;
      cues.push({ at: kickAt, run: () => world.sound("kick") });
      cues.push({ at: arrive, run: () => (high ? (world.sound("impact"), reaction(world, good)) : good ? (world.sound("whistle"), world.crowd("standing")) : reaction(world, false)) });
      frame = (t) => {
        chase(t, arrive, high ? highLand : null);
        if (high) {
          runner(hero, route([[hx, hz], [highLand[0] + s * 0.3, highLand[1] + 0.6]]), t, kickAt + 0.3, arrive - 0.1, { from: 0.4, to: 1, speed: 1 });
          if (t < kickAt + 0.3) hero.place(hx, hz, FACE_LINE).set(kick(span(t, 0, kickAt + 0.3), true));
          const contester = chasers[1][0];
          if (t > arrive - 0.3) {
            const air = span(t, arrive - 0.3, arrive + 0.3);
            hero.set({ ...jump(1), lift: Math.sin(air * Math.PI) * (good ? 0.9 : 0.5) });
            contester.place(highLand[0] - s * 0.3, highLand[1] - 0.6, FACE_FIELD).set({ ...jump(1), lift: Math.sin(air * Math.PI) * (good ? 0.5 : 0.9) });
          }
          const winner = good ? hero : contester;
          if (t < kickAt) world.ballAt(carried(hero, "two", ball), v(1, 0, 0));
          else if (t < arrive) world.ballAt(lob(carried(hero, "two", v()), target, 18, span(t, kickAt, arrive), ball), v(Math.sin(t * 7), 1, 0));
          else world.ballAt(winner.local(0, 2.2 + winner.current.lift, 0.2, ball), v(1, 0, 0));
          if (t > arrive + 0.5) (good ? contester : hero).set(dejected());
        } else {
          hero.place(hx, hz, headingTo(hx, hz, touchAt[0], touchAt[1])).set(kick(span(t, 0, kickAt + 0.4)));
          if (!good) {
            runner(catcher, route([rushTo(1), [target.x, target.z - 0.6]]), t, 0, arrive, { from: 0.7, to: 0.4, speed: 0.8 });
            if (t > arrive) runner(catcher, route([[target.x, target.z - 0.6], [target.x - s * 3, target.z + 14]]), t, arrive, duration, { from: 0.3, to: 0.9, speed: 0.9, carry: "one" });
          }
          if (t < kickAt) world.ballAt(carried(hero, "two", ball), v(1, 0, 0));
          else if (t < arrive) world.ballAt(lob(carried(hero, "two", v()), target, 15, span(t, kickAt, arrive), ball), v(Math.sin(t * 7), 1, 0));
          else world.ballAt(good ? target : carried(catcher, "one", ball), v(1, 0, 0));
        }
        const follow = smooth(span(t, kickAt, arrive));
        return broadcast(lerp(hx, target.x * 0.8, follow), lerp(hz - 4, target.z, follow), { far: lerp(0.95, 1.1, follow), fov: 34 });
      };
    }
    return {
      duration,
      cues,
      frame(t) {
        setupFrame(1.4);
        return frame(t);
      },
    };
  }

  return { setup, preview, previewShot: (key) => (key === "run" ? null : wide), outcome: outcomeFor };
}
