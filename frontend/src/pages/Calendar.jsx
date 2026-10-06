import { useCallback, useMemo, useState } from "react";
import { useOutletContext } from "react-router-dom";

import { api } from "../api.js";
import ClubCrest from "../components/ClubCrest.jsx";
import MatchList from "../components/MatchList.jsx";
import {
  STAGES,
  addDays,
  formatLongDate,
  formatMonthYear,
  formatShortDate,
  matchResult,
  matchdayLabel,
  scoreNote,
  parseDate,
  startOfWeek,
  toIso,
} from "../format.js";
import { useApi } from "../hooks/useApi.js";

const VIEWS = [
  { key: "week", label: "Semaine" },
  { key: "month", label: "Mois" },
  { key: "season", label: "Saison" },
];

const WEEKDAYS = ["Lun", "Mar", "Mer", "Jeu", "Ven", "Sam", "Dim"];

// Calendrier de la saison : par semaine, par mois ou en entier.
export default function Calendar() {
  const { career } = useOutletContext();
  const myId = career.club_id;
  const season = useApi(useCallback(api.getCurrentSeason, []));
  const [view, setView] = useState("week");
  // Date « curseur » : null tant que la saison n'est pas chargée (on se place
  // alors sur la prochaine journée).
  const [cursor, setCursor] = useState(null);

  const matchdays = useMemo(() => groupByMatchday(season.data?.matches ?? []), [season.data]);

  if (season.loading) return <p className="status">Chargement…</p>;
  if (season.error) return <p className="status status--error">{season.error.message}</p>;

  const data = season.data;
  const todayIso = data.next_matchday?.date ?? data.matches[data.matches.length - 1].date;
  const current = cursor ?? parseDate(todayIso);

  const shift = (days, months = 0) => {
    const next = new Date(current);
    next.setMonth(next.getMonth() + months);
    setCursor(addDays(next, days));
  };

  return (
    <>
      <header className="page-head">
        <div>
          <h1 className="title">Calendrier</h1>
          <p className="muted" style={{ margin: "8px 0 0" }}>
            {data.league.name} {data.year} · {data.regular_matchdays} journées, puis{" "}
            {data.league.playoff_stages.map((stage) => STAGES[stage].toLowerCase()).join(", ")}.
          </p>
        </div>
        <div className="chips" role="group" aria-label="Vue">
          {VIEWS.map((v) => (
            <button key={v.key} type="button" className="chip" aria-pressed={view === v.key} onClick={() => setView(v.key)}>
              {v.label}
            </button>
          ))}
        </div>
      </header>

      {view !== "season" && (
        <div className="calendar-nav">
          <button type="button" className="button button--small" onClick={() => (view === "week" ? shift(-7) : shift(0, -1))}>
            ← {view === "week" ? "Semaine précédente" : "Mois précédent"}
          </button>
          <span className="calendar-nav__title">
            {view === "week" ? weekTitle(current) : capitalize(formatMonthYear(current))}
          </span>
          <button type="button" className="button button--small" onClick={() => setCursor(parseDate(todayIso))}>
            Prochaine journée
          </button>
          <button type="button" className="button button--small" onClick={() => (view === "week" ? shift(7) : shift(0, 1))}>
            {view === "week" ? "Semaine suivante" : "Mois suivant"} →
          </button>
        </div>
      )}

      {view === "week" && <WeekView current={current} matchdays={matchdays} myId={myId} />}
      {view === "month" && <MonthView current={current} matchdays={matchdays} myId={myId} onPick={(date) => { setCursor(date); setView("week"); }} />}
      {view === "season" && <SeasonView matchdays={matchdays} myId={myId} />}
    </>
  );
}

// --- Semaine ----------------------------------------------------------------------

function WeekView({ current, matchdays, myId }) {
  const monday = startOfWeek(current);
  const sunday = addDays(monday, 6);
  const inWeek = matchdays.filter((md) => {
    const day = parseDate(md.date);
    return day >= monday && day <= sunday;
  });

  if (inWeek.length === 0) {
    return (
      <div className="card card--padded">
        <p className="eyebrow">Trêve</p>
        <p style={{ margin: "8px 0 0" }}>Pas de match cette semaine.</p>
      </div>
    );
  }

  return inWeek.map((md) => (
    <section key={md.matchday} className="section fill">
      <div className="section__head">
        <h2 className="eyebrow">{md.stage === "regular" ? `Journée ${md.matchday}` : STAGES[md.stage]}</h2>
        <span className="muted">{formatLongDate(md.date)}</span>
      </div>
      <div className="card">
        <MatchList matches={md.matches} myClubId={myId} />
      </div>
    </section>
  ));
}

// --- Mois -------------------------------------------------------------------------

function MonthView({ current, matchdays, myId, onPick }) {
  const first = new Date(current.getFullYear(), current.getMonth(), 1);
  const gridStart = startOfWeek(first);
  const byDate = Object.fromEntries(matchdays.map((md) => [md.date, md]));

  // 6 semaines suffisent toujours à couvrir un mois.
  const days = Array.from({ length: 42 }, (_, i) => addDays(gridStart, i));

  return (
    <div className="card calendar fill">
      <div className="calendar__weekdays">
        {WEEKDAYS.map((day) => (
          <span key={day}>{day}</span>
        ))}
      </div>
      <div className="calendar__grid">
        {days.map((day) => {
          const md = byDate[toIso(day)];
          const outside = day.getMonth() !== current.getMonth();
          const mine = md?.matches.find((m) => m.home.id === myId || m.away.id === myId);
          return (
            <div key={toIso(day)} className={`calendar__day${outside ? " calendar__day--outside" : ""}`}>
              <span className="calendar__date">{day.getDate()}</span>
              {md && (
                <button type="button" className={`calendar__event${mine ? " calendar__event--mine" : ""}`} onClick={() => onPick(day)}>
                  <span className="calendar__event-label">{matchdayLabel(md)}</span>
                  {mine ? <MyMatchLine match={mine} myId={myId} /> : <span className="muted">Sans nous</span>}
                </button>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

// « vs Val-Courvas · dom. · 24-19 »
function MyMatchLine({ match, myId }) {
  const home = match.home.id === myId;
  const opponent = home ? match.away : match.home;
  const played = match.home_score !== null;
  const score = played ? `${home ? match.home_score : match.away_score}-${home ? match.away_score : match.home_score}` : null;
  const note = played ? scoreNote(match, myId) : null;
  return (
    <span className="calendar__event-text">
      <ClubCrest name={opponent.name} size={16} className="calendar__crest" />
      {opponent.name}
      <span className="muted"> · {match.neutral ? "neutre" : home ? "dom." : "ext."}</span>
      {score && <span className="num"> · {score}{note && ` ${note}`}</span>}
    </span>
  );
}

// --- Saison -----------------------------------------------------------------------

function SeasonView({ matchdays, myId }) {
  return (
    <div className="card table-wrap fill">
      <table className="table">
        <thead>
          <tr>
            <th scope="col" className="left">Journée</th>
            <th scope="col" className="left">Date</th>
            <th scope="col" className="left">Adversaire</th>
            <th scope="col" className="left">Lieu</th>
            <th scope="col">Score</th>
            <th scope="col" className="left">Résultat</th>
          </tr>
        </thead>
        <tbody>
          {matchdays.map((md) => {
            const match = md.matches.find((m) => m.home.id === myId || m.away.id === myId);
            if (!match) {
              return (
                <tr key={md.matchday}>
                  <td className="left jersey">{matchdayLabel(md)}</td>
                  <td className="left muted">{formatShortDate(md.date)}</td>
                  <td className="left muted" colSpan={4}>Sans nous</td>
                </tr>
              );
            }
            const home = match.home.id === myId;
            const opponent = home ? match.away : match.home;
            const played = match.home_score !== null;
            const mine = home ? match.home_score : match.away_score;
            const theirs = home ? match.away_score : match.home_score;
            const result = played ? RESULTS[matchResult(match, myId)] : "";
            const note = played ? scoreNote(match, myId) : null;
            return (
              <tr key={md.matchday}>
                <td className="left jersey">{matchdayLabel(md)}</td>
                <td className="left muted">{formatShortDate(md.date)}</td>
                <td className="left" style={{ fontWeight: 600 }}>
                  <span className="with-crest">
                    <ClubCrest name={opponent.name} size={20} />
                    {opponent.name}
                  </span>
                </td>
                <td className="left muted">{match.neutral ? "Terrain neutre" : home ? "Domicile" : "Extérieur"}</td>
                <td>
                  {played ? `${mine} – ${theirs}` : "–"}
                  {note && <span className="muted"> {note}</span>}
                </td>
                <td className="left">{result}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

// --- Utilitaires --------------------------------------------------------------------

const RESULTS = { V: "Victoire", N: "Nul", D: "Défaite" };

// Regroupe les matchs par journée : [{ matchday, stage, date, matches }], dans l'ordre.
function groupByMatchday(matches) {
  const groups = new Map();
  for (const match of matches) {
    if (!groups.has(match.matchday)) {
      groups.set(match.matchday, { matchday: match.matchday, stage: match.stage, date: match.date, matches: [] });
    }
    groups.get(match.matchday).matches.push(match);
  }
  return [...groups.values()].sort((a, b) => a.matchday - b.matchday);
}

function weekTitle(date) {
  const monday = startOfWeek(date);
  return `Semaine du ${formatShortDate(toIso(monday))} au ${formatShortDate(toIso(addDays(monday, 6)))}`;
}

const capitalize = (text) => text.charAt(0).toUpperCase() + text.slice(1);
