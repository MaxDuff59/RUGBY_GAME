import * as THREE from "three";
import { mergeGeometries } from "three/addons/utils/BufferGeometryUtils.js";

import { BAR, GAP, PAD_H, PAD_R, POST_HEIGHT, POST_R } from "./ball.js";

// Le décor des scènes de match : un terrain sans stade entier (les poteaux d'un seul
// côté, où se jouent la plupart des actions ; l'autre moitié pour les relances). Pelouse tondue en bandes, lignes,
// poteaux en H aux protections du club qui reçoit, panneaux aux sponsors, et deux
// tribunes basses (le long de la touche d'en face et derrière l'en-but) garnies d'un
// public instancié qui se lève, chante, siffle et agite ses écharpes. Le temps du match
// (pluie, vent sur les fanions, chaleur) et l'heure (projecteurs le soir) aussi.
//
// Repère de ball.js : x en travers (touches en ±35), y en haut, ligne d'essai en z = 0,
// en-but de z = -10 à 0, le terrain vers +z.

export const TOUCH = 35;
export const DEAD_BALL = -10;
export const FAR_LINE = 100; // la ligne d'essai d'en face (sans poteaux)

const canvasOf = (width, height) => Object.assign(document.createElement("canvas"), { width, height });

const lambert = (color, extra = {}) => new THREE.MeshLambertMaterial({ color, flatShading: true, ...extra });

function texture(canvas, repeat = [1, 1]) {
  const map = new THREE.CanvasTexture(canvas);
  map.colorSpace = THREE.SRGBColorSpace;
  map.wrapS = map.wrapT = THREE.RepeatWrapping;
  map.repeat.set(...repeat);
  map.magFilter = THREE.NearestFilter;
  return map;
}

// Herbe : un grain fin de verts proches, raccordable.
function grassCanvas() {
  const size = 64;
  const canvas = canvasOf(size, size);
  const ctx = canvas.getContext("2d");
  ctx.fillStyle = "#3f6a3e";
  ctx.fillRect(0, 0, size, size);
  for (let i = 0; i < 700; i++) {
    ctx.fillStyle = `hsl(${100 + Math.random() * 20}, ${28 + Math.random() * 14}%, ${26 + Math.random() * 14}%)`;
    ctx.fillRect(Math.random() * size, Math.random() * size, 1, 1 + Math.random() * 2);
  }
  return canvas;
}

// Lignes blanches, fusionnées en un seul maillage posé sur l'herbe.
function linesGeometry() {
  const parts = [];
  const strip = (x1, z1, x2, z2, width = 0.12) => {
    const length = Math.hypot(x2 - x1, z2 - z1);
    const geometry = new THREE.PlaneGeometry(width, length);
    geometry.rotateX(-Math.PI / 2);
    geometry.rotateY(Math.atan2(x2 - x1, z2 - z1));
    geometry.translate((x1 + x2) / 2, 0.006, (z1 + z2) / 2);
    parts.push(geometry);
  };
  const dashedX = (z, from, to, dash, gap) => {
    for (let x = from; x < to; x += dash + gap) strip(x, z, Math.min(x + dash, to), z);
  };
  strip(-TOUCH, DEAD_BALL, TOUCH, DEAD_BALL); // ballon mort
  strip(-TOUCH, 0, TOUCH, 0); // essai
  strip(-TOUCH, 22, TOUCH, 22); // 22 m
  strip(-TOUCH, 50, TOUCH, 50); // médiane
  strip(-TOUCH, 78, TOUCH, 78); // nos 22
  strip(-TOUCH, FAR_LINE, TOUCH, FAR_LINE);
  strip(-TOUCH, DEAD_BALL, -TOUCH, FAR_LINE);
  strip(TOUCH, DEAD_BALL, TOUCH, FAR_LINE);
  for (const z of [5, 40, 60, 95]) dashedX(z, -TOUCH + 5, TOUCH - 5, 1.2, 1.8); // 5 m, 10 m
  for (const x of [-30, -20, 20, 30]) {
    for (let z = 2; z < FAR_LINE - 1; z += 5) if (![22, 50, 78].some((line) => Math.abs(z - line) < 1.5)) strip(x, z, x, z + 1.2);
  }
  return mergeGeometries(parts);
}

// Panneau publicitaire : les logos des sponsors du club, ou son nom, sur fond sombre.
function boardCanvas(clubName, logos, accent) {
  const canvas = canvasOf(1024, 48);
  const ctx = canvas.getContext("2d");
  ctx.fillStyle = "#16181B";
  ctx.fillRect(0, 0, 1024, 48);
  ctx.font = '700 32px "Barlow Condensed", "Arial Narrow", sans-serif';
  ctx.textBaseline = "middle";
  ctx.textAlign = "center";
  const slots = 4;
  for (let i = 0; i < slots; i++) {
    const x = (i + 0.5) * (1024 / slots);
    const logo = logos.length ? logos[i % logos.length] : null;
    if (logo && i % 2 === 0) {
      ctx.drawImage(logo, x - 100, 4, 200, 40);
    } else {
      ctx.fillStyle = accent;
      ctx.fillRect(x - 128, 0, 8, 48);
      ctx.fillStyle = "#F7F7F4";
      ctx.fillText(clubName.toUpperCase(), x, 26, 230);
    }
  }
  return canvas;
}

// Protection des poteaux aux couleurs du club qui reçoit.
function padCanvas(color, ink, clubName) {
  const canvas = canvasOf(64, 128);
  const ctx = canvas.getContext("2d");
  ctx.fillStyle = color;
  ctx.fillRect(0, 0, 64, 128);
  ctx.save();
  ctx.translate(32, 64);
  ctx.rotate(-Math.PI / 2);
  ctx.fillStyle = ink;
  ctx.font = '700 22px "Barlow Condensed", "Arial Narrow", sans-serif';
  ctx.textAlign = "center";
  ctx.textBaseline = "middle";
  ctx.fillText(clubName.toUpperCase().slice(0, 12), 0, 0, 120);
  ctx.restore();
  return canvas;
}

const FORWARD = new THREE.Vector3(0, 0, 1);

// Le public : chaque spectateur est un buste et une tête (deux maillages instanciés),
// une partie tient une écharpe. `stands` : les rangées, déjà placées.
class Crowd {
  constructor(group, seats, { homeColors, awayColors, skins }) {
    const count = seats.length;
    const bodyGeometry = new THREE.BoxGeometry(0.5, 0.62, 0.34).translate(0, 0.31, 0);
    const headGeometry = new THREE.BoxGeometry(0.24, 0.26, 0.24).translate(0, 0.13, 0);
    const scarfGeometry = new THREE.BoxGeometry(1.0, 0.16, 0.05);
    this.bodies = new THREE.InstancedMesh(bodyGeometry, lambert(0xffffff), count);
    this.heads = new THREE.InstancedMesh(headGeometry, lambert(0xffffff), count);
    this.scarves = new THREE.InstancedMesh(scarfGeometry, lambert(0xffffff), count);
    const color = new THREE.Color();
    this.seats = seats.map((seat, i) => {
      const away = seat.away;
      const colors = away ? awayColors : homeColors;
      const neutral = ["#5E6168", "#8A8D93", "#16181B", "#EDEDE8"];
      const shirt = Math.random() < 0.7 ? colors[i % colors.length] : neutral[i % neutral.length];
      this.bodies.setColorAt(i, color.set(shirt));
      this.heads.setColorAt(i, color.set(skins[(i * 13) % skins.length]));
      this.scarves.setColorAt(i, color.set(colors[(i + 1) % colors.length]));
      return {
        ...seat,
        phase: Math.random() * Math.PI * 2,
        delay: Math.random() * 0.6,
        scarf: Math.random() < 0.45,
        stand: 0, // de 0 (assis) à 1 (debout)
        rise: 0,
      };
    });
    for (const mesh of [this.bodies, this.heads, this.scarves]) {
      mesh.instanceMatrix.setUsage(THREE.DynamicDrawUsage);
      mesh.frustumCulled = false;
      group.add(mesh);
    }
    this.mood = "seated";
    this.moodAt = 0;
    this.side = "home"; // qui se réjouit (cheer) ou siffle (boo)
    this.matrix = new THREE.Matrix4();
    this.quaternion = new THREE.Quaternion();
    this.position = new THREE.Vector3();
    this.scale = new THREE.Vector3(1, 1, 1);
    this.swing = new THREE.Quaternion();
    this.update(0, 0);
  }

  // "seated" : assis, ça murmure ; "standing" : debout, tendu ; "cheer" : debout, ça
  // saute et les écharpes tournent (côté `side`) ; "boo" : debout, ça siffle.
  setMood(mood, time, side = "home") {
    this.mood = mood;
    this.moodAt = time;
    this.side = side;
  }

  update(time, dt) {
    const { matrix, quaternion, position, scale, swing } = this;
    this.seats.forEach((seat, i) => {
      const ours = (seat.away ? "away" : "home") === this.side;
      const active = time - this.moodAt > seat.delay;
      let wanted = 0;
      if (this.mood === "standing") wanted = seat.phase > 1.2 ? 1 : 0.4;
      if (this.mood === "cheer") wanted = ours ? 1 : 0;
      if (this.mood === "boo") wanted = ours ? 1 : 0.2;
      if (active) seat.stand += (wanted - seat.stand) * Math.min(1, dt * 5);
      const jumping = this.mood === "cheer" && ours && active;
      const hop = jumping ? Math.max(0, Math.sin(time * 9 + seat.phase)) * 0.22 : Math.sin(time * 1.3 + seat.phase) * 0.01;
      const y = seat.y + seat.stand * 0.38 + hop;
      quaternion.setFromAxisAngle(THREE.Object3D.DEFAULT_UP, seat.turn);
      position.set(seat.x, y, seat.z);
      scale.set(1, 0.85 + seat.stand * 0.2, 1);
      this.bodies.setMatrixAt(i, matrix.compose(position, quaternion, scale));
      position.y = y + (0.85 + seat.stand * 0.2) * 0.62;
      scale.set(1, 1, 1);
      this.heads.setMatrixAt(i, matrix.compose(position, quaternion, scale));
      // L'écharpe tendue au-dessus de la tête, qui tourne quand ça chante.
      const waving = seat.scarf && seat.stand > 0.5 && (jumping || this.mood === "standing");
      position.y += waving ? 0.55 : -0.4;
      swing.setFromAxisAngle(FORWARD, waving ? Math.sin(time * (jumping ? 7 : 2.5) + seat.phase) * 0.5 : 0);
      scale.setScalar(waving ? 1 : 0.001);
      this.scarves.setMatrixAt(i, matrix.compose(position, quaternion.multiply(swing), scale));
    });
    this.bodies.instanceMatrix.needsUpdate = true;
    this.heads.instanceMatrix.needsUpdate = true;
    this.scarves.instanceMatrix.needsUpdate = true;
  }
}

// La pluie : des traits qui tombent dans une boîte autour de ce que regarde la caméra.
class Rain {
  constructor(group, wind) {
    const count = 900;
    this.drops = new Float32Array(count * 3);
    for (let i = 0; i < count; i++) {
      this.drops[i * 3] = (Math.random() - 0.5) * 50;
      this.drops[i * 3 + 1] = Math.random() * 18;
      this.drops[i * 3 + 2] = (Math.random() - 0.5) * 50;
    }
    this.positions = new Float32Array(count * 6);
    const geometry = new THREE.BufferGeometry();
    geometry.setAttribute("position", new THREE.BufferAttribute(this.positions, 3).setUsage(THREE.DynamicDrawUsage));
    this.lines = new THREE.LineSegments(
      geometry,
      new THREE.LineBasicMaterial({ color: 0xc9d4dc, transparent: true, opacity: 0.55 }),
    );
    this.lines.frustumCulled = false;
    this.wind = wind;
    group.add(this.lines);
  }

  update(center, dt) {
    const { drops, positions, wind } = this;
    for (let i = 0; i < drops.length / 3; i++) {
      drops[i * 3 + 1] -= dt * 14;
      drops[i * 3] += dt * wind.x * 0.4;
      drops[i * 3 + 2] += dt * wind.z * 0.4;
      if (drops[i * 3 + 1] < 0) drops[i * 3 + 1] += 18;
      const x = center.x + (((drops[i * 3] % 50) + 75) % 50) - 25;
      const z = center.z + (((drops[i * 3 + 2] % 50) + 75) % 50) - 25;
      const y = drops[i * 3 + 1];
      positions.set([x, y, z, x - wind.x * 0.03, y + 0.5, z - wind.z * 0.03], i * 6);
    }
    this.lines.geometry.attributes.position.needsUpdate = true;
  }
}

// Le décor entier. `options` : les noms et couleurs des clubs, leurs sponsors (images
// des logos), le temps et l'heure du match.
export function buildField(scene, options) {
  const { homeName, homeColors, awayColors, homeInk, accent, logos, weather, evening } = options;
  const group = new THREE.Group();
  scene.add(group);

  // Ciel et lumière : soleil de l'après-midi, soir aux projecteurs, gris de pluie,
  // chaleur dorée.
  const sky = evening ? 0x14203a : weather === "rain" ? 0x8e9aa4 : weather === "heat" ? 0xd8d2b8 : 0xa9c3da;
  scene.background = new THREE.Color(sky);
  scene.fog = new THREE.Fog(sky, evening ? 90 : 120, evening ? 220 : 320);
  const hemi = new THREE.HemisphereLight(evening ? 0x40507a : 0xdfe9f2, 0x2e4a38, evening ? 0.9 : 1.3);
  const sun = new THREE.DirectionalLight(
    evening ? 0xeef2ff : weather === "heat" ? 0xffe2b0 : weather === "rain" ? 0xd8dde2 : 0xfff2dc,
    evening ? 1.6 : weather === "rain" ? 1.3 : 2.4,
  );
  sun.position.set(-40, 60, 30);
  group.add(hemi, sun);
  if (evening) {
    const second = new THREE.DirectionalLight(0xeef2ff, 1.1);
    second.position.set(50, 55, -40);
    group.add(second);
  }

  // Pelouse : bandes de 5 m parallèles à la ligne d'essai, sur un tapis plus large.
  const grass = grassCanvas();
  const light = lambert(0xd9e6cf, { map: texture(grass, [16, 1]) });
  const dark = lambert(0xa9bd9d, { map: texture(grass, [16, 1]) });
  const bandGeometry = new THREE.PlaneGeometry(80, 5).rotateX(-Math.PI / 2);
  for (let i = 0; i < 25; i++) {
    const band = new THREE.Mesh(bandGeometry, i % 2 ? dark : light);
    band.position.set(0, 0, -15 + 2.5 + i * 5);
    group.add(band);
  }
  const surround = new THREE.Mesh(
    new THREE.PlaneGeometry(260, 260).rotateX(-Math.PI / 2),
    lambert(0x9fb294, { map: texture(grass, [60, 60]) }),
  );
  surround.position.set(0, -0.02, 40);
  group.add(surround);
  group.add(new THREE.Mesh(linesGeometry(), lambert(0xf2f2ec, { polygonOffset: true, polygonOffsetFactor: -2 })));

  // Poteaux en H : montants, barre, protections, fanions.
  const white = lambert(0xf6f6f2);
  const pad = lambert(0xffffff, { map: texture(padCanvas(homeColors[0], homeInk, homeName)) });
  const flagMaterial = lambert(homeColors[0], { side: THREE.DoubleSide });
  const flagGeometry = new THREE.ShapeGeometry(
    new THREE.Shape([new THREE.Vector2(0, 0), new THREE.Vector2(1, 0.22), new THREE.Vector2(0, 0.45)]),
  ).translate(0, -0.45, 0);
  const flags = [];
  for (const side of [-1, 1]) {
    const x = side * (GAP + POST_R);
    const upright = new THREE.Mesh(new THREE.CylinderGeometry(POST_R * 1.6, POST_R * 1.6, POST_HEIGHT, 6), white);
    upright.position.set(x, POST_HEIGHT / 2, 0);
    const padMesh = new THREE.Mesh(new THREE.CylinderGeometry(PAD_R, PAD_R, PAD_H, 10), pad);
    padMesh.position.set(x, PAD_H / 2, 0);
    const flag = new THREE.Mesh(flagGeometry, flagMaterial);
    flag.position.set(x, POST_HEIGHT, 0);
    flags.push(flag);
    group.add(upright, padMesh, flag);
  }
  const crossbar = new THREE.Mesh(new THREE.CylinderGeometry(POST_R * 1.6, POST_R * 1.6, 2 * (GAP + POST_R), 6), white);
  crossbar.rotation.z = Math.PI / 2;
  crossbar.position.set(0, BAR - POST_R, 0);
  group.add(crossbar);
  // Piquets de coin et de ligne d'essai, eux aussi au vent.
  const stickGeometry = new THREE.CylinderGeometry(0.03, 0.03, 1.5, 4).translate(0, 0.75, 0);
  const cornerFlag = lambert(homeColors[1] ?? homeColors[0], { side: THREE.DoubleSide });
  const smallFlag = new THREE.PlaneGeometry(0.4, 0.3).translate(0.2, 1.35, 0);
  for (const x of [-TOUCH, TOUCH]) {
    for (const z of [DEAD_BALL, 0, 22, 78, FAR_LINE]) {
      const stick = new THREE.Mesh(stickGeometry, white);
      stick.position.set(x, 0, z);
      const flag = new THREE.Mesh(smallFlag, cornerFlag);
      flag.position.set(x, 0, z);
      flags.push(flag);
      group.add(stick, flag);
    }
  }

  // Panneaux publicitaires le long de la touche d'en face et derrière l'en-but.
  const boardMap = texture(boardCanvas(homeName, logos, accent), [1, 1]);
  const boardMaterial = new THREE.MeshLambertMaterial({ map: boardMap, emissive: 0xffffff, emissiveMap: boardMap, emissiveIntensity: evening ? 0.9 : 0.35 });
  const boards = [
    [112, TOUCH + 4, 46, -Math.PI / 2, 11],
    [76, 0, DEAD_BALL - 3, 0, 8],
  ];
  for (const [length, x, z, turn, repeat] of boards) {
    const geometry = new THREE.BoxGeometry(length, 0.9, 0.15);
    const uv = geometry.attributes.uv;
    for (let i = 0; i < uv.count; i++) uv.setX(i, uv.getX(i) * repeat);
    const board = new THREE.Mesh(geometry, boardMaterial);
    board.position.set(x, 0.45, z);
    board.rotation.y = turn;
    group.add(board);
  }
  const repaint = (nextLogos) => {
    boardMap.image = boardCanvas(homeName, nextLogos, accent);
    boardMap.needsUpdate = true;
  };

  // Tribunes basses : huit marches de béton, un toit léger, et le public. Une tribune
  // est dessinée face à +z, son pied en z = 0, puis tournée et placée.
  const concrete = lambert(0x6a6d72);
  const roof = lambert(0x2a2d32);
  const seats = [];
  const stand = (length, x, z, turn, awayFrom = null) => {
    const rows = 7;
    const g = new THREE.Group();
    for (let r = 0; r < rows; r++) {
      const step = new THREE.Mesh(new THREE.BoxGeometry(length, 0.5 + r * 0.55, 0.9), concrete);
      step.position.set(0, (0.5 + r * 0.55) / 2 + 0.6, -r * 0.9 - 0.45);
      g.add(step);
    }
    const wall = new THREE.Mesh(new THREE.BoxGeometry(length, 1.1, 0.25), concrete);
    wall.position.set(0, 0.55, 0.1);
    const top = new THREE.Mesh(new THREE.BoxGeometry(length, 0.25, rows * 0.9 + 1.5), roof);
    top.position.set(0, 0.6 + rows * 0.55 + 3.4, -rows * 0.45);
    const back = new THREE.Mesh(new THREE.BoxGeometry(length, 0.6 + rows * 0.55 + 3.4, 0.3), roof);
    back.position.set(0, (0.6 + rows * 0.55 + 3.4) / 2, -rows * 0.9 - 0.15);
    g.add(wall, top, back);
    g.rotation.y = turn;
    g.position.set(x, 0, z);
    group.add(g);
    // Les places, en coordonnées du terrain.
    const c = Math.cos(turn);
    const s = Math.sin(turn);
    for (let r = 0; r < rows; r++) {
      for (let u = -length / 2 + 0.6; u < length / 2 - 0.6; u += 1.3) {
        if (Math.random() < 0.18) continue;
        const lx = u + (Math.random() - 0.5) * 0.3;
        const lz = -r * 0.9 - 0.45;
        seats.push({
          x: x + lx * c + lz * s,
          z: z - lx * s + lz * c,
          y: 0.6 + 0.5 + r * 0.55,
          turn,
          away: awayFrom !== null && lx > awayFrom,
        });
      }
    }
  };
  stand(116, TOUCH + 7, 46, -Math.PI / 2);
  stand(70, 0, DEAD_BALL - 6, 0, 22);
  const crowd = new Crowd(group, seats, {
    homeColors,
    awayColors,
    skins: ["#E8C4A8", "#D6A585", "#B9825C", "#8A5A3C", "#F0D2BC"],
  });

  // Projecteurs le soir : quatre pylônes aux coins, leurs rampes allumées.
  if (evening) {
    const mast = lambert(0x3a3d42);
    const lamp = new THREE.MeshBasicMaterial({ color: 0xfff6d8 });
    for (const [x, z] of [
      [TOUCH + 16, -14],
      [TOUCH + 16, 96],
      [-TOUCH - 16, -14],
      [-TOUCH - 16, 96],
    ]) {
      const pole = new THREE.Mesh(new THREE.BoxGeometry(0.6, 34, 0.6), mast);
      pole.position.set(x, 17, z);
      const head = new THREE.Mesh(new THREE.BoxGeometry(4, 2.4, 0.4), lamp);
      head.position.set(x, 34.5, z);
      head.lookAt(0, 0, 25);
      group.add(pole, head);
    }
  }

  const windSpeed = weather === "wind" ? 9 : weather === "rain" ? 4 : 1.5;
  const wind = new THREE.Vector3(Math.cos(0.7) * windSpeed, 0, Math.sin(0.7) * windSpeed);
  const rain = weather === "rain" ? new Rain(group, wind) : null;

  return {
    crowd,
    wind,
    repaint,
    update(time, dt, focus) {
      crowd.update(time, dt);
      rain?.update(focus, dt);
      flags.forEach((flag, index) => {
        const gust = wind.length();
        flag.rotation.y = Math.atan2(-wind.z, wind.x) + Math.sin(time * (3 + gust * 0.6) + index) * (0.1 + gust * 0.02);
        flag.scale.x = 0.55 + Math.min(0.45, gust / 12) + Math.sin(time * 9 + index) * 0.04;
      });
    },
  };
}
