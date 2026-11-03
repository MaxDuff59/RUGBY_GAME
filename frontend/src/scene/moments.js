import { canStage } from "./prefs.js";

// Les moments d'un match qui se regardent en 3D, sans décision à prendre (MomentScene) :
// l'entrée des équipes d'une finale ou d'un derby, l'essai de la victoire, la séance de
// tirs au but, la remise du trophée. Ce module ne charge pas three.js.

const SEEN = "rugby.moments";

// L'essai qui a donné l'avantage pour de bon, s'il est venu dans les dernières minutes.
const LATE_MINUTES = 5;

function winningTry(live) {
  let us = 0;
  let them = 0;
  let decisive = null;
  for (const event of live.events) {
    if (!event.points) continue;
    const ahead = us > them;
    if (event.club_id === live.my_club_id) us += event.points;
    else them += event.points;
    if (us <= them) decisive = null;
    else if (!ahead) decisive = event;
  }
  if (decisive?.type === "conversion") {
    decisive = live.events.findLast(
      (event) => event.type === "try" && event.club_id === live.my_club_id && event.minute === decisive.minute,
    );
  }
  if (decisive?.type !== "try" || decisive.minute < live.last_minute - LATE_MINUTES) return null;
  return decisive;
}

// Les moments de ce match à l'instant présent, dans l'ordre : `kind`, de quoi les jouer
// (`data`), et leur clé (un moment ne se joue qu'une fois).
export function matchMoments(live) {
  const mine = live.home.club.id === live.my_club_id ? live.home : live.away;
  const other = mine === live.home ? live.away : live.home;
  const numberOf = (side, id) => {
    const player = side.players.find((p) => p.id === id);
    return player?.slot_number ?? player?.number ?? null;
  };
  const moment = (kind, data) => ({ key: `${live.match_id}:${kind}`, kind, data });
  if (!live.finished) {
    const opening = live.minute === 0 && (live.stage === "final" || Boolean(live.derby));
    return opening ? [moment("tunnel", { final: live.stage === "final", derby: live.derby })] : [];
  }
  const found = [];
  const shootout = live.home.shootout !== null;
  if (shootout) {
    const kicks = live.events
      .filter((event) => event.type === "shootout_goal" || event.type === "shootout_missed")
      .map((event) => {
        const us = event.club_id === live.my_club_id;
        return {
          us,
          number: numberOf(us ? mine : other, event.player_id),
          name: event.player_name,
          scored: event.type === "shootout_goal",
        };
      });
    if (kicks.length) found.push(moment("shootout", { kicks }));
  } else {
    const decisive = winningTry(live);
    if (decisive) {
      found.push(moment("winning_try", { minute: decisive.minute, name: decisive.player_name, number: numberOf(mine, decisive.player_id) }));
    }
  }
  const won = shootout ? mine.shootout > other.shootout : mine.score > other.score;
  if (won && live.stage === "final") found.push(moment("trophy", { competition: live.competition ?? null }));
  return found;
}

function seen() {
  try {
    return JSON.parse(sessionStorage.getItem(SEEN)) ?? [];
  } catch {
    return [];
  }
}

// Vrai la première fois que ce moment est demandé, si les scènes peuvent se jouer.
export function wantsMoment(key) {
  const keys = seen();
  if (keys.includes(key) || !canStage()) return false;
  try {
    sessionStorage.setItem(SEEN, JSON.stringify([...keys, key]));
  } catch {
    // Stockage refusé : le moment se rejouera si la page est rechargée.
  }
  return true;
}
