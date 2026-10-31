import * as THREE from "three";

import { crouch, dejected, ground, pass, ready, run, tackle } from "../rig.js";
import { FACE_FIELD, broadcast, carried, grubber, keys, lerp, lob, reaction, route, runner, smooth, span } from "./common.js";

// Carrière de joueur, « Un contre un » (one_on_one) : le joueur incarné reçoit le ballon
// lancé, un défenseur monte sur lui. Le crochet (un appui à l'extérieur, puis dedans),
// le raffût (le bras tendu, il passe à travers), ou la passe au soutien. Un crochet ou
// un raffût réussi est un franchissement : le deux contre un s'enchaîne (twoOnOne.js).

// Le raffût : la course, le bras tendu devant.
const fend = (phase, k) => ({ ...run(phase, 0.8, "one"), armL: lerp(0, 1.45, k), elL: lerp(1.3, 0.1, k), abL: -0.15 });

export function buildOneOnOne(world, data) {
  const rng = world.rng;
  const s = rng() < 0.5 ? -1 : 1; // le côté du soutien
  const hx = s * (5 + rng() * 5);
  const hz = 29.5;
  const heroNo = data.hero ?? 12;
  const passerNo = heroNo === 10 ? 12 : 10;
  const supportNo = [13, 14, 11, 15, 7].find((n) => n !== heroNo && n !== passerNo);
  const hero = world.player("us", heroNo, { hero: true });
  const passer = world.player("us", passerNo);
  const support = world.player("us", supportNo);
  const marker = world.player("them", 13);
  const inside = world.player("them", 12);
  const cover = world.player("them", 15);
  const ref = world.player("ref");

  const start = {
    hero: [hx + s * 0.6, 35.5],
    passer: [hx - s * 5, 34],
    support: [hx + s * 4, 37],
    marker: [hx - s * 0.4, 20.5],
    inside: [hx - s * 7, 22],
    cover: [hx + s * 3, 9],
  };
  const end = {
    hero: [hx, hz],
    passer: [hx - s * 5.5, 31.8],
    support: [hx + s * 4.2, hz + 1.8],
    marker: [hx - s * 0.2, hz - 3.8],
    inside: [hx - s * 6.5, hz - 5.5],
    cover: [hx + s * 3.5, 12],
  };
  const paths = Object.fromEntries(Object.keys(start).map((key) => [key, route([start[key], end[key]])]));
  const passAt = [0.3, 0.7];
  const ball = new THREE.Vector3();
  const from = new THREE.Vector3();
  const to = new THREE.Vector3();
  const shot = broadcast(hx, hz - 1.5);
  const camera = keys([
    [0, [hx - 58, 26, 58, hx * 0.6, 0.5, 30, 44]],
    [1.4, [...shot.pos, ...shot.look, shot.fov]],
  ]);

  function setupFrame(t) {
    runner(passer, paths.passer, t, 0, passAt[0], { from: 0.6, to: 0.5, speed: 0.5, carry: "two" });
    if (t >= passAt[0]) passer.set(pass(span(t, passAt[0] - 0.1, passAt[0] + 0.2), s > 0 ? 1 : -1));
    runner(hero, paths.hero, t, 0, 1.4, { from: 0.7, to: 0.8, speed: 0.7, carry: t > passAt[1] ? "two" : "none" });
    runner(support, paths.support, t, 0, 1.4, { from: 0.7, to: 0.8, speed: 0.7 });
    runner(marker, paths.marker, t, 0, 1.4, { from: 0.6, to: 0.9, speed: 0.8 });
    runner(inside, paths.inside, t, 0, 1.4, { from: 0.6, to: 0.8, speed: 0.7 });
    runner(cover, paths.cover, t, 0, 1.4, { from: 0.4, to: 0.5, speed: 0.5 });
    ref.place(hx - s * 9, 34, Math.PI * 0.75).set(ready(0.1));
    if (t < passAt[0]) world.ballAt(carried(passer, "two", ball), new THREE.Vector3(1, 0, 0));
    else if (t < passAt[1]) {
      carried(passer, "two", from);
      carried(hero, "two", to);
      world.ballAt(lob(from, to, 0.4, span(t, ...passAt), ball), new THREE.Vector3(to.x - from.x, 0, to.z - from.z));
    } else world.ballAt(carried(hero, "two", ball), new THREE.Vector3(1, 0, 0));
    const [cx, cy, cz, lx, ly, lz, fov] = camera(t);
    return { pos: [cx, cy, cz], look: [lx, ly, lz], fov };
  }

  const setup = {
    duration: 1.4,
    frame: setupFrame,
    cues: [{ at: 0.1, run: () => world.crowd(world.pressure > 1 ? "standing" : "seated") }],
  };

  // Les trajets de chaque voie, partagés par l'aperçu et l'issue.
  const jink = [[hx, hz], [hx - s * 1.3, hz - 2.3], [hx + s * 0.9, hz - 5.5], [hx + s * 1.1, hz - 12]];
  const through = [[hx, hz], [hx + s * 0.2, hz - 3], [hx + s * 0.4, hz - 12]];
  const supportRun = [end.support, [hx + s * 4.6, hz - 11]];

  function preview(key) {
    const draw = world.draw;
    if (key === "step") return [draw.path(jink), draw.mark(jink[3])];
    if (key === "fend") return [draw.path(through), draw.mark(end.marker, 0.7), draw.mark(through[2])];
    const a = carried(hero, "two", new THREE.Vector3());
    const b = carried(support, "two", new THREE.Vector3());
    const arc = [];
    for (let i = 0; i <= 10; i++) arc.push(lob(a, b, 0.35, i / 10).toArray());
    return [draw.arc(arc, 0.08), draw.path(supportRun), draw.mark(supportRun[1])];
  }

  // Les autres continuent l'action : le soutien suit, les défenseurs reviennent.
  const others = (t, duration) => {
    runner(passer, route([end.passer, [end.passer[0] + s * 1.5, end.passer[1] - 6]]), t, 0, duration, { from: 0.5, to: 0.4, speed: 0.5 });
    runner(inside, route([end.inside, [hx - s * 2, hz - 10]]), t, 0, duration, { from: 0.8, to: 0.8, speed: 0.8 });
    runner(cover, route([end.cover, [hx + s * 2, 14]]), t, 0, duration, { from: 0.5, to: 0.8, speed: 0.8 });
    ref.place(hx - s * 9, 34, Math.PI * 0.75).set(ready(0.1));
  };
  const follow = (player) => broadcast(player.root.position.x, player.root.position.z - 1.5);

  // Franchissement (crochet, raffût réussis) : le joueur file, le défenseur reste.
  function breaks(key) {
    const path = route(key === "step" ? jink : through);
    const duration = 2.1;
    const contact = key === "step" ? 0.55 : 0.45;
    return {
      duration,
      cues: [
        { at: contact, run: () => world.sound(key === "fend" ? "impact" : "kick") },
        { at: contact + 0.4, run: () => reaction(world, true) },
      ],
      frame(t) {
        setupFrame(1.4);
        others(t, duration);
        runner(hero, path, t, 0, duration, { from: 0.8, to: 1, speed: 1, carry: "one" });
        if (key === "fend" && t > contact - 0.2 && t < contact + 0.35) hero.set(fend(t * 3, smooth(span(t, contact - 0.2, contact))));
        runner(support, route(supportRun), t, 0, duration, { from: 0.8, to: 1, speed: 0.95 });
        if (key === "step") {
          // Il plonge du mauvais côté.
          const k = span(t, contact - 0.15, contact + 0.45);
          marker.place(lerp(end.marker[0], hx - s * 1.6, smooth(k)), lerp(end.marker[1], hz - 3.4, smooth(k)), FACE_FIELD - s * 0.5);
          marker.set(k < 1 ? tackle(k) : ground());
        } else {
          // Repoussé, il tombe en arrière.
          const k = span(t, contact, contact + 0.45);
          marker.place(end.marker[0] - s * 0.3 * k, end.marker[1] - 1.2 * smooth(k), FACE_FIELD);
          marker.set(k < 1 ? ready(0.6) : ground(true));
          if (k > 0.3) marker.set(ground(true));
        }
        world.ballAt(carried(hero, "one", ball), new THREE.Vector3(0, 0, 1));
        return follow(hero);
      },
    };
  }

  // Plaqué (crochet raté) ou arraché (raffût raté) : le ballon change de camp.
  function caught(key) {
    const contact = 0.5;
    const meet = key === "step" ? [hx - s * 1.0, hz - 2.2] : [hx + s * 0.15, hz - 2.8];
    const duration = 2.6;
    const loose = new THREE.Vector3(meet[0] - s * 0.4, 0.12, meet[1] - 1.8);
    return {
      duration,
      cues: [
        { at: contact, run: () => world.sound("impact") },
        { at: contact + 0.6, run: () => reaction(world, false) },
      ],
      frame(t) {
        setupFrame(1.4);
        others(t, duration);
        runner(support, route([end.support, [hx + s * 3.8, hz - 3]]), t, 0, 1.2, { from: 0.8, to: 0.1, speed: 0.6 });
        if (t > 1.2) support.set(dejected());
        runner(hero, route([[hx, hz], meet]), t, 0, contact, { from: 0.8, to: 0.8, speed: 0.8, carry: "one" });
        runner(marker, route([end.marker, [meet[0], meet[1] - 0.7]]), t, 0, contact, { from: 0.9, to: 0.6, speed: 0.7 });
        if (t >= contact) {
          const k = span(t, contact, contact + 0.5);
          if (key === "step") {
            hero.place(meet[0], meet[1] - 0.6 * k, Math.PI).set(k < 1 ? tackle(k * 0.7) : ground());
            marker.place(meet[0] + s * 0.3, meet[1] - 0.8, FACE_FIELD).set(tackle(k));
          } else {
            // Il encaisse, le tient debout et lui arrache le ballon, puis repart.
            hero.place(meet[0], meet[1], Math.PI).set(k < 1 ? ready(0.5) : dejected());
            if (t < 1.3) marker.place(meet[0], meet[1] - 0.7, FACE_FIELD).set(tackle(0.25));
            else runner(marker, route([[meet[0], meet[1] - 0.7], [meet[0] - s * 1, meet[1] + 8]]), t, 1.3, duration, { from: 0.3, to: 0.8, speed: 0.7, carry: "one" });
          }
        }
        // Le ballon : chez lui, puis au sol (plaqué) ou chez le défenseur (arraché).
        if (t < contact) world.ballAt(carried(hero, "one", ball), new THREE.Vector3(0, 0, 1));
        else if (key === "step") {
          if (t < contact + 0.6) {
            carried(hero, "one", from);
            world.ballAt(grubber(from, loose, span(t, contact, contact + 0.6), 2, ball), new THREE.Vector3(Math.sin(t * 9), 0.3, 1));
          } else world.ballAt(t < 1.4 ? loose : carried(inside, "one", ball), new THREE.Vector3(1, 0, 0));
          // Leur 12 ramasse et repart.
          if (t > 0.9) {
            if (t < 1.4) inside.place(loose.x, loose.z + 0.5, Math.PI).set(crouch(span(t, 0.9, 1.2)));
            else runner(inside, route([[loose.x, loose.z + 0.5], [loose.x + s * 2, loose.z + 9]]), t, 1.4, duration, { from: 0.3, to: 0.8, speed: 0.7, carry: "one" });
          }
        } else world.ballAt(carried(t < 1.15 ? hero : marker, t < 1.15 ? "one" : "two", ball), new THREE.Vector3(1, 0, 0));
        return broadcast(meet[0], meet[1]);
      },
    };
  }

  // La passe au soutien : propre (le jeu continue), ou dans les pieds (ballon perdu).
  function passOutcome(good) {
    const release = 0.25;
    const arrive = 0.6;
    const duration = good ? 2.4 : 2.4;
    const feet = new THREE.Vector3(end.support[0] - s * 0.3, 0.12, end.support[1] - 2.2);
    const loose = new THREE.Vector3(feet.x + s * 0.6, 0.12, feet.z - 1.8);
    return {
      duration,
      cues: [{ at: good ? 1.6 : arrive, run: () => (good ? world.sound("impact") : reaction(world, false)) }],
      frame(t) {
        setupFrame(1.4);
        others(t, duration);
        hero.place(hx, hz - 0.5 * span(t, 0, 0.6), Math.PI).set(t < release + 0.25 ? pass(span(t, release - 0.1, release + 0.2), s > 0 ? -1 : 1) : ready(0.2));
        if (t > release + 0.25) runner(hero, route([[hx, hz - 0.5], [hx + s * 2, hz - 5]]), t, release + 0.25, duration, { from: 0.3, to: 0.6, speed: 0.6 });
        carried(hero, "two", from);
        if (good) {
          runner(support, route(supportRun), t, 0, duration, { from: 0.8, to: 0.9, speed: 0.9, carry: t > arrive ? "one" : "none" });
          // Leur 13 glisse sur le soutien et le plaque.
          const [mx, mz] = end.marker;
          runner(marker, route([[mx, mz], [hx + s * 4.3, hz - 6.5]]), t, 0, 1.6, { from: 0.8, to: 0.8, speed: 0.8 });
          if (t > 1.6) marker.set(tackle(span(t, 1.6, 2.0) * 0.6));
          if (t < release) world.ballAt(from, new THREE.Vector3(1, 0, 0));
          else if (t < arrive) world.ballAt(lob(from, carried(support, "two", to), 0.35, span(t, release, arrive), ball), new THREE.Vector3(1, 0, 0));
          else world.ballAt(carried(support, "one", ball), new THREE.Vector3(0, 0, 1));
          return follow(support);
        }
        runner(support, route([end.support, [feet.x, feet.z + 0.6]]), t, 0, 0.8, { from: 0.8, to: 0.2, speed: 0.6 });
        if (t > 0.8) support.set(crouch(0.6));
        if (t < release) world.ballAt(from, new THREE.Vector3(1, 0, 0));
        else if (t < arrive) world.ballAt(lob(from, feet, 0.25, span(t, release, arrive), ball), new THREE.Vector3(1, 0, 0));
        else world.ballAt(grubber(feet, loose, span(t, arrive, 1.3), 2, ball), new THREE.Vector3(Math.sin(t * 11), 0.2, 1));
        const [mx, mz] = end.marker;
        if (t < 1.3) runner(marker, route([[mx, mz], [loose.x, loose.z - 0.6]]), t, 0, 1.3, { from: 0.9, to: 0.8, speed: 0.8 });
        else marker.place(loose.x, loose.z - 0.4, FACE_FIELD).set(crouch(1));
        return broadcast(feet.x, feet.z);
      },
    };
  }

  return {
    setup,
    preview,
    outcome(key, result) {
      if (key === "pass") return passOutcome(result.success);
      return result.success ? breaks(key) : caught(key);
    },
  };
}
