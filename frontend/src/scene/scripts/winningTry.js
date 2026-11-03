import * as THREE from "three";

import { cheer, dejected, dive, ground, mixPose, pass, ready, tackle, tryAward } from "../rig.js";
import { FACE_LINE, broadcast, carried, lerp, lob, reaction, route, runner, smooth, span } from "./common.js";

// Moment à regarder, « L'essai de la victoire » : le ralenti de l'essai, comme à la
// télévision. La même action (`action(a)`, une fonction de son temps à elle) rejouée
// sous trois angles, de plus en plus près, un fondu au noir bref entre chaque, le dernier
// plan au ralenti sur le plongeon ; puis la joie des joueurs et le public.
//
// Le coin est toujours le même, côté caméra (x < 0) : au dernier plan, vu du ras de la
// pelouse, le marqueur se détache sur la tribune debout, sans leur arrière devant lui.

const v = (x, y, z) => new THREE.Vector3(x, y, z);

// Une ligne brisée arrondie, pour que le cap ne saute pas à chaque changement d'appui.
function curve(points, samples = 48) {
  const spline = new THREE.CatmullRomCurve3(points.map(([x, z]) => v(x, 0, z)), false, "centripetal");
  const out = [];
  for (let i = 0; i <= samples; i++) {
    const p = spline.getPoint(i / samples);
    out.push([p.x, p.z]);
  }
  return route(out);
}

// Le ballon entre ses mains, là où elles sont (le plongeon se voit de près).
function hands(player, out) {
  player.root.updateWorldMatrix(true, true);
  const left = player.elbowL.localToWorld(v(0, -0.3, 0));
  const right = player.elbowR.localToWorld(v(0, -0.3, 0));
  return out.addVectors(left, right).multiplyScalar(0.5);
}

// Du temps de la scène au temps de l'action : [[temps, action], ...], en ligne droite.
const warp = (points) => (t) => {
  if (t <= points[0][0]) return points[0][1];
  for (let i = 1; i < points.length; i++) {
    const [t1, a1] = points[i];
    if (t <= t1) {
      const [t0, a0] = points[i - 1];
      return lerp(a0, a1, (t - t0) / (t1 - t0));
    }
  }
  return points[points.length - 1][1];
};

const FADE = 0.22; // la moitié d'un fondu
const LAND_X = -17;
const CATCH = [0.45, 0.8];
const DIVE = 4.15; // le plongeon part
const DOWN = 4.6; // le ballon est au sol
const END = 5; // fin de l'action
const DIVE_FROM = 1.9;
const DIVE_TO = 0.65;

export function buildWinningTry(world, data) {
  const number = data.number ?? 11;
  const free = (n, other) => (n === number ? other : n);
  const scorer = world.player("us", number, { hero: true });
  const passer = world.player("us", free(12, 10));
  const support = world.player("us", free(13, 15));
  const flanker = world.player("us", free(7, 6));
  const winger = world.player("them", 14);
  const fullback = world.player("them", 15);
  const chaser = world.player("them", 7);
  const centre = world.player("them", 13);
  const ref = world.player("ref");

  // Le marqueur prend la passe lancé, sort sur l'ailier, rentre d'un appui et file.
  const scorerPath = curve([[-11, 34], [-13.5, 27], [-17.5, 19], [-21, 12.5], [-19, 8], [-17.5, 4.5], [LAND_X, DIVE_FROM]]);
  const passerPath = route([[-7, 31], [-9, 25], [-11, 16]]);
  const supportPath = route([[-5.5, 33], [-9, 22], [-12, 8], [-13.5, 3]]);
  const flankerPath = route([[-3, 34], [-6, 22], [-9, 8]]);
  const wingerAt = [-27, 15];
  const wingerTo = [-22.3, 11];
  const fullbackAt = [-5, 11];
  const fullbackTo = [-15.6, 2.9];
  const chaserPath = route([[-5, 27], [-11, 18], [-15, 8]]);
  const centrePath = route([[-3, 22], [-8, 14], [-12, 7]]);
  const refPath = route([[-1, 26], [-6, 12], [-9.5, 2.5]]);
  const lunge = 3.0; // l'ailier plonge dans le vide
  const late = 4.05; // l'arrière arrive trop tard

  const ball = new THREE.Vector3();
  const from = new THREE.Vector3();
  const to = new THREE.Vector3();
  const axis = v(0, 0, -1);
  const grounded = v(LAND_X, 0.13, -0.85);

  // Le marqueur à l'instant `a` de l'action, sans le poser : pour les caméras.
  const scorerSpot = (a) => {
    if (a >= DIVE) return { x: LAND_X, z: lerp(DIVE_FROM, DIVE_TO, smooth(span(a, DIVE, DOWN))) };
    return scorerPath.at((scorerPath.total * Math.max(0, a)) / DIVE);
  };

  // L'action entière à son instant `a` : tout le monde et le ballon.
  function action(a) {
    // Le marqueur : il court, puis plonge ; le ballon finit dans ses mains, au sol.
    if (a < DIVE) {
      const carry = a < CATCH[0] ? "none" : a < CATCH[1] + 0.3 || a > DIVE - 0.25 ? "two" : "one";
      runner(scorer, scorerPath, a, 0, DIVE, { from: 1, to: 1, speed: 1, carry });
      if (a <= 0) scorer.set(ready(0.2));
    } else {
      const k = span(a, DIVE, DOWN);
      // Le plongeon pris de près : il décolle vraiment, les pieds quittent la pelouse.
      const flight = dive(k);
      scorer.place(LAND_X, lerp(DIVE_FROM, DIVE_TO, smooth(k)), FACE_LINE).set({ ...flight, lift: flight.lift + Math.sin(k * Math.PI) * 0.22 });
    }
    if (a < CATCH[1]) runner(passer, passerPath, a, 0, 3, { from: 0.8, to: 0.5, speed: 0.6, carry: "two" });
    else runner(passer, passerPath, a, 0, 3, { from: 0.8, to: 0.5, speed: 0.6 });
    if (a >= CATCH[0] - 0.15 && a < CATCH[1] + 0.05) passer.set(pass(span(a, CATCH[0] - 0.15, CATCH[0] + 0.2), 1));
    if (a >= 3) passer.set(ready(0.2));

    if (a < CATCH[0]) world.ballAt(carried(passer, "two", ball), v(1, 0, 0));
    else if (a < CATCH[1]) {
      carried(passer, "two", from);
      carried(scorer, "two", to);
      world.ballAt(lob(from, to, 0.4, span(a, CATCH[0], CATCH[1]), ball), v(1, 0, 0));
    } else if (a < DIVE) {
      world.ballAt(carried(scorer, a < CATCH[1] + 0.3 || a > DIVE - 0.25 ? "two" : "one", ball), a > DIVE - 0.25 ? v(1, 0, 0) : axis);
    } else {
      const k = span(a, DIVE, DOWN);
      hands(scorer, ball);
      ball.y = Math.max(0.13, ball.y);
      ball.lerp(grounded, smooth(span(k, 0.6, 1)));
      world.ballAt(ball, v(1, 0, 0));
    }

    runner(support, supportPath, a, 0, 4.4, { from: 0.8, to: 0.9, speed: 0.85, still: ready(0.2) });
    runner(flanker, flankerPath, a, 0, 4.6, { from: 0.7, to: 0.7, speed: 0.7, still: ready(0.2) });
    if (a >= 4.4) support.set(ready(0.2));
    if (a >= 4.6) flanker.set(ready(0.2));

    // Leur ailier : il sort sur lui, plonge, et l'appui rentrant le laisse sur place.
    if (a < lunge) runner(winger, route([wingerAt, wingerTo]), a, 0.4, lunge, { from: 0.5, to: 1, speed: 0.9, still: ready(0.5) });
    else {
      const k = span(a, lunge, lunge + 0.5);
      winger.place(wingerTo[0], wingerTo[1], Math.atan2(1.5, -0.5)).set(k < 1 ? tackle(k) : ground());
    }
    // Leur arrière coupe vers le coin ; il glisse derrière le marqueur.
    if (a < late) runner(fullback, route([fullbackAt, fullbackTo]), a, 0.2, late, { from: 0.6, to: 1, speed: 1, still: ready(0.4) });
    else {
      const k = span(a, late, late + 0.55);
      fullback.place(lerp(fullbackTo[0], LAND_X + 0.9, smooth(k)), lerp(fullbackTo[1], 1.5, smooth(k)), Math.atan2(-1.4, -1.4)).set(k < 1 ? tackle(k) : ground());
    }
    runner(chaser, chaserPath, a, 0, 4.8, { from: 0.9, to: 0.7, speed: 0.85, still: ready(0.2) });
    if (a >= 4.8) chaser.set(ready(0.2));
    runner(centre, centrePath, a, 0, 4.2, { from: 0.8, to: 0.3, speed: 0.75, still: ready(0.3) });
    if (a >= 4.2) centre.set(ready(0.2));
    runner(ref, refPath, a, 0, 4.6, { from: 0.7, to: 0.5, speed: 0.7, still: ready(0.1) });
    ref.place(ref.root.position.x, ref.root.position.z, a >= 4.6 ? -Math.PI / 2 : ref.heading);
    ref.set(a >= 4.6 ? tryAward(smooth(span(a, 4.6, 4.9))) : ref.current);
  }

  // --- Les plans ------------------------------------------------------------------------

  // Plan 1, de la tribune d'en face : l'action entière, à vitesse normale.
  const A1 = warp([[0, 0.15], [4.2, END - 0.1]]);
  // Plan 2, dans le dos du marqueur : l'appui qui efface l'ailier.
  const A2 = warp([[0, 2.0], [3.0, END - 0.15]]);
  // Plan 3, au ras de la pelouse, le long de la ligne : le plongeon au ralenti.
  const A3 = warp([[0, 3.25], [0.7, 3.8], [1.3, 4.1], [3.5, 4.6], [3.9, 4.78]]);
  const P1 = 4.2;
  const P2 = 3.0;
  const P3 = 3.9;
  const T1 = P1;
  const T2 = T1 + P2;
  const T3 = T2 + P3;
  const PARTY = 2.7;
  const duration = T3 + PARTY;
  const DOWN1 = T1 - (END - 0.1 - DOWN) / ((END - 0.1 - 0.15) / P1);
  const DOWN3 = T2 + 3.5;

  // Le noir, à chaque raccord entre deux plans.
  const dark = (t) => {
    let e = 1;
    for (const cut of [T1, T2, T3]) e = Math.min(e, smooth(Math.abs(t - cut) / FADE));
    return e;
  };

  const followShot = (a) => {
    const spot = scorerSpot(a);
    return broadcast(lerp(-12, spot.x, 0.7), Math.max(spot.z - 2, 1), { far: 1.1, fov: 33 });
  };
  const backShot = (a) => {
    // Une moyenne de la course, pour que la caméra ne suive pas chaque appui.
    const near = scorerSpot(a - 0.4);
    const ahead = scorerSpot(a + 0.4);
    const x = (near.x + ahead.x) / 2;
    const z = (near.z + ahead.z) / 2;
    const spot = scorerSpot(a);
    return { pos: [x + 1.4, 2.5, z + 8.5], look: [lerp(x, spot.x, 0.5), 1, spot.z - 4.5], fov: 28 };
  };
  const lowShot = (a) => {
    const spot = scorerSpot(a);
    return { pos: [spot.x - 7, 0.95, lerp(spot.z, 0, 0.45) + 0.4], look: [spot.x, 0.72, spot.z - 0.65], fov: 26 };
  };

  // La joie : il se relève, les siens lui sautent dessus, leur arrière reste au sol.
  const up = [LAND_X, -0.45];
  const circle = [
    [support, [LAND_X + 1.4, -0.4], 0.45],
    [flanker, [LAND_X + 0.3, 1], 0.85],
    [passer, [LAND_X + 1.3, 1], 1.1],
  ];
  function party(c) {
    action(END);
    const rise = smooth(span(c, 0.2, 0.75));
    scorer.place(LAND_X, lerp(DIVE_TO, up[1], rise), FACE_LINE);
    scorer.set(mixPose(dive(1), cheer(c * 1.4), rise));
    world.ballAt(grounded, v(1, 0, 0));
    circle.forEach(([player, spot, arrive], i) => {
      const startAt = [player.root.position.x, player.root.position.z];
      const heading = Math.atan2(up[0] - spot[0], up[1] - spot[1]);
      if (c < arrive) runner(player, route([startAt, spot]), c, 0, arrive, { from: 1, to: 0.6, speed: 0.9, still: ready(0.2) });
      else player.place(spot[0], spot[1], heading).set(cheer(c * 1.3 + i * 0.3));
    });
    winger.set(ground());
    // Leur arrière se relève et s'éloigne, tête basse : la fête n'est pas pour lui.
    const down = [LAND_X + 0.9, 1.5];
    const off = [LAND_X + 6.5, 5.5];
    if (c < 0.9) fullback.set(ground());
    else if (c < 1.3) fullback.set(mixPose(ground(), ready(0.2), smooth(span(c, 0.9, 1.3))));
    else runner(fullback, route([down, off]), c, 1.3, PARTY, { from: 0.4, to: 0.2, speed: 0.2, still: dejected() });
    chaser.place(chaser.root.position.x, chaser.root.position.z, chaser.heading).set(dejected());
    centre.set(dejected());
    ref.set(tryAward(1));
    const turn = smooth(span(c, 0, PARTY));
    return {
      pos: [lerp(LAND_X - 7.5, LAND_X - 6.2, turn), lerp(1.7, 2.3, turn), lerp(4.4, 3.4, turn)],
      look: [LAND_X + 0.6, 1.05, 0],
      fov: lerp(30, 32, turn),
    };
  }

  function frame(t) {
    world.exposure(t >= T3 + FADE ? 1 : dark(t));
    if (t < T1) {
      const a = A1(t);
      action(a);
      return followShot(a);
    }
    if (t < T2) {
      const a = A2(t - T1);
      action(a);
      return backShot(a);
    }
    if (t < T3) {
      const a = A3(t - T2);
      action(a);
      return lowShot(a);
    }
    return party(t - T3);
  }

  return {
    setup: {
      duration: 0.05,
      frame() {
        world.exposure(1);
        action(A1(0));
        return followShot(A1(0));
      },
      cues: [],
    },
    outcome() {
      return {
        duration,
        cues: [
          { at: 0.05, run: () => world.crowd("standing") },
          {
            at: DOWN1,
            run: () => {
              world.sound("whistle", true);
              reaction(world, true);
            },
          },
          { at: T1 + 0.1, run: () => world.crowd("standing") },
          { at: DOWN3, run: () => world.sound("impact") },
          { at: DOWN3 + 0.15, run: () => reaction(world, true) },
          { at: T3 + 0.3, run: () => reaction(world, true) },
        ],
        frame,
      };
    },
  };
}
