import { useState } from "react";

import { formatDiff, formatLongDate, windowDayLabel } from "../format.js";
import ClubCrest from "./ClubCrest.jsx";
import MatchList from "./MatchList.jsx";

// Une fenêtre internationale dans une carte : son classement (un tournoi) ou ses poules
// (la Coupe du monde), puis ses matchs jour par jour, les plus avancés d'abord quand les
// poules sont finies. Une liste déroulante passe d'une fenêtre de la saison à l'autre.
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

  // Coupe du monde : le tableau final en tête (le dernier tour d'abord), puis les
  // poules et leurs matchs. Ailleurs, les matchs dans l'ordre du calendrier.
  const isKnockout = (date) => shown.matches.some((m) => m.date === date && m.stage !== "regular");
  const knockout = shown.dates.filter(isKnockout).reverse();
  const rounds = shown.dates.filter((date) => !isKnockout(date));

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
        {knockout.map((date) => (
          <Day key={date} window={shown} date={date} myId={myId} />
        ))}
        {shown.standings.length > 0 && <Standings rows={shown.standings} myId={myId} />}
        {shown.pools.map((pool) => (
          <Standings key={pool.name} rows={pool.standings} myId={myId} title={pool.name} qualified={2} />
        ))}
        {rounds.map((date) => (
          <Day key={date} window={shown} date={date} myId={myId} />
        ))}
      </div>
    </section>
  );
}

// Les matchs d'un samedi de la fenêtre (rien tant que les affiches ne sont pas connues).
function Day({ window, date, myId }) {
  const matches = window.matches.filter((match) => match.date === date);
  if (matches.length === 0) return null;
  return (
    <div>
      <div className="matches__stage">
        {windowDayLabel(window, date)} · {formatLongDate(date)}
      </div>
      <MatchList matches={matches} myClubId={myId} reports={false} />
    </div>
  );
}

// `qualified` : nombre de places qualificatives (un filet sous la dernière).
function Standings({ rows, myId, title, qualified }) {
  return (
    <table className="table">
      <thead>
        <tr>
          <th scope="col" className="left">#</th>
          <th scope="col" className="left">{title ?? "Sélection"}</th>
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
        {rows.map((row) => (
          <tr
            key={row.club_id}
            className={[row.club_id === myId ? "table__row--mine" : "", row.rank === qualified ? "table__row--cut" : ""].join(" ")}
          >
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
  );
}
