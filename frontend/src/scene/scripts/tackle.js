import * as THREE from "three";

import { card, cheer, crouch, dejected, dive, ground, pose, ready, run, signal, tackle, tryAward } from "../rig.js";
import { FACE_FIELD, FACE_LINE, broadcast, carried, keys, lerp, lob, penaltyAgainst, reaction, route, runner, smooth, span } from "./common.js";

// Carrière de joueur, « Un attaquant lancé » (tackle) : un attaquant adverse arrive
// dans le couloir du joueur incarné, qui défend sa ligne (z = 0). Le plaquage offensif
// (il le renverse, le ballon sort), le plaquage à deux (un partenaire arrive), ou
// viser le ballon (il l'arrache, ou plaque trop haut : pénalité, carton jaune).
//
// Les échecs suivent l'effet tiré : plaquage manqué (un défenseur rattrape plus loin),
// essai encaissé (l'attaquant file à l'essai), pénalité concédée, carton jaune.

const HIGH = pose({ lean: 0.3, armL: 1.9, armR: 1.9, abL: -0.3, abR: -0.3, elL: 0.6, elR: 0.6, legL: 0.4, knL: 0.5, knR: 0.3 });
const WRESTLE = pose({ y: -0.1, lean: 0.45, armL: 1.3, armR: 1.4, abL: -0.35, abR: -0.35, elL: 1.0, elR: 0.9, legL: 0.4, legR: -0.2, knL: 0.6, knR: 0.4 });

export function buildTackle(world, data) {
  const rng = world.rng;
  const s = rng() < 0.5 ? -1 : 1;
  const hx = s * (4 + rng() * 6);
  const hz = 12.5;
  const heroNo = data.hero ?? 7;
  const hero = world.player("us", heroNo, { hero: true });
  const partner = world.player("us", heroNo === 6 ? 7 : 6);
  const cover = world.player("us", heroNo === 15 ? 14 : 15);
  const attacker = world.player("them", 12);
  const runnerB = world.player("them", 13);
  const ref = world.player("ref");

  const start = {
    hero: [hx, 10.5],
    partner: [hx - s * 3.8, 12],
    cover: [hx + s * 9, 4],
    attacker: [hx + s * 3.5, 30],
    runnerB: [hx + s * 6.5, 32],
  };
  const end = {
    hero: [hx, hz],
    partner: [hx - s * 3.2, 13.6],
    cover: [hx + s * 8, 5],
    attacker: [hx + s * 1.1, 16.8],
    runnerB: [hx + s * 5.5, 19.8],
  };
  const paths = Object.fromEntries(Object.keys(start).map((key) => [key, route([start[key], end[key]])]));
  const contact = [hx + s * 0.5, 14.2];
  const ball = new THREE.Vector3();
  const shot = broadcast(hx + s * 0.5, 15, { far: 0.9 });
  const camera = keys([
    [0, [hx - 56, 25, 46, hx * 0.6, 0.5, 18, 44]],
    [1.4, [...shot.pos, ...shot.look, shot.fov]],
  ]);
  const refSpot = [hx - s * 7, 19];

  function setupFrame(t) {
    runner(hero, paths.hero, t, 0, 1.4, { from: 0.4, to: 0.2, speed: 0.3 });
    hero.root.rotation.y = hero.heading = FACE_FIELD;
    if (t > 1.1) hero.set(ready(0.8));
    runner(partner, paths.partner, t, 0, 1.4, { from: 0.4, to: 0.3, speed: 0.4 });
    partner.root.rotation.y = partner.heading = FACE_FIELD + s * 0.4;
    runner(cover, paths.cover, t, 0, 1.4, { from: 0.3, to: 0.2, speed: 0.3 });
    runner(attacker, paths.attacker, t, 0, 1.4, { from: 0.9, to: 1, speed: 1, carry: "one" });
    runner(runnerB, paths.runnerB, t, 0, 1.4, { from: 0.9, to: 0.9, speed: 0.9 });
    ref.place(refSpot[0], refSpot[1], Math.PI / 2).set(ready(0.1));
    world.ballAt(carried(attacker, "one", ball), new THREE.Vector3(0, 0, -1));
    const [cx, cy, cz, lx, ly, lz, fov] = camera(t);
    return { pos: [cx, cy, cz], look: [lx, ly, lz], fov };
  }

  const setup = {
    duration: 1.4,
    frame: setupFrame,
    cues: [{ at: 0.1, run: () => world.crowd(world.pressure > 1 ? "standing" : "seated") }],
  };

  function preview(key) {
    const draw = world.draw;
    if (key === "smash") return [draw.arrow([hx, hz + 0.3], [contact[0], contact[1] + 1.6], 1.4)];
    if (key === "hold") return [draw.path([end.partner, [contact[0] - s * 0.6, contact[1]]]), draw.mark(contact, 0.8)];
    return [draw.path([end.hero, contact]), draw.mark(end.attacker, 0.55)];
  }

  // L'attaquant passe : il file à l'essai (`scores`) ou un défenseur le rattrape.
  const sidestep = [contact[0] + s * 1.4, contact[1] - 0.8];
  const escape = (at, scores) => {
    const lineSpot = [sidestep[0] + s * 1.5, -1.2];
    const caught = [sidestep[0] + s * 2.5, 5.5];
    const path = route([sidestep, scores ? [lineSpot[0], lineSpot[1] + 0.8] : caught]);
    return { lineSpot, caught, path, tEnd: at + path.total / 8 };
  };
  function breakaway(t, at, scores) {
    const { lineSpot, caught, path, tEnd } = escape(at, scores);
    if (t < tEnd) runner(attacker, path, t, at, tEnd, { from: 0.8, to: 1, speed: 1, carry: "one" });
    else if (scores) {
      const k = span(t, tEnd, tEnd + 0.45);
      attacker.place(lineSpot[0], lerp(lineSpot[1] + 0.8, lineSpot[1], smooth(k)), FACE_LINE).set(t > tEnd + 1.1 ? cheer(t * 1.5) : dive(k));
    } else {
      const k = span(t, tEnd, tEnd + 0.5);
      attacker.place(caught[0], caught[1] - 0.5 * k, FACE_LINE).set(k < 1 ? tackle(k * 0.6) : ground());
    }
    // L'arrière revient couvrir, plaque s'il le peut.
    runner(cover, route([end.cover, scores ? [lineSpot[0] + s * 2, 1.5] : [caught[0] + s * 0.3, caught[1] - 0.8]]), t, at - 0.2, tEnd, { from: 0.5, to: 1, speed: 0.9 });
    if (!scores && t >= tEnd) cover.place(caught[0] + s * 0.3, caught[1] - 0.8, FACE_FIELD).set(tackle(span(t, tEnd, tEnd + 0.45)));
    world.ballAt(carried(attacker, t > tEnd && scores ? "low" : "one", ball), new THREE.Vector3(0, 0, -1));
    return { tEnd, spot: scores ? lineSpot : caught };
  }

  const others = (t, duration) => {
    runner(runnerB, route([end.runnerB, [end.runnerB[0] - s * 0.5, 9]]), t, 0, duration, { from: 0.9, to: 0.6, speed: 0.8 });
  };

  function outcomeFor(key, result) {
    const { success, effect } = result;
    const hit = key === "hold" ? 0.55 : 0.45;
    const attackerTo = route([end.attacker, contact]);
    const scored = escape(hit, true).tEnd + 0.4; // l'essai encaissé
    const duration = success ? 2.6 : effect === "try_conceded" ? scored + 1.8 : effect === "yellow" ? 3.4 : 2.8;
    const cues = [{ at: hit, run: () => world.sound("impact") }];
    if (success) cues.push({ at: hit + 0.5, run: () => reaction(world, true) });
    else if (effect === "try_conceded") {
      cues.push({
        at: scored,
        run: () => {
          world.sound("whistle", true);
          reaction(world, false);
        },
      });
    }
    else if (effect === "yellow" || effect === "penalty_conceded") cues.push({ at: hit + 0.35, run: () => penaltyAgainst(world, "us") });
    else cues.push({ at: hit + 1.2, run: () => world.sound("groan") });
    return {
      duration,
      cues,
      frame(t) {
        setupFrame(1.4);
        others(t, duration);
        ref.place(refSpot[0], refSpot[1], Math.PI / 2).set(ready(0.1));
        runner(attacker, attackerTo, t, 0, hit, { from: 1, to: 1, speed: 1, carry: "one" });
        world.ballAt(carried(attacker, "one", ball), new THREE.Vector3(0, 0, -1));
        const lunge = route([end.hero, [contact[0], contact[1] - 0.6]]);
        let look = contact;

        if (key === "smash" && success) {
          // Renversé : il part en arrière, le ballon sort, notre 6 ou 7 ramasse.
          runner(hero, lunge, t, 0, hit, { from: 0.3, to: 1, speed: 0.9 });
          if (t >= hit) {
            const k = span(t, hit, hit + 0.45);
            hero.place(contact[0], contact[1] - 0.2 + 0.9 * smooth(k), FACE_FIELD).set(tackle(k));
            attacker.place(contact[0] + s * 0.2, contact[1] + 0.7 + 1.1 * smooth(k), FACE_LINE).set(k < 0.4 ? ready(0.4) : ground(true));
            const loose = new THREE.Vector3(contact[0] - s * 1.4, 0.12, contact[1] + 0.4);
            if (t < hit + 0.55) world.ballAt(lob(carried(attacker, "one", new THREE.Vector3()), loose, 1.0, span(t, hit, hit + 0.55), ball), new THREE.Vector3(1, 0.4, 0));
            else world.ballAt(t < 1.35 ? loose : carried(partner, "one", ball), new THREE.Vector3(1, 0, 0));
            runner(partner, route([end.partner, [loose.x - s * 0.3, loose.z + 0.4]]), t, 0, 1.1, { from: 0.4, to: 0.3, speed: 0.6 });
            if (t >= 1.1 && t < 1.35) partner.set(crouch(1));
            if (t >= 1.35) runner(partner, route([[loose.x - s * 0.3, loose.z + 0.4], [loose.x - s * 2, loose.z + 9]]), t, 1.35, duration, { from: 0.3, to: 0.9, speed: 0.8, carry: "one" });
          }
        } else if (key === "hold" && success) {
          // À deux : il est tenu debout, puis mis au sol.
          runner(hero, lunge, t, 0, hit, { from: 0.3, to: 0.7, speed: 0.7 });
          runner(partner, route([end.partner, [contact[0] - s * 0.7, contact[1] + 0.2]]), t, 0, hit, { from: 0.4, to: 0.9, speed: 0.8 });
          if (t >= hit) {
            const k = span(t, hit + 0.4, hit + 0.9);
            hero.place(contact[0], contact[1] - 0.4, FACE_FIELD).set(k > 0 ? tackle(0.5 + k * 0.5) : WRESTLE);
            partner.place(contact[0] - s * 0.7, contact[1] + 0.2, FACE_FIELD + s * 0.9).set(k > 0 ? tackle(0.3 + k * 0.4) : WRESTLE);
            attacker.place(contact[0] + s * 0.1, contact[1] + 0.4 + 0.5 * k, FACE_LINE).set(k < 1 ? ready(0.5) : ground(true));
          }
        } else if (key === "ball" && success) {
          // Il arrache le ballon dans le contact et repart dans l'autre sens.
          runner(hero, lunge, t, 0, hit, { from: 0.3, to: 0.7, speed: 0.7 });
          if (t >= hit) {
            const wrestle = Math.sin((t - hit) * 18) * 0.12 * (t < 1.1 ? 1 : 0);
            if (t < 1.1) {
              hero.place(contact[0], contact[1] - 0.3, FACE_FIELD + wrestle).set(WRESTLE);
              attacker.place(contact[0], contact[1] + 0.45, FACE_LINE - wrestle).set(WRESTLE);
              world.ballAt(ball.set(contact[0], 1.1, contact[1] + 0.1), new THREE.Vector3(1, 0, 0));
            } else {
              runner(hero, route([[contact[0], contact[1] - 0.3], [contact[0] - s * 2, contact[1] + 8]]), t, 1.1, duration, { from: 0.3, to: 0.9, speed: 0.8, carry: "one" });
              attacker.place(contact[0], contact[1] + 0.45, FACE_LINE).set(dejected());
              world.ballAt(carried(hero, "one", ball), new THREE.Vector3(0, 0, 1));
            }
          }
        } else if (key === "ball") {
          // Plaquage haut : l'arbitre siffle, pénalité, peut-être le carton.
          runner(hero, lunge, t, 0, hit, { from: 0.3, to: 0.7, speed: 0.7 });
          if (t >= hit) {
            const k = span(t, hit, hit + 0.4);
            hero.place(contact[0], contact[1] - 0.4, FACE_FIELD).set(k < 1 ? HIGH : dejected());
            attacker.place(contact[0], contact[1] + 0.5 + 0.6 * smooth(k), FACE_LINE).set(k < 0.5 ? ready(0.3) : ground(true));
            world.ballAt(carried(attacker, "low", ball), new THREE.Vector3(1, 0, 0));
          }
          // L'arbitre accourt, bras levé vers leur attaque (-z), puis le carton.
          const rk = span(t, hit + 0.2, hit + 0.9);
          const near = [contact[0] - s * 3, contact[1] + 1];
          ref.place(lerp(refSpot[0], near[0], smooth(rk)), lerp(refSpot[1], near[1], smooth(rk)), Math.PI / 2);
          if (rk < 1) ref.set(run(t * 3, 0.5));
          else if (effect === "yellow" && t > hit + 1.6) {
            ref.set(card(smooth(span(t, hit + 1.6, hit + 1.9))));
            ref.card.visible = true;
          } else ref.set(signal(1, smooth(span(t, hit + 0.9, hit + 1.2))));
          look = near;
        } else {
          // Raté : il plonge, l'attaquant s'échappe (le partenaire glisse aussi à deux).
          runner(hero, lunge, t, 0, hit, { from: 0.3, to: 0.9, speed: 0.8 });
          if (t >= hit) {
            const k = span(t, hit - 0.1, hit + 0.45);
            hero.place(contact[0] - s * 0.6, contact[1] - 0.4 - 0.6 * smooth(k), FACE_FIELD - s * 0.4).set(k < 1 ? tackle(k) : ground());
          }
          if (key === "hold") runner(partner, route([end.partner, [contact[0] - s * 1.2, contact[1] - 0.8]]), t, 0, hit + 0.2, { from: 0.4, to: 0.8, speed: 0.7 });
          if (t >= hit) {
            const gone = breakaway(t, hit, effect === "try_conceded");
            if (effect === "try_conceded" && t > scored) {
              ref.place(gone.spot[0] - s * 5, 3, Math.PI / 2).set(tryAward(smooth(span(t, scored, scored + 0.35))));
            }
            look = [lerp(contact[0], attacker.root.position.x, 0.7), Math.max(1, attacker.root.position.z)];
          }
        }
        if (ref.card && !(key === "ball" && !success && effect === "yellow")) ref.card.visible = false;
        return broadcast(look[0], look[1] + 0.5, { far: 0.9 });
      },
    };
  }

  return {
    setup,
    preview,
    outcome(key, result) {
      return outcomeFor(key, result);
    },
  };
}
