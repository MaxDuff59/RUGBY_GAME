import { formatNote, matchdayLabel } from "../format.js";

// Les notes de vie du club, du haut vers le bas de la carte. `levels` : paliers de la
// note la plus haute à la plus basse ; `neutral` : note de départ, en pointillé.
export const NOTE_LINES = [
  {
    key: "morale",
    label: "Moral",
    neutral: 12,
    levels: ["Euphorique", "Confiant", "Serein", "Inquiet", "Au plus bas"],
  },
  {
    key: "cohesion",
    label: "Cohésion",
    neutral: 10,
    levels: ["Soudé", "Uni", "En rodage", "Décousu", "Éclaté"],
  },
  {
    key: "freshness",
    label: "Fraîcheur",
    before: true, // mesurée avant chaque match
    levels: ["Frais", "En jambes", "Entamé", "Fatigué", "Épuisé"],
  },
  {
    key: "board",
    label: "Direction",
    neutral: 12,
    levels: ["Ravie", "Confiante", "Patiente", "Sceptique", "Excédée"],
  },
  {
    key: "supporters",
    label: "Supporters",
    neutral: 10,
    levels: ["Enflammés", "Enthousiastes", "Fidèles", "Déçus", "Hostiles"],
  },
];
export const LEVEL_FLOORS = [16, 13.5, 10.5, 7.5, 0];

// 1.3 -> "+1,3", -0.8 -> "−0,8"
export const formatChange = (value) => `${value > 0 ? "+" : value < 0 ? "−" : ""}${formatNote(Math.abs(value))}`;

// Palier d'une note (« Soudé », « Inquiet »…).
export const levelOf = (line, value) => line.levels[LEVEL_FLOORS.findIndex((floor) => value >= floor)];

// Note avant le premier match de la saison.
export const startValue = (note) => (note.history.length > 0 ? note.history[0].value - note.history[0].change : note.value);

export function NoteLine({ line, note, warning }) {
  const level = levelOf(line, note.value);
  const history = note.history;
  return (
    <div className="club-note">
      <div className="club-note__name">
        <span className="club-note__label">{line.label}</span>
        <span className={warning ? "club-note__warning" : "muted"} title={warning ?? undefined}>
          {warning ? "Poste menacé" : level}
        </span>
      </div>
      <div className="club-note__chart" role="img" aria-label={`${line.label} après chacun des ${history.length} matchs joués`}>
        {line.neutral && <div className="club-note__neutral" style={{ bottom: `${(line.neutral / 20) * 100}%` }} />}
        {history.map((step, index) => (
          <div
            key={`${step.stage}-${step.matchday}`}
            className="club-note__col"
            title={`${matchdayLabel(step)} · ${step.result} ${step.scored}-${step.conceded} contre ${step.opponent.name} · ${line.label.toLowerCase()}${line.before ? " avant le match" : ""} ${formatNote(step.value)} (${formatChange(step.change)})`}
          >
            <div
              className={`club-note__bar ${index === history.length - 1 ? "club-note__bar--current" : ""}`}
              style={{ height: `${(step.value / 20) * 100}%` }}
            />
          </div>
        ))}
      </div>
      <span className="club-note__value num">{formatNote(note.value)}</span>
    </div>
  );
}
