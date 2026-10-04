import { PITCH_LINES } from "../lineup.js";

// Terrain vu de dessus, attaque vers le haut, avec des marqueurs placés en %.
// marker : { key, x, y, number, label, tone } ; tone : "accent" | "muted" | undefined.
// `compact` : pastilles plus petites (fiche joueur, terrain réduit).
export default function Pitch({ markers, style, onPick, compact = false }) {
  return (
    <div className={`pitch${compact ? " pitch--compact" : ""}`} style={style}>
      {PITCH_LINES.map((line) => (
        <div
          key={line.top}
          className={`pitch__line ${line.solid ? "pitch__line--solid" : "pitch__line--dashed"}`}
          style={{ top: `${line.top}%` }}
        />
      ))}
      {markers.map((marker) => {
        const Tag = onPick ? "button" : "div";
        return (
          <Tag
            key={marker.key}
            type={onPick ? "button" : undefined}
            className={`pitch__player${onPick ? " pitch__player--clickable" : ""}`}
            style={{ left: `${marker.x}%`, top: `${marker.y}%` }}
            onClick={onPick ? () => onPick(marker) : undefined}
            title={marker.title}
          >
            <span className={`pitch__number${marker.tone ? ` pitch__number--${marker.tone}` : ""}`}>
              {marker.number}
            </span>
            {marker.label && <span className="pitch__name">{marker.label}</span>}
          </Tag>
        );
      })}
    </div>
  );
}
