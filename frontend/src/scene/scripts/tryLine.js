import * as THREE from "three";

import { cheer, crouch, dejected, dive, ground, pass, pose, ready, signal, tackle, tryAward } from "../rig.js";
import { FACE_FIELD, FACE_LINE, broadcast, carried, keys, lerp, lob, penaltyAgainst, reaction, route, runner, smooth, span } from "./common.js";

// Carrière de joueur, « À cinq mètres de la ligne » (try_line) : le joueur incarné
// porte le ballon à cinq mètres de l'en-but, la défense regroupée devant lui. Plonger
// seul (par-dessus, ou tenu au-dessus de la ligne), décaler un partenaire (qui aplatit,
// ou la passe est interceptée), ou jouer le temps de jeu (au sol, ballon présenté : la
// défense craque et concède la pénalité, ou le ballon est ralenti).

const BRACE = pose({ y: -0.22, lean: 0.55, legL: 0.6, legR: 0.4, knL: 1.0, knR: 0.8, armL: 0.9, armR: 0.9, elL: 0.8, elR: 0.8 });

export function buildTryLine(world, data) {
  const rng = world.rng;
  const s = rng() < 0.5 ? -1 : 1; // le côté du soutien
  const hx = -s * (3 + rng() * 7);
  const hz = 4.4;
  const heroNo = data.hero ?? 8;
  const hero = world.player("us", heroNo, { hero: true });
  const nine = heroNo === 9 ? null : world.player("us", 9);
  const support = world.player("us", heroNo === 4 ? 5 : 4);
  const second = world.player("us", heroNo === 6 ? 7 : 6);
  const ruckBody = world.player("us", 3);
  const wall = [-2.4, -0.8, 0.8, 2.4].map((dx, i) => [world.player("them", [6, 4, 5, 7][i]), [hx + dx, 1.9 + (i % 2) * 0.35]]);
  const ref = world.player("ref");
  const ruck = [hx - s * 1.2, 8.4];
  const start = {
    hero: nine ? [hx - s * 0.6, 9.4] : [ruck[0] + s * 0.4, ruck[1] + 0.8],
    support: [hx + s * 3.6, 9.5],
    second: [hx - s * 2.6, 10],
  };
  const end = { hero: [hx, hz], support: [hx + s * 3.3, 6.2], second: [hx - s * 2.4, 6.8] };
  const ball = new THREE.Vector3();
  const from = new THREE.Vector3();
  const to = new THREE.Vector3();
  const shot = broadcast(hx, 3.2, { far: 0.75, fov: 32, y: 0.3 });
  const camera = keys([
    [0, [hx - 52, 24, 36, hx * 0.6, 0, 8, 44]],
    [1.2, [...shot.pos, ...shot.look, shot.fov]],
  ]);
  const passAt = [0.15, 0.45];
  const refSpot = [hx - s * 6, 2.5];

  function setupFrame(t) {
    ruckBody.place(ruck[0], ruck[1] - 0.4, FACE_LINE + 0.4).set(ground());
    if (nine) {
      nine.place(ruck[0] + s * 0.3, ruck[1] + 0.9, FACE_LINE + s * 0.6).set(t < passAt[0] ? crouch(1) : pass(span(t, passAt[0] - 0.1, passAt[0] + 0.2), s));
      runner(hero, route([start.hero, end.hero]), t, 0, 1.2, { from: 0.6, to: 0.5, speed: 0.6, carry: t > passAt[1] ? "two" : "none" });
      if (t < passAt[0]) world.ballAt(carried(nine, "low", ball), new THREE.Vector3(1, 0, 0));
      else if (t < passAt[1]) {
        carried(nine, "two", from);
        carried(hero, "two", to);
        world.ballAt(lob(from, to, 0.3, span(t, ...passAt), ball), new THREE.Vector3(1, 0, 0));
      } else world.ballAt(carried(hero, "two", ball), new THREE.Vector3(1, 0, 0));
    } else {
      runner(hero, route([start.hero, end.hero]), t, 0.2, 1.2, { from: 0.3, to: 0.5, speed: 0.6, carry: "two" });
      if (t < 0.2) hero.set(crouch(1));
      world.ballAt(carried(hero, t < 0.2 ? "low" : "two", ball), new THREE.Vector3(1, 0, 0));
    }
    runner(support, route([start.support, end.support]), t, 0, 1.2, { from: 0.6, to: 0.6, speed: 0.6 });
    runner(second, route([start.second, end.second]), t, 0, 1.2, { from: 0.5, to: 0.4, speed: 0.5 });
    // La défense, regroupée et basse, monte d'un pas.
    for (const [player, [x, z]] of wall) {
      player.place(x, lerp(z - 0.7, z, smooth(t / 1.2)), FACE_FIELD).set(BRACE);
    }
    ref.place(refSpot[0], refSpot[1], (s * Math.PI) / 2).set(ready(0.1));
    const [cx, cy, cz, lx, ly, lz, fov] = camera(t);
    return { pos: [cx, cy, cz], look: [lx, ly, lz], fov };
  }

  const setup = {
    duration: 1.2,
    frame: setupFrame,
    cues: [{ at: 0.1, run: () => world.crowd("standing") }],
  };

  const supportLine = [end.support, [end.support[0] + s * 0.4, -1.3]];
  function preview(key) {
    const draw = world.draw;
    if (key === "dive") return [draw.arrow([hx, hz - 0.4], [hx, -1.6], 1.4), draw.mark([hx, -1.3])];
    if (key === "offload") {
      const a = carried(hero, "two", new THREE.Vector3());
      const b = carried(support, "two", new THREE.Vector3());
      const arc = [];
      for (let i = 0; i <= 10; i++) arc.push(lob(a, b, 0.3, i / 10).toArray());
      return [draw.arc(arc, 0.08), draw.path(supportLine), draw.mark(supportLine[1])];
    }
    return [draw.path([end.hero, [hx, hz - 1.2]]), draw.mark([hx, hz - 1.4], 1.1)];
  }

  // La défense au contact : ceux du milieu plaquent le porteur.
  const brace = (t, at, onto) => {
    for (const [player, [x, z]] of wall) {
      const near = Math.abs(x - onto[0]) < 1.7;
      const k = span(t, at - 0.1, at + 0.4);
      if (near) player.place(lerp(x, onto[0] + (x - onto[0]) * 0.4, k), lerp(z, onto[1] - 0.6, k), FACE_FIELD).set(tackle(k * 0.6));
      else player.place(x, z, FACE_FIELD).set(BRACE);
    }
  };

  function diveOutcome(good) {
    const jumpAt = 0.35;
    const land = good ? -0.9 : 0.6;
    const scoreAt = 1.15;
    return {
      duration: 3,
      cues: [
        { at: jumpAt + 0.1, run: () => world.sound("impact") },
        {
          at: scoreAt,
          run: () => {
            world.sound("whistle", true);
            reaction(world, good);
          },
        },
      ],
      frame(t) {
        setupFrame(1.2);
        brace(t, jumpAt + 0.1, [hx, hz - 1.5]);
        runner(hero, route([end.hero, [hx, hz - 1.2]]), t, 0, jumpAt, { from: 0.5, to: 0.9, speed: 0.8, carry: "two" });
        if (t >= jumpAt) {
          // Par-dessus la mêlée de bras ; tenu en l'air au-dessus de la ligne, s'il échoue.
          const k = span(t, jumpAt, jumpAt + 0.6);
          const held = !good && k > 0.6;
          hero.place(hx, lerp(hz - 1.2, land, smooth(k)), FACE_LINE).set({ ...dive(held ? 0.6 : k), lift: held ? 0.65 : dive(k).lift + (good ? 0 : 0.3 * k) });
          if (good && t > scoreAt + 0.8) hero.set(cheer(t * 1.5));
        }
        world.ballAt(carried(hero, t > jumpAt ? "low" : "two", ball), new THREE.Vector3(1, 0, 0));
        runner(support, route([end.support, [end.support[0] - s * 1.5, 1.5]]), t, 0, 1.0, { from: 0.6, to: 0.2, speed: 0.6 });
        if (t > scoreAt + 0.4) support.set(good ? cheer(t * 1.4 + 1) : dejected());
        ref.place(refSpot[0], refSpot[1], (s * Math.PI) / 2);
        ref.set(t > scoreAt ? (good ? tryAward(smooth(span(t, scoreAt, scoreAt + 0.35))) : signal(1, smooth(span(t, scoreAt, scoreAt + 0.3)))) : ready(0.1));
        return shot;
      },
    };
  }

  function offloadOutcome(good) {
    const hit = 0.4;
    const release = 0.45;
    const arrive = 0.75;
    const thief = wall.reduce((best, item) => (Math.abs(item[1][0] - end.support[0]) < Math.abs(best[1][0] - end.support[0]) ? item : best))[0];
    const scoreAt = 1.55;
    return {
      duration: good ? 3.2 : 3,
      cues: [
        { at: hit, run: () => world.sound("impact") },
        {
          at: good ? scoreAt : arrive + 0.2,
          run: () => {
            if (good) world.sound("whistle", true);
            reaction(world, good);
          },
        },
      ],
      frame(t) {
        setupFrame(1.2);
        brace(t, hit, [hx, hz - 1.4]);
        runner(hero, route([end.hero, [hx, hz - 1.3]]), t, 0, hit, { from: 0.5, to: 0.7, speed: 0.7, carry: "two" });
        if (t >= hit) hero.place(hx, hz - 1.3, FACE_LINE).set(t < release + 0.3 ? pass(span(t, release - 0.15, release + 0.15), s) : tackle(0.4));
        carried(hero, "two", from);
        if (good) {
          // Le partenaire prend la passe lancé et plonge dans l'en-but.
          const path = route(supportLine);
          if (t < 1.15) runner(support, path, t, 0, 1.15, { from: 0.6, to: 1, speed: 0.95, carry: t > arrive ? "two" : "none" });
          else {
            const k = span(t, 1.15, 1.55);
            support.place(supportLine[1][0], lerp(0.2, -1.3, smooth(k)), FACE_LINE).set(t > scoreAt + 0.8 ? cheer(t * 1.5) : dive(k));
          }
          if (t < release) world.ballAt(from, new THREE.Vector3(1, 0, 0));
          else if (t < arrive) world.ballAt(lob(from, carried(support, "two", to), 0.3, span(t, release, arrive), ball), new THREE.Vector3(1, 0, 0));
          else world.ballAt(carried(support, t > 1.15 ? "low" : "two", ball), new THREE.Vector3(1, 0, 0));
          ref.place(refSpot[0], refSpot[1], (s * Math.PI) / 2).set(t > scoreAt ? tryAward(smooth(span(t, scoreAt, scoreAt + 0.35))) : ready(0.1));
        } else {
          // Interceptée : leur flanker s'interpose et remonte le terrain.
          const [tx, tz] = wall.find((item) => item[0] === thief)[1];
          const cut = [lerp(hx, end.support[0], 0.6), 3.4];
          if (t < arrive) thief.place(lerp(tx, cut[0], smooth(span(t, 0.3, arrive))), lerp(tz, cut[1], smooth(span(t, 0.3, arrive))), FACE_FIELD).set(ready(0.5));
          else runner(thief, route([cut, [cut[0] + s * 2, 16]]), t, arrive, 3, { from: 0.4, to: 1, speed: 0.95, carry: "one" });
          runner(support, route([end.support, [end.support[0], 4.5]]), t, 0, 0.9, { from: 0.6, to: 0.1, speed: 0.6 });
          if (t > 1.2) support.set(dejected());
          const catchPoint = new THREE.Vector3(cut[0], 1.2, cut[1] + 0.3);
          if (t < release) world.ballAt(from, new THREE.Vector3(1, 0, 0));
          else if (t < arrive) world.ballAt(lob(from, catchPoint, 0.2, span(t, release, arrive), ball), new THREE.Vector3(1, 0, 0));
          else world.ballAt(carried(thief, "one", ball), new THREE.Vector3(0, 0, 1));
          ref.place(refSpot[0], refSpot[1], (s * Math.PI) / 2).set(ready(0.1));
          if (t > 1.2) return broadcast(thief.root.position.x, thief.root.position.z - 1, { far: 0.85 });
        }
        return shot;
      },
    };
  }

  // Le temps de jeu : au sol, le ballon présenté, les nôtres liés par-dessus.
  function recycleOutcome(result) {
    const good = result.success;
    const down = 0.5;
    const callAt = 1.3;
    const lost = !good && result.effect === "lost";
    const jackal = wall[1][0];
    return {
      duration: 3,
      cues: [
        { at: down, run: () => world.sound("impact") },
        {
          at: callAt,
          run: () => {
            if (good) penaltyAgainst(world, "them");
            else world.sound("groan");
          },
        },
      ],
      frame(t) {
        setupFrame(1.2);
        brace(t, down, [hx, hz - 1]);
        runner(hero, route([end.hero, [hx, hz - 1]]), t, 0, down, { from: 0.5, to: 0.5, speed: 0.6, carry: "two" });
        if (t >= down) hero.place(hx, hz - 0.6, FACE_LINE).set(ground());
        // Les nôtres viennent lier le ruck.
        runner(support, route([end.support, [hx + s * 0.5, hz + 0.6]]), t, 0, down + 0.4, { from: 0.6, to: 0.3, speed: 0.6 });
        if (t > down + 0.4) support.place(hx + s * 0.5, hz + 0.6, FACE_LINE).set(crouch(0.9));
        runner(second, route([end.second, [hx - s * 0.5, hz + 0.7]]), t, 0, down + 0.5, { from: 0.5, to: 0.3, speed: 0.6 });
        if (t > down + 0.5) second.place(hx - s * 0.5, hz + 0.7, FACE_LINE).set(crouch(0.9));
        // Le ballon posé derrière lui ; ralenti, leur 4 met les mains dessus.
        const placed = new THREE.Vector3(hx, 0.12, hz + 0.4);
        if (t < down) world.ballAt(carried(hero, "two", ball), new THREE.Vector3(1, 0, 0));
        else if (lost && t > 1.6) world.ballAt(carried(jackal, "two", ball), new THREE.Vector3(1, 0, 0));
        else world.ballAt(placed, new THREE.Vector3(1, 0, 0));
        if (good && t > down + 0.3) wall[2][0].place(hx + 0.6, hz - 0.2, FACE_FIELD + 0.6).set(ground()); // au sol, du mauvais côté
        if (!good && t > down + 0.3) jackal.place(hx + 0.1, hz - 0.9, FACE_FIELD).set(t > 1.6 && lost ? ready(0.4) : crouch(1));
        ref.place(refSpot[0], refSpot[1], (s * Math.PI) / 2);
        // L'arbitre lève le bras vers notre attaque (-z) : pour nous ; sinon, rien.
        ref.set(good && t > callAt ? signal(s > 0 ? 1 : -1, smooth(span(t, callAt, callAt + 0.3))) : ready(0.1));
        return shot;
      },
    };
  }

  return {
    setup,
    preview,
    outcome(key, result) {
      if (key === "dive") return diveOutcome(result.success);
      if (key === "offload") return offloadOutcome(result.success);
      return recycleOutcome(result);
    },
  };
}
