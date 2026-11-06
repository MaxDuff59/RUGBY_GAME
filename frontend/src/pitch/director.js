import { DILEMMAS } from "../format.js";
import { MID_Y, clamp, fromGoal, keyOf, numberOf, other, toGoal } from "./geometry.js";
import { kickoff, openPlay } from "./formations.js";
import { Scene } from "./scene.js";
import { SceneMoves, playOutcome, stageSituation } from "./situations.js";

Object.assign(Scene.prototype, SceneMoves);

// Le metteur en scène du terrain 2D : d'une réponse du match en direct (`live`), il tire
// les actions à montrer pour la minute qui vient d'être jouée, d'après ce que le moteur
// a noté (`live.play` : temps de jeu, touche, action dangereuse, pénalité) et les
// événements (essais, coups de pied, cartons). Il garde d'une minute à l'autre où est le
// ballon et qui l'a (`memo`), pour que le jeu s'enchaîne. Un choix crucial ou un dilemme
// en attente laisse le terrain sur leur mise en place ; leur issue se joue ensuite.

// Ce que la page sait du match, rangé pour le terrain : qui est sur le terrain, à quelle
// place, et comment passer d'un joueur (id) à sa clé (« us9 »).
export function pitchContext(live) {
  const mine = live.home.club.id === live.my_club_id ? live.home : live.away;
  const theirs = mine === live.home ? live.away : live.home;
  const teamOfClub = (id) => (id === mine.club.id ? "us" : "them");
  const present = { us: new Set(), them: new Set() };
  const onField = new Map();
  const anywhere = new Map();
  const people = new Map();
  for (const [team, side] of [
    ["us", mine],
    ["them", theirs],
  ]) {
    for (const p of side.players) {
      if (!p.slot_number) continue;
      const key = keyOf(team, p.slot_number);
      anywhere.set(p.id, key);
      if (p.status === "field") {
        present[team].add(p.slot_number);
        onField.set(p.id, key);
        people.set(key, p);
      }
    }
  }
  const sideOf = (team) => (team === "us" ? mine : theirs);
  // Qui donne le coup d'envoi : tiré une fois pour toutes d'après le match.
  const homeKicks = live.match_id % 2 === 0;
  const opening = (homeKicks ? live.home : live.away) === mine ? "us" : "them";
  return {
    live,
    mine,
    theirs,
    present,
    opening,
    teamOfClub,
    keyOf: (id) => (id === null || id === undefined ? null : (onField.get(id) ?? null)),
    anyKey: (id) => anywhere.get(id) ?? null,
    person: (key) => people.get(key) ?? null,
    name: (key) => people.get(key)?.last_name || people.get(key)?.name || "",
    clubName: (team) => sideOf(team).club.name,
    kicker: (team) => onField.get(sideOf(team).kicker_id) ?? null,
  };
}

const kickSide = (live, minute) => ((live.match_id + minute) % 2 ? 1 : -1);

const signature = (live) =>
  [
    live.minute,
    live.events.length,
    live.outcomes.length,
    live.dilemma ? `${live.dilemma.minute}:${live.dilemma.situation}` : "",
    live.crunch ? live.crunch.minute : "",
    live.play?.penalty?.option ?? "",
    live.finished,
  ].join("|");

// L'état de départ quand rien n'a encore été montré (page ouverte en cours de match).
function initial(ctx) {
  const { live } = ctx;
  if (live.minute === 0 || !live.play) {
    const f = kickoff(ctx.present, { kicker: ctx.opening, ks: kickSide(live, 1) });
    return { start: { pos: f.pos, ball: f.ball, down: [] }, att: ctx.opening, loc: { x: 50, y: MID_Y } };
  }
  const first = live.play.phases[0];
  const att = first ? ctx.teamOfClub(first.club_id) : ctx.opening;
  const f = openPlay(ctx.present, { att, bx: 50, by: MID_Y, seed: live.match_id });
  return { start: { pos: f.pos, ball: f.ball, down: f.down }, att, loc: { x: 50, y: MID_Y } };
}

// Rend { timeline, memo, animate } pour la réponse `live`, ou null s'il n'y a rien de
// neuf à montrer depuis `memo`.
export function direct(ctx, memo) {
  const { live } = ctx;
  const sig = signature(live);
  const same = memo && memo.matchId === live.match_id;
  if (same && memo.sig === sig) return null;
  const minute = live.minute;
  const continuing = same && memo.minute === minute;
  const onward = same && minute > memo.minute;
  let start;
  let att;
  let loc;
  if (continuing || onward) ({ end: start, att, loc } = memo);
  else ({ start, att, loc } = initial(ctx));
  const S = new Scene(ctx, start, { att, loc, seed: live.match_id * 977 + minute * 31 + live.events.length });
  if (continuing) {
    S.sit = memo.sit;
    S.lastSituation = memo.lastSituation;
  }
  const fresh = live.events.slice(continuing ? memo.events : live.events.length);

  if (continuing) {
    if (memo.frozen === "crunch" && !live.crunch) penaltyChoice(S, ctx, fresh);
    else if (memo.frozen === "dilemma" && live.outcomes.length > memo.outcomes) {
      for (const outcome of live.outcomes.slice(memo.outcomes)) playOutcome(S, outcome, fresh, ctx);
    }
  } else if (minute > 0) {
    scriptMinute(S, ctx);
  }
  // Un dilemme en attente (aussi celui qui s'enchaîne sur le précédent).
  const dilemma = live.dilemma;
  const staged = continuing && memo.frozen === "dilemma" && memo.dilemmaKey === dilemmaKey(live);
  if (dilemma && !staged) {
    const id = dilemma.player_id ?? live.hero?.player_id;
    stageSituation(S, dilemma.situation, ctx.keyOf(id), {
      title: DILEMMAS[dilemma.situation]?.title ?? "À toi de jouer",
      chained: dilemma.chained,
    });
  }
  const end = S.tl.stateAt(S.tl.length);
  return {
    timeline: S.tl,
    animate: Boolean(same),
    memo: {
      matchId: live.match_id,
      sig,
      minute,
      events: live.events.length,
      outcomes: live.outcomes.length,
      frozen: live.crunch ? "crunch" : live.dilemma ? "dilemma" : null,
      dilemmaKey: dilemmaKey(live),
      end: { pos: end.pos, ball: S.tl.lastBall(), down: end.down, gone: end.gone },
      att: S.att,
      loc: S.loc,
      sit: S.sit,
      lastSituation: S.lastSituation,
    },
  };
}

const dilemmaKey = (live) => (live.dilemma ? `${live.dilemma.minute}:${live.dilemma.situation}:${live.outcomes.length}` : null);

// --- La minute ----------------------------------------------------------------------------

function scriptMinute(S, ctx) {
  const { live } = ctx;
  const play = live.play;
  const minute = live.minute;
  if (!play || play.minute !== minute) return;
  const T = ctx.teamOfClub;
  const events = live.events.filter((e) => e.minute === minute);
  const prior = live.events.filter((e) => e.minute === minute - 1 && e.points > 0);

  // Le coup d'envoi : début de chaque période, ou après des points.
  const half = live.half_time;
  let kicker = null;
  if (minute === 1 || minute === 81) kicker = ctx.opening;
  else if (minute === half + 1 || minute === 91) kicker = other(ctx.opening);
  else if (prior.length) kicker = other(T(prior.at(-1).club_id));
  if (kicker) S.kickoff(kicker, { ks: kickSide(live, minute) });

  // Les cartons d'abord (ils tombent en début de minute), et leur pénalité.
  const used = new Set();
  const kicks = events.filter((e) => e.type === "penalty_goal" || e.type === "penalty_missed");
  for (const card of events.filter((e) => e.type === "yellow_card" || e.type === "red_card")) {
    const team = T(card.club_id);
    S.card(ctx.anyKey(card.player_id), card.type === "red_card", card.player_name);
    const kick = kicks.find((e) => T(e.club_id) === other(team) && !used.has(e));
    if (kick) {
      used.add(kick);
      S.penaltyGoal(other(team), ctx.keyOf(kick.player_id), kick.type === "penalty_goal");
      if (kick.type === "penalty_goal") S.kickoff(team, { ks: -kickSide(live, minute) });
    }
  }

  const phases = play.phases
    .map((p) => ({
      team: T(p.club_id),
      carrier: ctx.keyOf(p.carrier_id),
      tackler: ctx.keyOf(p.tackler_id),
      result: p.result,
      other: ctx.keyOf(p.other_id),
    }))
    .filter((p) => p.carrier);
  const chance = play.chance;

  // L'équipe qui a le ballon cette minute : celle de l'action dangereuse, sinon celle qui
  // a joué le plus de temps de jeu.
  let P;
  if (chance) P = T(chance.club_id);
  else {
    const count = { us: 0, them: 0 };
    phases.forEach((p) => (count[p.team] += 1));
    P = count.us === count.them ? (phases.at(-1)?.team ?? S.att) : count.us > count.them ? "us" : "them";
  }

  // La touche qui lui donne le ballon.
  const lo = play.lineout;
  if (lo && T(lo.won_by) === P) {
    const thrower = T(lo.club_id);
    if (S.att !== thrower) S.exchange(thrower, { touch: true });
    S.lineout({ thrower, winner: P, jumper: ctx.keyOf(lo.jumper_id) });
  }
  // Le ballon change de mains : ballon gratté, ou jeu au pied.
  if (S.att !== P) {
    const turnover = phases.find((p) => p.team !== P && p.result === "turnover");
    if (turnover) S.phase(turnover);
    if (S.att !== P) S.exchange(P);
  }

  // Ses temps de jeu, qui l'amènent là où l'action dangereuse se joue. Un ballon gratté
  // ne se montre qu'en dernier (sinon il garde le ballon, au sol, après un contest).
  let mine = phases.filter((p) => p.team === P);
  mine = mine.map((p, i) => (p.result === "turnover" && (chance || i < mine.length - 1) ? { ...p, result: "tackled" } : p));
  const tryEvent = events.find((e) => e.type === "try" && T(e.club_id) === P);
  const scorer = tryEvent ? ctx.keyOf(tryEvent.player_id) : null;
  const option = play.penalty && T(play.penalty.club_id) === P ? play.penalty.option : null;
  const target = chance ? targetFor(S, chance.result, option, scorer) : null;
  const gains = plan(S, P, mine, target);
  mine.forEach((p, i) => S.phase(p, { next: mine[i + 1] ?? null, gain: gains[i] }));
  if (!chance) return;

  // L'action dangereuse.
  const conversion = () => {
    const e = events.find((x) => (x.type === "conversion" || x.type === "conversion_missed") && T(x.club_id) === P);
    if (e) S.conversion(P, ctx.keyOf(e.player_id), e.type === "conversion");
  };
  const lastCarrier = mine.at(-1)?.carrier ?? [8, 6, 4].map((n) => keyOf(P, n)).find((key) => ctx.present[P].has(numberOf(key)));
  if (scorer && (chance.result === "try" || chance.result === "penalty")) {
    if (option === "touch") S.maulPenalty(P, scorer, { kicker: ctx.kicker(P) });
    else if (option === "scrum") S.scrumPenalty(P, scorer);
    else if (option === "play") S.tapPenalty(P, scorer, lastCarrier);
    else S.tryRun(P, scorer);
    conversion();
    return;
  }
  if (chance.result === "penalty") {
    if (option === "touch") S.maulPenalty(P, null, { kicker: ctx.kicker(P) });
    else if (option === "scrum") S.scrumPenalty(P, null);
    else if (option === "play") S.tapPenalty(P, null, lastCarrier);
    else {
      const kick = kicks.find((e) => T(e.club_id) === P && !used.has(e));
      if (kick) S.penaltyGoal(P, ctx.keyOf(kick.player_id), kick.type === "penalty_goal");
    }
    return;
  }
  if (chance.result === "drop") {
    const drop = events.find((e) => e.type === "drop_goal" && T(e.club_id) === P);
    if (drop) {
      if (toGoal(P, S.loc.x) > 40) S.moveBall(fromGoal(P, 30), S.loc.y);
      S.drop(P, ctx.keyOf(drop.player_id));
    }
    return;
  }
  if (chance.result === "held") {
    if (lastCarrier) S.held(P, lastCarrier);
    return;
  }
  if (chance.result === "crunch") {
    S.awaitPenalty(P, live.crunch ? "Pénalité : à toi de choisir" : `Pénalité pour ${S.club(P)}`);
  }
}

// À combien de mètres de la ligne adverse l'action dangereuse se joue.
function targetFor(S, result, option, scorer) {
  if (result === "try" || (result === "penalty" && scorer)) {
    if (option === "touch") return S.rnd(16, 26);
    if (option === "scrum") return S.rnd(10, 16);
    if (option === "play") return S.rnd(8, 11);
    return numberOf(scorer) <= 8 ? S.rnd(2.5, 4.5) : S.rnd(10, 24);
  }
  if (result === "penalty") return option === "kick" || !option ? S.rnd(24, 38) : S.rnd(14, 24);
  if (result === "drop") return S.rnd(22, 30);
  if (result === "held") return S.rnd(3, 6);
  if (result === "crunch") return S.rnd(22, 34);
  return null;
}

// Les mètres de chaque temps de jeu pour arriver à `target` (null : leur gain naturel).
function plan(S, team, phases, target) {
  if (target === null || !phases.length) return phases.map(() => null);
  const natural = phases.map((p) => (p.result === "break" ? 24 : p.result === "missed" ? 7 : 1.8));
  const need = toGoal(team, S.loc.x) - target;
  if (need <= 0) return phases.map(() => S.rnd(0, 0.8));
  const total = natural.reduce((sum, g) => sum + g, 0);
  const k = need / total;
  return phases.map((p, i) => clamp(natural[i] * k, 0.3, p.result === "break" ? 42 : p.result === "missed" ? 16 : 11));
}

// Le choix crucial tranché : la pénalité se joue comme le manager l'a voulu.
function penaltyChoice(S, ctx, fresh) {
  const { live } = ctx;
  const penalty = live.play?.penalty;
  if (!penalty) return;
  const T = ctx.teamOfClub;
  const team = T(penalty.club_id);
  const tryEvent = fresh.find((e) => e.type === "try" && T(e.club_id) === team);
  const scorer = tryEvent ? ctx.keyOf(tryEvent.player_id) : null;
  const carrier = [8, 6, 4].map((n) => keyOf(team, n)).find((key) => ctx.present[team].has(numberOf(key)));
  if (penalty.option === "kick") {
    const kick = fresh.find((e) => (e.type === "penalty_goal" || e.type === "penalty_missed") && T(e.club_id) === team);
    if (kick) S.penaltyGoal(team, ctx.keyOf(kick.player_id), kick.type === "penalty_goal", [S.loc.x, S.loc.y]);
  } else if (penalty.option === "touch") S.maulPenalty(team, scorer, { kicker: ctx.kicker(team) });
  else if (penalty.option === "scrum") S.scrumPenalty(team, scorer);
  else S.tapPenalty(team, scorer, carrier);
  if (scorer) {
    const e = fresh.find((x) => (x.type === "conversion" || x.type === "conversion_missed") && T(x.club_id) === team);
    if (e) S.conversion(team, ctx.keyOf(e.player_id), e.type === "conversion");
  }
}
