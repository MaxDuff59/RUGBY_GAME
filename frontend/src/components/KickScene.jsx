import { useEffect, useRef, useState } from "react";
import * as THREE from "three";
import { Sky } from "three/addons/objects/Sky.js";
import { mergeGeometries } from "three/addons/utils/BufferGeometryUtils.js";

// Coup de pied au but, vu par le buteur (page de connexion, sur ordinateur). Le ballon
// est posé sur son tee, les poteaux en face, au fond d'un stade. On vise à la souris
// (la ligne sur la pelouse), on maintient le clic pour doser la frappe, on relâche :
// élan de la caméra, puis le ballon part en culbutant, freiné par l'air et poussé par
// le vent (fanions en haut des poteaux, indication à l'écran), rebondit sur les
// montants et la barre, puis rebondit de travers sur l'herbe. Réussi s'il passe
// au-dessus de la barre entre les poteaux. Chaque réussite éloigne le tir suivant.
//
// Repère : x vers la droite, y en haut ; la ligne d'essai est en z = 0 et le terrain
// s'étend vers +z, du côté du buteur. Les longueurs sont en mètres.

const GAP = 2.8; // demi-écart intérieur des poteaux (5,6 m)
const BAR = 3; // dessus de la barre
const POST_HEIGHT = 16;
const POST_R = 0.065;
const PAD_R = 0.3;
const PAD_H = 2;

const BALL_A = 0.15; // demi-longueur du ballon
const BALL_B = 0.095; // demi-largeur
const BALL_R = 0.12; // rayon retenu pour les chocs
const TEE_TOP = 0.062;
const TILT = 0.2; // le ballon penche vers les poteaux sur son tee

const G = 9.81;
const DRAG = 0.012; // ½ ρ Cx S / m : un ballon frappé à 33 m/s retombe vers 55 m
const ELEVATION = THREE.MathUtils.degToRad(33);
const SPEED_MIN = 14;
const SPEED_MAX = 33;
const OVERHIT = 0.92; // au-delà, la frappe perd en précision
const CHARGE_PERIOD = 2.2; // aller-retour de la jauge (s)
const RUNUP = 0.45; // élan avant l'impact (s)
const STEP = 1 / 240;

const FOV = 50;
const EYE = 1.6;
const BACK = 2.7;
const PITCH_DOWN = 0.2;
const SUN = new THREE.Vector3(-0.55, 0.62, -0.56).normalize();

const UP = new THREE.Vector3(0, 1, 0);

// Tir suivant : le premier en face à 22 m sans vent, puis de plus en plus loin, de
// plus en plus excentré et venté à mesure des réussites.
function nextSpot(level) {
  if (level < 0) return { x: 0, z: 25, kind: "Pénalité", wind: new THREE.Vector3(0.8, 0, 0.3) };
  const reach = Math.min(level, 6);
  const z = 18 + reach * 3.5 + Math.random() * 8;
  const x = (Math.random() * 2 - 1) * Math.min(32, 6 + reach * 4.5);
  const speed = Math.random() * (2 + reach);
  const angle = Math.random() * Math.PI * 2;
  return {
    x,
    z,
    kind: Math.random() < 0.5 ? "Transformation" : "Pénalité",
    wind: new THREE.Vector3(Math.cos(angle) * speed, 0, Math.sin(angle) * speed),
  };
}

function gaussian() {
  return Math.sqrt(-2 * Math.log(1 - Math.random())) * Math.cos(2 * Math.PI * Math.random());
}

const canvasOf = (width, height) => Object.assign(document.createElement("canvas"), { width, height });

// Herbe en carreau raccordable : des brins courts de verts variés.
function grassCanvas() {
  const size = 512;
  const canvas = canvasOf(size, size);
  const ctx = canvas.getContext("2d");
  ctx.fillStyle = "#4d7a37";
  ctx.fillRect(0, 0, size, size);
  ctx.lineCap = "round";
  for (let i = 0; i < 14000; i++) {
    const x = Math.random() * size;
    const y = Math.random() * size;
    const angle = Math.random() * Math.PI * 2;
    const length = 2 + Math.random() * 6;
    const light = 30 + Math.random() * 22;
    ctx.strokeStyle = `hsl(${92 + Math.random() * 18}, ${38 + Math.random() * 18}%, ${light}%)`;
    ctx.lineWidth = 0.8 + Math.random() * 1.2;
    const dx = Math.cos(angle) * length;
    const dy = Math.sin(angle) * length;
    for (const ox of [-size, 0, size]) {
      for (const oy of [-size, 0, size]) {
        if (x + ox < -8 || x + ox > size + 8 || y + oy < -8 || y + oy > size + 8) continue;
        ctx.beginPath();
        ctx.moveTo(x + ox, y + oy);
        ctx.lineTo(x + ox + dx, y + oy + dy);
        ctx.stroke();
      }
    }
  }
  return canvas;
}

// Tribune vue de loin : marches de béton, sièges, spectateurs habillés surtout aux
// couleurs du club ; le haut, sous le toit, plus sombre.
function crowdCanvas() {
  const cols = 96;
  const rows = 32;
  const cw = 21;
  const rh = 32;
  const canvas = canvasOf(cols * cw, rows * rh);
  const ctx = canvas.getContext("2d");
  ctx.fillStyle = "#34363b";
  ctx.fillRect(0, 0, canvas.width, canvas.height);
  const shirts = ["#7a1f2b", "#7a1f2b", "#7a1f2b", "#8c2333", "#f1f0ea", "#f1f0ea", "#1d2b45", "#22252a", "#22252a", "#6f737a", "#c8a35c", "#2f5d8a", "#9aa0a8"];
  const skins = ["#e8c4a8", "#d6a585", "#b9825c", "#8a5a3c", "#f0d2bc"];
  const hair = ["#2a211b", "#4a3426", "#1b1b1b", "#8a6a45", "#bcb6aa"];
  const pick = (list) => list[Math.floor(Math.random() * list.length)];
  for (let r = 0; r < rows; r++) {
    const y = r * rh;
    // Marche de béton, puis la rangée de sièges.
    ctx.fillStyle = "#45474d";
    ctx.fillRect(0, y + rh - 6, canvas.width, 6);
    ctx.fillStyle = "#5c2229";
    ctx.fillRect(0, y + rh - 12, canvas.width, 6);
    for (let c = 0; c < cols; c++) {
      if (Math.random() < 0.1) continue;
      const x = c * cw + cw / 2 + (Math.random() - 0.5) * 5;
      const standing = Math.random() < 0.08 ? -5 : 0;
      const top = y + 11 + standing + (Math.random() - 0.5) * 3;
      const width = 12 + Math.random() * 5;
      ctx.fillStyle = pick(shirts);
      ctx.beginPath();
      ctx.roundRect(x - width / 2, top + 5, width, rh - 13 - standing, [6, 6, 1, 1]);
      ctx.fill();
      ctx.fillStyle = pick(skins);
      ctx.beginPath();
      ctx.arc(x, top, 4.6 + Math.random() * 0.8, 0, Math.PI * 2);
      ctx.fill();
      ctx.fillStyle = pick(hair);
      ctx.beginPath();
      ctx.arc(x, top - 1.5, 4.4, Math.PI, 0);
      ctx.fill();
      // Quelques bras levés, une écharpe.
      if (Math.random() < 0.06) {
        ctx.fillStyle = pick(skins);
        ctx.fillRect(x + width / 2 - 3, top - 10, 3, 14);
      }
    }
  }
  const shade = ctx.createLinearGradient(0, 0, 0, canvas.height);
  shade.addColorStop(0, "rgba(0,0,0,0.5)");
  shade.addColorStop(0.5, "rgba(0,0,0,0.12)");
  shade.addColorStop(1, "rgba(0,0,0,0)");
  ctx.fillStyle = shade;
  ctx.fillRect(0, 0, canvas.width, canvas.height);
  return canvas;
}

// Panneaux publicitaires lumineux autour du terrain.
function boardCanvas() {
  const canvas = canvasOf(1024, 64);
  const ctx = canvas.getContext("2d");
  ctx.fillStyle = "#14203a";
  ctx.fillRect(0, 0, 1024, 64);
  ctx.font = '700 44px "Barlow Condensed", "Arial Narrow", sans-serif';
  ctx.textBaseline = "middle";
  ctx.textAlign = "center";
  ["RUGBY MANAGER", "RUGBY MANAGER"].forEach((text, index) => {
    const x = 256 + index * 512;
    ctx.fillStyle = "#7a1f2b";
    ctx.fillRect(x - 256, 0, 10, 64);
    ctx.fillStyle = "#f4f2ec";
    ctx.fillText(text, x, 34);
  });
  return canvas;
}

// Protection des poteaux : mousse bordeaux, nom du jeu en blanc.
function padCanvas() {
  const canvas = canvasOf(512, 256);
  const ctx = canvas.getContext("2d");
  ctx.fillStyle = "#7a1f2b";
  ctx.fillRect(0, 0, 512, 256);
  ctx.font = '700 46px "Barlow Condensed", "Arial Narrow", sans-serif';
  ctx.fillStyle = "#f4f2ec";
  ctx.textAlign = "center";
  ctx.textBaseline = "middle";
  for (const x of [128, 384]) {
    ctx.save();
    ctx.translate(x, 128);
    ctx.rotate(-Math.PI / 2);
    ctx.fillText("RUGBY MANAGER", 0, 0);
    ctx.restore();
  }
  return canvas;
}

// Cuir du ballon, déplié (largeur : le tour du ballon, hauteur : d'une pointe à
// l'autre) : quatre panneaux cousus et, sur chacun, une vague bleu nuit liserée d'or
// qui s'effile vers les pointes. Le relief (picots, coutures creusées) à part.
function ballCanvases() {
  const width = 1024;
  const height = 512;
  const color = canvasOf(width, height);
  const bump = canvasOf(width, height);
  const ctx = color.getContext("2d");
  const relief = bump.getContext("2d");
  ctx.fillStyle = "#f1ede3";
  ctx.fillRect(0, 0, width, height);
  relief.fillStyle = "#808080";
  relief.fillRect(0, 0, width, height);

  const panel = width / 4;
  for (let p = 0; p < 4; p++) {
    for (let y = 0; y < height; y++) {
      const s = (y / (height - 1)) * 2 - 1;
      const half = 24 * (1 - (s / 0.8) ** 4);
      if (half <= 0) continue;
      const center = p * panel + panel / 2 + Math.sin(s * 3.2 + p * 1.9) * 46;
      if (p & 1) {
        ctx.fillStyle = "#c8a35c";
        ctx.fillRect(center - half * 0.55, y, half * 1.1, 1);
      } else {
        ctx.fillStyle = "#c8a35c";
        ctx.fillRect(center - half - 5, y, half * 2 + 10, 1);
        ctx.fillStyle = "#1d2b45";
        ctx.fillRect(center - half, y, half * 2, 1);
      }
    }
  }
  relief.fillStyle = "#a6a6a6";
  for (let y = 4; y < height; y += 9) {
    for (let x = (y % 18 === 4 ? 0 : 4.5); x < width; x += 9) {
      relief.beginPath();
      relief.arc(x, y, 2.2, 0, Math.PI * 2);
      relief.fill();
    }
  }
  for (let p = 0; p <= 4; p++) {
    const x = p * panel;
    ctx.fillStyle = "#5c5954";
    ctx.fillRect(x - 2, 0, 4, height);
    relief.fillStyle = "#2a2a2a";
    relief.fillRect(x - 4, 0, 8, height);
  }
  return { color, bump };
}

// Ballon : une sphère étirée, aux pointes plus effilées qu'un ellipsoïde ; normales
// calculées d'après la forme exacte (celles d'un maillage seraient fausses aux pointes).
function ballGeometry() {
  const E = 0.68;
  const geometry = new THREE.SphereGeometry(1, 72, 48);
  const position = geometry.attributes.position;
  const normal = geometry.attributes.normal;
  for (let i = 0; i < position.count; i++) {
    const y = position.getY(i);
    const ring = Math.sqrt(Math.max(0, 1 - y * y));
    const cos = ring > 1e-6 ? position.getX(i) / ring : 0;
    const sin = ring > 1e-6 ? position.getZ(i) / ring : 0;
    const base = Math.max(0, 1 - y * y);
    const rho = base ** E;
    position.setXYZ(i, cos * rho * BALL_B, y * BALL_A, sin * rho * BALL_B);
    if (base < 1e-6) {
      normal.setXYZ(i, 0, Math.sign(y), 0);
    } else {
      const slope = -2 * E * y * base ** (E - 1);
      const n = new THREE.Vector3(cos * BALL_A, -slope * BALL_B, sin * BALL_A).normalize();
      normal.setXYZ(i, n.x, n.y, n.z);
    }
  }
  return geometry;
}

// Tee de buteur en plastique : un socle évasé, une coupelle où se pose la pointe.
function teeGeometry() {
  const profile = [
    [0, 0],
    [0.075, 0],
    [0.076, 0.006],
    [0.056, 0.012],
    [0.031, 0.045],
    [0.035, 0.06],
    [0.045, 0.069],
    [0.041, 0.072],
    [0.026, 0.064],
    [0, TEE_TOP],
  ].map(([x, y]) => new THREE.Vector2(x, y));
  return new THREE.LatheGeometry(profile, 40);
}

// Lignes blanches du terrain, fusionnées en un seul maillage posé sur l'herbe.
function linesGeometry() {
  const parts = [];
  const strip = (x1, z1, x2, z2, width = 0.1) => {
    const length = Math.hypot(x2 - x1, z2 - z1);
    const geometry = new THREE.PlaneGeometry(width, length);
    geometry.rotateX(-Math.PI / 2);
    geometry.rotateY(Math.atan2(x2 - x1, z2 - z1));
    geometry.translate((x1 + x2) / 2, 0.004, (z1 + z2) / 2);
    parts.push(geometry);
  };
  const dashedX = (z, from, to, dash, gap) => {
    for (let x = from; x < to; x += dash + gap) strip(x, z, Math.min(x + dash, to), z);
  };
  strip(-35, -10, 35, -10); // ballon mort
  strip(-35, 0, 35, 0); // essai
  strip(-35, 22, 35, 22);
  strip(-35, 50, 35, 50); // milieu
  strip(-35, -10, -35, 120);
  strip(35, -10, 35, 120);
  dashedX(5, -35, 35, 1, 2); // 5 m
  dashedX(40, -35, 35, 1, 2); // 10 m
  for (const x of [-30, -20, 20, 30]) {
    for (let z = 2; z < 120; z += 5) strip(x, z, x, z + 1); // 5 m et 15 m des touches
  }
  return mergeGeometries(parts);
}

export default function KickScene({ aside, onFail }) {
  const frame = useRef(null);
  const fail = useRef(onFail);
  fail.current = onFail;
  const powerFill = useRef(null);
  const fade = useRef(null);
  const [free, setFree] = useState(0);
  const [hud, setHud] = useState(null);
  const [charging, setCharging] = useState(false);
  const [result, setResult] = useState(null);
  const [score, setScore] = useState({ made: 0, taken: 0 });
  const [hint, setHint] = useState(true);

  useEffect(() => {
    const element = frame.current;
    let renderer;
    try {
      renderer = new THREE.WebGLRenderer({ antialias: true });
    } catch {
      fail.current?.();
      return undefined;
    }
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    renderer.outputColorSpace = THREE.SRGBColorSpace;
    renderer.toneMapping = THREE.ACESFilmicToneMapping;
    renderer.toneMappingExposure = 0.8;
    renderer.shadowMap.enabled = true;
    renderer.shadowMap.type = THREE.PCFShadowMap;
    element.prepend(renderer.domElement);
    const still = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

    const scene = new THREE.Scene();
    scene.fog = new THREE.Fog(0xb9c8d4, 160, 700);
    const camera = new THREE.PerspectiveCamera(FOV, 1, 0.05, 2000);

    // Ciel (diffusion de l'atmosphère, quelques nuages) ; il éclaire aussi la scène.
    const sky = new Sky();
    sky.scale.setScalar(1000);
    const skyUniforms = sky.material.uniforms;
    skyUniforms.turbidity.value = 4;
    skyUniforms.rayleigh.value = 1.4;
    skyUniforms.mieCoefficient.value = 0.004;
    skyUniforms.mieDirectionalG.value = 0.82;
    skyUniforms.cloudCoverage.value = 0.32;
    skyUniforms.sunPosition.value.copy(SUN);
    const pmrem = new THREE.PMREMGenerator(renderer);
    const skyScene = new THREE.Scene();
    skyScene.add(sky);
    scene.environment = pmrem.fromScene(skyScene).texture;
    scene.environmentIntensity = 0.55;
    pmrem.dispose();
    scene.add(sky);

    const sun = new THREE.DirectionalLight(0xfff0dc, 3.2);
    sun.castShadow = true;
    sun.shadow.mapSize.set(4096, 4096);
    sun.shadow.camera.near = 1;
    sun.shadow.camera.far = 260;
    sun.shadow.bias = -0.0002;
    sun.shadow.normalBias = 0.03;
    scene.add(sun, sun.target);
    scene.add(new THREE.HemisphereLight(0xcfe0f0, 0x3d5a2c, 0.5));

    const anisotropy = renderer.capabilities.getMaxAnisotropy();
    const textureOf = (canvas, { repeat = [1, 1], color = true } = {}) => {
      const texture = new THREE.CanvasTexture(canvas);
      if (color) texture.colorSpace = THREE.SRGBColorSpace;
      texture.wrapS = texture.wrapT = THREE.RepeatWrapping;
      texture.repeat.set(...repeat);
      texture.anisotropy = anisotropy;
      return texture;
    };

    // Pelouse : bandes de tonte de 5 m parallèles à la ligne d'essai, sur un tapis
    // d'herbe plus large qui file sous les tribunes.
    const grass = grassCanvas();
    const bandTexture = textureOf(grass, { repeat: [40, 2.5] });
    const lightBand = new THREE.MeshStandardMaterial({ map: bandTexture, roughness: 0.95, color: 0xdde8d4 });
    const darkBand = new THREE.MeshStandardMaterial({ map: bandTexture, roughness: 0.95, color: 0xb0c2a4 });
    const bandGeometry = new THREE.PlaneGeometry(84, 5);
    bandGeometry.rotateX(-Math.PI / 2);
    for (let i = 0; i < 28; i++) {
      const band = new THREE.Mesh(bandGeometry, i % 2 ? darkBand : lightBand);
      band.position.set(0, 0, -15 + 2.5 + i * 5);
      band.receiveShadow = true;
      scene.add(band);
    }
    const surround = new THREE.Mesh(
      new THREE.PlaneGeometry(400, 400),
      new THREE.MeshStandardMaterial({
        map: textureOf(grass, { repeat: [160, 160] }),
        roughness: 1,
        color: 0xa9b8a0,
      }),
    );
    surround.rotation.x = -Math.PI / 2;
    surround.position.set(0, -0.01, 60);
    surround.receiveShadow = true;
    scene.add(surround);
    const lines = new THREE.Mesh(
      linesGeometry(),
      new THREE.MeshStandardMaterial({
        color: 0xf2f2ec,
        roughness: 0.9,
        polygonOffset: true,
        polygonOffsetFactor: -2,
      }),
    );
    lines.receiveShadow = true;
    scene.add(lines);

    // Poteaux : montants, barre, protections, fanions au sommet.
    const white = new THREE.MeshStandardMaterial({ color: 0xf6f6f2, roughness: 0.35 });
    const padMaterial = new THREE.MeshStandardMaterial({ map: textureOf(padCanvas()), roughness: 0.8 });
    const flagMaterial = new THREE.MeshStandardMaterial({ color: 0x7a1f2b, roughness: 0.8, side: THREE.DoubleSide });
    const flagShape = new THREE.Shape([new THREE.Vector2(0, 0), new THREE.Vector2(1, 0.22), new THREE.Vector2(0, 0.45)]);
    const flagGeometry = new THREE.ShapeGeometry(flagShape);
    flagGeometry.translate(0, -0.45, 0);
    const flags = [];
    for (const side of [-1, 1]) {
      const x = side * (GAP + POST_R);
      const upright = new THREE.Mesh(new THREE.CylinderGeometry(POST_R, POST_R, POST_HEIGHT, 20), white);
      upright.position.set(x, POST_HEIGHT / 2, 0);
      const pad = new THREE.Mesh(new THREE.CylinderGeometry(PAD_R, PAD_R, PAD_H, 40), padMaterial);
      pad.position.set(x, PAD_H / 2, 0);
      const flag = new THREE.Mesh(flagGeometry, flagMaterial);
      flag.position.set(x, POST_HEIGHT, 0);
      flags.push(flag);
      for (const mesh of [upright, pad, flag]) mesh.castShadow = true;
      scene.add(upright, pad, flag);
    }
    const crossbar = new THREE.Mesh(new THREE.CylinderGeometry(POST_R, POST_R, 2 * (GAP + POST_R), 20), white);
    crossbar.rotation.z = Math.PI / 2;
    crossbar.position.set(0, BAR - POST_R, 0);
    crossbar.castShadow = true;
    scene.add(crossbar);

    // Stade : panneaux lumineux, tribunes garnies sous leur toit, en fond et sur les côtés.
    const board = textureOf(boardCanvas());
    const boardMaterial = new THREE.MeshStandardMaterial({
      map: board,
      emissive: 0xffffff,
      emissiveMap: board,
      emissiveIntensity: 0.55,
      roughness: 0.6,
    });
    const crowd = crowdCanvas();
    const concrete = new THREE.MeshStandardMaterial({ color: 0x55585e, roughness: 1 });
    // Sous le toit, tout est dans l'ombre.
    const shadowed = new THREE.MeshStandardMaterial({ color: 0x17191d, roughness: 1, envMapIntensity: 0.2 });
    const roofMaterial = new THREE.MeshStandardMaterial({ color: 0x0e0f12, roughness: 1, envMapIntensity: 0.1 });
    const stands = new THREE.Group();
    // Une tribune vue de face, son pied en z = 0 et qui monte vers -z, longue de `length`
    // (selon x), puis tournée et placée.
    const stand = (length, x, z, turn) => {
      const group = new THREE.Group();
      const depth = 27;
      const rise = 22;
      const slope = Math.hypot(depth, rise);
      const seats = new THREE.Mesh(
        new THREE.PlaneGeometry(length, slope),
        new THREE.MeshStandardMaterial({
          map: textureOf(crowd, { repeat: [length / 48, slope / 25.6] }),
          roughness: 1,
          color: 0x8a8a8a,
        }),
      );
      seats.rotation.x = -Math.atan2(depth, rise);
      seats.position.set(0, 1.8 + rise / 2, -depth / 2);
      const wall = new THREE.Mesh(new THREE.BoxGeometry(length, 1.8, 0.4), concrete);
      wall.position.set(0, 0.9, 0);
      const back = new THREE.Mesh(new THREE.BoxGeometry(length, 30, 0.5), shadowed);
      back.position.set(0, 15, -depth - 0.5);
      const roof = new THREE.Mesh(new THREE.BoxGeometry(length, 0.8, depth + 8), roofMaterial);
      roof.position.set(0, rise + 7, -depth / 2 + 4);
      const fascia = new THREE.Mesh(new THREE.BoxGeometry(length, 2.2, 0.3), white);
      fascia.position.set(0, rise + 6.4, 8.1);
      group.add(seats, wall, back, roof, fascia);
      group.rotation.y = turn;
      group.position.set(x, 0, z);
      stands.add(group);
    };
    stand(140, 0, -20, 0);
    stand(160, -47, 50, Math.PI / 2);
    stand(160, 47, 50, -Math.PI / 2);
    stand(140, 0, 128, Math.PI);
    for (const [length, x, z, turn] of [
      [84, 0, -14, 0],
      [130, -40, 51, Math.PI / 2],
      [130, 40, 51, -Math.PI / 2],
    ]) {
      const boards = new THREE.Mesh(new THREE.BoxGeometry(length, 0.9, 0.12), boardMaterial);
      boards.geometry.attributes.uv.array.forEach((value, index, array) => {
        if (index % 2 === 0) array[index] = value * (length / 12);
      });
      boards.position.set(x, 0.45, z);
      boards.rotation.y = turn;
      boards.castShadow = true;
      stands.add(boards);
    }
    scene.add(stands);
    // La police des panneaux arrive après le premier dessin : on les repeint alors.
    document.fonts?.load('700 44px "Barlow Condensed"').then(() => {
      board.image = boardCanvas();
      board.needsUpdate = true;
      padMaterial.map.image = padCanvas();
      padMaterial.map.needsUpdate = true;
    });

    // Tee et ballon.
    const tee = new THREE.Mesh(
      teeGeometry(),
      new THREE.MeshStandardMaterial({ color: 0xf0a020, roughness: 0.45 }),
    );
    tee.castShadow = true;
    tee.receiveShadow = true;
    scene.add(tee);
    const leather = ballCanvases();
    const ball = new THREE.Mesh(
      ballGeometry(),
      new THREE.MeshStandardMaterial({
        map: textureOf(leather.color),
        bumpMap: textureOf(leather.bump, { color: false }),
        bumpScale: 1.2,
        roughness: 0.5,
      }),
    );
    ball.castShadow = true;
    scene.add(ball);

    // Ligne de visée sur la pelouse, en tirets, du ballon à la ligne d'essai.
    const dash = canvasOf(8, 64);
    const dashCtx = dash.getContext("2d");
    dashCtx.fillStyle = "#fff";
    dashCtx.fillRect(0, 0, 8, 36);
    const dashTexture = textureOf(dash);
    const aimGeometry = new THREE.PlaneGeometry(0.06, 1);
    aimGeometry.rotateX(-Math.PI / 2);
    aimGeometry.translate(0, 0.01, -0.5);
    const aimLine = new THREE.Mesh(
      aimGeometry,
      new THREE.MeshBasicMaterial({ map: dashTexture, transparent: true, opacity: 0.6, depthWrite: false }),
    );
    scene.add(aimLine);

    // --- État du jeu ---------------------------------------------------------------
    const game = {
      phase: "aim", // aim | charge | runup | flight | done
      level: -1,
      spot: null,
      facing: new THREE.Vector3(),
      aim: new THREE.Vector3(),
      power: 0,
      chargeAt: 0,
      kickAt: 0,
      launchAt: 0,
      resultAt: 0,
      result: null,
      hit: null, // "poteau" | "barre"
      pos: new THREE.Vector3(),
      vel: new THREE.Vector3(),
      spinAxis: new THREE.Vector3(),
      spin: 0,
      landed: false,
      teePos: new THREE.Vector3(),
      teeVel: new THREE.Vector3(),
      teeFlying: false,
      camRest: new THREE.Vector3(),
      camFrom: new THREE.Vector3(),
      look: new THREE.Vector3(),
      fov: FOV,
      made: 0,
      taken: 0,
    };
    const restLook = () =>
      game.camRest.clone().addScaledVector(game.facing, 10).add(new THREE.Vector3(0, -10 * Math.tan(PITCH_DOWN), 0));

    function placeSpot(spot) {
      game.spot = spot;
      game.facing.set(-spot.x, 0, -spot.z).normalize();
      game.aim.copy(game.facing);
      game.teePos.set(spot.x, 0, spot.z);
      tee.position.copy(game.teePos);
      tee.rotation.set(0, 0, 0);
      game.teeFlying = false;
      const axis = new THREE.Vector3(game.facing.x * Math.sin(TILT), Math.cos(TILT), game.facing.z * Math.sin(TILT));
      game.pos.set(spot.x, TEE_TOP, spot.z).addScaledVector(axis, BALL_A);
      ball.position.copy(game.pos);
      ball.quaternion.setFromUnitVectors(UP, axis);
      game.vel.set(0, 0, 0);
      game.landed = false;
      game.hit = null;
      game.result = null;
      game.camRest.set(spot.x, EYE, spot.z).addScaledVector(game.facing, -BACK);
      camera.position.copy(game.camRest);
      game.look.copy(restLook());
      game.fov = FOV;
      camera.fov = FOV;
      camera.updateProjectionMatrix();
      game.phase = "aim";
      updateAimLine();
      aimLine.visible = true;
      // L'ombre suit le tir : la carte d'ombre couvre le buteur et les poteaux.
      const middle = new THREE.Vector3(spot.x / 2, 0, spot.z / 2);
      const reach = Math.hypot(spot.x, spot.z) / 2 + 22;
      sun.target.position.copy(middle);
      sun.position.copy(middle).addScaledVector(SUN, 120);
      Object.assign(sun.shadow.camera, { left: -reach, right: reach, top: reach, bottom: -reach });
      sun.shadow.camera.updateProjectionMatrix();
      flags.forEach((flag) => (flag.rotation.y = Math.atan2(-spot.wind.z, spot.wind.x)));
      // Vent à l'écran : la flèche pointe vers le haut quand il souffle vers les poteaux.
      const right = new THREE.Vector3(-game.facing.z, 0, game.facing.x);
      setHud({
        kind: spot.kind,
        distance: Math.round(Math.hypot(spot.x, spot.z)),
        wind: Math.round(spot.wind.length() * 3.6),
        windTurn: THREE.MathUtils.radToDeg(Math.atan2(spot.wind.dot(right), spot.wind.dot(game.facing))),
      });
    }

    function updateAimLine() {
      const length = Math.max(1, -game.pos.z / Math.min(-0.05, game.aim.z) - 0.6);
      aimLine.position.copy(game.teePos).addScaledVector(game.aim, 0.6);
      aimLine.rotation.y = Math.atan2(-game.aim.x, -game.aim.z);
      aimLine.scale.set(1, 1, length);
      dashTexture.repeat.set(1, length / 0.7);
    }

    // --- Visée et frappe --------------------------------------------------------------
    const raycaster = new THREE.Raycaster();
    const goalPlane = new THREE.Plane(new THREE.Vector3(0, 0, 1), 0);
    const pointer = new THREE.Vector2();
    const target = new THREE.Vector3();
    const maxTurn = THREE.MathUtils.degToRad(28);

    function aimAt(event) {
      if (game.phase !== "aim" && game.phase !== "charge") return;
      const box = element.getBoundingClientRect();
      pointer.set(((event.clientX - box.left) / box.width) * 2 - 1, -((event.clientY - box.top) / box.height) * 2 + 1);
      raycaster.setFromCamera(pointer, camera);
      if (!raycaster.ray.intersectPlane(goalPlane, target)) return;
      const direction = new THREE.Vector3(target.x - game.pos.x, 0, target.z - game.pos.z).normalize();
      let turn = Math.atan2(
        game.facing.x * direction.z - game.facing.z * direction.x,
        game.facing.x * direction.x + game.facing.z * direction.z,
      );
      turn = Math.max(-maxTurn, Math.min(maxTurn, turn));
      game.aim.copy(game.facing).applyAxisAngle(UP, -turn);
      updateAimLine();
    }

    function onPointerDown(event) {
      if (event.button !== 0 || game.phase !== "aim") return;
      aimAt(event);
      game.phase = "charge";
      game.chargeAt = performance.now() / 1000;
      element.setPointerCapture(event.pointerId);
      setCharging(true);
    }

    function onPointerUp() {
      if (game.phase !== "charge") return;
      game.phase = "runup";
      game.kickAt = performance.now() / 1000;
      game.camFrom.copy(camera.position);
      aimLine.visible = false;
      setCharging(false);
      setHint(false);
    }

    function onPointerCancel() {
      if (game.phase !== "charge") return;
      game.phase = "aim";
      setCharging(false);
    }

    // Garde le curseur dans le champ de saisie quand on clique sur la scène.
    const keepFocus = (event) => event.preventDefault();
    element.addEventListener("pointerdown", onPointerDown);
    element.addEventListener("pointermove", aimAt);
    element.addEventListener("pointerup", onPointerUp);
    element.addEventListener("pointercancel", onPointerCancel);
    element.addEventListener("mousedown", keepFocus);

    function launch() {
      const power = game.power;
      let spread = THREE.MathUtils.degToRad(0.6);
      if (power > OVERHIT) spread += THREE.MathUtils.degToRad(3) * ((power - OVERHIT) / (1 - OVERHIT));
      const direction = game.aim.clone().applyAxisAngle(UP, gaussian() * spread);
      const elevation = ELEVATION + THREE.MathUtils.degToRad(1.2) * gaussian();
      const speed = SPEED_MIN + power * (SPEED_MAX - SPEED_MIN);
      game.vel
        .copy(direction)
        .multiplyScalar(Math.cos(elevation) * speed)
        .addScaledVector(UP, Math.sin(elevation) * speed);
      // Frappé sous son centre, le ballon culbute : le bas part devant.
      game.spinAxis.crossVectors(direction, UP).normalize();
      game.spin = Math.PI * 2 * (5 + 3 * power);
      game.phase = "flight";
      game.launchAt = performance.now() / 1000;
      // Le tee s'envole un peu sous le choc.
      game.teeFlying = true;
      game.teeVel.copy(direction).multiplyScalar(2.2).addScaledVector(UP, 1.4);
    }

    function decide(result, made) {
      if (game.result) return;
      game.result = result;
      game.resultAt = performance.now() / 1000;
      game.made += made ? 1 : 0;
      game.taken += 1;
      setResult({ text: result, made });
      setScore({ made: game.made, taken: game.taken });
    }

    // Choc contre un cylindre vertical (montant, protection) ou contre la barre.
    function bounceOff(nx, ny, nz, depth) {
      const vn = game.vel.x * nx + game.vel.y * ny + game.vel.z * nz;
      game.pos.x += nx * depth;
      game.pos.y += ny * depth;
      game.pos.z += nz * depth;
      if (vn >= 0) return;
      game.vel.x -= 1.5 * vn * nx;
      game.vel.y -= 1.5 * vn * ny;
      game.vel.z -= 1.5 * vn * nz;
      game.vel.multiplyScalar(0.85);
      game.spinAxis.set(Math.random() - 0.5, Math.random() - 0.5, Math.random() - 0.5).normalize();
    }

    function collide() {
      const p = game.pos;
      for (const side of [-1, 1]) {
        const x = side * (GAP + POST_R);
        for (const [radius, top] of [
          [POST_R, POST_HEIGHT],
          [PAD_R, PAD_H],
        ]) {
          if (p.y > top + BALL_R) continue;
          const dx = p.x - x;
          const dz = p.z;
          const distance = Math.hypot(dx, dz);
          const reach = radius + BALL_R;
          if (distance < reach && distance > 0) {
            bounceOff(dx / distance, 0, dz / distance, reach - distance);
            game.hit = "poteau";
          }
        }
      }
      if (Math.abs(p.x) < GAP + POST_R) {
        const dy = p.y - (BAR - POST_R);
        const dz = p.z;
        const distance = Math.hypot(dy, dz);
        const reach = POST_R + BALL_R;
        if (distance < reach && distance > 0) {
          bounceOff(0, dy / distance, dz / distance, reach - distance);
          game.hit = "barre";
        }
      }
    }

    function fly(dt) {
      const wind = game.spot.wind;
      const relative = new THREE.Vector3();
      for (let t = 0; t < dt; t += STEP) {
        const before = game.pos.clone();
        relative.copy(game.vel).sub(wind);
        const drag = DRAG * relative.length();
        game.vel.addScaledVector(relative, -drag * STEP);
        game.vel.y -= G * STEP;
        game.pos.addScaledVector(game.vel, STEP);
        collide();
        // Les panneaux publicitaires renvoient le ballon.
        if (game.pos.y < 0.9 + BALL_R) {
          if (game.pos.z < -14 + BALL_R && game.vel.z < 0) game.vel.z *= -0.3;
          if (Math.abs(game.pos.x) > 40 - BALL_R && game.vel.x * game.pos.x > 0) game.vel.x *= -0.3;
        }
        // La ligne d'essai franchie : au-dessus de la barre et entre les poteaux ?
        if (before.z > 0 && game.pos.z <= 0 && !game.landed) {
          const k = before.z / (before.z - game.pos.z);
          const x = before.x + (game.pos.x - before.x) * k;
          const y = before.y + (game.pos.y - before.y) * k;
          if (Math.abs(x) < GAP && y > BAR) decide(game.hit ? "Poteau rentrant !" : "Entre les perches !", true);
          else if (Math.abs(x) < GAP) decide("Sous la barre", false);
          else if (game.hit === "poteau") decide("Sur le poteau", false);
          else decide(x < 0 ? "À gauche" : "À droite", false);
        }
        // Rebond sur l'herbe, de travers comme un ballon ovale ; posé, il roule.
        if (game.pos.y < BALL_B && game.vel.y < 0) {
          if (!game.landed && game.pos.z > 0) {
            decide(game.hit === "barre" ? "Sur la barre" : game.hit === "poteau" ? "Sur le poteau" : "Trop court", false);
          }
          game.landed = true;
          game.pos.y = BALL_B;
          if (game.vel.y > -1) {
            game.vel.y = 0;
          } else {
            game.vel.y = -game.vel.y * 0.45;
            const turn = (Math.random() - 0.5) * 0.9;
            game.vel.set(
              (game.vel.x * Math.cos(turn) - game.vel.z * Math.sin(turn)) * 0.7,
              game.vel.y,
              (game.vel.x * Math.sin(turn) + game.vel.z * Math.cos(turn)) * 0.7,
            );
            game.spin *= 0.6;
            game.spinAxis.set(Math.random() - 0.5, Math.random() - 0.5, Math.random() - 0.5).normalize();
          }
        }
        if (game.landed && game.pos.y <= BALL_B + 1e-4) {
          game.vel.x *= 1 - 1.2 * STEP;
          game.vel.z *= 1 - 1.2 * STEP;
          game.spin *= 1 - 2 * STEP;
        }
      }
      ball.position.copy(game.pos);
      const turn = new THREE.Quaternion().setFromAxisAngle(game.spinAxis, game.spin * dt);
      ball.quaternion.premultiply(turn);
      // Au sol et presque arrêté, il finit couché.
      if (game.landed && game.vel.lengthSq() < 4) {
        const lying = new THREE.Quaternion().setFromUnitVectors(UP, game.aim.clone());
        ball.quaternion.slerp(lying, Math.min(1, dt * 3));
      }
    }

    function flyTee(dt) {
      if (!game.teeFlying) return;
      game.teeVel.y -= G * dt;
      game.teePos.addScaledVector(game.teeVel, dt);
      tee.rotation.x -= 9 * dt * game.aim.z;
      tee.rotation.z += 9 * dt * game.aim.x;
      if (game.teePos.y <= 0) {
        game.teePos.y = 0;
        game.teeFlying = false;
        tee.rotation.set(Math.PI / 2 * -game.aim.z, 0, (Math.PI / 2) * game.aim.x);
      }
      tee.position.copy(game.teePos);
    }

    // --- Cadrage --------------------------------------------------------------------
    // La scène occupe tout l'écran, mais son centre est celui de la place laissée à
    // gauche de la carte de connexion (décalage de la projection).
    const fit = () => {
      const { width, height } = element.getBoundingClientRect();
      if (!width || !height) return;
      const card = aside?.current?.getBoundingClientRect();
      const room = Math.max(360, Math.min(width, (card?.left ?? width) - 16));
      const shift = width / 2 - room / 2;
      renderer.setSize(width, height);
      camera.aspect = (width + 2 * shift) / height;
      camera.setViewOffset(width + 2 * shift, height, 2 * shift, 0, width, height);
      camera.updateProjectionMatrix();
      setFree(room);
    };
    const observer = new ResizeObserver(fit);
    observer.observe(element);

    placeSpot(nextSpot(-1));
    fit();

    let frameId;
    let last = performance.now() / 1000;
    let fading = false;
    let timer = 0;
    const loop = () => {
      frameId = requestAnimationFrame(loop);
      const now = performance.now() / 1000;
      const dt = Math.min(0.05, now - last);
      last = now;
      skyUniforms.time.value = now;

      if (game.phase === "charge") {
        const t = ((now - game.chargeAt) / CHARGE_PERIOD) % 1;
        game.power = t < 0.5 ? t * 2 : 2 - t * 2;
        if (powerFill.current) {
          powerFill.current.style.transform = `scaleX(${game.power})`;
          powerFill.current.classList.toggle("is-over", game.power > OVERHIT);
        }
      }

      // Élan : deux pas vers le ballon, la tête qui monte et descend, puis l'impact.
      if (game.phase === "runup") {
        const k = Math.min(1, (now - game.kickAt) / RUNUP);
        const ease = k * k;
        camera.position
          .copy(game.camFrom)
          .addScaledVector(game.aim, 1.5 * ease)
          .addScaledVector(UP, -0.12 * ease + Math.abs(Math.sin(k * Math.PI * 2)) * 0.05);
        if (k >= 1) launch();
      }

      if (game.phase === "flight") {
        fly(dt);
        flyTee(dt);
        // La caméra suit le ballon et zoome à mesure qu'il s'éloigne.
        game.look.lerp(game.pos, 1 - Math.exp(-dt * 5));
        const distance = camera.position.distanceTo(game.pos);
        const wanted = still ? FOV : Math.max(16, Math.min(FOV, (FOV * 12) / distance));
        game.fov += (wanted - game.fov) * (1 - Math.exp(-dt * 3));
        camera.fov = game.fov;
        camera.updateProjectionMatrix();
        if (!game.result && now - game.launchAt > 7) decide("Trop court", false);
        if (game.result && now - game.resultAt > 2.6 && !fading) {
          fading = true;
          fade.current?.classList.add("is-on");
          timer = setTimeout(() => {
            game.level = game.made;
            placeSpot(nextSpot(game.level));
            setResult(null);
            fade.current?.classList.remove("is-on");
            fading = false;
          }, 380);
          game.phase = "done";
        }
      } else if (game.phase === "aim" || game.phase === "charge") {
        // Au repos : la respiration du buteur.
        camera.position.copy(game.camRest);
        if (!still) camera.position.y += Math.sin(now * 1.3) * 0.012;
      }

      if (!still) {
        flags.forEach((flag, index) => {
          const gust = game.spot.wind.length();
          flag.rotation.y = Math.atan2(-game.spot.wind.z, game.spot.wind.x) + Math.sin(now * (4 + gust) + index) * 0.18;
          flag.scale.x = 0.6 + Math.min(0.4, gust / 10) + Math.sin(now * 9 + index) * 0.04;
        });
      }

      camera.lookAt(game.look);
      renderer.render(scene, camera);
    };
    loop();

    return () => {
      cancelAnimationFrame(frameId);
      clearTimeout(timer);
      observer.disconnect();
      element.removeEventListener("pointerdown", onPointerDown);
      element.removeEventListener("pointermove", aimAt);
      element.removeEventListener("pointerup", onPointerUp);
      element.removeEventListener("pointercancel", onPointerCancel);
      element.removeEventListener("mousedown", keepFocus);
      const textures = new Set();
      scene.traverse((object) => {
        object.geometry?.dispose();
        const material = object.material;
        if (!material) return;
        for (const key of ["map", "bumpMap", "emissiveMap"]) if (material[key]) textures.add(material[key]);
        material.dispose();
      });
      textures.forEach((texture) => texture.dispose());
      scene.environment.dispose();
      renderer.dispose();
      renderer.domElement.remove();
    };
  }, [aside]);

  return (
    <div className="kick" ref={frame} aria-hidden="true">
      <div className="kick__hud" style={{ width: free || undefined }}>
        {hud && (
          <div className="kick__board">
            <span className="kick__kind">{hud.kind}</span>
            <strong className="kick__distance">{hud.distance} m</strong>
            <span className="kick__line">
              <svg className="kick__arrow" viewBox="0 0 16 16" style={{ transform: `rotate(${hud.windTurn}deg)` }}>
                <path d="M8 1 L13 8 H9.5 V15 H6.5 V8 H3 Z" fill="currentColor" />
              </svg>
              Vent {hud.wind} km/h
            </span>
            <span className="kick__line">
              Réussis {score.made} / {score.taken}
            </span>
          </div>
        )}
        {result && <p className={`kick__result${result.made ? " is-made" : ""}`}>{result.text}</p>}
        <div className={`kick__power${charging ? " is-on" : ""}`}>
          <span className="kick__power-label">Puissance</span>
          <span className="kick__gauge">
            <span className="kick__fill" ref={powerFill} />
            <span className="kick__over" style={{ left: `${OVERHIT * 100}%` }} />
          </span>
        </div>
        {hint && !charging && (
          <p className="kick__hint">Vise à la souris, maintiens le clic pour doser la frappe, relâche pour taper.</p>
        )}
      </div>
      <div className="kick__fade" ref={fade} />
    </div>
  );
}
