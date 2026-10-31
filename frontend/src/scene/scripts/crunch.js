import * as THREE from "three";

import { BALL_A, TEE_TOP } from "../ball.js";
import { TOUCH } from "../field.js";
import { cheer, crouch, dejected, dive, ground, kick, pass, pose, ready, signal, tackle, tryAward } from "../rig.js";
import {
  FACE_LINE,
  carried,
  clamp,
  goalKick,
  headingTo,
  keys,
  lerp,
  lob,
  route,
  runner,
  seeded,
  smooth,
  span,
} from "./common.js";
import { halfBack, lineout, lineoutSpots, maul, scrum } from "./setPieces.js";

// Le choix crucial : une pénalité pour nous dans une fin de match serrée.
//
// Mise en place : l'arbitre siffle et lève le bras, nos joueurs se regroupent autour
// du ballon, les leurs reculent de dix mètres. Les quatre suites : les perches (le
// buteur pose le ballon sur son tee, élan, frappe : la physique de ball.js, réglée pour
// donner l'issue tirée), la touche (coup de pied en touche, alignement, sauteur soulevé,
// maul), la mêlée à cinq mètres (huit contre huit, poussée), ou la jouer vite (petite
// tape, passes vers l'aile, l'ailier au coin).
//
// `data` : le numéro du buteur. Le résultat : `scored` (les points, ou l'essai).

const HOLD_BALL = pose({ armL: 0.75, armR: 0.75, elL: 1.1, elR: 1.1, abL: -0.15, abR: -0.15 });
const STAND = pose();

export function buildCrunch(world, data) {
  const rng = world.rng;
  const s = rng() < 0.5 ? -1 : 1; // côté de la pénalité
  const open = -s; // le grand côté
  const x0 = s * (5 + rng() * 8);
  const z0 = 27 + rng() * 5;
  const kickerNo = data.kickerNumber ?? 10;
  const holderNo = kickerNo === 9 ? 2 : 9;
  // Face à la ligne d'essai, notre gauche est vers -x : l'ailier gauche porte le 11.
  const wingNo = open < 0 ? 11 : 14;
  const theirWing = open < 0 ? 14 : 11;

  const ours = {};
  const theirs = {};
  const add = (map, team, n) => (map[n] ??= world.player(team, n));
  for (const n of [holderNo, kickerNo, 2, 7, 12, 13, wingNo]) add(ours, "us", n);
  for (const n of [10, 7, 12, 13, theirWing, 15]) add(theirs, "them", n);
  const ref = world.player("ref");
  const holder = ours[holderNo];
  const kicker = ours[kickerNo];
  const setupCast = [...new Set([...Object.values(ours), ...Object.values(theirs)])];

  // --- Mise en place -----------------------------------------------------------------
  const paths = {
    holder: route([[x0 + s * 1.4, z0 + 3], [x0, z0 + 0.4]]),
    ref: route([[x0 - s * 3, z0 - 4.5], [x0 + s * 2.6, z0 - 1.2]]),
    kicker: route([[x0 + open * 6, z0 + 6], [x0 + open * 1.5, z0 + 1.9]]),
    2: route([[x0 + s * 4.5, z0 + 4], [x0 + s * 1.4, z0 + 1.7]]),
    7: route([[x0 + s * 1.5, z0 + 7], [x0 - s * 0.2, z0 + 2.6]]),
    12: route([[x0 + open * 10, z0 + 5], [x0 + open * 8, z0 + 2.6]]),
    13: route([[x0 + open * 16, z0 + 6], [x0 + open * 14.5, z0 + 3.2]]),
    wing: route([[open * 29.5, z0 + 3], [open * 28.5, z0 - 0.5]]),
  };
  const retreat = {
    10: route([[x0 + open * 2, z0 - 2.5], [x0 + open * 2.5, z0 - 10]]),
    7: route([[x0 + s * 2.2, z0 - 2], [x0 + s * 2.6, z0 - 10]]),
    12: route([[x0 + open * 8, z0 - 4], [x0 + open * 8.5, z0 - 10.5]]),
    13: route([[x0 + open * 14, z0 - 5], [x0 + open * 14.5, z0 - 11]]),
    [theirWing]: route([[open * 27, z0 - 6], [open * 27, z0 - 11.5]]),
    15: route([[x0 * 0.2, z0 - 19], [x0 * 0.2 + open * 3, z0 - 22]]),
  };
  // Caméra de retransmission : en hauteur, de biais derrière le point de pénalité, les
  // perches au fond. Le regard vise sous le groupe pour le garder au-dessus des voies.
  const focus = [x0 * 0.75, -1.2, z0 * 0.72];
  const broadcast = [x0 - 20, 13, z0 + 19];
  const setupCamera = keys([
    [0, [x0 - 52, 32, z0 + 50, focus[0], 0, focus[2] - 4, 44]],
    [1.5, [...broadcast, ...focus, 34]],
  ]);
  const refSide = -s; // le bras levé vers notre attaque (vers -z)
  const refFacing = headingTo(x0 + s * 2.6, 0, x0, 0);
  const ballPoint = new THREE.Vector3();

  function setupFrame(t) {
    setupCast.forEach((player) => (player.visible = true));
    runner(holder, paths.holder, t, 0, 0.8, { carry: "two", from: 0.7, to: 0, speed: 0.35 });
    if (t >= 0.8) holder.place(x0, z0 + 0.4, headingTo(x0, z0 + 0.4, x0 + s * 2.6, z0 - 1.2)).set(HOLD_BALL);
    runner(ref, paths.ref, t, 0, 0.75, { from: 0.9, to: 0, speed: 0.5 });
    if (t >= 0.75) ref.place(x0 + s * 2.6, z0 - 1.2, refFacing).set(signal(refSide, smooth(span(t, 0.75, 1.1))));
    runner(kicker, paths.kicker, t, 0, 1.1, { from: 0.8, to: 0, speed: 0.45 });
    if (t >= 1.1) kicker.place(x0 + open * 1.5, z0 + 1.9, headingTo(x0 + open * 1.5, z0 + 1.9, x0, z0)).set(ready(0.15));
    for (const n of [2, 7, 12, 13]) {
      if (ours[n] === kicker || ours[n] === holder) continue;
      runner(ours[n], paths[n], t, 0, 1.2, { from: 0.7, to: 0, speed: 0.4 });
      if (t >= 1.2) ours[n].set(ready(0.2));
    }
    if (ours[wingNo] !== kicker) {
      runner(ours[wingNo], paths.wing, t, 0, 1.3, { from: 0.6, to: 0, speed: 0.4 });
      if (t >= 1.3) ours[wingNo].place(open * 28.5, z0 - 0.5, FACE_LINE).set(ready(0.4));
    }
    for (const [n, path] of Object.entries(retreat)) {
      const player = theirs[n];
      runner(player, path, t, 0, 1.4, { from: 0.9, to: 0.1, speed: 0.55 });
      // Arrivés, ils se retournent vers nous.
      const turn = smooth(span(t, 1.05, 1.5));
      if (turn > 0) {
        player.root.rotation.y = player.heading = lerp(FACE_LINE, FACE_LINE + Math.PI, turn);
        if (t >= 1.4) player.set(ready(0.45));
      }
    }
    world.ballAt(carried(holder, "two", ballPoint), new THREE.Vector3(1, 0, 0));
    world.tee.visible = false;
    const [cx, cy, cz, lx, ly, lz, fov] = setupCamera(t);
    return { pos: [cx, cy, cz], look: [lx, ly, lz], fov };
  }

  const theyAreHome = !world.homeIsUs;
  const setup = {
    duration: 1.5,
    frame: setupFrame,
    cues: [
      { at: 0.05, run: () => world.sound("whistle", true) },
      {
        at: 0.4,
        run: () => {
          // Le public siffle la pénalité quand elle est contre son club.
          if (theyAreHome) {
            world.crowd("boo", "them");
            world.sound("boo");
          } else {
            world.crowd("standing");
          }
        },
      },
    ],
  };

  // --- Aperçus ------------------------------------------------------------------------
  const tee = new THREE.Vector3(x0, TEE_TOP * 1.4 + BALL_A * 1.1, z0);
  let aimed = null;
  const sx = clamp(x0, -18, 18);
  const lineoutZ = 5;
  const spots = lineoutSpots(s, lineoutZ);
  const corner = [open * 26, -1.6];

  function preview(key) {
    const draw = world.draw;
    if (key === "kick") {
      aimed ??= goalKick(tee, world.wind, true, seeded(7));
      const points = aimed.points(1.1);
      // La courbe dans l'air, et son ombre sur la pelouse jusqu'aux perches.
      return [draw.arc(points), draw.path(points.map(([x, , z]) => [x, z]), { width: 0.3 }), draw.mark([0, 0], 1.2)];
    }
    if (key === "touch") {
      const from = new THREE.Vector3(x0, 1.2, z0);
      const to = new THREE.Vector3(s * (TOUCH + 2), 0.5, lineoutZ + 1);
      const arc = [];
      for (let i = 0; i <= 16; i++) arc.push(lob(from, to, 13, i / 16).toArray());
      return [draw.arc(arc), draw.mark(spots.jumper), draw.arrow([spots.jumper[0], lineoutZ + 2.2], [spots.jumper[0], -0.6], 2.4)];
    }
    if (key === "scrum") return [draw.mark([sx, lineoutZ], 1.6), draw.arrow([sx, lineoutZ + 2.8], [sx, -0.8], 3)];
    return [
      draw.path([
        [x0, z0],
        [x0 + open * 5, z0 - 1.2],
        [x0 + open * 12, z0 - 4],
        [open * 23, z0 * 0.4],
        corner,
      ]),
      draw.mark(corner),
    ];
  }

  // --- Les suites ---------------------------------------------------------------------
  // Qui se réjouit : le public de notre club (`us`), et l'autre public sinon.
  const celebrate = (scored) => {
    if (scored) {
      world.crowd("cheer", "us");
      world.sound(world.homeIsUs ? "roar" : "groan");
    } else {
      world.crowd(world.homeIsUs ? "seated" : "cheer", world.homeIsUs ? "us" : "them");
      world.sound(world.homeIsUs ? "groan" : "roar");
    }
  };
  // Les joueurs, après coup : bras levés ou mains sur les hanches.
  const aftermath = (players, scored, t, from) => {
    if (t < from) return;
    players.forEach((player, i) => player.set(scored ? cheer(t * 1.6 + i * 0.3) : dejected()));
  };
  const fade = (t, at) => {
    // Fondu au noir de at - 0.25 à at, puis retour.
    world.exposure(t < at ? 1 - smooth(span(t, at - 0.25, at)) : smooth(span(t, at, at + 0.25)));
  };

  function kickOutcome(result) {
    const flight = goalKick(tee, world.wind, result.scored, rng);
    const back = new THREE.Vector3(x0, 0, z0).normalize();
    const kickAt = 2.45;
    const crossAt = kickAt + flight.crossAt;
    const spotAt = [x0 + back.x * 0.6, z0 + back.z * 0.6];
    const stepBack = [x0 + back.x * 3.4 + open * back.z * 1.2, z0 + back.z * 3.4 - open * back.x * 1.2];
    const toBall = route([stepBack, [x0 + back.x * 0.35, z0 + back.z * 0.35]]);
    const walkIn = route([[x0 + open * 1.5, z0 + 1.9], spotAt]);
    const rest = new THREE.Quaternion().setFromUnitVectors(new THREE.Vector3(0, 1, 0), new THREE.Vector3(-back.x * 0.2, 1, -back.z * 0.2).normalize());
    const q = new THREE.Quaternion();
    // Derrière le buteur, un peu de biais et en hauteur : lui en bas, les perches au fond.
    const camBehind = [x0 + back.x * 15 - back.z * 3, 4.6, z0 + back.z * 15 + back.x * 3];
    const duration = crossAt + 2.2;
    return {
      duration,
      cues: [
        { at: kickAt, run: () => world.sound("kick") },
        { at: crossAt, run: () => celebrate(result.scored) },
      ],
      frame(t) {
        setupFrame(1.5);
        world.exposure(1);
        // Le porteur s'écarte, le buteur vient poser le ballon sur le tee.
        runner(holder, route([[x0, z0 + 0.4], [x0 + s * 4, z0 - 1.5]]), t, 0.1, 1.0, { from: 0.2, to: 0, speed: 0.3 });
        if (t > 1.0) holder.set(t > crossAt ? STAND : ready(0.1));
        // Les autres s'écartent de la ligne entre le buteur et les perches.
        [2, 7].forEach((n, i) => {
          const player = ours[n];
          if (player === kicker || player === holder) return;
          const spot = [player.root.position.x, player.root.position.z];
          runner(player, route([spot, [x0 + open * (4 + i * 1.6), z0 - 1.5 - i]]), t, 0.1, 1.2, { from: 0.3, to: 0, speed: 0.3 });
          if (t > 1.2) player.set(ready(0.1));
        });
        if (t < 0.7) {
          runner(kicker, walkIn, t, 0, 0.7, { from: 0.4, to: 0, speed: 0.3 });
        } else if (t < 1.2) {
          kicker.place(spotAt[0], spotAt[1], headingTo(spotAt[0], spotAt[1], 0, 0)).set(crouch(smooth(span(t, 0.7, 0.9)) * (1 - smooth(span(t, 1.05, 1.2)))));
        } else if (t < 1.6) {
          // Il recule, les yeux sur les perches.
          const k = smooth(span(t, 1.2, 1.6));
          kicker.place(lerp(spotAt[0], stepBack[0], k), lerp(spotAt[1], stepBack[1], k), headingTo(stepBack[0], stepBack[1], x0, z0)).set(STAND);
        } else if (t < 2.0) {
          kicker.place(stepBack[0], stepBack[1], headingTo(stepBack[0], stepBack[1], x0, z0)).set(ready(0.12));
        } else if (t < kickAt) {
          runner(kicker, toBall, t, 2.0, kickAt, { from: 0.4, to: 0.9, speed: 0.6 });
        } else {
          kicker.place(toBall.at(toBall.total).x, toBall.at(toBall.total).z, headingTo(x0, z0, 0, 0)).set(kick(span(t, kickAt - 0.12, kickAt + 0.4)));
        }
        if (t >= crossAt + 0.4) aftermath([kicker, ...[2, 7, 12, 13].map((n) => ours[n])], result.scored, t, crossAt + 0.4);
        if (t >= crossAt && result.scored) ref.set(tryAward(smooth(span(t, crossAt, crossAt + 0.4))));
        else ref.set(pose());

        world.tee.visible = t > 0.85;
        world.tee.position.set(x0, 0, z0);
        if (t < 0.9) world.ballAt(carried(kicker, "two", ballPoint), new THREE.Vector3(1, 0, 0));
        else if (t < kickAt) world.ballAt(tee, new THREE.Vector3(-back.x * 0.2, 1, -back.z * 0.2));
        else {
          flight.at(t - kickAt, ballPoint, q, rest);
          world.ball.position.copy(ballPoint);
          world.ball.quaternion.copy(q);
        }
        // La caméra suit le ballon à moitié : les perches restent dans le cadre.
        const follow = smooth(span(t, kickAt, kickAt + 0.6)) * (1 - smooth(span(t, crossAt + 0.3, crossAt + 1.4)));
        return {
          pos: camBehind,
          look: [lerp(x0 * 0.3, ballPoint.x * 0.5, follow), lerp(2, Math.min(ballPoint.y, 9) * 0.6, follow), lerp(z0 * 0.3, ballPoint.z * 0.5, follow)],
          fov: 32,
        };
      },
    };
  }

  // La touche, le maul.
  function touchOutcome(result) {
    const kickAt = 0.55;
    const landAt = 2.0;
    const swap = 2.3;
    const from = new THREE.Vector3(x0, 1.0, z0);
    const out = new THREE.Vector3(s * (TOUCH + 2.5), 0.4, lineoutZ + 1.2);
    // Le pack : nos avants 1 à 8 et six des leurs. Les joueurs de la mise en place
    // sortent du champ au fondu.
    const pack = { 2: ours[2], 7: ours[7] };
    for (const n of [1, 4, 5, 6, 8]) pack[n] = world.player("us", n);
    const their = {};
    for (const n of [1, 4, 5, 6, 8]) their[n] = world.player("them", n);
    their[7] = theirs[7];
    const lineCast = [...Object.values(pack), ...Object.values(their), ref];
    const thrower = pack[2];
    const throwAt = 0.3;
    const catchAt = 0.75;
    const maulAt = 1.0;
    const driveAt = 1.35;
    const end = result.scored ? -0.7 : 1.6;
    const groundAt = driveAt + 1.7;
    const starts = new Map();
    const maulFocus = [spots.jumper[0], 0.8, 3];
    const throwerHands = new THREE.Vector3();
    const catchPoint = new THREE.Vector3();
    const duration = swap + groundAt + 1.9;
    return {
      duration,
      cues: [
        { at: kickAt, run: () => world.sound("kick") },
        { at: swap + 0.6, run: () => world.crowd("standing") },
        { at: swap + driveAt, run: () => world.sound("impact") },
        {
          at: swap + groundAt + (result.scored ? 0.35 : 0),
          run: () => {
            world.sound("whistle", true);
            celebrate(result.scored);
          },
        },
      ],
      frame(t) {
        fade(t, swap);
        if (t < swap) {
          setupFrame(1.5);
          lineCast.forEach((player) => player !== ref && !setupCast.includes(player) && (player.visible = false));
          // Le buteur tape en touche.
          holder.set(STAND);
          kicker.place(x0 + open * 0.3, z0 + 0.6, headingTo(x0, z0, out.x, out.z)).set(t < kickAt - 0.3 ? HOLD_BALL : kick(span(t, kickAt - 0.3, kickAt + 0.35), true));
          if (t < kickAt) world.ballAt(carried(kicker, "two", ballPoint), new THREE.Vector3(1, 0, 0));
          else {
            const k = span(t, kickAt, landAt);
            lob(from, out, 13, k, ballPoint);
            world.ballAt(ballPoint, new THREE.Vector3(Math.sin(t * 9), Math.cos(t * 9), 0.3));
          }
          const follow = smooth(span(t, kickAt, landAt));
          return {
            pos: [lerp(broadcast[0], s * 6 - 40, follow), lerp(broadcast[1], 15, follow), lerp(broadcast[2], 24, follow)],
            look: [lerp(focus[0], ballPoint.x * 0.8, follow), lerp(focus[1], 3, follow), lerp(focus[2], ballPoint.z, follow)],
            fov: 34,
          };
        }
        // Après le fondu : la touche à cinq mètres.
        setupCast.forEach((player) => (player.visible = false));
        lineCast.forEach((player) => (player.visible = true));
        const u = t - swap;
        if (u < maulAt) {
          const top = lineout(pack, their, spots, s, u, { throwAt, catchAt });
          thrower.place(spots.thrower[0], spots.thrower[1], (-s * Math.PI) / 2);
          thrower.set(u < throwAt ? pose({ armL: 2.9, armR: 2.9, elL: 0.9, elR: 0.9, lean: -0.15 }) : pose({ armL: lerp(2.9, 1.6, span(u, throwAt, throwAt + 0.2)), armR: lerp(2.9, 1.6, span(u, throwAt, throwAt + 0.2)), lean: 0.2 }));
          thrower.local(0, 2.25, 0.1, throwerHands);
          pack[5].local(0, top + 0.05, 0.15, catchPoint);
          if (u < throwAt) world.ballAt(throwerHands, new THREE.Vector3(0, 1, 0));
          else if (u < catchAt) world.ballAt(lob(throwerHands, catchPoint, 1.4, span(u, throwAt, catchAt), ballPoint), new THREE.Vector3(1, 0.2, 0));
          else world.ballAt(catchPoint, new THREE.Vector3(1, 0, 0));
          [...Object.values(pack), ...Object.values(their)].forEach((player) => starts.set(player, [player.root.position.x, player.root.position.z]));
        } else {
          // Le maul se forme autour du sauteur, puis pousse vers la ligne.
          const k = span(u, maulAt, driveAt);
          const drive = span(u, driveAt, groundAt);
          const front = lerp(lineoutZ, end + 2.4, result.scored ? smooth(drive) : Math.sqrt(drive));
          const center = [spots.jumper[0] - s * 0.6, front - 0.4];
          maul(pack, their, starts, center, k, u * 1.4, 1);
          thrower.place(lerp(spots.thrower[0], center[0], smooth(k)), lerp(spots.thrower[1], center[1] + 2.9, smooth(k)), FACE_LINE);
          const carrier = pack[8];
          if (result.scored && u > groundAt) {
            // Le maul s'écroule dans l'en-but, le numéro 8 aplatit.
            const g = span(u, groundAt, groundAt + 0.4);
            carrier.place(center[0], lerp(center[1] + 2.1, -0.4, smooth(g)), FACE_LINE).set(dive(g));
            for (const player of Object.values(pack)) if (player !== carrier) player.set(cheer(u * 1.5 + player.root.position.x));
            Object.values(their).forEach((player) => player.set(dejected()));
          } else if (!result.scored && u > groundAt) {
            Object.values(pack).forEach((player) => player.set(dejected()));
            Object.values(their).forEach((player, i) => player.set(cheer(u * 1.5 + i)));
          }
          carried(carrier, result.scored && u > groundAt ? "low" : "two", ballPoint);
          world.ballAt(ballPoint, new THREE.Vector3(1, 0, 0));
        }
        // L'arbitre suit, au bord du maul, et lève le bras pour l'essai.
        ref.place(spots.jumper[0] - s * 4, lerp(lineoutZ - 0.5, 0.5, smooth(span(u, maulAt, groundAt))), (s * Math.PI) / 2);
        if (result.scored && u > groundAt + 0.35) ref.set(tryAward(smooth(span(u, groundAt + 0.35, groundAt + 0.7))));
        else if (!result.scored && u > groundAt) ref.set(signal(s > 0 ? 1 : -1, smooth(span(u, groundAt, groundAt + 0.3))));
        else ref.set(ready(0.2));
        return { pos: [maulFocus[0] - 17, 7.5, maulFocus[2] + 10], look: [maulFocus[0] * 0.92, 0.9, lerp(4, 1.5, span(u, maulAt, groundAt))], fov: 30 };
      },
    };
  }

  // La mêlée à cinq mètres.
  function scrumOutcome(result) {
    const swap = 0.25;
    const pack = { 2: ours[2], 7: ours[7] };
    for (const n of [1, 3, 4, 5, 6, 8]) pack[n] = world.player("us", n);
    const their = { 7: theirs[7] };
    for (const n of [1, 2, 3, 4, 5, 6, 8]) their[n] = world.player("them", n);
    const nine = holder;
    const scrumCast = [...Object.values(pack), ...Object.values(their), nine, ref];
    const engageAt = 0.65;
    const feedAt = 0.95;
    const pushAt = 1.35;
    const doneAt = 3.3;
    const cz = lineoutZ;
    const feeder = [sx - 1.1, cz + 0.2];
    const ballPath = new THREE.Vector3();
    const duration = swap + doneAt + 2;
    return {
      duration,
      cues: [
        { at: swap + 0.1, run: () => world.crowd("standing") },
        { at: swap + engageAt, run: () => world.sound("impact") },
        {
          at: swap + doneAt,
          run: () => {
            world.sound("whistle", true);
            celebrate(result.scored);
          },
        },
      ],
      frame(t) {
        if (t < swap) {
          setupFrame(1.5);
          fade(t, swap);
          scrumCast.forEach((player) => !setupCast.includes(player) && player !== ref && (player.visible = false));
          return { pos: broadcast, look: focus, fov: 34 };
        }
        fade(t, swap);
        setupCast.forEach((player) => (player.visible = false));
        scrumCast.forEach((player) => (player.visible = true));
        const u = t - swap;
        const engage = smooth(span(u, engageAt - 0.3, engageAt));
        const drive = span(u, pushAt, doneAt);
        const push = result.scored ? smooth(drive) * (cz + 0.4) : -0.5 * smooth(drive);
        const wheel = result.scored ? 0 : 0.45 * smooth(span(u, 2.2, doneAt));
        const [mx, mz] = scrum(pack, their, sx, cz, { push, wheel, drive: u > pushAt ? 1 : 0, phase: u * 1.3, engage });
        // Le demi de mêlée introduit, puis suit.
        nine.place(feeder[0], feeder[1] - push, Math.PI / 2).set(u < feedAt + 0.2 ? halfBack : ready(0.3));
        const no8 = pack[8];
        if (u < feedAt) world.ballAt(carried(nine, "low", ballPath), new THREE.Vector3(0, 0, 1));
        else if (u < feedAt + 0.5) {
          const k = span(u, feedAt, feedAt + 0.5);
          ballPath.set(lerp(feeder[0] + 0.5, mx, k), 0.12, lerp(feeder[1], mz + 2.2, k));
          world.ballAt(ballPath, new THREE.Vector3(1, 0, 0));
        } else world.ballAt(ballPath.set(mx, 0.12, mz + 2.2), new THREE.Vector3(1, 0, 0));
        if (result.scored && u > doneAt - 0.3) {
          // Le numéro 8 ramasse au pied de la mêlée et aplatit.
          const g = span(u, doneAt - 0.3, doneAt + 0.15);
          no8.place(mx, lerp(mz + 2.3, -0.5, smooth(g)), FACE_LINE).set(dive(g));
          carried(no8, "low", ballPath);
          world.ballAt(ballPath, new THREE.Vector3(1, 0, 0));
          if (u > doneAt + 0.5) Object.values(pack).forEach((player) => player !== no8 && player.set(cheer(u * 1.5 + player.root.position.x)));
        }
        if (!result.scored && u > doneAt + 0.2) Object.values(their).forEach((player, i) => player.set(cheer(u * 1.4 + i)));
        ref.place(mx + 2.6, mz + 0.4, -Math.PI / 2);
        if (result.scored && u > doneAt) ref.set(tryAward(smooth(span(u, doneAt, doneAt + 0.35))));
        else if (!result.scored && u > doneAt) ref.set(signal(1, smooth(span(u, doneAt, doneAt + 0.3))));
        else ref.set(ready(0.25));
        return { pos: [sx - 17, 6.5, cz + 11], look: [sx * 0.95, 0.6, lerp(cz, mz, 0.6)], fov: 30 };
      },
    };
  }

  // La jouer vite : une tape, trois passes vers le grand côté, l'ailier au coin.
  function playOutcome(result) {
    const r1 = kicker;
    const chain = [holder, r1, ours[12], ours[13], ours[wingNo]].filter((player, i, all) => all.indexOf(player) === i);
    const passes = [
      [0.3, 0.6],
      [0.85, 1.15],
      [1.35, 1.65],
      [1.85, 2.15],
    ].slice(0, chain.length - 1);
    const catchSpots = [
      [x0, z0 + 0.4],
      [x0 + open * 4, z0 - 1],
      [x0 + open * 10, z0 - 3.4],
      [x0 + open * 15.5, z0 - 5],
      [open * 24.5, z0 - 7.5],
    ];
    const wing = chain[chain.length - 1];
    const finishAt = 3.4;
    const tackled = [open * 27.2, 3.2];
    const wingRun = route([catchSpots[chain.length - 1], result.scored ? [corner[0], corner[1] + 1.2] : tackled]);
    const chaser = theirs[15];
    const chaseFrom = [x0 * 0.2 + open * 3, z0 - 22];
    const chaseTo = result.scored ? [corner[0] + open * 0.3, corner[1] + 3.6] : [tackled[0] - open * 0.4, tackled[1] - 0.6];
    const a = new THREE.Vector3();
    const b = new THREE.Vector3();
    const duration = finishAt + 1.9;
    return {
      duration,
      cues: [
        { at: 0.05, run: () => world.crowd("standing") },
        { at: finishAt + (result.scored ? 0.35 : 0), run: () => (result.scored ? world.sound("whistle", true) : world.sound("impact")) },
        { at: finishAt + 0.45, run: () => celebrate(result.scored) },
      ],
      frame(t) {
        setupFrame(1.5);
        world.exposure(1);
        // Chacun court vers son point de réception, puis continue en soutien.
        chain.forEach((player, i) => {
          if (i === chain.length - 1) return;
          const [px, pz] = catchSpots[i];
          const next = catchSpots[i + 1];
          const catchAt = i === 0 ? 0 : passes[i - 1][1];
          const start = [player.root.position.x, player.root.position.z];
          if (i > 0) runner(player, route([start, [px, pz]]), t, 0, catchAt, { from: 0.5, to: 1, speed: 0.7, carry: "two" });
          if (t >= catchAt) {
            const releaseAt = passes[i][0];
            const after = route([[px, pz], [px + open * 2, pz - 4]]);
            if (t < releaseAt + 0.2) {
              player.place(px + open * 0.6 * span(t, catchAt, releaseAt), pz - 1.2 * span(t, catchAt, releaseAt), headingTo(px, pz, next[0], next[1]) * 0.4 + FACE_LINE * 0.6);
              player.set(i === 0 && t < 0.3 ? crouch(1 - span(t, 0, 0.3)) : pass(span(t, releaseAt - 0.15, releaseAt + 0.15), open < 0 ? 1 : -1));
            } else runner(player, after, t, releaseAt + 0.2, releaseAt + 1.8, { from: 0.6, to: 0.3, speed: 0.6 });
          }
        });
        const lastCatch = passes[passes.length - 1][1];
        runner(wing, route([[wing.root.position.x, wing.root.position.z], catchSpots[chain.length - 1]]), t, 0, lastCatch, { from: 0.4, to: 1, speed: 0.8, carry: "two" });
        if (t >= lastCatch) {
          if (t < finishAt) runner(wing, wingRun, t, lastCatch, finishAt, { from: 1, to: 1, speed: 1, carry: "one" });
          else if (result.scored) {
            const g = span(t, finishAt, finishAt + 0.45);
            wing.place(corner[0], lerp(corner[1] + 1.2, corner[1], smooth(g)), FACE_LINE).set(t > finishAt + 1.1 ? cheer(t * 1.6) : dive(g));
          } else {
            const g = span(t, finishAt, finishAt + 0.5);
            wing.place(tackled[0], tackled[1] - g * 0.6, FACE_LINE + open * 0.3).set(g < 1 ? tackle(g * 0.6) : ground(true));
          }
        }
        // Leur arrière coupe la course ; il plaque, ou plonge dans le vide.
        runner(chaser, route([chaseFrom, chaseTo]), t, 0.6, finishAt, { from: 0.5, to: 1, speed: 0.95 });
        if (t >= finishAt) {
          const g = span(t, finishAt - 0.1, finishAt + 0.5);
          chaser.place(chaseTo[0], chaseTo[1] + (result.scored ? 0.5 * g : 0.2), headingTo(chaseTo[0], chaseTo[1], tackled[0], tackled[1])).set(g < 1 ? tackle(g) : ground());
        }
        // Les autres défenseurs remontent et glissent.
        for (const n of [10, 12, 13, 7, theirWing]) {
          const player = theirs[n];
          const sx0 = player.root.position.x;
          const sz0 = player.root.position.z;
          runner(player, route([[sx0, sz0], [sx0 + open * 6, sz0 + 4]]), t, 0.2, 2.6, { from: 0.5, to: 0.8, speed: 0.75 });
        }
        // Le ballon : dans les mains du porteur, ou entre deux joueurs.
        let carrier = chain[0];
        let inFlight = null;
        passes.forEach(([release, arrive], i) => {
          if (t >= release && t < arrive) inFlight = [chain[i], chain[i + 1], span(t, release, arrive)];
          if (t >= arrive) carrier = chain[i + 1];
        });
        if (t < 0.3) {
          // La petite tape du pied, à la reprise.
          const k = span(t, 0, 0.3);
          carried(holder, "two", a);
          world.ballAt(a.setY(lerp(1.1, 0.25, Math.sin(k * Math.PI))), new THREE.Vector3(0, 1, 0));
        } else if (inFlight) {
          carried(inFlight[0], "two", a);
          carried(inFlight[1], "two", b);
          world.ballAt(lob(a, b, 0.35, inFlight[2], ballPoint), new THREE.Vector3(b.x - a.x, 0, b.z - a.z));
        } else if (carrier === wing && t >= finishAt && result.scored) world.ballAt(carried(wing, "low", ballPoint), new THREE.Vector3(1, 0, 0));
        else world.ballAt(carried(carrier, carrier === wing ? "one" : "two", ballPoint), new THREE.Vector3(0, 0, 1));
        // L'arbitre suit l'action et accorde l'essai.
        runner(ref, route([[x0 + s * 2.6, z0 - 1.2], [open * 20, 4]]), t, 0.3, finishAt, { from: 0.4, to: 0.6, speed: 0.7 });
        if (t >= finishAt) ref.place(open * 20, 4, headingTo(open * 20, 4, corner[0], corner[1])).set(result.scored ? tryAward(smooth(span(t, finishAt + 0.35, finishAt + 0.7))) : ready(0.2));
        // La caméra suit le ballon de haut, puis se pose sur le coin.
        const settle = smooth(span(t, finishAt - 0.4, finishAt + 0.6));
        const fx = lerp(ballPoint.x, corner[0] * 0.9, settle);
        const fz = lerp(ballPoint.z, 2, settle);
        return { pos: [fx - 22, 9, fz + 11], look: [fx, 0.8, fz], fov: lerp(34, 28, settle) };
      },
    };
  }

  // Au survol, la caméra prend de la hauteur pour montrer toute la voie.
  const wide = { pos: [x0 - 34, 30, z0 + 16], look: [x0 * 0.55, -2, z0 * 0.42], fov: 42 };

  return {
    setup,
    preview,
    previewShot: () => wide,
    outcome(key, result) {
      if (key === "kick") return kickOutcome(result);
      if (key === "touch") return touchOutcome(result);
      if (key === "scrum") return scrumOutcome(result);
      return playOutcome(result);
    },
  };
}
