import { useState } from "react";

import { formatDiff, formatLongDate, testLabel } from "../format.js";
import ClubCrest from "./ClubCrest.jsx";
import MatchList from "./MatchList.jsx";

// Une fenêtre internationale dans une carte : son classement (tournoi), puis ses matchs
// jour par jour. Une liste déroulante passe d'une fenêtre de la saison à l'autre.
// `initial` : code de la fenêtre montrée d'abord (sinon la première pas encore finie).
// `myId` : la sélection du joueur, mise en avant (aucune dans une carrière de club).
export default function WindowBoard({ windows, initial, myId = null }) {
  const [code, setCode] = useState(null);
  const fallback = windows.find((w) => !w.finished) ?? windows.at(-1);
  const shown = windows.find((w) => w.code === (code ?? initial)) ?? fallback;

  if (!shown) {
    return (
      <section className="section">
        <div className="section__head">
          <h2 className="eyebrow">Matchs internationaux</h2>
        </div>
        <p className="muted">Aucune fenêtre internationale cette saison.</p>
      </section>
    );
  }

  return (
    <section className="section">
      <div className="section__head">
        <h2 className="eyebrow">
          {shown.name}
          {shown.champion ? ` · vainqueur : ${shown.champion.name}` : ""}
        </h2>
        {windows.length > 1 && (
          <select
            className="input tactics__select"
            aria-label="Fenêtre internationale"
            value={shown.code}
            onChange={(event) => setCode(event.target.value)}
          >
            {windows.map((w) => (
              <option key={w.code} value={w.code}>
                {w.short_name}
              </option>
            ))}
          </select>
        )}
      </div>
      <div className="card table-wrap">
        {shown.has_table && (
          <table className="table">
            <thead>
              <tr>
                <th scope="col" className="left">#</th>
                <th scope="col" className="left">Sélection</th>
                <th scope="col" title="Joués">J</th>
                <th scope="col" title="Gagnés">G</th>
                <th scope="col" title="Nuls">N</th>
                <th scope="col" title="Perdus">P</th>
                <th scope="col" title="Différence de points">Diff</th>
                <th scope="col" title="Bonus offensifs et défensifs">Bon.</th>
                <th scope="col">Pts</th>
              </tr>
            </thead>
            <tbody>
              {shown.standings.map((row) => (
                <tr key={row.club_id} className={row.club_id === myId ? "table__row--mine" : ""}>
                  <td className="left muted">{row.rank}</td>
                  <td className="left">
                    <span className="with-crest">
                      <ClubCrest name={row.club_name} size={20} />
                      {row.club_name}
                    </span>
                  </td>
                  <td>{row.played}</td>
                  <td>{row.won}</td>
                  <td>{row.drawn}</td>
                  <td>{row.lost}</td>
                  <td>{formatDiff(row.points_difference)}</td>
                  <td>{row.offensive_bonus + row.defensive_bonus}</td>
                  <td style={{ fontWeight: 600 }}>{row.league_points}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        {shown.dates.map((date) => {
          const matches = shown.matches.filter((match) => match.date === date);
          return (
            <div key={date}>
              <div className="matches__stage">
                {testLabel(shown, matches[0])} · {formatLongDate(date)}
              </div>
              <MatchList matches={matches} myClubId={myId} />
            </div>
          );
        })}
      </div>
    </section>
  );
}
