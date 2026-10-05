import { matchResult } from "../format.js";

// Les derniers résultats d'un club, en pastilles V / N / D (plein, gris, contour).
export default function FormPills({ results }) {
  if (results.length === 0) return <span className="muted">Aucun match joué</span>;
  return (
    <span className="form">
      {results.map((result, index) => (
        <span key={index} className={`pill pill--${result}`} aria-label={LABELS[result]}>
          {result}
        </span>
      ))}
    </span>
  );
}

const LABELS = { V: "Victoire", N: "Nul", D: "Défaite" };

// Résultats (V/N/D) des `count` derniers matchs joués par un club, du plus
// ancien au plus récent.
export function recentForm(matches, clubId, count = 5) {
  return matches
    .filter((m) => m.home_score !== null && (m.home.id === clubId || m.away.id === clubId))
    .slice(-count)
    .map((m) => matchResult(m, clubId));
}
