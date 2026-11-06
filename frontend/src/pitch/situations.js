import {
  MID_Y,
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
  teamOf,
  toGoal,
  wingOn,
} from "./geometry.js";
import { kickAtGoal, lineout, maulCluster, openPlay, scrum, underTheBall } from "./formations.js";

// Les dilemmes sur le terrain : chaque situation (engine/dilemmas.py) a sa mise en place,
// avec le joueur concerné (`actor`, de notre équipe) là où le texte le dit ; puis, une
// fois la voie choisie, son issue (`Effect`) se joue depuis cette mise en place.

const nearestIn = (f, team, point, except = []) =>
  Object.keys(f.pos)
    .filter((key) => key !== "ref" && teamOf(key) === team && !except.includes(key) && !(f.down ?? []).includes(key))
    .sort((a, b) => dist(f.pos[a], point) - dist(f.pos[b], point))[0] ?? null;

const has = (S, key) => Boolean(key) && S.present[teamOf(key)].has(numberOf(key));

// Là où est le ballon, ramené dans `[lo, hi]` : pour les situations que le texte ne
// situe pas, elles se jouent où en était le jeu.
const hereX = (S, lo, hi) => clamp(S.loc.x, lo, hi);
const hereY = (S) => clamp(S.loc.y, 12, WIDTH - 12);

// Les phases statiques : le joueur concerné y est lié (mêlée, touche, maul).
const SET_PIECES = new Set(["scrum", "lineout", "throw", "goal_scrum", "steal_lineout", "defend_maul"]);

// Un ruck en (x, y) pour `att`, son corps au sol pris parmi les avants (pas le joueur concerné).
function ruckAt(S, att, x, y, actor, opts = {}) {
  S.moveBall(x, y);
  const body = [7, 6, 4, 1, 5, 3].map((n) => keyOf(att, n)).find((key) => key !== actor && has(S, key));
  return openPlay(S.present, { att, bx: x, by: y, ruck: opts.ruck ?? body ?? null, seed: S.layout, ...opts });
}

const SETUPS = {
  one_on_one(S, actor) {
    const f = ruckAt(S, "us", hereX(S, 30, 80), hereY(S), actor, { carrier: actor });
    const a = f.pos[actor];
    const p = [a[0] + 3, a[1]];
    f.pos[actor] = p;
    f.ball = { holder: actor };
    const def = nearestIn(f, "them", p);
    if (def) f.pos[def] = [p[0] + 4, p[1] + 0.6];
    return { f, possession: "us", carrier: actor, opp: def };
  },
  try_line(S, actor) {
    const f = ruckAt(S, "us", 94.5, 26 + S.rnd(0, 16), actor, { carrier: actor, squeeze: 0.6 });
    f.pos[actor] = clampPoint([f.bx - 1.6, f.by + f.o * 1.6]);
    f.ball = { holder: actor };
    return { f, possession: "us", carrier: actor };
  },
  tackle(S, actor) {
    const carrier = [13, 12, 8].map((n) => keyOf("them", n)).find((key) => has(S, key));
    const f = ruckAt(S, "them", hereX(S, 25, 75), hereY(S), actor, { carrier, tackler: actor });
    const a = f.pos[actor];
    if (carrier && a) {
      f.pos[carrier] = [a[0] + 5, a[1] + 0.4];
      f.ball = { holder: carrier };
    }
    return { f, possession: "them", carrier, opp: carrier };
  },
  ruck(S, actor) {
    const body = [12, 13, 8].map((n) => keyOf("them", n)).find((key) => has(S, key));
    const f = ruckAt(S, "them", hereX(S, 22, 78), hereY(S), actor, { ruck: body });
    f.pos[actor] = [f.bx - 1.2, f.by + 0.2];
    // Leurs soutiens arrivent à peine.
    for (const key of Object.keys(f.pos)) {
      if (teamOf(key) === "them" && key !== body && dist(f.pos[key], [f.bx, f.by]) < 1.6) f.pos[key] = [f.bx + 2.4, f.pos[key][1] + 0.6];
    }
    return { f, possession: "them", carrier: null, opp: body };
  },
  scrum(S) {
    S.moveBall(70, 30);
    const f = scrum(S.present, { feed: "us", x0: 70, y0: 30 });
    return { f, possession: "us", carrier: keyOf("us", 9) };
  },
  lineout(S) {
    S.moveBall(90, S.loc.y < MID_Y ? 3 : WIDTH - 3);
    const f = lineout(S.present, { thrower: "us", x0: 90, side: S.loc.y < MID_Y ? 0 : WIDTH });
    return { f, possession: "us", carrier: keyOf("us", 2) };
  },
  throw(S) {
    S.moveBall(86, S.loc.y < MID_Y ? 3 : WIDTH - 3);
    const f = lineout(S.present, { thrower: "us", x0: 86, side: S.loc.y < MID_Y ? 0 : WIDTH });
    return { f, possession: "us", carrier: keyOf("us", 2) };
  },
  kick(S, actor) {
    const f = ruckAt(S, "us", 66, 32, actor, { carrier: actor, rush: 2.5 });
    f.pos[actor] = clampPoint([f.bx - 6.5, f.by + f.o * 2.5]);
    f.ball = { holder: actor };
    return { f, possession: "us", carrier: actor };
  },
  cross_kick(S, actor) {
    const f = ruckAt(S, "us", 74, 16, actor, { carrier: actor, rush: 3.5 });
    f.ball = { holder: actor };
    // Leurs défenseurs du large montent en pointe, leur ailier compris.
    for (const key of Object.keys(f.pos)) {
      if (teamOf(key) === "them" && f.pos[key][1] > 40) f.pos[key] = [f.pos[key][0] - 3.5, f.pos[key][1]];
    }
    return { f, possession: "us", carrier: actor };
  },
  box_kick(S, actor) {
    const f = ruckAt(S, "us", 28, 15, actor);
    f.pos[actor] = clampPoint([f.bx - 1.3, f.by + 0.6]);
    f.ball = { holder: actor };
    return { f, possession: "us", carrier: actor };
  },
  touchline(S, actor) {
    const f = ruckAt(S, "us", 52, 42, actor);
    const y = numberOf(actor) === 14 ? WIDTH - 3 : 3;
    const s = y < MID_Y ? 1 : -1;
    f.pos[actor] = [66, y];
    f.ball = { holder: actor };
    const fullback = keyOf("them", 15);
    if (f.pos[fullback]) f.pos[fullback] = [77, y + s * 9];
    const wing = keyOf("them", wingOn("them", -s));
    if (f.pos[wing]) f.pos[wing] = [61, y + s * 4];
    return { f, possession: "us", carrier: actor, opp: fullback };
  },
  counter(S, actor) {
    const spot = [14, 28 + S.rnd(0, 12)];
    S.moveBall(...spot);
    const f = underTheBall(S.present, { team: "us", receiver: actor, spot, chase: 17, seed: S.layout });
    f.ball = { at: spot, hover: 5 };
    return { f, possession: "us", carrier: actor };
  },
  high_ball(S, actor) {
    const spot = [17, 24 + S.rnd(0, 20)];
    S.moveBall(...spot);
    const f = underTheBall(S.present, { team: "us", receiver: actor, spot, chase: 7, seed: S.layout });
    f.ball = { at: spot, hover: 10 };
    return { f, possession: "us", carrier: actor };
  },
  provocation(S, actor) {
    const f = ruckAt(S, "us", hereX(S, 25, 75), hereY(S), actor);
    f.pos[actor] = [f.bx + 1.8, f.by + 4];
    const opp = nearestIn(f, "them", f.pos[actor]);
    if (opp) f.pos[opp] = [f.bx + 2.7, f.by + 4.5];
    f.pos.ref = [f.bx + 3.8, f.by + 7];
    return { f, possession: "us", carrier: null, opp };
  },
  two_on_one(S, actor, { chained }) {
    const x = chained ? clamp(S.loc.x + 4, 60, 86) : 76;
    const y = clamp(chained ? S.loc.y : 30, 12, WIDTH - 18);
    const f = ruckAt(S, "us", x - 8, y, actor, { ruck: null });
    f.down = [];
    f.pos[actor] = [x, y];
    f.ball = { holder: actor };
    const partner = [14, 11, 13, 12, 15, 7].map((n) => keyOf("us", n)).find((key) => key !== actor && f.pos[key]);
    if (partner) f.pos[partner] = [x - 0.4, y + 7];
    const last = keyOf("them", 15);
    for (const key of Object.keys(f.pos)) {
      if (key === actor || key === partner || key === "ref") continue;
      const behind = teamOf(key) === "us" ? S.rnd(5, 22) : S.rnd(5, 18);
      f.pos[key] = clampPoint([x - behind, y + S.rnd(-22, 22)]);
    }
    if (f.pos[last]) f.pos[last] = [x + 10, y + 3];
    f.pos.ref = [x - 12, y - 6];
    return { f, possession: "us", carrier: actor, opp: last, partner };
  },
  interception(S, actor) {
    const twelve = keyOf("them", 12);
    const f = ruckAt(S, "them", hereX(S, 25, 75), hereY(S), actor, { carrier: twelve });
    const ten = keyOf("them", 10);
    if (f.pos[ten]) f.ball = { holder: ten };
    const target = f.pos[twelve];
    if (target) f.pos[actor] = [target[0] - 3.2, target[1] - 1.4];
    return { f, possession: "them", carrier: ten, opp: twelve };
  },
  long_penalty(S, actor) {
    const mark = [55, 28 + S.rnd(0, 14)];
    S.moveBall(...mark);
    const f = kickAtGoal(S.present, { team: "us", mark, kicker: actor, seed: S.layout });
    f.pos[actor] = [mark[0] - 0.8, mark[1]];
    f.ball = { holder: actor };
    return { f, possession: "us", carrier: actor, tee: f.tee };
  },
  last_ditch(S, actor) {
    const f = ruckAt(S, "them", 45, 50, actor, { ruck: null });
    f.down = [];
    const wing = keyOf("them", wingOn("them", 1));
    const runner = f.pos[wing] ? wing : nearestIn(f, "them", [30, 60]);
    for (const key of Object.keys(f.pos)) {
      if (key === "ref") continue;
      if (teamOf(key) === "us") f.pos[key] = [S.rnd(40, 64), S.rnd(10, 64)];
      else f.pos[key] = [S.rnd(38, 60), S.rnd(20, 66)];
    }
    if (runner) {
      f.pos[runner] = [30, 60];
      f.ball = { holder: runner };
    }
    f.pos[actor] = [37, 48];
    f.pos.ref = [44, 56];
    S.moveBall(30, 60);
    return { f, possession: "them", carrier: runner };
  },
  goal_scrum(S) {
    S.moveBall(5, 30);
    const f = scrum(S.present, { feed: "them", x0: 5, y0: 30 });
    return { f, possession: "them", carrier: keyOf("them", 9) };
  },
  defend_maul(S, actor) {
    const side = S.loc.y < MID_Y ? 0 : WIDTH;
    S.moveBall(10, side === 0 ? 8 : WIDTH - 8);
    const f = lineout(S.present, { thrower: "them", x0: 10, side });
    const carrier = keyOf("them", 2);
    Object.assign(f.pos, maulCluster(S.present, { team: "them", x0: 10, y0: side === 0 ? 8 : WIDTH - 8, carrier }));
    if (numberOf(actor) > 8) f.pos[actor] = [8, side === 0 ? 10 : WIDTH - 10];
    f.ball = { holder: carrier };
    return { f, possession: "them", carrier };
  },
  steal_lineout(S, actor) {
    const side = S.loc.y < MID_Y ? 0 : WIDTH;
    S.moveBall(32, side === 0 ? 3 : WIDTH - 3);
    const f = lineout(S.present, { thrower: "them", x0: 32, side });
    return { f, possession: "them", carrier: keyOf("them", 2), opp: keyOf("them", 4), actor };
  },
  carry(S, actor) {
    const f = ruckAt(S, "us", hereX(S, 25, 80), hereY(S), actor, { carrier: actor });
    f.pos[actor] = clampPoint([f.bx - 1.8, f.by + f.o * 2.6]);
    const nine = keyOf("us", 9);
    f.ball = { holder: f.pos[nine] && nine !== actor ? nine : actor };
    const first = nearestIn(f, "them", f.pos[actor]);
    if (first) f.pos[first] = clampPoint([f.bx + 1.3, f.by + f.o * 2.0]);
    const second = nearestIn(f, "them", f.pos[actor], [first]);
    if (second) f.pos[second] = clampPoint([f.bx + 1.5, f.by + f.o * 3.7]);
    return { f, possession: "us", carrier: actor, opp: first };
  },
  charge_down(S, actor) {
    const f = ruckAt(S, "them", 88, 22, actor);
    const nine = keyOf("them", 9);
    if (f.pos[nine]) f.ball = { holder: nine };
    f.pos[actor] = [f.bx - 1.3, f.by + 1.8];
    return { f, possession: "them", carrier: nine };
  },
  fifty_22(S, actor) {
    const f = ruckAt(S, "us", 36, 40, actor, { carrier: actor });
    f.pos[actor] = clampPoint([f.bx - 9, f.by + f.o * 5]);
    f.ball = { holder: actor };
    // Leur ailier monté dans la ligne, personne derrière lui.
    const wing = keyOf("them", wingOn("them", -f.o));
    if (f.pos[wing]) f.pos[wing] = [f.bx + 2.5, f.pos[wing][1]];
    const fullback = keyOf("them", 15);
    if (f.pos[fullback]) f.pos[fullback] = [f.bx + 18, f.by + f.o * 22];
    return { f, possession: "us", carrier: actor };
  },
  in_goal(S, actor) {
    const f = ruckAt(S, "them", 24, 34, actor, { ruck: null });
    f.down = [];
    for (const key of Object.keys(f.pos)) {
      if (key === "ref") continue;
      f.pos[key] = teamOf(key) === "us" ? [S.rnd(10, 26), S.rnd(10, 60)] : [S.rnd(14, 32), S.rnd(10, 60)];
    }
    const wing = keyOf("them", 14);
    if (f.pos[wing]) f.pos[wing] = [5, 36];
    f.pos[actor] = [4, 29];
    f.ball = { at: [-2.5, 32] };
    f.pos.ref = [12, 22];
    S.moveBall(1, 32);
    return { f, possession: null, carrier: null, opp: wing };
  },
  pressure_clear(S, actor) {
    const f = ruckAt(S, "us", 10, 30, actor, { rush: 3.5 });
    if (numberOf(actor) !== 9) f.pos[actor] = clampPoint([f.bx - 5, f.by + f.o * 2]);
    f.ball = { holder: actor };
    return { f, possession: "us", carrier: actor };
  },
  last_play(S, actor) {
    const f = ruckAt(S, "us", hereX(S, 40, 75), hereY(S), actor, { carrier: actor });
    f.ball = { holder: actor };
    return { f, possession: "us", carrier: actor };
  },
  counter_attack(S, actor, { chained }) {
    const x = chained ? clamp(S.loc.x, 25, 75) : 48;
    const f = ruckAt(S, "us", x, 35, actor, { carrier: actor, broken: 1, ruck: null });
    f.down = [];
    f.pos[actor] = clampPoint([f.bx + 1, f.by + f.o * 3]);
    f.ball = { holder: actor };
    return { f, possession: "us", carrier: actor };
  },
};

// Met en place la situation du dilemme en attente ; `title` : son nom (format.js).
export function stageSituation(S, situation, actor, { title, chained = false }) {
  const build = SETUPS[situation];
  if (!build || !actor || !has(S, actor)) return false;
  const setup = build(S, actor, { chained });
  S.sit = { situation, actor, ...setup };
  S.lastSituation = situation;
  S.align(setup.f, { ms: chained ? 700 : 1200, essential: true, caption: title });
  const b = S.tl.beat(300, { essential: true, label: "wait" });
  b.caption(0, title).focus(0, actor);
  if (setup.f.ball?.hover) b.ball(0, setup.f.ball);
  b.done();
  if (setup.possession) S.att = setup.possession;
  return true;
}

// Les voies qui se jouent au pied : comment le ballon part.
const KICKS = {
  "kick.drop": "posts",
  "long_penalty.posts": "posts",
  "kick.grubber": "grubber",
  "cross_kick.cross": "cross",
  "cross_kick.touch": "touch",
  "box_kick.box": "box",
  "counter.up_and_under": "box",
  "counter.touch": "touch",
  "long_penalty.touch_kick": "touch",
  "fifty_22.fifty": "touch",
  "fifty_22.long_kick": "long",
  "pressure_clear.boot": "touch",
  "last_play.boot_out": "touch",
  "in_goal.clear": "touch",
  "touchline.chip": "chip",
};

// Joue l'issue d'un dilemme tranché. `outcome` : { situation, option, success, effect } ;
// `events` : ce que le choix a ajouté au match (essai, transformation, pénalité...).
export function playOutcome(S, outcome, events, ctx) {
  const sit = S.sit;
  const actor = sit?.actor ?? null;
  if (!sit || !actor) return;
  const us = "us";
  const them = "them";
  const find = (type, team) => events.find((e) => e.type === type && ctx.teamOfClub(e.club_id) === team);
  const kickOf = KICKS[`${outcome.situation}.${outcome.option}`];
  const effect = outcome.effect;
  const holder = S.tl.lastBall()?.holder ?? null;
  const conversion = (team) => {
    const made = find("conversion", team);
    const missed = find("conversion_missed", team);
    const e = made ?? missed;
    if (e) S.conversion(team, ctx.keyOf(e.player_id), Boolean(made));
  };

  // Le joueur concerné prend le ballon s'il ne l'a pas (le demi lui passe) ; pas en mêlée
  // ni en touche, où il est lié.
  const setPiece = SET_PIECES.has(outcome.situation);
  const toActor = () => {
    if (!setPiece && holder && holder !== actor && teamOf(holder) === us) S.pass(holder, actor);
  };

  if (kickOf && effect !== "lost") {
    toActor();
    if (kickOf === "posts") {
      const success = effect === "drop" || effect === "goal";
      S.kickFromHand(actor, success, outcome.situation === "kick" ? "drop" : "goal");
      return;
    }
    if (kickOf === "cross" || kickOf === "chip") {
      const scorerEvent = find("try", us);
      const scorer = scorerEvent ? ctx.keyOf(scorerEvent.player_id) : actor;
      S.kickTo(actor, kickOf, scorer);
      S.tryRun(us, scorer);
      conversion(us);
      return;
    }
    if (kickOf === "grubber") {
      S.kickTo(actor, "grubber", actor);
      S.carryOn(actor, { gain: S.rnd(6, 12) });
      return;
    }
    S.kickTo(actor, kickOf, null, { regather: effect === "turnover" });
    return;
  }

  switch (effect) {
    case "try": {
      if (sit.possession === us || !sit.possession) toActor();
      if (holder && teamOf(holder) === them) S.steal(actor);
      if (outcome.situation === "lineout" || outcome.situation === "throw") {
        S.maulPenalty(us, find("try", us) ? ctx.keyOf(find("try", us).player_id) : actor, { noKick: true });
      } else S.tryRun(us, actor);
      conversion(us);
      return;
    }
    case "assist": {
      toActor();
      const e = find("try", us);
      const scorer = e ? ctx.keyOf(e.player_id) : sit.partner;
      if (scorer && scorer !== actor) S.tryRun(us, scorer);
      else S.tryRun(us, actor);
      conversion(us);
      return;
    }
    case "break":
      toActor();
      S.carryOn(actor, { gain: S.rnd(14, 24), result: "break" });
      return;
    case "drop":
    case "goal":
    case "goal_missed":
      toActor();
      S.kickFromHand(actor, effect !== "goal_missed", effect === "drop" ? "drop" : "goal");
      return;
    case "penalty_won":
    case "penalty_conceded":
    case "yellow": {
      const team = effect === "penalty_won" ? us : them;
      if (effect === "yellow") S.card(actor, false, ctx.name(actor));
      const made = find("penalty_goal", team);
      const missed = find("penalty_missed", team);
      const e = made ?? missed;
      S.whistle(effect === "penalty_won" ? `Pénalité obtenue pour ${S.club(us)}` : `Pénalité pour ${S.club(them)}`);
      if (e) S.penaltyGoal(team, ctx.keyOf(e.player_id), Boolean(made), S.markNear(team));
      return;
    }
    case "turnover":
      S.steal(actor);
      return;
    case "lost": {
      const taker = sit.opp && S.present.them.has(numberOf(sit.opp)) ? sit.opp : null;
      S.lose(actor, taker);
      return;
    }
    case "missed":
      S.beaten(actor, sit.carrier && teamOf(sit.carrier) === them ? sit.carrier : null);
      return;
    case "try_conceded": {
      const e = find("try", them);
      const scorer = e ? ctx.keyOf(e.player_id) : sit.carrier;
      if (scorer) {
        S.beaten(actor, null, { short: true });
        S.tryRun(them, scorer);
        conversion(them);
      }
      return;
    }
    default: {
      // Rien de décisif : le porteur est plaqué, le jeu continue. Sur une phase statique
      // gagnée, le ballon sort au demi de mêlée, puis à l'ouvreur qui va au contact.
      if (setPiece && sit.possession) {
        S.setPieceOut(sit.possession);
        return;
      }
      if (sit.possession === us) {
        toActor();
        S.carryOn(holder && teamOf(holder) === us && !["one_on_one", "carry", "try_line"].includes(outcome.situation) ? holder : actor, {
          gain: S.rnd(0.5, 2.5),
        });
      } else if (sit.possession === them && sit.carrier && S.present.them.has(numberOf(sit.carrier))) {
        S.carryOn(sit.carrier, { gain: S.rnd(0, 1.5), tackler: actor });
      } else S.realign();
    }
  }
}

// --- Les gestes que demandent les issues, ajoutés à la scène ------------------------------

export const SceneMoves = {
  // Une passe directe, sans contact.
  pass(from, to) {
    const b = this.tl.beat(420, { label: "pass" });
    const at = b.pos(to, 0);
    const passer = b.pos(from, 0);
    const d = dir(teamOf(to));
    b.ball(0, { holder: from });
    b.ball(0.7, { holder: to, h: 0.6 });
    if (at && passer) {
      // Il arrive lancé, toujours derrière le passeur.
      let x = at[0] + d * 1.2;
      if ((x - passer[0]) * d > -0.9) x = passer[0] - d * 0.9;
      b.at(0.7, to, [x, at[1]]);
    }
    b.done();
  },

  // Le porteur `carrier` avance de `gain` mètres depuis où il est, puis il est plaqué
  // (par `tackler` ou le défenseur le plus proche) ; un ruck se forme, le jeu reprend.
  carryOn(carrier, { gain = 2, result = "tackled", tackler = null } = {}) {
    const team = teamOf(carrier);
    const d = dir(team);
    const D = other(team);
    const b = this.tl.beat(result === "break" ? 1500 : 1000, { label: "carry" });
    const from = b.pos(carrier, 0);
    if (!from) {
      b.done();
      return;
    }
    const ahead = Math.min(gain, Math.max(1, toGoal(team, from[0]) - 2));
    const point = [from[0] + d * ahead, clampY(from[1] + (result === "break" ? (MID_Y - from[1]) * 0.25 : this.rnd(-1, 1)), 4)];
    const tHit = result === "break" ? 0.7 : 0.45;
    b.ball(0, { holder: carrier });
    b.at(tHit, carrier, point);
    const hitter = tackler && b.start.pos[tackler] ? tackler : this.nearest(b, D, point, 0, 1)[0];
    if (hitter) b.at(tHit, hitter, [point[0] + d * 0.9, point[1] + 0.4]);
    this.pressure(b, tHit, team, { rush: 1.5, toward: point, frontX: point[0], except: [carrier, hitter] });
    b.down(tHit, [carrier, hitter].filter(Boolean));
    b.ball(tHit + 0.03, { at: [point[0] - d * 0.5, point[1]] });
    b.caption(0, result === "break" ? `Franchissement de ${this.name(carrier)} !` : `${this.name(carrier)} au contact`);
    b.focus(0, carrier);
    this.moveBall(...point);
    this.ruck = carrier;
    this.cleaners = this.support(b, team, point, tHit, [carrier, hitter]);
    const end = this.open(team);
    this.settle(b, end, [carrier]);
    b.at(1, carrier, end.pos[carrier] ?? point);
    b.down(Math.min(tHit + 0.2, 0.95), [carrier]);
    b.ball(Math.min(tHit + 0.25, 0.97), end.ball);
    b.done();
    this.att = team;
    this.sit = null;
  },

  // Mêlée ou touche gagnée par `team` : le demi de mêlée reçoit, sert l'ouvreur, contact.
  setPieceOut(team) {
    const nine = keyOf(team, 9);
    const ten = keyOf(team, 10);
    const state = this.now();
    if (!state.pos[nine] || !state.pos[ten] || this.gone.has(ten)) {
      this.realign();
      return;
    }
    const d = dir(team);
    const b = this.tl.beat(700, { label: "out" });
    const at = b.pos(nine, 0);
    b.ball(0.15, { holder: nine, h: 0.4 });
    b.at(0.15, nine, at);
    const ten0 = b.pos(ten, 0);
    let x = ten0[0] + d * 2;
    if ((x - at[0]) * d > -1.5) x = at[0] - d * 1.5;
    b.at(0.6, ten, [x, ten0[1]]);
    b.ball(0.6, { holder: ten, h: 0.6 });
    b.caption(0, `Ballon gagné · ${this.club(team)}`);
    b.focus(0, ten);
    b.done();
    this.sit = null;
    this.carryOn(ten, { gain: this.rnd(1, 4) });
  },

  // Le joueur concerné prend le ballon à l'adversaire : il le porte, son équipe repart.
  steal(actor) {
    const b = this.tl.beat(900, { label: "steal" });
    const at = b.pos(actor, 0);
    b.ball(0.3, { holder: actor, h: 0.4 });
    if (at) b.at(0.3, actor, at);
    b.caption(0, `Ballon récupéré par ${this.name(actor)} !`);
    b.focus(0, actor);
    b.done();
    if (at) this.moveBall(...at);
    this.ruck = null;
    this.cleaners = [];
    this.att = "us";
    this.sit = null;
    const end = this.open("us", { carrier: actor });
    if (end.pos[actor] && at) end.pos[actor] = at;
    end.ball = { holder: actor };
    end.down = [];
    this.align(end, { ms: 800 });
  },

  // Ballon perdu : l'adversaire le ramasse.
  lose(actor, taker) {
    const b = this.tl.beat(900, { label: "lost" });
    const at = b.pos(actor, 0) ?? [this.loc.x, this.loc.y];
    const spot = [at[0] + 1.2, at[1] + 0.6];
    const grab = taker ?? this.nearest(b, "them", spot, 0, 1)[0];
    b.ball(0.25, { at: spot });
    if (grab) {
      b.at(0.5, grab, spot);
      b.ball(0.55, { holder: grab });
    }
    b.caption(0, `Ballon perdu · ${this.club("them")} récupère`);
    b.focus(0, actor);
    b.done();
    this.moveBall(...spot);
    this.ruck = null;
    this.cleaners = [];
    this.att = "them";
    this.sit = null;
    this.align(this.open("them"), { ms: 800 });
  },

  // Le joueur concerné est battu par le porteur adverse (`carrier`), qui file avant d'être repris.
  beaten(actor, carrier, { short = false } = {}) {
    const b = this.tl.beat(short ? 500 : 1100, { label: "beaten" });
    const at = b.pos(actor, 0);
    if (at) b.at(0.35, actor, [at[0] - 0.8, at[1] + 1.2]);
    b.down(0.35, [actor]);
    b.caption(0, `${this.name(actor)} est battu`);
    b.focus(0, actor);
    b.done();
    if (!short && carrier) this.carryOn(carrier, { gain: this.rnd(6, 10) });
  },

  // Un coup de pied du joueur concerné : en touche, long, chandelle, rasant, par-dessus,
  // vers l'ailier opposé. `catcher` : qui le reprend (chandelle reprise, grubber, ailier).
  kickTo(actor, kind, catcher, { regather = false } = {}) {
    const team = teamOf(actor);
    const d = dir(team);
    const b = this.tl.beat(kind === "touch" || kind === "long" ? 1500 : 1300, { essential: true, label: "kick" });
    const at = b.pos(actor, 0);
    if (!at) {
      b.done();
      return;
    }
    b.ball(0.12, { holder: actor });
    let land;
    let h = 12;
    if (kind === "touch") {
      const side = at[1] < MID_Y ? -0.8 : WIDTH + 0.8;
      land = [clampX(at[0] + d * this.rnd(25, 40)), side];
      h = 10;
    } else if (kind === "long") {
      land = [clampX(Math.min(at[0] + d * 42, fromGoal(team, 8))), clampY(at[1] + this.rnd(-10, 10), 6)];
      h = 14;
    } else if (kind === "box") {
      land = [at[0] + d * this.rnd(18, 24), clampY(at[1] + this.rnd(-4, 4), 5)];
      h = 15;
    } else if (kind === "cross") {
      const target = catcher ? b.pos(catcher, 0) : [at[0] + d * 12, WIDTH - 5];
      land = [Math.min(target[0] + d * 6, fromGoal(team, 4)), target[1]];
      h = 9;
    } else if (kind === "chip") {
      land = [at[0] + d * 9, at[1]];
      h = 5;
    } else {
      land = [at[0] + d * 12, at[1] + this.rnd(-2, 2)];
      h = 0.3;
    }
    b.ball(0.55, { at: land, h });
    const D = other(team);
    // Les chasseurs montent ; en face, on se replace sous le ballon.
    for (const [key, p] of Object.entries(b.start.pos)) {
      if (key === "ref" || key === actor || key === catcher) continue;
      if (teamOf(key) === team) b.at(0.6, key, [p[0] + d * 6, p[1]]);
      else b.at(0.6, key, [p[0] + d * 4, p[1] + (land[1] - p[1]) * 0.15]);
    }
    const labels = {
      touch: `${this.name(actor)} trouve la touche`,
      long: `Long coup de pied de ${this.name(actor)}`,
      box: `Chandelle de ${this.name(actor)}`,
      cross: `Coup de pied par-dessus de ${this.name(actor)}`,
      chip: `Petit coup de pied de ${this.name(actor)}`,
      grubber: `Coup de pied rasant de ${this.name(actor)}`,
    };
    b.caption(0, labels[kind]);
    b.focus(0, actor);
    let owner = kind === "touch" ? D : D;
    const grab = catcher ?? (regather ? this.nearest(b, team, land, 0.3, 1, [actor])[0] : this.nearest(b, D, land, 0.3, 1)[0]);
    if (kind !== "touch" && grab) {
      const spot = clampPoint([land[0], land[1]]);
      b.at(0.56, grab, spot);
      b.ball(0.58, { holder: grab, h: 1 });
      owner = teamOf(grab);
      if (kind === "box" || kind === "long") {
        b.caption(0.58, owner === team ? `Repris par ${this.name(grab)} !` : `Capté par ${this.name(grab)}`);
      }
    }
    b.done();
    this.moveBall(land[0], kind === "touch" ? (land[1] < MID_Y ? 3 : WIDTH - 3) : land[1]);
    this.sit = null;
    this.ruck = null;
    this.cleaners = [];
    this.att = owner;
    if (kind === "touch") {
      // La touche qui suit : lancer pour nous après une pénalité ou un 50-22.
      this.att = ["long_penalty", "fifty_22"].includes(this.lastSituation) ? team : D;
      this.lineoutSetup(this.att);
    }
  },

  // Une touche mise en place, sans la jouer (la minute s'arrête là).
  lineoutSetup(thrower) {
    const f = lineout(this.present, { thrower, x0: this.loc.x, side: this.loc.y < MID_Y ? 0 : WIDTH });
    this.align(f, { ms: 900, caption: `Touche pour ${this.club(thrower)}` });
  },

  // Coup de pied au but du joueur concerné, d'où il est (drop) ou du tee (pénalité).
  kickFromHand(actor, success, kind) {
    const team = teamOf(actor);
    const b = this.tl.beat(1700, { essential: true, label: "kick" });
    const at = b.pos(actor, 0);
    if (!at) {
      b.done();
      return;
    }
    const tee = this.sit?.tee ?? at;
    b.ball(0, { holder: actor });
    this.kickAtPosts(b, team, actor, tee, success, 0.3);
    const verb = kind === "drop" ? "Drop" : "Pénalité";
    b.caption(0, `${verb} de ${this.name(actor)}…`);
    b.caption(0.84, success ? `${verb} réussi${kind === "drop" ? "" : "e"} · ${this.name(actor)}` : `${verb} manqué${kind === "drop" ? "" : "e"}`);
    b.focus(0, actor);
    b.done();
    this.moveBall(50, MID_Y);
    this.sit = null;
    this.att = other(team);
  },

  // Coup de sifflet : l'arbitre au point de la faute.
  whistle(caption) {
    const b = this.tl.beat(600, { label: "whistle" });
    const point = [this.loc.x, this.loc.y];
    b.at(0.6, "ref", [point[0] + 1.5, point[1] + 2]);
    b.caption(0, caption);
    b.done();
  },

  // Le point de pénalité près de l'action, à portée pour `team`.
  markNear(team) {
    const m = toGoal(team, this.loc.x);
    if (m > 46 || m < 8) return this.penaltyMark(team);
    return [this.loc.x, clamp(this.loc.y, 10, WIDTH - 10)];
  },

  // Le jeu reprend sa forme, sans action.
  realign() {
    this.sit = null;
    this.align(this.open(this.att ?? "us"), { ms: 800 });
  },
};
