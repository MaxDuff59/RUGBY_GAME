import { useCallback, useMemo, useState } from "react";
import { Link } from "react-router-dom";

import { api } from "../api.js";
import ClubCrest from "./ClubCrest.jsx";
import Modal from "./Modal.jsx";
import SortHeader from "./SortHeader.jsx";
import WeatherIcon from "./WeatherIcon.jsx";
import {
  EVENTS,
  MATCH_STATS,
  POSITION_SHORT,
  WEATHER,
  formatLongDate,
  formatNote,
  matchdayLabel,
  scoreNote,
} from "../format.js";
import { useApi } from "../hooks/useApi.js";
import { useSort } from "../hooks/useSort.js";

// Faits de jeu qui comptent dans la fiche : les points et les cartons.
const SHOWN_EVENTS = new Set(["try", "penalty_goal", "drop_goal", "yellow_card", "red_card", "injury"]);

// Fiche d'un match joué : le score et le temps qu'il faisait, puis deux onglets.
// « Le match » : les deux équipes face à face, statistique par statistique, l'homme
// du match et les faits de jeu ; « Les joueurs » : chaque joueur entré en jeu, ses
// minutes, sa note et ce qu'il a fait, une équipe à la fois.
export default function MatchReport({ summary, myClubId, onClose }) {
  const report = useApi(useCallback(() => api.getMatch(summary.id), [summary.id]));
  const [tab, setTab] = useState("match");
  const mine = [summary.home.id, summary.away.id].includes(myClubId) ? myClubId : summary.home.id;
  const [teamId, setTeamId] = useState(mine);
  const data = report.data;
  const weather = data?.weather ?? summary.weather;
  const note = scoreNote(summary, summary.home.id);

  return (
    <Modal onClose={onClose} className="match-report">
      <header className="match-report__head">
        <p className="eyebrow">
          {matchdayLabel(summary)} · {formatLongDate(summary.date)}
          {summary.neutral && " · terrain neutre"}
        </p>
        <button type="button" className="button button--small match-report__close" onClick={onClose}>
          Fermer
        </button>
      </header>
      <div className="match-report__score">
        <TeamName club={summary.home} mine={summary.home.id === myClubId} />
        <span className="match-report__points num">
          {summary.home_score} – {summary.away_score}
          {note && <small className="match__note">{note}</small>}
        </span>
        <TeamName club={summary.away} mine={summary.away.id === myClubId} away />
      </div>
      {weather && (
        <p className="match-report__weather">
          <WeatherIcon weather={weather} size={18} />
          <strong>{WEATHER[weather].label}</strong>
          <span className="muted">{WEATHER[weather].scope}</span>
        </p>
      )}

      {report.loading && <p className="status">Chargement…</p>}
      {report.error && <p className="status status--error">{report.error.message}</p>}
      {data && data.players.length === 0 && (
        <p className="table__note">Ce match a été joué avant que le staff ne relève les statistiques des joueurs.</p>
      )}
      {data && data.players.length > 0 && (
        <>
          <div className="chips" role="group" aria-label="Vue">
            {[
              ["match", "Le match"],
              ["players", "Les joueurs"],
            ].map(([key, label]) => (
              <button key={key} type="button" className="chip" aria-pressed={tab === key} onClick={() => setTab(key)}>
                {label}
              </button>
            ))}
          </div>
          {tab === "match" ? (
            <Overview data={data} summary={summary} myClubId={myClubId} />
          ) : (
            <>
              <div className="chips" role="group" aria-label="Équipe">
                {[summary.home, summary.away].map((club) => (
                  <button key={club.id} type="button" className="chip" aria-pressed={teamId === club.id} onClick={() => setTeamId(club.id)}>
                    <ClubCrest name={club.name} size={18} />
                    {club.name}
                  </button>
                ))}
              </div>
              <PlayerTable players={data.players.filter((p) => p.club_id === teamId)} onLeave={onClose} />
            </>
          )}
        </>
      )}
    </Modal>
  );
}

function TeamName({ club, mine, away = false }) {
  return (
    <span className={`match-report__team${away ? " match-report__team--away" : ""}${mine ? " match-report__team--mine" : ""}`}>
      <ClubCrest name={club.name} size={40} />
      <span>{club.name}</span>
    </span>
  );
}

// Les totaux d'une équipe : ses statistiques, ses essais, ses cartons.
function totals(data, clubId) {
  const players = data.players.filter((p) => p.club_id === clubId);
  const sum = Object.fromEntries(MATCH_STATS.map(({ key }) => [key, players.reduce((t, p) => t + p.stats[key], 0)]));
  const count = (type) => data.events.filter((e) => e.club_id === clubId && e.type === type).length;
  return { ...sum, tries: count("try"), penalties: count("penalty_goal"), cards: count("yellow_card") + count("red_card") };
}

const TEAM_ROWS = [
  { key: "tries", label: "Essais" },
  { key: "penalties", label: "Pénalités réussies" },
  { key: "carries", label: "Ballons portés" },
  { key: "line_breaks", label: "Franchissements" },
  { key: "tackles", label: "Plaquages réussis" },
  { key: "missed_tackles", label: "Plaquages manqués", lowerIsBetter: true },
  { key: "turnovers", label: "Ballons grattés" },
  { key: "lineouts", label: "Touches gagnées" },
  { key: "cards", label: "Cartons", lowerIsBetter: true },
];

function Overview({ data, summary, myClubId }) {
  const home = totals(data, summary.home.id);
  const away = totals(data, summary.away.id);
  // Touches gagnées : celles prises sur son lancer et celles volées à l'adversaire.
  home.lineouts = home.lineouts_won + home.lineout_steals;
  away.lineouts = away.lineouts_won + away.lineout_steals;
  const names = Object.fromEntries(data.players.map((p) => [p.id, p.name]));
  const best = data.players.reduce((top, p) => (top === null || p.stats.rating > top.stats.rating ? p : top), null);
  const events = data.events.filter((e) => SHOWN_EVENTS.has(e.type));
  const club = (clubId) => (clubId === summary.home.id ? summary.home : summary.away);

  return (
    <div className="match-report__overview">
      <section className="match-report__duel" aria-label="Face à face">
        {TEAM_ROWS.map(({ key, label, lowerIsBetter }) => {
          const [h, a] = [home[key], away[key]];
          const total = h + a || 1;
          const leader = h === a ? null : (h > a) !== Boolean(lowerIsBetter) ? "home" : "away";
          return (
            <div key={key} className="duel">
              <span className={`duel__value num${leader === "home" ? " duel__value--lead" : ""}`}>{h}</span>
              <span className="duel__label">{label}</span>
              <span className={`duel__value num${leader === "away" ? " duel__value--lead" : ""}`}>{a}</span>
              <span className="duel__bar" aria-hidden="true">
                <span
                  className={`duel__half duel__half--home${summary.home.id === myClubId ? " duel__half--mine" : ""}`}
                  style={{ width: `${(100 * h) / total}%` }}
                />
                <span
                  className={`duel__half duel__half--away${summary.away.id === myClubId ? " duel__half--mine" : ""}`}
                  style={{ width: `${(100 * a) / total}%` }}
                />
              </span>
            </div>
          );
        })}
      </section>
      <section className="match-report__side">
        {best && (
          <div className="match-report__best">
            <p className="eyebrow">Homme du match</p>
            <p className="match-report__best-name">
              <ClubCrest name={club(best.club_id).name} size={22} />
              <Link to={`/joueurs/${best.id}`}>{best.name ?? "Ancien joueur"}</Link>
              <span className="num match-report__rating">{formatNote(best.stats.rating)}</span>
            </p>
            <p className="muted match-report__best-line">{highlights(best.stats)}</p>
          </div>
        )}
        <p className="eyebrow">Faits de jeu</p>
        <ul className="match-report__events">
          {events.map((event, index) => (
            <li key={index} className={event.club_id === summary.away.id ? "match-report__event--away" : undefined}>
              <span className="num muted">{event.minute}'</span>
              <ClubCrest name={club(event.club_id).name} size={16} />
              <span>
                {EVENTS[event.type]}
                {event.player_id && <span className="muted"> · {names[event.player_id] ?? "—"}</span>}
              </span>
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}

// « 14 plaquages · 2 franchissements » : les deux chiffres les plus parlants d'un joueur.
function highlights(stats) {
  const picks = MATCH_STATS.filter(({ key }) => key !== "missed_tackles" && stats[key] > 0)
    .sort((a, b) => stats[b.key] - stats[a.key])
    .slice(0, 3);
  return picks.map(({ key, label }) => `${stats[key]} ${label.toLowerCase()}`).join(" · ");
}

function PlayerTable({ players, onLeave }) {
  const rows = useMemo(
    () => players.map((p) => ({ ...p, ...p.stats, order: p.number ?? 100 - p.stats.minutes })),
    [players],
  );
  const { rows: sorted, sort, toggle } = useSort(rows, { key: "order", dir: "asc" });
  const header = (key, label, title) => (
    <SortHeader sortKey={key} label={label} title={title} sort={sort} onToggle={toggle} first="desc" />
  );
  return (
    <div className="table-wrap match-report__table">
      <table className="table">
        <thead>
          <tr>
            <SortHeader sortKey="order" label="N°" sort={sort} onToggle={toggle} />
            <SortHeader sortKey="name" label="Joueur" sort={sort} onToggle={toggle} left />
            <th scope="col">Poste</th>
            {header("minutes", "Min", "Minutes jouées")}
            {header("rating", "Note", "Note sur 10")}
            {MATCH_STATS.map(({ key, label, short }) => header(key, short, label))}
          </tr>
        </thead>
        <tbody>
          {sorted.map((p) => (
            <tr key={p.id}>
              <td className="jersey">{p.number ?? "R"}</td>
              <td className="left" style={{ fontWeight: 600 }}>
                {p.name ? (
                  <Link to={`/joueurs/${p.id}`} onClick={onLeave}>
                    {p.name}
                  </Link>
                ) : (
                  <span className="muted">Ancien joueur</span>
                )}
              </td>
              <td className="muted">{p.position ? POSITION_SHORT[p.position] : "–"}</td>
              <td className="num">{p.minutes}</td>
              <td className={`num${p.rating >= 7.5 ? " match-report__high" : ""}`}>{formatNote(p.rating)}</td>
              {MATCH_STATS.map(({ key }) => (
                <td key={key} className={`num${p[key] === 0 ? " muted" : ""}`}>
                  {p[key]}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
