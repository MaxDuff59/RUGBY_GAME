import * as THREE from "three";

import { cheer, mixPose, pose, run } from "../rig.js";
import { lerp, route, smooth, span } from "./common.js";

// La remise du trophée, à regarder : notre équipe en demi-cercle devant un petit podium,
// la coupe sur son socle. Le capitaine va la chercher, revient au milieu, la soulève au-
// dessus de sa tête ; le stade se lève, l'équipe saute, les confettis partent. La caméra
// tourne doucement. Les confettis ne dépendent que du temps ; à la fin, les joueurs
// retombent les pieds au sol, bras levés, pour que l'image figée reste belle.
//
// `data` : `competition`.

const CX = 4;
const CZ = 40; // le capitaine, au milieu du terrain, la tribune derrière lui
const SOCLE_X = CX + 2.9;
const SOCLE_H = 1;

const WALK_TO = 1.4;
const PICK = 1.75;
const BACK_FROM = 2.2;
const BACK_AT = 3.5;
const LIFT_FROM = 4.5;
const LIFT_AT = 5.5;
const DURATION = 10.5;

const FACE_SOCLE = Math.PI / 2;
const FACE_CAMERA = -Math.PI / 2;

const AT_CHEST = pose({ armL: 0.95, armR: 0.95, elL: 1.05, elR: 1.05, abL: -0.08, abR: -0.08, nod: 0.1 });
const REACH = pose({ y: -0.08, lean: 0.4, legL: 0.25, knL: 0.35, knR: 0.2, armL: 1.15, armR: 1.15, elL: 0.45, elR: 0.45, abL: -0.08, abR: -0.08, nod: 0.25 });
const RAISED = pose({ armL: 2.86, armR: 2.86, elL: 0.12, elR: 0.12, abL: -0.26, abR: -0.26, lean: -0.05, nod: -0.3 });

// La couleur d'un maillot, lue sur les chaussettes d'un joueur (le plateau n'en donne pas).
const kitColor = (player) => player.kneeL.children[0].material.color;

// La coupe : pied, tige, vasque tournés, deux anses. Son origine est là où les mains la
// tiennent, au bas de la vasque.
function buildCup() {
  const gold = new THREE.MeshLambertMaterial({ color: 0xf5c63a, emissive: 0x7a5508, flatShading: true });
  const cup = new THREE.Group();
  const profile = [
    [0, -0.28],
    [0.17, -0.28],
    [0.15, -0.23],
    [0.05, -0.19],
    [0.045, -0.04],
    [0.13, 0.02],
    [0.2, 0.2],
    [0.215, 0.44],
    [0.25, 0.52],
    [0.19, 0.5],
    [0, 0.34],
  ].map(([x, y]) => new THREE.Vector2(x, y));
  cup.add(new THREE.Mesh(new THREE.LatheGeometry(profile, 10), gold));
  cup.scale.setScalar(1.25); // vue de loin, une coupe à l'échelle tiendrait dans dix pixels
  const handle = new THREE.TorusGeometry(0.11, 0.022, 4, 8);
  for (const side of [-1, 1]) {
    const mesh = new THREE.Mesh(handle, gold);
    mesh.position.set(side * 0.24, 0.27, 0);
    cup.add(mesh);
  }
  return cup;
}

// Le podium : deux marches, la toile de fond aux couleurs du club, le socle de la coupe.
function buildPodium(color, trim) {
  const group = new THREE.Group();
  const lambert = (c) => new THREE.MeshLambertMaterial({ color: c, flatShading: true });
  const dark = lambert(0x2a2d32);
  const light = lambert(0xeaeae4);
  const club = lambert(color);
  const edge = lambert(trim);
  const box = (w, h, d, x, y, z, material) => {
    const mesh = new THREE.Mesh(new THREE.BoxGeometry(w, h, d), material);
    mesh.position.set(x, y, z);
    group.add(mesh);
  };
  box(2.4, 0.25, 4.4, CX + 5, 0.125, CZ, dark);
  box(1.6, 0.25, 3.2, CX + 5.4, 0.375, CZ, light);
  // La toile, au sombre de la couleur du club : la coupe s'y détache, quelle qu'elle soit.
  box(0.25, 4.2, 7, CX + 6.5, 2.1, CZ, lambert(new THREE.Color(color).multiplyScalar(0.35)));
  box(0.3, 0.7, 7, CX + 6.5, 0.35, CZ, club);
  box(0.3, 0.3, 7.3, CX + 6.5, 4.3, CZ, edge);
  box(0.7, SOCLE_H, 0.7, SOCLE_X, SOCLE_H / 2, CZ, dark);
  box(0.82, 0.08, 0.82, SOCLE_X, SOCLE_H - 0.04, CZ, light);
  return group;
}

// Les confettis : chaque paillette sort d'un canon derrière le capitaine, monte, puis
// retombe en voltigeant. Sa place ne dépend que du temps.
function buildConfetti(colors, burstAt) {
  const count = 520;
  const positions = new Float32Array(count * 3);
  const tints = new Float32Array(count * 3);
  const seeds = [];
  const tint = new THREE.Color();
  // Un tirage à part : le nombre de paillettes ne change rien au reste de la scène.
  let a = 12345;
  const random = () => {
    a = (Math.imul(a, 1664525) + 1013904223) >>> 0;
    return a / 4294967296;
  };
  for (let i = 0; i < count; i++) {
    tint.copy(colors[i % colors.length]);
    tints.set([tint.r, tint.g, tint.b], i * 3);
    seeds.push({
      delay: random() * random() * 2.4,
      x: -4 + random() * 13,
      z: (random() - 0.5) * 22,
      top: 4.5 + random() * 5,
      fall: 0.95 + random() * 0.7,
      sway: 0.25 + random() * 0.5,
      rate: 1.4 + random() * 2.2,
      phase: random() * Math.PI * 2,
      from: (random() - 0.5) * 3,
    });
  }
  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute("position", new THREE.BufferAttribute(positions, 3).setUsage(THREE.DynamicDrawUsage));
  geometry.setAttribute("color", new THREE.BufferAttribute(tints, 3));
  // Sans écriture de profondeur : le contour du rendu noircirait des paillettes si petites.
  const material = new THREE.PointsMaterial({ size: 0.3, vertexColors: true, transparent: true, depthWrite: false });
  const points = new THREE.Points(geometry, material);
  points.frustumCulled = false;
  const SPAN = 9.5; // une paillette arrivée au sol repart d'en haut
  return {
    points,
    update(t) {
      seeds.forEach((seed, i) => {
        const age = t - burstAt - seed.delay;
        if (age < 0) {
          positions.set([CX, -5, CZ], i * 3);
          return;
        }
        const out = 1 - (1 - Math.min(1, age / 0.7)) ** 3; // la sortie du canon
        const down = Math.max(0, age - 0.5) * seed.fall;
        const y = lerp(2.2, seed.top, out) - down;
        positions[i * 3] = CX + 1.5 + (seed.x - 1.5) * out + Math.sin(age * seed.rate + seed.phase) * seed.sway * out;
        positions[i * 3 + 1] = ((y % SPAN) + SPAN) % SPAN;
        positions[i * 3 + 2] = CZ + lerp(seed.from, seed.z, out) + Math.cos(age * seed.rate * 0.8 + seed.phase) * seed.sway * out;
      });
      geometry.attributes.position.needsUpdate = true;
    },
  };
}

export function buildTrophy(world) {
  const captain = world.player("us", 8);
  // Deux ailes, de part et d'autre du podium, tournées vers le capitaine ; un rang sur
  // deux un peu en arrière, pour que personne n'en cache un autre.
  const numbers = [1, 2, 3, 4, 5, 6, 7, 9, 10, 11, 12, 13, 14, 15];
  const team = numbers.map((number, i) => {
    const side = i % 2 ? 1 : -1;
    const j = i >> 1;
    const angle = THREE.MathUtils.degToRad(36 + j * 10.8);
    const radius = 3.4 + (j % 2) * 0.95;
    const x = CX + Math.cos(angle) * radius;
    const z = CZ + side * Math.sin(angle) * radius;
    return { player: world.player("us", number), x, z, heading: Math.atan2(CX - x, CZ - z), i };
  });
  const official = world.player("ref");
  const colors = [kitColor(captain), new THREE.Color(0xf2c230), new THREE.Color(0xf7f7f4)];
  world.add(buildPodium(colors[0], 0xf2c230));
  const cup = world.add(buildCup());
  const confetti = buildConfetti(colors, LIFT_AT - 0.1);
  world.add(confetti.points);
  world.ball.visible = false;
  world.tee.visible = false;

  const toSocle = route([[CX + 0.9, CZ], [SOCLE_X - 0.62, CZ]]);
  const handL = new THREE.Vector3();
  const handR = new THREE.Vector3();
  const rest = new THREE.Vector3(CX + 2.9, SOCLE_H + 0.28, CZ);

  function placeCaptain(t) {
    const near = toSocle.at(toSocle.total);
    if (t < WALK_TO) {
      const k = span(t, 0.1, WALK_TO);
      const d = toSocle.total * smooth(k);
      const spot = toSocle.at(d);
      captain.place(spot.x, spot.z, FACE_SOCLE).set(k > 0 && k < 1 ? run(d / 1.1, 0.15) : pose());
    } else if (t < BACK_FROM) {
      const reach = smooth(span(t, WALK_TO, PICK));
      const up = smooth(span(t, PICK, BACK_FROM));
      captain.place(near.x, near.z, FACE_SOCLE).set(mixPose(mixPose(pose(), REACH, reach), AT_CHEST, up));
    } else if (t < BACK_AT) {
      // Il se retourne, la coupe contre lui, et revient au milieu.
      const k = smooth(span(t, BACK_FROM, BACK_AT));
      const heading = lerp(FACE_SOCLE, FACE_SOCLE + Math.PI, smooth(span(t, BACK_FROM, BACK_FROM + 0.7)));
      captain.place(lerp(near.x, CX, k), CZ, heading).set(AT_CHEST);
    } else {
      const raise = smooth(span(t, LIFT_FROM, LIFT_AT));
      const body = mixPose(AT_CHEST, RAISED, raise);
      // Il agite la coupe, de moins en moins : à la fin, elle est tout en haut.
      const pump = Math.sin((t - LIFT_AT) * 5.5) * 0.14 * smooth(span(t, LIFT_AT, LIFT_AT + 0.3)) * (1 - smooth(span(t, DURATION - 1.4, DURATION - 0.3)));
      body.armL += pump;
      body.armR += pump;
      captain.place(CX, CZ, FACE_CAMERA).set(body);
    }
  }

  // La coupe : sur le socle, puis exactement entre les mains du capitaine.
  function placeCup(t) {
    if (t < PICK) {
      cup.position.copy(rest);
      cup.rotation.y = FACE_SOCLE;
      return;
    }
    captain.root.updateWorldMatrix(true, true);
    captain.elbowL.localToWorld(handL.set(0, -0.3, 0));
    captain.elbowR.localToWorld(handR.set(0, -0.3, 0));
    cup.position.addVectors(handL, handR).multiplyScalar(0.5);
    cup.position.y += 0.18; // les mains au pied de la vasque
    cup.rotation.y = captain.heading;
  }

  function frame(t) {
    world.exposure(smooth(t / 0.3));
    placeCaptain(t);
    placeCup(t);
    const settle = 1 - smooth(span(t, DURATION - 1.3, DURATION - 0.2));
    for (const { player, x, z, heading, i } of team) {
      player.place(x, z, heading);
      if (t < LIFT_AT - 0.2) {
        // Ils applaudissent.
        const clap = Math.sin(t * 8 + i * 1.3) * 0.5 + 0.5;
        player.set(pose({ armL: 1.05, armR: 1.05, elL: 0.9, elR: 0.9, abL: -0.25 - clap * 0.22, abR: -0.25 - clap * 0.22 }));
      } else {
        const body = cheer((t - LIFT_AT) * 1.5 + i * 0.29);
        body.lift *= settle;
        player.set(body);
      }
    }
    official.place(CX + 5.4, CZ + 1.15, -Math.PI / 2);
    official.root.position.y = 0.5;
    official.set(pose({ armL: 1.05, armR: 1.05, elL: 0.9, elR: 0.9, abL: -0.25 - (Math.sin(t * 7) * 0.5 + 0.5) * 0.22, abR: -0.3 }));
    confetti.update(t);

    // La caméra tourne doucement autour du capitaine et monte avec la coupe.
    const k = t / DURATION;
    const angle = lerp(-0.4, 0.22, k);
    const radius = lerp(10, 8.8, smooth(k));
    const up = smooth(span(t, LIFT_FROM - 0.5, LIFT_AT));
    return {
      pos: [CX - Math.cos(angle) * radius, lerp(2.5, 2.1, up), CZ + Math.sin(angle) * radius],
      look: [CX + lerp(1.6, 0.4, smooth(span(t, BACK_FROM, BACK_AT))), lerp(1.2, 1.75, up), CZ],
      fov: 33,
    };
  }

  return {
    setup: { duration: 0.05, frame: () => frame(0), cues: [] },
    outcome: () => ({
      duration: DURATION,
      cues: [
        { at: 0.1, run: () => world.crowd("standing") },
        {
          at: LIFT_AT - 0.2,
          run: () => {
            world.crowd("cheer", "us");
            world.sound("roar");
          },
        },
      ],
      frame,
    }),
  };
}
