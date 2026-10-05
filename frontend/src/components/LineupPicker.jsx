import { useState } from "react";

import { POSITION_ORDER, POSITIONS, formatNote } from "../format.js";
import InjuryIcon from "./InjuryIcon.jsx";
import Modal from "./Modal.jsx";

// Fenêtre ouverte en touchant un titulaire sur le terrain : on choisit qui prend
// sa place. Les joueurs du poste d'abord, puis les autres (alignés hors poste), rangés par poste.
// Un autre titulaire choisi échange sa place avec lui ; les blessés ne sont pas proposés.
//
// `entry` : la place touchée { slot, player } ; `jerseys` : Map(id -> numéro) des titulaires.
// `onPick(candidate)` renvoie une promesse : la fenêtre attend, affiche l'erreur
// éventuelle et reste ouverte, ou se ferme quand le changement est enregistré.
export default function LineupPicker({ entry, players, jerseys, onPick, onOpen, onClose }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const { slot, player } = entry;

  const candidates = players
    .filter((p) => p.id !== player.id && p.injury?.status !== "active")
    .sort((a, b) => b.overall - a.overall);
  const groups = [
    { label: "Au poste", players: candidates.filter((p) => p.position === slot.position) },
    {
      label: "Autres postes",
      players: candidates
        .filter((p) => p.position !== slot.position)
        .sort((a, b) => POSITION_ORDER.indexOf(a.position) - POSITION_ORDER.indexOf(b.position)),
    },
  ];

  async function pick(candidate) {
    setBusy(true);
    setError(null);
    try {
      await onPick(candidate);
      onClose();
    } catch (err) {
      setError(err);
      setBusy(false);
    }
  }

  return (
    <Modal compact className="lineup-picker" onClose={busy ? () => {} : onClose}>
      <div className="lineup-picker__head">
        <div>
          <p className="eyebrow">
            N° {slot.number} · {POSITIONS[slot.position].label}
          </p>
          <h2 className="confirm__title">{player.name}</h2>
          <p className="muted lineup-picker__meta">
            {POSITIONS[player.position].label} · {player.age} ans · note {formatNote(player.overall)}
          </p>
        </div>
        <button type="button" className="button button--small" onClick={() => onOpen(player)}>
          Voir sa fiche
        </button>
      </div>

      <p className="muted lineup-picker__hint">
        Qui prend sa place ? Un autre titulaire échange son numéro avec lui.
      </p>
      {error && <p className="status--error lineup-picker__hint">{error.message}</p>}

      <div className="lineup-picker__list">
        {groups.map(
          (group) =>
            group.players.length > 0 && (
              <section key={group.label} className="lineup-picker__group">
                <h3 className="eyebrow">{group.label}</h3>
                {group.players.map((candidate) => {
                  const jersey = jerseys.get(candidate.id);
                  return (
                    <button
                      key={candidate.id}
                      type="button"
                      className="lineup-picker__option"
                      disabled={busy}
                      onClick={() => pick(candidate)}
                    >
                      <span className="lineup-picker__jersey" title={jersey ? `Titulaire, n° ${jersey}` : "Remplaçant"}>
                        {jersey ?? ""}
                      </span>
                      <span className="squad__name">
                        <InjuryIcon injury={candidate.injury} />
                        {candidate.name}
                      </span>
                      <span className="muted">{POSITIONS[candidate.position].label}</span>
                      <span className="muted">{candidate.age} ans</span>
                      <span className="note">{formatNote(candidate.overall)}</span>
                    </button>
                  );
                })}
              </section>
            ),
        )}
      </div>
    </Modal>
  );
}
