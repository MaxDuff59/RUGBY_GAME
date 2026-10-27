import { useEffect, useState } from "react";

import Modal from "./Modal.jsx";

// Les étapes de l'intersaison (api/routers/seasons.py, `offseason`), dans l'ordre.
const STEPS = [
  "Fin des derniers matchs du monde",
  "Palmarès et montée en Top 14",
  "Fin des prêts et pré-contrats",
  "Joueurs en fin de contrat",
  "Vieillissement et retraites",
  "Arrivée des jeunes du centre",
  "Recrutement des clubs adverses",
  "Tirage du nouveau calendrier",
];

// La requête ne dit pas où elle en est : la barre avance avec le temps, de plus en
// plus lentement, sans dépasser 92 % avant la réponse.
const CEILING = 92;
const PACE_MS = 6000;
// Le temps de voir la barre pleine avant que la fenêtre se ferme.
const LINGER_MS = 500;

// Fenêtre d'attente de l'intersaison : une barre de chargement et l'étape en cours.
// `done` : la nouvelle saison est arrivée, la barre se remplit puis `onFinished`.
export default function Offseason({ year, done, onFinished }) {
  const [start] = useState(() => performance.now());
  const [now, setNow] = useState(start);

  useEffect(() => {
    if (done) return undefined;
    const timer = window.setInterval(() => setNow(performance.now()), 120);
    return () => window.clearInterval(timer);
  }, [done]);

  useEffect(() => {
    if (!done) return undefined;
    const timer = window.setTimeout(onFinished, LINGER_MS);
    return () => window.clearTimeout(timer);
  }, [done, onFinished]);

  const progress = done ? 100 : CEILING * (1 - Math.exp(-(now - start) / PACE_MS));
  const step = done ? STEPS.length - 1 : Math.min(STEPS.length - 1, Math.floor((progress / CEILING) * STEPS.length));

  return (
    <Modal compact className="modal--dialog offseason" onClose={() => {}}>
      <div>
        <p className="eyebrow">Intersaison</p>
        <h2 className="confirm__title">Préparation de la saison {year + 1}</h2>
      </div>
      <div
        className="meter offseason__meter"
        role="progressbar"
        aria-label="Avancement de l'intersaison"
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={Math.round(progress)}
      >
        <div className="meter__fill meter__fill--accent offseason__fill" style={{ width: `${progress}%` }} />
      </div>
      <div className="offseason__status">
        <span>{done ? "Nouvelle saison prête" : `${STEPS[step]}…`}</span>
        <span className="num muted">{Math.round(progress)} %</span>
      </div>
    </Modal>
  );
}
