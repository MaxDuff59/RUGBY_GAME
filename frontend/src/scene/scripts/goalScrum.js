import * as THREE from "three";

import { card, cheer, crouch, dejected, dive, mixPose, pass, pose, ready, run, signal, tryAward, whistle } from "../rig.js";
import { FACE_FIELD, FACE_LINE, broadcast, carried, keys, lerp, lob, penaltyAgainst, reaction, route, runner, smooth, span } from "./common.js";
import { halfBack, scrum } from "./setPieces.js";

// Carrière de joueur, « Mêlée sur notre ligne » (goal_scrum) : mêlée à cinq mètres de
// notre ligne (z = 0), introduction pour eux. Le joueur incarné est à sa place dans le
// paquet. Pousser à la limite (leur mêlée recule, le ballon nous revient ; ou il se
// relève trop tôt), tenir sans risque (rien ne bouge ; ou le paquet recule, jusqu'à
// l'essai de pénalité de poussée), écrouler (l'arbitre fait rejouer ; ou il a tout vu).
//
// Ici c'est l'adversaire qui pousse vers notre ligne : `scrum` reçoit les packs inversés.

// Un groupe écroulé : à genoux, le buste à plat, la tête dans l'herbe.
export const HEAP = pose({ y: -0.62, lean: 1.42, legL: 1.5, legR: 1.3, knL: 2.3, knR: 2.1, armL: 1.6, armR: 1.5, abL: 0.3, abR: 0.3, elL: 0.5, elR: 0.5, nod: -0.5 });

// Nos avants : le joueur incarné à la place `slot` (son numéro, s'il est avant), celui
// qui la tenait à la sienne.
export function forwards(world, heroNo, slot) {
  const ours = {};
  const isForward = heroNo >= 1 && heroNo <= 8;
  for (let n = 1; n <= 8; n++) {
    const number = n === slot ? heroNo : isForward && n === heroNo ? slot : n;
    ours[n] = world.player("us", number, { hero: n === slot });
  }
  const theirs = {};
  for (let n = 1; n <= 8; n++) theirs[n] = world.player("them", n);
  return { ours, theirs, hero: ours[slot] };
}

export function buildGoalScrum(world, data) {
  const rng = world.rng;
  const s = rng() < 0.5 ? -1 : 1;
  const sx = s * (4 + rng() * 7);
  const cz = 5;
  const heroNo = data.hero ?? 3;
  const { ours, theirs, hero } = forwards(world, heroNo, heroNo >= 1 && heroNo <= 8 ? heroNo : 3);
  // Le repère du joueur incarné se voit à travers le paquet.
  hero.marker.material.depthTest = false;
  hero.marker.renderOrder = 3;
  const theirNine = world.player("them", 9);
  const theirTen = world.player("them", 10);
  const nine = world.player("us", 9);
  const ten = world.player("us", 10);
  const ref = world.player("ref");

  const feeder = [sx - 1.1, cz + 0.2];
  const nineSpot = [sx - 2.1, cz - 1.5];
  const tenSpot = [sx - 7.5, 1.2];
  // Leur ouvreur de l'autre côté du paquet : côté caméra, il cacherait les voies.
  const theirTenSpot = [sx + 7, cz + 6];
  const ball = new THREE.Vector3();
  const from = new THREE.Vector3();
  const to = new THREE.Vector3();
  const across = new THREE.Vector3(1, 0, 0);
  // Le paquet haut dans l'image : les voies couvrent le bas.
  const shot = broadcast(sx, cz + 0.5, { far: 0.72, fov: 30, y: -0.9 });
  const camera = keys([
    [0, [sx - 50, 24, cz + 30, sx * 0.6, 0, cz, 44]],
    [1.4, [...shot.pos, ...shot.look, shot.fov]],
  ]);
  // Leur pack devant (côté +z) pousse vers notre ligne : ils tiennent ici le rôle de `ours`.
  const packs = (options) => scrum(theirs, ours, sx, cz, options);
  const refAt = (mx, mz) => ref.place(mx + 2.7, mz + 0.4, -Math.PI / 2);
  // Le ballon d'introduction, à bout de bras côté ligne : le 9 tourne le dos à la caméra,
  // à ses pieds on ne le verrait pas.
  const readyBall = (out) => theirNine.local(0.42, 0.62, 0.3, out);

  function setupFrame(t) {
    // « Flexion, liez, jeu » : les packs s'approchent, se lient, l'impact.
    const engage = smooth(span(t, 0.5, 0.95));
    packs({ engage, phase: t });
    theirNine.place(...feeder, Math.PI / 2 + 0.3).set(t > 1 ? halfBack : ready(0.3));
    theirTen.place(...theirTenSpot, FACE_LINE).set(ready(0.3));
    nine.place(...nineSpot, FACE_FIELD).set(ready(0.5));
    ten.place(...tenSpot, FACE_FIELD).set(ready(0.4));
    refAt(sx, cz).set(ready(0.1));
    ref.card.visible = false;
    world.ballAt(t > 1 ? readyBall(ball) : carried(theirNine, "two", ball), new THREE.Vector3(0, 0, 1));
    const [cx, cy, cz2, lx, ly, lz, fov] = camera(t);
    return { pos: [cx, cy, cz2], look: [lx, ly, lz], fov };
  }

  const setup = {
    duration: 1.4,
    frame: setupFrame,
    cues: [
      { at: 0.1, run: () => world.crowd(world.pressure > 1 ? "standing" : "seated") },
      { at: 0.95, run: () => world.sound("impact") },
    ],
  };

  function preview(key) {
    const draw = world.draw;
    if (key === "shove") return [draw.arrow([sx - 2.6, cz - 2.8], [sx - 2.6, cz + 3], 2.4), draw.mark([sx, cz + 2.4], 0.7)];
    if (key === "hold_scrum") return [draw.mark([sx, cz - 2.5], 1.1), draw.path([[sx - 2.6, cz], [sx + 2.6, cz]], { width: 0.3 })];
    return [draw.mark([sx, cz], 1.9), draw.mark([sx, cz], 1.1)];
  }

  function outcomeFor(key, result) {
    const { success, effect } = result;
    const feedAt = 0.3;
    const hookAt = feedAt + 0.22;
    const heel = hookAt + 0.4; // le ballon est au pied de leur 8
    const conceded = !success && key === "hold_scrum" && effect === "try_conceded";
    const yellow = !success && effect === "yellow";
    const whistled = !success && (key === "collapse" || effect === "penalty_conceded");
    const collapsing = key === "collapse";
    const callAt = collapsing ? 1.25 : 1.4;
    const rise = 0.95; // il se relève trop tôt
    const cardAt = callAt + 1.3;
    const peelAt = 2.75; // leur 8 lâche la mêlée, sur notre ligne
    const scoredAt = peelAt + 0.95;
    const duration = conceded ? scoredAt + 1.9 : yellow ? cardAt + 1.5 : 3.6;

    // De combien leur mêlée a gagné de terrain (négatif : elle a reculé).
    const pushAt = (t) => {
      const step = smooth(span(t, 0.5, 1.5));
      if (key === "shove") return success ? -2.6 * step : 0.9 * smooth(span(t, 0.95, 1.7));
      if (key === "collapse") return 0.15 * step;
      if (success) return 0.04 * Math.sin(t * 9) * step;
      return step + (conceded ? 5.4 * smooth(span(t, 1.5, 3.0)) : 0);
    };

    const cues = [];
    if (key === "collapse") cues.push({ at: 0.85, run: () => world.sound("impact") });
    if (conceded) {
      cues.push({ at: 1.5, run: () => world.crowd("standing") });
      cues.push({
        at: scoredAt,
        run: () => {
          world.sound("whistle", true);
          reaction(world, false);
        },
      });
    } else if (whistled) cues.push({ at: callAt, run: () => penaltyAgainst(world, "us") });
    else if (collapsing) {
      cues.push({ at: callAt, run: () => world.sound("whistle") });
      cues.push({ at: callAt + 0.3, run: () => world.crowd("standing") });
    } else cues.push({ at: 1.5, run: () => reaction(world, success) });

    return {
      duration,
      cues,
      frame(t) {
        setupFrame(1.4);
        const push = pushAt(t);
        const wheel = !success && key === "hold_scrum" ? 0.14 * smooth(span(t, 0.9, 1.6)) : 0;
        const [mx, mz] = packs({ push, wheel, drive: 1, phase: t * 1.3 });
        const pack = [...Object.values(theirs), ...Object.values(ours)];
        const eight = theirs[8];
        // Le pied de leur 8, où le talonneur envoie le ballon.
        const foot = ball.clone().set(mx, 0.12, mz + 2);
        let spot = shot;

        // --- Les joueurs ---------------------------------------------------------------
        if (collapsing) {
          // Tout le paquet descend, front contre front, puis se relève si on rejoue.
          const fall = smooth(span(t, 0.8, 1.15));
          const up = success ? smooth(span(t, 2.1, 2.7)) : smooth(span(t, callAt + 0.6, callAt + 1.1));
          pack.forEach((player) => {
            const lying = mixPose(player.current, HEAP, fall);
            player.set(mixPose(lying, ready(0.25), up));
          });
        }
        if (key === "shove" && !success) {
          // Lui seul se redresse, le paquet continue sans lui.
          const k = smooth(span(t, rise, rise + 0.35));
          hero.set(mixPose(hero.current, ready(0.3), k));
        }
        if (key === "shove" && success) {
          // Leur pack recule en se désunissant ; le nôtre se relève, le joueur incarné exulte.
          const k = smooth(span(t, 1.9, 2.4));
          Object.values(theirs).forEach((player) => player.set(mixPose(player.current, dejected(), k)));
          Object.values(ours).forEach((player) => player.set(mixPose(player.current, player === hero ? cheer(t * 1.5) : ready(0.2), k)));
        }
        if (key === "hold_scrum" && success && t > 2.4) {
          const k = smooth(span(t, 2.4, 2.9));
          pack.forEach((player) => player.set(mixPose(player.current, ready(0.25), k)));
        }
        if (key === "hold_scrum" && !success && !conceded && t > 2.4) {
          const k = smooth(span(t, 2.4, 2.9));
          Object.values(ours).forEach((player) => player.set(mixPose(player.current, player === hero ? dejected() : ready(0.25), k)));
          Object.values(theirs).forEach((player) => player.set(mixPose(player.current, ready(0.25), k)));
        }
        if (whistled && key === "shove" && t > callAt + 0.5) {
          // Le jeu est arrêté : tout le monde se relève.
          const k = smooth(span(t, callAt + 0.5, callAt + 1));
          pack.forEach((player) => player !== hero && player.set(mixPose(player.current, ready(0.2), k)));
        }

        // --- Le ballon -----------------------------------------------------------------
        const picksUp = (at) => {
          // Leur 9 fait le tour et ramasse au pied du 8.
          const k = smooth(span(t, at - 0.55, at));
          const bend = [mx - 0.55, mz + 2.45];
          theirNine.place(lerp(feeder[0], bend[0], k), lerp(feeder[1], bend[1], k), lerp(Math.PI / 2 + 0.3, FACE_LINE, k));
          theirNine.set(t < at + 0.25 ? (k < 1 ? run(t * 2.5, 0.4) : crouch(1)) : ready(0.25));
        };
        const feed = t < feedAt;
        if (feed) world.ballAt(readyBall(ball), new THREE.Vector3(0, 0, 1));
        else if (t < hookAt) {
          readyBall(from);
          world.ballAt(ball.lerpVectors(from, to.set(mx, 0.12, mz), span(t, feedAt, hookAt)), across);
        } else if (key === "shove" && success) {
          // Le ballon reste où il est : c'est notre pack qui passe dessus, notre 9 ramasse.
          const lie = to.set(sx, 0.12, cz + 0.55);
          const pick = 2.0;
          const k = smooth(span(t, 1.45, pick - 0.05));
          const bend = [sx - 0.55, cz + 0.35];
          nine.place(lerp(nineSpot[0], bend[0], k), lerp(nineSpot[1], bend[1], k), FACE_FIELD - Math.PI / 2 * k);
          nine.set(k < 1 ? run(t * 2.5, 0.4) : t < pick + 0.15 ? crouch(1) : pass(span(t, pick + 0.15, pick + 0.45), -1));
          const toTen = route([tenSpot, [tenSpot[0] - 0.5, tenSpot[1] + 3.5]]);
          runner(ten, toTen, t, 2.2, 3.6, { from: 0.4, to: 0.5, speed: 0.5, carry: t > 2.7 ? "two" : "none" });
          if (t < 2.7) ten.heading = FACE_FIELD;
          if (t < pick + 0.15) world.ballAt(t < 0.92 ? ball.lerpVectors(to.clone().set(sx, 0.12, cz), lie, span(t, hookAt, 0.92)) : lie, across);
          else if (t < 2.7) world.ballAt(lob(carried(nine, "two", from), carried(ten, "two", to), 0.6, span(t, pick + 0.15, 2.7), ball), across);
          else world.ballAt(carried(ten, "two", ball), across);
        } else if (conceded && t > peelAt - 0.4) {
          world.ballAt(carried(eight, "low", ball), across);
        } else if (t < heel) {
          world.ballAt(ball.lerpVectors(to.set(mx, 0.12, mz), foot, span(t, hookAt, heel)), across);
        } else if (collapsing) {
          // Le jeu arrêté, leur 9 reprend le ballon : l'introduction à refaire, ou la pénalité.
          const pick = callAt + 0.9;
          picksUp(pick);
          world.ballAt(t < pick ? foot : carried(theirNine, "two", ball), across);
        } else if (whistled) {
          const pick = callAt + 0.7;
          picksUp(pick);
          world.ballAt(t < pick ? foot : carried(theirNine, "two", ball), across);
        } else {
          // Le ballon gagné par leur pack : leur 9 sert leur ouvreur.
          const pick = 2.1;
          picksUp(pick);
          if (t > pick + 0.15) theirNine.set(pass(span(t, pick + 0.15, pick + 0.45), 1));
          const toTen = route([theirTenSpot, [theirTenSpot[0] + 0.3, theirTenSpot[1] - 3]]);
          runner(theirTen, toTen, t, 2.2, 3.6, { from: 0.4, to: 0.6, speed: 0.6, carry: t > 2.75 ? "two" : "none" });
          if (t <= 2.2) theirTen.set(ready(0.3));
          if (t < pick + 0.15) world.ballAt(foot, across);
          else if (t < 2.75) world.ballAt(lob(carried(theirNine, "two", from), carried(theirTen, "two", to), 0.6, span(t, pick + 0.15, 2.75), ball), across);
          else world.ballAt(carried(theirTen, "two", ball), across);
        }

        // --- L'essai sur la poussée ------------------------------------------------------
        if (conceded) {
          // Leur 8 lâche la mêlée et aplatit sur le côté, le paquet franchit notre ligne.
          const k = smooth(span(t, peelAt, peelAt + 0.45));
          const start = [mx, mz + 2.45];
          const landing = [mx - 1.9, 0.75];
          if (t > peelAt) {
            eight.place(lerp(start[0], landing[0], k), lerp(start[1], landing[1], k), FACE_LINE);
            const flat = span(t, peelAt + 0.45, scoredAt);
            eight.set(flat > 0 ? dive(flat) : run(t * 3, 0.7, "two"));
            if (flat > 0) world.ballAt(eight.local(0, 0.2, lerp(0.55, 1.75, smooth(flat)), ball), across);
          }
          nine.place(nineSpot[0] - 1, lerp(nineSpot[1], 0.5, smooth(span(t, 1.5, 3))), FACE_FIELD);
          const after = smooth(span(t, scoredAt + 0.1, scoredAt + 0.6));
          if (after > 0) {
            Object.values(ours).forEach((player) => player.set(mixPose(player.current, dejected(), after)));
            Object.values(theirs).forEach((player, i) => player !== eight && player.set(mixPose(player.current, cheer(t * 1.5 + i * 0.2), after)));
            if (t > scoredAt + 0.9) eight.set(cheer(t * 1.5));
          }
          spot = broadcast(sx - 0.5, Math.max(1, mz + 0.8), { far: 0.72, fov: 30, y: 0 });
        }

        // --- L'arbitre ----------------------------------------------------------------
        // À la faute, il contourne le paquet par notre côté : debout, le paquet le cacherait.
        const walk = whistled ? smooth(span(t, callAt, callAt + 0.7)) : 0;
        ref.place(mx + lerp(2.7, 0.7, walk), mz + lerp(0.4, -3.8, walk), -Math.PI / 2);
        const sign = smooth(span(t, callAt + 0.6, callAt + 0.9));
        if (conceded) {
          ref.set(t > scoredAt ? tryAward(smooth(span(t, scoredAt, scoredAt + 0.3))) : ready(0.15));
        } else if (yellow && t > cardAt) {
          ref.set(card(smooth(span(t, cardAt, cardAt + 0.3))));
        } else if (whistled) {
          // Vers leur attaque (-z) : son bras droit, face à la caméra.
          ref.set(walk > 0 && walk < 1 ? run(t * 3, 0.4) : t > callAt ? signal(-1, sign) : ready(0.1));
        } else if (collapsing) {
          // Le sifflet, sans bras levé : on rejoue.
          ref.set(t > callAt ? whistle(1 - span(t, callAt + 0.9, callAt + 1.3)) : ready(0.1));
        } else ref.set(ready(0.1));
        ref.card.visible = yellow && t > cardAt;
        if (whistled && t > callAt + 0.5) {
          // Le fautif sort du paquet et vient devant l'arbitre, tête basse.
          const k = smooth(span(t, callAt + 0.5, callAt + 1.2));
          const [hx, hz] = [hero.root.position.x, hero.root.position.z];
          const before = [mx - 1.8, mz - 3.8];
          hero.place(lerp(hx, before[0], k), lerp(hz, before[1], k), k < 1 ? Math.atan2(before[0] - hx, before[1] - hz) : Math.PI / 2);
          hero.set(k < 1 ? run(t * 2.5, 0.3) : dejected());
        }
        return spot;
      },
    };
  }

  return { setup, preview, outcome: outcomeFor };
}
