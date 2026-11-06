// Le terrain 2D du match en direct, vu de dessus, en mètres : x de 0 (notre ligne d'essai)
// à 100 (la leur), en-buts de 10 m au-delà ; y de 0 à 70 d'une ligne de touche à l'autre.
// Notre équipe (« us ») attaque toujours vers x = 100, l'adversaire (« them ») vers x = 0.
// Un joueur se repère par son équipe et la place qu'il occupe (1 à 15) : « us9 », « them10 ».

export const LENGTH = 100;
export const WIDTH = 70;
export const IN_GOAL = 10;
export const MID_Y = WIDTH / 2;
// Les perches : 5,6 m entre les poteaux.
export const POST_GAP = 5.6;

export const FORWARDS = [1, 2, 3, 4, 5, 6, 7, 8];
export const BACKS = [9, 10, 11, 12, 13, 14, 15];
export const NUMBERS = [...FORWARDS, ...BACKS];

export const clamp = (x, a = 0, b = 1) => Math.min(b, Math.max(a, x));
export const lerp = (a, b, k) => a + (b - a) * k;
export const smooth = (k) => {
  const c = clamp(k);
  return c * c * (3 - 2 * c);
};
export const dist = (a, b) => Math.hypot(a[0] - b[0], a[1] - b[1]);
export const mixPoint = (a, b, k) => [lerp(a[0], b[0], k), lerp(a[1], b[1], k)];

export const other = (team) => (team === "us" ? "them" : "us");
// Le sens de l'attaque d'une équipe, sur x.
export const dir = (team) => (team === "us" ? 1 : -1);
// La ligne d'essai qu'attaque une équipe.
export const goalOf = (team) => (team === "us" ? LENGTH : 0);
// x à `m` mètres de la ligne qu'attaque `team` ; et dans l'autre sens.
export const fromGoal = (team, m) => goalOf(team) - dir(team) * m;
export const toGoal = (team, x) => (goalOf(team) - x) * dir(team);

export const keyOf = (team, number) => `${team}${number}`;
export const teamOf = (key) => (key.startsWith("us") ? "us" : "them");
export const numberOf = (key) => Number(key.replace(/\D/g, ""));
export const isForward = (key) => numberOf(key) <= 8;

// La gauche d'une équipe (côté de son ailier 11), sur y : face à x = 100, la gauche est
// vers y = 0 ; face à x = 0, vers y = 70.
export const leftOf = (team) => (team === "us" ? -1 : 1);
// L'ailier d'une équipe du côté `side` (+1 : vers y = 70, -1 : vers y = 0).
export const wingOn = (team, side) => (side === leftOf(team) ? 11 : 14);

// Tirage rejouable (mulberry32) : la même minute se montre toujours pareil.
export function seeded(seed) {
  let a = Math.floor(seed) >>> 0;
  return () => {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

// Dans les limites du dessin : le terrain, ses en-buts, un pas hors des touches.
export const clampX = (x) => clamp(x, -IN_GOAL + 0.8, LENGTH + IN_GOAL - 0.8);
export const clampY = (y, margin = 0.9) => clamp(y, margin, WIDTH - margin);
export const clampPoint = ([x, y], margin) => [clampX(x), clampY(y, margin)];
