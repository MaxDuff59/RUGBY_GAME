import * as THREE from "three";

import { TOUCH } from "../field.js";
import { cheer, crouch, dejected, dive, ground, mixPose, pass, ready, run, signal, tackle, tryAward } from "../rig.js";
import { FACE_FIELD, FACE_LINE, broadcast, carried, headingTo, keys, lerp, lob, reaction, route, runner, smooth, span } from "./common.js";

// Carrière de joueur, « La passe à lire » (interception) : on défend la ligne z = 0, leur
// ouvreur arme une passe vers le vis-à-vis du joueur incarné. Sortir de la ligne (il
// cueille la passe et file : la contre-attaque prend la suite ; ou il a vu venir, la passe
// lui passe dans le dos), tenir sa place (il plaque le vis-à-vis sur la ligne d'avantage ;
// ou celui-ci le prend de vitesse), ou glisser (il l'accompagne jusqu'à la touche ; ou il
// repique dans le trou laissé).
//
// Le vis-à-vis lancé, deux fins selon l'effet tiré : l'essai encaissé, ou l'arrière qui
// revient et le prend à quelques mètres de la ligne (plaquage manqué, sans points).

const v = (x, y, z) => new THREE.Vector3(x, y, z);
const aim = (x, z, options) => {
  const shot = broadcast(x, z, options);
  shot.look[0] = x;
  return shot;
};

export function buildInterception(world, data) {
  const rng = world.rng;
  const s = rng() < 0.5 ? -1 : 1; // la touche, du côté du joueur incarné
  const T = 1.4;
  const zd = 20; // la ligne de défense
  const heroNo = data.hero ?? 13;
  const hero = world.player("us", heroNo, { hero: true });
  const inner = world.player("us", heroNo === 12 ? 13 : 12);
  const inner2 = world.player("us", heroNo === 10 ? 9 : 10);
  const cover = world.player("us", heroNo === 15 ? 14 : 15);
  const flyHalf = world.player("them", heroNo === 10 ? 9 : 10);
  const opposite = world.player("them", heroNo); // le vis-à-vis
  const flanker = world.player("them", heroNo === 7 ? 6 : 7);
  const deep = world.player("them", heroNo === 12 ? 13 : 12);
  const ref = world.player("ref");

  const at = {
    hero: [s * 22, zd],
    inner: [s * 15.5, zd],
    inner2: [s * 9, zd + 0.4],
    cover: [s * 10, 5],
    flyHalf: [s * 11, 26.5],
    opposite: [s * 25.5, 25.5],
    flanker: [s * 7.5, 25.5],
    deep: [s * 16, 30],
  };
  const refAt = [s * 15, 34];
  const ball = new THREE.Vector3();
  // Le joueur et le vis-à-vis cadrés hauts : vue de la tribune, la touche est tantôt au
  // fond de l'image (s > 0), tantôt devant (s < 0), juste au-dessus des voies.
  const lookX = s > 0 ? 18 : -27;
  const near = s > 0 ? 0 : -3;
  const shot = aim(lookX, zd + 2.5, { far: 1.05, fov: 34, y: -0.8 });
  const camera = keys([
    [0, [s * 18 - 42, 24, zd + 42, s * 16, 0, zd + 10, 44]],
    [T, [...shot.pos, ...shot.look, shot.fov]],
  ]);
  // Une passe vers +s en regardant la ligne z = 0 : sa droite si s > 0.
  const passSide = -s;
  const ARMED = pass(0.05, passSide);

  function setupFrame(t) {
    runner(hero, route([[at.hero[0], at.hero[1] - 5], at.hero]), t, 0, T, { from: 0.6, to: 0.4, speed: 0.6 });
    hero.set(mixPose(run(t * 2.2, 0.6), ready(0.8), smooth(span(t, 0.95, T))));
    runner(inner, route([[at.inner[0], at.inner[1] - 5], at.inner]), t, 0, T, { from: 0.6, to: 0.4, speed: 0.6 });
    runner(inner2, route([[at.inner2[0], at.inner2[1] - 5], at.inner2]), t, 0, T, { from: 0.6, to: 0.4, speed: 0.6 });
    runner(cover, route([[at.cover[0], at.cover[1] - 2], at.cover]), t, 0, T, { from: 0.4, to: 0.2, speed: 0.3 });
    cover.root.rotation.y = cover.heading = FACE_FIELD;
    runner(flyHalf, route([[at.flyHalf[0], at.flyHalf[1] + 7], at.flyHalf]), t, 0, T, { from: 0.7, to: 0.5, speed: 0.6 });
    flyHalf.set(mixPose(run(t * 2.2, 0.6, "two"), ARMED, smooth(span(t, 0.8, T))));
    runner(opposite, route([[at.opposite[0], at.opposite[1] + 8], at.opposite]), t, 0, T, { from: 0.8, to: 0.8, speed: 0.8 });
    runner(flanker, route([[at.flanker[0], at.flanker[1] + 7], at.flanker]), t, 0, T, { from: 0.7, to: 0.6, speed: 0.6 });
    runner(deep, route([[at.deep[0], at.deep[1] + 7], at.deep]), t, 0, T, { from: 0.7, to: 0.6, speed: 0.6 });
    ref.place(refAt[0], refAt[1], FACE_LINE).set(run(t * 2, 0.35));
    if (ref.card) ref.card.visible = false;
    world.ballAt(flyHalf.local(0, 1.12, 0.42, ball), v(1, 0, 0));
    const [cx, cy, cz, lx, ly, lz, fov] = camera(t);
    return { pos: [cx, cy, cz], look: [lx, ly, lz], fov };
  }

  const setup = {
    duration: T,
    frame: setupFrame,
    cues: [{ at: 0.1, run: () => world.crowd(world.pressure > 1 ? "standing" : "seated") }],
  };

  // Les tracés de chaque voie.
  const hands = () => flyHalf.local(0, 1.12, 0.42, new THREE.Vector3());
  const steal = [s * 19.4, 25.9];
  const stealRun = [steal, [s * 18, 38]];
  const toTouch = [s * 34.2, 19.4];

  function preview(key) {
    const draw = world.draw;
    if (key === "shoot") {
      const from = hands();
      const to = v(steal[0], 1.2, steal[1]);
      const arc = [];
      for (let i = 0; i <= 8; i++) arc.push(lob(from, to, 0.25, i / 8).toArray());
      return [draw.arc(arc, 0.07), draw.path([at.hero, steal]), draw.mark(steal, 0.8)];
    }
    if (key === "hold_line") return [draw.path([[at.inner2[0], zd + 1.2], [at.hero[0] + s * 2.5, zd + 1.2]], { dashed: false, width: 0.3 }), draw.arrow([at.hero[0], zd + 0.2], [at.hero[0], zd + 2.7], 1.4)];
    return [draw.path([at.hero, [s * 27, 22.4], toTouch]), draw.mark([s * (TOUCH - 0.4), 19.2], 1)];
  }

  // Le vis-à-vis lancé : le long de `points` jusqu'à l'essai (`scores`), ou jusqu'à
  // l'arrière qui le prend (fin du trajet + une ligne droite jusqu'à z = 7).
  const lineZ = -1.3;
  function escape(points, t0, scores) {
    const last = points[points.length - 1];
    const end = scores ? [last[0], lineZ + 0.8] : [last[0], 7];
    const path = route([...points, end]);
    return { path, end, t0, tEnd: t0 + path.total / 9 };
  }
  function breakaway(t, way, scores) {
    const { path, end, t0, tEnd } = way;
    if (t >= t0 && t < tEnd) runner(opposite, path, t, t0, tEnd, { from: 0.8, to: 1, speed: 1, carry: "one" });
    if (t >= tEnd) {
      const k = span(t, tEnd, tEnd + 0.45);
      if (scores) {
        opposite.place(end[0], lerp(end[1], lineZ, smooth(k)), FACE_LINE).set(t > tEnd + 1.2 ? cheer(t * 1.5) : dive(k));
      } else {
        opposite.place(end[0], end[1] - 0.5 * k, FACE_LINE + s * 0.35).set(k < 1 ? tackle(k * 0.6) : ground());
      }
    }
    // Le ballon : porté, puis aplati derrière la ligne (ou tenu au sol).
    if (t >= t0) {
      if (t < tEnd) world.ballAt(carried(opposite, "one", ball), v(0, 0, -1));
      else if (scores) world.ballAt(ball.set(end[0], lerp(1.08, 0.14, smooth(span(t, tEnd, tEnd + 0.4))), lerp(end[1], lineZ - 1.5, smooth(span(t, tEnd, tEnd + 0.4)))), v(1, 0, 0));
      else world.ballAt(ball.lerpVectors(carried(opposite, "one", new THREE.Vector3()), opposite.local(0, 0.3, 1.0, new THREE.Vector3()), smooth(span(t, tEnd, tEnd + 0.4))), v(1, 0, 0));
    }
    // L'arrière revient : il le prend de côté, ou arrive trop tard.
    const meet = [end[0] - s * 1.6, end[1] - 0.4];
    const late = [end[0] - s * 4, 2.2];
    runner(cover, route([at.cover, scores ? late : meet]), t, Math.max(0, t0 - 0.6), tEnd, { from: 0.5, to: 1, speed: 1 });
    if (t >= tEnd) {
      if (scores) cover.set(t > tEnd + 0.8 ? dejected() : ready(0.3));
      else cover.place(meet[0], meet[1], (s * Math.PI) / 2).set(tackle(span(t, tEnd, tEnd + 0.45)));
    }
    if (scores && t > tEnd + 0.4) {
      ref.place(end[0] + 4.5, 2.4, -Math.PI / 2).set(tryAward(smooth(span(t, tEnd + 0.4, tEnd + 0.75))));
    }
    return tEnd;
  }

  // La passe de l'ouvreur : lâchée à `release`, reçue à `arrive`, puis il regarde.
  function theirPass(t, release, arrive, target) {
    flyHalf.place(at.flyHalf[0], at.flyHalf[1] - Math.min(t, 0.7) * 2.5, FACE_LINE);
    flyHalf.set(t < release + 0.35 ? pass(span(t, release - 0.2, release + 0.15), passSide) : ready(0.2));
    if (t < release) world.ballAt(hands().clone(), v(1, 0, 0));
    else if (t < arrive) world.ballAt(lob(hands().clone(), target(), 0.3, span(t, release, arrive), ball), v(s, 0.1, 0.1));
  }
  // Les autres continuent de monter, puis ralentissent.
  function others(t) {
    runner(inner, route([at.inner, [at.inner[0], zd + 4.5]]), t, 0, 1.4, { from: 0.6, to: 0.2, speed: 0.6 });
    runner(inner2, route([at.inner2, [at.inner2[0], zd + 4.8]]), t, 0, 1.4, { from: 0.6, to: 0.2, speed: 0.6 });
    runner(flanker, route([at.flanker, [at.flanker[0] + s * 1.5, 21]]), t, 0, 1.6, { from: 0.7, to: 0.2, speed: 0.6 });
    runner(deep, route([at.deep, [at.deep[0] - s * 0.5, 25]]), t, 0, 1.6, { from: 0.7, to: 0.2, speed: 0.6 });
  }

  function outcomeFor(key, result) {
    const { success: good, effect } = result;
    const scores = !good && effect === "try_conceded";
    const cues = [];
    let duration = 3;
    let frame;

    if (key === "shoot" && good) {
      // Il cueille la passe et file vers le camp adverse : la contre-attaque s'enchaîne.
      const catchAt = 0.85;
      duration = 2.3;
      cues.push({ at: catchAt, run: () => reaction(world, true) });
      frame = (t) => {
        others(t);
        runner(hero, route([at.hero, steal]), t, 0, catchAt, { from: 0.6, to: 1, speed: 1 });
        if (t >= catchAt) runner(hero, route(stealRun), t, catchAt, duration, { from: 0.9, to: 1, speed: 1, carry: "one" });
        theirPass(t, 0.2, catchAt, () => carried(hero, "two", new THREE.Vector3()));
        if (t >= catchAt) world.ballAt(carried(hero, "one", ball), v(0, 0, 1));
        // Le vis-à-vis attendait le ballon : il freine, se retourne et court après.
        const stopAt = [s * 25.2, 23.4];
        runner(opposite, route([at.opposite, stopAt]), t, 0, catchAt + 0.1, { from: 0.8, to: 0.1, speed: 0.7 });
        if (t >= catchAt + 0.1) runner(opposite, route([stopAt, [s * 22, 33]]), t, catchAt + 0.25, duration, { from: 0.2, to: 0.9, speed: 0.8 });
        if (t >= catchAt + 0.4) {
          flyHalf.set(dejected());
          deep.root.rotation.y = deep.heading = headingTo(deep.root.position.x, deep.root.position.z, hero.root.position.x, hero.root.position.z);
        }
        const follow = smooth(span(t, 0.5, catchAt + 0.6));
        return aim(lerp(lookX, hero.root.position.x + near, follow), lerp(zd + 3, hero.root.position.z + 2, follow), { far: lerp(1, 0.9, follow), fov: 33, y: lerp(-0.4, -0.9, follow) });
      };
    } else if (key === "hold_line" && good) {
      // La ligne monte droite, il plaque le vis-à-vis sur la ligne d'avantage.
      const catchAt = 0.85;
      const hit = 1.2;
      const c = [s * 23.8, 21.6];
      const caught = [s * 24.8, 23.4];
      duration = 3;
      cues.push({ at: hit, run: () => world.sound("impact") }, { at: hit + 0.35, run: () => reaction(world, true) });
      frame = (t) => {
        others(t);
        runner(hero, route([at.hero, [c[0], c[1] - 0.2]]), t, 0, hit, { from: 0.5, to: 0.9, speed: 0.8 });
        runner(opposite, route([at.opposite, caught, c]), t, 0, hit, { from: 0.8, to: 1, speed: 0.9, carry: t >= catchAt ? "one" : "none" });
        theirPass(t, 0.2, catchAt, () => carried(opposite, "two", new THREE.Vector3()));
        if (t >= hit) {
          const k = span(t, hit, hit + 0.45);
          hero.place(c[0], c[1] - 0.2 + 0.9 * smooth(k), FACE_FIELD).set(tackle(k));
          opposite.place(c[0] + s * 0.2, c[1] + 0.7 + 1.1 * smooth(k), FACE_LINE).set(mixPose(run(1.25, 1, "one"), ground(true), smooth(k * 1.4)));
        }
        if (t >= catchAt) world.ballAt(carried(opposite, t >= hit + 0.3 ? "low" : "one", ball), v(1, 0, 0));
        // Le premier soutien arrive sur le ballon, de chaque côté.
        runner(inner, route([at.inner, [c[0] - s * 1.5, c[1] + 0.4]]), t, 0, 2.1, { from: 0.6, to: 0.3, speed: 0.7 });
        if (t >= 2.1) inner.set(crouch(0.8));
        return aim(s * 22.2 + near * 1.3, 22.2, { far: 0.95, fov: 33, y: lerp(-0.8, -0.9, smooth(span(t, 0, 1))) });
      };
    } else if (key === "drift" && good) {
      // Il glisse à son épaule intérieure, le pousse jusqu'à la touche : plus d'espace.
      const catchAt = 1;
      const out = [s * (TOUCH + 1.4), 19];
      const rideAt = 2.2;
      duration = 3.3;
      cues.push(
        { at: rideAt - 0.25, run: () => world.sound("impact") },
        { at: rideAt, run: () => world.sound("whistle") },
        { at: rideAt + 0.1, run: () => reaction(world, true) },
      );
      frame = (t) => {
        others(t);
        runner(hero, route([at.hero, [s * 27, 22.4], toTouch]), t, 0, rideAt, { from: 0.6, to: 0.8, speed: 0.8 });
        if (t >= rideAt) hero.place(toTouch[0], toTouch[1], FACE_LINE).set(t > rideAt + 0.6 ? cheer(t * 1.5) : ready(0.3));
        runner(opposite, route([at.opposite, [s * 27, 24.6], [s * 31.5, 23.2], out]), t, 0, rideAt, { from: 0.8, to: 0.7, speed: 0.85, carry: t >= catchAt ? "one" : "none" });
        if (t >= rideAt) opposite.place(out[0], out[1], FACE_LINE).set(dejected());
        theirPass(t, 0.2, catchAt, () => carried(opposite, "two", new THREE.Vector3()));
        if (t >= catchAt) world.ballAt(carried(opposite, t >= rideAt ? "two" : "one", ball), v(0, 0, -1));
        runner(ref, route([refAt, [s * 27, 25]]), t, 0, rideAt, { from: 0.4, to: 0.1, speed: 0.6 });
        if (t >= rideAt) ref.set(signal(1, smooth(span(t, rideAt, rideAt + 0.3))));
        const follow = smooth(span(t, 0.5, 1.7));
        return aim(lerp(lookX, s * 30.5 + near, follow), lerp(zd + 3, 22, follow), { far: 0.95, fov: 33, y: lerp(-0.6, -0.9, follow) });
      };
    } else if (key === "shoot") {
      // Sorti trop tôt : l'ouvreur retient sa passe, elle file dans le dos du joueur.
      const release = 0.55;
      const catchAt = 1.15;
      const pastLine = [s * 17.5, 28];
      const taken = [s * 25, 22.6];
      const way = escape([taken, [s * 24.5, 15]], catchAt, scores);
      const tEnd = way.tEnd;
      duration = tEnd + (scores ? 2.1 : 1.3);
      cues.push({ at: catchAt, run: () => world.sound("groan") });
      if (scores) cues.push({ at: tEnd + 0.35, run: () => (world.sound("whistle", true), reaction(world, false)) });
      else cues.push({ at: tEnd, run: () => world.sound("impact") }, { at: tEnd + 0.35, run: () => world.crowd("standing") });
      frame = (t) => {
        others(t);
        runner(hero, route([at.hero, pastLine]), t, 0, 0.95, { from: 0.6, to: 0.6, speed: 1 });
        if (t >= 0.95) {
          // Il se retourne, trop tard.
          const turn = smooth(span(t, 0.95, 1.35));
          hero.place(pastLine[0], pastLine[1], s * lerp(-0.2, Math.PI * 0.8, turn)).set(ready(0.4));
          if (t > tEnd - 0.6) hero.set(dejected());
        }
        runner(opposite, route([at.opposite, taken]), t, 0, catchAt, { from: 0.5, to: 0.8, speed: 0.7 });
        theirPass(t, release, catchAt, () => carried(opposite, "two", new THREE.Vector3()));
        breakaway(t, way, scores);
        const follow = smooth(span(t, 0.9, 2));
        return aim(lerp(lookX, opposite.root.position.x + near, follow), lerp(zd + 3, Math.max(opposite.root.position.z - 1, 0), follow), { far: 0.95, fov: 33, y: lerp(-0.6, -0.9, follow) });
      };
    } else if (key === "hold_line") {
      // Il tient sa place, mais le vis-à-vis accélère par l'extérieur.
      const catchAt = 0.85;
      const taken = [s * 26, 23.6];
      const lungeFrom = [s * 24.7, 20.8];
      const way = escape([taken, [s * 28.5, 20.4], [s * 28.2, 15]], catchAt, scores);
      const tEnd = way.tEnd;
      duration = tEnd + (scores ? 2.1 : 1.3);
      cues.push({ at: 1.35, run: () => world.sound("groan") });
      if (scores) cues.push({ at: tEnd + 0.35, run: () => (world.sound("whistle", true), reaction(world, false)) });
      else cues.push({ at: tEnd, run: () => world.sound("impact") }, { at: tEnd + 0.35, run: () => world.crowd("standing") });
      frame = (t) => {
        others(t);
        runner(hero, route([at.hero, lungeFrom]), t, 0, 1.1, { from: 0.5, to: 0.8, speed: 0.7 });
        if (t >= 1.1) {
          const k = span(t, 1.1, 1.65);
          hero.place(lerp(lungeFrom[0], s * 25.6, smooth(k)), lerp(lungeFrom[1], 20.2, smooth(k)), (s * Math.PI) / 2).set(k < 1 ? tackle(k) : ground());
        }
        runner(opposite, route([at.opposite, taken]), t, 0, catchAt, { from: 0.8, to: 0.9, speed: 0.8 });
        theirPass(t, 0.2, catchAt, () => carried(opposite, "two", new THREE.Vector3()));
        breakaway(t, way, scores);
        const follow = smooth(span(t, 1, 2.1));
        return aim(lerp(lookX, opposite.root.position.x + near, follow), lerp(zd + 2.4, Math.max(opposite.root.position.z - 1, 0), follow), { far: 0.95, fov: 33, y: lerp(-0.6, -0.9, follow) });
      };
    } else {
      // Il glisse vers la touche, le vis-à-vis repique à l'intérieur dans le trou laissé.
      const catchAt = 1;
      const plant = [s * 27.2, 24];
      const wrong = [s * 27.5, 21.2];
      const way = escape([plant, [s * 23.8, 19.2], [s * 20.5, 15]], 1.1, scores);
      const tEnd = way.tEnd;
      duration = tEnd + (scores ? 2.1 : 1.3);
      cues.push({ at: 1.5, run: () => world.sound("groan") });
      if (scores) cues.push({ at: tEnd + 0.35, run: () => (world.sound("whistle", true), reaction(world, false)) });
      else cues.push({ at: tEnd, run: () => world.sound("impact") }, { at: tEnd + 0.35, run: () => world.crowd("standing") });
      frame = (t) => {
        others(t);
        runner(hero, route([at.hero, wrong]), t, 0, 1.25, { from: 0.6, to: 0.7, speed: 0.7 });
        if (t >= 1.25) {
          const k = span(t, 1.25, 1.85);
          hero.place(lerp(wrong[0], s * 26, smooth(k)), lerp(wrong[1], 20.6, smooth(k)), -s * Math.PI * 0.55).set(k < 1 ? tackle(k) : ground());
        }
        runner(opposite, route([at.opposite, plant]), t, 0, 1.1, { from: 0.8, to: 0.8, speed: 0.8, carry: t >= catchAt ? "one" : "none" });
        theirPass(t, 0.2, catchAt, () => carried(opposite, "two", new THREE.Vector3()));
        if (t >= catchAt && t < 1.1) world.ballAt(carried(opposite, "one", ball), v(0, 0, -1));
        breakaway(t, way, scores);
        const follow = smooth(span(t, 1.1, 2.2));
        return aim(lerp(lookX, opposite.root.position.x + near, follow), lerp(zd + 2.4, Math.max(opposite.root.position.z - 1, 0), follow), { far: 0.95, fov: 33, y: lerp(-0.6, -0.9, follow) });
      };
    }
    return {
      duration,
      cues,
      frame(t) {
        setupFrame(T);
        return frame(t);
      },
    };
  }

  return { setup, preview, outcome: outcomeFor };
}
