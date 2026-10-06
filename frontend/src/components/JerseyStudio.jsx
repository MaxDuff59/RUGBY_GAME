import { useEffect, useMemo, useRef, useState } from "react";
import * as THREE from "three";
import { RoomEnvironment } from "three/addons/environments/RoomEnvironment.js";

import { useLogos } from "../hooks/useLogos.js";
import {
  SHOULDER_LINE,
  TEXTURE_HEIGHT,
  TEXTURE_WIDTH,
  drawLogo,
  loadCrest,
  paintJersey,
  paintMarks,
  sleeveColor,
  sleeveHoops,
} from "../jersey.js";
import { placedLogos } from "../sponsors.js";

// Maillot en 3D (three.js, chargé seulement à l'ouverture de l'éditeur). Le torse, les
// manches et le col sont des tubes à section elliptique construits rangée par rangée,
// avec quelques plis ; le torse porte le canevas déroulé de jersey.js (devant à gauche,
// dos à droite), complété ici d'une patte de boutonnage et des coutures. Le tissu est
// une maille (relief procédural), plus brillante là où sont imprimés blason, logos des
// sponsors (`deals`, `library` : src/sponsors.js) et numéro. L'éclairage vient d'une pièce virtuelle (RoomEnvironment) et d'une lampe qui
// porte l'ombre des manches sur le torse et celle du maillot au sol. On glisse pour le
// tourner ; « Face » et « Dos » le ramènent de face ou de dos.

const FRONT_YAW = -0.42; // un peu de trois quarts, pour voir le volume
const BACK_YAW = Math.PI + 0.42;
const TILT = 0.12;
const SLEEVE_WIDTH = 256;
const SLEEVE_HEIGHT = 128;
// Hauteur (de 0, en bas, à 1, au col) où s'arrête la patte de boutonnage.
const PLACKET_BOTTOM = 0.7;

export default function JerseyStudio({ jersey, clubName, deals = [], library = [] }) {
  const frame = useRef(null);
  const three = useRef(null); // scène, matériaux, canevas : créés une fois
  const [crest, setCrest] = useState(null);
  const images = useLogos(library);
  const logos = useMemo(() => placedLogos(deals, library, images), [deals, library, images]);

  useEffect(() => {
    let cancelled = false;
    loadCrest(clubName).then((image) => !cancelled && setCrest(image));
    return () => {
      cancelled = true;
    };
  }, [clubName]);

  // Mise en place de la scène, une seule fois.
  useEffect(() => {
    const element = frame.current;
    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    renderer.outputColorSpace = THREE.SRGBColorSpace;
    // Neutral : garde les couleurs du tissu (ACES les délave).
    renderer.toneMapping = THREE.NeutralToneMapping;
    renderer.toneMappingExposure = 1;
    renderer.shadowMap.enabled = true;
    renderer.shadowMap.type = THREE.PCFShadowMap;
    element.appendChild(renderer.domElement);

    const scene = new THREE.Scene();
    const camera = new THREE.PerspectiveCamera(28, 1, 0.1, 50);
    camera.position.set(0, 0.25, 6.4);
    camera.lookAt(0, 0.05, 0);

    // Lumière d'ambiance : une pièce virtuelle, qui donne aussi les reflets du tissu.
    const pmrem = new THREE.PMREMGenerator(renderer);
    scene.environment = pmrem.fromScene(new RoomEnvironment(), 0.04).texture;
    scene.environmentIntensity = 0.65;
    pmrem.dispose();

    // Lampe principale, celle qui porte l'ombre des manches sur le torse.
    const key = new THREE.DirectionalLight(0xffffff, 1.5);
    key.position.set(-2.6, 4.6, 4.2);
    key.castShadow = true;
    key.shadow.mapSize.set(2048, 2048);
    key.shadow.camera.near = 1;
    key.shadow.camera.far = 14;
    key.shadow.camera.left = key.shadow.camera.bottom = -2.4;
    key.shadow.camera.right = key.shadow.camera.top = 2.4;
    key.shadow.bias = -0.0004;
    key.shadow.normalBias = 0.02;
    scene.add(key);
    const fill = new THREE.DirectionalLight(0xffffff, 0.35);
    fill.position.set(3.5, 1.5, -3);
    scene.add(fill);

    // Ombre au sol : un halo doux sous le maillot (une vraie ombre portée serait
    // anguleuse), aplati par la perspective.
    const halo = new THREE.Mesh(
      new THREE.PlaneGeometry(3.2, 3.2),
      new THREE.MeshBasicMaterial({ map: haloTexture(), transparent: true, depthWrite: false }),
    );
    halo.rotation.x = -Math.PI / 2;
    halo.position.y = -1.4;
    halo.scale.set(1, 0.55, 1);
    scene.add(halo);

    const anisotropy = renderer.capabilities.getMaxAnisotropy();
    const colorTexture = (canvas) => {
      const texture = new THREE.CanvasTexture(canvas);
      texture.colorSpace = THREE.SRGBColorSpace;
      texture.anisotropy = anisotropy;
      return texture;
    };
    // Relief répété sur toute la surface : la maille du tissu, les côtes du col.
    const reliefTexture = (canvas, repeatX, repeatY) => {
      const texture = new THREE.CanvasTexture(canvas);
      texture.wrapS = texture.wrapT = THREE.RepeatWrapping;
      texture.repeat.set(repeatX, repeatY);
      texture.anisotropy = anisotropy;
      return texture;
    };

    // Les canevas ont leur taille finale dès le départ : three.js fixe la taille d'une
    // texture à son premier envoi, et la scène est dessinée avant d'être peinte.
    const sizedCanvas = (width, height) =>
      Object.assign(document.createElement("canvas"), { width, height });
    const bodyCanvas = sizedCanvas(TEXTURE_WIDTH, TEXTURE_HEIGHT);
    const glossCanvas = sizedCanvas(TEXTURE_WIDTH, TEXTURE_HEIGHT); // rugosité : mat sauf les impressions
    const marksCanvas = sizedCanvas(TEXTURE_WIDTH, TEXTURE_HEIGHT); // masque des impressions
    const sleeveCanvases = [sizedCanvas(SLEEVE_WIDTH, SLEEVE_HEIGHT), sizedCanvas(SLEEVE_WIDTH, SLEEVE_HEIGHT)];
    const bodyTexture = colorTexture(bodyCanvas);
    const glossTexture = new THREE.CanvasTexture(glossCanvas);
    const sleeveTextures = sleeveCanvases.map(colorTexture);
    const knitCanvas = knitRelief();
    const ribCanvas = ribRelief();

    // Tissu : une maille mate, avec le voile clair d'un textile (sheen) sur les bords.
    const fabric = (map, { roughnessMap = null, knitRepeat }) =>
      new THREE.MeshPhysicalMaterial({
        map,
        roughness: roughnessMap ? 1 : 0.88,
        roughnessMap,
        metalness: 0,
        normalMap: reliefTexture(knitCanvas, ...knitRepeat),
        normalScale: new THREE.Vector2(0.3, 0.3),
        // Léger voile clair sur les bords, comme un textile ; plus fort, il délave les couleurs.
        sheen: 0.15,
        sheenRoughness: 0.8,
        sheenColor: new THREE.Color(0xffffff),
      });
    // L'intérieur (vu par le col et le bas) : le même tissu, dans l'ombre.
    const lining = (map) =>
      new THREE.MeshStandardMaterial({ map, color: 0x5e5e5e, roughness: 1, side: THREE.BackSide });
    const trimMaterial = new THREE.MeshPhysicalMaterial({
      roughness: 0.9,
      metalness: 0,
      normalMap: reliefTexture(ribCanvas, 56, 1),
      normalScale: new THREE.Vector2(0.6, 0.6),
      sheen: 0.12,
      sheenRoughness: 0.9,
      side: THREE.DoubleSide,
    });

    const jerseyGroup = new THREE.Group();
    jerseyGroup.position.y = -0.04;
    scene.add(jerseyGroup);
    const shaded = (mesh) => {
      mesh.castShadow = true;
      mesh.receiveShadow = true;
      return mesh;
    };

    const rows = bodyRows();
    const bodyGeometry = tube(rows, { ratio: 0.55, wrinkles: true });
    jerseyGroup.add(shaded(new THREE.Mesh(bodyGeometry, fabric(bodyTexture, { roughnessMap: glossTexture, knitRepeat: [26, 13] }))));
    jerseyGroup.add(new THREE.Mesh(bodyGeometry, lining(bodyTexture)));

    // Manches : un tube le long de l'axe vertical, puis basculé vers l'extérieur ; la
    // tête de manche s'enfonce dans l'épaule.
    const sleeveGeometry = tube(sleeveRows(), { ratio: 0.92, wrinkles: true });
    [-1, 1].forEach((sideSign, index) => {
      const sleeve = new THREE.Group();
      sleeve.add(shaded(new THREE.Mesh(sleeveGeometry, fabric(sleeveTextures[index], { knitRepeat: [10, 6] }))));
      sleeve.add(new THREE.Mesh(sleeveGeometry, lining(sleeveTextures[index])));
      sleeve.position.set(sideSign * 0.76, 0.66, 0);
      sleeve.rotation.z = sideSign * 0.72;
      sleeve.rotation.y = sideSign * -0.1;
      jerseyGroup.add(sleeve);
    });

    // Col : une bande côtelée qui monte, s'évase et se replie vers l'extérieur ; son
    // devant descend (dip) pour ouvrir l'encolure.
    const collar = tube(
      [
        { y: 1.07, rx: 0.285, rz: 0.255, dip: 0.14 },
        { y: 1.16, rx: 0.3, rz: 0.27, dip: 0.14 },
        { y: 1.2, rx: 0.315, rz: 0.285, dip: 0.14 },
        { y: 1.21, rx: 0.335, rz: 0.305, dip: 0.14 },
        { y: 1.18, rx: 0.345, rz: 0.315, dip: 0.14 },
      ],
      { ratio: 0.9 },
    );
    jerseyGroup.add(shaded(new THREE.Mesh(collar, trimMaterial)));

    const state = {
      renderer,
      scene,
      camera,
      jerseyGroup,
      bodyCanvas,
      bodyTexture,
      glossCanvas,
      glossTexture,
      marksCanvas,
      sleeveCanvases,
      sleeveTextures,
      trimMaterial,
      widthScale: widthScale(rows),
      yaw: FRONT_YAW,
      target: FRONT_YAW,
      tilt: TILT,
      dirty: true,
    };
    three.current = state;

    const fit = () => {
      const { width, height } = element.getBoundingClientRect();
      if (!width || !height) return;
      renderer.setSize(width, height);
      camera.aspect = width / height;
      // Recule la caméra sur un cadre étroit, pour que les manches restent visibles.
      camera.position.z = 6.4 * Math.max(1, 1.25 / camera.aspect);
      camera.updateProjectionMatrix();
      state.dirty = true;
    };
    fit();
    const observer = new ResizeObserver(fit);
    observer.observe(element);

    let frameId;
    const loop = () => {
      frameId = requestAnimationFrame(loop);
      const gap = state.target - state.yaw;
      if (Math.abs(gap) > 0.0005) {
        state.yaw += gap * 0.14;
        state.dirty = true;
      }
      if (!state.dirty) return;
      jerseyGroup.rotation.set(state.tilt, state.yaw, 0);
      renderer.render(scene, camera);
      state.dirty = false;
    };
    loop();

    return () => {
      cancelAnimationFrame(frameId);
      observer.disconnect();
      scene.traverse((object) => {
        object.geometry?.dispose();
        for (const key of ["map", "normalMap", "roughnessMap"]) object.material?.[key]?.dispose();
        object.material?.dispose();
      });
      scene.environment.dispose();
      renderer.dispose();
      element.removeChild(renderer.domElement);
      three.current = null;
    };
  }, []);

  // Le maillot change : on repeint les canevas (une fois de plus quand la police est prête).
  useEffect(() => {
    const state = three.current;
    if (!state) return undefined;
    let cancelled = false;
    const paint = () => {
      if (cancelled) return;
      paintJersey(state.bodyCanvas, jersey, { crest, clubName, logos });
      const ctx = state.bodyCanvas.getContext("2d");
      paintSeams(ctx);
      paintPlacket(ctx, jersey, state.widthScale);
      state.bodyTexture.needsUpdate = true;

      // Rugosité : le tissu est mat (clair), les impressions brillent (sombre).
      const marks = state.marksCanvas.getContext("2d");
      marks.clearRect(0, 0, TEXTURE_WIDTH, TEXTURE_HEIGHT);
      paintMarks(marks, jersey, { crest, clubName, logos });
      marks.globalCompositeOperation = "source-in";
      marks.fillStyle = "#707070";
      marks.fillRect(0, 0, TEXTURE_WIDTH, TEXTURE_HEIGHT);
      marks.globalCompositeOperation = "source-over";
      const gloss = state.glossCanvas.getContext("2d");
      gloss.fillStyle = "#e4e4e4";
      gloss.fillRect(0, 0, TEXTURE_WIDTH, TEXTURE_HEIGHT);
      gloss.drawImage(state.marksCanvas, 0, 0);
      state.glossTexture.needsUpdate = true;

      // Le logo de manche va sur la manche gauche du joueur (à droite vu de face).
      const sleeveLogo = logos.find((logo) => logo.placement === "sleeve");
      state.sleeveCanvases.forEach((canvas, index) => {
        paintSleeve(canvas, jersey, index === 1, index === 1 ? sleeveLogo : null);
        state.sleeveTextures[index].needsUpdate = true;
      });
      state.trimMaterial.color.set(jersey.trim);
      state.dirty = true;
    };
    paint();
    document.fonts?.load('700 40px "Barlow Condensed"').then(paint, () => {});
    return () => {
      cancelled = true;
    };
  }, [jersey, crest, clubName, logos]);

  // Glisser pour tourner (et un peu incliner).
  const drag = useRef(null);
  function onPointerDown(event) {
    const state = three.current;
    drag.current = { x: event.clientX, y: event.clientY, yaw: state.target, tilt: state.tilt };
    event.currentTarget.setPointerCapture(event.pointerId);
  }
  function onPointerMove(event) {
    const state = three.current;
    if (!drag.current || !state) return;
    state.target = drag.current.yaw + (event.clientX - drag.current.x) * 0.012;
    state.yaw = state.target;
    state.tilt = Math.min(0.5, Math.max(-0.3, drag.current.tilt + (event.clientY - drag.current.y) * 0.004));
    state.dirty = true;
  }
  function onPointerUp() {
    drag.current = null;
  }

  // Ramène de face ou de dos, par le plus court chemin.
  function face(yaw) {
    const state = three.current;
    const turns = Math.round((state.yaw - yaw) / (2 * Math.PI));
    state.target = yaw + turns * 2 * Math.PI;
    state.tilt = TILT;
  }

  return (
    <>
      <div
        ref={frame}
        className="jersey-studio"
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={onPointerUp}
        onPointerCancel={onPointerUp}
      />
      <div className="viewer__hint">
        <span className="muted">Glisse pour tourner le maillot</span>
        <div className="jersey-studio__turn">
          <button type="button" className="button button--small" onClick={() => face(FRONT_YAW)}>
            Face
          </button>
          <button type="button" className="button button--small" onClick={() => face(BACK_YAW)}>
            Dos
          </button>
        </div>
      </div>
    </>
  );
}

// Torse, de l'ourlet (v = 0) au col (v = 1) : jusqu'à SHOULDER_LINE, un tube un peu
// évasé en bas, resserré à la taille et large à la poitrine ; au-dessus, les épaules
// qui s'arrondissent puis montent en pente vers le col, dont le devant s'ouvre (dip).
function bodyRows() {
  const rows = [];
  const torsoRows = 40;
  const shoulderRows = 18;
  const lerp = (a, b, t) => a + (b - a) * t;
  // Profil du torse : [t, demi-largeur, demi-épaisseur].
  const profile = [
    [0, 0.87, 0.52],
    [0.12, 0.82, 0.48],
    [0.36, 0.8, 0.46],
    [0.72, 0.95, 0.56],
    [1, 0.98, 0.52],
  ];
  for (let i = 0; i <= torsoRows; i += 1) {
    const t = i / torsoRows;
    const k = profile.findIndex(([at]) => at >= t);
    const [t0, x0, z0] = profile[Math.max(0, k - 1)];
    const [t1, x1, z1] = profile[k];
    const s = t1 === t0 ? 0 : smooth((t - t0) / (t1 - t0));
    rows.push({ v: t * SHOULDER_LINE, y: -1.12 + t * 2.0, rx: lerp(x0, x1, s), rz: lerp(z0, z1, s) });
  }
  for (let i = 1; i <= shoulderRows; i += 1) {
    const s = i / shoulderRows;
    const round = Math.sin(Math.min(1, s / 0.28) * (Math.PI / 2)); // arrondi de l'épaule
    rows.push({
      v: SHOULDER_LINE + s * (1 - SHOULDER_LINE),
      y: 0.88 + 0.11 * round + 0.11 * Math.max(0, (s - 0.28) / 0.72),
      rx: lerp(0.98, 0.29, smooth(s) * 0.55 + s * 0.45),
      rz: lerp(0.52, 0.26, s),
      dip: 0.14 * smooth(Math.max(0, (s - 0.45) / 0.55)),
    });
  }
  return rows;
}

// Manche : de la manchette (en bas) à la tête de manche (à l'origine), puis une pointe
// qui s'enfonce dans l'épaule en se resserrant, pour qu'on n'en voie jamais le bord.
function sleeveRows() {
  const length = 0.68;
  const inside = 0.24;
  const rows = [];
  for (let i = 0; i <= 12; i += 1) {
    const t = i / 12;
    const r = 0.26 + 0.11 * smooth(t);
    rows.push({ y: -length + t * length, rx: r, rz: r * 0.92 });
  }
  for (let i = 1; i <= 4; i += 1) {
    const t = i / 4;
    const r = 0.37 - 0.22 * t;
    rows.push({ y: t * inside, rx: r, rz: r * 0.92 });
  }
  return rows.map((row, i) => ({ ...row, v: i / (rows.length - 1) }));
}

function smooth(t) {
  return t * t * (3 - 2 * t);
}

// Tube à section elliptique, rangée par rangée ({ y, rx, rz, v, dip }). Le tour commence
// sur le côté gauche (vu de face), passe par le devant (u = 0,25) puis le dos (u = 0,75) ;
// u suit la longueur de l'ellipse (pour que la texture ne s'écrase pas sur les côtés).
// `dip` abaisse le devant de la rangée (encolure). Le devant est un peu plus bombé que
// le dos, et `wrinkles` ajoute quelques plis.
const SEGMENTS = 112;

function tube(rows, { ratio, wrinkles = false }) {
  const angles = arcLengthAngles(ratio, SEGMENTS);
  const positions = [];
  const uvs = [];
  rows.forEach((row, i) => {
    const v = row.v ?? i / (rows.length - 1);
    for (let j = 0; j <= SEGMENTS; j += 1) {
      const theta = angles[j];
      const front = Math.max(0, Math.sin(theta)); // 1 au milieu du devant, 0 dans le dos
      const fold = wrinkles
        ? 1 + (1 - v) * (0.011 * Math.sin(theta * 11 + v * 4) + 0.007 * Math.sin(theta * 5 - v * 7))
        : 1;
      const belly = 1 + 0.05 * Math.sin(theta);
      positions.push(
        -row.rx * fold * Math.cos(theta),
        row.y - (row.dip ?? 0) * front ** 1.6,
        row.rz * fold * belly * Math.sin(theta),
      );
      uvs.push(j / SEGMENTS, v);
    }
  });
  const indices = [];
  const stride = SEGMENTS + 1;
  for (let i = 0; i < rows.length - 1; i += 1) {
    for (let j = 0; j < SEGMENTS; j += 1) {
      const a = i * stride + j;
      const b = a + 1;
      const c = a + stride;
      const d = c + 1;
      indices.push(a, b, c, b, d, c);
    }
  }
  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute("position", new THREE.Float32BufferAttribute(positions, 3));
  geometry.setAttribute("uv", new THREE.Float32BufferAttribute(uvs, 2));
  geometry.setIndex(indices);
  geometry.computeVertexNormals();
  // Couture : le premier et le dernier sommet de chaque rangée sont au même endroit ;
  // on leur donne la même normale pour ne pas voir de trait.
  const normals = geometry.attributes.normal;
  for (let i = 0; i < rows.length; i += 1) {
    const first = i * stride;
    const last = first + SEGMENTS;
    const n = new THREE.Vector3().fromBufferAttribute(normals, first);
    n.add(new THREE.Vector3().fromBufferAttribute(normals, last)).normalize();
    normals.setXYZ(first, n.x, n.y, n.z);
    normals.setXYZ(last, n.x, n.y, n.z);
  }
  return geometry;
}

// Angles qui découpent une ellipse (demi-axes 1 et `ratio`) en arcs de même longueur.
function arcLengthAngles(ratio, segments) {
  const samples = 720;
  const lengths = [0];
  for (let k = 1; k <= samples; k += 1) {
    const [a, b] = [((k - 1) / samples) * 2 * Math.PI, (k / samples) * 2 * Math.PI];
    const dx = Math.cos(b) - Math.cos(a);
    const dz = ratio * (Math.sin(b) - Math.sin(a));
    lengths.push(lengths[k - 1] + Math.hypot(dx, dz));
  }
  const total = lengths[samples];
  const angles = [];
  let k = 0;
  for (let j = 0; j <= segments; j += 1) {
    const goal = (j / segments) * total;
    while (k < samples && lengths[k + 1] < goal) k += 1;
    const span = lengths[k + 1] - lengths[k] || 1;
    const t = Math.min(1, (goal - lengths[k]) / span);
    angles.push(((k + t) / samples) * 2 * Math.PI);
  }
  return angles;
}

// La texture fait tout le tour quelle que soit la rangée : vers le col, où le tour est
// court, un dessin est d'autant plus resserré. Renvoie, pour une hauteur v, le facteur
// par lequel élargir un dessin pour qu'il garde sa largeur réelle (1 à la poitrine).
function widthScale(rows) {
  const perimeter = ({ rx, rz }) => Math.PI * (3 * (rx + rz) - Math.sqrt((3 * rx + rz) * (rx + 3 * rz)));
  const chest = perimeter(rows.find((row) => row.v >= PLACKET_BOTTOM));
  return (v) => {
    const k = Math.max(1, rows.findIndex((row) => row.v >= v));
    const [a, b] = [rows[k - 1], rows[k]];
    const t = (v - a.v) / (b.v - a.v || 1);
    return chest / (perimeter(a) + (perimeter(b) - perimeter(a)) * t);
  };
}

// Coutures sur le canevas : les côtés (bords de chaque moitié) et l'ourlet.
function paintSeams(ctx) {
  const [W, H] = [TEXTURE_WIDTH, TEXTURE_HEIGHT];
  ctx.save();
  ctx.lineWidth = 2;
  for (const x of [1, W / 2, W - 1]) {
    ctx.strokeStyle = "rgba(0, 0, 0, 0.22)";
    ctx.beginPath();
    ctx.moveTo(x, 0);
    ctx.lineTo(x, H);
    ctx.stroke();
  }
  // Ourlet : un repli de 3 % avec sa piqûre.
  ctx.strokeStyle = "rgba(0, 0, 0, 0.18)";
  ctx.beginPath();
  ctx.moveTo(0, H * 0.97);
  ctx.lineTo(W, H * 0.97);
  ctx.stroke();
  ctx.strokeStyle = "rgba(255, 255, 255, 0.22)";
  ctx.setLineDash([5, 4]);
  ctx.lineWidth = 1.5;
  ctx.beginPath();
  ctx.moveTo(0, H * 0.97 + 3);
  ctx.lineTo(W, H * 0.97 + 3);
  ctx.stroke();
  ctx.restore();
}

// Patte de boutonnage, au milieu du devant sous le col : une bande du fond du maillot,
// piquée sur ses bords, avec deux boutons. Élargie vers le haut selon `scale(v)` pour
// garder une largeur constante sur le modèle.
function paintPlacket(ctx, jersey, scale) {
  const [half, H] = [TEXTURE_WIDTH / 2, TEXTURE_HEIGHT];
  const cx = half / 2;
  const bottom = H * (1 - PLACKET_BOTTOM);
  const width = 30;
  const steps = 24;
  const edge = (side) => {
    const points = [];
    for (let i = 0; i <= steps; i += 1) {
      const y = (bottom * i) / steps;
      points.push([cx + (side * width * scale(1 - y / H)) / 2, y]);
    }
    return points;
  };
  const left = edge(-1);
  const right = edge(1).reverse();
  ctx.save();
  ctx.beginPath();
  [...left, ...right].forEach(([x, y], i) => (i ? ctx.lineTo(x, y) : ctx.moveTo(x, y)));
  ctx.closePath();
  ctx.fillStyle = jersey.base;
  ctx.fill();
  ctx.lineWidth = 2;
  ctx.strokeStyle = "rgba(0, 0, 0, 0.28)";
  ctx.stroke();
  ctx.setLineDash([4, 3]);
  ctx.lineWidth = 1.2;
  ctx.strokeStyle = "rgba(255, 255, 255, 0.3)";
  ctx.stroke();
  ctx.setLineDash([]);
  // Boutons : de la couleur du col, cernés, avec deux trous.
  for (const y of [bottom * 0.36, bottom * 0.7]) {
    const s = scale(1 - y / H);
    ctx.beginPath();
    ctx.ellipse(cx, y, 6.5 * s, 6.5, 0, 0, 2 * Math.PI);
    ctx.fillStyle = jersey.trim;
    ctx.fill();
    ctx.lineWidth = 1.5;
    ctx.strokeStyle = "rgba(0, 0, 0, 0.35)";
    ctx.stroke();
    ctx.fillStyle = "rgba(0, 0, 0, 0.4)";
    for (const dx of [-2.3, 2.3]) {
      ctx.beginPath();
      ctx.ellipse(cx + dx * s, y, 1.1 * s, 1.1, 0, 0, 2 * Math.PI);
      ctx.fill();
    }
  }
  ctx.restore();
}

// Relief d'une maille : un tissage en losanges, un peu irrégulier. Carte de normales
// répétable (bords qui se raccordent).
function knitRelief() {
  const size = 128;
  const period = 8;
  return normalMap(size, size, (x, y) => {
    const a = Math.sin((2 * Math.PI * (x + y)) / period);
    const b = Math.sin((2 * Math.PI * (x - y)) / period);
    return 0.5 + 0.18 * a + 0.18 * b + 0.14 * (hash(x, y) - 0.5);
  });
}

// Côtes du col : des crêtes verticales.
function ribRelief() {
  const size = 32;
  return normalMap(size, size, (x) => 0.5 + 0.5 * Math.sin((2 * Math.PI * x) / size));
}

// Carte de normales (espace tangent) à partir d'une fonction de hauteur périodique.
function normalMap(width, height, heightAt) {
  const canvas = Object.assign(document.createElement("canvas"), { width, height });
  const ctx = canvas.getContext("2d");
  const image = ctx.createImageData(width, height);
  const strength = 2.2;
  for (let y = 0; y < height; y += 1) {
    for (let x = 0; x < width; x += 1) {
      const dx = heightAt((x + 1) % width, y) - heightAt((x + width - 1) % width, y);
      const dy = heightAt(x, (y + 1) % height) - heightAt(x, (y + height - 1) % height);
      // v (texture) monte alors que y (canevas) descend : la pente en y change de signe.
      const n = new THREE.Vector3(-dx * strength, dy * strength, 1).normalize();
      const at = (y * width + x) * 4;
      image.data[at] = (n.x * 0.5 + 0.5) * 255;
      image.data[at + 1] = (n.y * 0.5 + 0.5) * 255;
      image.data[at + 2] = (n.z * 0.5 + 0.5) * 255;
      image.data[at + 3] = 255;
    }
  }
  ctx.putImageData(image, 0, 0);
  return canvas;
}

// Halo d'ombre : un disque qui s'estompe du centre vers le bord.
function haloTexture() {
  const size = 256;
  const canvas = Object.assign(document.createElement("canvas"), { width: size, height: size });
  const ctx = canvas.getContext("2d");
  const gradient = ctx.createRadialGradient(size / 2, size / 2, 0, size / 2, size / 2, size / 2);
  gradient.addColorStop(0, "rgba(22, 24, 27, 0.28)");
  gradient.addColorStop(0.45, "rgba(22, 24, 27, 0.12)");
  gradient.addColorStop(1, "rgba(22, 24, 27, 0)");
  ctx.fillStyle = gradient;
  ctx.fillRect(0, 0, size, size);
  const texture = new THREE.CanvasTexture(canvas);
  texture.colorSpace = THREE.SRGBColorSpace;
  return texture;
}

// Bruit déterministe entre 0 et 1.
function hash(x, y) {
  const n = Math.sin(x * 127.1 + y * 311.7) * 43758.5453;
  return n - Math.floor(n);
}

// Manche : sa couleur (ou les cerceaux), la manchette aux couleurs du col avec sa
// piqûre, la couture sous le bras (au bord du canevas) et, s'il y en a un, le logo
// du sponsor entre le devant et l'extérieur de la manche.
// (Le bas du canevas est la manchette ; le haut, caché dans l'épaule.)
function paintSleeve(canvas, jersey, right, logo = null) {
  const [w, h] = [SLEEVE_WIDTH, SLEEVE_HEIGHT];
  const ctx = canvas.getContext("2d");
  ctx.fillStyle = sleeveColor(jersey, right);
  ctx.fillRect(0, 0, w, h);
  if (sleeveHoops(jersey)) {
    ctx.fillStyle = jersey.motif;
    ctx.fillRect(0, h * 0.4, w, h * 0.2);
  }
  ctx.fillStyle = jersey.trim;
  ctx.fillRect(0, h * 0.88, w, h * 0.12);
  ctx.strokeStyle = "rgba(0, 0, 0, 0.25)";
  ctx.lineWidth = 1.5;
  ctx.beginPath();
  ctx.moveTo(0, h * 0.88);
  ctx.lineTo(w, h * 0.88);
  ctx.moveTo(1, 0);
  ctx.lineTo(1, h);
  ctx.moveTo(w - 1, 0);
  ctx.lineTo(w - 1, h);
  ctx.stroke();
  if (logo) drawLogo(ctx, logo.image, w * 0.4, h * 0.6, w * 0.34, h * 0.2);
}
