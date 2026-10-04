import { useCallback } from "react";
import { useOutletContext } from "react-router-dom";

import { api } from "../api.js";
import { ATTRIBUTES, POSITION_ORDER, POSITIONS, formatMoney, formatNote } from "../format.js";
import { useApi } from "../hooks/useApi.js";

// Places du XV sur le terrain : numéro, poste, position en % (attaque vers le haut).
const SLOTS = [
  { number: 1, position: "PROP", x: 28, y: 12 },
  { number: 2, position: "HOOKER", x: 50, y: 12 },
  { number: 3, position: "PROP", x: 72, y: 12 },
  { number: 4, position: "LOCK", x: 39, y: 23 },
  { number: 5, position: "LOCK", x: 61, y: 23 },
  { number: 6, position: "BACK_ROW", x: 20, y: 33 },
  { number: 8, position: "BACK_ROW", x: 50, y: 36 },
  { number: 7, position: "BACK_ROW", x: 80, y: 33 },
  { number: 9, position: "SCRUM_HALF", x: 42, y: 50 },
  { number: 10, position: "FLY_HALF", x: 30, y: 60 },
  { number: 12, position: "CENTRE", x: 44, y: 70 },
  { number: 13, position: "CENTRE", x: 62, y: 78 },
  { number: 11, position: "WING", x: 12, y: 76 },
  { number: 14, position: "WING", x: 88, y: 76 },
  { number: 15, position: "FULLBACK", x: 50, y: 89 },
];

// Lignes du terrain : en-but, 22 m, milieu, 22 m, en-but (en % de la hauteur).
const PITCH_LINES = [
  { top: 6, solid: true },
  { top: 28, solid: false },
  { top: 50, solid: true },
  { top: 72, solid: false },
  { top: 94, solid: true },
];

// Associe à chaque place du terrain un titulaire de ce poste. Si l'effectif est
// incomplet, le moteur a complété avec d'autres joueurs : on les met où il reste
// de la place.
function buildLineup(players, lineupIds) {
  const remaining = lineupIds.map((id) => players.find((p) => p.id === id));
  const lineup = SLOTS.map((slot) => {
    const index = remaining.findIndex((p) => p.position === slot.position);
    return { slot, player: index === -1 ? null : remaining.splice(index, 1)[0] };
  });
  for (const entry of lineup) {
    if (!entry.player && remaining.length) entry.player = remaining.shift();
  }
  return lineup.filter((entry) => entry.player);
}

export default function Squad() {
  const { career } = useOutletContext();
  const load = useCallback(() => api.getClub(career.club_id), [career.club_id]);
  const { data: club, error, loading } = useApi(load);

  if (loading) return <p className="status">Chargement de l'effectif…</p>;
  if (error) return <p className="status status--error">{error.message}</p>;

  const lineup = buildLineup(club.players, club.strength.lineup_ids);
  const jerseyByPlayer = new Map(lineup.map(({ slot, player }) => [player.id, slot.number]));
  const starters = lineup.map(({ player }) => player);

  const average = (values) => values.reduce((sum, v) => sum + v, 0) / values.length;
  const sortedPlayers = sortSquad(club.players, jerseyByPlayer);

  return (
    <>
      <header className="squad__head">
        <div className="squad__stats">
          <h1 className="title">Effectif</h1>
          <Stat value={club.players.length} label="joueurs" />
          <Stat value={formatNote(average(starters.map((p) => p.overall)))} label="note moyenne du XV" />
          <Stat value={formatNote(average(starters.map((p) => p.age)))} label="âge moyen du XV" />
        </div>
        <p className="muted">Composition choisie par le staff</p>
      </header>

      <div className="squad__body">
        <figure className="squad__pitch" aria-label="XV de départ sur le terrain">
          <div className="pitch">
            {PITCH_LINES.map((line) => (
              <div
                key={line.top}
                className={`pitch__line ${line.solid ? "pitch__line--solid" : "pitch__line--dashed"}`}
                style={{ top: `${line.top}%` }}
              />
            ))}
            {lineup.map(({ slot, player }) => (
              <div
                key={slot.number}
                className="pitch__player"
                style={{ left: `${slot.x}%`, top: `${slot.y}%` }}
              >
                <span className="pitch__number">{slot.number}</span>
                <span className="pitch__name">{player.last_name}</span>
              </div>
            ))}
          </div>
          <figcaption className="muted">
            Sens de l'attaque vers le haut. Avants en haut, arrières en bas.
          </figcaption>
        </figure>

        <div className="card table-wrap squad__table">
          <table className="table">
            <thead>
              <tr>
                <th scope="col" className="left">N°</th>
                <th scope="col" className="left">Joueur</th>
                <th scope="col">Âge</th>
                <th scope="col">Note</th>
                <th scope="col">Valeur</th>
                <th scope="col">Salaire</th>
                {ATTRIBUTES.map((attr) => (
                  <th key={attr.key} scope="col" title={attr.label}>
                    {attr.short}
                  </th>
                ))}
              </tr>
            </thead>
            {[
              { title: "Avants", forward: true },
              { title: "Arrières", forward: false },
            ].map((group) => (
              <tbody key={group.title}>
                <tr>
                  <th scope="rowgroup" colSpan={6 + ATTRIBUTES.length} className="table__group">
                    {group.title}
                  </th>
                </tr>
                {sortedPlayers
                  .filter((p) => POSITIONS[p.position].forward === group.forward)
                  .map((player) => (
                    <tr key={player.id}>
                      <td className="left jersey">{jerseyByPlayer.get(player.id) ?? ""}</td>
                      <td className="left">
                        <div style={{ fontWeight: 600 }}>{player.name}</div>
                        <div className="muted">{POSITIONS[player.position].label}</div>
                      </td>
                      <td className="muted">{player.age}</td>
                      <td className="note">{formatNote(player.overall)}</td>
                      <td>{formatMoney(player.value)}</td>
                      <td className="muted">{formatMoney(player.wage)}</td>
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
            ))}
          </table>
          <p className="table__note">
            {ATTRIBUTES.map((attr) => `${attr.short} ${attr.label.toLowerCase()}`).join(" · ")}.
            Attributs sur 20 ; en gras à partir de 15. Le numéro indique les titulaires. Salaire par saison.
          </p>
        </div>
      </div>
    </>
  );
}

function Stat({ value, label }) {
  return (
    <div className="stat">
      <span className="big-num">{value}</span>
      <span className="muted">{label}</span>
    </div>
  );
}

// Par poste (du 1 au 15), titulaires d'abord, puis par note décroissante.
function sortSquad(players, jerseyByPlayer) {
  return [...players].sort((a, b) => {
    const byPosition = POSITION_ORDER.indexOf(a.position) - POSITION_ORDER.indexOf(b.position);
    if (byPosition !== 0) return byPosition;
    const aStarts = jerseyByPlayer.has(a.id) ? 0 : 1;
    const bStarts = jerseyByPlayer.has(b.id) ? 0 : 1;
    if (aStarts !== bStarts) return aStarts - bStarts;
    return b.overall - a.overall;
  });
}
