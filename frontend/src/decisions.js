import { CRUNCH_OPTIONS, DILEMMA_EFFECTS, DILEMMAS, formatNote } from "./format.js";

// Les textes des décisions en match, communs à la fenêtre de texte (DilemmaDialog,
// CrunchDialog dans pages/Match.jsx) et aux scènes en 3D (src/scene).

export const signed = (value) => `${value > 0 ? "+" : value < 0 ? "−" : ""}${formatNote(Math.abs(value))}`;

// Ce qu'a donné un dilemme du joueur incarné : le texte de la voie (réussie ou non),
// complété par l'effet sur le match, ou par le nom de celui qui a marqué. `fresh` : les
// événements du match depuis le choix.
export function dilemmaText(outcome, fresh) {
  const option = DILEMMAS[outcome.situation].options[outcome.option];
  const scored = fresh.find((e) => e.type === "try" || e.type === "drop_goal" || e.type === "penalty_goal");
  let text = outcome.success ? option.won : option.lost;
  if (!outcome.success && DILEMMA_EFFECTS[outcome.effect]) text += ` ${DILEMMA_EFFECTS[outcome.effect]}`;
  if (scored && outcome.effect === "assist") text = `${option.won} ${scored.player_name} aplatit.`;
  if (scored && outcome.effect === "penalty_won") {
    text = `${option.won} ${scored.player_name} ${scored.type === "penalty_goal" ? "passe la pénalité" : "manque la pénalité"}.`;
  }
  return text;
}

// --- Choix crucial ------------------------------------------------------------------

export const points = (n) => `${n} pt${n > 1 ? "s" : ""}`;

// Ce que `scored` points font au score, quand on a `margin` points d'avance.
export function swing(margin, scored) {
  const after = margin + scored;
  if (margin > 0) return after >= 8 ? "deux scores d'avance" : "creuse l'écart";
  if (after === 0) return "égalise";
  return after > 0 ? "passe devant" : "reste derrière";
}

// Où en est le match : l'écart et le temps qui reste.
export function crunchSituation(margin, left) {
  const score = margin === 0 ? "À égalité" : margin > 0 ? `Devant de ${points(margin)}` : `Menés de ${points(-margin)}`;
  const time = left <= 0 ? "dernière action du match" : `${left} minute${left > 1 ? "s" : ""} à jouer`;
  return `${score}, ${time}`;
}

// Ce qu'une suite fait au score : « 3 pts · passe devant ».
export function crunchStake(key, margin) {
  if (key === "kick") return `${points(3)} · ${swing(margin, 3)}`;
  return swing(margin, 5) === swing(margin, 7)
    ? `${points(5)} ou 7 · ${swing(margin, 5)}`
    : `${points(5)} · ${swing(margin, 5)}, ${swing(margin, 7)} si transformé`;
}

// Ce qu'a donné le choix crucial : le verdict (« Essai ! », « Les 3 points », « Raté »)
// et son récit, d'après les événements depuis le choix.
export function crunchResult(option, fresh) {
  const scored = fresh.find((e) => e.type === "try" || e.type === "penalty_goal");
  const conversion = fresh.find((e) => e.type === "conversion" || e.type === "conversion_missed");
  const verdict = scored?.type === "try" ? "Essai !" : scored ? "Les 3 points" : "Raté";
  let text = CRUNCH_OPTIONS[option].missed;
  if (scored?.type === "try") {
    text = `${scored.player_name} aplatit. ${conversion?.type === "conversion" ? "Transformé par" : "Transformation manquée par"} ${conversion?.player_name}.`;
  } else if (scored) {
    text = `${scored.player_name} passe la pénalité.`;
  }
  return { scored: Boolean(scored), verdict, text };
}

// --- Qui joue l'action ------------------------------------------------------------------

// Les dilemmes déjà tranchés : du joueur incarné, ou du manager pour ses joueurs.
export const dilemmaOutcomes = (live) => live.outcomes ?? live.hero?.outcomes ?? [];

// Le joueur d'un dilemme (`playerId` : celui du dilemme ou de son issue) et la voix des
// textes : le joueur incarné (« À toi de jouer », « ta note »), ou le joueur pour qui le
// manager tranche (« Consigne · Dupont (12) », « sa note »). Les situations restent à la
// deuxième personne : c'est le manager qui parle à son joueur.
export function dilemmaActor(live, side, playerId) {
  const id = playerId ?? live.hero?.player_id;
  const player = side.players.find((p) => p.id === id) ?? null;
  const coach = playerId != null && playerId !== live.hero?.player_id;
  const name = player ? (player.last_name ?? player.name) : "ton joueur";
  const who = player ? `${name} (${player.slot_number ?? player.number})` : name;
  return {
    player,
    coach,
    call: (chained) => (coach ? `${chained ? "Dans la foulée" : "Consigne"} · ${who}` : chained ? "Dans la foulée" : "À toi de jouer"),
    note: coach ? "sa note" : "ta note",
    Note: coach ? `Note de ${name}` : "Ta note",
  };
}
