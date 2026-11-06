import { IN_GOAL, LENGTH, WIDTH, clamp, lerp, smooth } from "./geometry.js";

// La ligne de temps d'une minute montrée sur le terrain 2D : pour chaque joueur, ses
// positions clés dans le temps (en ms) ; pour le ballon, qui le tient ou où il vole ;
// et en marches d'escalier les joueurs au sol, le sauteur porté en touche, la légende
// et le joueur mis en avant. Les actions (`beat`) s'écrivent à la suite les unes des
// autres, chacune en temps relatif de 0 à 1.
//
// Un ballon se décrit par `{ holder: clé }` (dans les mains d'un joueur) ou
// `{ at: [x, y], h }` (posé, ou en vol jusqu'à ce point, `h` : hauteur de la cloche, en
// mètres). Entre deux états, il vole de l'un à l'autre : une passe, un coup de pied.

// Les joueurs qui entrent en jeu (retour du banc des pénalités) arrivent de la touche.
const BENCH = [50, 72];

// Un pas lissé, ni saccadé ni trop mou entre deux positions clés.
const ease = (k) => 0.35 * k + 0.65 * smooth(k);

function insert(list, entry) {
  let i = list.length;
  while (i > 0 && list[i - 1][0] > entry[0]) i -= 1;
  if (i > 0 && Math.abs(list[i - 1][0] - entry[0]) < 1e-6) list[i - 1] = entry;
  else list.splice(i, 0, entry);
}

function step(list, t) {
  let value = list[0][1];
  for (const [at, v] of list) {
    if (at <= t + 1e-6) value = v;
    else break;
  }
  return value;
}

export class Timeline {
  // `start` : { pos: { clé: [x, y] }, ball, down, lift, caption, focus }.
  constructor(start) {
    this.tracks = {};
    for (const [key, p] of Object.entries(start.pos)) this.tracks[key] = [[0, p[0], p[1]]];
    this.balls = [[0, start.ball ?? null]];
    this.downs = [[0, start.down ?? []]];
    this.lifts = [[0, start.lift ?? null]];
    this.captions = [[0, start.caption ?? null]];
    this.focuses = [[0, start.focus ?? null]];
    this.gones = [[0, start.gone ?? []]];
    this.length = 0;
    this.beats = [];
  }

  posAt(key, t) {
    const track = this.tracks[key];
    if (!track) return null;
    if (t <= track[0][0]) return [track[0][1], track[0][2]];
    for (let i = 1; i < track.length; i++) {
      if (t <= track[i][0]) {
        const a = track[i - 1];
        const b = track[i];
        const k = ease((t - a[0]) / Math.max(1e-6, b[0] - a[0]));
        return [lerp(a[1], b[1], k), lerp(a[2], b[2], k)];
      }
    }
    const last = track[track.length - 1];
    return [last[1], last[2]];
  }

  // Où est un ballon décrit par `spec` à l'instant `t`.
  resolve(spec, t) {
    if (!spec) return null;
    if (spec.holder) return this.posAt(spec.holder, t);
    return spec.at;
  }

  ballAt(t) {
    const balls = this.balls;
    let i = 0;
    while (i + 1 < balls.length && balls[i + 1][0] <= t) i += 1;
    const [t0, spec0] = balls[i];
    const next = balls[i + 1];
    if (!next || !spec0) {
      const p = this.resolve(spec0, t);
      return p ? { x: p[0], y: p[1], h: spec0?.hover ?? 0 } : null;
    }
    const [t1, spec1] = next;
    if (spec0.holder && spec0.holder === spec1.holder) {
      const p = this.resolve(spec0, t);
      return { x: p[0], y: p[1], h: 0 };
    }
    const from = this.resolve(spec0, t0);
    const to = this.resolve(spec1, t1);
    if (!from || !to) return null;
    const k = clamp((t - t0) / Math.max(1e-6, t1 - t0));
    const h = spec1.h ?? (spec1.holder ? 0.5 : 0);
    return { x: lerp(from[0], to[0], k), y: lerp(from[1], to[1], k), h: 4 * h * k * (1 - k) };
  }

  stateAt(t) {
    const pos = {};
    for (const key of Object.keys(this.tracks)) pos[key] = this.posAt(key, t);
    return {
      pos,
      ball: this.ballAt(t),
      down: step(this.downs, t),
      lift: step(this.lifts, t),
      caption: step(this.captions, t),
      focus: step(this.focuses, t),
      gone: step(this.gones, t),
    };
  }

  // La dernière description du ballon (pour enchaîner une action sur la précédente).
  lastBall() {
    return this.balls[this.balls.length - 1][1];
  }

  _key(key, t, raw) {
    if (!key || !raw) return;
    // Dans le dessin : le terrain, ses en-buts, un pas au-delà des touches.
    const p = [clamp(raw[0], -IN_GOAL + 0.6, LENGTH + IN_GOAL - 0.6), clamp(raw[1], -2.8, WIDTH + 2.8)];
    if (!this.tracks[key]) {
      // Un joueur qui n'était pas là : il entre de la touche au début de l'action.
      this.tracks[key] = [[0, BENCH[0], BENCH[1]]];
      const begin = this.beats.length ? this.length : 0;
      insert(this.tracks[key], [begin, BENCH[0], BENCH[1]]);
    }
    insert(this.tracks[key], [t, p[0], p[1]]);
  }

  // Une action de `ms` millisecondes (au rythme normal) : renvoie de quoi l'écrire.
  // `essential` : elle se montre toujours en entier (un essai, une pénalité) ; les
  // autres se raccourcissent quand le chrono va vite.
  beat(ms, { essential = false, label = null } = {}) {
    const t0 = this.length;
    const start = this.stateAt(t0);
    for (const key of Object.keys(this.tracks)) insert(this.tracks[key], [t0, ...start.pos[key]]);
    const T = (t) => t0 + clamp(t) * ms;
    const timeline = this;
    const writer = {
      start,
      ms,
      // La position d'un joueur à l'instant t de l'action (d'après ce qui est déjà écrit).
      pos: (key, t = 0) => timeline.posAt(key, T(t)) ?? start.pos[key] ?? null,
      at(t, key, p) {
        timeline._key(key, T(t), p);
        return writer;
      },
      set(t, positions) {
        for (const [key, p] of Object.entries(positions)) timeline._key(key, T(t), p);
        return writer;
      },
      // Le joueur reste où il est jusqu'à t (il ne part qu'après).
      hold(t, key) {
        const p = timeline.posAt(key, T(t));
        if (p) timeline._key(key, T(t), p);
        return writer;
      },
      holdAll(t, except = []) {
        for (const key of Object.keys(timeline.tracks)) if (!except.includes(key)) writer.hold(t, key);
        return writer;
      },
      ball(t, spec) {
        insert(timeline.balls, [T(t), spec]);
        return writer;
      },
      down(t, keys) {
        insert(timeline.downs, [T(t), keys]);
        return writer;
      },
      lift(t, key) {
        insert(timeline.lifts, [T(t), key]);
        return writer;
      },
      caption(t, text) {
        insert(timeline.captions, [T(t), text]);
        return writer;
      },
      focus(t, key) {
        insert(timeline.focuses, [T(t), key]);
        return writer;
      },
      gone(t, keys) {
        insert(timeline.gones, [T(t), keys]);
        return writer;
      },
      done() {
        timeline.length = t0 + ms;
        timeline.beats.push({ from: t0, to: t0 + ms, essential, label });
        return timeline;
      },
    };
    return writer;
  }
}

// Comment jouer la ligne de temps dans le temps réel : `tempo` (×1 au rythme normal,
// plus vite quand le chrono s'accélère) et `budget`, le temps d'une minute de jeu en ms.
// Les actions essentielles se jouent toujours en entier ; les autres se resserrent dans
// ce qui reste du budget, ou se résument à un fondu vers leur fin.
// Renvoie des segments `{ ms, from, to }` (un passage de la ligne de temps) ou
// `{ ms, from, to, tween: true }` (un fondu direct de l'état `from` à l'état `to`).
export function schedule(timeline, { tempo = 1, budget = Infinity, reduced = false }) {
  const beats = timeline.beats;
  if (!beats.length) return { segments: [], total: 0 };
  if (reduced) {
    const end = timeline.length;
    return { segments: [{ ms: 0, from: end, to: end, tween: true }], total: 0 };
  }
  const essentialMs = beats.filter((b) => b.essential).reduce((sum, b) => sum + (b.to - b.from) / tempo, 0);
  let left = Math.max(0, budget - essentialMs);
  const segments = [];
  let i = 0;
  while (i < beats.length) {
    if (beats[i].essential) {
      segments.push({ ms: (beats[i].to - beats[i].from) / tempo, from: beats[i].from, to: beats[i].to });
      i += 1;
      continue;
    }
    // Les actions secondaires qui se suivent, ensemble.
    let j = i;
    while (j < beats.length && !beats[j].essential) j += 1;
    const from = beats[i].from;
    const to = beats[j - 1].to;
    // Ce qu'il reste à donner aux suivantes : chaque groupe prend sa part.
    const later = beats.slice(j).filter((b) => !b.essential).reduce((sum, b) => sum + (b.to - b.from), 0);
    const natural = (to - from) / tempo;
    const share = later > 0 ? left * ((to - from) / (to - from + later)) : left;
    if (natural <= share) {
      segments.push({ ms: natural, from, to });
      left -= natural;
    } else if (natural <= share * 2.2 && share >= 260) {
      segments.push({ ms: share, from, to });
      left -= share;
    } else {
      const ms = Math.max(140, Math.min(share, 420));
      segments.push({ ms, from, to, tween: true });
      left = Math.max(0, left - ms);
    }
    i = j;
  }
  return { segments, total: segments.reduce((sum, s) => sum + s.ms, 0) };
}

// L'état à montrer `elapsed` ms après le début du programme `plan`.
export function frameAt(timeline, plan, elapsed, cache) {
  let t = elapsed;
  for (const segment of plan.segments) {
    if (t <= segment.ms || segment === plan.segments[plan.segments.length - 1]) {
      const k = segment.ms > 0 ? clamp(t / segment.ms) : 1;
      if (!segment.tween) return timeline.stateAt(lerp(segment.from, segment.to, k));
      const a = cached(timeline, segment.from, cache);
      const b = cached(timeline, segment.to, cache);
      return blend(a, b, smooth(k));
    }
    t -= segment.ms;
  }
  return timeline.stateAt(timeline.length);
}

function cached(timeline, t, cache) {
  if (!cache.has(t)) cache.set(t, timeline.stateAt(t));
  return cache.get(t);
}

// Un fondu entre deux états.
export function blend(a, b, k) {
  const pos = {};
  for (const key of new Set([...Object.keys(a.pos), ...Object.keys(b.pos)])) {
    const p = a.pos[key] ?? b.pos[key];
    const q = b.pos[key] ?? a.pos[key];
    pos[key] = [lerp(p[0], q[0], k), lerp(p[1], q[1], k)];
  }
  let ball = b.ball;
  if (a.ball && b.ball) {
    ball = { x: lerp(a.ball.x, b.ball.x, k), y: lerp(a.ball.y, b.ball.y, k), h: lerp(a.ball.h, b.ball.h, k) };
  }
  const late = k > 0.5 ? b : a;
  return { pos, ball, down: late.down, lift: late.lift, caption: b.caption, focus: b.focus, gone: late.gone };
}
