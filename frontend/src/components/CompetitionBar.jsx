import { useCallback, useState } from "react";
import { useNavigate } from "react-router-dom";

import { api } from "../api.js";
import { formatLongDate } from "../format.js";
import { useApi } from "../hooks/useApi.js";
import { leaveSlot } from "../save.js";
import { ActionError } from "./FullGame.jsx";
import Modal from "./Modal.jsx";

// Les journées enchaînées d'un coup, au plus : de quoi traverser une saison.
const MAX_DAYS = 200;
const DAY_MS = 24 * 3600 * 1000;

// Mode compétition (api/competition.py) : dans l'en-tête de chaque page, où en est
// l'équipe. Un club va droit à son prochain match de Coupe d'Europe (les journées de
// championnat d'ici là se jouent, menées par le staff) ; une sélection a déjà son
// bouton pour aller au prochain rendez-vous (page Sélection). Une fois la partie
// finie : l'issue, et le retour aux parties. Rien hors du mode compétition (404).
export default function CompetitionBar({ career }) {
  const navigate = useNavigate();
  const status = useApi(useCallback(api.getCompetition, []));
  const [progress, setProgress] = useState(null); // { origin, reached, target } pendant l'avance
  const [error, setError] = useState(null);
  const competition = status.data;
  if (!competition || !competition.team) return null;

  const target = competition.next_date;

  // Joue les journées une par une jusqu'au prochain match de coupe, en montrant la date
  // atteinte ; puis recharge la page, qui s'ouvre sur ce match.
  async function skipAhead() {
    setError(null);
    setProgress({ origin: null, reached: null, target });
    try {
      for (let day = 0; day < MAX_DAYS; day += 1) {
        const result = await api.playMatchday();
        const date = result.played.date;
        setProgress((now) => ({ ...now, origin: now.origin ?? date, reached: date }));
        if (!result.season.next_match || result.season.next_match.cup) break;
      }
      window.location.reload();
    } catch (err) {
      setError(err);
      setProgress(null);
    }
  }

  if (competition.over) {
    const won = competition.result === "Vainqueur";
    return (
      <div className={`competition-bar${won ? " competition-bar--won" : ""}`}>
        <div className="competition-bar__text">
          <span className="eyebrow">{competition.name} · terminée</span>
          <strong>
            {won
              ? `${competition.team.name} remporte la ${competition.name} !`
              : `${competition.team.name} · ${competition.result}`}
          </strong>
          {!won && competition.champion && (
            <span className="muted competition-bar__more">Vainqueur : {competition.champion.name}</span>
          )}
        </div>
        <button
          type="button"
          className="button button--small button--primary"
          onClick={() => {
            leaveSlot();
            navigate("/parties");
          }}
        >
          Retour aux parties
        </button>
      </div>
    );
  }

  return (
    <div className="competition-bar">
      <div className="competition-bar__text">
        <span className="eyebrow">{competition.name}</span>
        <strong>{target ? `Prochain match le ${formatLongDate(target)}` : "En attente du tour suivant"}</strong>
      </div>
      {career.kind !== "nation" && !competition.ready && (
        <button
          type="button"
          className="button button--small button--primary"
          disabled={progress !== null}
          onClick={skipAhead}
        >
          Aller au match de coupe
        </button>
      )}
      <ActionError error={error} />
      {progress && <SkipDialog name={competition.name} progress={progress} />}
    </div>
  );
}

// L'attente pendant que les journées se jouent : la date atteinte, et la barre jusqu'au match.
function SkipDialog({ name, progress }) {
  const { origin, reached, target } = progress;
  let percent = 0;
  if (origin && reached && target) {
    const span = new Date(target) - new Date(origin);
    percent = span > 0 ? Math.min(100, (100 * (new Date(reached) - new Date(origin) + DAY_MS)) / (span + DAY_MS)) : 100;
  }
  return (
    <Modal compact className="modal--dialog offseason" onClose={() => {}}>
      <div>
        <p className="eyebrow">{name}</p>
        <h2 className="confirm__title">Vers le match de coupe</h2>
      </div>
      <div
        className="meter offseason__meter"
        role="progressbar"
        aria-label="Avancement"
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={Math.round(percent)}
      >
        <div className="meter__fill meter__fill--accent offseason__fill" style={{ width: `${percent}%` }} />
      </div>
      <div className="offseason__status">
        <span>{reached ? `Journée du ${formatLongDate(reached)} jouée…` : "Les journées de championnat se jouent…"}</span>
        {target && <span className="num muted">{formatLongDate(target)}</span>}
      </div>
    </Modal>
  );
}
