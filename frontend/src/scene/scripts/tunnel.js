import * as THREE from "three";

import { mixPose, pose, run } from "../rig.js";
import { carried, clamp, lerp, route, smooth, span } from "./common.js";

// L'entrée des équipes d'une finale ou d'un derby, à regarder : le bâtiment du tunnel, au
// bord du terrain, côté sans tribune. L'arbitre sort le premier, ballon en mains, puis les
// capitaines, leurs équipes en deux files côte à côte. Ils marchent, trottinent, et
// s'écartent en deux lignes face au tunnel, le public debout derrière elles. Trois plans
// séparés par un fondu : serré à la sortie, large sur le stade, les deux lignes.
//
// `data` : `final`, `derby`.

const MOUTH = -38; // le fond de la façade
const BACK_WALL = -52;
const CENTER = 50; // le tunnel débouche sur la médiane
const HALF = 3; // demi-largeur du couloir
const HIGH = 3.6;
const FILE = 1; // écart de chaque file au milieu du couloir
const GAP = 1.15; // entre deux joueurs d'une file

const LINE_X = -9; // les deux lignes, le long de la médiane
const TURN_X = -31; // à la sortie du couloir, les files s'écartent
const SLOT = 1.05; // entre deux joueurs d'une ligne
const FIRST = 2; // du milieu au premier joueur de chaque ligne

const WALK_SPEED = 2.3;
const TROT_SPEED = 6;
const TROT_AT = 3.4;
const SHOT_WIDE = 4;
const SHOT_LINES = 8;
const FADE = 0.25;
const DURATION = 12.8;

const ORDER = [8, 1, 2, 3, 4, 5, 6, 7, 9, 10, 11, 12, 13, 14, 15]; // le capitaine devant
const STAND = pose({ abL: 0.12, abR: 0.12, elL: 0.25, elR: 0.25 });
const HOLD_BALL = pose({ armL: 0.75, armR: 0.75, elL: 1.1, elR: 1.1, abL: -0.15, abR: -0.15 });
const FACE = -Math.PI / 2; // vers le tunnel et la caméra
const BRAKE = 1.6; // un joueur freine sur ses derniers mètres

// La couleur d'un maillot, lue sur les chaussettes d'un joueur (le plateau n'en donne pas).
const kitColor = (player) => player.kneeL.children[0].material.color;

// La distance parcourue par la tête de file : la marche, puis le trot.
const covered = (t) => WALK_SPEED * Math.min(t, TROT_AT) + TROT_SPEED * Math.max(0, t - TROT_AT);
// Le temps qu'il faut pour parcourir `d`.
const timeFor = (d) => (d <= WALK_SPEED * TROT_AT ? d / WALK_SPEED : TROT_AT + (d - WALK_SPEED * TROT_AT) / TROT_SPEED);

// Le bâtiment : la façade en deux pans et un linteau, le couloir sombre, un auvent aux
// couleurs des deux équipes, un tapis jusqu'à la touche.
function buildTunnelSet(colors) {
  const group = new THREE.Group();
  const lambert = (color, extra = {}) => new THREE.MeshLambertMaterial({ color, flatShading: true, ...extra });
  const concrete = lambert(0xa8abb0); // la façade est à contre-jour
  const dark = lambert(0x55585e);
  const black = lambert(0x0c0d0f);
  const paint = lambert(0xeaeae4);
  const ours = lambert(colors.us);
  const theirs = lambert(colors.them);
  const box = (w, h, d, x, y, z, material) => {
    const mesh = new THREE.Mesh(new THREE.BoxGeometry(w, h, d), material);
    mesh.position.set(x, y, z);
    group.add(mesh);
    return mesh;
  };
  const depth = MOUTH - BACK_WALL;
  const midX = (MOUTH + BACK_WALL) / 2;
  const height = 9;
  const near = -12;
  const far = 112;
  box(depth, height, CENTER - HALF - near, midX, height / 2, (near + CENTER - HALF) / 2, concrete);
  box(depth, height, far - CENTER - HALF, midX, height / 2, (far + CENTER + HALF) / 2, concrete);
  box(depth, height - HIGH, HALF * 2, midX, (height + HIGH) / 2, CENTER, concrete);
  // Le toit et un bandeau sombre le long de la façade.
  box(depth + 3, 0.4, far - near, midX + 1.5, height + 0.2, (near + far) / 2, dark);
  box(0.15, 1.1, far - near, MOUTH + 0.08, height - 2, (near + far) / 2, dark);
  // Le couloir : sol, plafond, parois et fond sombres.
  box(depth, 0.1, HALF * 2, midX, 0.03, CENTER, black);
  box(depth, 0.1, HALF * 2, midX, HIGH - 0.05, CENTER, black);
  box(depth, HIGH, 0.1, midX, HIGH / 2, CENTER - HALF + 0.05, black);
  box(depth, HIGH, 0.1, midX, HIGH / 2, CENTER + HALF - 0.05, black);
  box(0.1, HIGH, HALF * 2, BACK_WALL + 0.1, HIGH / 2, CENTER, black);
  // L'auvent, jusqu'à la touche : une paroi par équipe, leur file de son côté.
  const reach = 2.4;
  box(reach, HIGH + 0.3, 0.3, MOUTH + reach / 2, (HIGH + 0.3) / 2, CENTER - HALF - 0.15, ours);
  box(reach, HIGH + 0.3, 0.3, MOUTH + reach / 2, (HIGH + 0.3) / 2, CENTER + HALF + 0.15, theirs);
  box(reach, 0.3, HALF * 2 + 0.6, MOUTH + reach / 2, HIGH + 0.15, CENTER, paint);
  box(0.12, 0.7, HALF * 2 + 0.6, MOUTH + reach + 0.06, HIGH + 0.15, CENTER, dark);
  // Le tapis, jusqu'à la touche.
  box(MOUTH * -1 - 34, 0.03, HALF * 2 - 1, (MOUTH - 34) / 2, 0.02, CENTER, dark);
  // De grandes bannières sur la façade, chaque club de son côté du tunnel.
  for (let i = 0; i < 3; i++) {
    box(0.12, 6, 2.6, MOUTH + 0.1, 3.8, CENTER - HALF - 3.6 - i * 7, ours);
    box(0.12, 6, 2.6, MOUTH + 0.1, 3.8, CENTER + HALF + 3.6 + i * 7, theirs);
  }

  return group;
}

// D'un cap à l'autre, par le chemin le plus court.
function lerpAngle(a, b, k) {
  const turn = ((((b - a) % (Math.PI * 2)) + Math.PI * 3) % (Math.PI * 2)) - Math.PI;
  return a + turn * k;
}

export function buildTunnel(world) {
  const start = MOUTH - 3.5; // la tête de file au début, encore dans le couloir

  // Une file, puis sa place sur la ligne : les premiers au milieu, les derniers au bout.
  const fileOf = (team, side) =>
    ORDER.map((number, i) => {
      const file = CENTER + side * FILE;
      const slot = CENTER + side * (FIRST + i * SLOT);
      const path = route([[start - i * GAP, file], [TURN_X, file], [LINE_X, slot]]);
      return { player: world.player(team, number), path, arrive: timeFor(path.total + BRAKE / 2), i };
    });
  const walkers = [...fileOf("us", -1), ...fileOf("them", 1)];
  const ref = world.player("ref");
  const refPath = route([[start + 2.4, CENTER], [LINE_X - 3, CENTER]]);
  const refArrive = timeFor(refPath.total + BRAKE / 2);
  const set = buildTunnelSet({
    us: kitColor(walkers[0].player),
    them: kitColor(walkers[walkers.length - 1].player),
  });
  world.add(set);
  world.tee.visible = false;

  const ballPoint = new THREE.Vector3();
  const axis = new THREE.Vector3(1, 0, 0);

  // Un marcheur : il suit son trajet à l'allure commune, ralentit, se retourne, s'arrête.
  function walk({ player, path, arrive, i }, t, carry = "none") {
    const left = path.total - covered(t);
    const k = clamp((left + BRAKE) / (2 * BRAKE));
    const spot = path.at(left > BRAKE ? covered(t) : path.total - BRAKE * k * k);
    const turn = smooth(span(t, arrive - 0.1, arrive + 0.55));
    const phase = (Math.min(t, TROT_AT) * WALK_SPEED) / 1.5 + (Math.max(0, t - TROT_AT) * TROT_SPEED) / 2.3 + i * 0.37;
    const pace = lerp(0.15, 0.42, smooth(span(t, TROT_AT - 0.2, TROT_AT + 0.6)));
    player.visible = spot.x > BACK_WALL + 0.5;
    player.place(spot.x, spot.z, lerpAngle(spot.heading, FACE, turn));
    const still = carry === "two" ? HOLD_BALL : STAND;
    player.set(turn >= 1 ? still : mixPose(run(phase, pace, carry), still, smooth(span(t, arrive - 0.25, arrive + 0.2))));
  }

  // Les trois plans.
  function camera(t) {
    if (t < SHOT_WIDE) {
      // Serré à la sortie : les joueurs viennent vers la caméra, de biais.
      const k = t / SHOT_WIDE;
      return { pos: [lerp(-29.5, -28.5, k), 1.7, lerp(44.2, 43.6, k)], look: [lerp(-36, -33, k), 1.75, lerp(50, 49.6, k)], fov: 36 };
    }
    if (t < SHOT_LINES) {
      // Au-dessus du toit : le terrain, les deux files qui s'écartent, la tribune en face.
      const k = (t - SHOT_WIDE) / (SHOT_LINES - SHOT_WIDE);
      return { pos: [lerp(-37, -35, k), lerp(19, 17, k), lerp(76, 72, k)], look: [lerp(-13, -6, k), 3, lerp(47, 44, k)], fov: 38 };
    }
    // Les deux lignes, de biais depuis le tunnel, le public derrière elles.
    const k = smooth((t - SHOT_LINES) / (DURATION - SHOT_LINES));
    return { pos: [lerp(-36, -35.5, k), lerp(6, 5.4, k), lerp(31, 33, k)], look: [-9, lerp(0.8, 1, k), lerp(45, 46, k)], fov: 43 };
  }

  function frame(t) {
    const near = Math.min(t, Math.abs(t - SHOT_WIDE), Math.abs(t - SHOT_LINES));
    world.exposure(smooth(near / FADE));
    for (const walker of walkers) walk(walker, t);
    walk({ player: ref, path: refPath, arrive: refArrive, i: 0 }, t, "two");
    world.ballAt(carried(ref, "two", ballPoint), axis);
    return camera(t);
  }

  return {
    setup: { duration: 0.05, frame: () => frame(0), cues: [] },
    outcome: () => ({
      duration: DURATION,
      cues: [
        { at: 0.1, run: () => world.crowd("standing") },
        { at: 0.7, run: () => world.sound("roar") },
        { at: SHOT_LINES + 0.2, run: () => world.sound("roar") },
      ],
      frame,
    }),
  };
}
