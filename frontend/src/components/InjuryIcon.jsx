import { useState } from "react";
import { createPortal } from "react-dom";

import { INJURY_SOURCES, PROTOCOLS, SEVERITIES, formatPercent, formatShortDate, formatWeeks } from "../format.js";

const CARD_WIDTH = 260;
const GAP = 6;

// Croix médicale devant le nom : rouge tant qu'il est blessé, grise pendant la reprise.
// Au survol, une fiche détaille la blessure. Elle est rendue dans <body> en position fixe
// pour ne pas être coupée par le tableau qui défile.
export default function InjuryIcon({ injury }) {
  const [anchor, setAnchor] = useState(null);
  if (!injury || (injury.status !== "active" && injury.status !== "fragile")) return null;
  const injured = injury.status === "active";
  const label = injured ? `Blessé, retour le ${formatShortDate(injury.return_date)}` : "Fragile";

  return (
    <>
      <svg
        className={`medical-icon medical-icon--${injured ? "injured" : "fragile"}`}
        viewBox="0 0 16 16"
        role="img"
        aria-label={label}
        onMouseEnter={(event) => setAnchor(event.currentTarget.getBoundingClientRect())}
        onMouseLeave={() => setAnchor(null)}
      >
        <rect width="16" height="16" rx="3.5" fill="currentColor" />
        <path d="M6.5 3.5h3v3h3v3h-3v3h-3v-3h-3v-3h3z" fill="#fff" />
      </svg>
      {anchor && createPortal(<InjuryCard injury={injury} anchor={anchor} />, document.body)}
    </>
  );
}

// Sous la croix, ou au-dessus quand on est trop près du bas de la fenêtre.
function InjuryCard({ injury, anchor }) {
  const injured = injury.status === "active";
  const left = Math.max(8, Math.min(anchor.left, window.innerWidth - CARD_WIDTH - 8));
  const below = anchor.bottom + 180 < window.innerHeight;
  const style = below
    ? { left, top: anchor.bottom + GAP, width: CARD_WIDTH }
    : { left, bottom: window.innerHeight - anchor.top + GAP, width: CARD_WIDTH };

  return (
    <div className="injury-card" style={style} role="tooltip">
      <div className="injury-card__tags">
        <span className={`tag ${injured ? "tag--injured" : "tag--fragile"}`}>{injured ? "Blessé" : "Fragile"}</span>
        <span className={`tag tag--${injury.severity}`}>{SEVERITIES[injury.severity].label}</span>
        {injury.relapse && <span className="tag tag--light">Rechute</span>}
      </div>
      <div className="injury-card__kind">{injury.kind}</div>
      <div className="muted">
        {capitalize(INJURY_SOURCES[injury.source])} le {formatShortDate(injury.occurred_on)}
      </div>
      {injured ? (
        <>
          <div>
            Retour le <strong>{formatShortDate(injury.return_date)}</strong> ({formatWeeks(injury.weeks_left)}
            {injury.weeks_left !== injury.weeks_total ? ` sur ${injury.weeks_total}` : ""})
          </div>
          <div className="muted">
            {injury.protocol_chosen ? `Protocole ${PROTOCOLS[injury.protocol].label.toLowerCase()}` : "Protocole à choisir"}
            {" · "}puis fragile jusqu'au {formatShortDate(injury.fragile_until)}
          </div>
        </>
      ) : (
        <>
          <div>
            Revenu le {formatShortDate(injury.return_date)}, fragile jusqu'au{" "}
            <strong>{formatShortDate(injury.fragile_until)}</strong>
          </div>
          <div className="muted">Rechute {formatPercent(injury.relapse_risk)} par match joué</div>
        </>
      )}
    </div>
  );
}

const capitalize = (text) => text.charAt(0).toUpperCase() + text.slice(1);
