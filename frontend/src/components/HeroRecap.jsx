import { DILEMMAS, MATCH_STATS, formatNote } from "../format.js";
import Modal from "./Modal.jsx";

// Ce que rapporte chacun de ses points au tableau d'affichage.
const SCORING = [
  { type: "try", label: "essai", plural: "essais" },
  { type: "conversion", label: "transformation", plural: "transformations" },
  { type: "penalty_goal", label: "pénalité", plural: "pénalités" },
  { type: "drop_goal", label: "drop", plural: "drops" },
];

// Carrière de joueur, coup de sifflet final : le match du joueur incarné en une fenêtre.
// Sa note, son temps de jeu, ses points, ses statistiques, puis chacune de ses actions
// (la situation, son choix, ce qu'il en est sorti). `onContinue` finit la journée ;
// `onClose` laisse revoir le match (le bouton du tableau d'affichage finit la journée).
export default function HeroRecap({ live, side, finishing, doneLabel, onContinue, onClose }) {
  const me = side.players.find((p) => p.id === live.hero.player_id);
  if (!me) return null;
  const outcomes = live.hero.outcomes;
  const won = outcomes.filter((o) => o.success).length;
  const mine = live.events.filter((e) => e.player_id === me.id);
  const points = mine.reduce((sum, e) => sum + e.points, 0);
  const scoring = SCORING.map((kind) => ({ ...kind, count: mine.filter((e) => e.type === kind.type).length })).filter(
    (kind) => kind.count > 0,
  );
  const cards = mine.filter((e) => e.type === "yellow_card" || e.type === "red_card");
  const minutes = me.stats?.minutes ?? 0;
  const ours = live.home.club.id === side.club.id;
  const result = side.score > (ours ? live.away : live.home).score ? "V" : side.score === (ours ? live.away : live.home).score ? "N" : "D";
  const time =
    minutes === 0
      ? "Resté sur le banc"
      : me.since > 0
        ? `Entré à la ${me.since}e minute · ${minutes} min`
        : me.until !== null
          ? `Sorti à la ${me.until}e minute · ${minutes} min`
          : `${minutes} min, tout le match`;

  return (
    <Modal compact className="modal--dialog hero-recap" onClose={onClose}>
      <div>
        <p className="eyebrow">Coup de sifflet final</p>
        <h2 className="confirm__title hero-recap__score">
          <span className={`pill pill--${result}`}>{result}</span>
          {live.home.club.name} {live.home.score} – {live.away.score} {live.away.club.name}
        </h2>
      </div>

      <div className="hero-recap__head">
        <div className="hero-recap__note">
          <span className="num">{me.rating !== null ? formatNote(me.rating) : "–"}</span>
          <span className="muted">ta note</span>
        </div>
        <div className="hero-recap__facts">
          <strong>{me.name}</strong>
          <span className="muted">{time}</span>
          <span>
            {points > 0
              ? `${points} point${points > 1 ? "s" : ""} : ${scoring
                  .map((kind) => `${kind.count} ${kind.count > 1 ? kind.plural : kind.label}`)
                  .join(", ")}`
              : "Pas de points marqués"}
            {cards.length > 0 && ` · ${cards.some((e) => e.type === "red_card") ? "carton rouge" : "carton jaune"}`}
          </span>
        </div>
      </div>

      {me.stats && minutes > 0 && (
        <dl className="hero-recap__stats">
          {MATCH_STATS.map((stat) => (
            <div key={stat.key} className="hero-recap__stat">
              <dt className="muted">{stat.label}</dt>
              <dd className="num">{me.stats[stat.key]}</dd>
            </div>
          ))}
        </dl>
      )}

      <section className="hero-recap__actions">
        <h3 className="eyebrow">
          {outcomes.length === 0
            ? "Aucune action à jouer pour toi"
            : `Tes actions · ${won} réussie${won > 1 ? "s" : ""} sur ${outcomes.length}`}
        </h3>
        {outcomes.length > 0 && (
          <ol className="hero-recap__list">
            {outcomes.map((o) => {
              const situation = DILEMMAS[o.situation];
              const option = situation?.options[o.option];
              return (
                <li key={`${o.minute}-${o.situation}`} className="hero-recap__action">
                  <span className="num muted hero-recap__minute">{o.minute}'</span>
                  <span>
                    <strong>{situation?.title ?? o.situation}</strong>
                    <span className="muted"> · {option?.label ?? o.option}</span>
                    <span className="hero-recap__text">{option?.[o.success ? "won" : "lost"]}</span>
                  </span>
                  <span className={`hero-recap__mark hero-recap__mark--${o.success ? "won" : "lost"}`}>
                    {o.success ? "Réussi" : "Raté"}
                  </span>
                </li>
              );
            })}
          </ol>
        )}
      </section>

      <div className="confirm__actions">
        <button type="button" className="button" onClick={onClose}>
          Revoir le match
        </button>
        <button type="button" className="button button--primary" autoFocus disabled={finishing} onClick={onContinue}>
          {finishing ? "Fin de journée…" : doneLabel}
        </button>
      </div>
    </Modal>
  );
}
