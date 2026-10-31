import * as THREE from "three";

import { createAudio } from "./audio.js";
import { ballCanvases, ballGeometry, teeGeometry } from "./ball.js";
import { buildField } from "./field.js";
import { buildPalette } from "./palette.js";
import { createPipeline } from "./render.js";
import { seeded } from "./scripts/common.js";
import { Player, createKit, refereeJersey, sharedMaterials } from "./rig.js";

// Le plateau d'une scène de match : le rendu, le décor, les joueurs, la caméra de
// retransmission et le cycle d'une scène en trois temps :
//
// - mise en place (`setup`) : la scène se joue, ralentit puis se fige ;
// - choix (`hold`) : l'image reste figée mais vivante (souffle des joueurs, caméra qui
//   dérive, rumeur du public) ; au survol d'une voie, elle se dessine sur la pelouse ;
// - issue (`outcome`) : l'action tirée par le serveur se joue, puis l'image se tient.
//
// Les scènes (scripts/) décrivent chaque instant comme une fonction du temps : où sont
// les joueurs, leur pose, le ballon, la caméra. Le plateau ne fait qu'avancer le temps,
// ralentir, figer, sauter à la fin, et déclencher les repères sonores (`cues`).

const SLOW = 0.6; // dernière part de la mise en place jouée au ralenti (s de scène)
const BLEND = 0.7; // raccord de caméra entre deux temps (s)
// Sur téléphone, les voies couvrent la moitié basse de l'image : son centre remonte à
// 1 - LIFT / 2 de sa hauteur (sur ordinateur, les scènes sont cadrées pour elles).
const LIFT = 1.3;
const WIDE = 16 / 9; // les scènes sont cadrées pour cet écran

// L'angle de vue vertical de la caméra pour l'angle voulu par la scène (cadré en 16/9) :
// compensé du décalage (LIFT), et élargi sur un écran en hauteur pour garder l'action
// dans le cadre (un téléphone en voit à peu près la moitié de la largeur).
function fovFor(fov, aspect, lift) {
  const half = Math.tan(THREE.MathUtils.degToRad(fov) / 2) * Math.max(1, (WIDE * 0.55) / aspect) * lift;
  return THREE.MathUtils.radToDeg(2 * Math.atan(half));
}

const smooth = (k) => k * k * (3 - 2 * k);

// `host` : l'élément qui reçoit le canevas ; `context` : les clubs, leurs maillots, le
// temps, l'heure, la pression, le son ; `events` : onChoice (la scène est figée, les
// voies s'affichent), onDone (l'issue est jouée), onFail (WebGL indisponible).
export function createStage(host, context, events) {
  let renderer;
  try {
    renderer = new THREE.WebGLRenderer({ antialias: false, powerPreference: "high-performance" });
  } catch {
    events.onFail?.();
    return null;
  }
  renderer.setPixelRatio(1);
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  const canvas = renderer.domElement;
  canvas.className = "match-scene__canvas";
  host.prepend(canvas);

  const { home, away, us, accent, weather, evening, phone } = context;
  const ours = us === "home" ? home : away;
  const theirs = us === "home" ? away : home;
  const refJersey = refereeJersey([home.jersey, away.jersey]);
  const palette = buildPalette({
    clubs: [ours.jersey.base, theirs.jersey.base, ours.jersey.motif, theirs.jersey.motif, ours.jersey.trim, theirs.jersey.trim, refJersey.base, home.colors[0]],
    extra: [accent, "#F7F7F4"],
    evening,
  });
  const pipeline = createPipeline(renderer, palette);

  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(36, 16 / 9, 0.3, 400);
  const field = buildField(scene, {
    homeName: home.name,
    homeColors: home.colors,
    awayColors: away.colors,
    homeInk: home.ink,
    accent,
    logos: [],
    weather,
    evening,
  });
  const audio = createAudio();
  audio.setMuted(context.muted);
  audio.setTension(context.pressure > 1 ? 0.6 : 0.25);

  // Le ballon et le tee, communs à toutes les scènes.
  const leather = ballCanvases();
  const leatherMap = new THREE.CanvasTexture(leather.color);
  leatherMap.colorSpace = THREE.SRGBColorSpace;
  const ball = new THREE.Mesh(ballGeometry(14, 10), new THREE.MeshLambertMaterial({ map: leatherMap }));
  ball.scale.setScalar(1.15); // vu de loin, un ballon à l'échelle tiendrait dans un pixel
  scene.add(ball);
  const tee = new THREE.Mesh(teeGeometry(), new THREE.MeshLambertMaterial({ color: 0xe35205 }));
  tee.scale.setScalar(1.4);
  tee.visible = false;
  scene.add(tee);

  const shared = sharedMaterials();
  const kits = {
    us: createKit(ours.jersey),
    them: createKit(theirs.jersey),
    ref: createKit(refJersey, { shorts: "#16181B", socks: refJersey.base }),
  };
  const previews = new THREE.Group();
  scene.add(previews);
  // Vus d'en haut comme d'en bas (les tracés au sol sont des faces sans envers).
  const previewMaterial = new THREE.MeshBasicMaterial({ color: 0xf7f7f4, transparent: true, opacity: 0.92, depthWrite: false, side: THREE.DoubleSide });
  const accentMaterial = new THREE.MeshBasicMaterial({ color: accent, depthWrite: false, side: THREE.DoubleSide });

  // --- Ce que les scènes ont sous la main -----------------------------------------
  let cast = [];
  let silent = false;
  const world = {
    rng: seeded(context.seed),
    ball,
    tee,
    wind: field.wind,
    us,
    homeIsUs: us === "home",
    pressure: context.pressure,
    // Un joueur de l'équipe "us" ou "them", ou l'arbitre ("ref").
    player(team, number = null, { hero = false } = {}) {
      const player = new Player({
        kit: kits[team],
        number: team === "ref" ? null : number,
        seed: Math.floor(world.rng() * 1000),
        marker: hero ? accent : null,
        shared,
      });
      player.team = team;
      scene.add(player.root);
      cast.push(player);
      return player;
    },
    // Le ballon à un point, couché selon `axis` (la direction de la pointe), tourné de
    // `spin` autour de son axe de rotation (culbute).
    ballAt(position, axis = null, spin = 0, spinAxis = null) {
      ball.position.copy(position);
      if (axis) ball.quaternion.setFromUnitVectors(THREE.Object3D.DEFAULT_UP, axis.clone().normalize());
      if (spinAxis && spin) ball.quaternion.premultiply(new THREE.Quaternion().setFromAxisAngle(spinAxis, spin));
    },
    sound(name, ...args) {
      if (!silent) audio.play(name, ...args);
    },
    // Fondu au noir (0) et retour (1), pour passer d'un endroit du terrain à un autre.
    exposure(value) {
      pipeline.exposure = value;
    },
    // Le public : "cheer" pour l'équipe `team` ("us" ou "them"), "boo" contre elle,
    // "standing", "seated".
    crowd(mood, team = "us") {
      const side = team === "us" ? us : us === "home" ? "away" : "home";
      field.crowd.setMood(mood, clock, side);
      audio.setTension(mood === "seated" ? 0.25 : mood === "standing" ? 0.6 : 0.9);
    },
    // Aperçus d'une voie, posés sur la pelouse ou dans l'air.
    draw: {
      // Un trajet au sol en tirets : [[x, z], ...].
      path(points, { width = 0.45, dashed = true } = {}) {
        const curve = new THREE.CatmullRomCurve3(points.map(([x, z]) => new THREE.Vector3(x, 0.04, z)));
        const steps = Math.max(12, Math.round(curve.getLength() * 2));
        const positions = [];
        const index = [];
        const p = new THREE.Vector3();
        const tangent = new THREE.Vector3();
        for (let i = 0; i <= steps; i++) {
          curve.getPointAt(i / steps, p);
          curve.getTangentAt(i / steps, tangent);
          const nx = -tangent.z * width * 0.5;
          const nz = tangent.x * width * 0.5;
          positions.push(p.x + nx, p.y, p.z + nz, p.x - nx, p.y, p.z - nz);
          if (i < steps && (!dashed || i % 3 !== 2)) {
            const a = i * 2;
            index.push(a, a + 1, a + 2, a + 1, a + 3, a + 2);
          }
        }
        const geometry = new THREE.BufferGeometry();
        geometry.setAttribute("position", new THREE.Float32BufferAttribute(positions, 3));
        geometry.setIndex(index);
        const mesh = new THREE.Mesh(geometry, previewMaterial);
        mesh.renderOrder = 2;
        return grow(mesh, index.length);
      },
      // Une trajectoire dans l'air : [[x, y, z], ...].
      arc(points, radius = 0.1) {
        const curve = new THREE.CatmullRomCurve3(points.map((q) => new THREE.Vector3(...q)));
        const geometry = new THREE.TubeGeometry(curve, 64, radius, 4, false);
        return grow(new THREE.Mesh(geometry, previewMaterial), geometry.index.count);
      },
      // Une flèche plate au sol, de `from` à `to` ([x, z]) : la poussée d'une mêlée.
      arrow(from, to, width = 2.2) {
        const length = Math.hypot(to[0] - from[0], to[1] - from[1]);
        const shape = new THREE.Shape();
        const head = Math.min(length * 0.45, width * 1.1);
        shape.moveTo(-width / 4, 0);
        shape.lineTo(width / 4, 0);
        shape.lineTo(width / 4, length - head);
        shape.lineTo(width / 2, length - head);
        shape.lineTo(0, length);
        shape.lineTo(-width / 2, length - head);
        shape.lineTo(-width / 4, length - head);
        shape.closePath();
        const geometry = new THREE.ShapeGeometry(shape);
        geometry.rotateX(Math.PI / 2);
        const mesh = new THREE.Mesh(geometry, accentMaterial);
        mesh.position.set(from[0], 0.05, from[1]);
        mesh.rotation.y = Math.atan2(to[0] - from[0], to[1] - from[1]);
        mesh.renderOrder = 2;
        return mesh;
      },
      // Le point d'arrivée : un anneau à la couleur du club.
      mark([x, z], radius = 0.9) {
        const mesh = new THREE.Mesh(new THREE.RingGeometry(radius * 0.7, radius, 20).rotateX(-Math.PI / 2), accentMaterial);
        mesh.position.set(x, 0.05, z);
        mesh.renderOrder = 2;
        return mesh;
      },
    },
  };

  // Un aperçu se dessine du départ à l'arrivée en une demi-seconde.
  const growing = [];
  function grow(mesh, count) {
    mesh.geometry.setDrawRange(0, 0);
    growing.push({ mesh, count, from: clock });
    return mesh;
  }

  // --- Le temps -------------------------------------------------------------------
  let clock = 0;
  let script = null;
  let phase = "idle"; // setup | hold | outcome | after
  let t = 0; // temps réel écoulé dans le temps en cours
  let holdTime = 0;
  let outcome = null;
  let cue = 0;
  let shot = null; // la caméra voulue par la scène
  let aside = null; // le plan large d'un aperçu, le temps du survol
  const view = { pos: new THREE.Vector3(-30, 20, 60), look: new THREE.Vector3(0, 0, 20), fov: 36 };
  const blendFrom = { pos: new THREE.Vector3(), look: new THREE.Vector3(), fov: 36, at: -10 };
  const tight = { value: 1 }; // caméra plus serrée sous la pression

  const setupLength = () => {
    const d = script.setup.duration;
    const a = Math.max(0, d - SLOW);
    return { d, a, real: a + 2 * (d - a) };
  };
  // Le temps de la scène pendant la mise en place : normal, puis ralenti jusqu'à l'arrêt.
  const setupTime = (u) => {
    const { d, a, real } = setupLength();
    if (u <= a) return u;
    const k = Math.min(1, (u - a) / (real - a));
    return a + (d - a) * (1 - (1 - k) * (1 - k));
  };

  const markBlend = () => {
    blendFrom.pos.copy(view.pos);
    blendFrom.look.copy(view.look);
    blendFrom.fov = view.fov;
    blendFrom.at = clock;
  };

  function clearPreview() {
    previews.children.slice().forEach((child) => {
      previews.remove(child);
      child.geometry.dispose();
    });
    growing.length = 0;
  }

  function step(dt) {
    clock += dt;
    if (!script) return;
    if (phase === "setup") {
      t += dt;
      const { real } = setupLength();
      const now = setupTime(Math.min(t, real));
      shot = script.setup.frame(now);
      const setupCues = script.setup.cues ?? [];
      while (cue < setupCues.length && setupCues[cue].at <= now) setupCues[cue++].run();
      if (t >= real) {
        phase = "hold";
        holdTime = 0;
        events.onChoice?.();
      }
    } else if (phase === "hold") {
      holdTime += dt;
      shot = script.setup.frame(script.setup.duration);
      if (aside) shot = aside;
      script.hold?.(holdTime);
      cast.forEach((player) => player.set(player.current, holdTime));
    } else if (phase === "outcome" || phase === "after") {
      t += dt;
      const s = Math.min(t, outcome.duration);
      shot = outcome.frame(s);
      while (cue < outcome.cues.length && outcome.cues[cue].at <= s) outcome.cues[cue++].run();
      if (phase === "outcome" && t >= outcome.duration) {
        phase = "after";
        holdTime = 0;
        events.onDone?.();
      }
      if (phase === "after") {
        holdTime += dt;
        cast.forEach((player) => player.set(player.current, holdTime));
      }
    }

    // Caméra : celle de la scène, raccordée au temps précédent, qui dérive au choix.
    if (shot) {
      const wanted = phase === "hold" && world.pressure > 1 ? 0.84 : 1;
      tight.value += (wanted - tight.value) * Math.min(1, dt * 1.5);
      const drift = phase === "hold" ? 1 : 0;
      const target = {
        pos: new THREE.Vector3(...shot.pos).add(
          new THREE.Vector3(Math.sin(clock * 0.31) * 0.5, Math.sin(clock * 0.23) * 0.25, Math.cos(clock * 0.27) * 0.5).multiplyScalar(drift),
        ),
        look: new THREE.Vector3(...shot.look),
        fov: shot.fov * tight.value,
      };
      const k = smooth(Math.min(1, (clock - blendFrom.at) / BLEND));
      view.pos.lerpVectors(blendFrom.pos, target.pos, k);
      view.look.lerpVectors(blendFrom.look, target.look, k);
      view.fov = blendFrom.fov + (target.fov - blendFrom.fov) * k;
    }
    growing.forEach(({ mesh, count, from }) => {
      const k = Math.min(1, (clock - from) / 0.5);
      mesh.geometry.setDrawRange(0, Math.floor((count * smooth(k)) / 3) * 3);
    });
    field.update(clock, dt, view.look);
  }

  // --- Cadrage et boucle ------------------------------------------------------------
  const rows = phone ? 260 : 300; // lignes de pixels de la scène
  const lift = phone ? LIFT : 1;
  const fit = () => {
    const { width, height } = host.getBoundingClientRect();
    if (!width || !height) return;
    const ratio = Math.min(window.devicePixelRatio || 1, 2);
    const scale = Math.max(1, Math.round((height * ratio) / rows));
    pipeline.setSize(Math.ceil((width * ratio) / scale), Math.ceil((height * ratio) / scale));
    camera.aspect = width / height;
    // Le point visé monte vers le haut du cadre : on ne garde que le bas d'une image
    // plus haute.
    camera.setViewOffset(width, height * lift, 0, height * (lift - 1), width, height);
  };
  const observer = new ResizeObserver(fit);
  observer.observe(host);
  fit();

  let frame = 0;
  let last = performance.now();
  let lastDraw = 0;
  const interval = phone ? 1 / 30 : 0; // 30 images par seconde sur téléphone
  const loop = (now) => {
    frame = requestAnimationFrame(loop);
    const dt = Math.min(0.05, (now - last) / 1000);
    last = now;
    step(dt);
    if (interval && (now - lastDraw) / 1000 < interval - 0.004) return;
    lastDraw = now;
    camera.position.copy(view.pos);
    camera.fov = fovFor(view.fov, camera.aspect, lift);
    camera.updateProjectionMatrix();
    camera.lookAt(view.look);
    pipeline.render(scene, camera);
  };
  frame = requestAnimationFrame(loop);

  // Pertes de contexte (onglet en arrière-plan sur téléphone) : on rend la main au texte.
  const onLost = (event) => {
    event.preventDefault();
    events.onFail?.();
  };
  canvas.addEventListener("webglcontextlost", onLost);

  return {
    world,
    // Une scène commence (ou s'enchaîne sur la précédente, sans coupure : les joueurs
    // gardés par la nouvelle restent, les autres s'en vont).
    begin(build, data) {
      const previous = cast;
      cast = [];
      clearPreview();
      const handover = script ? { cast: previous, ball: ball.position.clone() } : null;
      const kept = new Set();
      world.keep = (player) => {
        kept.add(player);
        cast.push(player);
        return player;
      };
      script = build(world, data, handover);
      script.setup.cues?.sort((a, b) => a.at - b.at);
      previous.filter((player) => !kept.has(player)).forEach((player) => scene.remove(player.root));
      phase = "setup";
      t = 0;
      cue = 0;
      if (handover) markBlend();
      else blendFrom.at = -10;
    },
    // Dessine la voie survolée (null : rien).
    preview(key) {
      clearPreview();
      const wide = (key && phase === "hold" && script.previewShot?.(key)) || null;
      if (wide !== aside) markBlend();
      aside = wide;
      if (!key || phase !== "hold" || !script.preview) return;
      const drawn = script.preview(key);
      (Array.isArray(drawn) ? drawn : [drawn]).filter(Boolean).forEach((object) => previews.add(object));
    },
    // L'issue tirée par le serveur : la voie et ce qu'elle a donné.
    play(key, result) {
      clearPreview();
      aside = null;
      outcome = script.outcome(key, result);
      outcome.cues.sort((a, b) => a.at - b.at);
      cue = 0;
      phase = "outcome";
      t = 0;
      markBlend();
    },
    // Clic ou Espace : la mise en place file au choix, l'issue à sa fin.
    skip() {
      if (phase === "setup") {
        silent = true;
        const setupCues = script.setup.cues ?? [];
        while (cue < setupCues.length) setupCues[cue++].run();
        silent = false;
        t = setupLength().real;
        markBlend();
      } else if (phase === "outcome") {
        silent = true;
        while (cue < outcome.cues.length) outcome.cues[cue++].run();
        silent = false;
        t = outcome.duration;
        markBlend();
      }
    },
    get phase() {
      return phase;
    },
    setMuted(value) {
      audio.setMuted(value);
    },
    wake() {
      audio.wake();
    },
    setLogos(images) {
      field.repaint(images);
    },
    dispose() {
      cancelAnimationFrame(frame);
      observer.disconnect();
      canvas.removeEventListener("webglcontextlost", onLost);
      audio.dispose();
      const textures = new Set();
      scene.traverse((object) => {
        object.geometry?.dispose();
        const materials = Array.isArray(object.material) ? object.material : [object.material];
        materials.filter(Boolean).forEach((material) => {
          for (const key of ["map", "emissiveMap"]) if (material[key]) textures.add(material[key]);
          material.dispose();
        });
      });
      for (const kit of Object.values(kits)) {
        for (const material of [kit.front, kit.side, ...kit.backs.values()]) textures.add(material.map);
      }
      textures.forEach((texture) => texture.dispose());
      previewMaterial.dispose();
      accentMaterial.dispose();
      pipeline.dispose();
      renderer.forceContextLoss();
      renderer.dispose();
      canvas.remove();
    },
  };
}
