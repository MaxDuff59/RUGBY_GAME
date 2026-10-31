import { useState } from "react";

import { dilemmaActor, dilemmaOutcomes, dilemmaText, signed } from "../decisions.js";
import { DILEMMAS, formatNote } from "../format.js";
import Modal from "./Modal.jsx";

// Carrière de joueur : le match s'arrête sur une action du joueur incarné. Chaque voie
// montre ses chances et ce qu'elle fait à sa note (gagné si elle réussit, perdu sinon).
// Une fois le choix fait, la fenêtre raconte l'action et sa note ; une réussite qui en
// appelle une autre (un deux contre un après un franchissement) enchaîne dans la même
// fenêtre. Un moment sous pression (fin de match serrée, phase finale) pèse plus lourd.
export default function DilemmaDialog({ live, side, busy, error, onChoose, onResume }) {
  const [choice, setChoice] = useState(null); // { option, outcomes, events } : la voie et ce qu'il y avait avant
  const dilemma = live.dilemma;
  const outcomes = dilemmaOutcomes(live);
  const outcome = choice && outcomes.length > choice.outcomes ? outcomes[outcomes.length - 1] : null;
  // Le joueur incarné, ou celui du manager pour qui il tranche.
  const actor = dilemmaActor(live, side, outcome ? outcome.player_id : dilemma?.player_id);
  const me = actor.player;
  const other = side === live.home ? live.away : live.home;

  if (outcome && !busy) {
    const situation = DILEMMAS[outcome.situation];
    const option = situation.options[outcome.option];
    const text = dilemmaText(outcome, live.events.slice(choice.events));
    return (
      <Modal compact className="modal--dialog live-dialog" onClose={onResume}>
        <div>
          <p className="eyebrow">
            {situation.title} · {outcome.minute}'
          </p>
          <h2 className="confirm__title">{option.label}</h2>
        </div>
        <div className={`talk__outcome talk__outcome--${outcome.success ? "lifted" : "backfired"}`}>
          <span className="talk__verdict">{outcome.success ? "Réussi" : "Raté"}</span>
          <p className="confirm__text">{text}</p>
          <span className="muted talk__effect">
            {actor.Note} {signed(outcome.delta)} · {me ? formatNote(me.rating ?? 6) : "–"} / 10 · {side.club.name}{" "}
            {side.score} – {other.score} {other.club.name}
          </span>
        </div>
        <div className="confirm__actions">
          {dilemma ? (
            <button type="button" className="button button--primary" autoFocus onClick={() => setChoice(null)}>
              Continuer l'action
            </button>
          ) : (
            <button type="button" className="button button--primary" autoFocus onClick={onResume}>
              {live.finished ? "Fermer" : "Reprendre le match"}
            </button>
          )}
        </div>
      </Modal>
    );
  }

  if (!dilemma) return null;
  const situation = DILEMMAS[dilemma.situation];
  const choose = (key) => {
    setChoice({ option: key, outcomes: outcomes.length, events: live.events.length });
    onChoose(key);
  };

  return (
    <Modal compact className="modal--dialog live-dialog" onClose={() => {}}>
      <div>
        <p className="eyebrow">
          {actor.call(dilemma.chained)} · {dilemma.minute}'
          {me && ` · ${actor.note} ${formatNote(me.rating ?? 6)}`}
        </p>
        <h2 className="confirm__title">{situation.title}</h2>
      </div>
      {dilemma.pressure > 1 && (
        <p className="dilemma__pressure">
          Moment décisif : {actor.note} gagne ou perd ×{formatNote(dilemma.pressure)}
        </p>
      )}
      <p className="crunch__situation">{situation.text}</p>
      {choice !== null && !error ? (
        <p className="muted">L'action se joue…</p>
      ) : (
        <ul className="talk__options">
          {dilemma.options.map((option) => (
            <li key={option.key}>
              <button type="button" className="talk__option" disabled={busy} onClick={() => choose(option.key)}>
                <span className="talk__name">{situation.options[option.key].label}</span>
                <span className="muted talk__scope">
                  {situation.options[option.key].scope} · note {signed(option.reward)} ou {signed(option.cost)}
                </span>
                <span className="talk__odds">
                  <span className="crunch__chance num">{Math.round(option.success * 100)} %</span>
                  de réussite
                </span>
              </button>
            </li>
          ))}
        </ul>
      )}
      {error && (
        <p className="status--error" style={{ margin: 0 }}>
          {error.message}
        </p>
      )}
    </Modal>
  );
}
