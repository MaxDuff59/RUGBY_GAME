import { useCallback, useMemo, useState } from "react";
import { useOutletContext } from "react-router-dom";

import { api } from "../api.js";
import ClubCrest from "../components/ClubCrest.jsx";
import MatchList from "../components/MatchList.jsx";
import MatchReport from "../components/MatchReport.jsx";
import WeatherIcon from "../components/WeatherIcon.jsx";
import {
  STAGES,
  addDays,
  formatLongDate,
  formatMonthYear,
  formatShortDate,
  matchResult,
  matchdayLabel,
  matchdayTitle,
  scoreNote,
  parseDate,
  startOfWeek,
  toIso,
  windowDayLabel,
} from "../format.js";
import { useApi } from "../hooks/useApi.js";

const VIEWS = [
  { key: "week", label: "Semaine" },
  { key: "month", label: "Mois" },
  { key: "season", label: "Saison" },
  { key: "cup", label: "Coupes d'Europe", cup: true },
];

const WEEKDAYS = ["Lun", "Mar", "Mer", "Jeu", "Ven", "Sam", "Dim"];

// Calendrier de la saison : par semaine, par mois ou en entier. Les fenêtres
// internationales y figurent aussi, samedi par samedi : un jour où le club joue pendant
// que des sélections jouent est un doublon, avec nos joueurs retenus quand les listes
// sont annoncées.
export default function Calendar() {
  const { career } = useOutletContext();
  const myId = career.club_id;
  const season = useApi(useCallback(api.getCurrentSeason, []));
  // Sans sélections (monde de clubs inventés) ou en cas d'erreur : un calendrier de club seul.
  const tests = useApi(useCallback(api.getInternationals, []));
  const international = useMemo(() => internationalDays(tests.data), [tests.data]);
  const [view, setView] = useState("week");
  // Date « curseur » : null tant que la saison n'est pas chargée (on se place
  // alors sur la prochaine journée).
  const [cursor, setCursor] = useState(null);

  const matchdays = useMemo(() => groupByMatchday(season.data?.matches ?? []), [season.data]);
  // Les coupes d'Europe, journée par journée (poules, puis tours à élimination directe),
  // chaque journée avec le nom de sa coupe.
  const cupDays = useMemo(
    () =>
      (season.data?.cups ?? []).flatMap((cup) =>
        groupByMatchday(cup.matches).map((md) => ({
          ...md,
          cup: true,
          code: cup.code,
          competition: cup.name,
          pool_rounds: cup.pool_rounds,
        })),
      ),
    [season.data],
  );

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
          {VIEWS.filter((v) => !v.cup || data.cups.length > 0).map((v) => (
            <button key={v.key} type="button" className="chip" aria-pressed={view === v.key} onClick={() => setView(v.key)}>
              {v.label}
            </button>
          ))}
        </div>
      </header>

      {(view === "week" || view === "month") && (
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

      {view === "week" && (
        <WeekView current={current} matchdays={matchdays} cupDays={cupDays} international={international} myId={myId} />
      )}
      {view === "month" && (
        <MonthView
          current={current}
          matchdays={matchdays}
          international={international}
          myId={myId}
          onPick={(date) => {
            setCursor(date);
            setView("week");
          }}
        />
      )}
      {view === "season" && <SeasonView matchdays={matchdays} cupDays={cupDays} international={international} myId={myId} />}
      {view === "cup" && data.cups.length > 0 && <CupView cups={data.cups} cupDays={cupDays} myId={myId} />}
    </>
  );
}

// --- Semaine ----------------------------------------------------------------------

function WeekView({ current, matchdays, cupDays, international, myId }) {
  const monday = startOfWeek(current);
  const sunday = addDays(monday, 6);
  const within = (iso) => {
    const day = parseDate(iso);
    return day >= monday && day <= sunday;
  };
  const inWeek = matchdays.filter((md) => within(md.date));
  const cupWeek = cupDays.filter((md) => within(md.date));
  const testDays = [...international.values()].filter((day) => within(day.date));

  return (
    <>
      {inWeek.length === 0 && cupWeek.length === 0 && (
        <div className="card card--padded">
          <p className="eyebrow">Trêve</p>
          <p style={{ margin: "8px 0 0" }}>
            {testDays.length > 0 ? "Pas de match de championnat cette semaine : place aux sélections." : "Pas de match cette semaine."}
          </p>
        </div>
      )}
      {inWeek.map((md) => {
        const doublon = international.get(md.date);
        const ours = md.matches.find((m) => m.home.id === myId || m.away.id === myId);
        return (
          <section key={md.matchday} className="section fill">
            <div className="section__head">
              <h2 className="eyebrow">{md.stage === "regular" ? `Journée ${md.matchday}` : STAGES[md.stage]}</h2>
              <span className="muted">{formatLongDate(md.date)}</span>
            </div>
            <div className="card">
              {doublon && ours && (
                <p className="call-ups">
                  <span className="tag tag--fragile">Doublon</span> {doublonText(doublon, ours.home_score !== null)}
                </p>
              )}
              <MatchList matches={md.matches} myClubId={myId} />
            </div>
          </section>
        );
      })}
      {cupWeek.map((md) => (
        <section key={`${md.code}-${md.matchday}`} className="section fill">
          <div className="section__head">
            <h2 className="eyebrow">{matchdayTitle(md)}</h2>
            <span className="muted">{formatLongDate(md.date)}</span>
          </div>
          <div className="card">
            <MatchList matches={md.matches} myClubId={myId} />
          </div>
        </section>
      ))}
      {testDays.map((day) => (
        <section key={day.date} className="section fill">
          <div className="section__head">
            <h2 className="eyebrow">
              {day.window.name} · {day.label}
            </h2>
            <span className="muted">{formatLongDate(day.date)}</span>
          </div>
          <div className="card">
            {day.matches.length > 0 ? (
              <MatchList matches={day.matches} myClubId={null} reports={false} />
            ) : (
              <p className="table__note">Les affiches seront connues à la fin du tour précédent.</p>
            )}
          </div>
        </section>
      ))}
    </>
  );
}

// --- Mois -------------------------------------------------------------------------

function MonthView({ current, matchdays, international, myId, onPick }) {
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
          const test = international.get(toIso(day));
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
              {/* Sélections ce jour-là : un doublon si nous jouons aussi. */}
              {test && (
                <button
                  type="button"
                  className="calendar__event calendar__event--test"
                  title={mine ? doublonText(test, mine.home_score !== null) : `${test.window.name} · ${test.label}`}
                  onClick={() => onPick(day)}
                >
                  <span className="calendar__event-text">
                    {mine && <span className="tag tag--fragile">Doublon</span>} {test.window.short_name}
                    <span className="muted"> · {mine && test.absent.length > 0 ? absentCount(test) : test.label}</span>
                  </span>
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

function SeasonView({ matchdays, cupDays, international, myId }) {
  const [open, setOpen] = useState(null); // fiche du match ouverte
  // Nos journées, et entre elles les samedis où seules les sélections jouent.
  const clubDates = new Set(matchdays.map((md) => md.date));
  // Nos matchs de coupe s'intercalent, à leur date.
  const cupRows = cupDays
    .map((md) => ({ md, match: md.matches.find((m) => m.home.id === myId || m.away.id === myId) }))
    .filter(({ match }) => match)
    .map(({ md, match }) => ({ date: md.date, md: { ...md, matches: [match], cup: true } }));
  const rows = [
    ...matchdays.map((md) => ({ date: md.date, md })),
    ...cupRows,
    ...[...international.values()].filter((day) => !clubDates.has(day.date)).map((test) => ({ date: test.date, test })),
  ].sort((a, b) => a.date.localeCompare(b.date));
  const withTests = international.size > 0;

  return (
    <div className="card table-wrap fill">
      <table className="table">
        <thead>
          <tr>
            <th scope="col" className="left">Journée</th>
            <th scope="col" className="left">Date</th>
            <th scope="col" className="left">Adversaire</th>
            <th scope="col" className="left">Lieu</th>
            <th scope="col">Météo</th>
            <th scope="col">Score</th>
            <th scope="col">Résultat</th>
            {withTests && <th scope="col" className="left">Sélections</th>}
          </tr>
        </thead>
        <tbody>
          {rows.map(({ date, md, test }) => {
            if (test) {
              return (
                <tr key={`test-${date}`} className="table__row--bench">
                  <td className="left jersey">–</td>
                  <td className="left muted">{formatShortDate(date)}</td>
                  <td className="left muted" colSpan={5}>Pas de match de championnat</td>
                  <td className="left">
                    {test.window.short_name} <span className="muted">· {test.label}</span>
                  </td>
                </tr>
              );
            }
            const doublon = international.get(md.date);
            const match = md.matches.find((m) => m.home.id === myId || m.away.id === myId);
            if (!match) {
              return (
                <tr key={`${md.cup ? `${md.code}-` : ""}${md.matchday}`}>
                  <td className="left jersey">{matchdayLabel(md)}</td>
                  <td className="left muted">{formatShortDate(md.date)}</td>
                  <td className="left muted" colSpan={5}>Sans nous</td>
                  {withTests && (
                    <td className="left muted">{doublon && `${doublon.window.short_name} · ${doublon.label}`}</td>
                  )}
                </tr>
              );
            }
            const home = match.home.id === myId;
            const opponent = home ? match.away : match.home;
            const played = match.home_score !== null;
            const mine = home ? match.home_score : match.away_score;
            const theirs = home ? match.away_score : match.home_score;
            const result = played ? matchResult(match, myId) : null;
            const note = played ? scoreNote(match, myId) : null;
            return (
              <tr key={`${md.cup ? `${md.code}-` : ""}${md.matchday}`}>
                <td className="left jersey">{matchdayLabel(md)}</td>
                <td className="left muted">{formatShortDate(md.date)}</td>
                <td className="left" style={{ fontWeight: 600 }}>
                  <span className="with-crest">
                    <ClubCrest name={opponent.name} size={20} />
                    {opponent.name}
                  </span>
                </td>
                <td className="left muted">{match.neutral ? "Terrain neutre" : home ? "Domicile" : "Extérieur"}</td>
                <td className="muted">
                  <WeatherIcon weather={match.weather} />
                </td>
                <td>
                  {played ? (
                    <button type="button" className="link-button num" onClick={() => setOpen(match)}>
                      {mine} – {theirs}
                    </button>
                  ) : (
                    "–"
                  )}
                  {note && <span className="muted"> {note}</span>}
                </td>
                <td>
                  {result && (
                    <span className={`result-dot result-dot--${result}`} role="img" title={RESULTS[result]} aria-label={RESULTS[result]} />
                  )}
                </td>
                {withTests && (
                  <td className="left" title={doublon ? doublonText(doublon, played) : undefined}>
                    {doublon && (
                      <>
                        <span className="tag tag--fragile">Doublon</span> {doublon.window.short_name}
                        <span className="muted"> · {doublon.absent.length > 0 ? absentCount(doublon) : doublon.label}</span>
                      </>
                    )}
                  </td>
                )}
              </tr>
            );
          })}
        </tbody>
      </table>
      {open && <MatchReport summary={open} myClubId={myId} onClose={() => setOpen(null)} />}
    </div>
  );
}

// --- Coupes d'Europe --------------------------------------------------------------

// Une coupe d'Europe (au choix, celle de notre club d'abord) : à gauche ses poules (les
// deux premiers, qualifiés, au-dessus d'un filet), à droite les journées, poules puis
// phases finales, la plus récente jouée en tête ; notre club en accent.
function CupView({ cups, cupDays, myId }) {
  const ours = cups.find((cup) => cup.pools.some((pool) => pool.table.some((row) => row.club.id === myId)));
  const [code, setCode] = useState((ours ?? cups[0]).code);
  const cup = cups.find((c) => c.code === code) ?? cups[0];
  const ordered = cupDays.filter((md) => md.code === cup.code).reverse();
  // Trois poules : les deux meilleurs troisièmes complètent les quarts.
  const rule = cup.pools.length === 3 ? "Les deux premiers et les deux meilleurs troisièmes vont en quarts" : "Les deux premiers vont en quarts";
  return (
    <div className="cup fill">
      <section className="card panel">
        <div className="panel__head">
          {cups.length > 1 ? (
            <div className="chips" role="group" aria-label="Coupe">
              {cups.map((c) => (
                <button key={c.code} type="button" className="chip chip--small" aria-pressed={c.code === cup.code} onClick={() => setCode(c.code)}>
                  {c.name}
                </button>
              ))}
            </div>
          ) : (
            <span className="eyebrow">Poules</span>
          )}
          <span className="muted">{cup.champion ? `Vainqueur : ${cup.champion.name}` : rule}</span>
        </div>
        <div className="panel__body cup__pools">
          {cup.pools.map((pool) => (
            <table key={pool.pool} className="table cup__pool">
              <thead>
                <tr>
                  <th scope="col" className="left">Poule {pool.pool}</th>
                  <th scope="col">J</th>
                  <th scope="col">G</th>
                  <th scope="col">Diff</th>
                  <th scope="col">Pts</th>
                </tr>
              </thead>
              <tbody>
                {pool.table.map((row, index) => (
                  <tr
                    key={row.club.id}
                    className={`${row.club.id === myId ? "table__row--mine" : ""}${index === 1 ? " cup__cut" : ""}`}
                  >
                    <td className="left">
                      <span className="with-crest">
                        <ClubCrest name={row.club.name} size={18} />
                        {row.club.name}
                      </span>
                    </td>
                    <td className="num">{row.played}</td>
                    <td className="num">{row.won}</td>
                    <td className="num">{row.points_difference > 0 ? `+${row.points_difference}` : row.points_difference}</td>
                    <td className="num" style={{ fontWeight: 700 }}>
                      {row.league_points}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          ))}
        </div>
      </section>
      <section className="card panel">
        <div className="panel__head">
          <span className="eyebrow">Matchs</span>
        </div>
        <div className="panel__body">
          {ordered.map((md) => (
            <div key={`${md.code}-${md.matchday}`}>
              <div className="matches__stage">
                {md.stage === "regular" ? `Poules · journée ${md.matchday}` : STAGES[md.stage]} · {formatLongDate(md.date)}
              </div>
              <MatchList matches={md.matches} myClubId={myId} />
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}

// --- Utilitaires --------------------------------------------------------------------

const RESULTS = { V: "Victoire", N: "Nul", D: "Défaite" };

// Les samedis des fenêtres internationales, par date : la fenêtre, le libellé du jour
// (« Journée 2 », « Test 1 », « Quarts de finale »), ses matchs, et nos joueurs retenus
// qui manqueront ce jour-là (connus une fois les listes annoncées).
function internationalDays(data) {
  const days = new Map();
  for (const window of data?.windows ?? []) {
    for (const date of window.dates) {
      days.set(date, {
        date,
        window,
        label: windowDayLabel(window, date),
        matches: window.matches.filter((match) => match.date === date),
        absent: [],
      });
    }
  }
  for (const { player, dates } of data?.my_players ?? []) {
    for (const date of dates) days.get(date)?.absent.push(player.name);
  }
  return days;
}

const absentCount = (day) => `${day.absent.length} absent${day.absent.length > 1 ? "s" : ""}`;

// « Tournoi des Six Nations, journée 1 : 5 joueurs en sélection (…) », ou ce qu'on en sait :
// rien de plus pour un match déjà joué, et avant l'annonce des listes ou le tirage d'un
// tour de Coupe du monde, on ne peut pas encore dire qui manquera.
function doublonText(day, played = false) {
  const where = `${day.window.name}, ${day.label.toLowerCase()}`;
  if (day.absent.length > 0) {
    return `${where} : ${day.absent.length} joueur${day.absent.length > 1 ? "s" : ""} en sélection (${day.absent.join(", ")}).`;
  }
  if (played) return `${where}.`;
  if (day.matches.length === 0) return `${where} : nos joueurs des sélections encore en course manqueront.`;
  if (!day.window.announced) return `${where} : les listes ne sont pas encore annoncées.`;
  return `${where} : aucun de nos joueurs n'est retenu.`;
}

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
