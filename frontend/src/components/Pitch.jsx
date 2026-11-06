import { PITCH_LINES } from "../lineup.js";

// Terrain vu de dessus, attaque vers le haut, avec des marqueurs placés en %. Le rond
// est centré sur le point, le nom (et la note) pendent dessous.
//
// marker : { key, x, y, number, label, title, tone, note, badges, state, off, extra }
// - tone : "accent" | "muted" | undefined (couleur du rond) ;
// - note : texte sous le nom (la note au poste dans une composition) ;
// - badges : [{ text, title, kind }] collés au rond (capitaine, buteur) ;
// - state : "selected" | "over" | "source" | "target" (composition en cours d'édition) ;
// - off : joué hors de son poste (anneau d'alerte) ;
// - extra : contenu ajouté après le nom (une croix médicale).
// `compact` : pastilles plus petites (fiche joueur, terrain réduit).
// `markerProps(marker)` : propriétés en plus sur chaque marqueur (glisser-déposer).
export default function Pitch({ markers, style, onPick, compact = false, markerProps }) {
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
        const classes = [
          "pitch__player",
          onPick && "pitch__player--clickable",
          marker.state && `pitch__player--${marker.state}`,
        ].filter(Boolean);
        return (
          <Tag
            key={marker.key}
            type={onPick ? "button" : undefined}
            className={classes.join(" ")}
            style={{ left: `${marker.x}%`, top: `${marker.y}%` }}
            onClick={onPick ? () => onPick(marker) : undefined}
            title={marker.title}
            {...markerProps?.(marker)}
          >
            <span
              className={[
                "pitch__number",
                marker.tone && `pitch__number--${marker.tone}`,
                marker.off && "pitch__number--off",
              ]
                .filter(Boolean)
                .join(" ")}
            >
              {marker.number}
              {marker.badges?.map((badge) => (
                <span key={badge.kind} className={`pitch__badge pitch__badge--${badge.kind}`} title={badge.title}>
                  {badge.text}
                </span>
              ))}
            </span>
            {marker.label && (
              <span className="pitch__name">
                {marker.extra}
                <span className="pitch__label">{marker.label}</span>
              </span>
            )}
            {marker.note && (
              <span className={`pitch__note${marker.off ? " pitch__note--off" : ""}`}>{marker.note}</span>
            )}
          </Tag>
        );
      })}
    </div>
  );
}
