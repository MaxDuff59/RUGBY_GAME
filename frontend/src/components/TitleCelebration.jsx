import { useState } from "react";

import ClubCrest from "./ClubCrest.jsx";
import Modal from "./Modal.jsx";

const seasonLabel = (year) => `${year}-${String(year + 1).slice(2)}`;

// Les confettis : leur place, leur retard, leur couleur, tirés une fois pour toutes.
const CONFETTI = Array.from({ length: 28 }, (_, index) => ({
  left: (index * 37) % 100,
  delay: ((index * 53) % 20) / 10,
  duration: 2.6 + ((index * 29) % 14) / 10,
  color: ["var(--accent)", "var(--ink)", "#d4a72c", "#2a5aa8"][index % 4],
  turn: (index * 71) % 360,
}));

// Carrière de joueur : un titre tout juste gagné (championnat, coupe d'Europe, tournoi
// en sélection) se fête dans sa fenêtre, un titre après l'autre. `onDone` à la fin.
export default function TitleCelebration({ titles, onDone }) {
  const [index, setIndex] = useState(0);
  const title = titles[index];
  if (!title) return null;
  const last = index === titles.length - 1;
  const next = () => (last ? onDone() : setIndex(index + 1));

  return (
    <Modal compact className="modal--dialog celebration" onClose={onDone}>
      <div className="celebration__confetti" aria-hidden="true">
        {CONFETTI.map((piece, i) => (
          <span
            key={`${index}-${i}`}
            style={{
              left: `${piece.left}%`,
              background: piece.color,
              animationDelay: `${piece.delay}s`,
              animationDuration: `${piece.duration}s`,
              "--turn": `${piece.turn}deg`,
            }}
          />
        ))}
      </div>
      <div className="celebration__body">
        <span className="celebration__cup" aria-hidden="true">
          🏆
        </span>
        <p className="eyebrow">
          {title.international ? "Titre en sélection" : "Titre"} · saison {seasonLabel(title.year)}
          {titles.length > 1 && ` · ${index + 1} sur ${titles.length}`}
        </p>
        <h2 className="celebration__title">{title.competition}</h2>
        <p className="celebration__club">
          <ClubCrest name={title.club.name} size={40} />
          <span>
            Vainqueur avec <strong>{title.club.name}</strong>
          </span>
        </p>
        <p className="muted">
          {title.international
            ? "Le maillot de ta sélection, et une ligne de plus à ton palmarès."
            : "Le trophée rejoint ton palmarès."}
        </p>
      </div>
      <div className="confirm__actions">
        <button type="button" className="button button--primary" autoFocus onClick={next}>
          {last ? "Savourer" : "Titre suivant"}
        </button>
      </div>
    </Modal>
  );
}
