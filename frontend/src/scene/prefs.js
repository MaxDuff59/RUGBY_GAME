import { useEffect, useState } from "react";

// Quand une décision en match se joue en scène 3D plutôt que dans la fenêtre de texte.
// Ce module ne charge pas three.js : les pages l'importent sans alourdir leur paquet.
//
// Une part des décisions seulement (SCENE_SHARE), tirée au hasard à l'ouverture de
// chacune et gardée jusqu'à sa fin : les scènes restent un moment, pas la règle. Jamais
// sans WebGL, ni quand le système demande moins d'animations, ni quand le joueur a coupé
// « Scènes 3D » ; seulement pour les situations qui ont leur scène (SCENE_SITUATIONS).

export const SCENE_SHARE = 1 / 3;

// Les situations des dilemmes (engine/dilemmas.py) qui ont leur scène ; le choix
// crucial a toujours la sienne.
export const SCENE_SITUATIONS = new Set(["kick", "one_on_one", "tackle", "try_line", "two_on_one"]);

const KEY = "rugby.scenes";
const DEFAULTS = { scenes: true, sound: true };
const CHANGE = "rugby-scenes-change";

export function readPrefs() {
  try {
    return { ...DEFAULTS, ...JSON.parse(localStorage.getItem(KEY)) };
  } catch {
    return { ...DEFAULTS };
  }
}

export function writePrefs(change) {
  const next = { ...readPrefs(), ...change };
  try {
    localStorage.setItem(KEY, JSON.stringify(next));
  } catch {
    // Stockage refusé (navigation privée) : le réglage vaut pour la page.
  }
  window.dispatchEvent(new CustomEvent(CHANGE, { detail: next }));
  return next;
}

// Les réglages, tenus à jour quand ils changent ailleurs dans la page.
export function useScenePrefs() {
  const [prefs, setPrefs] = useState(readPrefs);
  useEffect(() => {
    const update = () => setPrefs(readPrefs());
    window.addEventListener(CHANGE, update);
    window.addEventListener("storage", update);
    return () => {
      window.removeEventListener(CHANGE, update);
      window.removeEventListener("storage", update);
    };
  }, []);
  return [prefs, (change) => setPrefs(writePrefs(change))];
}

let webgl = null;
function hasWebGL() {
  if (webgl === null) {
    try {
      const canvas = document.createElement("canvas");
      const context = canvas.getContext("webgl2");
      webgl = Boolean(context);
      context?.getExtension("WEBGL_lose_context")?.loseContext();
    } catch {
      webgl = false;
    }
  }
  return webgl;
}

const reducedMotion = () => window.matchMedia?.("(prefers-reduced-motion: reduce)").matches ?? false;

// Le tirage de chaque décision (par match, minute et sorte), gardé tant que la page vit.
const draws = new Map();

// Vrai si la décision `key` se joue en scène. `situation` : celle d'un dilemme (null
// pour le choix crucial). `prefs.always` (sans interface, pour les essais) : à chaque fois.
export function wantsScene(key, situation = null) {
  if (situation !== null && !SCENE_SITUATIONS.has(situation)) return false;
  const prefs = readPrefs();
  if (!prefs.scenes || reducedMotion() || !hasWebGL()) return false;
  if (!draws.has(key)) draws.set(key, Boolean(prefs.always) || Math.random() < SCENE_SHARE);
  return draws.get(key);
}
