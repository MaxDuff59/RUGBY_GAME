import { useCallback, useRef } from "react";
import { useNavigate, useOutletContext } from "react-router-dom";

import { api } from "../api.js";
import Pitch from "../components/Pitch.jsx";
import SortHeader from "../components/SortHeader.jsx";
import {
  ATTRIBUTES,
  POSITION_ORDER,
  POSITIONS,
  formatContractEnd,
  formatMoney,
  formatNote,
  formatShortDate,
} from "../format.js";
import { useApi } from "../hooks/useApi.js";
import { usePitchWidth } from "../hooks/usePitchWidth.js";
import { useSort } from "../hooks/useSort.js";
import { buildLineup } from "../lineup.js";

export default function Squad() {
  const { career } = useOutletContext();
  const navigate = useNavigate();
  const load = useCallback(() => api.getClub(career.club_id), [career.club_id]);
  const { data: club, error, loading } = useApi(load);
  // Sans tri choisi (null), l'ordre reste celui du staff : titulaires du 1 au 15, puis les autres.
  const squadSort = useSort(club ? squadRows(club) : [], null);
  const pitchRef = useRef(null);
  const pitchWidth = usePitchWidth(pitchRef, Boolean(club));

  if (loading) return <p className="status">Chargement de l'effectif…</p>;
  if (error) return <p className="status status--error">{error.message}</p>;

  const lineup = buildLineup(club.players, club.strength.lineup_ids);
  const starters = lineup.map(({ player }) => player);
  const average = (values) => values.reduce((sum, v) => sum + v, 0) / values.length;
  const rows = squadSort.sort ? squadSort.rows : sortSquad(squadRows(club));
  const header = (key, label, first = "desc", left = false, title) => (
    <SortHeader sortKey={key} label={label} sort={squadSort.sort} onToggle={squadSort.toggle} first={first} left={left} title={title} />
  );
  const open = (player) => navigate(`/joueurs/${player.id}`);

  return (
    <>
      <header className="squad__head">
        <div className="squad__stats">
          <h1 className="title">Effectif</h1>
          <Stat value={club.players.length} label="joueurs" />
          <Stat value={formatNote(average(starters.map((p) => p.overall)))} label="note moyenne du XV" />
          <Stat value={formatNote(average(starters.map((p) => p.age)))} label="âge moyen du XV" />
        </div>
        <p className="muted">Composition choisie par le staff · clique sur un joueur pour sa fiche</p>
      </header>

      <div className="squad__body fill">
        <figure
          ref={pitchRef}
          className="squad__pitch"
          style={pitchWidth ? { width: pitchWidth, flexBasis: pitchWidth } : undefined}
          aria-label="XV de départ sur le terrain"
        >
          <Pitch
            markers={lineup.map(({ slot, player }) => ({
              key: slot.number,
              x: slot.x,
              y: slot.y,
              number: slot.number,
              label: player.last_name,
              title: `${player.name} · ${POSITIONS[player.position].label}`,
              player,
            }))}
            onPick={(marker) => open(marker.player)}
          />
          <figcaption className="muted">Sens de l'attaque vers le haut. Avants en haut, arrières en bas.</figcaption>
        </figure>

        <div className="card table-wrap squad__table">
          <table className="table">
            <thead>
              <tr>
                {header("jersey", "N°", "asc", true)}
                {header("name", "Joueur", "asc", true)}
                {header("positionRank", "Poste", "asc", true)}
                {header("age", "Âge", "asc")}
                {header("overall", "Note")}
                {header("value", "Valeur")}
                {header("wage", "Salaire")}
                {header("contract_until", "Contrat", "asc", false, "Fin du contrat")}
                {ATTRIBUTES.map((attr) => (
                  <SortHeader
                    key={attr.key}
                    sortKey={attr.key}
                    label={attr.short}
                    title={attr.label}
                    sort={squadSort.sort}
                    onToggle={squadSort.toggle}
                    first="desc"
                  />
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((player) => (
                <tr
                  key={player.id}
                  className={`table__row--clickable${player.jersey === null ? " table__row--bench" : ""}`}
                  tabIndex={0}
                  onClick={() => open(player)}
                  onKeyDown={(event) => {
                    if (event.key === "Enter" || event.key === " ") {
                      event.preventDefault();
                      open(player);
                    }
                  }}
                >
                  <td className="left jersey">{player.jersey ?? ""}</td>
                  <td className="left">
                    <div style={{ fontWeight: 600 }}>{player.name}</div>
                    <InjuryTag injury={player.injury} />
                  </td>
                  <td className="left">{POSITIONS[player.position].label}</td>
                  <td className="muted">{player.age}</td>
                  <td className="note">{formatNote(player.overall)}</td>
                  <td>{formatMoney(player.value)}</td>
                  <td className="muted">{formatMoney(player.wage)}</td>
                  <td className="muted">
                    {player.loaned_from ? `Prêt · ${player.loaned_from_name}` : formatContractEnd(player.contract_until)}
                  </td>
                  {ATTRIBUTES.map((attr) => {
                    const value = player[attr.key];
                    const tone = value >= 15 ? "cell--strong" : value <= 8 ? "cell--weak" : "";
                    return (
                      <td key={attr.key} className={tone}>
                        {value}
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
          <p className="table__note">
            {ATTRIBUTES.map((attr) => `${attr.short} ${attr.label.toLowerCase()}`).join(" · ")}.
            Attributs sur 20 ; en gras à partir de 15. Le numéro indique les titulaires. Salaire par saison,
            contrat jusqu'en juin de l'année indiquée. Les blessés ne sont pas alignés : voir la page Médical.
          </p>
        </div>
      </div>
    </>
  );
}

// Lignes du tableau : le joueur, son numéro de titulaire (null sinon) et le rang de son poste.
function squadRows(club) {
  const jerseys = new Map(
    buildLineup(club.players, club.strength.lineup_ids).map(({ slot, player }) => [player.id, slot.number]),
  );
  return club.players.map((player) => ({
    ...player,
    jersey: jerseys.get(player.id) ?? null,
    positionRank: POSITION_ORDER.indexOf(player.position),
  }));
}

// Titulaires du 1 au 15, puis les remplaçants par poste et note décroissante.
function sortSquad(rows) {
  return [...rows].sort((a, b) => {
    if (a.jersey !== null || b.jersey !== null) {
      if (a.jersey === null) return 1;
      if (b.jersey === null) return -1;
      return a.jersey - b.jersey;
    }
    if (a.positionRank !== b.positionRank) return a.positionRank - b.positionRank;
    return b.overall - a.overall;
  });
}

// « Blessé » jusqu'à la date de retour, « Fragile » pendant la reprise, rien sinon.
function InjuryTag({ injury }) {
  if (!injury) return null;
  if (injury.status === "active") {
    return (
      <div className="muted">
        <span className="tag tag--injured">Blessé</span> retour le {formatShortDate(injury.return_date)}
      </div>
    );
  }
  if (injury.status === "fragile") {
    return (
      <div className="muted">
        <span className="tag tag--fragile">Fragile</span>
      </div>
    );
  }
  return null;
}

function Stat({ value, label }) {
  return (
    <div className="stat">
      <span className="big-num">{value}</span>
      <span className="muted">{label}</span>
    </div>
  );
}
