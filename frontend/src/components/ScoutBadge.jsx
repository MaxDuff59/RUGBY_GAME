import { useState } from "react";

import { api } from "../api.js";
import { formatShortDate } from "../format.js";

// Ce que le club sait d'un joueur d'un autre club (api/scouting.py) : « Estimation »
// et « Superviser » (le rapport arrive au soir de la journée suivante), « Rapport
// attendu », ou « Supervisé ». Rien pour nos joueurs. `onScouted` reçoit la fiche à jour.
export default function ScoutBadge({ player, onScouted }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);

  async function scout() {
    setBusy(true);
    setError(null);
    try {
      onScouted?.(await api.scoutPlayer(player.id));
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }

  switch (player.scouting) {
    case "estimate":
      return (
        <span className="scout">
          <span className="tag tag--light" title="Attributs estimés à deux points près : aucun recruteur ne l'a supervisé">
            Estimation
          </span>
          <button type="button" className="link-button" disabled={busy} onClick={scout}>
            Superviser · 15 k€
          </button>
          {error && <span className="status--error">{error.message}</span>}
        </span>
      );
    case "pending":
      return (
        <span className="tag tag--light" title="Le rapport arrive au soir de la prochaine journée">
          Rapport attendu · demandé le {formatShortDate(player.report_on)}
        </span>
      );
    case "report":
      return <span className="tag tag--healed">Supervisé</span>;
    default:
      return null;
  }
}
