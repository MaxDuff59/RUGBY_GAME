import { useEffect, useRef } from "react";

// Ballon de rugby en 3D, dessiné pixel par pixel dans un canvas, sans bibliothèque :
// pour chaque pixel on lance un rayon vers un ellipsoïde allongé, puis on éclaire le
// point touché (cuir clair, quatre panneaux cousus, picots d'accroche, une vague bleu
// nuit et or comme le logo). Le ballon tourne sur son grand axe comme une passe vissée,
// flotte au-dessus de son ombre, s'incline vers la souris ; un clic le fait sauter en
// culbutant. Avec « réduire les animations », il reste immobile.

const A = 1; // demi grand axe (le long du ballon)
const B = 0.62; // demi petit axe
const QUARTER = Math.PI / 2;
const LEATHER = [244, 240, 231];
const NAVY = [29, 43, 69];
const GOLD = [200, 163, 92];
const SEAM = [84, 82, 80];

// Lumière en haut à gauche, devant ; repère du monde : x à droite, y en haut, z vers nous.
const LIGHT = normalize([-0.5, 0.7, 0.6]);
const HALF = normalize([LIGHT[0], LIGHT[1], LIGHT[2] + 1]);

const SPIN = 2.4; // vitesse de la vrille au repos (rad/s)
const ROLL = -0.55; // le grand axe pointe vers le haut à droite
// Saut proportionné à la taille du ballon : il monte d'un tiers de sa largeur.
const GRAVITY = 6.5; // largeurs/s²
const KICK = 2.05; // largeurs/s

function normalize(v) {
  const n = Math.hypot(v[0], v[1], v[2]);
  return [v[0] / n, v[1] / n, v[2] / n];
}

function multiply(m, n) {
  const out = new Array(9);
  for (let i = 0; i < 3; i++) {
    for (let j = 0; j < 3; j++) {
      out[i * 3 + j] = m[i * 3] * n[j] + m[i * 3 + 1] * n[3 + j] + m[i * 3 + 2] * n[6 + j];
    }
  }
  return out;
}

const rotX = (a) => [1, 0, 0, 0, Math.cos(a), -Math.sin(a), 0, Math.sin(a), Math.cos(a)];
const rotY = (a) => [Math.cos(a), 0, Math.sin(a), 0, 1, 0, -Math.sin(a), 0, Math.cos(a)];
const rotZ = (a) => [Math.cos(a), -Math.sin(a), 0, Math.sin(a), Math.cos(a), 0, 0, 0, 1];

// Dessine le ballon tourné par `R` (monde = R · ballon) dans `image`, carré de côté `W`.
function render(image, W, R) {
  const data = image.data;
  data.fill(0);
  const S = W * 0.38; // pixels par unité
  const c = W / 2;

  // Rayon vers -z, ramené dans le repère du ballon (Rᵀ), puis dans la sphère unité.
  const dx = -R[6] / A;
  const dy = -R[7] / B;
  const dz = -R[8] / B;
  const a = dx * dx + dy * dy + dz * dz;
  const Z0 = 4;

  const from = Math.max(0, Math.floor(c - S * 1.02));
  const to = Math.min(W, Math.ceil(c + S * 1.02));
  for (let py = from; py < to; py++) {
    const Y = (c - py) / S;
    for (let px = from; px < to; px++) {
      const X = (px - c) / S;
      // Origine du rayon dans le repère du ballon.
      const ox = R[0] * X + R[3] * Y + R[6] * Z0;
      const oy = R[1] * X + R[4] * Y + R[7] * Z0;
      const oz = R[2] * X + R[5] * Y + R[8] * Z0;
      const sx = ox / A;
      const sy = oy / B;
      const sz = oz / B;
      const b = 2 * (sx * dx + sy * dy + sz * dz);
      const disc = b * b - 4 * a * (sx * sx + sy * sy + sz * sz - 1);
      if (disc <= 0) continue;

      const root = Math.sqrt(disc);
      const t = (-b - root) / (2 * a);
      // Point touché, repère du ballon.
      const hx = ox - R[6] * t;
      const hy = oy - R[7] * t;
      const hz = oz - R[8] * t;

      // Normale, puis dans le monde pour l'éclairage.
      const bx = hx / (A * A);
      const by = hy / (B * B);
      const bz = hz / (B * B);
      let nx = R[0] * bx + R[1] * by + R[2] * bz;
      let ny = R[3] * bx + R[4] * by + R[5] * bz;
      let nz = R[6] * bx + R[7] * by + R[8] * bz;
      const nl = Math.hypot(nx, ny, nz);
      nx /= nl;
      ny /= nl;
      nz /= nl;

      // Surface : position le long du ballon, angle autour du grand axe, panneau.
      const u = hx / A;
      const radius = B * Math.sqrt(Math.max(0, 1 - u * u));
      const phi = Math.atan2(hz, hy);
      const m = phi / QUARTER;
      const panel = Math.floor(m);
      const q = m - panel;
      const seam = Math.min(q, 1 - q) * QUARTER * radius;

      let color = LEATHER;
      let shade = 1;
      // La vague, qui s'effile vers les pointes : bleu nuit liseré d'or, ou or seul.
      const width = 0.06 * (1 - (u / 0.78) ** 4);
      if (width > 0) {
        const wave = 0.5 + 0.2 * Math.sin(u * 3.2 + panel * 1.9);
        const off = Math.abs(q - wave) * QUARTER * radius;
        if (panel & 1) {
          if (off < width * 0.6) color = GOLD;
        } else if (off < width) {
          color = NAVY;
        } else if (off < width + 0.018) {
          color = GOLD;
        }
      }
      // Coutures : un trait sombre, le cuir creusé de part et d'autre.
      if (seam < 0.011) {
        color = SEAM;
      } else if (seam < 0.06) {
        shade = 0.82 + 0.18 * (seam / 0.06);
      }
      // Picots d'accroche.
      const gx = hx * 24;
      const gy = phi * radius * 24;
      const fx = gx - Math.floor(gx) - 0.5;
      const fy = gy - Math.floor(gy) - 0.5;
      if (fx * fx + fy * fy < 0.07) shade *= 0.94;

      const diffuse = Math.max(0, nx * LIGHT[0] + ny * LIGHT[1] + nz * LIGHT[2]);
      let spec = Math.max(0, nx * HALF[0] + ny * HALF[1] + nz * HALF[2]);
      spec *= spec;
      spec *= spec;
      spec *= spec;
      spec *= spec;
      spec *= spec;
      const light = (0.3 + 0.78 * diffuse) * shade;
      const gloss = spec * 90;

      // Bord adouci : distance au contour, en pixels, déduite de la demi-corde.
      const half = root / (2 * a);
      const alpha = Math.min(1, ((half * half) / (2 * B)) * S);

      const i = (py * W + px) * 4;
      data[i] = Math.min(255, color[0] * light + gloss);
      data[i + 1] = Math.min(255, color[1] * light + gloss);
      data[i + 2] = Math.min(255, color[2] * light + gloss);
      data[i + 3] = alpha * 255;
    }
  }
}

export default function RugbyBall() {
  const canvas = useRef(null);
  const shadow = useRef(null);
  const kick = useRef(() => {});

  useEffect(() => {
    const element = canvas.current;
    const context = element.getContext("2d");
    const still = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    let W = 0;
    let image = null;

    // État du ballon : vrille, culbute, saut, inclinaison vers la souris.
    let spin = 0;
    let spinSpeed = SPIN;
    let flip = 0;
    let flipTarget = 0;
    let hop = 0;
    let hopSpeed = 0;
    let yaw = 0;
    let pitch = 0.3;
    let aimYaw = 0;
    let aimPitch = 0.3;
    let time = 0;

    function resize() {
      const dpr = Math.min(window.devicePixelRatio || 1, 2);
      const size = Math.round(element.clientWidth * dpr);
      if (size === W || size === 0) return;
      W = size;
      element.width = W;
      element.height = W;
      image = context.createImageData(W, W);
      draw();
    }

    function draw() {
      if (!image) return;
      const R = multiply(multiply(multiply(rotX(pitch), rotY(yaw)), rotZ(ROLL + flip)), rotX(spin));
      render(image, W, R);
      context.putImageData(image, 0, 0);
      // Le ballon monte, l'ombre rétrécit et pâlit.
      const lift = hop + 6 * Math.sin(time * 1.5);
      element.style.transform = `translateY(${-lift}px)`;
      const scale = Math.max(0.45, 1 - lift / (element.clientWidth * 0.65));
      shadow.current.style.transform = `scale(${scale})`;
      shadow.current.style.opacity = String(scale);
    }

    const observer = new ResizeObserver(resize);
    observer.observe(element);
    resize();
    if (still) return () => observer.disconnect();

    kick.current = () => {
      if (hop > 20) return;
      hopSpeed = KICK * element.clientWidth;
      spinSpeed = 18;
      flipTarget += 2 * Math.PI;
    };

    function onMove(event) {
      const box = element.getBoundingClientRect();
      const x = (event.clientX - (box.left + box.width / 2)) / 600;
      const y = (event.clientY - (box.top + box.height / 2)) / 600;
      aimYaw = Math.max(-1, Math.min(1, x)) * 0.7;
      aimPitch = 0.3 + Math.max(-1, Math.min(1, y)) * 0.45;
    }
    window.addEventListener("pointermove", onMove);

    let frame = 0;
    let last = performance.now();
    function tick(now) {
      const dt = Math.min(0.05, (now - last) / 1000);
      last = now;
      time += dt;
      spinSpeed += (SPIN - spinSpeed) * Math.min(1, dt * 1.2);
      spin += spinSpeed * dt;
      flip += (flipTarget - flip) * Math.min(1, dt * 4);
      yaw += (aimYaw - yaw) * Math.min(1, dt * 3);
      pitch += (aimPitch - pitch) * Math.min(1, dt * 3);
      if (hop > 0 || hopSpeed > 0) {
        hopSpeed -= GRAVITY * element.clientWidth * dt;
        hop += hopSpeed * dt;
        // Retombée : un petit rebond, puis il se pose.
        if (hop <= 0) {
          hop = 0;
          hopSpeed = hopSpeed < -element.clientWidth * 0.5 ? -hopSpeed * 0.3 : 0;
        }
      }
      draw();
      frame = requestAnimationFrame(tick);
    }
    frame = requestAnimationFrame(tick);

    return () => {
      cancelAnimationFrame(frame);
      window.removeEventListener("pointermove", onMove);
      observer.disconnect();
    };
  }, []);

  return (
    <div className="ball" aria-hidden="true">
      <span className="ball__shadow" ref={shadow} />
      <canvas className="ball__canvas" ref={canvas} onClick={() => kick.current()} />
    </div>
  );
}
