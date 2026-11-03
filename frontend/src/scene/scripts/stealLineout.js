import * as THREE from "three";

import { TOUCH } from "../field.js";
import { bind, cheer, dejected, ground, jump, lifter, mixPose, pass, pose, ready, run, signal } from "../rig.js";
import { FACE_FIELD, FACE_LINE, broadcast, carried, keys, lerp, lob, penaltyAgainst, reaction, route, runner, smooth, span } from "./common.js";
import { forwards } from "./goalScrum.js";
import { maul } from "./setPieces.js";

// Carrière de joueur, « Touche adverse » (steal_lineout) : touche pour eux, à quinze
// mètres de notre ligne (z = 0). Le joueur incarné est au milieu de notre alignement.
// Sauter devant (il contre le lancer court ; ou le ballon passe au-dessus de lui), sauter
// au fond (il vole le long ; ou le lancer part devant, il est hors du coup), rester au sol
// (leur maul ne part pas ; ou il démarre mieux que prévu).
//
// Comme à la mêlée, leur alignement est côté +z : ils attaquent vers notre ligne.

const OURS = { 1: 5.5, 6: 6.5, 3: 7.5, 4: 8.9, 5: 10, 7: 11.1, 8: 13.6 };
const THEIRS = { 1: 5.8, 6: 6.8, 3: 7.8, 4: 9.3, 5: 10.3, 7: 11.3, 8: 13.8 };
const THROWING = pose({ armL: 2.9, armR: 2.9, elL: 0.9, elR: 0.9, lean: -0.15 });
// Le saut : le ballon de `to`, à la hauteur des mains d'un joueur soulevé.
const REACH = 2.25;

export function buildStealLineout(world, data) {
  const s = 1; // toujours la touche d'en face : le lanceur reste face à la caméra
  const zl = 15;
  const heroNo = data.hero ?? 5;
  // Le joueur incarné tient le milieu de l'alignement (la place 5), à égale distance des deux sauts.
  const { ours, theirs, hero } = forwards(world, heroNo, 5);
  // Le repère du joueur incarné se voit à travers l'alignement.
  hero.marker.material.depthTest = false;
  hero.marker.renderOrder = 3;
  const thrower = theirs[2];
  const nine = world.player("us", 9);
  const ten = world.player("us", 10);
  const theirNine = world.player("them", 9);
  const theirTen = world.player("them", 10);
  const ref = world.player("ref");

  const face = (s * Math.PI) / 2;
  const spot = (depth, z) => [s * (TOUCH - depth), z];
  const home = {};
  for (const [n, depth] of Object.entries(OURS)) home[n] = spot(depth, zl - 0.55);
  const away = {};
  for (const [n, depth] of Object.entries(THEIRS)) away[n] = spot(depth, zl + 0.55);
  const throwFrom = [s * (TOUCH + 0.7), zl];
  const ball = new THREE.Vector3();
  const from = new THREE.Vector3();
  const to = new THREE.Vector3();
  // Tout l'alignement dans le cadre, du lanceur au dernier sauteur, au-dessus des voies.
  const focus = [s * (TOUCH - 7), zl];
  const frameOn = (z) => {
    const view = broadcast(focus[0], z, { far: 0.85, fov: 31, y: 0.4 });
    return { ...view, look: [focus[0] - s * 1.6, view.look[1], z] };
  };
  const shot = frameOn(zl + 0.3);
  const camera = keys([
    [0, [focus[0] - 50, 24, zl + 32, focus[0] * 0.7, 0, zl + 4, 44]],
    [1.3, [...shot.pos, ...shot.look, shot.fov]],
  ]);
  const nineSpot = spot(10, zl - 3.8);
  const tenSpot = spot(19, zl - 9);
  const theirNineSpot = spot(9.5, zl + 3.8);
  const theirTenSpot = spot(20, zl + 9);
  const refSpot = spot(4, zl - 5.5);

  function setupFrame(t) {
    // Les avants trottent jusqu'à l'alignement, le lanceur prend le ballon au-dessus de sa tête.
    const k = smooth(span(t, 0, 1.0));
    for (let n = 1; n <= 8; n++) {
      if (n === 2) continue;
      const [x, z] = home[n];
      ours[n].place(lerp(x - s * 2, x, k), lerp(z - 3, z, k), face).set(k < 1 ? run(t * 2.5, 0.3) : ready(0.3));
      const [ax, az] = away[n];
      theirs[n].place(lerp(ax - s * 2, ax, k), lerp(az + 3, az, k), face).set(k < 1 ? run(t * 2.5 + 0.3, 0.3) : ready(0.3));
    }
    // Notre talonneur à sa place, dans le couloir des cinq mètres.
    ours[2].place(s * (TOUCH + 0.4), zl - 4.5, -face).set(ready(0.2));
    thrower.place(...throwFrom, -face).set(t > 0.8 ? THROWING : ready(0.1));
    nine.place(...nineSpot, face).set(ready(0.4));
    ten.place(...tenSpot, FACE_FIELD).set(ready(0.4));
    theirNine.place(...theirNineSpot, face).set(ready(0.4));
    theirTen.place(...theirTenSpot, FACE_LINE).set(ready(0.4));
    ref.place(...refSpot, FACE_FIELD).set(ready(0.1));
    ref.card.visible = false;
    world.ballAt(thrower.local(0, t > 0.8 ? 2.25 : 1.1, 0.25, ball), new THREE.Vector3(0, 1, 0));
    const [cx, cy, cz, lx, ly, lz, fov] = camera(t);
    return { pos: [cx, cy, cz], look: [lx, ly, lz], fov };
  }

  const setup = {
    duration: 1.3,
    frame: setupFrame,
    cues: [{ at: 0.1, run: () => world.crowd(world.pressure > 1 ? "standing" : "seated") }],
  };

  // Où saute-t-il, selon la voie : ses lifteurs, et qui lui laisse la place.
  const JUMPS = {
    jump_front: { depth: 6.5, lifters: [1, 3], gives: 6, rival: 6 },
    jump_back: { depth: 12.6, lifters: [7, 8], gives: null, rival: 8 },
    stay_down: { depth: 10, lifters: [], gives: null, rival: 5 },
  };

  function preview(key) {
    const draw = world.draw;
    const plan = JUMPS[key];
    const target = spot(plan.depth, zl - 0.55);
    if (key === "stay_down") return [draw.mark(target, 0.9), draw.arrow([target[0], zl - 2.6], [target[0], zl - 0.9], 1.5)];
    const a = new THREE.Vector3(throwFrom[0], 2.4, throwFrom[1]);
    const b = new THREE.Vector3(target[0], 3.4, zl);
    const arc = [];
    for (let i = 0; i <= 12; i++) arc.push(lob(a, b, 1.2, i / 12).toArray());
    return [draw.arc(arc, 0.08), draw.path([[home[5][0], zl - 1.6], [target[0], zl - 1.6]], { width: 0.35 }), draw.mark(target, 0.8)];
  }

  function outcomeFor(key, result) {
    const { success, effect } = result;
    const plan = JUMPS[key];
    const penalty = !success && effect === "penalty_conceded";
    const throwAt = 0.5;
    // Où part le lancer : là où il a deviné s'il a raison ; sinon, ailleurs.
    const rivalNo = key === "jump_front" ? (success ? 6 : 5) : key === "jump_back" ? (success ? 8 : 6) : 5;
    const catchAt = rivalNo === 8 ? 1.15 : rivalNo === 6 ? 0.92 : 1.02;
    const stole = success && key !== "stay_down";
    const maulAt = catchAt + 0.5; // leur maul se forme (au sol)
    const passAt = catchAt + 0.55; // le sauteur redescendu sert son demi
    const callAt = catchAt + 0.5;
    const target = spot(plan.depth, zl - 0.55);
    const rivalSpot = away[rivalNo];
    const duration = key === "stay_down" ? 4 : 3.4;

    const cues = [];
    if (stole) {
      cues.push({ at: catchAt, run: () => world.sound("impact") });
      cues.push({ at: catchAt + 0.1, run: () => reaction(world, true) });
    } else if (penalty) cues.push({ at: callAt, run: () => penaltyAgainst(world, "us") });
    else if (key === "stay_down") {
      cues.push({ at: maulAt + 0.2, run: () => world.sound("impact") });
      cues.push({ at: 3, run: () => reaction(world, success) });
    } else cues.push({ at: catchAt + 0.2, run: () => reaction(world, false) });

    return {
      duration,
      cues,
      frame(t) {
        setupFrame(1.3);
        thrower.place(...throwFrom, -face).set(t < throwAt ? THROWING : pose({ armL: 1.6, armR: 1.6, lean: 0.2 }));
        // Le joueur incarné file à sa place, ses lifteurs serrent sous lui, on lui fait place.
        const move = smooth(span(t, 0, throwAt));
        if (key !== "stay_down") {
          // Retombé, il recule d'un pas : leur alignement le cacherait à la caméra.
          const clear = smooth(span(t, catchAt + 0.55, catchAt + 1.15));
          hero.place(lerp(home[5][0], target[0], move), lerp(home[5][1], target[1], move) - 1.6 * clear, face);
          const [la, lb] = plan.lifters;
          ours[la].place(lerp(home[la][0], target[0] + s * 0.95, move), home[la][1], face);
          ours[lb].place(lerp(home[lb][0], target[0] - s * 0.95, move), home[lb][1], face);
          if (plan.gives) {
            // Celui qui tenait la place recule d'un pas et prend la sienne, derrière le saut.
            const [gx, gz] = home[plan.gives];
            const arc = Math.sin(move * Math.PI) * 1.3;
            ours[plan.gives].place(lerp(gx, home[5][0], move), gz - arc, face);
            if (move > 0 && move < 1) ours[plan.gives].set(run(t * 2.5, 0.3));
          }
        }
        // Leurs sauteurs : celui visé par le lancer, soulevé par ses voisins.
        const rival = theirs[rivalNo];
        const theirUp = smooth(span(t, throwAt, throwAt + 0.32)) * (1 - smooth(span(t, catchAt + 0.15, catchAt + 0.5)));
        // Battu quand on lui vole le ballon : il monte moins haut.
        rival.place(rivalSpot[0], rivalSpot[1], face).set({ ...jump(theirUp), lift: theirUp * (stole ? 1.2 : 1.6) });
        ({ 6: [1, 3], 5: [4, 7], 8: [7, 4] })[rivalNo].forEach((n, i) => {
          theirs[n].place(rivalSpot[0] + (i ? -s : s) * 0.95, away[n][1], face).set(lifter(theirUp));
        });

        // Son saut : avant le leur s'il a deviné, à vide s'il s'est trompé.
        const up = key === "stay_down" ? 0 : smooth(span(t, throwAt - 0.12, throwAt + 0.18)) * (1 - smooth(span(t, catchAt + 0.2, catchAt + 0.55)));
        if (key !== "stay_down") {
          hero.set(move < 1 && up === 0 ? run(t * 2.5, 0.5) : { ...jump(up), lift: up * 1.6 });
          plan.lifters.forEach((n) => ours[n].set(lifter(up)));
        }

        const hands = hero.local(0, REACH + 0.15, 0.1, to);
        const rivalHands = rival.local(0, REACH + 0.15, 0.1, new THREE.Vector3());
        // `local` compte déjà la hauteur du saut (`lift`).
        thrower.local(0, 2.25, 0.1, from);
        const catcher = stole ? hands.clone() : rivalHands;
        const handOff = catchAt + 0.5;

        if (t < throwAt) world.ballAt(from, new THREE.Vector3(0, 1, 0));
        else if (t < catchAt) world.ballAt(lob(from, catcher, 1.2, span(t, throwAt, catchAt), ball), new THREE.Vector3(1, 0.2, 0));
        else if (stole) {
          // Ballon volé : il redescend, le passe à notre 9, qui sert.
          const held = hero.local(0, REACH + 0.15 + (up - 1) * 1.2, 0.1, new THREE.Vector3());
          const nineAt = spot(plan.depth, zl - 2.4);
          const k = smooth(span(t, catchAt + 0.1, handOff));
          nine.place(lerp(nineSpot[0], nineAt[0], k), lerp(nineSpot[1], nineAt[1], k), lerp(face, FACE_FIELD, k));
          nine.set(k < 1 ? run(t * 2.5, 0.5) : ready(0.4));
          const nineHands = carried(nine, "two", new THREE.Vector3());
          if (t < handOff) world.ballAt(held, new THREE.Vector3(1, 0, 0));
          else if (t < handOff + 0.3) world.ballAt(ball.lerpVectors(held, nineHands, span(t, handOff, handOff + 0.3)), new THREE.Vector3(1, 0, 0));
          else if (t < handOff + 0.65) {
            nine.place(nineAt[0], nineAt[1], -face).set(pass(span(t, handOff + 0.3, handOff + 0.6), s > 0 ? 1 : -1));
            world.ballAt(carried(nine, "two", ball), new THREE.Vector3(1, 0, 0));
          } else {
            nine.place(nineAt[0], nineAt[1], -face).set(pass(1, s > 0 ? 1 : -1));
            const carry = t > handOff + 1.05;
            runner(ten, route([tenSpot, [tenSpot[0] - s * 1, tenSpot[1] + 3.5]]), t, handOff + 0.3, duration, { from: 0.3, to: 0.7, speed: 0.7, carry: carry ? "two" : "none" });
            if (carry) world.ballAt(carried(ten, "two", ball), new THREE.Vector3(1, 0, 0));
            else world.ballAt(lob(carried(nine, "two", from), carried(ten, "two", new THREE.Vector3()), 0.8, span(t, handOff + 0.65, handOff + 1.05), ball), new THREE.Vector3(1, 0, 0));
          }
          const glad = smooth(span(t, catchAt + 0.6, catchAt + 1.1));
          if (glad > 0) {
            hero.set(mixPose(hero.current, cheer(t * 1.5), glad));
            Object.values(theirs).forEach((player) => player !== thrower && player.set(mixPose(player.current, dejected(), glad)));
            thrower.set(mixPose(thrower.current, dejected(), glad));
          }
        } else if (key === "stay_down") {
          // Le sauteur retombe, leur maul se forme : il y entre le premier, côté caméra.
          const formed = smooth(span(t, maulAt, maulAt + 0.55));
          const front = success ? zl - 0.1 - 0.3 * smooth(span(t, maulAt, maulAt + 1)) : lerp(zl - 0.1, zl - 5.2, smooth(span(t, maulAt + 0.3, duration - 0.3)));
          const center = [spot(10.2, 0)[0], front];
          if (t >= maulAt) {
            const starts = new Map();
            const attackers = { 5: theirs[5], 1: theirs[3], 4: theirs[4], 6: theirs[1], 7: theirs[7], 8: theirs[8] };
            const defenders = { 1: hero, 5: ours[1], 4: ours[4], 6: ours[6], 7: ours[7], 8: ours[8] };
            for (const group of [Object.values(attackers), Object.values(defenders)]) group.forEach((player) => starts.set(player, [player.root.position.x, player.root.position.z]));
            maul(attackers, defenders, starts, center, formed, t * 1.4, 1);
            const carrier = theirs[8];
            if (formed < 1) carrier.set(mixPose(ready(0.3), bind(t, 1, 0.5), formed));
            else carrier.set(pose({ y: -0.2, lean: 0.75, legL: 0.65, legR: 0.45, knL: 0.8, knR: 0.7, armL: 1.15, armR: 1.1, abL: 0.25, abR: -0.1, elL: 1.2, elR: 1.1, nod: -0.25 }));
            const tail = carrier.local(0.3, 1.0, 0.25, new THREE.Vector3());
            const toTail = span(t, maulAt, maulAt + 0.5);
            const low = rival.local(0, 1.2, 0.3, new THREE.Vector3());
            world.ballAt(toTail < 1 ? ball.lerpVectors(low, tail, toTail) : tail, new THREE.Vector3(1, 0, 0.3));
            theirs[6].place(center[0] + 1.3, front + 1.5, FACE_LINE).set(bind(t * 1.4, 1, 0.75));
          } else {
            const landing = span(t, catchAt, maulAt);
            world.ballAt(ball.lerpVectors(rivalHands, rival.local(0, 1.2, 0.3, new THREE.Vector3()), landing), new THREE.Vector3(1, 0, 0));
          }
          return frameOn(Math.min(front + 1, zl + 0.3));
        } else {
          // Le lancer est pour eux : leur sauteur redescend et remet à leur 9, qui sert.
          const nineAt = spot(THEIRS[rivalNo], zl + 2.6);
          const k = smooth(span(t, catchAt, passAt));
          theirNine.place(lerp(theirNineSpot[0], nineAt[0], k), lerp(theirNineSpot[1], nineAt[1], k), face);
          theirNine.set(k < 1 ? run(t * 2.5, 0.5) : ready(0.35));
          const nineHands = carried(theirNine, "two", new THREE.Vector3());
          const dropped = rival.local(0, 1.5, 0.3, new THREE.Vector3());
          if (t < passAt) world.ballAt(ball.lerpVectors(rivalHands, dropped, span(t, catchAt, passAt)), new THREE.Vector3(1, 0, 0));
          else if (t < passAt + 0.3) world.ballAt(ball.lerpVectors(dropped, nineHands, span(t, passAt, passAt + 0.3)), new THREE.Vector3(1, 0, 0));
          else if (penalty) world.ballAt(nineHands, new THREE.Vector3(1, 0, 0));
          else if (t < passAt + 0.65) {
            theirNine.set(pass(span(t, passAt + 0.3, passAt + 0.6), s > 0 ? -1 : 1));
            world.ballAt(nineHands, new THREE.Vector3(1, 0, 0));
          } else {
            theirNine.set(pass(1, s > 0 ? -1 : 1));
            const carry = t > passAt + 1.05;
            runner(theirTen, route([theirTenSpot, [theirTenSpot[0] - s, theirTenSpot[1] - 3.5]]), t, passAt + 0.3, duration, { from: 0.3, to: 0.7, speed: 0.7, carry: carry ? "two" : "none" });
            if (carry) world.ballAt(carried(theirTen, "two", ball), new THREE.Vector3(1, 0, 0));
            else world.ballAt(lob(nineHands, carried(theirTen, "two", new THREE.Vector3()), 0.8, span(t, passAt + 0.65, passAt + 1.05), ball), new THREE.Vector3(1, 0, 0));
          }
          // Hors du coup : il retombe, seul, regarde ailleurs.
          const late = smooth(span(t, catchAt + 0.55, catchAt + 0.95));
          if (late > 0) hero.set(mixPose(hero.current, dejected(), late));
          if (penalty) {
            // Il retombe sur leur 6 resté en face de lui : le geste de trop.
            const hit = theirs[6];
            const f = span(t, catchAt + 0.25, catchAt + 0.65);
            if (f > 0) hit.place(away[6][0], away[6][1] + 0.6 * smooth(f), face).set(f < 0.5 ? ready(0.5) : ground(true));
            ref.place(lerp(refSpot[0], target[0] + s * 0.5, smooth(span(t, callAt - 0.2, callAt + 0.5))), lerp(refSpot[1], zl - 3.6, smooth(span(t, callAt - 0.2, callAt + 0.5))), -Math.PI / 2);
            ref.set(t < callAt ? run(t * 3, 0.5) : signal(-1, smooth(span(t, callAt, callAt + 0.3))));
          }
        }
        return shot;
      },
    };
  }

  return { setup, preview, outcome: outcomeFor };
}
