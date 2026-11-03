import * as THREE from "three";

import { TOUCH } from "../field.js";
import { cheer, crouch, dejected, ground, jump, kick, mixPose, pass, pose, ready, run, signal, tackle } from "../rig.js";
import { FACE_FIELD, FACE_LINE, broadcast, carried, grubber, headingTo, keys, lerp, lob, reaction, route, runner, smooth, span } from "./common.js";

// Carrière de joueur, « Le 50-22 » (fifty_22) : le joueur incarné a le ballon dans son
// camp (z > 50), leur ailier est monté, son couloir est ouvert. Le 50-22 (le ballon
// rebondit et sort dans leurs 22 ; raté, il reste en jeu et leur arrière récupère), le
// coup de pied long et sûr (raté : trop court, attrapé par leur ailier, qui relance si
// l'effet est `lost`, sinon il est pris aussitôt), ou le jeu à la main (on perce au
// large ; raté : passe en avant).

const v = (x = 0, y = 0, z = 0) => new THREE.Vector3(x, y, z);
const ARC = (a, b, height, steps = 16) => {
  const out = [];
  for (let i = 0; i <= steps; i++) out.push(lob(a, b, height, i / steps).toArray());
  return out;
};
// Le ballon qui passe du sol à ses mains (`k` de 0 à 1), ou l'inverse, sans à-coup.
const lift = (player, how, k, out) => out.lerpVectors(carried(player, "low", new THREE.Vector3()), carried(player, how, new THREE.Vector3()), smooth(k));
const HOLD = pose({ armL: 0.75, armR: 0.75, elL: 1.1, elR: 1.1, abL: -0.15, abR: -0.15, lean: 0.15, y: -0.05, knL: 0.2, knR: 0.2 });
const CATCH = { ...jump(0.6), armL: 1.5, armR: 1.5, elL: 1.2, elR: 1.2 };

export function buildFifty22(world, data) {
  const rng = world.rng;
  const s = rng() < 0.5 ? -1 : 1; // le couloir ouvert, du côté de leur ailier monté
  const hx = -s * 4;
  const hz = 60;
  const heroNo = data.hero ?? 10;
  const other = (n, alt) => (n === heroNo ? alt : n);
  const hero = world.player("us", heroNo, { hero: true });
  const feeder = world.player("us", other(9, 7));
  const twelve = world.player("us", other(12, 13));
  const thirteen = world.player("us", other(13, 12));
  const ourWing = world.player("us", s > 0 ? 14 : 11);
  const ruckOurs = world.player("us", 4);
  const ruckTheirs = world.player("them", 6);
  const line = [[10, -2.5], [12, 3], [13, 9], [7, 14.5]].map(([n, dx]) => ({ player: world.player("them", n), x: hx + s * dx }));
  const theirWing = world.player("them", s > 0 ? 11 : 14);
  const fullback = world.player("them", 15);
  const ref = world.player("ref");

  const ruck = [hx - s * 6, 63.5];
  const feederAt = [ruck[0] + s * 0.5, ruck[1] + 1.2];
  const lineZ = 52.5;
  const wingUp = [s * 26, 49];
  const fullbackAt = [s * 8, 17];
  const refAt = [ruck[0] - s * 5, ruck[1] - 3];
  const spots = {
    twelve: [hx + s * 6, hz + 1.2],
    thirteen: [hx + s * 12, hz + 2.2],
    wing: [s * 18, hz + 3],
  };
  const ball = new THREE.Vector3();
  const from = new THREE.Vector3();
  const to = new THREE.Vector3();
  // De derrière son épaule : lui, leur ligne qui monte, et le couloir vide au fond.
  const shot = { pos: [hx - s * 9, 13, hz + 20], look: [hx + s * 9, 0.5, hz - 13], fov: 38 };
  const camera = keys([
    [0, [hx - s * 16, 22, hz + 32, hx + s * 8, 0.5, hz - 12, 44]],
    [1.3, [...shot.pos, ...shot.look, shot.fov]],
  ]);
  const passAt = [0.3, 0.7];

  function setupFrame(t) {
    ruckOurs.place(ruck[0], ruck[1] + 0.2, FACE_LINE).set(crouch(0.9));
    ruckTheirs.place(ruck[0] + s * 0.1, ruck[1] - 1.1, FACE_FIELD).set(crouch(0.9));
    feeder.place(feederAt[0], feederAt[1], headingTo(...feederAt, hx, hz)).set(t < passAt[0] ? crouch(1) : pass(span(t, passAt[0] - 0.1, passAt[0] + 0.2), -s));
    runner(hero, route([[hx - s * 1, hz + 4], [hx, hz]]), t, 0, 1.3, { from: 0.6, to: 0.3, speed: 0.45, carry: t > passAt[1] ? "two" : "none" });
    if (t >= 1.3) hero.place(hx, hz, FACE_LINE).set(HOLD);
    runner(twelve, route([[spots.twelve[0], spots.twelve[1] + 3], spots.twelve]), t, 0, 1.3, { from: 0.5, to: 0.4, speed: 0.45 });
    runner(thirteen, route([[spots.thirteen[0], spots.thirteen[1] + 3], spots.thirteen]), t, 0, 1.3, { from: 0.5, to: 0.4, speed: 0.45 });
    runner(ourWing, route([[spots.wing[0], spots.wing[1] + 3], spots.wing]), t, 0, 1.3, { from: 0.5, to: 0.4, speed: 0.45 });
    // Leur ligne monte d'un bloc, l'ailier en tête : derrière lui, plus personne.
    line.forEach(({ player, x }) => runner(player, route([[x, lineZ - 4], [x, lineZ]]), t, 0, 1.3, { from: 0.8, to: 0.9, speed: 0.75 }));
    runner(theirWing, route([[wingUp[0] + s * 0.5, wingUp[1] - 5], wingUp]), t, 0, 1.3, { from: 0.8, to: 0.9, speed: 0.8 });
    fullback.place(...fullbackAt, FACE_FIELD).set(ready(0.3));
    ref.place(refAt[0], refAt[1], Math.PI / 2).set(ready(0.1));
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
    duration: 1.3,
    frame: setupFrame,
    cues: [{ at: 0.1, run: () => world.crowd(world.pressure > 1 ? "standing" : "seated") }],
  };

  // Le 50-22 : il rebondit dans le couloir, et sort dans leurs 22 (z < 22).
  const land = [s * (TOUCH - 7), 30];
  const outPoint = v(s * (TOUCH + 2.5), 0.12, 15);
  const crossZ = 18.3;
  const longLand = v(s * 5, 1.12, 14.5);
  const shortLand = v(s * 15, 1.12, 41);
  const wide = { pos: [hx - s * 14, 36, hz + 22], look: [s * 8, 0, 36], fov: 50 };
  const breakLine = [spots.wing, [s * 19.5, 52], [s * 20.5, 38]];

  function preview(key) {
    const draw = world.draw;
    const hands = carried(hero, "two", v());
    if (key === "fifty") {
      return [draw.arc(ARC(hands, v(land[0], 0.2, land[1]), 13)), draw.path([land, [s * TOUCH, crossZ]]), draw.mark([s * TOUCH, crossZ], 1.2)];
    }
    if (key === "long_kick") return [draw.arc(ARC(hands, longLand, 20)), draw.mark([longLand.x, longLand.z], 1.2)];
    const arcs = [
      draw.arc(ARC(hands, carried(twelve, "two", v()), 0.35, 8), 0.08),
      draw.arc(ARC(carried(twelve, "two", v()), carried(thirteen, "two", v()), 0.35, 8), 0.08),
      draw.arc(ARC(carried(thirteen, "two", v()), carried(ourWing, "two", v()), 0.35, 8), 0.08),
    ];
    return [...arcs, draw.path(breakLine), draw.mark(breakLine[2])];
  }

  // Les défenseurs finissent leur montée, puis regardent.
  const pressOn = (t, until = 1.1) => {
    line.forEach(({ player, x }) => {
      runner(player, route([[x, lineZ], [x, lineZ + 3.5]]), t, 0, until, { from: 0.9, to: 0.1, speed: 0.75 });
      if (t >= until) player.set(ready(0.3));
    });
  };
  const kicking = (t, kickAt, aim) => {
    hero.place(hx, hz, headingTo(hx, hz, aim[0], aim[1])).set(mixPose(kick(span(t, kickAt - 0.2, kickAt + 0.35)), ready(0.1), smooth(span(t, kickAt + 0.55, kickAt + 0.95))));
  };
  const ballFromHands = (t, kickAt, target, height, arrive) => {
    carried(hero, "two", from);
    if (t < kickAt) world.ballAt(ball.copy(from), v(1, 0, 0));
    else if (t < arrive) world.ballAt(lob(v(hx, 0.9, hz - 0.3), target, height, span(t, kickAt, arrive), ball), v(0, 1, 0), (t - kickAt) * 11, v(1, 0, 0));
  };
  // La caméra, de l'épaule du joueur jusqu'au point de chute.
  const followTo = (t, a, b, target) => {
    const f = smooth(span(t, a, b));
    return {
      pos: shot.pos.map((value, i) => lerp(value, target.pos[i], f)),
      look: shot.look.map((value, i) => lerp(value, target.look[i], f)),
      fov: lerp(shot.fov, target.fov, f),
    };
  };

  // --- Le 50-22 ---------------------------------------------------------------------------
  function fiftyOutcome(result) {
    const good = result.success;
    const kickAt = 0.3;
    const landAt = kickAt + 2;
    const rollEnd = landAt + 1.3;
    const landing = v(land[0], 0.12, land[1]);
    // Raté : il reste en jeu, et leur arrière arrive avant la touche.
    const stay = v(s * (TOUCH - 2.5), 0.12, 21);
    const gather = [stay.x - s * 0.4, stay.z - 0.6];
    const outAt = landAt + 0.64 * (rollEnd - landAt);
    const pickAt = rollEnd + 0.05;
    const duration = good ? rollEnd + 1.9 : pickAt + 1.7;
    const view = broadcast(s * (TOUCH - 7), 21, { far: 1.05, fov: 33 });
    return {
      duration,
      cues: [
        { at: kickAt, run: () => world.sound("kick") },
        { at: landAt, run: () => world.crowd("standing") },
        good
          ? { at: outAt, run: () => (world.sound("whistle"), reaction(world, true)) }
          : { at: pickAt, run: () => reaction(world, false) },
      ],
      frame(t) {
        setupFrame(1.3);
        pressOn(t);
        kicking(t, kickAt, land);
        // Leur ailier se retourne et court après le ballon, sans jamais l'avoir.
        runner(theirWing, route([wingUp, [s * 31, 26]]), t, 0.45, rollEnd, { from: 0.3, to: 0.8, speed: 0.95 });
        if (t > rollEnd + 0.6) theirWing.set(good ? dejected() : ready(0.2));
        runner(ourWing, route([spots.wing, [s * 29, 33]]), t, 0.4, duration, { from: 0.4, to: 0.6, speed: 0.85 });
        if (good) {
          runner(fullback, route([fullbackAt, [s * 30, 15.5]]), t, 0.5, rollEnd, { from: 0.3, to: 0.3, speed: 0.9 });
          if (t >= rollEnd) fullback.place(s * 30, 15.5, FACE_FIELD).set(t > rollEnd + 0.4 ? dejected() : ready(0.3));
        } else {
          runner(fullback, route([fullbackAt, gather]), t, 0.5, pickAt, { from: 0.4, to: 0.5, speed: 0.95 });
          if (t >= pickAt) {
            if (t < pickAt + 0.3) fullback.place(gather[0], gather[1], FACE_FIELD).set(crouch(1));
            else runner(fullback, route([gather, [s * 25, 33]]), t, pickAt + 0.3, duration, { from: 0.3, to: 0.9, speed: 0.85, carry: "one" });
          }
        }
        if (t > outAt + 0.3 && good) hero.set(cheer(t * 1.6));
        else if (t > pickAt + 0.3 && !good) hero.set(dejected());
        ballFromHands(t, kickAt, landing, 13, landAt);
        if (t >= landAt) {
          if (good) world.ballAt(grubber(landing, outPoint, span(t, landAt, rollEnd), 4, ball), v(1, 0.3, Math.sin(t * 9)));
          else if (t < pickAt) world.ballAt(grubber(landing, stay, span(t, landAt, pickAt), 4, ball), v(1, 0.3, Math.sin(t * 9)));
          else world.ballAt(lift(fullback, "one", span(t, pickAt, pickAt + 0.3), ball), v(0, 0, 1));
        }
        return followTo(t, kickAt + 0.1, landAt + 0.25, view);
      },
    };
  }

  // --- Long et sûr --------------------------------------------------------------------------
  function longOutcome(result) {
    const { success: good, effect } = result;
    const kickAt = 0.3;
    const target = good ? longLand : shortLand;
    const arrive = kickAt + (good ? 2.7 : 1.6);
    const catcher = good ? fullback : theirWing;
    const catchAt = [target.x, target.z - 0.42];
    const start = good ? fullbackAt : wingUp;
    // Trop court : leur ailier relance (`lost`), ou notre 12 le prend aussitôt.
    const breaks = !good && effect === "lost";
    const meet = [catchAt[0] + s * 0.3, catchAt[1] + 4];
    const meetAt = arrive + 1;
    const duration = good ? arrive + 1.8 : breaks ? arrive + 1.9 : meetAt + 1.3;
    const view = good ? broadcast(s * 6, 19, { fov: 33 }) : broadcast(s * 13, 44, { far: 0.95, fov: 33 });
    return {
      duration,
      cues: [
        { at: kickAt, run: () => world.sound("kick") },
        { at: arrive, run: () => reaction(world, good) },
        ...(!good && !breaks ? [{ at: meetAt, run: () => world.sound("impact") }] : []),
      ],
      frame(t) {
        setupFrame(1.3);
        pressOn(t);
        kicking(t, kickAt, [target.x, target.z]);
        runner(catcher, route([start, catchAt]), t, 0.2, arrive - 0.25, { from: 0.4, to: 0.1, speed: 0.75 });
        if (t >= arrive - 0.25) catcher.place(catchAt[0], catchAt[1], FACE_FIELD).set(CATCH);
        if (good) {
          // Les nôtres montent : il est loin de tout, et il va devoir la jouer d'ici.
          if (t > arrive + 0.3) fullback.set(HOLD);
          runner(ourWing, route([spots.wing, [s * 10, 25]]), t, 0.4, duration, { from: 0.5, to: 0.9, speed: 0.9 });
          runner(twelve, route([spots.twelve, [s * 3, 30]]), t, 0.5, duration, { from: 0.4, to: 0.8, speed: 0.8 });
          if (t > arrive + 0.4) hero.set(run(t * 2, 0.15));
        } else if (breaks) {
          if (t >= arrive) runner(catcher, route([catchAt, [s * 21, 62]]), t, arrive, duration, { from: 0.3, to: 1, speed: 0.95, carry: "one" });
          runner(twelve, route([spots.twelve, [s * 14, 52]]), t, 0.5, duration, { from: 0.4, to: 0.6, speed: 0.75 });
          if (t > arrive + 0.5) hero.set(dejected());
        } else {
          // Il remonte de quelques mètres, notre 12 le plaque.
          if (t >= arrive && t < meetAt) runner(catcher, route([catchAt, meet]), t, arrive, meetAt, { from: 0.3, to: 0.7, speed: 0.6, carry: "one" });
          runner(twelve, route([spots.twelve, [meet[0] - s * 0.2, meet[1] + 0.9]]), t, 0.5, meetAt, { from: 0.4, to: 1, speed: 0.9 });
          if (t >= meetAt) {
            const k = span(t, meetAt, meetAt + 0.45);
            catcher.place(meet[0], meet[1] + 0.4 * smooth(k) * -1, FACE_FIELD).set(k < 1 ? tackle(k * 0.6) : ground());
            twelve.place(meet[0] - s * 0.2, meet[1] + 0.9, FACE_LINE).set(tackle(k));
          }
        }
        ballFromHands(t, kickAt, target, good ? 20 : 11, arrive);
        if (t >= arrive) {
          if (good || t < arrive + 0.05) world.ballAt(carried(catcher, "two", ball), v(1, 0, 0));
          else if (!breaks && t >= meetAt) world.ballAt(lift(catcher, "one", 1 - span(t, meetAt, meetAt + 0.3), ball), v(1, 0, 0));
          else world.ballAt(carried(catcher, "one", ball), v(0, 0, 1));
        }
        return followTo(t, kickAt + 0.1, Math.min(arrive, kickAt + 1.8), view);
      },
    };
  }

  // --- À la main ----------------------------------------------------------------------------
  function handsOutcome(result) {
    const good = result.success;
    const out = [0.2, 0.55];
    const second = [0.95, 1.25];
    const third = [1.6, 2];
    const duration = good ? 4 : 2.9;
    const fall = v(spots.twelve[0] + s * 0.3, 0.12, spots.twelve[1] - 3.6);
    const rolled = v(fall.x + s * 0.6, 0.12, fall.z - 1.8);
    const twelveRun = route([spots.twelve, [spots.twelve[0] + s * 0.6, spots.twelve[1] - 4.5]]);
    const thirteenRun = route([spots.thirteen, [spots.thirteen[0] + s * 0.8, spots.thirteen[1] - 5.5]]);
    const wingRun = route(breakLine);
    const beaten = [s * 22.2, 50.5];
    const whistleAt = 0.85;
    return {
      duration,
      cues: good
        ? [
            { at: third[0], run: () => world.crowd("standing") },
            { at: 2.7, run: () => reaction(world, true) },
          ]
        : [
            { at: whistleAt, run: () => world.sound("whistle") },
            { at: whistleAt + 0.1, run: () => reaction(world, false) },
          ],
      frame(t) {
        setupFrame(1.3);
        pressOn(t, 1.2);
        hero.place(hx, hz, FACE_LINE).set(t < out[0] + 0.25 ? pass(span(t, out[0] - 0.1, out[0] + 0.2), -s) : ready(0.2));
        carried(hero, "two", from);
        if (good) {
          runner(hero, route([[hx, hz], [hx + s * 2.5, hz - 3]]), t, out[0] + 0.4, duration, { from: 0.3, to: 0.6, speed: 0.55 });
          runner(twelve, twelveRun, t, 0, second[0] + 0.3, { from: 0.6, to: 0.7, speed: 0.75, carry: t > out[1] ? "two" : "none" });
          if (t > second[0] - 0.1 && t < second[0] + 0.25) twelve.set(pass(span(t, second[0] - 0.1, second[0] + 0.2), -s));
          runner(thirteen, thirteenRun, t, 0.2, third[0] + 0.3, { from: 0.6, to: 0.8, speed: 0.8, carry: t > second[1] ? "two" : "none" });
          if (t > third[0] - 0.1 && t < third[0] + 0.25) thirteen.set(pass(span(t, third[0] - 0.1, third[0] + 0.2), -s));
          runner(ourWing, wingRun, t, 0.8, duration, { from: 0.5, to: 1, speed: 1, carry: t > third[1] + 0.3 ? "one" : t > third[1] ? "two" : "none" });
          // Leur ailier a serré, il plonge trop tard : le couloir est à nous.
          const dive = span(t, 2.05, 2.5);
          if (t < 2.05) runner(theirWing, route([wingUp, beaten]), t, 0.5, 2.05, { from: 0.8, to: 0.9, speed: 0.8 });
          else theirWing.place(beaten[0] - s * 0.5 * dive, beaten[1] + 0.3 * dive, FACE_FIELD - s * 0.5).set(dive < 1 ? tackle(dive) : ground());
          if (t < out[0]) world.ballAt(ball.copy(from), v(1, 0, 0));
          else if (t < out[1]) world.ballAt(lob(from, carried(twelve, "two", to), 0.3, span(t, ...out), ball), v(1, 0, 0));
          else if (t < second[0]) world.ballAt(carried(twelve, "two", ball), v(1, 0, 0));
          else if (t < second[1]) world.ballAt(lob(carried(twelve, "two", from), carried(thirteen, "two", to), 0.3, span(t, ...second), ball), v(1, 0, 0));
          else if (t < third[0]) world.ballAt(carried(thirteen, "two", ball), v(1, 0, 0));
          else if (t < third[1]) world.ballAt(lob(carried(thirteen, "two", from), carried(ourWing, "two", to), 0.3, span(t, ...third), ball), v(1, 0, 0));
          else world.ballAt(carried(ourWing, t > third[1] + 0.3 ? "one" : "two", ball), v(0, 0, 1));
          if (t > 2.9) hero.set(run(t * 2.2, 0.5));
        } else {
          // La passe part devant lui, tombe et rebondit : en-avant.
          runner(twelve, twelveRun, t, 0, 0.8, { from: 0.6, to: 0.2, speed: 0.6 });
          if (t >= 0.8) twelve.set(t > whistleAt + 0.3 ? dejected() : ready(0.4));
          if (t < out[0]) world.ballAt(ball.copy(from), v(1, 0, 0));
          else if (t < 0.72) world.ballAt(lob(from, fall, 0.5, span(t, out[0], 0.72), ball), v(1, 0.2, 0));
          else if (t < 1.4) world.ballAt(grubber(fall, rolled, span(t, 0.72, 1.4), 2, ball), v(Math.sin(t * 10), 0.3, 1));
          else world.ballAt(ball.copy(rolled), v(1, 0, 0.3));
          if (t > whistleAt + 0.3) hero.set(dejected());
          // L'arbitre accourt, le bras vers leur attaque (+z), la mêlée sera pour eux.
          const rk = span(t, whistleAt - 0.25, whistleAt + 0.6);
          const near = [fall.x - s * 4.5, fall.z - 1];
          ref.place(lerp(refAt[0], near[0], smooth(rk)), lerp(refAt[1], near[1], smooth(rk)), Math.PI / 2);
          if (t > whistleAt - 0.25) ref.set(rk < 1 ? run(t * 3, 0.5) : signal(-1, smooth(span(t, whistleAt + 0.6, whistleAt + 0.9))));
        }
        const f = smooth(span(t, 0.1, 1));
        const focus = good ? ball : fall;
        const view = broadcast(lerp(hx + s * 2, focus.x, good ? f : 0.7 * f), lerp(hz - 2, focus.z, f), { far: lerp(1.05, 1, f) });
        return followTo(t, 0, 0.8, view);
      },
    };
  }

  return {
    setup,
    preview,
    previewShot: () => wide,
    outcome(key, result) {
      if (key === "fifty") return fiftyOutcome(result);
      if (key === "long_kick") return longOutcome(result);
      return handsOutcome(result);
    },
  };
}
