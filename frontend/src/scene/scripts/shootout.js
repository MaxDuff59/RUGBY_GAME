import * as THREE from "three";

import { BALL_A, TEE_TOP } from "../ball.js";
import { cheer, dejected, kick, mixPose, pose, ready, run, tryAward, whistle } from "../rig.js";
import { goalKick, headingTo, lerp, reaction, route, smooth, span } from "./common.js";

// La séance de tirs au but, à regarder : les deux équipes en ligne sur la médiane, puis
// les tirs réels, dans l'ordre, chacun vu de derrière le buteur (il marche au ballon,
// prend son élan, frappe : la physique de ball.js, réglée pour donner l'issue déjà tirée,
// calculée une fois pour toutes), un bref fondu au noir entre deux tirs. Dernier plan :
// la ligne des vainqueurs court vers la caméra et exulte, l'autre reste abattue.
//
// `data` : `kicks` ({ us, number, name, scored }, de 2 à 30 tirs), `onKick(n)` : le n-ième
// ballon vient d'arriver (le score affiché suit).

const X0 = 0;
const Z0 = 22; // le point de tir, à 22 m face aux perches
const LINE_Z = 50; // les équipes attendent sur la médiane, une de chaque côté du centre
const SPACING = 1.25;
const SQUAD = 15;

const INTRO = 2.6;
const OUTRO = 3.8;
const FADE = 0.22; // demi-durée d'un fondu au noir

// Un tir, en secondes depuis le début de son plan.
const WALK_END = 1.05;
const RUN_FROM = 1.35;
const KICK_AT = 1.95;
const AFTER = 1.2; // ce qui suit l'arrivée du ballon

const WAIT = ready(0.1);
const LOOK_UP = ready(0.12);
const HANDS_ON_KNEES = pose({ y: -0.26, lean: 0.8, legL: 0.75, legR: 0.55, knL: 1.2, knR: 1.0, armL: 0.95, armR: 0.95, abL: 0.05, abR: 0.05, elL: 0.35, elR: 0.35, nod: 0.25 });
const STAND = pose();

const START = [X0 - 3.3, Z0 + 6.1];
const BACK = [X0 - 2.1, Z0 + 3.1];
const CONTACT = [X0 - 0.1, Z0 + 0.28]; // le pied droit arrive au ballon
const walkIn = route([START, BACK]);
const runUp = route([BACK, CONTACT]);
const toPosts = headingTo(BACK[0], BACK[1], X0, 0);

const REF = [X0 + 5.6, Z0 - 2.4];

// Tous les numéros d'une équipe : ses buteurs d'abord, complétés jusqu'à quinze.
function squad(kicks, us) {
  const numbers = new Set(kicks.filter((k) => k.us === us).map((k) => k.number ?? 10));
  for (let n = 1; n <= SQUAD && numbers.size < SQUAD; n++) numbers.add(n);
  return [...numbers].sort((a, b) => a - b);
}

export function buildShootout(world, data) {
  const { kicks } = data;
  const rng = world.rng;
  const goals = (us) => kicks.filter((k) => k.us === us && k.scored).length;
  const won = goals(true) > goals(false);
  // Les vainqueurs à gauche de l'image, du côté de la caméra du dernier plan.
  const sideOf = (us) => (us === won ? -1 : 1);

  const lineOf = (us) =>
    squad(kicks, us).map((number, i) => {
      const side = sideOf(us);
      return { player: world.player(us ? "us" : "them", number), number, us, x: side * (3 + i * SPACING), i };
    });
  const lines = [...lineOf(true), ...lineOf(false)];
  const ref = world.player("ref");

  // Chaque tir, une seule fois : le vol est calculé ici, jamais à l'image.
  const tee = new THREE.Vector3(X0, TEE_TOP * 1.4 + BALL_A * 1.1, Z0);
  const tilt = new THREE.Vector3(-X0 * 0.01, 1, 0.2);
  const rest = new THREE.Quaternion().setFromUnitVectors(new THREE.Vector3(0, 1, 0), tilt.clone().normalize());
  let clock = INTRO;
  const shots = kicks.map((entry, i) => {
    const flight = goalKick(tee, world.wind, entry.scored, rng);
    const cross = KICK_AT + flight.crossAt;
    const shot = {
      i,
      entry,
      flight,
      cross,
      start: clock,
      length: cross + AFTER,
      kicker: lines.find((row) => row.us === entry.us && row.number === (entry.number ?? 10)),
    };
    clock += shot.length;
    return shot;
  });
  const lastShot = clock;
  const duration = lastShot + OUTRO;
  const cuts = [0, ...shots.map((shot) => shot.start), lastShot];

  const ballPoint = new THREE.Vector3();
  const ballTurn = new THREE.Quaternion();

  function placeLines() {
    for (const { player, x } of lines) {
      player.visible = true;
      player.place(x, LINE_Z, Math.PI).set(WAIT);
    }
  }

  // Le premier plan : les deux lignes de dos, le point de tir et les perches au fond ; le
  // premier buteur quitte sa ligne.
  function intro(t) {
    const first = shots[0]?.kicker;
    if (first) {
      const path = route([[first.x, LINE_Z], [lerp(first.x, START[0], 0.3), LINE_Z - 7]]);
      const d = path.total * smooth(span(t, 0.7, INTRO));
      const spot = path.at(d);
      first.player.place(spot.x, spot.z, spot.heading).set(t > 0.7 ? run(d / 1.6, 0.15) : WAIT);
    }
    ref.place(REF[0], REF[1], headingTo(REF[0], REF[1], X0, Z0)).set(STAND);
    world.ball.visible = true;
    world.tee.visible = true;
    world.ballAt(tee, tilt);
    const k = t / INTRO;
    return { pos: [lerp(-31, -29.5, k), lerp(6.4, 5.8, k), lerp(61, 59.5, k)], look: [-6.5, 2.5, 41.5], fov: 34 };
  }

  // Un tir : `u` depuis le début de son plan.
  function kickShot(shot, u) {
    const { kicker, entry, flight, cross } = shot;
    const player = kicker.player;
    const scored = entry.scored;
    if (u < WALK_END) {
      const k = span(u, 0, WALK_END);
      const d = walkIn.total * (1 - (1 - k) * (1 - k));
      const spot = walkIn.at(d);
      player.place(spot.x, spot.z, spot.heading).set(run(d / 1.5, 0.15));
    } else if (u < RUN_FROM) {
      // Les yeux sur les perches.
      player.place(BACK[0], BACK[1], lerpAngle(walkIn.at(0).heading, toPosts, smooth(span(u, WALK_END, WALK_END + 0.25)))).set(LOOK_UP);
    } else if (u < KICK_AT) {
      const k = span(u, RUN_FROM, KICK_AT);
      const d = runUp.total * (0.35 * k + 0.65 * k * k);
      const spot = runUp.at(d);
      player.place(spot.x, spot.z, spot.heading);
      player.set(u < KICK_AT - 0.2 ? run(d / 1.6, 0.55) : kick(span(u, KICK_AT - 0.2, KICK_AT + 0.32)));
    } else {
      const k = smooth(span(u, cross + 0.05, cross + 0.55));
      // La joie se tourne vers les siens, la déception reste face aux perches.
      const heading = lerpAngle(toPosts, scored ? Math.PI * 2 : Math.PI * 1.15, k);
      const after = scored ? cheer((u - cross) * 1.6) : dejected();
      player.place(CONTACT[0], CONTACT[1], heading).set(mixPose(kick(span(u, KICK_AT - 0.2, KICK_AT + 0.32)), after, k));
    }

    const signal = scored ? smooth(span(u, cross, cross + 0.4)) : 0;
    const whistling = u > WALK_END && u < KICK_AT ? smooth(span(u, WALK_END, WALK_END + 0.2)) : 0;
    ref.place(REF[0], REF[1], headingTo(REF[0], REF[1], X0, Z0)).set(signal > 0 ? tryAward(signal) : whistling > 0 ? whistle(whistling) : STAND);

    world.ball.visible = true;
    world.tee.visible = true;
    if (u < KICK_AT) {
      world.ballAt(tee, tilt);
      ballPoint.copy(tee);
    } else {
      flight.at(u - KICK_AT, ballPoint, ballTurn, rest);
      world.ball.position.copy(ballPoint);
      world.ball.quaternion.copy(ballTurn);
    }
    // Derrière le buteur, un peu de biais : lui en bas, les perches au fond ; la caméra
    // suit le ballon à moitié, puis revient au buteur.
    const follow = smooth(span(u, KICK_AT, KICK_AT + 0.5)) * (1 - smooth(span(u, cross + 0.2, cross + 1.0)));
    return {
      pos: [X0 + 1.9, 3.6, Z0 + 10.8],
      look: [lerp(X0 - 0.3, ballPoint.x * 0.5, follow), lerp(1.9, 2.1 + Math.min(ballPoint.y, 9) * 0.34, follow), lerp(10, 8, follow)],
      fov: 33,
    };
  }

  // Le dernier plan : les vainqueurs courent vers la caméra, puis sautent ; les vaincus
  // restent sur la médiane. Au dernier instant, tout le monde a les pieds au sol.
  function outro(s) {
    const settle = 1 - smooth(span(s, OUTRO - 1, OUTRO - 0.15));
    for (const { player, x, us, i } of lines) {
      if (us === won) {
        const reach = 3 + ((i * 37) % 5) * 0.9;
        const k = span(s, 0.1 + (i % 3) * 0.08, 1.3);
        const d = reach * (1 - (1 - k) * (1 - k));
        player.place(x, LINE_Z - d, Math.PI);
        const body = cheer(s * 1.7 + i * 0.31);
        body.lift *= settle;
        if (k < 1) player.set({ ...run(d / 2, 0.6), armL: 2.9, armR: 2.7, abL: 0.35, abR: 0.35, elL: 0.15, elR: 0.25 });
        else player.set(body);
      } else {
        player.place(x, LINE_Z, Math.PI + (i % 2 ? 0.25 : -0.2)).set(i % 4 === 1 ? HANDS_ON_KNEES : dejected());
      }
    }
    ref.place(REF[0], REF[1], Math.PI * 0.5).set(STAND);
    world.ball.visible = false;
    world.tee.visible = false;
    world.ballAt(tee, tilt);
    const k = smooth(s / OUTRO);
    return { pos: [lerp(-31, -29.5, k), lerp(5.2, 4.6, k), lerp(25, 26.5, k)], look: [lerp(-8.5, -8, k), 1.4, 48], fov: 31 };
  }

  function frame(t) {
    // Le fondu : au noir à chaque coupure, et à l'image pleine au dernier instant.
    const near = cuts.reduce((best, cut) => Math.min(best, Math.abs(t - cut)), Infinity);
    world.exposure(smooth(near / FADE));
    placeLines();
    if (t < INTRO) return intro(t);
    if (t >= lastShot) return outro(t - lastShot);
    const shot = shots.find((candidate) => t < candidate.start + candidate.length) ?? shots[shots.length - 1];
    return kickShot(shot, t - shot.start);
  }

  const cues = [{ at: 0.1, run: () => world.crowd("standing") }];
  for (const shot of shots) {
    const { start, entry, cross, i } = shot;
    if (i > 0) cues.push({ at: start, run: () => world.crowd("standing") });
    cues.push({ at: start + WALK_END + 0.05, run: () => world.sound("whistle") });
    cues.push({ at: start + KICK_AT, run: () => world.sound("kick") });
    cues.push({
      at: start + cross,
      run: () => {
        data.onKick?.(i + 1);
        reaction(world, entry.us === entry.scored);
      },
    });
  }
  cues.push({ at: lastShot + 0.15, run: () => { world.sound("whistle", true); reaction(world, won); } });

  return {
    setup: { duration: 0.05, frame: () => frame(0), cues: [] },
    outcome: () => ({ duration, cues, frame }),
  };
}

// D'un cap à l'autre, par le chemin le plus court.
function lerpAngle(a, b, k) {
  const turn = ((((b - a) % (Math.PI * 2)) + Math.PI * 3) % (Math.PI * 2)) - Math.PI;
  return a + turn * k;
}
