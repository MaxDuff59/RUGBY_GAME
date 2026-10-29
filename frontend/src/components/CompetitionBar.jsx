import { useCallback, useState } from "react";
import { useNavigate } from "react-router-dom";

import { api } from "../api.js";
import { formatLongDate, formatShortDate } from "../format.js";
import { useApi } from "../hooks/useApi.js";
import { leaveSlot } from "../save.js";
import ClubCrest from "./ClubCrest.jsx";
import { ActionError } from "./FullGame.jsx";
import Modal from "./Modal.jsx";

// Les journées enchaînées d'un coup, au plus : de quoi traverser une saison.
const MAX_DAYS = 200;
const DAY_MS = 24 * 3600 * 1000;

// Mode compétition (api/competition.py) : dans l'en-tête de chaque page, où en est
// l'équipe. Un club va droit à son prochain match de Coupe d'Europe (les journées de
// championnat d'ici là se jouent, menées par le staff) ; une sélection a déjà son
// bouton pour aller au prochain rendez-vous (page Sélection). Une fois la partie
// finie : l'issue, et son récap (parcours, quitter ou recommencer), ouvert d'office.
// Rien hors du mode compétition (404).
export default function CompetitionBar({ career }) {
  const navigate = useNavigate();
  const status = useApi(useCallback(api.getCompetition, []));
  const [progress, setProgress] = useState(null); // { origin, reached, target } pendant l'avance
  const [error, setError] = useState(null);
  const [recap, setRecap] = useState(true); // le récap de la partie finie, tant qu'on ne l'a pas fermé
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
        <button type="button" className="button button--small button--primary" onClick={() => setRecap(true)}>
          Bilan
        </button>
        {recap && (
          <Recap
            competition={competition}
            onClose={() => setRecap(false)}
            onLeave={() => {
              leaveSlot();
              navigate("/parties");
            }}
          />
        )}
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

const RESULTS = { won: "V", drawn: "N", lost: "D" };
const ROUNDS = { quarter: "Quart de finale", semi: "Demi-finale", final: "Finale" };

// Le récap d'une compétition finie : l'issue, le bilan, chaque match du parcours. Puis
// quitter, ou recommencer : même compétition, même équipe, dans un monde neuf (la partie
// finie est remplacée).
function Recap({ competition, onClose, onLeave }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const { path, team, champion, name } = competition;
  const won = competition.result === "Vainqueur";
  const count = (result) => path.filter((match) => match.result === result).length;
  const scored = path.reduce((sum, match) => sum + match.score_for, 0);
  const conceded = path.reduce((sum, match) => sum + match.score_against, 0);
  let pool = 0;

  async function restart() {
    setBusy(true);
    setError(null);
    try {
      const fresh = await api.restartCompetition();
      // Tout le jeu se recharge : la partie d'avant n'existe plus. Sans l'équipe (pas
      // qualifiée au nouveau tirage), on la choisit à nouveau.
      window.location.assign(fresh.team ? "/" : "/competition");
    } catch (err) {
      setError(err);
      setBusy(false);
    }
  }

  return (
    <Modal compact className="modal--dialog recap" onClose={busy ? () => {} : onClose}>
      <div className="recap__head">
        <ClubCrest name={team.name} size={48} />
        <div>
          <p className="eyebrow">{name} · terminée</p>
          <h2 className={`confirm__title${won ? " recap__title--won" : ""}`}>
            {won ? `${team.name} remporte la ${name} !` : `${team.name} · ${competition.result}`}
          </h2>
          {!won && champion && <p className="muted recap__sub">Vainqueur : {champion.name}</p>}
        </div>
      </div>

      <dl className="recap__stats">
        <div>
          <dt className="muted">Bilan</dt>
          <dd className="num">
            {count("won")} V · {count("drawn")} N · {count("lost")} D
          </dd>
        </div>
        <div>
          <dt className="muted">Points</dt>
          <dd className="num">
            {scored} – {conceded}
          </dd>
        </div>
      </dl>

      <ol className="recap__path">
        {path.map((match) => {
          if (match.stage === "regular") pool += 1;
          const stage = match.stage === "regular" ? `Poules · J${pool}` : ROUNDS[match.stage];
          return (
            <li key={`${match.date}-${match.opponent.id}`}>
              <span className="muted recap__stage">
                {stage}
                <small>{formatShortDate(match.date)}</small>
              </span>
              <span className="with-crest recap__opponent">
                <ClubCrest name={match.opponent.name} size={20} />
                <span>
                  {match.home || match.neutral ? "" : "à "}
                  {match.opponent.name}
                </span>
              </span>
              <span className="num recap__score">
                {match.score_for} – {match.score_against}
              </span>
              <span className={`pill pill--${RESULTS[match.result]}`}>{RESULTS[match.result]}</span>
            </li>
          );
        })}
      </ol>

      <ActionError error={error} />
      <div className="confirm__actions">
        <span className="muted recap__note">Recommencer remplace cette partie par une nouvelle.</span>
        <button type="button" className="button" disabled={busy} onClick={onLeave}>
          Quitter
        </button>
        <button type="button" className="button button--primary" disabled={busy} onClick={restart}>
          {busy ? "Nouveau tirage…" : "Recommencer"}
        </button>
      </div>
    </Modal>
  );
}
