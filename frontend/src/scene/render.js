import * as THREE from "three";

import { PALETTE_SIZE, oklabToLinear } from "./palette.js";

// Rendu des scènes de match : la scène est dessinée en basse résolution (quelques
// centaines de lignes) dans une cible hors écran avec sa profondeur, puis une passe
// plein écran tire les contours de la profondeur, ramène chaque pixel à la palette
// (la couleur la plus proche en OKLab, avec un tramage ordonné léger) et écrit le
// résultat dans un canevas de la même taille, que la page agrandit en pixels nets
// (`image-rendering: pixelated`).

const VERTEX = /* glsl */ `
  varying vec2 vUv;
  void main() {
    vUv = uv;
    gl_Position = vec4(position.xy, 0.0, 1.0);
  }
`;

const FRAGMENT = /* glsl */ `
  precision highp float;
  uniform sampler2D tColor;
  uniform sampler2D tDepth;
  uniform vec2 uTexel;
  uniform float uNear;
  uniform float uFar;
  uniform float uExposure;
  uniform vec3 uInk;
  uniform vec3 uLab[${PALETTE_SIZE}];
  uniform vec3 uRgb[${PALETTE_SIZE}];
  varying vec2 vUv;

  float linearDepth(vec2 uv) {
    float d = texture2D(tDepth, uv).x;
    float z = d * 2.0 - 1.0;
    return 2.0 * uNear * uFar / (uFar + uNear - z * (uFar - uNear));
  }

  vec3 toOklab(vec3 c) {
    float l = pow(max(0.0, 0.4122214708 * c.r + 0.5363325363 * c.g + 0.0514459929 * c.b), 1.0 / 3.0);
    float m = pow(max(0.0, 0.2119034982 * c.r + 0.6806995451 * c.g + 0.1073969566 * c.b), 1.0 / 3.0);
    float s = pow(max(0.0, 0.0883024619 * c.r + 0.2817188376 * c.g + 0.6299787005 * c.b), 1.0 / 3.0);
    return vec3(
      0.2104542553 * l + 0.793617785 * m - 0.0040720468 * s,
      1.9779984951 * l - 2.428592205 * m + 0.4505937099 * s,
      0.0259040371 * l + 0.7827717662 * m - 0.808675766 * s
    );
  }

  // Tramage ordonné 4 × 4.
  float bayer(vec2 p) {
    vec2 q = mod(floor(p), 4.0);
    float i = q.x + q.y * 4.0;
    float v = 0.0;
    if (i == 0.0) v = 0.0; else if (i == 1.0) v = 8.0; else if (i == 2.0) v = 2.0; else if (i == 3.0) v = 10.0;
    else if (i == 4.0) v = 12.0; else if (i == 5.0) v = 4.0; else if (i == 6.0) v = 14.0; else if (i == 7.0) v = 6.0;
    else if (i == 8.0) v = 3.0; else if (i == 9.0) v = 11.0; else if (i == 10.0) v = 1.0; else if (i == 11.0) v = 9.0;
    else if (i == 12.0) v = 15.0; else if (i == 13.0) v = 7.0; else if (i == 14.0) v = 13.0; else v = 5.0;
    return v / 16.0 - 0.5;
  }

  void main() {
    vec3 color = texture2D(tColor, vUv).rgb * uExposure;
    // Courbe douce (ACES, approximation de Narkowicz) : les projecteurs ne brûlent pas.
    color = clamp((color * (2.51 * color + 0.03)) / (color * (2.43 * color + 0.59) + 0.14), 0.0, 1.0);

    // Contours : le pixel est plus proche que l'un de ses voisins, d'assez loin.
    float center = linearDepth(vUv);
    float edge = 0.0;
    float gap = max(0.35, center * 0.06);
    edge = max(edge, step(gap, linearDepth(vUv + vec2(uTexel.x, 0.0)) - center));
    edge = max(edge, step(gap, linearDepth(vUv - vec2(uTexel.x, 0.0)) - center));
    edge = max(edge, step(gap, linearDepth(vUv + vec2(0.0, uTexel.y)) - center));
    edge = max(edge, step(gap, linearDepth(vUv - vec2(0.0, uTexel.y)) - center));
    color = mix(color, uInk, edge * 0.85);

    vec3 lab = toOklab(color);
    lab.x += bayer(gl_FragCoord.xy) * 0.035;
    float best = 1e9;
    vec3 chosen = uRgb[0];
    for (int i = 0; i < ${PALETTE_SIZE}; i++) {
      vec3 d = lab - uLab[i];
      d.yz *= 1.4; // la teinte compte un peu plus que la clarté
      float e = dot(d, d);
      if (e < best) {
        best = e;
        chosen = uRgb[i];
      }
    }
    gl_FragColor = vec4(chosen, 1.0);
  }
`;

const srgb = (c) => (c <= 0.0031308 ? c * 12.92 : 1.055 * c ** (1 / 2.4) - 0.055);

export function createPipeline(renderer, palette) {
  const halfFloat =
    renderer.extensions.has("EXT_color_buffer_half_float") || renderer.extensions.has("EXT_color_buffer_float");
  const depthTexture = new THREE.DepthTexture(1, 1);
  const target = new THREE.WebGLRenderTarget(1, 1, {
    minFilter: THREE.NearestFilter,
    magFilter: THREE.NearestFilter,
    type: halfFloat ? THREE.HalfFloatType : THREE.UnsignedByteType,
    depthTexture,
  });
  const material = new THREE.ShaderMaterial({
    vertexShader: VERTEX,
    fragmentShader: FRAGMENT,
    depthTest: false,
    depthWrite: false,
    uniforms: {
      tColor: { value: target.texture },
      tDepth: { value: depthTexture },
      uTexel: { value: new THREE.Vector2() },
      uNear: { value: 0.1 },
      uFar: { value: 500 },
      uExposure: { value: 1 },
      uInk: { value: new THREE.Vector3(0.008, 0.009, 0.011) },
      uLab: { value: [] },
      uRgb: { value: [] },
    },
  });
  const quad = new THREE.Mesh(new THREE.PlaneGeometry(2, 2), material);
  quad.frustumCulled = false;
  const quadScene = new THREE.Scene();
  quadScene.add(quad);
  const quadCamera = new THREE.OrthographicCamera(-1, 1, 1, -1, 0, 1);

  const setPalette = (colors) => {
    material.uniforms.uLab.value = colors.map(([L, a, b]) => new THREE.Vector3(L, a, b));
    material.uniforms.uRgb.value = colors.map((lab) => new THREE.Vector3(...oklabToLinear(lab).map(srgb)));
  };
  setPalette(palette);

  return {
    // Taille du canevas en pixels de la scène (déjà réduite).
    setSize(width, height) {
      renderer.setSize(width, height, false);
      target.setSize(width, height);
      material.uniforms.uTexel.value.set(1 / width, 1 / height);
    },
    setPalette,
    set exposure(value) {
      material.uniforms.uExposure.value = value;
    },
    render(scene, camera) {
      material.uniforms.uNear.value = camera.near;
      material.uniforms.uFar.value = camera.far;
      renderer.setRenderTarget(target);
      renderer.render(scene, camera);
      renderer.setRenderTarget(null);
      renderer.render(quadScene, quadCamera);
    },
    dispose() {
      target.dispose();
      depthTexture.dispose();
      material.dispose();
      quad.geometry.dispose();
    },
  };
}
