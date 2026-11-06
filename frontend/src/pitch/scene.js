import {
  MID_Y,
  POST_GAP,
  WIDTH,
  clamp,
  clampPoint,
  clampX,
  clampY,
  dir,
  dist,
  fromGoal,
  goalOf,
  keyOf,
  numberOf,
  other,
  seeded,
  teamOf,
  toGoal,
} from "./geometry.js";
import { conversionSetup, kickAtGoal, kickoff, lineout, maulCluster, openPlay, scrum } from "./formations.js";
import { Timeline } from "./timeline.js";

// Les actions d'une minute, écrites sur la ligne de temps : chaque méthode joue une
// action (un temps de jeu, une touche, un essai...) depuis l'état où la précédente a
// laissé le terrain, et tient à jour qui a le ballon (`att`) et où (`loc`).

// Durées au rythme normal (×1), en ms.
const MS = {
  phase: 1150,
  break: 1750,
  kickoff: 1900,
  exchange: 1850,
  lineout: 1900,
  card: 1200,
  conversion: 1900,
  penaltyGoal: 2000,
  touchKick: 1300,
  maul: 2300,
  scrum: 2100,
  tap: 1700,
  drop: 1500,
  held: 1800,
  effect: 1500,
};

const POSTS_X = (team) => goalOf(team) + dir(team) * 4;

export class Scene {
  constructor(ctx, start, { att, loc, seed }) {
    this.ctx = ctx;
    this.present = ctx.present;
    this.tl = new Timeline(start);
    this.att = att;
    this.loc = { ...loc };
    this.R = seeded(seed);
    this.seed = seed;
    this.ruck = start.down?.[0] ?? null;
    this.cleaners = [];
    this.gone = new Set(start.gone ?? []);
    this.tryY = MID_Y;
    this.sit = null; // la situation de dilemme en place, s'il y en a une
    this.layout = Math.floor(this.R() * 1e6); // tirage des placements, tant que le ballon ne bouge pas
  }

  rnd(a = 0, b = 1) {
    return a + (b - a) * this.R();
  }

  now() {
    return this.tl.stateAt(this.tl.length);
  }

  name(key) {
    return this.ctx.name(key);
  }

  club(team) {
    return this.ctx.clubName(team);
  }

  moveBall(x, y) {
    this.loc = { x: clampX(x), y: clampY(y, 5) };
    this.layout = Math.floor(this.R() * 1e6);
  }

  // --- Placement ------------------------------------------------------------------------

  // Le ruck au point du ballon, `att` en possession, prêt pour `opts` (carrier, tackler...).
  open(att, opts = {}) {
    return openPlay(this.present, {
      att,
      bx: this.loc.x,
      by: this.loc.y,
      ruck: this.ruck,
      cleaners: this.cleaners,
      seed: this.layout,
      ...opts,
    });
  }

  // Tout le monde rejoint `formation` (une course, plus ou moins longue). Les joueurs sortis
  // (carton, blessure sans remplaçant) quittent le terrain par la touche la plus proche.
  align(formation, { ms = null, essential = false, caption = undefined } = {}) {
    const state = this.now();
    let far = 0;
    for (const [key, p] of Object.entries(formation.pos)) {
      const q = state.pos[key];
      far = Math.max(far, q ? dist(p, q) : 30);
    }
    const leaving = Object.keys(state.pos).filter((key) => key !== "ref" && !formation.pos[key] && !this.gone.has(key));
    const back = Object.keys(formation.pos).filter((key) => this.gone.has(key));
    const ballBefore = this.tl.lastBall();
    const sameBall = JSON.stringify(ballBefore) === JSON.stringify(formation.ball ?? ballBefore);
    if (far < 0.9 && !leaving.length && !back.length && sameBall) {
      this.ruck = formation.down?.[0] ?? null;
      return;
    }
    const b = this.tl.beat(ms ?? clamp(320 + far * 24, 380, 1200), { essential, label: "align" });
    for (const [key, p] of Object.entries(formation.pos)) b.at(1, key, p);
    for (const key of leaving) {
      const p = state.pos[key];
      b.at(1, key, [p[0], p[1] < MID_Y ? -2.4 : WIDTH + 2.4]);
      this.gone.add(key);
    }
    for (const key of back) this.gone.delete(key);
    if (back.length) b.gone(0, [...this.gone]);
    if (leaving.length) b.gone(1, [...this.gone]);
    if (formation.ball) b.ball(1, formation.ball);
    const keep = (state.down ?? []).filter((key) => (formation.down ?? []).includes(key));
    b.down(0.12, keep);
    b.down(0.92, formation.down ?? []);
    b.lift(0, null);
    if (caption !== undefined) b.caption(0, caption);
    b.done();
    this.ruck = formation.down?.[0] ?? null;
  }

  // --- Passes ---------------------------------------------------------------------------

  // Les passeurs jusqu'au porteur `carrier`, depuis le demi de mêlée : une passe va vers
  // l'arrière, le receveur arrive lancé derrière le passeur.
  chain(formation, carrier) {
    const att = teamOf(carrier);
    const free = (key) => formation.pos[key] && !formation.down.includes(key) && !(formation.bound ?? []).includes(key);
    const nine = [9, 7, 10, 6].map((n) => keyOf(att, n)).find(free);
    if (!nine || carrier === nine) return nine ? [nine] : [carrier];
    const n = numberOf(carrier);
    if (n <= 8 || n === 10) return [nine, carrier];
    const ten = keyOf(att, 10);
    const via = free(ten) && ten !== carrier && ten !== nine ? [nine, ten] : [nine];
    const blind = formation.pos[carrier] && (formation.pos[carrier][1] - formation.by) * formation.o < 0;
    if (blind && (n === 11 || n === 14)) return [nine, carrier];
    const thirteen = keyOf(att, 13);
    if ((n === 11 || n === 14) && free(thirteen)) return [...via, thirteen, carrier];
    return [...via, carrier];
  }

  // Joue les passes de `keys` (le premier a le ballon à `t0`) ; rend l'instant où le
  // dernier l'attrape et où il est alors.
  passes(b, keys, t0 = 0.08) {
    const att = teamOf(keys[0]);
    const d = dir(att);
    let t = t0;
    let carrierAt = b.pos(keys[0], t0);
    b.ball(t, { holder: keys[0] });
    b.at(t, keys[0], carrierAt);
    for (let i = 1; i < keys.length; i++) {
      const passer = keys[i - 1];
      const receiver = keys[i];
      const release = t + 0.035;
      const from = b.pos(passer, t);
      const releaseAt = [from[0] + d * 0.8, from[1]];
      b.at(release, passer, releaseAt);
      const catchT = release + 0.075;
      const start = b.pos(receiver, 0);
      let x = start[0] + d * 1.8;
      if ((x - releaseAt[0]) * d > -0.9) x = releaseAt[0] - d * 0.9;
      const catchAt = [x, start[1] + (start[1] - releaseAt[1]) * 0.04];
      b.at(catchT, receiver, catchAt);
      b.ball(release, { holder: passer });
      b.ball(catchT, { holder: receiver, h: 0.6 });
      // Le passeur suit, ralentit.
      b.at(catchT + 0.12, passer, [releaseAt[0] + d * 1.0, releaseAt[1]]);
      t = catchT;
      carrierAt = catchAt;
    }
    return { t, at: carrierAt };
  }

  // Les défenseurs montent (`rush` mètres) et se resserrent vers `toward` à l'instant `t` ;
  // les attaquants suivent sans dépasser le porteur.
  pressure(b, t, att, { rush = 2.2, toward = null, follow = 1.6, frontX = null, except = [] }) {
    const d = dir(att);
    const state = b.start;
    for (const [key, p] of Object.entries(state.pos)) {
      if (key === "ref" || except.includes(key) || this.gone.has(key)) continue;
      if (teamOf(key) === att) {
        let x = p[0] + d * follow;
        if (frontX !== null && (x - frontX) * d > -1.2) x = frontX - d * 1.2;
        b.at(t, key, [x, p[1]]);
      } else {
        const y = toward ? p[1] + (toward[1] - p[1]) * 0.15 : p[1];
        b.at(t, key, [p[0] - d * rush, y]);
      }
    }
  }

  // Les plus proches de `point` dans `team`, sauf `except`.
  nearest(b, team, point, t, count = 1, except = []) {
    return Object.keys(b.start.pos)
      .filter((key) => key !== "ref" && teamOf(key) === team && !except.includes(key) && !this.gone.has(key))
      .map((key) => [key, dist(b.pos(key, t), point)])
      .sort((a, b2) => a[1] - b2[1])
      .slice(0, count)
      .map(([key]) => key);
  }

  // Les deux premiers soutiens sur un ruck en `point` : les plus proches, les avants
  // d'abord, jamais le demi de mêlée ni l'ouvreur (ils servent le ballon suivant).
  support(b, team, point, t, except = []) {
    const skip = [...except, keyOf(team, 9), keyOf(team, 10)];
    const near = this.nearest(b, team, point, t, 5, skip);
    const close = near.filter((key) => dist(b.pos(key, t), point) < 12);
    return [...close.filter((key) => numberOf(key) <= 8), ...close.filter((key) => numberOf(key) > 8), ...near]
      .filter((key, i, list) => list.indexOf(key) === i)
      .slice(0, 2);
  }

  // Tout le monde rejoint `formation` à la fin de l'action (sauf `except`).
  settle(b, formation, except = [], t = 1) {
    for (const [key, p] of Object.entries(formation.pos)) if (!except.includes(key)) b.at(t, key, p);
  }

  // --- Le jeu courant -------------------------------------------------------------------

  // Un temps de jeu : le demi de mêlée sert le porteur, qui va au contact.
  // `phase` : { team, carrier, tackler, result, other, carrierId, tacklerId } ;
  // `next` : le temps de jeu suivant (pour s'y placer) ; `gain` : les mètres à prendre.
  phase(phase, { next = null, gain = null } = {}) {
    const att = phase.team;
    const d = dir(att);
    const D = other(att);
    const carrier = phase.carrier;
    if (!this.present[att].has(numberOf(carrier))) return;
    const start = this.open(att, { carrier, tackler: phase.tackler });
    this.align(start);
    const isBreak = phase.result === "break";
    const b = this.tl.beat(isBreak ? MS.break : MS.phase, { label: "phase" });
    b.ball(0, start.ball);
    const keys = this.chain(start, carrier);
    const { t: tCatch, at: catchAt } = this.passes(b, keys, 0.08);
    // Le contact, sur la ligne d'avantage : la défense est montée.
    const tContact = Math.min(tCatch + 0.24, 0.66);
    const contact = [start.bx + d * this.rnd(0.2, 1.3), clampY(catchAt[1] + this.rnd(-1.4, 1.4), 4)];
    let tackler = phase.tackler && b.start.pos[phase.tackler] ? phase.tackler : null;
    tackler ??= this.nearest(b, D, contact, 0, 1)[0];
    b.at(tContact, carrier, contact);
    if (tackler) b.at(tContact, tackler, [contact[0] + d * 0.9, contact[1] + 0.3]);
    this.pressure(b, tContact, att, { toward: contact, frontX: contact[0], except: [carrier, tackler, ...keys] });

    let point = contact;
    let tGround = tContact + 0.07;
    let downed = [carrier];
    let caption;
    const carrierName = this.name(carrier);
    const tacklerName = tackler ? this.name(tackler) : "";
    if (phase.result === "missed" || isBreak) {
      // Le plaqueur manque, le porteur passe.
      b.at(tContact + 0.05, tackler, [contact[0] - d * 0.2, contact[1] - 1.1]);
      const run = gain ?? (isBreak ? this.rnd(18, 30) : this.rnd(5, 8.5));
      const room = Math.max(3, toGoal(att, contact[0]) - 3);
      const ahead = Math.min(run, room);
      const drift = isBreak ? (MID_Y - contact[1]) * this.rnd(0.15, 0.35) : this.rnd(-2, 2);
      point = [contact[0] + d * ahead, clampY(contact[1] + drift, 4)];
      const tCatchUp = isBreak ? 0.8 : Math.min(tContact + 0.17, 0.82);
      const cover = [...(isBreak ? [keyOf(D, 15)] : []), ...this.nearest(b, D, point, tContact, 2, [tackler])].find(
        (key) => b.start.pos[key] && !this.gone.has(key),
      );
      b.at(tCatchUp, carrier, point);
      if (cover) b.at(tCatchUp, cover, [point[0] + d * 0.9, point[1] + 0.4]);
      if (isBreak) {
        const support = this.nearest(b, att, point, tContact, 1, [carrier])[0];
        if (support) b.at(tCatchUp, support, [point[0] - d * 3, point[1] + (MID_Y > point[1] ? 2.2 : -2.2)]);
      }
      tGround = tCatchUp + 0.05;
      downed = [carrier, cover].filter(Boolean);
      b.down(tContact + 0.05, [tackler].filter(Boolean));
      caption = isBreak
        ? `Franchissement de ${carrierName} !`
        : `${carrierName} passe ${tacklerName}, repris plus loin`;
      tackler = cover ?? tackler;
    } else {
      const forward = gain ?? (phase.result === "turnover" ? this.rnd(-0.5, 1) : this.rnd(0.8, 3));
      point = [contact[0] + d * Math.max(-1, Math.min(forward, toGoal(att, contact[0]) - 1.5)), contact[1]];
      b.at(tGround, carrier, point);
      if (tackler) b.at(tGround, tackler, [point[0] + d * 1.0, point[1] + 0.7]);
      downed = [carrier, tackler].filter(Boolean);
      caption = `${carrierName} au contact, plaqué par ${tacklerName}`;
    }
    b.down(tGround, downed);
    b.ball(tGround, { at: [point[0] - d * 0.5, point[1]] });

    // Le ruck se forme ; possession gardée, ou ballon gratté.
    this.moveBall(point[0], point[1]);
    const turnover = phase.result === "turnover";
    const owner = turnover ? D : att;
    const support = this.support(b, owner, point, tGround, [carrier, tackler, phase.other].filter(Boolean));
    if (turnover && phase.other && b.start.pos[phase.other]) {
      b.at(tGround + 0.1, phase.other, [point[0] + d * 0.15, point[1] + 0.2]);
      caption = `${carrierName} plaqué, ballon gratté par ${this.name(phase.other)}`;
    }
    this.ruck = carrier;
    this.cleaners = turnover ? [phase.other, ...support].filter(Boolean) : support;
    const end = this.open(owner, {
      carrier: next?.team === owner ? next.carrier : null,
      tackler: next?.team === owner ? next.tackler : null,
    });
    for (const [i, key] of this.cleaners.slice(0, 2).entries()) {
      if (end.pos[key]) b.at(Math.min(tGround + 0.12 + i * 0.04, 0.95), key, end.pos[key]);
    }
    this.settle(b, end, [carrier]);
    b.at(1, carrier, end.pos[carrier] ?? point);
    b.down(Math.min(tGround + 0.25, 0.97), [carrier]);
    b.caption(Math.max(0, tCatch - 0.05), caption);
    b.focus(0, carrier);
    b.ball(Math.min(tGround + 0.3, 0.98), end.ball);
    b.done();
    this.att = owner;
  }

  // --- Coups de pied --------------------------------------------------------------------

  // Coup d'envoi de `team` : il tape court, les sauteurs adverses captent, un ruck se forme.
  kickoff(team, { caption, ks = this.R() < 0.5 ? 1 : -1 } = {}) {
    const f = kickoff(this.present, { kicker: team, ks });
    this.align(f, { ms: 900 });
    const b = this.tl.beat(MS.kickoff, { label: "kickoff" });
    const d = dir(team);
    const R = other(team);
    const land = [50 + d * this.rnd(12, 16), MID_Y + ks * this.rnd(15, 21)];
    if (f.kicker) {
      b.at(0.18, f.kicker, [50 - d * 0.6, MID_Y - ks * 0.4]);
      b.at(0.4, f.kicker, [50 + d * 3, MID_Y]);
    }
    b.ball(0.2, { at: [50, MID_Y] });
    b.ball(0.62, { at: land, h: 13 });
    const catcher = [4, 5, 6, 7, 8].map((n) => keyOf(R, n)).filter((key) => f.pos[key]).sort((a, c) => dist(f.pos[a], land) - dist(f.pos[c], land))[0];
    for (const [key, p] of Object.entries(f.pos)) {
      if (key === "ref" || key === f.kicker) continue;
      if (teamOf(key) === team) b.at(0.62, key, [p[0] + d * this.rnd(9, 13), p[1] + (land[1] - p[1]) * 0.25]);
      else if (key !== catcher) b.at(0.62, key, [p[0] + (land[0] - p[0]) * 0.25, p[1] + (land[1] - p[1]) * 0.2]);
    }
    if (catcher) {
      b.at(0.58, catcher, land);
      b.lift(0.45, catcher);
      b.ball(0.64, { holder: catcher });
      b.lift(0.74, null);
      b.down(0.84, [catcher]);
    }
    this.moveBall(land[0] - d * 0.6, land[1]);
    this.ruck = catcher ?? null;
    const lifters = catcher ? this.support(b, R, land, 0.6, [catcher]) : [];
    this.cleaners = lifters;
    const end = this.open(R);
    this.settle(b, end);
    b.ball(0.86, end.ball);
    b.caption(0, caption ?? `Coup d'envoi · ${this.club(team)}`);
    b.focus(0, null);
    b.done();
    this.att = R;
  }

  // Un dégagement de l'équipe en possession vers `to` : au pied, chandelle ou long, repris
  // par l'arrière (ou un ailier) ; `touch` : en touche, pour une touche de `to`.
  exchange(to, { touch = false } = {}) {
    const A = this.att;
    if (A === to) return;
    const d = dir(A);
    const start = this.open(A);
    this.align(start);
    const b = this.tl.beat(touch ? MS.touchKick : MS.exchange, { label: "exchange" });
    const deep = toGoal(A, this.loc.x) > 62;
    const nine = this.chain(start, keyOf(A, 9))[0];
    const ten = keyOf(A, 10);
    const kicker = deep || !start.pos[ten] || start.down.includes(ten) || start.bound.includes(ten) ? nine : ten;
    b.ball(0, start.ball);
    b.ball(0.08, { holder: nine });
    let tKick = 0.18;
    if (kicker !== nine) {
      b.ball(0.14, { holder: nine });
      b.ball(0.24, { holder: kicker, h: 0.6 });
      tKick = 0.3;
    }
    const kickAt = b.pos(kicker, tKick);
    b.at(tKick, kicker, kickAt);
    const length = touch ? this.rnd(22, 34) : deep ? this.rnd(28, 38) : this.rnd(30, 42);
    let x = kickAt[0] + d * length;
    x = d > 0 ? Math.min(x, fromGoal(A, 7)) : Math.max(x, fromGoal(A, 7));
    const side = this.loc.y < MID_Y ? 0 : WIDTH;
    const land = touch ? [x, side === 0 ? -0.6 : WIDTH + 0.6] : [x, clampY(MID_Y + this.rnd(-18, 18), 6)];
    const tLand = tKick + (touch ? 0.42 : 0.4);
    b.ball(tKick, { holder: kicker });
    b.ball(tLand, { at: land, h: touch ? 9 : 15 });
    // Les chasseurs montent, la défense recule vers le point de chute.
    for (const [key, p] of Object.entries(start.pos)) {
      if (key === "ref" || key === kicker) continue;
      if (teamOf(key) === A) b.at(tLand, key, [p[0] + d * this.rnd(8, 16), p[1] + (land[1] - p[1]) * 0.2]);
      else b.at(tLand, key, [p[0] + d * this.rnd(7, 12), p[1] + (land[1] - p[1]) * 0.15]);
    }
    b.caption(0, touch ? `Dégagement en touche · ${this.club(A)}` : `Jeu au pied de ${this.name(kicker)}`);
    b.focus(0, kicker);
    if (touch) {
      this.moveBall(land[0], side === 0 ? 3 : WIDTH - 3);
      b.done();
      this.att = to;
      this.ruck = null;
      this.cleaners = [];
      return;
    }
    const receivers = [15, 11, 14, 10].map((n) => keyOf(to, n)).filter((key) => start.pos[key]);
    const receiver = receivers.sort((a, c) => dist(start.pos[a], land) - dist(start.pos[c], land))[0];
    if (!receiver) {
      b.done();
      return;
    }
    b.at(tLand - 0.02, receiver, land);
    b.ball(tLand, { holder: receiver, h: 15 });
    const dt = dir(to);
    const tackleAt = [land[0] + dt * this.rnd(4, 9), clampY(land[1] + this.rnd(-3, 3), 4)];
    const tTackle = Math.min(tLand + 0.2, 0.86);
    b.at(tTackle, receiver, tackleAt);
    const chaser = this.nearest(b, A, tackleAt, tLand, 1)[0];
    if (chaser) b.at(tTackle, chaser, [tackleAt[0] + dt * 0.9, tackleAt[1] + 0.5]);
    b.down(tTackle, [receiver, chaser].filter(Boolean));
    b.ball(tTackle + 0.02, { at: [tackleAt[0] - dt * 0.5, tackleAt[1]] });
    this.moveBall(...tackleAt);
    this.ruck = receiver;
    this.cleaners = this.support(b, to, tackleAt, tTackle, [receiver]);
    const end = this.open(to);
    this.settle(b, end, [receiver]);
    b.at(1, receiver, end.pos[receiver] ?? tackleAt);
    b.down(Math.min(tTackle + 0.12, 0.98), [receiver]);
    b.ball(Math.min(tTackle + 0.1, 0.98), end.ball);
    b.done();
    this.att = to;
  }

  // --- Touche ---------------------------------------------------------------------------

  // Touche lancée par `thrower`, gagnée par `winner` : sauteur porté, ballon au demi de
  // mêlée, puis l'ouvreur au contact.
  lineout({ thrower, winner, jumper }) {
    const x0 = clamp(this.loc.x, 6, 94);
    const side = this.loc.y < MID_Y ? 0 : WIDTH;
    const f = lineout(this.present, { thrower, x0, side });
    this.align(f, { ms: 1000 });
    const b = this.tl.beat(MS.lineout, { label: "lineout" });
    const T = thrower;
    const d = dir(T);
    const ts = f.ts;
    const yy = (m) => side + ts * m;
    const catcher =
      jumper && f.pos[jumper] && teamOf(jumper) === winner
        ? jumper
        : [4, 5, 6].map((n) => keyOf(winner, n)).find((key) => f.pos[key]);
    if (!catcher) {
      b.done();
      return;
    }
    const m = f.slot[catcher] ?? 8;
    const hooker = keyOf(T, 2);
    b.ball(0.18, { holder: f.pos[hooker] ? hooker : catcher });
    b.lift(0.28, catcher);
    b.at(0.3, catcher, [f.pos[catcher][0] + (winner === T ? 0 : 0), yy(m)]);
    b.ball(0.42, { holder: catcher, h: 2.6 });
    b.lift(0.55, null);
    const W = winner;
    const dw = dir(W);
    const nine = keyOf(W, 9);
    const tNine = 0.56;
    if (f.pos[nine]) {
      b.at(tNine, nine, [x0 - dw * 2.0, yy(m + 1.5)]);
      b.ball(tNine, { holder: nine, h: 0.6 });
    }
    // Le porteur suivant : l'ouvreur (lancer gagné) ou un avant (ballon volé).
    const runner = W === T ? keyOf(W, 10) : this.nearest(b, W, [x0, yy(m + 3)], tNine, 1, [catcher, nine])[0];
    const contact = [x0 + dw * this.rnd(0.5, 2), yy(W === T ? 20 : m + 4)];
    if (runner && f.pos[runner]) {
      const tCatch = tNine + 0.1;
      b.at(tCatch, runner, [contact[0] - dw * 5.5, contact[1]]);
      b.ball(tCatch, { holder: runner, h: 0.7 });
      const tContact = 0.84;
      b.at(tContact, runner, contact);
      const tackler = this.nearest(b, other(W), contact, tCatch, 1)[0];
      if (tackler) b.at(tContact, tackler, [contact[0] + dw * 0.9, contact[1] + 0.4]);
      b.down(tContact, [runner, tackler].filter(Boolean));
      b.ball(tContact + 0.02, { at: [contact[0] - dw * 0.5, contact[1]] });
      // Les trois-quarts montent ; les défenseurs aussi, une fois le ballon sorti.
      for (const [key, p] of Object.entries(f.pos)) {
        if ([catcher, nine, runner, tackler, hooker, "ref"].includes(key)) continue;
        if (numberOf(key) >= 9) b.at(tContact, key, [p[0] + dir(teamOf(key)) * 3, p[1]]);
      }
      this.moveBall(...contact);
      this.ruck = runner;
      this.cleaners = this.support(b, W, contact, tContact, [runner, catcher]);
      const end = this.open(W);
      this.settle(b, end, [runner]);
      b.at(1, runner, end.pos[runner] ?? contact);
      b.down(0.94, [runner]);
      b.ball(0.92, end.ball);
    }
    b.caption(0, `Touche · ${this.club(T)}`);
    b.caption(0.42, W === T ? `Touche gagnée par ${this.name(catcher)}` : `Touche volée par ${this.name(catcher)} !`);
    b.focus(0.3, catcher);
    b.done();
    this.att = W;
  }

  // --- Les points -----------------------------------------------------------------------

  // Un essai en jeu courant de `team`, marqué par `scorer` : les passes jusqu'à lui (s'il
  // n'a pas déjà le ballon), sa course, les défenseurs qui plongent trop tard, l'en-but.
  tryRun(team, scorer, { label = null } = {}) {
    const d = dir(team);
    const D = other(team);
    const goal = goalOf(team);
    const holder = this.tl.lastBall()?.holder ?? null;
    let fromHolder = holder && teamOf(holder) === team;
    if (!fromHolder) {
      const start = this.open(team, { carrier: scorer });
      this.align(start);
    }
    const state = this.now();
    const scorerAt = state.pos[scorer];
    if (!scorerAt) return;
    const far = Math.abs(goal - scorerAt[0]);
    const ms = clamp(1500 + far * 26, 1700, 3300);
    const b = this.tl.beat(ms, { essential: true, label: "try" });
    let tCatch = 0.06;
    let catchAt = scorerAt;
    if (fromHolder && holder !== scorer) {
      ({ t: tCatch, at: catchAt } = this.passes(b, [holder, scorer], 0.04));
    } else if (!fromHolder) {
      const formation = this.open(team, { carrier: scorer });
      ({ t: tCatch, at: catchAt } = this.passes(b, this.chain(formation, scorer), 0.08));
    } else {
      b.ball(0, { holder: scorer });
    }
    const forward = numberOf(scorer) <= 8;
    const wing = [11, 14].includes(numberOf(scorer));
    let y = catchAt[1];
    if (!forward) y += (MID_Y - y) * (wing ? 0.12 : 0.35);
    const ground = [goal + d * (forward ? 0.7 : this.rnd(1.2, 3)), clampY(y, 4)];
    const tGround = Math.min(0.84, tCatch + 0.12 + 0.62 * clamp(far / 55, 0.25, 1));
    b.at(tGround - 0.04, scorer, [goal + d * 0.2, ground[1]]);
    b.at(tGround, scorer, ground);
    // Ceux qui tentent de le rattraper : trop tard.
    const chasers = this.nearest(b, D, [goal - d * 6, ground[1]], tCatch, 2);
    chasers.forEach((key, i) => {
      const at = [goal - d * (1.4 + i * 1.8), ground[1] + (i ? -1.6 : 1.4)];
      b.at(tGround - 0.02, key, at);
    });
    b.down(tGround - 0.01, chasers.slice(0, 1));
    const support = this.nearest(b, team, ground, tCatch, 1, [scorer, holder].filter(Boolean))[0];
    if (support) b.at(tGround, support, [goal - d * 2.5, ground[1] + (ground[1] < MID_Y ? 3 : -3)]);
    for (const [key, p] of Object.entries(state.pos)) {
      if (key === "ref" || key === scorer || chasers.includes(key) || key === support || this.gone.has(key)) continue;
      const k = teamOf(key) === team ? 0.35 : 0.3;
      b.at(tGround, key, [p[0] + (goal - p[0]) * k, p[1] + (ground[1] - p[1]) * 0.15]);
    }
    b.ball(tGround, { at: ground });
    b.down(tGround, [scorer, ...chasers.slice(0, 1)]);
    // Les partenaires le rejoignent.
    for (const key of this.nearest(b, team, ground, tGround, 3, [scorer])) {
      b.at(1, key, [ground[0] - d * this.rnd(1.5, 3.5), ground[1] + this.rnd(-2.5, 2.5)]);
    }
    b.at(1, "ref", [goal + d * 0.5, clampY(ground[1] + (ground[1] < MID_Y ? 5 : -5))]);
    b.caption(0, label ?? `${this.club(team)} attaque`);
    b.caption(tGround - 0.02, `Essai de ${this.name(scorer)} !`);
    b.focus(0, scorer);
    b.done();
    this.tryY = ground[1];
    this.moveBall(...ground);
    this.ruck = null;
    this.cleaners = [];
  }

  // Coup de pied au but (transformation ou pénalité) : élan, frappe, entre les perches ou à côté.
  kickAtPosts(b, team, kicker, tee, success, tKick = 0.4) {
    const d = dir(team);
    const off = tee[1] < MID_Y ? -1 : 1;
    const target = success
      ? [POSTS_X(team), MID_Y + this.rnd(-1.6, 1.6)]
      : this.R() < 0.75
        ? [POSTS_X(team), MID_Y + (this.R() < 0.5 ? -off : off) * (POST_GAP / 2 + this.rnd(0.8, 3.5))]
        : [goalOf(team) - d * this.rnd(1, 5), MID_Y + this.rnd(-3, 3)];
    if (kicker) {
      b.at(tKick - 0.06, kicker, [tee[0] - d * 0.6, tee[1] + 0.25 * off]);
      b.at(tKick + 0.12, kicker, [tee[0] + d * 1.2, tee[1]]);
    }
    b.ball(tKick, { at: tee });
    b.ball(0.84, { at: target, h: success ? 10 : 8 });
  }

  conversion(team, kicker, success) {
    const f = conversionSetup(this.present, { team, tryY: this.tryY, kicker, seed: this.layout });
    this.align(f, { ms: 1000, caption: `Transformation · ${this.name(kicker)}` });
    const b = this.tl.beat(MS.conversion, { essential: true, label: "conversion" });
    const d = dir(team);
    // La défense charge dès l'élan du buteur.
    for (const [key, p] of Object.entries(f.pos)) {
      if (key !== "ref" && teamOf(key) !== team) b.at(0.36, key, p).at(0.56, key, [p[0] - d * this.rnd(3, 6), p[1] + (f.tee[1] - p[1]) * 0.2]);
    }
    this.kickAtPosts(b, team, kicker, f.tee, success);
    b.caption(0, `Transformation · ${this.name(kicker)}`);
    b.caption(0.84, success ? `Transformation réussie · ${this.name(kicker)}` : "Transformation manquée");
    b.focus(0, kicker);
    b.done();
    this.moveBall(50, MID_Y);
  }

  // Une pénalité : tentée face aux perches.
  penaltyGoal(team, kicker, success, mark = null) {
    const spot = mark ?? this.penaltyMark(team);
    const f = kickAtGoal(this.present, { team, mark: spot, kicker, seed: this.layout });
    this.align(f, { ms: 1000, caption: `Pénalité pour ${this.club(team)}` });
    const b = this.tl.beat(MS.penaltyGoal, { essential: true, label: "penalty" });
    this.kickAtPosts(b, team, kicker, f.tee, success, 0.42);
    const metres = Math.round(Math.hypot(toGoal(team, f.tee[0]), f.tee[1] - MID_Y));
    b.caption(0, `Pénalité tentée par ${this.name(kicker)} · ${metres} m`);
    b.caption(0.84, success ? `Pénalité réussie · ${this.name(kicker)}` : `Pénalité manquée · ${this.name(kicker)}`);
    b.focus(0, kicker);
    b.done();
    this.moveBall(success ? 50 : fromGoal(team, 22), MID_Y);
    this.att = other(team);
    this.ruck = null;
  }

  // L'endroit d'une pénalité : là où est le ballon, ramené à portée de buteur.
  penaltyMark(team) {
    let m = toGoal(team, this.loc.x);
    if (m > 46 || m < 12) m = this.rnd(24, 40);
    return [fromGoal(team, m), clamp(this.loc.y, 10, WIDTH - 10)];
  }

  drop(team, kicker) {
    const d = dir(team);
    const f = this.open(team, { carrier: kicker });
    if (kicker && f.pos[kicker]) f.pos[kicker] = [f.bx - d * 10, clampY(f.by + f.o * 2.5)];
    this.align(f);
    const b = this.tl.beat(MS.drop, { essential: true, label: "drop" });
    b.ball(0, f.ball);
    const { t } = this.passes(b, [this.chain(f, kicker)[0], kicker], 0.08);
    const at = b.pos(kicker, t);
    b.at(t + 0.12, kicker, [at[0] + d * 0.8, at[1]]);
    b.ball(t + 0.12, { holder: kicker });
    b.ball(0.84, { at: [POSTS_X(team), MID_Y + this.rnd(-1.5, 1.5)], h: 9 });
    this.pressure(b, t + 0.15, team, { rush: 4, follow: 0.5, except: [kicker] });
    b.caption(0, `${this.club(team)} attaque`);
    b.caption(t + 0.12, `Drop de ${this.name(kicker)}…`);
    b.caption(0.84, `Drop réussi · ${this.name(kicker)}`);
    b.focus(0, kicker);
    b.done();
    this.moveBall(50, MID_Y);
    this.att = other(team);
    this.ruck = null;
  }

  // L'attaque échoue près de la ligne : le porteur est tenu, la défense récupère.
  held(team, carrier) {
    const d = dir(team);
    const D = other(team);
    const goal = goalOf(team);
    const start = this.open(team, { carrier });
    this.align(start);
    const b = this.tl.beat(MS.held, { essential: true, label: "held" });
    b.ball(0, start.ball);
    const { t } = this.passes(b, this.chain(start, carrier), 0.08);
    const at = b.pos(carrier, t);
    const line = [goal + d * 0.3, at[1]];
    const tHit = Math.min(t + 0.26, 0.6);
    b.at(tHit, carrier, line);
    const wall = this.nearest(b, D, line, t, 3);
    wall.forEach((key, i) => b.at(tHit, key, [line[0] + d * (0.8 + (i % 2) * 0.5), line[1] + (i - 1) * 0.9]));
    this.pressure(b, tHit, team, { rush: 1.0, frontX: line[0], except: [carrier, ...wall] });
    b.caption(0, `${this.club(team)} pousse près de la ligne`);
    b.caption(tHit, `${this.name(carrier)} tenu au-dessus de la ligne !`);
    b.focus(0, carrier);
    // La défense récupère et se dégage.
    const point = [goal - d * 4, clampY(line[1], 6)];
    this.moveBall(...point);
    this.ruck = carrier;
    this.cleaners = wall.slice(0, 2);
    const end = this.open(D);
    this.settle(b, end, [carrier]);
    b.at(1, carrier, end.pos[carrier] ?? point);
    b.down(tHit + 0.1, [carrier, wall[0]].filter(Boolean));
    b.down(0.9, [carrier]);
    b.ball(tHit + 0.12, { at: end.ball.at });
    b.done();
    this.att = D;
  }

  // Carton : le joueur sort par la touche.
  card(key, red, name) {
    if (!key) return;
    const b = this.tl.beat(MS.card, { label: "card" });
    const p = b.pos(key, 0);
    if (p) {
      b.at(0.3, "ref", [p[0] + 2, p[1] + 1.5]);
      b.at(1, key, [p[0], p[1] < MID_Y ? -2.4 : WIDTH + 2.4]);
    }
    this.gone.add(key);
    b.gone(1, [...this.gone]);
    b.caption(0, `${red ? "Carton rouge" : "Carton jaune"} pour ${name}`);
    b.focus(0, key);
    b.done();
  }

  // --- Les pénalités jouées autrement qu'au but -----------------------------------------

  // Pénalité jouée en touche : le buteur trouve la touche à cinq mètres, puis maul.
  // `scorer` : celui qui aplatit au bout du maul (null : le maul est arrêté).
  // `noKick` : la touche est déjà là (situation de touche), sans pénalité avant.
  maulPenalty(team, scorer, { kicker = null, noKick = false } = {}) {
    const d = dir(team);
    const D = other(team);
    const goal = goalOf(team);
    const side = this.loc.y < MID_Y ? 0 : WIDTH;
    let x0 = clamp(this.loc.x, 5.5, 94.5);
    if (!noKick) {
      const kick = kicker ?? keyOf(team, 10);
      const mark = this.penaltyMark(team);
      const setup = kickAtGoal(this.present, { team, mark, kicker: kick, seed: this.layout });
      this.align(setup, { ms: 900, caption: `Pénalité pour ${this.club(team)} : en touche` });
      x0 = fromGoal(team, 5.5);
      const k = this.tl.beat(MS.touchKick, { label: "touch" });
      k.ball(0.2, { at: setup.tee });
      k.ball(0.75, { at: [x0, side === 0 ? -0.8 : WIDTH + 0.8], h: 10 });
      k.caption(0, `Pénalité en touche · ${this.name(kick)}`);
      k.focus(0, kick);
      k.done();
      this.moveBall(x0, side === 0 ? 3 : WIDTH - 3);
    }
    const f = lineout(this.present, { thrower: team, x0, side });
    this.align(f, { ms: 1000 });
    const b = this.tl.beat(MS.maul, { essential: true, label: "maul" });
    const yy = (m) => side + f.ts * m;
    const jumper = [4, 5].map((n) => keyOf(team, n)).find((key) => f.pos[key]);
    const hooker = keyOf(team, 2);
    if (jumper) {
      b.ball(0.12, { holder: f.pos[hooker] ? hooker : jumper });
      b.lift(0.18, jumper);
      b.ball(0.3, { holder: jumper, h: 2.5 });
      b.lift(0.4, null);
    }
    const back = scorer && numberOf(scorer) <= 8 ? scorer : f.pos[hooker] ? hooker : jumper;
    const y0 = yy(7);
    const formed = maulCluster(this.present, { team, x0: x0 + d * 0.3, y0, carrier: back });
    b.set(0.42, formed);
    if (back) b.ball(0.46, { holder: back });
    const push = scorer ? Math.abs(goal - x0) + 2 : this.rnd(1, 3);
    const moved = Object.fromEntries(Object.entries(formed).map(([key, [x, y]]) => [key, [x + d * push, y + f.ts * 0.8]]));
    b.set(0.84, moved);
    for (const [key, p] of Object.entries(f.pos)) {
      if (formed[key] || key === "ref") continue;
      b.at(0.84, key, [p[0] + d * (teamOf(key) === team ? 2 : -1), p[1]]);
    }
    b.caption(0, `Touche à cinq mètres · ${this.club(team)}`);
    b.caption(0.42, "Le maul se forme…");
    if (scorer) {
      const ground = [goal + d * 1.2, y0 + f.ts * 0.8];
      b.at(0.88, scorer, ground);
      b.ball(0.88, { at: ground });
      b.down(0.88, [scorer]);
      b.caption(0.86, `Essai de ${this.name(scorer)} au bout du maul !`);
      b.focus(0.42, scorer);
      this.tryY = ground[1];
      b.done();
      this.moveBall(...ground);
      this.ruck = null;
      return;
    }
    b.caption(0.84, `Le maul est arrêté · ${this.club(D)} récupère`);
    b.done();
    this.turnoverAtLine(team, back);
  }

  // Pénalité jouée en mêlée à cinq mètres : la poussée, le n°8 aplatit (ou la mêlée recule).
  scrumPenalty(team, scorer) {
    const d = dir(team);
    const goal = goalOf(team);
    const x0 = fromGoal(team, 5.5);
    const f = scrum(this.present, { feed: team, x0, y0: this.loc.y });
    this.align(f, { ms: 1100, caption: `Pénalité pour ${this.club(team)} : mêlée à cinq mètres` });
    const b = this.tl.beat(MS.scrum, { essential: true, label: "scrum" });
    const nine = keyOf(team, 9);
    const pack = Object.keys(f.pos).filter((key) => key !== "ref" && numberOf(key) <= 8);
    const push = scorer ? 6.8 : -this.rnd(0.8, 2);
    b.ball(0.2, { holder: f.pos[nine] ? nine : pack[0] });
    b.ball(0.32, { at: [f.x0 - d * 1.6, f.y0] });
    for (const key of pack) {
      const [x, y] = f.pos[key];
      b.at(0.3, key, [x, y]).at(0.8, key, [x + d * push, y]);
    }
    b.caption(0, `Mêlée à cinq mètres · ${this.club(team)}`);
    if (scorer) {
      const ground = [goal + d * 1.1, f.y0];
      const eight = scorer;
      b.at(0.84, eight, ground);
      b.ball(0.84, { at: ground });
      b.down(0.84, [eight]);
      b.caption(0.8, `Essai de ${this.name(eight)} en force !`);
      b.focus(0.3, eight);
      this.tryY = ground[1];
      b.done();
      this.moveBall(...ground);
      this.ruck = null;
      return;
    }
    b.caption(0.7, `La mêlée recule · ${this.club(other(team))} tient bon`);
    b.done();
    this.turnoverAtLine(team, keyOf(team, 8));
  }

  // Pénalité jouée vite à la main : le demi de mêlée tape et sert un avant lancé.
  tapPenalty(team, scorer, carrier) {
    const runner = scorer ?? carrier;
    if (!runner) return;
    const mark = [fromGoal(team, this.rnd(6, 10)), clamp(this.loc.y, 10, WIDTH - 10)];
    this.moveBall(...mark);
    this.ruck = null;
    this.cleaners = [];
    const f = this.open(team, { carrier: runner, rush: -6 });
    f.ball = { holder: this.chain(f, runner)[0] };
    this.align(f, { caption: `Pénalité pour ${this.club(team)} : jouée à la main` });
    if (scorer) {
      this.tryRun(team, scorer, { label: `Pénalité jouée vite par ${this.club(team)}` });
      return;
    }
    this.held(team, runner);
  }

  // La défense récupère le ballon sur sa ligne, après un maul ou une mêlée arrêtés.
  turnoverAtLine(team, carrier) {
    const D = other(team);
    this.moveBall(fromGoal(team, 4), this.loc.y);
    this.ruck = carrier && this.present[team].has(numberOf(carrier)) ? carrier : null;
    this.cleaners = [];
    this.align(this.open(D), { ms: 800 });
    this.att = D;
  }

  // --- L'arrêt de jeu sur une décision ----------------------------------------------------

  // Une pénalité sifflée qui attend le choix du manager : le buteur au point de pénalité,
  // la défense recule de dix mètres.
  awaitPenalty(team, caption) {
    const mark = this.penaltyMark(team);
    this.moveBall(...mark);
    this.ruck = null;
    this.cleaners = [];
    const f = this.open(team, { rush: -8.5 });
    const kicker = this.ctx.kicker(team);
    const holder = kicker && f.pos[kicker] ? kicker : this.chain(f, keyOf(team, 9))[0];
    if (holder) {
      f.pos[holder] = clampPoint([mark[0] - dir(team) * 0.6, mark[1]]);
      f.ball = { holder };
    }
    f.pos.ref = clampPoint([mark[0] + dir(team) * 1.5, mark[1] + 3]);
    this.align(f, { ms: 1200, essential: true, caption });
    this.tl.beat(400, { essential: true, label: "wait" }).focus(0, holder ?? null).caption(0, caption).done();
  }
}
