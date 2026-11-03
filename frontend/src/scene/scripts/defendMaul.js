import * as THREE from "three";

import { bind, card, cheer, crouch, dejected, dive, ground, mixPose, pose, ready, run, signal, tackle, tryAward } from "../rig.js";
import { FACE_FIELD, FACE_LINE, broadcast, carried, keys, lerp, penaltyAgainst, reaction, route, runner, smooth, span } from "./common.js";
import { HEAP } from "./goalScrum.js";
import { maul } from "./setPieces.js";

// Carrière de joueur, « Le maul avance » (defend_maul) : leur maul, formé à dix mètres de
// notre ligne (z = 0), pousse sur nos avants. Le joueur incarné est libre sur le flanc,
// côté caméra, là où il a encore à choisir. Entrer (il arrache le ballon ; ou le maul
// l'emporte), écrouler (sans que l'arbitre bronche ; ou pénalité, carton), attendre à la
// sortie (il cueille le porteur ; ou le maul avance sans lui).
//
// Un échec peut aller jusqu'à l'essai : le maul franchit, leur 8 aplatit. `maul` reçoit
// les packs inversés : ici c'est l'adversaire qui pousse vers z = 0.

const CARRIER = pose({ y: -0.2, lean: 0.75, legL: 0.65, legR: 0.45, knL: 0.8, knR: 0.7, armL: 1.15, armR: 1.1, abL: 0.25, abR: -0.1, elL: 1.2, elR: 1.1, nod: -0.25 });
const WRESTLE = pose({ y: -0.14, lean: 0.55, armL: 1.3, armR: 1.4, abL: -0.3, abR: -0.3, elL: 1.0, elR: 0.9, legL: 0.5, legR: -0.2, knL: 0.7, knR: 0.5, nod: -0.2 });

export function buildDefendMaul(world, data) {
  const rng = world.rng;
  const s = rng() < 0.5 ? -1 : 1;
  const mx = s * (5 + rng() * 8);
  const front = 10; // l'avant du maul au moment du choix
  const heroNo = data.hero ?? 6;

  // Six des nôtres dans le maul : le joueur incarné n'y est pas, un autre prend sa place.
  const hero = world.player("us", heroNo, { hero: true });
  const pool = [2, 3].filter((n) => n !== heroNo);
  const pack = {};
  for (const n of [1, 5, 4, 6, 7, 8]) pack[n] = world.player("us", n === heroNo ? pool.shift() : n);
  const spare = pool.map((n) => world.player("us", n));
  const them = {};
  for (let n = 1; n <= 8; n++) them[n] = world.player("them", n);
  const carrier = them[8];
  // Le maul sans leurs 2 et 3, repoussés sur l'autre flanc : le porteur reste à découvert.
  const attackers = { 5: them[5], 1: them[1], 4: them[4], 6: them[6], 7: them[7], 8: carrier };
  const theirNine = world.player("them", 9);
  const nine = world.player("us", 9);
  const ten = world.player("us", 10);
  const ref = world.player("ref");

  const ball = new THREE.Vector3();
  const flank = [mx - 2.4, front - 0.5];
  const wait = [mx - 3, front - 2.6]; // là où il attend le porteur
  const shot = broadcast(mx, front + 0.5, { far: 0.72, fov: 31, y: -1 });
  const camera = keys([
    [0, [mx - 50, 24, front + 30, mx * 0.6, 0, front + 2, 44]],
    [1.5, [...shot.pos, ...shot.look, shot.fov]],
  ]);

  const SETUP = 1.5;
  const frontAt = (t) => lerp(front + 3.2, front, smooth(span(t, 0, SETUP)) * 0.35 + span(t, 0, SETUP) * 0.65);
  // Où chacun était avant de se grouper.
  const starts = new Map();
  [...Object.values(attackers), ...Object.values(pack)].forEach((player, i) => {
    const angle = (i / 12) * Math.PI * 2;
    starts.set(player, [mx + Math.cos(angle) * 3.2, front + 3.2 + Math.sin(angle) * 2.8]);
  });
  const none = new Map();

  // Le maul à un instant : `at` l'avant, `drive` les jambes, le porteur à découvert.
  function group(t, at, drive = 1, formed = 1, from = none) {
    maul(attackers, pack, from, [mx, at], formed, t * 1.4, drive);
    carrier.set(CARRIER);
    them[2].place(mx + 1.2, at + 1.8, FACE_LINE).set(bind(t * 1.4 + 0.3, drive, 0.75));
    them[3].place(mx + 1.35, at + 0.8, FACE_LINE).set(bind(t * 1.4 + 0.6, drive, 0.75));
    spare.forEach((player, i) => player.place(mx + 1.9 + i * 0.5, at - 0.6 - i * 0.9, FACE_FIELD).set(ready(0.6)));
    theirNine.place(mx + 0.9, at + 3.7, FACE_LINE).set(ready(0.4));
  }
  // Le ballon dans les mains du porteur, sur son flanc côté caméra.
  const held = (out) => carrier.local(0.3, 1.0, 0.25, out);
  const refAt = (at) => ref.place(mx + 3.6, at + 0.6, -Math.PI / 2);

  function setupFrame(t) {
    group(t, frontAt(t), smooth(span(t, 0.3, 0.8)), smooth(span(t, 0, 0.75)), starts);
    runner(hero, route([[mx - 6.5, front - 5.5], flank]), t, 0, SETUP, { from: 0.9, to: 0.3, speed: 0.7 });
    if (t >= SETUP - 0.15) hero.place(flank[0], flank[1], FACE_FIELD + 0.25).set(ready(0.8));
    nine.place(mx + 5.5, 3.5, FACE_FIELD).set(ready(0.4));
    ten.place(mx + 10, 2, FACE_FIELD).set(ready(0.4));
    refAt(frontAt(t)).set(ready(0.1));
    ref.card.visible = false;
    world.ballAt(held(ball), new THREE.Vector3(1, 0, 0.3));
    const [cx, cy, cz, lx, ly, lz, fov] = camera(t);
    return { pos: [cx, cy, cz], look: [lx, ly, lz], fov };
  }

  const setup = {
    duration: SETUP,
    frame: setupFrame,
    cues: [
      { at: 0.1, run: () => world.crowd(world.pressure > 1 ? "standing" : "seated") },
      { at: 0.7, run: () => world.sound("impact") },
    ],
  };

  function preview(key) {
    const draw = world.draw;
    if (key === "stop") return [draw.path([flank, [mx - 1.3, front + 0.3], [mx - 1.3, front + 2]]), draw.mark([mx - 0.5, front + 2.2], 0.7)];
    if (key === "sack") return [draw.arrow([flank[0], flank[1]], [mx - 0.8, front + 0.8], 1.3), draw.mark([mx, front + 0.8], 1.8)];
    return [draw.path([flank, wait]), draw.mark(wait), draw.path([[mx - 1.1, front + 2.2], [wait[0] + 0.3, wait[1] + 1]], { width: 0.3 })];
  }

  function outcomeFor(key, result) {
    const { success, effect } = result;
    const scored = !success && effect === "try_conceded";
    const yellow = !success && effect === "yellow";
    const whistled = key === "sack" && !success;
    const enterAt = 0.5;
    const callAt = 1.15;
    const cardAt = callAt + 1.4;
    const lineAt = 3.5; // l'avant du maul sur notre ligne
    const peelAt = lineAt - 0.55; // leur 8 lâche le maul et file aplatir
    const flatAt = peelAt + 0.95;
    const ripAt = 1.85; // il a le ballon, dans le maul
    const breakAt = 1.15; // le porteur sort
    const hitAt = 1.65; // il cueille le porteur
    const duration = scored ? flatAt + 2 : yellow ? cardAt + 1.5 : 3.8;

    // L'avant du maul selon la voie : arrêté net, écroulé, ou qui continue.
    const atFor = (t) => {
      if (key === "stop" && success) return front - 0.6 * smooth(span(t, 0, 1.0));
      if (key === "sack") return front - 0.5 * smooth(span(t, 0, 1.0));
      if (key === "wait" && success) return front - 1.1 * smooth(span(t, 0, 1.5));
      if (scored) return lerp(front, -0.4, span(t, 0, lineAt) ** 1.1);
      return front - 5 * smooth(span(t, 0, 3.2)); // il continue, sans aller au bout
    };

    const cues = [];
    if (key === "stop") cues.push({ at: enterAt, run: () => world.sound("impact") });
    if (key === "sack") cues.push({ at: enterAt, run: () => world.sound("impact") });
    if (scored) {
      cues.push({ at: 1, run: () => world.crowd("standing") });
      cues.push({
        at: flatAt,
        run: () => {
          world.sound("whistle", true);
          reaction(world, false);
        },
      });
    } else if (whistled) cues.push({ at: callAt, run: () => penaltyAgainst(world, "us") });
    else if (success) {
      if (key === "wait") cues.push({ at: hitAt, run: () => world.sound("impact") });
      cues.push({ at: key === "stop" ? ripAt : key === "wait" ? hitAt + 0.25 : 1.3, run: () => reaction(world, true) });
    } else cues.push({ at: 2, run: () => reaction(world, false) });

    return {
      duration,
      cues,
      frame(t) {
        setupFrame(SETUP);
        const at = atFor(t);
        const stalled = (key === "stop" && success) || (key === "wait" && success) || key === "sack";
        group(t, at, stalled ? 1 - span(t, 1.2, 2) * 0.8 : 1);
        const all = [...Object.values(attackers), them[2], them[3], ...Object.values(pack)];
        const eightSpot = [mx, at + 2.1];
        world.ballAt(held(ball), new THREE.Vector3(1, 0, 0.3));
        let look = [mx, front + 0.5];
        let y = -0.4;

        if (key === "stop") {
          // Il contourne le premier rang et va chercher le ballon dans les mains du 8.
          const side = success ? [mx - 1.0, at + 2.25] : [mx - 1.12, at + 0.1];
          const k = smooth(span(t, 0, enterAt));
          hero.place(lerp(flank[0], side[0], k), lerp(flank[1], side[1], k), success ? lerp(FACE_FIELD + 0.25, Math.PI / 2, k) : FACE_FIELD + 0.5);
          hero.set(k < 1 ? run(t * 3, 0.6) : success ? WRESTLE : bind(t * 1.4 + 0.2, 1, 0.8));
          if (success) {
            const shake = Math.sin(t * 16) * 0.1 * (t < ripAt ? 1 : 0);
            carrier.root.rotation.y = carrier.heading = FACE_LINE + shake;
            carrier.set(t > ripAt ? dejected() : CARRIER);
            if (t >= enterAt && t < ripAt) world.ballAt(ball.lerpVectors(held(new THREE.Vector3()), hero.local(0, 1.05, 0.4), span(t, enterAt, ripAt) * 0.6), new THREE.Vector3(1, 0, 0.3));
            if (t >= ripAt) {
              // Le ballon à lui : il sort du maul vers les siens.
              const away = route([side, [side[0] - 3, side[1] - 5]]);
              runner(hero, away, t, ripAt, duration, { from: 0.3, to: 0.7, speed: 0.75, carry: "one" });
              world.ballAt(carried(hero, "one", ball), new THREE.Vector3(0, 0, 1));
              const k2 = smooth(span(t, ripAt + 0.1, ripAt + 0.7));
              all.forEach((player, i) => {
                const cheered = Object.values(pack).includes(player);
                player.set(mixPose(player.current, cheered ? cheer(t * 1.5 + i * 0.2) : dejected(), k2));
              });
            }
          }
          if (!success && t > 2.9 && !scored) hero.set(mixPose(hero.current, dejected(), smooth(span(t, 2.9, 3.4))));
        } else if (key === "sack") {
          // Il plonge sous le premier rang : tout le maul s'affaisse d'un bloc.
          const target = [mx - 1.0, at + 0.4];
          const k = smooth(span(t, 0, enterAt));
          const heading = Math.atan2(target[0] - flank[0], target[1] - flank[1]);
          hero.place(lerp(flank[0], target[0], k), lerp(flank[1], target[1], k), heading);
          hero.set(t < enterAt ? tackle(span(t, 0.05, enterAt) * 0.5) : tackle(0.5 + 0.5 * span(t, enterAt, enterAt + 0.4)));
          const fall = smooth(span(t, enterAt + 0.1, enterAt + 0.6));
          all.forEach((player) => player.set(mixPose(player.current, HEAP, fall)));
          const lie = new THREE.Vector3(mx - 0.45, 0.14, at + 2.3);
          world.ballAt(ball.lerpVectors(held(new THREE.Vector3()), lie, fall), new THREE.Vector3(1, 0, 0.3));
          // Il se relève : content si l'arbitre n'a rien vu, tête basse sinon.
          const up = smooth(span(t, callAt + 0.8, callAt + 1.3));
          if (up > 0) hero.set(mixPose(hero.current, success ? ready(0.3) : dejected(), up));
          if (whistled) {
            // Leur 9 ramasse : la pénalité se joue vite.
            const pick = callAt + 0.9;
            const j = smooth(span(t, callAt + 0.2, pick));
            theirNine.place(lerp(mx + 0.9, mx - 0.9, j), lerp(at + 3.7, at + 2.75, j), FACE_LINE);
            theirNine.set(t < pick ? (j < 1 ? run(t * 2.5, 0.4) : crouch(1)) : ready(0.2));
            if (t >= pick) world.ballAt(carried(theirNine, "two", ball), new THREE.Vector3(1, 0, 0));
            const back = smooth(span(t, callAt + 0.6, callAt + 1.2));
            all.forEach((player) => player.set(mixPose(player.current, ready(0.2), back)));
          }
        } else if (key === "wait") {
          const k = smooth(span(t, 0, 0.7));
          const backed = [lerp(flank[0], wait[0], k), lerp(flank[1], wait[1], k)];
          hero.place(backed[0], backed[1], FACE_FIELD + 0.25);
          hero.set(k < 1 ? run(-t * 2, 0.3) : ready(0.8));
          if (success) {
            // Le porteur lâche le maul de son côté : il arrive droit sur lui.
            const hit = [wait[0] + 0.2, wait[1] + 0.6];
            if (t > breakAt) {
              const exit = route([eightSpot, [mx - 1.7, at + 1.4], [hit[0], hit[1] + 0.7]]);
              if (t < hitAt) runner(carrier, exit, t, breakAt, hitAt, { from: 0.4, to: 1, speed: 0.85, carry: "one" });
              if (t < hitAt) world.ballAt(carried(carrier, "one", ball), new THREE.Vector3(0, 0, -1));
              else {
                const f = span(t, hitAt, hitAt + 0.45);
                carrier.place(hit[0], hit[1] + 0.7 + 0.9 * smooth(f), FACE_LINE).set(f < 0.4 ? ready(0.4) : ground(true));
                // Le ballon, serré contre lui, au sol avec lui.
                const lie = new THREE.Vector3(hit[0] + 0.45, 0.14, hit[1] + 1.25);
                world.ballAt(ball.lerpVectors(carried(carrier, "one", new THREE.Vector3()), lie, smooth(f)), new THREE.Vector3(1, 0, 0.3));
              }
            }
            if (t > hitAt - 0.45) {
              const lunge = smooth(span(t, hitAt - 0.45, hitAt));
              hero.place(lerp(wait[0], hit[0], lunge), lerp(wait[1], hit[1], lunge) + 0.25 * smooth(span(t, hitAt, hitAt + 0.45)), FACE_FIELD);
              hero.set(tackle(span(t, hitAt - 0.3, hitAt + 0.45)));
              if (t > hitAt + 1.1) hero.set(mixPose(ground(), ready(0.2), smooth(span(t, hitAt + 1.1, hitAt + 1.6))));
            }
            // Le maul, privé de ballon, se défait.
            const undone = smooth(span(t, hitAt, hitAt + 0.7));
            all.forEach((player) => player !== carrier && player.set(mixPose(player.current, Object.values(pack).includes(player) ? ready(0.2) : dejected(), undone)));
          } else {
            // Il attend ; personne ne sort, le maul le passe. Il suit, à reculons.
            hero.place(backed[0], Math.min(backed[1], at - 1.6), FACE_FIELD + 0.25);
            hero.set(t > 0.7 && at < wait[1] + 1.6 ? run(at / 2.3, 0.25) : hero.current);
            if (!scored && t > 3) hero.set(mixPose(hero.current, dejected(), smooth(span(t, 3, 3.4))));
          }
        }

        // Le maul va au bout : leur 8 sort du paquet, côté caméra, et aplatit dans l'en-but.
        if (scored) {
          const peel = smooth(span(t, peelAt, peelAt + 0.5));
          const landing = [mx - 2.2, 0.6];
          const start = [mx, at + 2.1];
          if (t > peelAt) {
            carrier.place(lerp(start[0], landing[0], peel), lerp(start[1], landing[1], peel), FACE_LINE);
            const flat = span(t, peelAt + 0.5, flatAt);
            carrier.set(flat > 0 ? dive(flat) : run(t * 3, 0.7, "two"));
            if (flat > 0) world.ballAt(carrier.local(0, 0.2, lerp(0.55, 1.75, smooth(flat)), ball), new THREE.Vector3(1, 0, 0));
            else world.ballAt(carried(carrier, "two", ball), new THREE.Vector3(1, 0, 0));
          }
          const after = smooth(span(t, flatAt + 0.1, flatAt + 0.6));
          if (after > 0) {
            Object.values(pack).forEach((player) => player.set(mixPose(player.current, dejected(), after)));
            hero.set(mixPose(hero.current, dejected(), after));
            [them[1], them[2], them[3], them[4], them[5], them[6], them[7]].forEach((player, i) => player.set(mixPose(player.current, cheer(t * 1.5 + i * 0.2), after)));
            if (t > flatAt + 1) carrier.set(cheer(t * 1.5));
          }
          y = 0;
        }

        // La caméra suit l'avant du maul quand il avance.
        if (!stalled) look = [mx, Math.max(1.5, at + 0.5)];

        // --- L'arbitre -------------------------------------------------------------
        refAt(at);
        ref.card.visible = yellow && t > cardAt;
        if (scored) {
          ref.set(t > flatAt ? tryAward(smooth(span(t, flatAt, flatAt + 0.3))) : run(at / 2.3, 0.3));
          ref.place(mx + 3.6, Math.max(at + 0.6, 1), -Math.PI / 2);
        } else if (whistled) {
          ref.set(yellow && t > cardAt ? card(smooth(span(t, cardAt, cardAt + 0.3))) : t > callAt ? signal(-1, smooth(span(t, callAt, callAt + 0.3))) : ready(0.1));
        } else if (at !== front && !stalled) ref.set(run(at / 2.3, 0.25));
        else ref.set(ready(0.1));
        return broadcast(look[0], look[1], { far: 0.72, fov: 31, y });
      },
    };
  }

  return { setup, preview, outcome: outcomeFor };
}
