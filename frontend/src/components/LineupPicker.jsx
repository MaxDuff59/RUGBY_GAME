import { useState } from "react";

import { POSITION_SHORT, POSITIONS, formatNote } from "../format.js";
import { ratingAt, unavailability } from "../lineup.js";
import InjuryIcon from "./InjuryIcon.jsx";
import { Delta } from "./LineupBoard.jsx";
import Modal from "./Modal.jsx";

// Fenêtre ouverte en touchant un titulaire sur le terrain : on choisit qui prend sa
// place. Chaque joueur montre sa note à ce poste (le critère du staff) et l'écart avec
// le titulaire ; « Au poste » d'abord, « Tous les postes » pour aligner hors poste.
// Un autre titulaire choisi échange sa place avec lui ; les indisponibles (blessés,
// suspendus, en sélection) sont listés à la fin, grisés, avec la raison.
//
// `entry` : la place touchée { slot, player } ; `team` : la composition (ClubDetail) ;
// `sheet` : Map(id -> numéro) de la feuille de match (1-15 titulaires, 16-23 remplaçants).
// `onPick(candidate)` renvoie une promesse : la fenêtre attend, affiche l'erreur
// éventuelle et reste ouverte, ou se ferme quand le changement est enregistré.
export default function LineupPicker({ entry, team, players, sheet, onPick, onOpen, onClose }) {
  const { slot, player } = entry;
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const others = players.filter((p) => p.id !== player.id);
  const atPosition = others.filter((p) => p.position === slot.position);
  const [scope, setScope] = useState(atPosition.some((p) => !unavailability(p)) ? "position" : "all");

  const current = ratingAt(team, player, slot.position);
  const rated = (scope === "position" ? atPosition : others)
    .map((p) => ({ player: p, rating: ratingAt(team, p, slot.position), reason: unavailability(p) }))
    .sort((a, b) => b.rating - a.rating);
  const available = rated.filter((row) => !row.reason);
  const unavailable = rated.filter((row) => row.reason);

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
        <span className="lineup-picker__slot" aria-hidden="true">
          {slot.number}
        </span>
        <div className="lineup-picker__who">
          <p className="eyebrow">
            N° {slot.number} · {POSITIONS[slot.position].label}
          </p>
          <h2 className="confirm__title">{player.name}</h2>
          <p className="muted lineup-picker__meta">
            {player.position !== slot.position && (
              <span className="tag tag--off">Hors poste · {POSITIONS[player.position].label}</span>
            )}{" "}
            {player.age} ans · note au poste <strong>{formatNote(current)}</strong>
          </p>
        </div>
        {/* Sans `onOpen` (match libre, hors partie) : pas de fiche à ouvrir. */}
        {onOpen && (
          <button type="button" className="button button--small" onClick={() => onOpen(player)}>
            Sa fiche
          </button>
        )}
      </div>

      <div className="lineup-picker__bar">
        <div className="chips" role="group" aria-label="Joueurs proposés">
          <button
            type="button"
            className="chip chip--small"
            aria-pressed={scope === "position"}
            onClick={() => setScope("position")}
          >
            {POSITIONS[slot.position].label} · {atPosition.length}
          </button>
          <button
            type="button"
            className="chip chip--small"
            aria-pressed={scope === "all"}
            onClick={() => setScope("all")}
          >
            Tous les postes · {others.length}
          </button>
        </div>
        <span className="muted lineup-picker__hint">Un titulaire choisi échange son numéro avec lui.</span>
      </div>
      {error && <p className="status--error lineup-picker__hint">{error.message}</p>}

      <div className="lineup-picker__list" role="list">
        <div className="lineup-picker__columns" aria-hidden="true">
          <span>N°</span>
          <span>Joueur</span>
          <span>Poste</span>
          <span>Âge</span>
          <span className="lineup-picker__right">Au poste</span>
        </div>
        {available.length === 0 && (
          <p className="muted lineup-picker__empty">Personne d'autre de disponible à ce poste.</p>
        )}
        {available.map(({ player: candidate, rating }) => (
          <Option
            key={candidate.id}
            candidate={candidate}
            rating={rating}
            delta={rating - current}
            number={sheet.get(candidate.id)}
            off={candidate.position !== slot.position}
            disabled={busy}
            onPick={() => pick(candidate)}
          />
        ))}
        {unavailable.length > 0 && (
          <>
            <h3 className="eyebrow lineup-picker__group">Indisponibles</h3>
            {unavailable.map(({ player: candidate, rating, reason }) => (
              <Option
                key={candidate.id}
                candidate={candidate}
                rating={rating}
                reason={reason}
                off={candidate.position !== slot.position}
                disabled
              />
            ))}
          </>
        )}
      </div>
    </Modal>
  );
}

function Option({ candidate, rating, delta, number, off, reason, disabled, onPick }) {
  const role = number === undefined ? null : number <= 15 ? "starter" : "bench";
  return (
    <button
      type="button"
      role="listitem"
      className={`lineup-picker__option${reason ? " lineup-picker__option--out" : ""}`}
      disabled={disabled}
      onClick={onPick}
    >
      <span
        className={`lineup-picker__jersey${role ? ` lineup-picker__jersey--${role}` : ""}`}
        title={
          role === "starter"
            ? `Titulaire, n° ${number}`
            : role === "bench"
              ? `Remplaçant, n° ${number}`
              : "Hors de la feuille de match"
        }
      >
        {number ?? ""}
      </span>
      <span className="squad__name lineup-picker__name">
        <InjuryIcon injury={candidate.injury} />
        <span className="lineup-picker__label">{candidate.name}</span>
        {reason && <span className="tag tag--light">{reason}</span>}
      </span>
      <span className={off ? "lineup-picker__pos lineup-picker__pos--off" : "lineup-picker__pos muted"}>
        {POSITION_SHORT[candidate.position]}
      </span>
      <span className="muted lineup-picker__age">{candidate.age}</span>
      <span className="lineup-picker__rating">
        <span className="note">{formatNote(rating)}</span>
        {delta !== undefined && <Delta value={delta} />}
      </span>
    </button>
  );
}
