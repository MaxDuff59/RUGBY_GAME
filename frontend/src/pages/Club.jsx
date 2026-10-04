import { useCallback, useState } from "react";
import { useOutletContext } from "react-router-dom";

import { api } from "../api.js";
import { formatDiff, formatNote } from "../format.js";
import { useApi } from "../hooks/useApi.js";

const SEASON_YEAR = 2026;

// Les 5 notes collectives calculées par le moteur sur le XV de départ.
const STRENGTH_LINES = [
  { key: "set_piece", label: "Conquête" },
  { key: "pack", label: "Paquet" },
  { key: "attack", label: "Attaque" },
  { key: "defense", label: "Défense" },
  { key: "kicking", label: "Buteur" },
];

export default function Club() {
  const { career } = useOutletContext();
  const loadClub = useCallback(() => api.getClub(career.club_id), [career.club_id]);
  const club = useApi(loadClub);

  if (club.loading) return <p className="status">Chargement…</p>;
  if (club.error) return <p className="status status--error">{club.error.message}</p>;

  return (
    <div className="club-grid">
      <section className="section">
        <div className="section__head">
          <h2 className="eyebrow">Niveau du XV</h2>
          <span className="muted">Notes sur 20</span>
        </div>
        <div className="card card--padded strength">
          {STRENGTH_LINES.map((line) => {
            const value = club.data.strength[line.key];
            return (
              <div key={line.key} className="strength__row">
                <span className="strength__label">{line.label}</span>
                <div className="meter">
                  <div className="meter__fill meter__fill--accent" style={{ width: `${(value / 20) * 100}%` }} />
                </div>
                <span className="strength__value num">{formatNote(value)}</span>
              </div>
            );
          })}
        </div>
      </section>

      <Standings myClubId={career.club_id} />
    </div>
  );
}

// Classement de la saison. Tant que la saison n'a pas été jouée, propose de la
// simuler d'un bloc (le jeu journée par journée arrivera ensuite).
function Standings({ myClubId }) {
  const load = useCallback(() => api.getSeason(SEASON_YEAR), []);
  const season = useApi(load);
  const [simulating, setSimulating] = useState(false);
  const [simulateError, setSimulateError] = useState(null);

  async function simulate() {
    setSimulating(true);
    setSimulateError(null);
    try {
      await api.simulateSeason(SEASON_YEAR);
      season.reload();
    } catch (err) {
      setSimulateError(err);
    } finally {
      setSimulating(false);
    }
  }

  return (
    <section className="section">
      <div className="section__head">
        <h2 className="eyebrow">Classement</h2>
        <span className="muted">Saison {SEASON_YEAR}</span>
      </div>

      {season.loading && <p className="status">Chargement…</p>}

      {season.error?.status === 404 && (
        <div className="card card--padded">
          <p style={{ marginTop: 0 }}>La saison n'a pas encore été jouée.</p>
          <button type="button" className="button button--primary" onClick={simulate} disabled={simulating}>
            {simulating ? "Simulation…" : "Simuler la saison complète"}
          </button>
          {simulateError && <p className="status--error">{simulateError.message}</p>}
        </div>
      )}

      {season.error && season.error.status !== 404 && (
        <p className="status status--error">{season.error.message}</p>
      )}

      {season.data && (
        <div className="card table-wrap">
          <table className="table">
            <thead>
              <tr>
                <th scope="col" className="left">#</th>
                <th scope="col" className="left">Club</th>
                <th scope="col">J</th>
                <th scope="col">G</th>
                <th scope="col">N</th>
                <th scope="col">P</th>
                <th scope="col">Diff</th>
                <th scope="col">Ess</th>
                <th scope="col" title="Bonus offensif">BO</th>
                <th scope="col" title="Bonus défensif">BD</th>
                <th scope="col">Pts</th>
              </tr>
            </thead>
            <tbody>
              {season.data.standings.map((row) => (
                <tr key={row.club_id} className={row.club_id === myClubId ? "table__row--mine" : ""}>
                  <td className="left muted">{row.rank}</td>
                  <td className="left">{row.club_name}</td>
                  <td>{row.played}</td>
                  <td>{row.won}</td>
                  <td>{row.drawn}</td>
                  <td>{row.lost}</td>
                  <td>{formatDiff(row.points_difference)}</td>
                  <td>{row.tries_for}</td>
                  <td>{row.offensive_bonus}</td>
                  <td>{row.defensive_bonus}</td>
                  <td style={{ fontWeight: 600 }}>{row.league_points}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="table__note">
            Diff : différence de points · Ess : essais marqués · BO/BD : bonus offensif/défensif
          </p>
        </div>
      )}
    </section>
  );
}
