import * as THREE from "three";

import { TOUCH } from "../field.js";
import { cheer, dejected, dive, ground, kick, pose, ready, run, signal, tackle, tryAward } from "../rig.js";
import { FACE_FIELD, FACE_LINE, broadcast, carried, grubber, keys, lerp, lob, penaltyAgainst, reaction, route, runner, smooth, span } from "./common.js";

// Carrière de joueur, « Le long de la touche » (touchline) : le joueur incarné file le
// long de la ligne de touche, leur arrière arrive. Déborder par l'extérieur (franchissement
// et deux contre un, ou poussé en touche), repiquer à l'intérieur, ou le petit par-dessus
// (rattrapé, il marque ; sinon le ballon sort).

export function buildTouchline(world, data) {
  const rng = world.rng;
  const s = rng() < 0.5 ? -1 : 1; // la touche
  const hx = s * 31.5;
  const hz = 28;
  const hero = world.player("us", data.hero ?? (s > 0 ? 11 : 14), { hero: true });
  const support = world.player("us", data.hero === 13 ? 12 : 13);
  const fullback = world.player("them", 15);
  const cover = world.player("them", s > 0 ? 14 : 11);
  const ref = world.player("ref");
  const supportAt = [s * 24.5, hz - 1.2];
  const fullbackAt = [s * 28.5, hz - 5.5];
  const coverAt = [s * 20, hz - 9];
  const ball = new THREE.Vector3();
  const shot = broadcast(s * 26, hz - 3, { far: 0.95, fov: 32 });
  const camera = keys([
    [0, [s * 20 - 50, 24, hz + 34, s * 18, 0, hz + 4, 44]],
    [1.3, [...shot.pos, ...shot.look, shot.fov]],
  ]);

  function setupFrame(t) {
    runner(hero, route([[hx, hz + 9], [hx, hz]]), t, 0, 1.3, { from: 1, to: 1, speed: 1, carry: "one" });
    runner(support, route([[supportAt[0], supportAt[1] + 8], supportAt]), t, 0, 1.3, { from: 0.9, to: 0.9, speed: 0.9 });
    runner(fullback, route([[s * 24, hz - 14], fullbackAt]), t, 0, 1.3, { from: 0.8, to: 0.8, speed: 0.8 });
    runner(cover, route([[s * 14, hz - 13], coverAt]), t, 0, 1.3, { from: 0.8, to: 0.9, speed: 0.85 });
    ref.place(s * 12, hz + 6, FACE_LINE).set(run(t * 2, 0.4));
    world.ballAt(carried(hero, "one", ball), new THREE.Vector3(0, 0, 1));
    const [cx, cy, cz, lx, ly, lz, fov] = camera(t);
    return { pos: [cx, cy, cz], look: [lx, ly, lz], fov };
  }

  const setup = { duration: 1.3, frame: setupFrame, cues: [{ at: 0.1, run: () => world.crowd("standing") }] };
  const outside = [[hx, hz], [s * 33.6, hz - 5], [s * 33.2, hz - 12]];
  const inside = [[hx, hz], [s * 30, hz - 4], [s * 26, hz - 12]];
  const chipLand = [s * 30.5, hz - 13];
  const finish = [s * 30, -1.3];

  function preview(key) {
    const draw = world.draw;
    if (key === "outside") return [draw.path(outside), draw.mark(outside[2])];
    if (key === "inside") return [draw.path(inside), draw.mark(inside[2])];
    const from = carried(hero, "one", new THREE.Vector3());
    const arc = [];
    for (let i = 0; i <= 12; i++) arc.push(lob(from, new THREE.Vector3(chipLand[0], 0.3, chipLand[1]), 5, i / 12).toArray());
    return [draw.arc(arc), draw.path([[hx, hz], chipLand, finish]), draw.mark(finish)];
  }

  function outcomeFor(key, result) {
    const good = result.success;
    const meet = 0.55;
    const cues = [];
    let duration = 2.4;
    let frame;
    if (key === "outside" || key === "inside") {
      const line = key === "outside" ? outside : inside;
      duration = good ? 2.2 : 2.8;
      cues.push({ at: meet, run: () => world.sound(good ? "kick" : "impact") });
      cues.push({ at: meet + 0.5, run: () => (good ? reaction(world, true) : key === "outside" ? (world.sound("whistle"), reaction(world, false)) : reaction(world, false)) });
      frame = (t) => {
        const k = span(t, meet - 0.2, meet + 0.35);
        if (good) {
          runner(hero, route(line), t, 0, duration, { from: 1, to: 1, speed: 1, carry: "one" });
          // L'arrière plonge, trop court.
          fullback.place(lerp(fullbackAt[0], s * 30.8, smooth(k)), lerp(fullbackAt[1], hz - 4.4, smooth(k)), FACE_FIELD + s * 0.6).set(k < 1 ? tackle(k) : ground());
          runner(support, route([supportAt, [supportAt[0] + s * 1, hz - 12]]), t, 0, duration, { from: 0.9, to: 1, speed: 0.95 });
          if (key === "inside") runner(cover, route([coverAt, [s * 24, hz - 9]]), t, 0, duration, { from: 0.8, to: 0.4, speed: 0.6 });
          world.ballAt(carried(hero, "one", ball), new THREE.Vector3(0, 0, 1));
        } else if (key === "outside") {
          // Poussé en touche : les deux passent la ligne et tombent dehors.
          const contact = [s * 33.4, hz - 3.6];
          runner(hero, route([[hx, hz], contact]), t, 0, meet, { from: 1, to: 1, speed: 1, carry: "one" });
          if (t >= meet) hero.place(lerp(contact[0], s * (TOUCH + 2.2), smooth(k)), contact[1] - 0.8 * k, FACE_LINE + s * 0.6).set(k < 1 ? tackle(k * 0.6) : ground());
          runner(fullback, route([fullbackAt, [contact[0] - s * 0.5, contact[1] - 0.6]]), t, 0, meet, { from: 0.8, to: 1, speed: 0.9 });
          if (t >= meet) fullback.place(lerp(contact[0] - s * 0.5, s * (TOUCH + 1.4), smooth(k)), contact[1] - 0.8, FACE_FIELD - s * 0.6).set(tackle(k));
          runner(support, route([supportAt, [supportAt[0] + s * 2, hz - 4]]), t, 0, 1.2, { from: 0.9, to: 0.1, speed: 0.6 });
          if (t > 1.4) support.set(dejected());
          world.ballAt(carried(hero, t > meet + 0.3 ? "low" : "one", ball), new THREE.Vector3(0, 0, 1));
        } else {
          // Repiqué dedans, leur ailier revient le prendre.
          const contact = [s * 29.6, hz - 4.6];
          runner(hero, route([[hx, hz], contact]), t, 0, meet, { from: 1, to: 1, speed: 1, carry: "one" });
          if (t >= meet) hero.place(contact[0], contact[1] - 0.7 * k, FACE_LINE).set(k < 1 ? tackle(k * 0.6) : ground());
          runner(cover, route([coverAt, [contact[0] - s * 0.6, contact[1] - 0.6]]), t, 0, meet, { from: 0.9, to: 1, speed: 1 });
          if (t >= meet) cover.place(contact[0] - s * 0.5, contact[1] - 0.9, FACE_FIELD).set(tackle(k));
          runner(fullback, route([fullbackAt, [s * 30.5, hz - 6]]), t, 0, meet, { from: 0.8, to: 0.3, speed: 0.6 });
          world.ballAt(carried(hero, "one", ball), new THREE.Vector3(0, 0, 1));
        }
        ref.place(s * 12, hz + 6, FACE_LINE).set(!good && key === "outside" && t > meet + 0.5 ? signal(s > 0 ? -1 : 1, smooth(span(t, meet + 0.5, meet + 0.8))) : ready(0.1));
        return broadcast(lerp(s * 26, hero.root.position.x, 0.5), hero.root.position.z - 2, { far: 0.9 });
      };
    } else {
      // Le petit par-dessus : rattrapé au rebond, il file à l'essai ; sinon il sort.
      const kickAt = 0.3;
      const land = 1.15;
      const regather = 1.75;
      const out = new THREE.Vector3(s * (TOUCH + 1.5), 0.12, chipLand[1] - 3);
      const landing = new THREE.Vector3(chipLand[0], 0.12, chipLand[1]);
      const toLine = route([[chipLand[0], chipLand[1] + 1.2], [finish[0], finish[1] + 0.8]]);
      const lineAt = regather + toLine.total / 8.2;
      duration = good ? lineAt + 1.8 : 2.8;
      cues.push({ at: kickAt, run: () => world.sound("kick") });
      cues.push(good ? { at: lineAt + 0.4, run: () => (world.sound("whistle", true), reaction(world, true)) } : { at: land + 0.5, run: () => (world.sound("whistle"), reaction(world, false)) });
      frame = (t) => {
        if (t < kickAt + 0.15) hero.place(hx, hz, FACE_LINE).set(kick(span(t, 0, kickAt + 0.15)));
        else if (t < regather) runner(hero, route([[hx, hz], [chipLand[0], chipLand[1] + 1.2]]), t, kickAt + 0.15, regather, { from: 0.6, to: 1, speed: 1, carry: good ? "none" : "none" });
        else if (good && t < lineAt) runner(hero, toLine, t, regather, lineAt, { from: 1, to: 1, speed: 1, carry: "one" });
        else if (good) {
          const g = span(t, lineAt, lineAt + 0.45);
          hero.place(finish[0], lerp(finish[1] + 0.8, finish[1], smooth(g)), FACE_LINE).set(t > lineAt + 1.1 ? cheer(t * 1.5) : dive(g));
        } else hero.set(dejected());
        // L'arrière, lobé, se retourne trop tard.
        const turn = span(t, kickAt, 1.2);
        fullback.place(lerp(fullbackAt[0], s * 30, turn), lerp(fullbackAt[1], fullbackAt[1] - 3 * turn, turn), FACE_FIELD + Math.PI * smooth(turn)).set(run(t * 2.5, 0.7));
        const from = new THREE.Vector3(hx, 0.5, hz - 0.5);
        if (t < kickAt) world.ballAt(carried(hero, "one", ball), new THREE.Vector3(0, 0, 1));
        else if (t < land) world.ballAt(lob(from, landing, 5, span(t, kickAt, land), ball), new THREE.Vector3(1, 0.2, 0));
        else if (good && t < regather) world.ballAt(lob(landing, carried(hero, "two", new THREE.Vector3()), 1.2, span(t, land, regather), ball), new THREE.Vector3(1, 0.4, 0));
        else if (good) world.ballAt(carried(hero, t > lineAt ? "low" : "one", ball), new THREE.Vector3(0, 0, 1));
        else world.ballAt(grubber(landing, out, span(t, land, 2.0), 3, ball), new THREE.Vector3(1, 0.3, 0));
        ref.place(s * 18, Math.min(hz + 6, hero.root.position.z + 6), FACE_LINE).set(good && t > lineAt + 0.4 ? tryAward(smooth(span(t, lineAt + 0.4, lineAt + 0.7))) : ready(0.1));
        return broadcast(lerp(s * 26, hero.root.position.x, 0.5), Math.max(hero.root.position.z - 2, 1), { far: 0.95 });
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

  return { setup, preview, outcome: outcomeFor };
}

// --- Provocation --------------------------------------------------------------------------

// Carrière de joueur, « Provocation » : après le coup de sifflet, un adversaire pousse le
// joueur incarné et le chambre ; l'arbitre s'interpose. Riposter (rien de grave, ou carton
// jaune, ou pénalité contre nous), prendre l'arbitre à témoin (pénalité pour nous, ou il
// laisse jouer), tourner les talons.

const POINT = pose({ armR: 1.6, abR: 0.3, elR: 0.1, turn: 0.3 });
const SHOVE = (k) => pose({ lean: 0.3 * k, armL: 1.5 * k, armR: 1.5 * k, elL: 0.3, elR: 0.3, abL: -0.2, abR: -0.2, legL: 0.4 * k, knL: 0.4 * k });
const CHIRP = (t) => pose({ lean: 0.15, armL: 0.8 + Math.sin(t * 7) * 0.4, armR: 0.5, elL: 1.4, elR: 1.0, abL: 0.3, nod: -0.15, turn: Math.sin(t * 3) * 0.2 });

export function buildProvocation(world, data) {
  const rng = world.rng;
  const s = rng() < 0.5 ? -1 : 1;
  const px = s * (2 + rng() * 10);
  const pz = 26;
  const hero = world.player("us", data.hero ?? 6, { hero: true });
  const rival = world.player("them", Math.floor(rng() * 7) + 1);
  const mate = world.player("us", data.hero === 8 ? 4 : 8);
  const pile = [world.player("them", 9), world.player("us", 9)];
  const ref = world.player("ref");
  const heroAt = [px, pz];
  const rivalAt = [px + 0.9, pz - 0.8];
  const refTo = [px + 1.2, pz + 0.7];
  const shot = { pos: [px - 9.5, 3.8, pz + 7], look: [px + 0.6, 1.2, pz - 0.2], fov: 30 };
  const camera = keys([
    [0, [px - 30, 14, pz + 20, px, 0.5, pz, 40]],
    [1.5, [...shot.pos, ...shot.look, shot.fov]],
  ]);
  const shoveAt = 0.7;
  const faceRival = Math.atan2(rivalAt[0] - heroAt[0], rivalAt[1] - heroAt[1]);
  const faceHero = faceRival + Math.PI;

  function setupFrame(t) {
    // Fin d'action : un ruck se défait derrière eux (loin de la caméra), l'adversaire
    // vient au contact et pousse.
    pile[0].place(px + 5, pz - 2.5, FACE_LINE).set(t < 0.6 ? ground() : ready(0.2));
    pile[1].place(px + 5.6, pz - 1.8, FACE_FIELD).set(ready(0.1));
    mate.place(px + 3.2, pz + 1.6, faceRival + Math.PI).set(ready(0.1));
    const back = smooth(span(t, shoveAt, shoveAt + 0.35)) * 0.7;
    hero.place(heroAt[0] - Math.sin(faceRival) * back, heroAt[1] - Math.cos(faceRival) * back, faceRival).set(t < shoveAt ? pose() : ready(0.3));
    runner(rival, route([[rivalAt[0] + 2, rivalAt[1] - 3], rivalAt]), t, 0, shoveAt - 0.1, { from: 0.4, to: 0.2, speed: 0.4 });
    if (t >= shoveAt - 0.1) rival.place(...rivalAt, faceHero).set(t < shoveAt + 0.4 ? SHOVE(span(t, shoveAt - 0.1, shoveAt + 0.1)) : CHIRP(t));
    runner(ref, route([[px + 6, pz - 5], refTo]), t, 0.6, 1.5, { from: 0.4, to: 0.3, speed: 0.6 });
    ref.root.rotation.y = ref.heading = t > 1.4 ? -Math.PI / 2 : ref.heading;
    world.ballAt(new THREE.Vector3(px + 5.3, 0.12, pz - 3), new THREE.Vector3(1, 0, 0));
    const [cx, cy, cz, lx, ly, lz, fov] = camera(t);
    return { pos: [cx, cy, cz], look: [lx, ly, lz], fov };
  }

  const setup = {
    duration: 1.5,
    frame: setupFrame,
    cues: [
      { at: 0.05, run: () => world.sound("whistle") },
      { at: shoveAt, run: () => (world.sound("impact"), world.crowd("standing")) },
    ],
  };

  function preview(key) {
    const draw = world.draw;
    if (key === "hit_back") return [draw.arrow([heroAt[0] - 0.4, heroAt[1] + 0.6], [rivalAt[0], rivalAt[1] + 0.2], 0.9)];
    if (key === "referee") return [draw.path([heroAt, refTo]), draw.mark(refTo, 0.6)];
    const away = [px - 5, pz + 4];
    return [draw.path([heroAt, away]), draw.mark(away, 0.7)];
  }

  function outcomeFor(key, result) {
    const { success: good, effect } = result;
    const cues = [];
    let frame;
    const callAt = 1.2;
    // L'arbitre, tourné vers -x : bras gauche vers +z (eux), droit vers -z (nous).
    const refFor = (team, t) => ref.set(signal(team === "us" ? -1 : 1, smooth(span(t, callAt, callAt + 0.3))));
    if (key === "hit_back") {
      cues.push({ at: 0.35, run: () => world.sound("impact") });
      cues.push({ at: callAt, run: () => (good ? world.crowd("standing") : penaltyAgainst(world, "us")) });
      frame = (t) => {
        hero.place(...heroAt, faceRival).set(t < 0.5 ? SHOVE(span(t, 0, 0.35)) : t > callAt && !good ? dejected() : ready(0.3));
        const k = span(t, 0.35, 0.8);
        rival.place(rivalAt[0] + Math.sin(faceRival) * 0.9 * smooth(k), rivalAt[1] + Math.cos(faceRival) * 0.9 * smooth(k), faceHero).set(k < 0.5 ? ready(0.3) : ground(true));
        ref.place(...refTo, -Math.PI / 2);
        if (good || t < callAt) ref.set(pose({ armL: 1.4, armR: 1.4, abL: 0.6, abR: 0.6, elL: 0.2, elR: 0.2 }));
        else if (effect === "yellow" && t > callAt + 0.6) {
          ref.set(pose({ armR: 3.05, abR: 0.1, elR: 0.05 }));
          ref.card.visible = true;
        } else refFor("them", t);
        if (!(effect === "yellow" && t > callAt + 0.6)) ref.card.visible = false;
        return shot;
      };
    } else if (key === "referee") {
      cues.push({ at: callAt, run: () => (good ? penaltyAgainst(world, "them") : world.sound("groan")) });
      frame = (t) => {
        hero.place(...heroAt, Math.atan2(refTo[0] - heroAt[0], refTo[1] - heroAt[1])).set(t < 1.0 ? POINT : ready(0.2));
        rival.place(...rivalAt, faceHero).set(good && t > callAt ? pose({ armL: 0.4, armR: 0.4, abL: 0.6, abR: 0.6, elL: 1.6, elR: 1.6, nod: 0.3 }) : CHIRP(t));
        ref.place(...refTo, -Math.PI / 2);
        if (good && t > callAt) refFor("us", t);
        else ref.set(t > callAt ? pose({ armL: 0.9, armR: 0.9, abL: -0.2, abR: -0.2, elL: 0.3, elR: 0.3 }) : ready(0.2));
        return shot;
      };
    } else {
      const away = route([heroAt, [px - 5, pz + 4]]);
      cues.push({ at: 1.0, run: () => (good ? world.crowd("seated") : world.sound("groan")) });
      frame = (t) => {
        runner(hero, away, t, 0.2, 1.8, { from: 0.2, to: 0.2, speed: 0.25 });
        if (t < 0.2) hero.set(ready(0.2));
        // Raté : il le suit en le chambrant.
        if (good) rival.place(...rivalAt, faceHero).set(t < 1 ? CHIRP(t) : pose({ armL: 0.3, armR: 0.3, abL: 0.5, abR: 0.5, elL: 1.5, elR: 1.5 }));
        else runner(rival, route([rivalAt, [px - 3.6, pz + 2.6]]), t, 0.3, 1.8, { from: 0.3, to: 0.3, speed: 0.3 });
        if (!good && t > 1.8) rival.set(CHIRP(t));
        ref.place(...refTo, -Math.PI / 2).set(ready(0.1));
        return shot;
      };
    }
    return {
      duration: 2.8,
      cues,
      frame(t) {
        setupFrame(1.5);
        return frame(t);
      },
    };
  }

  return { setup, preview, outcome: outcomeFor };
}
