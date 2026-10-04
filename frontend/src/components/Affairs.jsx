import { useState } from "react";

import { api } from "../api.js";
import { formatLongDate, formatNote, formatSignedMoney } from "../format.js";
import Modal from "./Modal.jsx";

// Notes de vie du club, dans l'ordre de la carte « Vie du club ».
const NOTE_LABELS = {
  morale: "Moral",
  cohesion: "Cohésion",
  freshness: "Fraîcheur",
  board: "Direction",
  supporters: "Supporters",
};

// 1.3 -> "+1,3", -0.8 -> "−0,8"
const formatChange = (value) => `${value > 0 ? "+" : "−"}${formatNote(Math.abs(value))}`;

// Affaires entre deux matchs : une à la fois. On choisit une réponse, puis on
// découvre la réaction et ses effets (cachés jusque-là). `onAnswered` reçoit
// l'affaire réglée ; la fenêtre se ferme quand il n'en reste plus.
export default function Affairs({ affairs, onAnswered, onClose }) {
  const [answered, setAnswered] = useState(null); // l'affaire qu'on vient de régler
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);

  const affair = answered ?? affairs[0];
  if (!affair) return null;
  const remaining = affairs.length - (answered ? 1 : 0);

  async function choose(choice) {
    setBusy(true);
    setError(null);
    try {
      setAnswered(await api.answerAffair(affair.id, choice));
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }

  function next() {
    const done = answered;
    setAnswered(null);
    onAnswered(done);
  }

  return (
    <Modal compact onClose={answered ? next : onClose}>
      <div>
        <p className="eyebrow">
          {affair.category_label} · {formatLongDate(affair.date)}
        </p>
        <h2 className="affair__title">{affair.title}</h2>
      </div>
      <p className="affair__text">{affair.text}</p>

      {answered ? (
        <>
          <div className="affair__answer">
            <span className="muted">{answered.choice_label ?? "Sans réponse"}</span>
            <p>{answered.outcome}</p>
          </div>
          <Effects affair={answered} />
          <div className="affair__actions">
            <button type="button" className="button button--primary" onClick={next}>
              {remaining > 0 ? `Affaire suivante (${remaining})` : "Continuer"}
            </button>
          </div>
        </>
      ) : (
        <>
          <ul className="affair__options">
            {affair.options.map((option) => (
              <li key={option.key}>
                <button type="button" className="affair__option" disabled={busy} onClick={() => choose(option.key)}>
                  {option.label}
                </button>
              </li>
            ))}
          </ul>
          {error && <p className="status--error">{error.message}</p>}
          <div className="affair__actions">
            <span className="muted">Sans réponse avant le prochain match, on tranchera pour toi.</span>
            <button type="button" className="button button--small" onClick={onClose}>
              Plus tard
            </button>
          </div>
        </>
      )}
    </Modal>
  );
}

// Ce que la réponse a changé : notes sur 20, argent, promesse en cours.
function Effects({ affair }) {
  const notes = Object.keys(NOTE_LABELS).filter((key) => affair.effects[key]);
  if (notes.length === 0 && !affair.money && !affair.promise) {
    return <p className="muted affair__effects">Aucun effet.</p>;
  }
  return (
    <ul className="affair__effects">
      {notes.map((key) => (
        <li key={key} className={affair.effects[key] > 0 ? "affair__effect--up" : "affair__effect--down"}>
          <span>{NOTE_LABELS[key]}</span>
          <span className="num">{formatChange(affair.effects[key])}</span>
        </li>
      ))}
      {affair.money !== 0 && (
        <li className={affair.money > 0 ? "affair__effect--up" : "affair__effect--down"}>
          <span>Trésorerie</span>
          <span className="num">{formatSignedMoney(affair.money)}</span>
        </li>
      )}
      {affair.promise && (
        <li>
          <span>Promesse</span>
          <span>{affair.promise === "start" ? "titulaire au prochain match" : "victoire au prochain match"}</span>
        </li>
      )}
    </ul>
  );
}
