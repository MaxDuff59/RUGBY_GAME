import * as THREE from "three";

import { cheer, crouch, dejected, ground, jump, kick, mixPose, pass, pose, ready, run, signal, tackle } from "../rig.js";
import { FACE_FIELD, FACE_LINE, broadcast, carried, grubber, headingTo, keys, lerp, lob, penaltyAgainst, reaction, route, runner, smooth, span } from "./common.js";

// Carrière de joueur, « Le dégagement adverse » (charge_down) : leur demi va dégager au
// pied depuis son camp, le joueur incarné arrive lancé. Charger (contré : le ballon
// rebondit pour lui, il le ramasse en pleine course et l'action s'enchaîne sur la
// contre-attaque), couper la ligne de passe (il tape mal, ou trouve son ouvreur dans le
// dos du joueur), ou rester en couverture (à sa place, ou en retard).
//
// Les échecs suivent l'effet tiré. Charger : `penalty_conceded` (il le percute après la
// frappe : pénalité), sinon le ballon file. Couper : `missed` (l'ouvreur file, le
// plaquage manque), sinon l'ouvreur dégage tranquillement.

const v = (x = 0, y = 0, z = 0) => new THREE.Vector3(x, y, z);
const ARC = (a, b, height, steps = 12) => {
  const out = [];
  for (let i = 0; i <= steps; i++) out.push(lob(a, b, height, i / steps).toArray());
  return out;
};
// Le ballon qui passe du sol à ses mains (`k` de 0 à 1), ou l'inverse, sans à-coup.
const lift = (player, how, k, out) => out.lerpVectors(carried(player, "low", new THREE.Vector3()), carried(player, how, new THREE.Vector3()), smooth(k));
const HOLD = pose({ armL: 0.75, armR: 0.75, elL: 1.1, elR: 1.1, abL: -0.15, abR: -0.15, lean: 0.15, y: -0.05, knL: 0.2, knR: 0.2 });

export function buildChargeDown(world, data) {
  const rng = world.rng;
  const s = rng() < 0.5 ? -1 : 1; // le côté du ruck ; le joueur incarné arrive à l'opposé
  const rx = s * (3 + rng() * 7);
  const rz = 30;
  const heroNo = data.hero ?? 7;
  const other = (n, alt) => (n === heroNo ? alt : n);
  const hero = world.player("us", heroNo, { hero: true });
  const mate = world.player("us", other(7, 6));
  const twelve = world.player("us", 12);
  const thirteen = world.player("us", 13);
  const fifteen = world.player("us", 15); // loin derrière, sous le dégagement
  const ruckOurs = world.player("us", 4);
  const ruckTheirs = [world.player("them", 4), world.player("them", 5)];
  const nine = world.player("them", 9);
  const ten = world.player("them", 10);
  const wings = [world.player("them", 13), world.player("them", 14)];
  const ref = world.player("ref");

  const nineAt = [rx - s * 2, rz - 2.6];
  const heroEnd = [rx - s * 3.5, 33];
  const heroStart = [rx - s * 6, 43];
  const mateEnd = [rx + s * 3.5, 35.5];
  const tenAt = [rx - s * 10.5, 23];
  const wingsAt = [[rx - s * 16, 25.5], [rx + s * 11, 26.5]];
  const twelveEnd = [rx + s * 3, 43];
  const thirteenEnd = [rx - s * 11, 42.5];
  const fifteenAt = [rx * 0.3 + s * 3, 58];
  const refAt = [rx + 8, rz + 3];
  const ballOnGround = v(rx - s * 0.1, 0.12, rz - 1.5);
  const ball = new THREE.Vector3();
  const from = new THREE.Vector3();
  const to = new THREE.Vector3();
  const shot = broadcast(rx - s * 2, 31, { far: 0.9 });
  const camera = keys([
    [0, [rx - 52, 25, 55, rx * 0.6, 0.5, 33, 44]],
    [1.3, [...shot.pos, ...shot.look, shot.fov]],
  ]);
  const pickAt = 0.7;

  function setupFrame(t) {
    // Le ruck : deux des leurs liés, un des nôtres en face.
    ruckTheirs[0].place(rx, rz - 0.3, FACE_FIELD).set(crouch(0.9));
    ruckTheirs[1].place(rx + s * 0.7, rz - 0.4, FACE_FIELD).set(crouch(0.9));
    ruckOurs.place(rx + s * 0.2, rz + 1, FACE_LINE).set(crouch(0.9));
    // Leur 9 ramasse et se recule pour taper.
    if (t < pickAt) nine.place(rx - s * 0.6, rz - 2, FACE_FIELD).set(crouch(1));
    else {
      const k = smooth(span(t, pickAt, 1.2));
      nine.place(lerp(rx - s * 0.6, nineAt[0], k), lerp(rz - 2, nineAt[1], k), FACE_FIELD).set(HOLD);
    }
    runner(hero, route([heroStart, heroEnd]), t, 0, 1.3, { from: 1, to: 0.95, speed: 0.95 });
    runner(mate, route([[mateEnd[0], mateEnd[1] + 9], mateEnd]), t, 0, 1.3, { from: 0.9, to: 0.8, speed: 0.8 });
    runner(twelve, route([[twelveEnd[0], twelveEnd[1] + 6], twelveEnd]), t, 0, 1.3, { from: 0.7, to: 0.6, speed: 0.6 });
    runner(thirteen, route([[thirteenEnd[0], thirteenEnd[1] + 6], thirteenEnd]), t, 0, 1.3, { from: 0.7, to: 0.6, speed: 0.6 });
    ten.place(...tenAt, FACE_FIELD).set(ready(0.4));
    wings.forEach((player, i) => player.place(...wingsAt[i], FACE_FIELD).set(ready(0.3)));
    fifteen.place(...fifteenAt, FACE_LINE).set(ready(0.3));
    ref.place(refAt[0], refAt[1], Math.PI / 2).set(ready(0.1));
    if (t < pickAt) world.ballAt(ball.copy(ballOnGround), v(1, 0, 0));
    else world.ballAt(ball.lerpVectors(ballOnGround, carried(nine, "two", to), smooth(span(t, pickAt, pickAt + 0.2))), v(1, 0, 0));
    const [cx, cy, cz, lx, ly, lz, fov] = camera(t);
    return { pos: [cx, cy, cz], look: [lx, ly, lz], fov };
  }

  const setup = {
    duration: 1.3,
    frame: setupFrame,
    cues: [{ at: 0.1, run: () => world.crowd(world.pressure > 1 ? "standing" : "seated") }],
  };

  // Les voies : le point de contre, le trou entre leur 9 et leur 10, le repli.
  const blockSpot = [nineAt[0] - s * 0.95, nineAt[1] + 1.25];
  const lane = [rx - s * 5.8, 26.5];
  const tenCatch = [rx - s * 9.8, 30];
  const coverAt = [rx - s * 5, 45];
  const deep = v(fifteenAt[0], 1.12, fifteenAt[1] - 0.42);
  const wide = { pos: [rx - 40, 22, 62], look: [rx * 0.7, 0, 42], fov: 40 };

  function preview(key) {
    const draw = world.draw;
    if (key === "block") return [draw.arrow(heroEnd, blockSpot, 1.5), draw.mark(nineAt, 0.7)];
    if (key === "cut") {
      const a = carried(nine, "two", v());
      return [draw.path([heroEnd, lane]), draw.mark(lane, 0.8), draw.arc(ARC(a, v(tenAt[0], 1.1, tenAt[1]), 0.4), 0.07)];
    }
    return [draw.path([heroEnd, [rx - s * 4.5, 38], coverAt]), draw.mark(coverAt)];
  }

  // Le coup de pied long de leur 9 (ou 10), attrapé par notre arrière.
  const AIR = 2.6;
  const clearing = (t, kicker, kickAt, air = AIR) => {
    const foot = kicker.local(-0.1, 0.5, 0.45, from);
    if (t < kickAt) return false;
    if (t < kickAt + air) world.ballAt(lob(foot, deep, 19, span(t, kickAt, kickAt + air), ball), v(0, 1, 0), (t - kickAt) * 10, v(1, 0, 0));
    else world.ballAt(carried(fifteen, "two", ball), v(1, 0, 0));
    return true;
  };
  const catching = (t, at) => {
    if (t > at - 0.25 && t < at + 0.4) fifteen.place(...fifteenAt, FACE_LINE).set({ ...jump(0.6), armL: 1.5, armR: 1.5, elL: 1.2, elR: 1.2 });
    else if (t >= at + 0.4) fifteen.place(...fifteenAt, FACE_LINE).set(HOLD);
  };
  const wingsChase = (t, a, b) => {
    wings.forEach((player, i) => runner(player, route([wingsAt[i], [wingsAt[i][0] * 0.9, wingsAt[i][1] + 15]]), t, a, b, { from: 0.4, to: 0.9, speed: 0.85 }));
  };
  // Il tape : pose de frappe (le ballon lâché des mains au pied), puis il regarde.
  const kickPose = (player, t, kickAt, heading = FACE_FIELD) => {
    player.place(player.root.position.x, player.root.position.z, heading).set(mixPose(kick(span(t, kickAt - 0.28, kickAt + 0.32), true), ready(0.15), smooth(span(t, kickAt + 0.55, kickAt + 0.95))));
  };

  // --- Charger le dégagement ---------------------------------------------------------------
  function blockOutcome(result) {
    const { success: good, effect } = result;
    if (good) {
      const kickAt = 0.46;
      const hit = 0.6;
      const landed = 0.85;
      const end = 2.25;
      const bounce = v(rx - s * 3.9, 0.12, 25);
      const gatherAt_ = [rx - s * 4.2, 22.6];
      const stop = v(gatherAt_[0], 0.25, gatherAt_[1] - 0.55); // au bout de ses mains quand il arrive
      const heroRun = route([blockSpot, [nineAt[0] - s * 1.6, nineAt[1] - 0.6], gatherAt_, [gatherAt_[0], 18]]);
      // Foulée constante après l'atterrissage : on sait quand il arrive au ballon.
      const toGather = route([blockSpot, [nineAt[0] - s * 1.6, nineAt[1] - 0.6], gatherAt_]).total;
      const gatherT = landed + ((end - landed) * toGather) / heroRun.total;
      const hands = v();
      const tenDive = [rx - s * 6.7, 21.4];
      return {
        duration: end,
        cues: [
          { at: kickAt, run: () => world.sound("kick") },
          { at: hit, run: () => world.sound("impact") },
          { at: hit + 0.2, run: () => reaction(world, true) },
        ],
        frame(t) {
          setupFrame(1.3);
          nine.place(...nineAt, FACE_FIELD).set(t < 0.95 ? kick(span(t, kickAt - 0.28, kickAt + 0.32), true) : dejected());
          if (t < hit) {
            runner(hero, route([heroEnd, blockSpot]), t, 0, hit, { from: 1, to: 1, speed: 1 });
            if (t > 0.38) hero.set({ ...jump(1), lift: Math.sin(span(t, 0.38, landed) * Math.PI) * 0.42, legL: 0.2, legR: -0.4 });
          } else if (t < landed) {
            hero.place(blockSpot[0], blockSpot[1], FACE_LINE).set({ ...jump(1), lift: Math.sin(span(t, 0.38, landed) * Math.PI) * 0.42, legL: 0.2, legR: -0.4 });
          } else runner(hero, heroRun, t, landed, end, { from: 1, to: 1, speed: 1, carry: t > gatherT ? "one" : "none" });
          // Le ballon : du pied aux bras, puis il rebondit devant lui.
          hero.local(0, 2.05, 0.35, hands);
          if (t < 0.34) world.ballAt(carried(nine, "two", ball), v(1, 0, 0));
          else if (t < kickAt) world.ballAt(ball.lerpVectors(carried(nine, "two", from), nine.local(-0.1, 0.5, 0.45, to), smooth(span(t, 0.34, kickAt))), v(0, 1, 0));
          else if (t < hit) world.ballAt(ball.lerpVectors(nine.local(-0.1, 0.5, 0.45, from), hands, span(t, kickAt, hit)), v(0, 1, 0));
          else if (t < hit + 0.45) world.ballAt(lob(v(blockSpot[0], 2.2, blockSpot[1]), bounce, 1.3, span(t, hit, hit + 0.45), ball), v(Math.sin(t * 12), 1, Math.cos(t * 12)));
          else if (t < gatherT) world.ballAt(grubber(bounce, stop, span(t, hit + 0.45, gatherT), 3, ball), v(Math.sin(t * 9), 0.3, 1));
          else world.ballAt(lift(hero, "one", span(t, gatherT, gatherT + 0.2), ball), v(0, 0, 1));
          // Le soutien et les trois-quarts suivent ; leur 10 plonge dans le vide.
          runner(mate, route([mateEnd, [mateEnd[0], 31], [rx - s * 0.2, 21]]), t, 0, end, { from: 0.8, to: 0.95, speed: 0.9 });
          runner(twelve, route([twelveEnd, [twelveEnd[0] - s * 2, 31]]), t, 0, end, { from: 0.6, to: 0.9, speed: 0.8 });
          runner(thirteen, route([thirteenEnd, [thirteenEnd[0], 29]]), t, 0, end, { from: 0.6, to: 0.9, speed: 0.8 });
          const k = span(t, 1.45, 1.9);
          if (t < 1.45) runner(ten, route([tenAt, tenDive]), t, 0.5, 1.45, { from: 0.4, to: 0.9, speed: 0.85 });
          else ten.place(tenDive[0] + s * 0.5 * smooth(k), tenDive[1] - 0.4 * smooth(k), FACE_FIELD + s * 1.2).set(k < 1 ? tackle(k) : ground());
          runner(ref, route([refAt, [refAt[0], 22]]), t, 0.3, end, { from: 0.4, to: 0.7, speed: 0.65 });
          const f = smooth(span(t, hit, end));
          const focus = hero.root.position;
          return broadcast(lerp(rx - s * 2, focus.x, 0.3 + 0.7 * f), lerp(31, focus.z - 1.5, f), { far: lerp(0.9, 1, f) });
        },
      };
    }

    // Il a tapé juste à temps : le ballon passe au-dessus des bras, ou il percute le 9.
    const late = effect === "penalty_conceded";
    const kickAt = 0.28;
    const arrive = kickAt + AIR;
    const hit = 0.72;
    const whistleAt = hit + 0.25;
    const duration = late ? Math.max(arrive, 3.2) + 0.6 : arrive + 1.4;
    const refNear = [nineAt[0] + 5.5, nineAt[1] + 1];
    return {
      duration,
      cues: [
        { at: kickAt, run: () => world.sound("kick") },
        ...(late ? [{ at: hit, run: () => world.sound("impact") }, { at: whistleAt, run: () => penaltyAgainst(world, "us") }] : [{ at: 0.65, run: () => reaction(world, false) }]),
      ],
      frame(t) {
        setupFrame(1.3);
        wingsChase(t, 0.2, duration);
        catching(t, arrive);
        runner(mate, route([mateEnd, [mateEnd[0] - s * 0.5, 39]]), t, 0.4, 1.9, { from: 0.3, to: 0.1, speed: 0.5 });
        if (t >= 1.9) mate.set(ready(0.2));
        nine.place(...nineAt, FACE_FIELD);
        // Le ballon part.
        if (t < kickAt - 0.08) world.ballAt(carried(nine, "two", ball), v(1, 0, 0));
        else if (t < kickAt) world.ballAt(ball.lerpVectors(carried(nine, "two", from), nine.local(-0.1, 0.5, 0.45, to), span(t, kickAt - 0.08, kickAt)), v(0, 1, 0));
        else clearing(t, nine, kickAt);
        if (late) {
          nine.set(t < hit ? kick(span(t, 0, kickAt + 0.32), true) : ground(true));
          if (t >= hit) nine.place(nineAt[0] - s * 0.1, nineAt[1] - 1.2 * smooth(span(t, hit, hit + 0.45)), FACE_FIELD);
          if (t < hit) {
            runner(hero, route([heroEnd, [nineAt[0] - s * 0.5, nineAt[1] + 0.9]]), t, 0, hit, { from: 1, to: 1, speed: 1 });
            if (t > 0.3) hero.set({ ...jump(1), lift: Math.sin(span(t, 0.3, hit + 0.1) * Math.PI) * 0.35 });
          } else {
            hero.place(nineAt[0] - s * 0.5, nineAt[1] + 0.9 - 0.7 * smooth(span(t, hit, hit + 0.4)), FACE_LINE).set(t > whistleAt + 0.5 ? dejected() : ready(0.5));
          }
          // L'arbitre accourt, bras vers leur attaque (+z) : pénalité contre nous.
          const rk = span(t, hit, whistleAt + 0.55);
          ref.place(lerp(refAt[0], refNear[0], smooth(rk)), lerp(refAt[1], refNear[1], smooth(rk)), Math.PI / 2);
          if (rk > 0) ref.set(rk < 1 ? run(t * 3, 0.5) : signal(-1, smooth(span(t, whistleAt + 0.55, whistleAt + 0.85))));
          return broadcast(rx - s * 2, 29.5, { far: 0.88 });
        }
        nine.set(mixPose(kick(span(t, 0, kickAt + 0.32), true), ready(0.15), smooth(span(t, kickAt + 0.55, kickAt + 0.95))));
        // Il saute, bras tendus, le ballon passe au-dessus ; il retombe et se retourne.
        const after = [blockSpot[0] - s * 0.3, blockSpot[1] - 0.6];
        const air = span(t, 0.22, 0.72);
        if (t < 0.5) {
          runner(hero, route([heroEnd, blockSpot]), t, 0, 0.5, { from: 1, to: 1, speed: 1 });
          if (t > 0.22) hero.set({ ...jump(1), lift: Math.sin(air * Math.PI) * 0.42 });
        } else {
          const k = smooth(span(t, 0.5, 0.9));
          const turn = smooth(span(t, 0.9, 1.5));
          hero.place(lerp(blockSpot[0], after[0], k), lerp(blockSpot[1], after[1], k), lerp(FACE_LINE, FACE_FIELD, turn)).set(air < 1 ? { ...jump(1), lift: Math.sin(air * Math.PI) * 0.42 } : t > 1.5 ? dejected() : ready(0.4));
        }
        const f = smooth(span(t, kickAt + 0.5, arrive - 0.1));
        return broadcast(lerp(rx - s * 2, (nineAt[0] + fifteenAt[0]) / 2, f), lerp(31, 46, f), { far: lerp(0.9, 1.5, f), fov: lerp(31, 33, f) });
      },
    };
  }

  // --- Couper la ligne de passe --------------------------------------------------------------
  function cutOutcome(result) {
    const { success: good, effect } = result;
    const toLane = route([heroEnd, lane]);
    const inLane = 0.78;
    if (good) {
      // Sans solution, il s'y reprend à deux fois et tape mal : court, au pied des nôtres.
      const kickAt = 1.25;
      const land = v(rx - s * 0.5, 0.12, 40);
      const roll = v(rx + s * 1.1, 0.12, 42.3);
      const arrive = kickAt + 0.85;
      const gatherAt = arrive + 0.6;
      const gatherSpot = [roll.x + s * 0.4, roll.z + 0.5];
      return {
        duration: gatherAt + 1.5,
        cues: [
          { at: kickAt, run: () => world.sound("kick") },
          { at: arrive, run: () => reaction(world, true) },
        ],
        frame(t) {
          setupFrame(1.3);
          runner(hero, toLane, t, 0, inLane, { from: 0.9, to: 0.3, speed: 0.75 });
          if (t >= inLane) hero.place(lane[0], lane[1], headingTo(...lane, ...nineAt)).set(t > arrive + 0.4 ? cheer(t * 1.5) : ready(0.6));
          // Il regarde son ouvreur, se retourne, n'a plus de temps.
          const look = Math.sin(span(t, 0, kickAt - 0.25) * Math.PI);
          nine.place(...nineAt, FACE_FIELD - s * 0.9 * look);
          if (t < kickAt - 0.3) nine.set(HOLD);
          else nine.set(mixPose(kick(span(t, kickAt - 0.28, kickAt + 0.32), true), dejected(), smooth(span(t, kickAt + 0.6, kickAt + 1))));
          runner(mate, route([mateEnd, [mateEnd[0] - s * 0.8, 33.5]]), t, 0, 1, { from: 0.8, to: 0.1, speed: 0.6 });
          if (t >= 1) mate.set(ready(0.4));
          runner(twelve, route([twelveEnd, gatherSpot]), t, kickAt - 0.1, gatherAt, { from: 0.4, to: 0.3, speed: 0.6 });
          if (t >= gatherAt) twelve.place(gatherSpot[0], gatherSpot[1], FACE_LINE).set(t < gatherAt + 0.25 ? crouch(1) : HOLD);
          const foot = nine.local(-0.1, 0.5, 0.45, from);
          if (t < kickAt - 0.1) world.ballAt(carried(nine, "two", ball), v(1, 0, 0));
          else if (t < kickAt) world.ballAt(ball.lerpVectors(carried(nine, "two", to), foot, span(t, kickAt - 0.1, kickAt)), v(0, 1, 0));
          else if (t < arrive) world.ballAt(lob(foot, land, 3, span(t, kickAt, arrive), ball), v(1, 0.5, 0), (t - kickAt) * 16, v(0, 1, 0));
          else if (t < gatherAt) world.ballAt(grubber(land, roll, span(t, arrive, gatherAt), 3, ball), v(Math.sin(t * 9), 0.3, 1));
          else world.ballAt(lift(twelve, "two", span(t, gatherAt, gatherAt + 0.25), ball), v(1, 0, 0));
          const f = smooth(span(t, kickAt - 0.2, arrive));
          return broadcast(rx - s * 2, lerp(31, 33.5, f), { far: lerp(0.9, 1.15, f), fov: 32 });
        },
      };
    }

    // Il trouve son ouvreur, monté à plat dans le dos du joueur incarné.
    const missed = effect === "missed";
    const out = [0.68, 1.12];
    const tenRun = route([tenCatch, [rx - s * 9.5, 47]]);
    const tenUp = route([tenAt, tenCatch]);
    const kickAt = 1.6;
    const arrive = kickAt + AIR - 0.2;
    const duration = missed ? 3 : arrive + 1;
    const lunge = [rx - s * 7.8, 30.1];
    const diveAt = 1.5;
    return {
      duration,
      cues: [
        missed ? { at: diveAt + 0.3, run: () => reaction(world, false) } : { at: kickAt, run: () => world.sound("kick") },
        ...(!missed ? [{ at: out[1] + 0.1, run: () => world.sound("groan") }] : []),
      ],
      frame(t) {
        setupFrame(1.3);
        wingsChase(t, 0.6, duration);
        runner(mate, route([mateEnd, [mateEnd[0] - s * 1, 37]]), t, 0.2, 1.4, { from: 0.4, to: 0.1, speed: 0.5 });
        if (t >= 1.4) mate.set(ready(0.2));
        nine.place(...nineAt, headingTo(...nineAt, ...tenCatch)).set(t < out[0] + 0.25 ? pass(span(t, out[0] - 0.15, out[0] + 0.2), s > 0 ? 1 : -1) : ready(0.15));
        runner(ten, tenUp, t, 0, out[1], { from: 0.6, to: 0.7, speed: 0.75, carry: t > out[0] + 0.2 ? "two" : "none" });
        // Lui : dans le trou, trop en avant ; le ballon passe derrière lui.
        if (t < inLane) runner(hero, toLane, t, 0, inLane, { from: 0.9, to: 0.4, speed: 0.75 });
        else if (t < 1.05) hero.place(lane[0], lane[1], lerp(FACE_LINE, FACE_FIELD - s * 0.8, smooth(span(t, inLane, 1.05)))).set(ready(0.5));
        if (missed) {
          if (t >= out[1]) runner(ten, tenRun, t, out[1], duration + 0.8, { from: 0.5, to: 1, speed: 1, carry: "one" });
          if (t >= 1.05 && t < diveAt) runner(hero, route([lane, lunge]), t, 1.05, diveAt, { from: 0.5, to: 1, speed: 0.9 });
          if (t >= diveAt) {
            const k = span(t, diveAt, diveAt + 0.45);
            hero.place(lunge[0] - s * 0.2 * k, lunge[1] + 0.9 * smooth(k), FACE_FIELD - s * 0.3).set(k < 1 ? tackle(k) : ground());
          }
          runner(thirteen, route([thirteenEnd, [rx - s * 10, 47]]), t, 1.3, duration, { from: 0.4, to: 0.5, speed: 0.6 });
        } else {
          if (t >= 1.05) {
            runner(hero, route([lane, [lane[0] - s * 0.5, 31]]), t, 1.05, 2.1, { from: 0.4, to: 0.1, speed: 0.4 });
            if (t >= 2.1) hero.set(dejected());
          }
          if (t >= out[1]) ten.place(tenCatch[0], tenCatch[1], FACE_FIELD).set(t < kickAt - 0.28 ? HOLD : mixPose(kick(span(t, kickAt - 0.28, kickAt + 0.32), true), ready(0.15), smooth(span(t, kickAt + 0.55, kickAt + 0.95))));
          catching(t, arrive);
        }
        carried(nine, "two", from);
        if (t < out[0]) world.ballAt(ball.copy(from), v(1, 0, 0));
        else if (t < out[1]) world.ballAt(lob(from, carried(ten, "two", to), 0.55, span(t, ...out), ball), v(1, 0, 0));
        else if (missed) world.ballAt(carried(ten, "one", ball), v(0, 0, 1));
        else if (t < kickAt) world.ballAt(carried(ten, "two", ball), v(1, 0, 0));
        else clearing(t, ten, kickAt, AIR - 0.2);

        const f = smooth(span(t, 0.4, 1.3));
        if (missed) {
          const g = smooth(span(t, diveAt, 2.6));
          return broadcast(lerp(rx - s * 2, rx - s * 8, f), lerp(lerp(31, 30.5, f), 36, g), { far: lerp(0.9, 1.02, g), fov: 32 });
        }
        const g = smooth(span(t, kickAt + 0.3, arrive - 0.2));
        return broadcast(lerp(lerp(rx - s * 2, rx - s * 7, f), (tenCatch[0] + fifteenAt[0]) / 2, g), lerp(30.5, 46, g), { far: lerp(0.95, 1.5, g), fov: lerp(31, 33, g) });
      },
    };
  }

  // --- Rester en couverture -------------------------------------------------------------------
  function coverOutcome(result) {
    const good = result.success;
    const kickAt = 0.75;
    const arrive = kickAt + AIR;
    const duration = arrive + 1.3;
    const peel = route([heroEnd, [rx - s * 4.5, 38], coverAt]);
    const overrun = [rx - s * 3.2, 29.8];
    const lateEnd = [rx - s * 4.5, 37.5];
    const turnAt = 1.05;
    return {
      duration,
      cues: [
        { at: kickAt, run: () => world.sound("kick") },
        { at: arrive, run: () => world.crowd(world.pressure > 1 ? "standing" : "seated") },
        ...(!good ? [{ at: arrive + 0.2, run: () => world.sound("groan") }] : []),
      ],
      frame(t) {
        setupFrame(1.3);
        wingsChase(t, kickAt - 0.1, duration);
        catching(t, arrive);
        nine.place(...nineAt, FACE_FIELD).set(t < kickAt - 0.28 ? HOLD : mixPose(kick(span(t, kickAt - 0.28, kickAt + 0.32), true), ready(0.15), smooth(span(t, kickAt + 0.55, kickAt + 0.95))));
        if (t < kickAt - 0.1) world.ballAt(carried(nine, "two", ball), v(1, 0, 0));
        else if (t < kickAt) world.ballAt(ball.lerpVectors(carried(nine, "two", from), nine.local(-0.1, 0.5, 0.45, to), span(t, kickAt - 0.1, kickAt)), v(0, 1, 0));
        else clearing(t, nine, kickAt);
        // Les nôtres se replacent en ligne, à hauteur du futur regroupement.
        runner(mate, route([mateEnd, [rx + s * 4, 45.5]]), t, 0.15, 1.9, { from: 0.4, to: 0.1, speed: 0.6 });
        if (t >= 1.9) mate.set(ready(0.4));
        runner(twelve, route([twelveEnd, [rx + s * 11, 46]]), t, 0.3, 1.8, { from: 0.4, to: 0.1, speed: 0.6 });
        if (t >= 1.8) twelve.set(ready(0.4));
        runner(thirteen, route([thirteenEnd, [rx - s * 13, 46]]), t, 0.3, 1.5, { from: 0.4, to: 0.1, speed: 0.5 });
        if (t >= 1.5) thirteen.set(ready(0.4));
        if (good) {
          // Il freine, repart en arrière et prend sa place dans la ligne.
          runner(hero, peel, t, 0.1, 2.1, { from: 0.6, to: 0.1, speed: 0.75 });
          if (t < 0.1) hero.place(heroEnd[0], heroEnd[1], FACE_LINE).set(run(t, 0.7));
          if (t >= 2.1) hero.place(coverAt[0], coverAt[1], FACE_LINE).set(ready(0.4));
        } else {
          // Il va trop loin, se retourne tard, et court après tout le monde.
          if (t < turnAt - 0.2) runner(hero, route([heroEnd, overrun]), t, 0, turnAt - 0.2, { from: 0.9, to: 0.1, speed: 0.7 });
          else if (t < turnAt) hero.place(overrun[0], overrun[1], lerp(FACE_LINE, FACE_FIELD, smooth(span(t, turnAt - 0.2, turnAt)))).set(ready(0.3));
          else {
            runner(hero, route([overrun, lateEnd]), t, turnAt, arrive + 0.3, { from: 0.4, to: 0.4, speed: 0.55 });
            if (t >= arrive + 0.3) hero.set(dejected());
          }
        }
        const f = smooth(span(t, kickAt + 0.3, arrive - 0.3));
        return broadcast(lerp(rx - s * 2, rx * 0.5 - s * 1, f), lerp(31, 44, f), { far: lerp(0.9, 1.45, f), fov: lerp(31, 33, f) });
      },
    };
  }

  return {
    setup,
    preview,
    previewShot: (key) => (key === "cover" ? wide : null),
    outcome(key, result) {
      if (key === "block") return blockOutcome(result);
      if (key === "cut") return cutOutcome(result);
      return coverOutcome(result);
    },
  };
}
