import { useCallback, useEffect, useRef, useState } from "react";
import { Link, useLocation, useNavigate, useOutletContext } from "react-router-dom";

import { api } from "../api.js";
import ClubCrest from "../components/ClubCrest.jsx";
import MatchList from "../components/MatchList.jsx";
import WindowBoard from "../components/WindowBoard.jsx";
import {
  INJURY_SOURCES,
  SEVERITIES,
  formatLongDate,
  formatShortDate,
  matchResult,
  scoreNote,
  testLabel,
} from "../format.js";
import { useApi } from "../hooks/useApi.js";

const RESULTS = { V: "Victoire", N: "Nul", D: "Défaite" };

// Tableau de bord du sélectionneur : ce qui l'attend (liste à annoncer, match à jouer,
// jours à passer), puis la fenêtre internationale en cours, le parcours de la sélection
// et le dernier jour joué. Le monde avance un jour de match à la fois.
export default function Selection() {
  const { career } = useOutletContext();
  const navigate = useNavigate();
  const location = useLocation();
  const myId = career.club_id;
  const selection = useApi(useCallback(api.getSelection, []));
  const calendar = useApi(useCallback(api.getInternationals, []));
  // Match en direct en cours (404 sinon) : « Jouer le match » le reprend.
  const liveMatch = useApi(useCallback(api.getLive, []));
  const [lastDay, setLastDay] = useState(null); // le dernier jour joué depuis cette page
  const [injuries, setInjuries] = useState([]); // blessés du groupe depuis le dernier rendez-vous
  const [busy, setBusy] = useState(false);
  const [running, setRunning] = useState(false); // on enchaîne les jours jusqu'au prochain rendez-vous
  const [actionError, setActionError] = useState(null);
  const stopped = useRef(false);

  const { setData: setSelection } = selection;
  const { reload: reloadCalendar } = calendar;

  // Un jour vient d'être joué (ici, ou fini depuis la page Match).
  const applyDay = useCallback(
    (result, fresh = false) => {
      setSelection(result.selection);
      setLastDay(result);
      setInjuries((previous) => (fresh ? result.injuries : [...previous, ...result.injuries]));
    },
    [setSelection],
  );

  // La page Match renvoie ici avec le jour qu'elle vient de finir (une seule fois).
  const applied = useRef(null);
  useEffect(() => {
    const played = location.state?.played;
    if (!played || applied.current === played) return;
    applied.current = played;
    applyDay(played, true);
    liveMatch.setData(null);
    reloadCalendar();
    navigate(location.pathname, { replace: true, state: null });
  }, [location, applyDay, navigate, liveMatch.setData, reloadCalendar]);

  // Joue le prochain jour ; avec `untilEvent`, enchaîne tant que rien ne nous attend.
  async function advance(untilEvent) {
    setBusy(true);
    setRunning(untilEvent);
    setActionError(null);
    stopped.current = false;
    try {
      let first = true;
      let phase;
      do {
        const result = await api.advanceSelection();
        applyDay(result, first);
        first = false;
        phase = result.selection.phase;
      } while (untilEvent && phase === "wait" && !stopped.current);
    } catch (err) {
      setActionError(err);
    } finally {
      setBusy(false);
      setRunning(false);
      reloadCalendar();
    }
  }

  async function playLive() {
    if (liveMatch.data) {
      navigate("/match");
      return;
    }
    setBusy(true);
    setActionError(null);
    try {
      await api.startLive();
      navigate("/match");
    } catch (err) {
      setActionError(err);
      setBusy(false);
    }
  }

  async function nextSeason() {
    setBusy(true);
    setActionError(null);
    try {
      await api.startNextSeason();
      setLastDay(null);
      setInjuries([]);
      selection.reload();
      reloadCalendar();
    } catch (err) {
      setActionError(err);
    } finally {
      setBusy(false);
    }
  }

  if (selection.loading && !selection.data) return <p className="status">Chargement…</p>;
  if (selection.error) return <p className="status status--error">{selection.error.message}</p>;

  const state = selection.data;
  const { window: current, next_match: nextMatch, record } = state;
  const windows = calendar.data?.windows ?? [];
  const ours = windows.flatMap((w) =>
    w.matches.filter((m) => m.home.id === myId || m.away.id === myId).map((m) => ({ ...m, window: w })),
  );

  return (
    <>
      {actionError && <p className="status--error">{actionError.message}</p>}

      <div className="hero-row">
        <section className="hero">
          {state.phase === "finished" && (
            <>
              <p className="eyebrow">Saison {state.year} terminée</p>
              <h1 className="hero__title">Bilan : {recordLabel(record)}</h1>
              <p className="hero__sub">Tous les championnats ont rendu leur verdict</p>
              <div className="hero__actions">
                <button type="button" className="button button--primary" disabled={busy} onClick={nextSeason}>
                  {busy ? "Intersaison…" : `Lancer la saison ${state.year + 1}`}
                </button>
              </div>
            </>
          )}

          {state.phase === "list" && (
            <>
              <p className="eyebrow">
                {current.name} · premier match le {formatLongDate(current.dates[0])}
              </p>
              <h1 className="hero__title">Annonce ta liste</h1>
              <p className="hero__sub">
                {state.squad_size} joueurs, avant le {formatLongDate(current.announce_by)}
              </p>
              <div className="hero__actions">
                <Link to="/liste" className="button button--primary">
                  Composer la liste
                </Link>
                <span className="muted">La saison reprend dès que la liste est annoncée.</span>
              </div>
            </>
          )}

          {state.phase === "match" && (
            <>
              <p className="eyebrow">
                {current.name} · {testLabel(current, nextMatch)} · {formatLongDate(nextMatch.date)}
              </p>
              <Opponent match={nextMatch} myId={myId} />
              <div className="hero__actions">
                <button type="button" className="button" disabled={busy} onClick={() => advance(false)}>
                  {busy ? "Simulation…" : "Simuler le match"}
                </button>
                <button
                  type="button"
                  className="button button--primary"
                  disabled={busy}
                  title="Le match en direct, minute par minute"
                  onClick={playLive}
                >
                  {liveMatch.data ? `Reprendre le match (${liveMatch.data.minute}')` : "Jouer le match"}
                </button>
                <Link to="/effectif" className="muted">
                  Composer le XV
                </Link>
              </div>
            </>
          )}

          {state.phase === "wait" && (
            <>
              <p className="eyebrow">
                {running && lastDay ? `Simulation · ${formatLongDate(lastDay.date)}` : `Nous sommes le ${formatLongDate(state.today)}`}
              </p>
              {nextMatch && state.list_announced ? (
                <Opponent match={nextMatch} myId={myId} label={`${current.name} · ${formatLongDate(nextMatch.date)}`} />
              ) : current ? (
                <>
                  <h1 className="hero__title">{current.name}</h1>
                  <p className="hero__sub">
                    Liste à annoncer avant le {formatLongDate(current.announce_by)} · premier match le{" "}
                    {formatLongDate(current.dates[0])}
                  </p>
                </>
              ) : (
                <>
                  <h1 className="hero__title">Plus de rendez-vous</h1>
                  <p className="hero__sub">Les championnats finissent leur saison</p>
                </>
              )}
              <div className="hero__actions">
                {running ? (
                  <button type="button" className="button" onClick={() => (stopped.current = true)}>
                    Arrêter
                  </button>
                ) : (
                  <button type="button" className="button button--primary" disabled={busy} onClick={() => advance(true)}>
                    {current ? "Avancer jusqu'au prochain rendez-vous" : "Avancer jusqu'à la fin de la saison"}
                  </button>
                )}
                <span className="muted">
                  {running
                    ? "Les clubs jouent leur saison, jour de match après jour de match…"
                    : "Les clubs et les autres sélections jouent pendant ce temps."}
                </span>
              </div>
            </>
          )}
        </section>

        <aside className="card card--padded club-notes facts">
          <div className="section__head">
            <h2 className="eyebrow">Le groupe</h2>
            <span className="muted">Saison {state.year}</span>
          </div>
          <dl className="facts__list">
            <dt>Bilan</dt>
            <dd>
              {record.played > 0
                ? `${plural(record.won, "victoire")}, ${plural(record.drawn, "nul")}, ${plural(record.lost, "défaite")}`
                : "Aucun match joué"}
            </dd>
            <dt>Rendez-vous</dt>
            <dd>
              {current ? `${current.name}, du ${formatShortDate(current.dates[0])} au ${formatShortDate(current.dates.at(-1))}` : "Aucun d'ici la fin de saison"}
            </dd>
            <dt>Liste</dt>
            <dd>
              {!current
                ? "—"
                : state.list_announced
                  ? `${state.squad_size} joueurs annoncés`
                  : `À annoncer avant le ${formatShortDate(current.announce_by)}`}
            </dd>
          </dl>
          <div className="facts__links">
            <Link to="/liste">Voir la liste</Link>
            <Link to="/effectif">Composer le XV</Link>
          </div>
        </aside>
      </div>

      <div className="club-grid club-grid--three fill">
        <WindowBoard windows={windows} initial={current?.code} myId={myId} />

        <section className="section">
          <div className="section__head">
            <h2 className="eyebrow">Notre saison</h2>
            <span className="muted">{ours.length} matchs</span>
          </div>
          <div className="card table-wrap">
            <table className="table table--nowrap">
              <tbody>
                {ours.map((match) => {
                  const home = match.home.id === myId;
                  const opponent = home ? match.away : match.home;
                  const played = match.home_score !== null;
                  const result = played ? matchResult(match, myId) : null;
                  const note = played ? scoreNote(match, myId) : null;
                  return (
                    <tr key={match.id}>
                      <td className="left muted">{formatShortDate(match.date)}</td>
                      <td className="left" style={{ fontWeight: 600 }}>
                        <span className="with-crest">
                          <ClubCrest name={opponent.name} size={20} />
                          {opponent.name}
                        </span>
                      </td>
                      <td className="left muted">{match.neutral ? "Neutre" : home ? "Dom." : "Ext."}</td>
                      <td>
                        {played ? `${home ? match.home_score : match.away_score} – ${home ? match.away_score : match.home_score}` : "–"}
                        {note && <span className="muted"> {note}</span>}
                      </td>
                      <td>
                        {result && (
                          <span className={`result-dot result-dot--${result}`} role="img" title={RESULTS[result]} aria-label={RESULTS[result]} />
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
            {ours.length === 0 && <p className="table__note">Aucun match cette saison.</p>}
          </div>
        </section>

        <section className="section">
          <div className="section__head">
            <h2 className="eyebrow">{lastDay ? "Dernier jour joué" : "Blessés du groupe"}</h2>
            {lastDay && <span className="muted">{formatLongDate(lastDay.date)}</span>}
          </div>
          <div className="card">
            {lastDay && lastDay.tests.length > 0 && <MatchList matches={lastDay.tests} myClubId={myId} reports={false} />}
            {lastDay && lastDay.tests.length === 0 && (
              <p className="table__note">
                Pas de match international ce jour-là · {lastDay.club_matches} match{lastDay.club_matches > 1 ? "s" : ""} de clubs.
              </p>
            )}
            {injuries.length > 0 && (
              <>
                <div className="matches__stage">Blessés du groupe · {injuries.length}</div>
                <ul className="injury-list">
                  {injuries.map(({ player, injury }) => (
                    <li key={injury.id}>
                      <span className={`tag tag--${injury.severity}`}>{SEVERITIES[injury.severity].label}</span>
                      <span style={{ fontWeight: 600 }}>{player.name}</span>
                      <span className="muted">
                        {injury.kind} {INJURY_SOURCES[injury.source]} · retour le {formatShortDate(injury.return_date)}
                      </span>
                    </li>
                  ))}
                </ul>
              </>
            )}
            {!lastDay && injuries.length === 0 && (
              <p className="table__note">Les blessures des joueurs de ta liste s'afficheront ici au fil des jours.</p>
            )}
          </div>
        </section>
      </div>
    </>
  );
}

const recordLabel = ({ won, drawn, lost }) => `${won} V · ${drawn} N · ${lost} D`;

// « 1 victoire », « 2 nuls », « 0 défaite ».
const plural = (count, word) => `${count} ${word}${count > 1 ? "s" : ""}`;

function Opponent({ match, myId, label }) {
  const home = match.home.id === myId;
  const opponent = home ? match.away : match.home;
  return (
    <>
      <div className="hero__club">
        <ClubCrest name={opponent.name} size={56} />
        <h1 className="hero__title">{opponent.name}</h1>
      </div>
      <p className="hero__sub">
        {match.neutral ? "Terrain neutre" : home ? "À domicile" : "À l'extérieur"}
        {label ? ` · ${label}` : ""}
      </p>
    </>
  );
}
