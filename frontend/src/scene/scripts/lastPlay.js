import * as THREE from "three";

import { TOUCH } from "../field.js";
import { bind, cheer, crouch, dejected, ground, kick, mixPose, pass, pose, ready, signal, tackle } from "../rig.js";
import { FACE_FIELD, FACE_LINE, broadcast, carried, grubber, headingTo, keys, lerp, lob, penaltyAgainst, reaction, route, runner, smooth, span } from "./common.js";

// Carrière de joueur, « Dernière action » (last_play) : le temps est presque écoulé, le
// match se joue à rien, tout le stade est debout. Le ballon sort d'un ruck dans notre
// camp et arrive sur le joueur incarné (n'importe quel numéro). Taper en touche (le temps
// file, ou le ballon reste en jeu et ils relancent), repartir de notre camp (il perce au
// milieu de terrain, balle en main et un partenaire proche : le deux contre un s'enchaîne ;
// ou il est pris et perd le ballon), ou chercher la pénalité au près (ils craquent au sol,
// ou le ballon est arraché dans le ruck).
//
// Notre équipe attaque vers la ligne d'essai (z = 0) : le ruck est vers z = 66.

const JACKAL = pose({ y: -0.3, lean: 1.15, legL: 0.9, legR: 0.7, knL: 1.3, knR: 1.1, armL: 1.6, armR: 1.6, elL: 0.2, elR: 0.2, abL: -0.2, abR: -0.2, nod: -0.4 });

const v = (x, y, z) => new THREE.Vector3(x, y, z);
const ARC = (a, b, height, steps = 14) => {
  const out = [];
  for (let i = 0; i <= steps; i++) out.push(lob(a, b, height, i / steps).toArray());
  return out;
};

export function buildLastPlay(world, data) {
  const s = world.rng() < 0.5 ? -1 : 1; // le côté de la touche proche ; le milieu est à -s
  const heroNo = data.hero ?? 10;
  const free = (number, other) => (number === heroNo ? other : number);
  const hero = world.player("us", heroNo, { hero: true });

  // Le ruck : notre porteur au sol, les nôtres liés au-dessus, les leurs en face.
  const rx = s * 15;
  const rz = 66;
  const floor = world.player("us", free(8, 6));
  const ours = [world.player("us", free(4, 5)), world.player("us", free(3, 1))];
  const theirs = [world.player("them", 6), world.player("them", 7)];
  const nine = world.player("us", free(9, 7));
  const footBall = v(rx - s * 0.2, 0.12, rz + 2.3);
  const nineAt = [rx - s * 0.7, rz + 3];

  // Le joueur incarné, en retrait du ruck, et ses soutiens côté milieu.
  const hx = s * 8;
  const hz = 71;
  const heroFrom = [hx + s * 0.8, hz + 2.2];
  const partner = world.player("us", free(12, 13));
  const wing = world.player("us", free(14, 11));
  const partnerFrom = [hx - s * 7, hz + 3];
  const partnerAt = [hx - s * 8, hz + 1.5];
  const wingAt = [hx - s * 17, hz + 3];

  // Leur rideau, sur la ligne de hors-jeu, et leurs deux hommes en couverture.
  const pillar = world.player("them", 10);
  const inner = world.player("them", 12);
  const outer = world.player("them", 13);
  const blind = world.player("them", 4);
  const curtain = [
    [pillar, [rx - s * 3.5, 60.5]],
    [inner, [s * 5, 60]],
    [outer, [-s * 3, 59.5]],
    [blind, [rx + s * 4, 60.5]],
  ];
  const spot = new Map(curtain);
  const fullback = world.player("them", 15);
  const theirWing = world.player("them", s > 0 ? 11 : 14);
  const fullbackAt = [-s * 4, 38];
  const theirWingAt = [s * 27, 46];
  const ref = world.player("ref");
  const refSpot = [rx + s * 5, rz + 1];
  const refHeading = (-s * Math.PI) / 2;
  // Le bras de l'arbitre vers notre attaque (-z) : sa gauche est en z = -sin(cap).
  const ourArm = -Math.sin(refHeading) * -1 > 0 ? 1 : -1;

  const ball = new THREE.Vector3();
  const from = new THREE.Vector3();
  const to = new THREE.Vector3();
  const axis = v(1, 0, 0);

  const DURATION = 2.3;
  const PASS = [1.25, 1.65];
  // D'abord dans le dos du joueur : ses numéros, le terrain à remonter, le stade debout ;
  // puis le plan de retransmission, le temps de choisir.
  const shot = broadcast(s * 6.5, hz - 1.5, { far: 1.02, fov: 33, y: 0.2 });
  const back = [hx - 2.2, 2.1, hz + 7.2, hx + 2.4, 1.5, hz - 8, 30];
  const nearer = [hx - 1.6, 1.9, hz + 6.2, hx + 2.2, 1.5, hz - 8, 30];
  const camera = keys([
    [0, back],
    [1.1, nearer],
    [DURATION, [...shot.pos, ...shot.look, shot.fov]],
  ]);

  // Le ruck vit tout le long de la scène.
  function ruckFrame(t) {
    floor.place(rx, rz + 0.3, FACE_LINE + s * 0.3).set(ground());
    ours.forEach((player, i) => player.place(rx + (i ? 0.6 : -0.6) * s, rz + 1.2, FACE_LINE).set(bind(t + i * 0.4, 0.35, 0.85)));
    theirs.forEach((player, i) => player.place(rx + (i ? 0.6 : -0.6) * s, rz - 0.8, FACE_FIELD).set(bind(t + i * 0.3 + 0.2, 0.35, 0.85)));
  }

  function setupFrame(t) {
    ruckFrame(t);
    nine.place(nineAt[0], nineAt[1], FACE_LINE).set(t < PASS[0] ? crouch(1) : pass(span(t, PASS[0] - 0.1, PASS[0] + 0.25), s));
    runner(hero, route([heroFrom, [hx, hz]]), t, PASS[0] - 0.3, DURATION, { from: 0.2, to: 0.5, speed: 0.45, carry: t > PASS[1] ? "two" : "none", still: ready(0.45) });
    runner(partner, route([partnerFrom, partnerAt]), t, PASS[0] - 0.3, DURATION, { from: 0.2, to: 0.5, speed: 0.45, still: ready(0.3) });
    wing.place(wingAt[0], wingAt[1], FACE_LINE).set(ready(0.3));
    // Le rideau attend, bas sur ses appuis, et monte d'un pas quand le ballon sort.
    curtain.forEach(([player, [x, z]]) => {
      runner(player, route([[x, z - 2.2], [x, z]]), t, PASS[0], DURATION, { from: 0.4, to: 0.3, speed: 0.4, still: ready(0.6) });
      player.root.rotation.y = player.heading = FACE_FIELD;
    });
    fullback.place(fullbackAt[0], fullbackAt[1], FACE_FIELD).set(ready(0.35));
    theirWing.place(theirWingAt[0], theirWingAt[1], FACE_FIELD).set(ready(0.35));
    ref.place(refSpot[0], refSpot[1], refHeading).set(ready(0.1));
    if (t < PASS[0]) world.ballAt(ball.copy(footBall), axis);
    else if (t < PASS[1]) {
      carried(nine, "two", from);
      carried(hero, "two", to);
      world.ballAt(lob(from, to, 0.45, span(t, PASS[0], PASS[1]), ball), axis);
    } else world.ballAt(carried(hero, "two", ball), axis);
    const [cx, cy, cz, lx, ly, lz, fov] = camera(t);
    return { pos: [cx, cy, cz], look: [lx, ly, lz], fov };
  }

  const setup = {
    duration: DURATION,
    frame: setupFrame,
    cues: [
      { at: 0.05, run: () => world.crowd("standing") },
      { at: PASS[0], run: () => world.sound("whistle") },
    ],
  };

  // --- Les voies -----------------------------------------------------------------------

  const touchAt = [s * (TOUCH + 2), hz - 27];
  const shortAt = [s * 25, hz - 24];
  const breach = [[hx, hz], [s * 3, 65], [s * 1, 60], [-s * 0.5, 48]];
  const caught = [[hx, hz], [s * 3, 65], [s * 1, 60], [-s * 0.2, 52]];
  const contact = [rx - s * 2.3, rz - 1.4];
  const pick = [[hx, hz], [rx - s * 3, rz + 1.5], contact];
  const wide = { pos: [hx - 38, 28, hz + 12], look: [hx * 0.4, -2, hz - 20], fov: 44 };

  function preview(key) {
    const draw = world.draw;
    const hands = carried(hero, "two", v());
    if (key === "boot_out") return [draw.arc(ARC(hands, v(touchAt[0], 0.5, touchAt[1]), 13)), draw.mark([s * TOUCH, touchAt[1]])];
    if (key === "go_long") return [draw.path(breach), draw.mark(breach[3])];
    return [draw.arrow([hx, hz - 0.4], [contact[0], contact[1] + 0.6], 1.5), draw.mark(contact, 0.7)];
  }

  // Le coup de pied : en touche, ou trop court (leur ailier ramasse et relance).
  function bootOutcome(good) {
    const kickAt = 0.35;
    const land = good ? 2.35 : 2.1;
    const target = v(...(good ? [touchAt[0], 0.45, touchAt[1]] : [shortAt[0], 0.2, shortAt[1]]));
    const rest = good ? v(s * (TOUCH + 3), 0.12, touchAt[1] - 2.5) : v(s * 27.5, 0.12, shortAt[1] - 4.5);
    const gather = 2.95;
    const lift = gather + 0.3;
    const duration = good ? 4 : 4.6;
    const wingStop = good ? [s * 31.5, 44.5] : [rest.x, rest.z + 0.1];
    const heading = headingTo(hx, hz, target.x, target.z);
    return {
      duration,
      cues: [
        { at: kickAt, run: () => world.sound("kick") },
        good
          ? {
              at: land + 0.1,
              run: () => {
                world.sound("whistle");
                reaction(world, true);
              },
            }
          : { at: gather, run: () => reaction(world, false) },
      ],
      frame(t) {
        setupFrame(DURATION);
        ruckFrame(DURATION + t);
        nine.set(ready(0.2));
        hero.place(hx, hz, heading).set(t < 0.1 ? ready(0.2) : t < kickAt + 0.6 ? kick(span(t, 0.1, kickAt + 0.4)) : good ? cheer(t * 1.4) : dejected());
        // Leur rideau a monté sur lui, trop tard.
        curtain.forEach(([player, [x, z]]) => {
          runner(player, route([[x, z], [lerp(x, hx, 0.25), hz - 5.5]]), t, 0, 1.0, { from: 0.8, to: 0.1, speed: 0.8, still: ready(0.2) });
          if (t >= 1.0) player.set(good ? dejected() : ready(0.2));
        });
        runner(partner, route([partnerAt, [partnerAt[0] - s * 1, partnerAt[1] - 2]]), t, 0, 1.0, { from: 0.5, to: 0.1, speed: 0.5, still: ready(0.2) });
        if (t >= 1.0) partner.set(good ? cheer(t * 1.3 + 1) : dejected());
        // Leur ailier court sous le ballon ; il le regarde sortir, ou il le ramasse.
        runner(theirWing, route([theirWingAt, wingStop]), t, 0.5, good ? 2.4 : gather, { from: 0.5, to: 0.5, speed: 0.75, still: ready(0.35) });
        if (good && t >= 2.4) theirWing.set(dejected());
        if (!good && t >= gather) {
          if (t < lift) theirWing.place(wingStop[0], wingStop[1], FACE_FIELD).set(crouch(1));
          else runner(theirWing, route([wingStop, [s * 20, 58]]), t, lift, duration + 0.1, { from: 0.4, to: 0.9, speed: 0.85, carry: "one" });
        }
        if (t < kickAt) world.ballAt(carried(hero, "two", ball), axis);
        else if (t < land) world.ballAt(lob(carried(hero, "two", from), target, good ? 13 : 8, span(t, kickAt, land), ball), v(Math.sin(t * 8), 1, Math.cos(t * 8)));
        else if (good) world.ballAt(grubber(target, rest, span(t, land, land + 0.8), 2, ball), v(1, 0.2, 0.3));
        else if (t < lift) world.ballAt(grubber(target, rest, span(t, land, gather), 3, ball), v(1, 0.2, 0.3));
        else world.ballAt(carried(theirWing, "one", ball), v(0, 0, 1));
        // La caméra suit le ballon (ou celui qui le relance).
        const follow = smooth(span(t, kickAt, land - 0.2));
        if (good) {
          // Serré sur la touche : le ballon dehors, leur ailier qui le regarde sortir.
          const end = { pos: [touchAt[0] - 19, 8, touchAt[1] + 10], look: [touchAt[0] - 2.5, 0.4, touchAt[1] + 0.5], fov: 30 };
          return { pos: shot.pos.map((value, i) => lerp(value, end.pos[i], follow)), look: shot.look.map((value, i) => lerp(value, end.look[i], follow)), fov: lerp(shot.fov, end.fov, follow) };
        }
        return broadcast(lerp(s * 6.5, theirWing.root.position.x, follow), lerp(hz - 1.5, theirWing.root.position.z - 1, follow), { far: lerp(1.02, 1.1, follow), fov: 33 });
      },
    };
  }

  // La relance : il passe entre leurs centres ; pris par l'arrière, ballon perdu.
  function longOutcome(good) {
    const path = route(good ? breach : caught);
    const hit = good ? 3.3 : 2.75;
    const duration = good ? hit : hit + 2.3;
    const dives = 1.75;
    const meet = caught[3];
    const loose = v(meet[0] + s * 0.9, 0.12, meet[1] - 2.4);
    const pickAt = hit + 1.05;
    return {
      duration,
      cues: good
        ? [
            { at: dives + 0.15, run: () => world.sound("impact") },
            { at: dives + 0.3, run: () => reaction(world, true) },
          ]
        : [
            { at: dives + 0.15, run: () => world.sound("impact") },
            { at: hit, run: () => world.sound("impact") },
            { at: hit + 0.5, run: () => reaction(world, false) },
          ],
      frame(t) {
        setupFrame(DURATION);
        ruckFrame(DURATION + t);
        nine.set(ready(0.2));
        if (t < hit || good) runner(hero, path, t, 0, hit, { from: 0.6, to: 1, speed: 0.95, carry: "one" });
        else {
          const k = span(t, hit, hit + 0.45);
          hero.place(meet[0], lerp(meet[1], meet[1] - 0.9, smooth(k)), FACE_LINE).set(k < 1 ? tackle(k * 0.6) : ground());
        }
        // Les deux centres plongent dans le vide.
        [[inner, [s * 2.3, 60.1]], [outer, [-s * 0.2, 59.4]]].forEach(([player, spotTo]) => {
          const a = spot.get(player);
          if (t < dives) runner(player, route([a, spotTo]), t, 0.1, dives, { from: 0.5, to: 1, speed: 0.85, still: ready(0.6) });
          else {
            const k = span(t, dives, dives + 0.5);
            player.place(spotTo[0], spotTo[1] - 0.5 * smooth(k), headingTo(...a, ...spotTo)).set(k < 1 ? tackle(k) : ground());
          }
        });
        // Les autres se retournent et courent après lui.
        runner(pillar, route([spot.get(pillar), [s * 5, 61], [s * 1.5, 54]]), t, 0.2, 3.6, { from: 0.4, to: 1, speed: 0.9 });
        runner(blind, route([spot.get(blind), [s * 11, 61], [s * 6, 54]]), t, 0.2, 3.6, { from: 0.4, to: 0.9, speed: 0.8 });
        // Son soutien file avec lui.
        runner(partner, route([partnerAt, [-s * 4.3, 50.8]]), t, 0.1, 3.3, { from: 0.6, to: 1, speed: 0.95 });
        runner(wing, route([wingAt, [wingAt[0] - s * 1, 54]]), t, 0.1, 3.6, { from: 0.6, to: 0.9, speed: 0.85 });
        theirWing.set(ready(0.35));
        const refTo = [hx + s * 2, 56];
        runner(ref, route([refSpot, refTo]), t, 0.3, 3.6, { from: 0.5, to: 0.8, speed: 0.7 });
        if (good) {
          runner(fullback, route([fullbackAt, [-s * 1.5, 34]]), t, 0.5, hit, { from: 0.4, to: 0.6, speed: 0.6 });
          fullback.root.rotation.y = fullback.heading = FACE_FIELD;
          world.ballAt(carried(hero, "one", ball), v(0, 0, 1));
        } else {
          // Leur arrière vient le prendre de face ; le ballon s'échappe, leur 10 ramasse.
          const tackleSpot = [meet[0] - s * 0.2, meet[1] - 1.1];
          runner(fullback, route([fullbackAt, tackleSpot]), t, 0.4, hit, { from: 0.5, to: 1, speed: 0.95 });
          if (t >= hit) {
            const k = span(t, hit, hit + 0.45);
            fullback.place(tackleSpot[0], tackleSpot[1], FACE_FIELD).set(k < 1 ? tackle(k) : ground());
          }
          if (t < hit) world.ballAt(carried(hero, "one", ball), v(0, 0, 1));
          else if (t < hit + 0.55) world.ballAt(lob(from.set(meet[0], 1, meet[1] - 0.2), loose, 0.8, span(t, hit, hit + 0.55), ball), v(Math.sin(t * 9), 0.4, 1));
          else if (t < pickAt) world.ballAt(loose, axis);
          else world.ballAt(carried(pillar, "two", ball), axis);
          if (t > hit - 0.2) {
            runner(pillar, route([[s * 3.2, 60.6], [loose.x + s * 0.2, loose.z + 0.7]]), t, hit - 0.2, pickAt - 0.25, { from: 1, to: 0.6, speed: 0.9 });
            if (t >= pickAt - 0.25) pillar.place(loose.x + s * 0.2, loose.z + 0.7, FACE_LINE).set(t < pickAt + 0.05 ? crouch(1) : ready(0.25));
            world.ballAt(t < pickAt ? (t < hit + 0.55 ? ball : loose) : carried(pillar, "two", ball), axis);
          }
          if (t > hit + 0.6) {
            partner.set(dejected());
            wing.set(dejected());
          }
        }
        const focus = hero.root.position;
        return broadcast(lerp(hx, focus.x, 0.85), focus.z - 2.5, { far: 1.02, fov: 33 });
      },
    };
  }

  // Au près : il charge dans le rideau, au ras du ruck, et se présente au sol.
  function pickOutcome(result) {
    const good = result.success;
    const hit = 1.05;
    const callAt = 2.05;
    const duration = 4;
    const placed = v(contact[0], 0.12, contact[1] + 1.1);
    const down = [contact[0] + s * 1.1, contact[1] - 0.9];
    const jackalAt = [contact[0] + s * 0.1, contact[1] + 0.35];
    const refNear = [contact[0] + s * 4.5, contact[1] + 2];
    const rip = 2.2;
    return {
      duration,
      cues: [
        { at: hit, run: () => world.sound("impact") },
        {
          at: good ? callAt : rip,
          run: () => {
            if (good) penaltyAgainst(world, "them");
            else reaction(world, false);
          },
        },
      ],
      frame(t) {
        setupFrame(DURATION);
        ruckFrame(DURATION + t);
        if (t < hit) runner(hero, route(pick), t, 0, hit, { from: 0.5, to: 1, speed: 0.9, carry: "two" });
        else {
          const k = span(t, hit, hit + 0.4);
          hero.place(contact[0], contact[1] + 0.2 * k, FACE_LINE).set(k < 1 ? tackle(k * 0.7) : ground());
        }
        // Leur 10 plaque ; il reste au sol, du mauvais côté, s'ils craquent.
        runner(pillar, route([spot.get(pillar), [contact[0] + s * 0.3, contact[1] - 1]]), t, 0.2, hit, { from: 0.6, to: 0.9, speed: 0.8 });
        if (t >= hit) {
          const k = span(t, hit, hit + 0.45);
          pillar.place(down[0], down[1], FACE_FIELD - s * 0.3).set(k < 1 ? tackle(k) : ground());
        }
        // Leur 12 arrive sur le ballon.
        const innerTo = good ? [contact[0] - s * 1.6, contact[1] - 2.2] : jackalAt;
        runner(inner, route([spot.get(inner), innerTo]), t, 0.3, good ? hit + 0.6 : hit + 0.45, { from: 0.5, to: 0.5, speed: 0.75 });
        if (t >= hit + 0.45) {
          if (good) inner.set(t > callAt ? dejected() : ready(0.5));
          else {
            const k = span(t, rip, rip + 0.5);
            inner.place(jackalAt[0], lerp(jackalAt[1], jackalAt[1] - 1.5, smooth(k)), FACE_FIELD).set(t < rip ? JACKAL : ready(0.3 * (1 - k) + 0.2));
          }
        }
        // Les nôtres viennent lier, et le 9 se présente.
        const tie = [contact[0] - s * 0.5, contact[1] + 1.9];
        runner(partner, route([partnerAt, tie]), t, 0.15, hit + 0.75, { from: 0.6, to: 0.4, speed: 0.8 });
        if (t >= hit + 0.75) partner.place(tie[0], tie[1], FACE_LINE).set(t > callAt + 0.9 && good ? cheer(t * 1.4) : !good && t > rip + 0.5 ? dejected() : crouch(0.9));
        const nineTo = [contact[0] + s * 0.8, contact[1] + 2.3];
        runner(nine, route([nineAt, nineTo]), t, 0.1, hit + 0.5, { from: 0.5, to: 0.3, speed: 0.6 });
        if (t >= hit + 0.5) nine.place(nineTo[0], nineTo[1], FACE_LINE).set(good && t > callAt + 0.9 ? cheer(t * 1.3 + 1) : !good && t > rip + 0.5 ? dejected() : crouch(0.8));
        // Le ballon est posé derrière lui ; arraché, il part dans les bras de leur 12.
        if (t < hit) world.ballAt(carried(hero, "two", ball), axis);
        else if (t < hit + 0.35) world.ballAt(ball.lerpVectors(carried(hero, "two", from).setY(0.7), placed, span(t, hit, hit + 0.35)), axis);
        else if (good || t < rip) world.ballAt(placed, axis);
        else world.ballAt(carried(inner, "two", ball), axis);
        const rk = span(t, 0.8, callAt - 0.15);
        ref.place(lerp(refSpot[0], refNear[0], smooth(rk)), lerp(refSpot[1], refNear[1], smooth(rk)), refHeading);
        if (rk > 0 && rk < 1) runner(ref, route([refSpot, refNear]), t, 0.8, callAt - 0.15, { from: 0.5, to: 0.5, speed: 0.5 });
        else ref.set(good && t >= callAt ? signal(ourArm, smooth(span(t, callAt, callAt + 0.3))) : ready(0.1));
        ref.root.rotation.y = ref.heading = refHeading;
        // Relevé après le coup de sifflet, les bras en l'air ; à terre, s'il a perdu le ballon.
        if (t > hit + 0.4) hero.set(good ? mixPose(ground(), cheer(t * 1.4), smooth(span(t, callAt + 0.9, callAt + 1.4))) : ground());
        return broadcast(contact[0], contact[1] + 1, { far: 0.72, fov: 31, y: 0.25 });
      },
    };
  }

  return {
    setup,
    preview,
    previewShot: (key) => (key === "hunt_penalty" ? null : wide),
    outcome(key, result) {
      if (key === "boot_out") return bootOutcome(result.success);
      if (key === "go_long") return longOutcome(result.success);
      return pickOutcome(result);
    },
  };
}
