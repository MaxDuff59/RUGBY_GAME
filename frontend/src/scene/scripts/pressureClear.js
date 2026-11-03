import * as THREE from "three";

import { TOUCH } from "../field.js";
import { cheer, crouch, dejected, dive, ground, jump, kick, mixPose, pass, pose, ready, signal, tackle, tryAward } from "../rig.js";
import { FACE_FIELD, FACE_LINE, broadcast, carried, grubber, headingTo, keys, lerp, lob, reaction, route, runner, smooth, span } from "./common.js";

// Carrière de joueur, « Dégagement sous pression » (pressure_clear) : le joueur incarné
// reçoit le ballon dans ses 22, près de notre ligne (z = 100, sans poteaux), leurs avants
// arrivent. Taper tout de suite (la touche, ou contré), feinter puis taper (leur 7 saute
// dans le vide, ou le prend avec le ballon), relancer à la main (il sort de ses 22, et
// l'action s'enchaîne sur le deux contre un, ou il est pris tout près de sa ligne).
//
// Les échecs suivent l'effet tiré : `try_conceded` (le ballon contré ou échappé finit en
// essai adverse, sur notre ligne), sinon `lost` (ils le récupèrent devant la ligne).

const v = (x = 0, y = 0, z = 0) => new THREE.Vector3(x, y, z);
const ARC = (a, b, height, steps = 16) => {
  const out = [];
  for (let i = 0; i <= steps; i++) out.push(lob(a, b, height, i / steps).toArray());
  return out;
};
// Le ballon qui passe du sol à ses mains (`k` de 0 à 1), ou l'inverse, sans à-coup.
const lift = (player, how, k, out) => out.lerpVectors(carried(player, "low", new THREE.Vector3()), carried(player, how, new THREE.Vector3()), smooth(k));
const HOLD = pose({ armL: 0.75, armR: 0.75, elL: 1.1, elR: 1.1, abL: -0.15, abR: -0.15, lean: 0.15, y: -0.05, knL: 0.2, knR: 0.2 });

export function buildPressureClear(world, data) {
  const rng = world.rng;
  const s = rng() < 0.5 ? -1 : 1; // le côté de la touche visée (et du ruck)
  const hx = s * (3 + rng() * 6);
  const hz = 92;
  const heroNo = data.hero ?? 10;
  const other = (n, alt) => (n === heroNo ? alt : n);
  const hero = world.player("us", heroNo, { hero: true });
  const feeder = world.player("us", other(9, 7));
  const mate = world.player("us", other(12, 13));
  const wing = world.player("us", s > 0 ? 11 : 14);
  const ruckOurs = world.player("us", 5);
  const ruckTheirs = world.player("them", 3);
  const ref = world.player("ref");
  // Leurs avants arrivent ; leur 7 en tête, face à lui, leur 8 juste derrière.
  const seven = world.player("them", 7);
  const eight = world.player("them", 8);
  const six = world.player("them", 6);
  const pack = [[world.player("them", 4), hx - s * 11, 81], [world.player("them", 2), hx + s * 12, 82]];
  // Loin devant, ceux qui regarderont le ballon sortir.
  const deep = [[world.player("them", 15), [s * (TOUCH - 12), 49], [s * (TOUCH - 6.5), 53.5]], [world.player("them", s > 0 ? 11 : 14), [s * (TOUCH - 6), 45], [s * (TOUCH - 3), 50]]];
  const ruck = [hx + s * 7, 87.5];
  const feederAt = [ruck[0] - s * 0.5, ruck[1] + 1.2];
  const sevenAt = [hx + s * 0.8, 85.8];
  const eightAt = [hx + s * 3.8, 84];
  const sixAt = [hx - s * 6.5, 84.5];
  const mateAt = [hx - s * 5.5, hz + 1];
  const wingAt = [hx - s * 13, hz - 1.5];
  const refAt = [ruck[0] + s * 4.5, ruck[1] + 1.5];
  const ball = new THREE.Vector3();
  const from = new THREE.Vector3();
  const to = new THREE.Vector3();
  const shot = broadcast(hx, hz - 2, { far: 0.95 });
  const camera = keys([
    [0, [hx - 46, 24, hz + 18, hx * 0.6, 0.5, hz - 5, 44]],
    [1.4, [...shot.pos, ...shot.look, shot.fov]],
  ]);
  const passAt = [0.35, 0.85];

  function setupFrame(t) {
    ruckOurs.place(ruck[0], ruck[1] + 0.2, FACE_LINE).set(crouch(0.9));
    ruckTheirs.place(ruck[0] - s * 0.1, ruck[1] - 1.1, FACE_FIELD).set(crouch(0.9));
    feeder.place(feederAt[0], feederAt[1], headingTo(...feederAt, hx, hz)).set(t < passAt[0] ? crouch(1) : pass(span(t, passAt[0] - 0.1, passAt[0] + 0.2), s));
    runner(hero, route([[hx - s * 1, hz + 3.5], [hx, hz]]), t, 0, 1.2, { from: 0.6, to: 0.1, speed: 0.4, carry: t > passAt[1] ? "two" : "none" });
    if (t >= 1.2) hero.place(hx, hz, FACE_LINE).set(HOLD);
    mate.place(...mateAt, FACE_LINE).set(ready(0.4));
    wing.place(...wingAt, FACE_LINE).set(ready(0.3));
    // Ils arrivent à pleine course : huit mètres de plus pendant la mise en place.
    runner(seven, route([[sevenAt[0], sevenAt[1] - 8], sevenAt]), t, 0, 1.4, { from: 1, to: 1, speed: 0.95 });
    runner(eight, route([[eightAt[0], eightAt[1] - 8], eightAt]), t, 0, 1.4, { from: 1, to: 1, speed: 0.9 });
    runner(six, route([[sixAt[0], sixAt[1] - 8], sixAt]), t, 0, 1.4, { from: 1, to: 1, speed: 0.9 });
    pack.forEach(([player, x, z]) => runner(player, route([[x, z - 7], [x, z]]), t, 0, 1.4, { from: 0.9, to: 0.9, speed: 0.8 }));
    ref.place(refAt[0], refAt[1], Math.PI / 2).set(ready(0.1));
    deep.forEach(([player, at]) => player.place(...at, FACE_FIELD).set(ready(0.3)));
    if (t < passAt[0]) world.ballAt(carried(feeder, "low", ball), v(1, 0, 0));
    else if (t < passAt[1]) {
      carried(feeder, "two", from);
      carried(hero, "two", to);
      world.ballAt(lob(from, to, 0.4, span(t, passAt[0], passAt[1]), ball), v(to.x - from.x, 0, to.z - from.z));
    } else world.ballAt(carried(hero, "two", ball), v(1, 0, 0));
    const [cx, cy, cz, lx, ly, lz, fov] = camera(t);
    return { pos: [cx, cy, cz], look: [lx, ly, lz], fov };
  }

  const setup = {
    duration: 1.4,
    frame: setupFrame,
    cues: [{ at: 0.1, run: () => world.crowd("standing") }],
  };

  // Les voies : la touche loin devant, la feinte (un pas de côté), la relance.
  const touchPoint = v(s * (TOUCH + 2.5), 0.4, 54);
  const restPoint = v(s * (TOUCH + 3.2), 0.12, 51.5);
  const stepAside = [hx - s * 1.8, hz + 0.2];
  const runLine = [[hx, hz], [hx - s * 1.6, hz - 2], [hx - s * 3, hz - 7], [hx - s * 3, 66]];
  const wide = { pos: [hx - 36, 30, hz + 8], look: [s * 8, -2, 70], fov: 46 };

  function preview(key) {
    const draw = world.draw;
    const hands = carried(hero, "two", v());
    if (key === "boot") return [draw.arc(ARC(hands, touchPoint, 17)), draw.mark([s * TOUCH, touchPoint.z], 1.2), draw.mark([sevenAt[0], sevenAt[1]], 0.6)];
    if (key === "fake_kick") return [draw.path([[hx, hz], stepAside], { width: 0.35 }), draw.arc(ARC(v(stepAside[0], 1.1, stepAside[1]), touchPoint, 17)), draw.mark([s * TOUCH, touchPoint.z], 1.2)];
    return [draw.path(runLine), draw.mark(runLine[3])];
  }

  // Les autres continuent d'arriver, puis s'arrêtent.
  const packOn = (t, until = 1.5) => {
    pack.forEach(([player, x, z]) => {
      runner(player, route([[x, z], [x + (hx - x) * 0.25, z + 7]]), t, 0, until, { from: 0.9, to: 0.1, speed: 0.75 });
      if (t >= until) player.set(ready(0.3));
    });
  };
  const closeIn = (player, at, t, dx, until = 0.9) => {
    const end = [at[0] + dx, at[1] + 4.5];
    runner(player, route([at, end]), t, 0, until, { from: 1, to: 0.15, speed: 0.85 });
    if (t >= until) player.set(ready(0.4));
  };
  // Vers la touche : la caméra quitte le joueur et rejoint le point de sortie ; leur
  // arrière et leur ailier arrivent, trop tard.
  const touchShot = { pos: [s * (TOUCH - 2) - 26, 11.5, 69], look: [s * (TOUCH - 2), 0.6, 56], fov: 33 };
  const pan = (t, a, b, arrive) => {
    deep.forEach(([player, at, end]) => {
      runner(player, route([at, end]), t, a - 0.2, arrive, { from: 0.4, to: 0.2, speed: 0.75 });
      if (t >= arrive) player.set(t > arrive + 0.4 ? dejected() : ready(0.3));
    });
    const f = smooth(span(t, a, b));
    return {
      pos: shot.pos.map((value, i) => lerp(value, touchShot.pos[i], f)),
      look: shot.look.map((value, i) => lerp(value, touchShot.look[i], f)),
      fov: lerp(shot.fov, touchShot.fov, f),
    };
  };
  const ballToTouch = (t, kickAt, arrive, start) => {
    if (t < arrive) world.ballAt(lob(start, touchPoint, 17, span(t, kickAt, arrive), ball), v(0, 1, 0), (t - kickAt) * 11, v(1, 0, 0));
    else world.ballAt(grubber(touchPoint, restPoint, span(t, arrive, arrive + 0.8), 2, ball), v(1, 0.2, 0.4));
  };

  // --- Taper tout de suite -------------------------------------------------------------------
  function bootOutcome(result) {
    const { success: good, effect } = result;
    if (good) {
      const kickAt = 0.22;
      const arrive = kickAt + 2.2;
      const start = v(hx, 0.9, hz - 0.4);
      const leap = [hx + s * 0.5, hz - 1.7];
      return {
        duration: arrive + 2,
        cues: [
          { at: kickAt, run: () => world.sound("kick") },
          { at: arrive, run: () => (world.sound("whistle"), reaction(world, true)) },
        ],
        frame(t) {
          setupFrame(1.4);
          packOn(t);
          closeIn(eight, eightAt, t, -s * 1.5);
          closeIn(six, sixAt, t, s * 1.5);
          hero.place(hx, hz, headingTo(hx, hz, touchPoint.x, touchPoint.z)).set(mixPose(kick(span(t, 0, kickAt + 0.35)), ready(0.1), smooth(span(t, kickAt + 0.6, kickAt + 1))));
          if (t > arrive + 0.2) hero.set(cheer(t * 1.5));
          // Leur 7 se jette, bras levés : trop tard, le ballon est déjà parti.
          const k = span(t, 0.05, 0.7);
          seven.place(lerp(sevenAt[0], leap[0], smooth(k)), lerp(sevenAt[1], leap[1], smooth(k)), FACE_FIELD).set(k < 1 ? { ...jump(Math.sin(k * Math.PI)), lift: Math.sin(k * Math.PI) * 0.45 } : t > 1.2 ? dejected() : ready(0.3));
          carried(hero, "two", from);
          if (t < kickAt) world.ballAt(ball.copy(from), v(1, 0, 0));
          else ballToTouch(t, kickAt, arrive, start);
          return pan(t, 0.75, arrive + 0.2, arrive);
        },
      };
    }

    // Contré : il frappe, le ballon heurte les bras de leur 7 et repart vers notre ligne.
    const scores = effect === "try_conceded";
    const kickAt = 0.46;
    const hit = 0.56;
    const leap = [hx + s * 0.4, hz - 1.6];
    const firstBounce = v(hx + s * 0.8, 0.12, hz + 3);
    const stop = scores ? v(hx + s * 1.5, 0.12, 100.7) : v(hx + s * 1.3, 0.12, 96.2);
    const settle = scores ? 2.2 : 1.7;
    const tryAt = settle + 0.4;
    const hitPoint = v(leap[0], 2.1, leap[1] + 0.35);
    const foot = v(hx - 0.1, 0.5, hz - 0.45);
    const scorer = scores ? seven : eight;
    const round = [hx + s * 2.1, hz];
    const scorerRoute = scores ? route([leap, round, [stop.x, 99.7]]) : route([eightAt, [stop.x + s * 0.5, stop.z - 0.7]]);
    const scorerGo = scores ? 0.85 : 0.2;
    const tackled = [stop.x + s * 0.3, stop.z - 0.3];
    const stopAt = 2.25;
    const duration = scores ? tryAt + 2.2 : 3.6;
    const refNear = [stop.x + s * 6, 95.5];
    return {
      duration,
      cues: [
        { at: kickAt, run: () => world.sound("kick") },
        { at: hit, run: () => world.sound("impact") },
        { at: hit + 0.15, run: () => world.crowd("standing") },
        scores
          ? { at: tryAt, run: () => (world.sound("whistle", true), reaction(world, false)) }
          : { at: settle + 0.1, run: () => reaction(world, false) },
        ...(!scores ? [{ at: stopAt, run: () => world.sound("impact") }] : []),
      ],
      frame(t) {
        setupFrame(1.4);
        packOn(t);
        if (scores) closeIn(eight, eightAt, t, -s * 1.2);
        closeIn(six, sixAt, t, s * 1.5);
        // Lui : la frappe, puis il se retourne et revient vers sa ligne, sans y arriver.
        const backTo = scores ? [hx - s * 0.6, 97.5] : [tackled[0] - s * 0.5, tackled[1] + 0.5];
        if (t < 0.85) hero.place(hx, hz, FACE_LINE).set(kick(span(t, 0.08, kickAt + 0.3)));
        else {
          runner(hero, route([[hx, hz], backTo]), t, 0.85, scores ? 2.3 : stopAt, { from: 0.3, to: 0.8, speed: 0.85 });
          if (scores && t >= 2.3) hero.set(t > tryAt + 0.3 ? dejected() : ready(0.3));
          if (!scores && t >= stopAt) hero.place(backTo[0], backTo[1], FACE_LINE).set(tackle(span(t, stopAt, stopAt + 0.45)));
        }
        // Leur 7 monte, bras levés, et prend le ballon dans les bras.
        const k = span(t, 0, hit);
        if (t < hit + 0.25) seven.place(lerp(sevenAt[0], leap[0], smooth(k)), lerp(sevenAt[1], leap[1], smooth(k)), FACE_FIELD).set({ ...jump(1), lift: Math.sin(span(t, 0.25, hit + 0.25) * Math.PI) * 0.4 });
        else if (!scores) seven.place(leap[0], leap[1], FACE_FIELD).set(ready(0.3));
        else if (t < scorerGo) seven.place(leap[0], leap[1], FACE_FIELD).set(ready(0.3));
        // Le ramasseur : leur 7 (qui file à l'essai) ou leur 8.
        if (scores) {
          if (t >= scorerGo && t < settle) runner(seven, scorerRoute, t, scorerGo, settle, { from: 0.4, to: 1, speed: 1 });
          else if (t >= settle) {
            const d = span(t, settle, tryAt);
            seven.place(stop.x, lerp(99.7, 100.5, smooth(d)), FACE_FIELD).set(t > tryAt + 0.8 ? cheer(t * 1.6) : dive(d));
          }
        } else {
          runner(eight, scorerRoute, t, scorerGo, settle, { from: 0.8, to: 0.5, speed: 0.9 });
          const spot = [stop.x + s * 0.5, stop.z - 0.7];
          if (t >= settle) {
            const f = span(t, stopAt, stopAt + 0.45);
            eight.place(spot[0], spot[1], FACE_FIELD).set(t < stopAt - 0.25 ? crouch(1) : f < 1 ? tackle(f * 0.6) : ground());
          }
        }
        runner(mate, route([mateAt, [lerp(mateAt[0], stop.x, scores ? 0.2 : 0.65), scores ? 97 : 95.5]]), t, 0.9, 2.6, { from: 0.4, to: 0.2, speed: 0.75 });
        if (t >= 2.6) mate.set(scores ? dejected() : ready(0.4));

        carried(hero, "two", from);
        if (t < 0.34) world.ballAt(ball.copy(from), v(1, 0, 0));
        else if (t < kickAt) world.ballAt(ball.lerpVectors(from, foot, smooth(span(t, 0.34, kickAt))), v(0, 1, 0));
        else if (t < hit) world.ballAt(ball.lerpVectors(foot, hitPoint, span(t, kickAt, hit)), v(0, 1, 0));
        else if (t < hit + 0.55) world.ballAt(lob(hitPoint, firstBounce, 1.4, span(t, hit, hit + 0.55), ball), v(Math.sin(t * 12), 1, Math.cos(t * 12)));
        else if (t < settle) world.ballAt(grubber(firstBounce, stop, span(t, hit + 0.55, settle), 3, ball), v(Math.sin(t * 9), 0.3, 1));
        else if (scores) world.ballAt(t < tryAt ? ball.copy(stop) : carried(seven, "low", ball), v(1, 0, 0));
        else world.ballAt(lift(eight, "two", t < stopAt ? span(t, settle, stopAt) : 1 - span(t, stopAt, stopAt + 0.3), ball), v(1, 0, 0));

        // Arbitre : il accorde l'essai, ou siffle le tenu contre le porteur adverse.
        const rk = span(t, 0.6, scores ? tryAt : stopAt);
        ref.place(lerp(refAt[0], refNear[0], smooth(rk)), lerp(refAt[1], refNear[1], smooth(rk)), Math.PI / 2);
        if (t > tryAt && scores) ref.set(tryAward(smooth(span(t, tryAt, tryAt + 0.35))));
        else if (rk > 0 && rk < 1) ref.set(ready(0.2));

        const f = smooth(span(t, hit, hit + 1));
        // L'action haut dans le cadre : la carte du résultat couvrira le bas.
        return broadcast(lerp(hx, stop.x, f), lerp(hz - 2, 98.5, f), { far: 0.95 });
      },
    };
  }

  // --- Feinter puis taper ---------------------------------------------------------------------
  function fakeOutcome(result) {
    const good = result.success;
    if (good) {
      const kickAt = 1.3;
      const arrive = kickAt + 2.2;
      const start = v(stepAside[0], 0.9, stepAside[1] - 0.4);
      const past = [hx + s * 0.7, hz - 0.5];
      return {
        duration: arrive + 2,
        cues: [
          { at: 0.3, run: () => world.crowd("standing") },
          { at: kickAt, run: () => world.sound("kick") },
          { at: arrive, run: () => (world.sound("whistle"), reaction(world, true)) },
        ],
        frame(t) {
          setupFrame(1.4);
          packOn(t, 2);
          closeIn(eight, eightAt, t, -s * 1.2, 1.4);
          closeIn(six, sixAt, t, s * 1, 1.4);
          const stepping = span(t, 0.35, 0.72);
          if (t < 0.35) hero.place(hx, hz, FACE_LINE).set(kick(span(t, 0, 0.35) * 0.32, true));
          else if (t < kickAt - 0.25) {
            hero.place(lerp(hx, stepAside[0], smooth(stepping)), lerp(hz, stepAside[1], smooth(stepping)), FACE_LINE).set(stepping < 1 ? mixPose(kick(0.32, true), HOLD, smooth(stepping)) : HOLD);
          } else {
            hero.place(stepAside[0], stepAside[1], headingTo(...stepAside, touchPoint.x, touchPoint.z)).set(mixPose(kick(span(t, kickAt - 0.25, kickAt + 0.35)), ready(0.1), smooth(span(t, kickAt + 0.6, kickAt + 1))));
          }
          if (t > arrive + 0.2) hero.set(cheer(t * 1.5));
          // Leur 7 mord : il saute, bras levés, là où le ballon aurait dû partir.
          const k = span(t, 0.22, 0.85);
          seven.place(lerp(sevenAt[0], past[0], smooth(k)), lerp(sevenAt[1], past[1], smooth(k)), FACE_FIELD).set(k < 1 ? { ...jump(1), lift: Math.sin(k * Math.PI) * 0.55 } : t > 1.3 ? dejected() : ready(0.4));
          carried(hero, "two", from);
          if (t < kickAt) world.ballAt(ball.copy(from), v(1, 0, 0));
          else ballToTouch(t, kickAt, arrive, start);
          return pan(t, kickAt + 0.45, arrive + 0.2, arrive);
        },
      };
    }

    // Ils ne mordent pas : leur 7 continue, le prend, et leur 8 ramasse.
    const meet = 0.85;
    const contact = [hx + s * 0.25, hz - 1];
    const spill = v(hx + s * 0.9, 0.12, hz + 1.6);
    const pickSpot = [spill.x + s * 0.5, spill.z - 0.6];
    const pickAt = 1.7;
    const dropped = v(hx + s * 0.3, 0.14, hz + 0.5);
    const duration = 3.5;
    return {
      duration,
      cues: [
        { at: meet, run: () => world.sound("impact") },
        { at: meet + 0.35, run: () => reaction(world, false) },
        { at: pickAt + 0.6, run: () => world.sound("whistle") },
      ],
      frame(t) {
        setupFrame(1.4);
        packOn(t);
        closeIn(six, sixAt, t, s * 2, 1.3);
        const k = span(t, meet, meet + 0.5);
        if (t < meet) hero.place(hx, hz, FACE_LINE).set(kick(Math.min(0.32, span(t, 0, 0.4) * 0.32), true));
        else hero.place(hx, hz + 1.1 * smooth(k), FACE_LINE).set(k < 0.6 ? tackle(k * 0.5) : ground(true));
        if (t < meet) runner(seven, route([sevenAt, contact]), t, 0, meet, { from: 1, to: 0.8, speed: 0.9 });
        else seven.place(contact[0], contact[1] + 1.1 * smooth(k), FACE_FIELD).set(tackle(k));
        runner(eight, route([eightAt, pickSpot]), t, 0.1, pickAt, { from: 0.8, to: 0.4, speed: 0.8 });
        if (t >= pickAt - 0.1) eight.place(pickSpot[0], pickSpot[1], FACE_FIELD).set(t < pickAt + 0.3 ? crouch(1) : HOLD);
        carried(hero, "two", from);
        if (t < meet) world.ballAt(ball.copy(from), v(1, 0, 0));
        else if (t < meet + 0.25) world.ballAt(lob(v(hx, 1.12, hz - 0.42), dropped, 0.2, span(t, meet, meet + 0.25), ball), v(1, 0.3, 0));
        else if (t < pickAt) world.ballAt(grubber(dropped, spill, span(t, meet + 0.25, pickAt), 2, ball), v(1, 0.3, Math.sin(t * 8)));
        else world.ballAt(lift(eight, "two", span(t, pickAt, pickAt + 0.3), ball), v(1, 0, 0));
        runner(mate, route([mateAt, [hx - s * 2.2, hz + 3.6]]), t, 0.5, 2.1, { from: 0.4, to: 0.1, speed: 0.6 });
        if (t >= 2.1) mate.set(dejected());
        // L'arbitre s'approche, bras vers leur attaque (+z) : le ballon est pour eux.
        const rk = span(t, 1, 2.1);
        const near = [spill.x + s * 6, hz - 1];
        ref.place(lerp(refAt[0], near[0], smooth(rk)), lerp(refAt[1], near[1], smooth(rk)), Math.PI / 2);
        if (t > 2.1) ref.set(signal(-1, smooth(span(t, 2.1, 2.4))));
        return broadcast(hx, lerp(hz - 2, hz + 2.5, smooth(span(t, 0.5, 1.6))), { far: lerp(0.95, 0.92, smooth(span(t, 0.5, 1.6))) });
      },
    };
  }

  // --- Relancer à la main --------------------------------------------------------------------
  function runOutcome(result) {
    const { success: good, effect } = result;
    if (good) {
      const duration = 3.4;
      const heroRun = route(runLine);
      const diveSeven = [hx - s * 0.5, hz - 3.3];
      const diveSix = [hx - s * 4.5, 85];
      return {
        duration,
        cues: [
          { at: 0.6, run: () => world.crowd("standing") },
          { at: 2.05, run: () => reaction(world, true) },
        ],
        frame(t) {
          setupFrame(1.4);
          runner(hero, heroRun, t, 0, duration, { from: 0.55, to: 1, speed: 1, carry: t > 0.45 ? "one" : "two" });
          world.ballAt(carried(hero, t > 0.45 ? "one" : "two", ball), v(0, 0, 1));
          // Ils plongent dans le vide, l'un puis l'autre.
          const a = span(t, 0.42, 0.85);
          if (t < 0.42) runner(seven, route([sevenAt, diveSeven]), t, 0, 0.42, { speed: 0.95 });
          else seven.place(diveSeven[0], diveSeven[1] + a * 0.7, FACE_FIELD + s * 0.5).set(a < 1 ? tackle(a) : ground());
          const b = span(t, 0.82, 1.25);
          if (t < 0.82) runner(six, route([sixAt, diveSix]), t, 0, 0.82, { speed: 0.9 });
          else six.place(diveSix[0], diveSix[1] + b * 0.7, FACE_FIELD - s * 0.5).set(b < 1 ? tackle(b) : ground());
          // Le soutien file à sa hauteur, le deux contre un se prépare.
          runner(mate, route([mateAt, [hx - s * 7.2, 84], [hx - s * 7.5, 67]]), t, 0.05, duration, { from: 0.55, to: 1, speed: 0.95 });
          runner(wing, route([wingAt, [wingAt[0], 71]]), t, 0.2, duration, { from: 0.45, to: 0.9, speed: 0.85 });
          // Les autres se retournent et lui courent après, trop tard.
          runner(eight, route([eightAt, [eightAt[0], eightAt[1] + 2], [eightAt[0] - s * 3, 70]]), t, 0.3, duration, { from: 0.3, to: 0.9, speed: 0.8 });
          pack.forEach(([player, x, z], i) => runner(player, route([[x, z], [x, z + 1], [x + (hx - x) * 0.3, 66 + i * 2]]), t, 0.5, duration, { from: 0.3, to: 0.8, speed: 0.75 }));
          runner(ref, route([refAt, [refAt[0], 69]]), t, 0.4, duration, { from: 0.4, to: 0.8, speed: 0.65 });
          const focus = hero.root.position;
          return broadcast(focus.x, focus.z - 3);
        },
      };
    }

    // Pris dans ses 22, repoussé vers sa ligne ; le ballon s'échappe derrière lui.
    const scores = effect === "try_conceded";
    const meet = 0.62;
    const caught = [hx - s * 1.5, hz - 2.4];
    const spill = v(hx - s * 0.5, 0.12, hz + 1);
    const dropped = v(caught[0] + s * 0.3, 0.14, caught[1] + 1.6);
    const pick = [spill.x + s * 0.5, spill.z - 0.5];
    const pickAt = 1.5;
    const goAt = pickAt + 0.28;
    const lineSpot = [pick[0] + s * 1.5, 99.7];
    const tryRun = route([pick, lineSpot]);
    const reachAt = goAt + tryRun.total / 7.5;
    const tryAt = reachAt + 0.42;
    const stopAt = 2.25;
    const duration = scores ? tryAt + 2.1 : 3.6;
    const refNear = scores ? [lineSpot[0] + s * 6, 96] : [pick[0] + s * 6, hz];
    return {
      duration,
      cues: [
        { at: meet, run: () => world.sound("impact") },
        { at: meet + 0.4, run: () => reaction(world, false) },
        ...(scores ? [{ at: tryAt, run: () => (world.sound("whistle", true), reaction(world, false)) }] : [{ at: stopAt, run: () => world.sound("impact") }, { at: stopAt + 0.4, run: () => world.sound("whistle") }]),
      ],
      frame(t) {
        setupFrame(1.4);
        packOn(t);
        closeIn(six, sixAt, t, s * 2, 1.2);
        const k = span(t, meet, meet + 0.55);
        if (t < meet) runner(hero, route([[hx, hz], caught]), t, 0, meet, { from: 0.55, to: 0.85, speed: 0.85, carry: "two" });
        else hero.place(caught[0], caught[1] + 1.5 * smooth(k), FACE_LINE).set(k < 0.6 ? tackle(k * 0.5) : ground(true));
        if (t < meet) runner(seven, route([sevenAt, [caught[0] + s * 0.1, caught[1] - 0.9]]), t, 0, meet, { from: 1, to: 0.8, speed: 0.9 });
        else seven.place(caught[0] + s * 0.1, caught[1] - 0.9 + 1.5 * smooth(k), FACE_FIELD).set(tackle(k));

        runner(eight, route([eightAt, pick]), t, 0.05, pickAt, { from: 0.8, to: 0.4, speed: 0.85 });
        if (t >= pickAt && t < goAt) eight.place(pick[0], pick[1], FACE_FIELD).set(crouch(1));
        if (scores) {
          if (t >= goAt && t < reachAt) runner(eight, tryRun, t, goAt, reachAt, { from: 0.5, to: 1, speed: 1, carry: "two" });
          else if (t >= reachAt) {
            const d = span(t, reachAt, tryAt);
            eight.place(lineSpot[0], lerp(lineSpot[1], 100.5, smooth(d)), FACE_FIELD).set(t > tryAt + 0.8 ? cheer(t * 1.6) : dive(d));
          }
          runner(mate, route([mateAt, [lineSpot[0] - s * 3, 96.5]]), t, 0.5, reachAt, { from: 0.4, to: 0.7, speed: 0.8 });
          if (t >= reachAt) mate.set(dejected());
        } else {
          // Notre 12 le plaque aussitôt, à sept mètres de la ligne.
          if (t >= goAt && t < stopAt) eight.place(pick[0], pick[1], FACE_FIELD).set(HOLD);
          const f = span(t, stopAt, stopAt + 0.45);
          if (t >= stopAt) eight.place(pick[0], pick[1] - 0.3 * smooth(f), FACE_FIELD).set(f < 1 ? tackle(f * 0.6) : ground());
          const hit = [pick[0] - s * 0.1, pick[1] + 0.9];
          runner(mate, route([mateAt, hit]), t, 0.6, stopAt, { from: 0.4, to: 1, speed: 0.85 });
          if (t >= stopAt) mate.place(hit[0], hit[1], FACE_LINE).set(tackle(f));
        }

        if (t < meet) world.ballAt(carried(hero, "two", ball), v(1, 0, 0));
        else if (t < meet + 0.25) world.ballAt(lob(v(caught[0], 1.12, caught[1] - 0.42), dropped, 0.2, span(t, meet, meet + 0.25), ball), v(1, 0.3, 0));
        else if (t < pickAt) world.ballAt(grubber(dropped, spill, span(t, meet + 0.25, pickAt), 2, ball), v(1, 0.3, Math.sin(t * 8)));
        else if (t < goAt) world.ballAt(lift(eight, "two", span(t, pickAt, goAt), ball), v(1, 0, 0));
        else if (scores) world.ballAt(lift(eight, "two", 1 - span(t, reachAt, reachAt + 0.25), ball), v(1, 0, 0));
        else world.ballAt(lift(eight, "two", 1 - span(t, stopAt, stopAt + 0.3), ball), v(1, 0, 0));

        const rk = span(t, 0.8, scores ? tryAt : stopAt + 0.4);
        ref.place(lerp(refAt[0], refNear[0], smooth(rk)), lerp(refAt[1], refNear[1], smooth(rk)), Math.PI / 2);
        if (scores && t > tryAt) ref.set(tryAward(smooth(span(t, tryAt, tryAt + 0.35))));

        const f = smooth(span(t, 0.3, 1.4));
        const end = scores ? smooth(span(t, goAt, reachAt)) : 0;
        return broadcast(lerp(hx, scores ? lineSpot[0] : pick[0], Math.max(f * 0.6, end)), lerp(lerp(hz - 2, 95.5, f), 98.5, end), { far: 0.93 });
      },
    };
  }

  return {
    setup,
    preview,
    previewShot: (key) => (key === "run_out" ? null : wide),
    outcome(key, result) {
      if (key === "boot") return bootOutcome(result);
      if (key === "fake_kick") return fakeOutcome(result);
      return runOutcome(result);
    },
  };
}
