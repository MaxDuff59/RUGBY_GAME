import * as THREE from "three";

import { FAR_LINE } from "../field.js";
import { cheer, crouch, dejected, dive, ground, kick, mixPose, pass, ready, run, signal, tackle, tryAward } from "../rig.js";
import { FACE_FIELD, FACE_LINE, broadcast, carried, clamp, grubber, headingTo, lerp, lob, reaction, route, runner, smooth, snapshot, span, trail } from "./common.js";

// Carrière de joueur, « Contre-attaque éclair » (counter_attack), toujours enchaînée sur
// un ballon récupéré : le joueur incarné repart balle en main, leur défense est à
// l'envers, leur arrière seul devant, un ailier à sa hauteur. Filer seul (personne ne le
// rattrape, ou il est repris dans les derniers mètres), écarter vite (l'ailier aplatit,
// ou la passe part en avant), ou taper à suivre (il aplatit, ou le rebond les favorise).
//
// La règle : à portée, la contre-attaque file vers la ligne vers laquelle il court à la
// reprise (d'après son cap) : z = 0, ou FAR_LINE. Tout se calcule en distance à cette ligne
// (`u`). Trop loin (ou trop près pour jouer l'action), un fondu au noir, et l'action reprend
// à 24 m, toujours vers les perches : la ligne d'en face n'a ni poteaux ni tribune.

const NEAR = 18; // en deçà, ou au-delà de FAR, on reprend à START de la ligne
const FAR = 26;
const START = 24;
const FADE = 0.35; // le noir se fait
const BACK = 0.8; // la caméra a fini son raccord dans le noir : l'action reprend
const RUN = 1.1; // la course jusqu'à l'arrêt sur image
const CHARGE = 8.2; // vitesse de course (m/s)
const DIVE_FROM = 1.9; // le plongeon part à cette distance de la ligne
const DIVE_TO = 0.5; // les pieds finissent là : les mains passent la ligne

const v = (x, y, z) => new THREE.Vector3(x, y, z);

// Le ballon entre ses mains, là où elles sont (le plongeon se lit de près).
function hands(player, out) {
  player.root.updateWorldMatrix(true, true);
  const left = player.elbowL.localToWorld(v(0, -0.3, 0));
  const right = player.elbowR.localToWorld(v(0, -0.3, 0));
  return out.addVectors(left, right).multiplyScalar(0.5);
}

export function buildCounterAttack(world, data, handover) {
  const previous = handover?.cast ?? [];
  let hero = previous.find((player) => player.role === "hero");
  if (hero) {
    world.keep(hero);
  } else {
    hero = world.player("us", data.hero ?? 14, { hero: true });
    hero.place(world.rng() < 0.5 ? -9 : 9, START, FACE_LINE);
  }
  const heading0 = hero.heading;
  const h0 = [hero.root.position.x, hero.root.position.z];

  // Le sens de l'attaque, et la distance à la ligne visée.
  const facing = Math.cos(heading0) > 0 ? 1 : -1;
  const ahead = facing > 0 ? FAR_LINE - h0[1] : h0[1];
  const cut = ahead > FAR || ahead < NEAR;
  const d = cut ? -1 : facing;
  const line = d > 0 ? FAR_LINE : 0;
  const toward = d > 0 ? FACE_FIELD : FACE_LINE;
  const Z = (u) => line - d * u;
  const at = (x, u) => [x, Z(u)];
  const uOf = (player) => d * (line - player.root.position.z);
  const u1 = cut ? START : ahead;
  const shift = cut ? Z(START) - h0[1] : 0;
  const T0 = cut ? BACK : 0;
  const duration = T0 + RUN;

  // Les places à l'arrêt sur image ; l'ailier du côté où il y a de la place.
  const hx = clamp(h0[0], -24, 24);
  const x1 = cut ? hx : h0[0];
  const uf = u1 - RUN * CHARGE * 0.9;
  const side = hx > 0 ? -1 : 1;
  const wingX = hx + side * 8.5;
  const heroLine = route([at(x1, u1), at(hx, uf)]);

  // Sa gauche, vue du terrain : en +x s'il regarde vers +z, en -x s'il regarde vers z = 0.
  const passSide = side * d;

  // Ceux qui restent de la scène d'avant : l'arbitre, leurs plus proches lancés à sa
  // poursuite. Après un fondu, tout le monde est reparti de plus loin : on les remplace.
  let ref = previous.find((player) => player.team === "ref");
  const r0 = ref ? [ref.root.position.x, ref.root.position.z + shift] : [hx + 11, Z(u1 + 2)];
  ref = ref ? world.keep(ref) : world.player("ref");
  const reusable = cut
    ? []
    : previous
        .filter((player) => player.team === "them" && Math.abs(player.current.pitch) < 0.8 && player.root.position.distanceTo(hero.root.position) < 13)
        .sort((a, b) => a.root.position.distanceTo(hero.root.position) - b.root.position.distanceTo(hero.root.position));
  const fresh = [];
  const newcomer = (team, number) => {
    const player = world.player(team, number);
    fresh.push(player);
    return player;
  };
  const chaserA = reusable[0] ? world.keep(reusable[0]) : newcomer("them", 7);
  const chaserB = reusable[1] ? world.keep(reusable[1]) : newcomer("them", 12);
  const from = (player, fallback) => (fresh.includes(player) ? fallback : [player.root.position.x, player.root.position.z]);
  const a0 = from(chaserA, at(hx - side * 2, u1 + 5));
  const b0 = from(chaserB, at(hx + side * 3.5, u1 + 8));
  const aEnd = at(hx - side * 1.6, uf + 3.2);
  const bEnd = at(hx + side * 3, uf + 5.5);

  const leftovers = new Map();
  for (const player of previous) {
    if (player === hero || player === ref || player === chaserA || player === chaserB) continue;
    // Tous finissent leur course dans le sens de l'action (avant un fondu : dans le leur).
    const snap = snapshot(player, player.team === "them" ? 6.5 : 5);
    leftovers.set(world.keep(player), cut ? snap : { ...snap, heading: toward });
  }

  const wing = newcomer("us", data.hero === 14 ? 11 : 14);
  const wingFrom = at(hx + side * 11, u1 + 7);
  const wingEnd = at(wingX, uf + 2.4);
  const fullback = newcomer("them", 15);
  const fullbackFrom = at(hx + side * 3.4, uf - 9.5);
  const fullbackEnd = at(hx + side * 2.8, Math.max(uf - 6.2, 3));
  const cover = newcomer("them", hx > 0 ? 14 : 11);
  const coverFrom = at(wingX + side * 5, uf + 7);
  const coverEnd = at(wingX + side * 3.5, uf + 4.8);
  // L'arbitre suit côté tribune (+x), derrière l'action vue de la caméra.
  const refX = Math.max(hx, wingX + (side > 0 ? 3.5 : 0)) + 5;
  const refEnd = at(refX, uf + 2);
  const faceHero = d > 0 ? FACE_LINE : FACE_FIELD; // l'arrière fait face au porteur

  const ball = new THREE.Vector3();
  const passFrom = new THREE.Vector3();
  const passTo = new THREE.Vector3();
  const forwardAxis = v(0, 0, d);

  // La caméra : de biais, depuis la tribune d'en face, en regardant vers la ligne visée.
  // Vers z = 0, c'est le plan de retransmission ; vers FAR_LINE, son miroir.
  const view = (x, u, options) => {
    const shot = broadcast(x, Z(u), options);
    if (d > 0) shot.pos[2] = Z(u) - (shot.pos[2] - Z(u));
    return shot;
  };
  const before = broadcast(h0[0] + Math.sin(heading0) * 3, h0[1] + Math.cos(heading0) * 3);
  const shot = view(lerp(hx, wingX, 0.3), uf - 3.6, { far: 1.08, fov: 33, y: 0.2 });
  const start = view(x1, u1 - 2);

  function setupFrame(time) {
    leftovers.forEach((snap, player) => {
      player.visible = !cut || time < FADE;
      trail(player, time, snap, 2.4);
    });
    fresh.forEach((player) => {
      player.visible = !cut || time >= FADE;
    });
    if (cut && time < FADE) {
      // Il finit sa foulée dans le sens où il courait, et le noir se fait.
      runner(hero, route([h0, [h0[0] + Math.sin(heading0) * 3, h0[1] + Math.cos(heading0) * 3]]), time, 0, FADE, { speed: 0.9, carry: "one" });
      world.ballAt(carried(hero, "one", ball), forwardAxis);
      ref.visible = false;
      world.exposure(1 - smooth(time / FADE));
      return before;
    }
    ref.visible = true;
    world.exposure(cut ? smooth(span(time, BACK, BACK + 0.25)) : 1);
    const t = time - T0;
    const stride = run(0, 0.9, "one");
    runner(hero, heroLine, t, 0, RUN, { from: cut ? 0.95 : 0.6, to: 1, speed: 0.95, carry: "one", still: stride });
    runner(wing, route([wingFrom, wingEnd]), t, 0, RUN, { from: 1, to: 0.9, speed: 0.95, still: run(0, 0.9) });
    runner(chaserA, route([a0, aEnd]), t, 0, RUN, { from: 0.7, to: 1, speed: 1, still: run(0, 0.9) });
    runner(chaserB, route([b0, bEnd]), t, 0, RUN, { from: 0.7, to: 1, speed: 0.95, still: run(0, 0.9) });
    runner(cover, route([coverFrom, coverEnd]), t, 0, RUN, { from: 0.7, to: 1, speed: 0.95, still: run(0, 0.9) });
    // Leur arrière, seul devant, recule en se plaçant entre lui et l'ailier.
    runner(fullback, route([fullbackFrom, fullbackEnd]), t, 0, RUN, { from: 0.6, to: 0.4, speed: 0.5, still: ready(0.6) });
    fullback.root.rotation.y = fullback.heading = faceHero;
    if (t >= RUN) fullback.set(ready(0.65));
    runner(ref, route([r0, refEnd]), t, 0, RUN, { from: 0.8, to: 0.7, speed: 0.7, still: run(0, 0.6) });
    world.ballAt(carried(hero, "one", ball), forwardAxis);
    const k = smooth(span(t, 0, RUN));
    return {
      pos: start.pos.map((value, i) => lerp(value, shot.pos[i], k)),
      look: start.look.map((value, i) => lerp(value, shot.look[i], k)),
      fov: lerp(start.fov, shot.fov, k),
    };
  }

  const setup = {
    duration,
    frame: setupFrame,
    cues: [{ at: 0.05, run: () => world.crowd("standing") }],
  };

  // --- Les voies -----------------------------------------------------------------------

  const heroX = hx;
  const dodge = hx - side * 2.6;
  const soloPath = [at(heroX, uf), at(dodge, Math.max(uf - 6.5, 4.5)), at(dodge - side * 0.2, DIVE_FROM)];
  const wingPath = [wingEnd, at(wingX + side * 0.6, DIVE_FROM)];
  const chipLand = [heroX - side * 0.8, Math.max(uf - 10.5, 3.5)];
  const chipTop = Math.max(uf - 5, 4);
  const kickPath = [at(heroX, uf), at(heroX - side * 1.4, chipTop), at(heroX - side * 0.6, DIVE_FROM)];

  function preview(key) {
    const draw = world.draw;
    const from3 = carried(hero, "two", v());
    if (key === "solo") return [draw.path(soloPath), draw.mark(soloPath[2])];
    if (key === "spread") {
      const to3 = carried(wing, "two", v());
      const arc = [];
      for (let i = 0; i <= 10; i++) arc.push(lob(from3, to3, 0.4, i / 10).toArray());
      return [draw.arc(arc, 0.08), draw.path(wingPath), draw.mark(wingPath[1])];
    }
    const landing = v(chipLand[0], 0.2, Z(chipLand[1]));
    const arc = [];
    for (let i = 0; i <= 14; i++) arc.push(lob(from3, landing, 5, i / 14).toArray());
    return [draw.arc(arc), draw.path(kickPath), draw.mark(kickPath[2])];
  }

  // Le coureur qui va à l'essai : il court, plonge (les mains passent la ligne), se relève
  // les bras en l'air. Rend sa place, et pose le ballon s'il l'a (`hasBall`).
  function tryRun(player, path, t, t0, tEnd, { carry = "one", hasBall = true, speed = 1, from: fromSpeed = 0.9 } = {}) {
    const last = path[path.length - 1];
    if (t < tEnd) {
      runner(player, route(path), t, t0, tEnd, { from: fromSpeed, to: 1, speed, carry, still: run(0, 0.9, carry) });
      if (hasBall) world.ballAt(carried(player, carry, ball), forwardAxis);
      return;
    }
    const k = span(t, tEnd, tEnd + 0.45);
    const rise = smooth(span(t, tEnd + 1.15, tEnd + 1.55));
    const u = lerp(DIVE_FROM, DIVE_TO, smooth(k));
    player.place(last[0], Z(u), toward).set(dive(k));
    if (hasBall) {
      const grounded = v(last[0], 0.13, Z(-1));
      hands(player, ball);
      ball.y = Math.max(0.13, ball.y);
      ball.lerp(grounded, smooth(span(k, 0.7, 1)));
      world.ballAt(ball, v(1, 0, 0));
    }
    if (rise > 0) player.place(last[0], Z(lerp(DIVE_TO, -0.8, rise)), toward).set(mixPose(dive(1), cheer(t * 1.5), rise));
  }

  // L'arbitre arrive sur l'essai et accorde.
  function refereeTo(target, t, t0, tEnd, scoreAt) {
    const reach = route([refEnd, target]);
    runner(ref, reach, t, t0, tEnd, { from: 0.7, to: 0.4, speed: 0.7, still: ready(0.1) });
    if (t >= tEnd) ref.place(target[0], target[1], headingTo(target[0], target[1], hx, Z(0))).set(ready(0.1));
    if (t > scoreAt) ref.set(tryAward(smooth(span(t, scoreAt, scoreAt + 0.35))));
  }

  // Les poursuivants, qui ne reviendront pas : ils s'arrêtent au bord de l'essai.
  function chase(t, tEnd, target = hx - side * 2) {
    runner(chaserA, route([aEnd, at(target, 2.8)]), t, 0, tEnd + 0.1, { from: 1, to: 0.3, speed: 0.95 });
    runner(chaserB, route([bEnd, at(target + side * 4.5, 6)]), t, 0, tEnd + 0.1, { from: 1, to: 0.3, speed: 0.9 });
    runner(cover, route([coverEnd, at(wingX + side * 3, 4.5)]), t, 0, tEnd + 0.1, { from: 1, to: 0.3, speed: 0.9 });
    if (t > tEnd + 0.1) {
      chaserA.set(dejected());
      chaserB.set(dejected());
      cover.set(dejected());
    }
  }

  // Une caméra qui suit l'action sans passer la ligne de plus d'un rien.
  const follow = (x, u) => view(lerp(hx, x, 0.75), Math.max(u - 1.6, 0.8), { far: 1.05, fov: 33 });

  function soloOutcome(good) {
    const length = route(soloPath).total;
    const tEnd = length / CHARGE;
    const hitU = 4;
    const hit = (((uf - hitU) / (uf - DIVE_FROM)) * length) / CHARGE;
    const scoreAt = tEnd + 0.4;
    const missAt = Math.min(0.55, tEnd * 0.35);
    const miss = at(lerp(hx, dodge, 0.7) + side * 0.6, Math.max(uf - 6.2, 4.2));
    const hitAt = route(soloPath).at((hit / tEnd) * length);
    const loose = v(hitAt.x - side * 0.7, 0.12, hitAt.z - d * 1.9);
    const pickAt = hit + 1.1;
    const end = good ? scoreAt + 2 : pickAt + 1.2;
    return {
      duration: end,
      cues: good
        ? [
            {
              at: scoreAt,
              run: () => {
                world.sound("whistle", true);
                reaction(world, true);
              },
            },
          ]
        : [
            { at: hit, run: () => world.sound("impact") },
            { at: hit + 0.45, run: () => reaction(world, false) },
          ],
      frame(t) {
        setupFrame(duration);
        leftovers.forEach((snap, player) => trail(player, RUN + t, snap, 2.4));
        runner(wing, route([wingEnd, at(wingX, Math.max(uf - 9, 3))]), t, 0, 1.6, { from: 0.9, to: 0.2, speed: 0.75 });
        if (t >= 1.6) wing.set(good && t > scoreAt + 0.3 ? cheer(t * 1.4) : good ? ready(0.2) : dejected());
        // L'arrière se jette, trop tard.
        if (t < missAt) runner(fullback, route([fullbackEnd, miss]), t, 0, missAt, { from: 0.5, to: 1, speed: 0.85 });
        else {
          const k = span(t, missAt, missAt + 0.5);
          fullback.place(miss[0], miss[1], headingTo(miss[0], miss[1], ...soloPath[1])).set(k < 1 ? tackle(k) : ground());
          if (!good && t > hit - 0.3) {
            // Relevé, il vient ramasser le ballon.
            const pick = [loose.x + side * 0.4, loose.z - d * 0.7];
            runner(fullback, route([miss, pick]), t, hit - 0.3, pickAt - 0.2, { from: 0.4, to: 0.6, speed: 0.7 });
            if (t >= pickAt - 0.2) fullback.place(pick[0], pick[1], faceHero).set(t < pickAt + 0.05 ? crouch(1) : ready(0.25));
          }
        }
        if (good) {
          tryRun(hero, soloPath, t, 0, tEnd);
          chase(t, tEnd);
          refereeTo(at(refX, 2.5), t, 0, tEnd, scoreAt);
          const u = uOf(hero);
          return follow(hero.root.position.x, u);
        }
        // Repris par derrière dans les derniers mètres ; le ballon s'échappe.
        if (t < hit) {
          runner(hero, route(soloPath), t, 0, tEnd, { from: 0.9, to: 1, speed: 1, carry: "one" });
          world.ballAt(carried(hero, "one", ball), forwardAxis);
        } else {
          const k = span(t, hit, hit + 0.45);
          hero.place(hitAt.x, hitAt.z + d * 0.7 * smooth(k), toward).set(k < 1 ? tackle(k * 0.6) : ground());
          if (t < hit + 0.5) world.ballAt(lob(passFrom.set(hitAt.x, 0.9, hitAt.z), loose, 0.7, span(t, hit, hit + 0.5), ball), v(Math.sin(t * 9), 0.4, 1));
          else if (t < pickAt) world.ballAt(loose, v(1, 0, 0));
          else world.ballAt(carried(fullback, "two", ball), v(1, 0, 0));
        }
        const grab = [hitAt.x + side * 0.2, hitAt.z - d * 0.6];
        if (t < hit) runner(chaserA, route([aEnd, grab]), t, 0, hit, { from: 1, to: 1, speed: 1 });
        else {
          const k = span(t, hit, hit + 0.45);
          chaserA.place(grab[0], grab[1], toward).set(k < 1 ? tackle(k) : ground());
        }
        runner(chaserB, route([bEnd, at(hitAt.x + side * 3, hitU + 4)]), t, 0, hit + 0.3, { from: 1, to: 0.3, speed: 0.9 });
        runner(cover, route([coverEnd, at(wingX + side * 3, hitU + 2)]), t, 0, hit + 0.3, { from: 1, to: 0.3, speed: 0.9 });
        if (t >= hit + 0.3) {
          chaserB.set(ready(0.2));
          cover.set(ready(0.2));
        }
        refereeTo(at(refX, hitU + 1), t, 0, hit + 0.5, Infinity);
        return follow(hero.root.position.x, Math.min(uOf(hero), hitU + 2));
      },
    };
  }

  function spreadOutcome(good) {
    const release = 0.26;
    const arrive = 0.68;
    const length = route(wingPath).total;
    const tEnd = length / CHARGE;
    const scoreAt = tEnd + 0.4;
    const fall = v(wingX + side * 0.8, 0.12, Z(uf - 5.4));
    const bounce = v(fall.x + side * 0.4, 0.12, fall.z - d * 2.2);
    const ground1 = 0.82;
    const whistleAt = 1.05;
    const pick = [bounce.x - side * 0.3, bounce.z - d * 0.7];
    const pickAt = 2.35;
    const end = good ? scoreAt + 2 : 3.4;
    const heroStop = at(hx - side * 0.3, uf - 5.5);
    const refHeading = -Math.PI / 2;
    // Leur attaque à eux part vers l'autre sens : le bras de l'arbitre.
    const arm = -Math.sin(refHeading) * -d > 0 ? 1 : -1;
    return {
      duration: end,
      cues: good
        ? [
            {
              at: scoreAt,
              run: () => {
                world.sound("whistle", true);
                reaction(world, true);
              },
            },
          ]
        : [
            { at: whistleAt, run: () => world.sound("whistle") },
            { at: whistleAt + 0.15, run: () => reaction(world, false) },
          ],
      frame(t) {
        setupFrame(duration);
        leftovers.forEach((snap, player) => trail(player, RUN + t, snap, 2.4));
        runner(hero, route([at(hx, uf), heroStop]), t, 0, 1.15, { from: 0.9, to: 0.15, speed: 0.75, carry: "none" });
        if (t < release + 0.28) hero.set(pass(span(t, release - 0.14, release + 0.14), passSide));
        else if (t >= 1.15) hero.set(good ? (t > scoreAt + 0.15 ? cheer(t * 1.5) : ready(0.2)) : dejected());
        carried(hero, "two", passFrom);
        if (good) {
          tryRun(wing, wingPath, t, 0, tEnd, { carry: t < arrive + 0.25 ? "two" : "one", hasBall: t >= arrive });
          if (t < release) world.ballAt(passFrom, v(1, 0, 0));
          else if (t < arrive) world.ballAt(lob(passFrom, carried(wing, "two", passTo), 0.4, span(t, release, arrive), ball), v(1, 0, 0));
          // L'arrière a mordu sur le joueur incarné : il repart trop tard et plonge en vain.
          const chaseTo = at(wingX + side * 0.2, 2.4);
          const biteAt = 0.55;
          const biteSpot = [hx + side * 1.8, fullbackEnd[1]];
          if (t < biteAt) runner(fullback, route([fullbackEnd, biteSpot]), t, 0, biteAt, { from: 0.3, to: 0.5, speed: 0.5 });
          else if (t < tEnd) runner(fullback, route([biteSpot, chaseTo]), t, biteAt, tEnd, { from: 0.4, to: 1, speed: 0.95 });
          else {
            const k = span(t, tEnd, tEnd + 0.5);
            fullback.place(chaseTo[0], chaseTo[1], headingTo(...biteSpot, ...chaseTo)).set(k < 1 ? tackle(k) : ground());
          }
          chase(t, tEnd, wingX - side * 4);
          refereeTo(at(refX, 3), t, 0, tEnd, scoreAt);
          return follow(wing.root.position.x, uOf(wing));
        }
        // La passe part en avant : elle tombe devant l'ailier, qui ne peut que la regarder.
        runner(wing, route([wingEnd, at(wingX, uf - 3.5)]), t, 0, 1.2, { from: 0.9, to: 0.1, speed: 0.75 });
        if (t >= 1.2) wing.set(dejected());
        if (t < release) world.ballAt(passFrom, v(1, 0, 0));
        else if (t < ground1) world.ballAt(lob(passFrom, fall, 0.55, span(t, release, ground1), ball), v(1, 0, 0));
        else if (t < pickAt) world.ballAt(grubber(fall, bounce, span(t, ground1, 1.5), 2, ball), v(Math.sin(t * 10), 0.3, 1));
        else world.ballAt(carried(fullback, "two", ball), v(1, 0, 0));
        // L'arbitre siffle, le bras vers leur attaque ; leur arrière vient ramasser.
        runner(fullback, route([fullbackEnd, pick]), t, 0.5, pickAt - 0.2, { from: 0.4, to: 0.5, speed: 0.55 });
        if (t >= pickAt - 0.2) fullback.place(pick[0], pick[1], faceHero).set(t < pickAt + 0.05 ? crouch(1) : ready(0.25));
        runner(chaserA, route([aEnd, at(hx - side * 1.2, uf - 1)]), t, 0, 1.3, { from: 1, to: 0.1, speed: 0.8 });
        runner(chaserB, route([bEnd, at(hx + side * 2.5, uf + 1)]), t, 0, 1.3, { from: 1, to: 0.1, speed: 0.8 });
        runner(cover, route([coverEnd, at(wingX + side * 3.5, uf - 1)]), t, 0, 1.3, { from: 1, to: 0.1, speed: 0.8 });
        if (t >= 1.3) [chaserA, chaserB, cover].forEach((player) => player.set(ready(0.2)));
        ref.place(refEnd[0], refEnd[1], refHeading).set(t > whistleAt ? signal(arm, smooth(span(t, whistleAt, whistleAt + 0.3))) : ready(0.1));
        return view(lerp(hx, wingX, 0.5), uf - 4.5, { far: 1.05, fov: 33 });
      },
    };
  }

  function kickOutcome(good) {
    const kickAt = 0.28;
    const land = 1.15;
    const landing = v(chipLand[0], 0.2, Z(chipLand[1]));
    const length = route(kickPath).total;
    const tEnd = 0.25 + length / CHARGE;
    const scoreAt = tEnd + 0.4;
    const grounded = v(kickPath[2][0], 0.13, Z(-1));
    // Raté : le ballon rebondit de travers, droit sur leur arrière.
    const askew = v(chipLand[0] + side * 3.2, 0.12, Z(chipLand[1] + 0.8));
    const gather = 1.75;
    const lift = gather + 0.3;
    const pick = [askew.x + side * 0.1, askew.z - d * 0.7];
    const away = at(askew.x + side * 8, chipLand[1] + 0.5); // il file dégager vers la touche
    const end = good ? scoreAt + 2 : lift + 1.9;
    const stopAt = at(hx - side * 0.8, Math.max(uf - 6.5, 4));
    const bite = at(heroX - side * 0.2, Math.max(uf - 6.8, 2.4));
    return {
      duration: end,
      cues: [
        { at: kickAt, run: () => world.sound("kick") },
        good
          ? {
              at: scoreAt,
              run: () => {
                world.sound("whistle", true);
                reaction(world, true);
              },
            }
          : { at: gather, run: () => reaction(world, false) },
      ],
      frame(t) {
        setupFrame(duration);
        leftovers.forEach((snap, player) => trail(player, RUN + t, snap, 2.4));
        runner(wing, route([wingEnd, at(wingX, Math.max(uf - 8, 3))]), t, 0, 1.6, { from: 0.9, to: 0.2, speed: 0.75 });
        if (t >= 1.6) wing.set(good && t > scoreAt + 0.3 ? cheer(t * 1.4) : good ? ready(0.2) : dejected());
        const kicking = t > 0.04 && t < kickAt + 0.3;
        if (good) {
          tryRun(hero, kickPath, t, 0.08, tEnd, { hasBall: false, carry: "none", from: 0.6 });
          if (kicking) hero.set(kick(span(t, 0.04, kickAt + 0.28)));
          if (t < kickAt) world.ballAt(carried(hero, "two", ball), forwardAxis);
          else if (t < land) world.ballAt(lob(passFrom.set(hx, 0.6, Z(uf - 1)), landing, 4.8, span(t, kickAt, land), ball), v(Math.sin(t * 9), 1, Math.cos(t * 9)));
          else if (t < tEnd + 0.35) world.ballAt(grubber(landing, grounded, span(t, land, tEnd + 0.35), 4, ball), v(Math.sin(t * 7), 0.3, 1));
          else world.ballAt(grounded, v(1, 0, 0));
          // Leur arrière se retourne, mais le ballon l'a passé et le joueur aussi.
          runner(fullback, route([fullbackEnd, bite, at(heroX + side * 1.8, 2.6)]), t, 0.15, tEnd + 0.2, { from: 0.3, to: 0.85, speed: 0.85 });
          if (t >= tEnd + 0.2) fullback.set(dejected());
          chase(t, tEnd);
          refereeTo(at(refX, 2.5), t, 0, tEnd, scoreAt);
          return follow(lerp(hero.root.position.x, ball.x, 0.3), Math.min(uOf(hero), lerp(uOf(hero), chipLand[1], 0.35)));
        }
        // Le rebond les favorise : leur arrière ramasse et file vers la touche.
        runner(hero, route([at(hx, uf), stopAt]), t, 0.08, 2.1, { from: 0.6, to: 0.1, speed: 0.75 });
        if (kicking) hero.set(kick(span(t, 0.04, kickAt + 0.28)));
        else if (t >= 2.1) hero.set(dejected());
        if (t < kickAt) world.ballAt(carried(hero, "two", ball), forwardAxis);
        else if (t < land) world.ballAt(lob(passFrom.set(hx, 0.6, Z(uf - 1)), landing, 4.8, span(t, kickAt, land), ball), v(Math.sin(t * 9), 1, Math.cos(t * 9)));
        else if (t < lift) world.ballAt(grubber(landing, askew, span(t, land, gather), 2, ball), v(Math.sin(t * 7), 0.3, 1));
        else world.ballAt(carried(fullback, "one", ball), forwardAxis);
        if (t < gather - 0.05) {
          runner(fullback, route([fullbackEnd, pick]), t, 0.3, gather - 0.05, { from: 0.3, to: 0.7, speed: 0.7 });
        } else if (t < lift) fullback.place(pick[0], pick[1], faceHero).set(crouch(1));
        else runner(fullback, route([pick, away]), t, lift, end + 0.1, { from: 0.4, to: 0.95, speed: 0.85, carry: "one" });
        runner(chaserA, route([aEnd, at(hx - side * 1.5, uf - 2)]), t, 0, 1.5, { from: 1, to: 0.1, speed: 0.8 });
        runner(chaserB, route([bEnd, at(hx + side * 2, uf)]), t, 0, 1.5, { from: 1, to: 0.1, speed: 0.8 });
        runner(cover, route([coverEnd, at(wingX + side * 3, uf - 1)]), t, 0, 1.5, { from: 1, to: 0.1, speed: 0.8 });
        if (t >= 1.5) [chaserA, chaserB, cover].forEach((player) => player.set(ready(0.2)));
        runner(ref, route([refEnd, at(refX, uf - 4)]), t, 0, 2, { from: 0.7, to: 0.2, speed: 0.6, still: ready(0.1) });
        // La caméra suit le ballon, puis l'arrière qui l'emporte.
        const onBall = smooth(span(t, kickAt, land));
        const onHim = smooth(span(t, lift, lift + 1));
        return view(lerp(lerp(hx, chipLand[0] + side * 2, onBall), fullback.root.position.x, onHim), lerp(uf - 3.6, chipLand[1] + 2.2, onBall), { far: 1.05, fov: 33 });
      },
    };
  }

  return {
    setup,
    preview,
    outcome(key, result) {
      if (key === "solo") return soloOutcome(result.success);
      if (key === "spread") return spreadOutcome(result.success);
      return kickOutcome(result.success);
    },
  };
}
