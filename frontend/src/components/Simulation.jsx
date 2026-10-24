import { useEffect, useRef, useState } from "react";

import { api } from "../api.js";
import { formatRank, matchResult, matchdayLabel, parseDate, scoreNote } from "../format.js";
import ClubCrest from "./ClubCrest.jsx";
import { SummaryRows } from "./ConfirmDialog.jsx";
import Modal from "./Modal.jsx";

// « Jusqu'à la fin de la saison » : une date au-delà de tout calendrier (les phases
// finales n'ont pas de date tant que leur tour n'est pas ouvert).
export const SEASON_END = "9999-12-31";

// Chaque journée reste au moins ce temps à l'écran : le temps de voir la page changer derrière.
const PACE_MS = 700;

const wait = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

const compactDay = new Intl.DateTimeFormat("fr-FR", { day: "numeric", month: "short" });
const fullDay = new Intl.DateTimeFormat("fr-FR", { weekday: "long", day: "numeric", month: "long" });

// "6 déc."
const formatCompactDate = (iso) => compactDay.format(parseDate(iso));
// "samedi 1er mars"
const formatFullDay = (iso) => fullDay.format(parseDate(iso)).replace(/ 1 /, " 1er ");

const plural = (count, word) => `${count} ${word}${count > 1 ? "s" : ""}`;

// Journées encore à jouer, dans l'ordre : { matchday, stage, date, matches, cup }. Celles
// du championnat, et (avec `clubId`) les journées de Coupe d'Europe où joue le club : la
// simulation s'y arrête aussi.
function upcoming(season, clubId = null) {
  const days = new Map();
  // `cup` : la coupe d'Europe de la journée (null pour le championnat).
  const add = (match, cup) => {
    const key = `${cup ? cup.code : "league"}:${match.matchday}`;
    if (!days.has(key)) {
      days.set(key, {
        matchday: match.matchday,
        stage: match.stage,
        date: match.date,
        matches: [],
        cup: Boolean(cup),
        competition: cup?.name,
        pool_rounds: cup?.pool_rounds,
      });
    }
    days.get(key).matches.push(match);
  };
  for (const match of season.matches) {
    if (match.home_score === null) add(match, null);
  }
  for (const cup of season.cups ?? []) {
    for (const match of cup.matches) {
      const ours = match.home.id === clubId || match.away.id === clubId;
      if (match.home_score === null && ours) add(match, cup);
    }
  }
  return [...days.values()].sort((a, b) => a.date.localeCompare(b.date) || a.matchday - b.matchday);
}

// La clé d'une journée jouée ou à jouer, la coupe à part du championnat.
const dayKey = (day) => `${day.cup ? (day.competition ?? "cup") : "league"}:${day.matchday}`;

// Raccourcis de « Simuler jusqu'à… » : la fin de la phase aller et celle de la saison
// régulière tant qu'elles sont devant nous, puis la fin de la saison.
export function simulationTargets(season) {
  const next = season.next_matchday;
  const targets = [];
  if (next?.stage === "regular") {
    const dayOf = (matchday) => upcoming(season).find((day) => day.stage === "regular" && day.matchday === matchday);
    const ends = [
      { key: "first-half", label: "La fin de la phase aller", short: "Phase aller", matchday: Math.floor(season.regular_matchdays / 2) },
      { key: "regular", label: "La fin de la saison régulière", short: "Saison régulière", matchday: season.regular_matchdays },
    ];
    for (const end of ends) {
      const day = dayOf(end.matchday);
      if (day && end.matchday > next.matchday) {
        targets.push({ ...end, date: day.date, hint: `J${day.matchday} · ${formatCompactDate(day.date)}` });
      }
    }
  }
  targets.push({ key: "season", label: "La fin de la saison", short: "Fin de saison", date: SEASON_END });
  return targets;
}

const rankOf = (season, clubId) => season.standings.find((row) => row.club_id === clubId)?.rank;

// Ce que plusieurs journées ont laissé au club : blessés, joueurs signés ailleurs, sélections.
const gather = (results) => ({
  injuries: results.flatMap((result) => result.injuries),
  signings: results.flatMap((result) => result.signings),
  callUps: results.flatMap((result) => result.call_ups ?? []),
});

// Pourquoi la simulation s'est arrêtée, en tête de fenêtre.
const OUTCOMES = {
  date: "Simulation terminée",
  season: "Saison terminée",
  affair: "Simulation interrompue",
  stopped: "Simulation arrêtée",
  error: "Simulation interrompue",
};

// Fenêtre « Simuler jusqu'à… » : on choisit une date (au clavier, par un raccourci ou en
// cliquant une journée), puis les journées se jouent une à une. La fenêtre garde le fil,
// match par match ; derrière elle, la page se met à jour à chaque journée (`onPlayed`
// reçoit la réponse de l'API et le cumul depuis le début). `onClose(played)` : `played`
// dit si au moins une journée a été jouée.
export default function Simulation({ season, clubId, initialUntil, onPlayed, onClose }) {
  // Sans date proposée : les deux prochaines journées, à ajuster.
  const [until, setUntil] = useState(() => initialUntil ?? upcoming(season, clubId).slice(0, 2).at(-1)?.date ?? "");
  const [stopOnAffair, setStopOnAffair] = useState(false);
  const [step, setStep] = useState("setup"); // setup → running → done
  const [results, setResults] = useState([]); // une réponse de l'API par journée jouée
  const [outcome, setOutcome] = useState(null);
  const [error, setError] = useState(null);
  const [stopping, setStopping] = useState(false);
  const stopRequested = useRef(false);
  const startRank = useRef(rankOf(season, clubId));
  const current = useRef(null); // la ligne de la journée en cours, gardée en vue
  // La page change à chaque journée : toujours sa dernière version de `onPlayed`.
  const notify = useRef(onPlayed);
  notify.current = onPlayed;
  const alive = useRef(true);
  useEffect(() => {
    alive.current = true;
    return () => {
      alive.current = false;
    };
  }, []);

  const plan = upcoming(season, clubId);
  const inRange = plan.filter((day) => day.date <= until);
  const targets = simulationTargets(season);

  useEffect(() => {
    current.current?.scrollIntoView({ block: "nearest" });
  }, [results.length, step]);

  async function run() {
    setStep("running");
    const played = [];
    let reason = "date";
    try {
      for (;;) {
        const [result] = await Promise.all([api.playMatchday(), wait(PACE_MS)]);
        if (!alive.current) return;
        played.push(result);
        setResults([...played]);
        notify.current(result, gather(played));
        if (result.dismissal) return; // limogé : la page est partie choisir un autre club
        const next = result.season.next_match ?? result.season.next_matchday;
        if (!next) {
          reason = "season";
          break;
        }
        if (next.date > until) break;
        if (stopOnAffair && result.affairs.length > 0) {
          reason = "affair";
          break;
        }
        if (stopRequested.current) {
          reason = "stopped";
          break;
        }
      }
    } catch (err) {
      if (!alive.current) return;
      setError(err);
      reason = "error";
    }
    setOutcome(reason);
    setStep("done");
  }

  const requestStop = () => {
    stopRequested.current = true;
    setStopping(true);
  };

  const close = () => onClose(results.length > 0);
  const last = results.at(-1);
  const total = results.length + (step === "running" ? inRange.length : 0);
  const untilLabel = until === SEASON_END ? "Jusqu'à la fin de la saison" : until ? `Jusqu'au ${formatFullDay(until)}` : "Jusqu'à…";

  return (
    <Modal compact light={step !== "setup"} className="modal--dialog simulation" onClose={step === "running" ? () => {} : close}>
      <div>
        <p className="eyebrow">
          {step === "setup" && "Simulation"}
          {/* Jusqu'à la fin de la saison, le compte est inconnu : les phases finales s'ouvrent en chemin. */}
          {step === "running" &&
            `Simulation en cours · ${
              until === SEASON_END
                ? matchdayLabel(inRange[0] ?? last.played)
                : `journée ${Math.min(results.length + 1, total)} sur ${total}`
            }`}
          {step === "done" && OUTCOMES[outcome]}
        </p>
        <h2 className="confirm__title">{untilLabel}</h2>
      </div>

      {step === "setup" && (
        <div className="simulation__fields">
          <div className="field">
            <label htmlFor="simulation-until">Simuler jusqu'au</label>
            <input
              id="simulation-until"
              type="date"
              className="input"
              min={(season.next_match ?? season.next_matchday).date}
              value={until === SEASON_END ? "" : until}
              onChange={(event) => setUntil(event.target.value)}
            />
          </div>
          <div className="chips" role="group" aria-label="Raccourcis">
            {targets.map((target) => (
              <button
                key={target.key}
                type="button"
                className="chip"
                aria-pressed={until === target.date}
                onClick={() => setUntil(target.date)}
              >
                {target.short}
              </button>
            ))}
          </div>
        </div>
      )}

      {step === "running" && (
        <div className="meter" role="progressbar" aria-valuemin={0} aria-valuemax={total} aria-valuenow={results.length}>
          <div className="meter__fill meter__fill--accent simulation__progress" style={{ width: `${(results.length / total) * 100}%` }} />
        </div>
      )}

      {step === "done" && outcome === "affair" && (
        <p className="confirm__warning">Une affaire demande ta réponse avant la journée suivante.</p>
      )}
      {error && <p className="confirm__warning">{error.message}</p>}

      <ul className="simulation__days">
        {results.map((result) => (
          <Day key={dayKey(result.played)} day={result.played} clubId={clubId} state="played" />
        ))}
        {(step === "setup" ? plan : inRange).map((day, index) => {
          const running = step === "running" && index === 0;
          return (
            <Day
              key={dayKey(day)}
              day={day}
              clubId={clubId}
              state={running ? "current" : day.date <= until ? "todo" : "out"}
              rowRef={running ? current : null}
              onPick={step === "setup" ? () => setUntil(day.date) : null}
            />
          );
        })}
      </ul>

      {step === "setup" && (
        <div className="simulation__option">
          <div>
            <strong>Affaires entre deux matchs</strong>
            <p className="muted">
              {stopOnAffair
                ? "La simulation s'arrête dès qu'une affaire demande ta réponse."
                : "Le staff tranche à ta place les affaires restées sans réponse."}
            </p>
          </div>
          <div className="chips" role="group" aria-label="Affaires entre deux matchs">
            <button type="button" className="chip" aria-pressed={!stopOnAffair} onClick={() => setStopOnAffair(false)}>
              Le staff tranche
            </button>
            <button type="button" className="chip" aria-pressed={stopOnAffair} onClick={() => setStopOnAffair(true)}>
              M'arrêter
            </button>
          </div>
        </div>
      )}

      {step === "done" && results.length > 0 && (
        <Summary results={results} clubId={clubId} startRank={startRank.current} />
      )}

      <div className="confirm__actions">
        {step === "setup" && (
          <>
            <button type="button" className="button" onClick={close}>
              Annuler
            </button>
            <button type="button" className="button button--primary" disabled={inRange.length === 0} onClick={run}>
              {inRange.length === 0
                ? "Aucune journée d'ici là"
                : until === SEASON_END
                  ? "Simuler jusqu'à la finale"
                  : `Simuler ${plural(inRange.length, "journée")}`}
            </button>
          </>
        )}
        {step === "running" && (
          <button type="button" className="button" disabled={stopping} onClick={requestStop}>
            {stopping ? "Arrêt après cette journée…" : "Arrêter"}
          </button>
        )}
        {step === "done" && (
          <button type="button" className="button button--primary" autoFocus onClick={close}>
            {last?.affairs.length > 0
              ? `Régler ${last.affairs.length > 1 ? `les ${last.affairs.length} affaires` : "l'affaire"}`
              : last?.season.phase === "finished"
                ? "Voir le bilan de la saison"
                : "Fermer"}
          </button>
        )}
      </div>
    </Modal>
  );
}

const VENUES = { home: "dom.", away: "ext.", neutral: "neutre" };

// Une journée de la liste : son nom, sa date, notre adversaire, puis notre résultat une
// fois jouée. `state` : played, current (en train de se jouer), todo, out (après la date
// choisie). Avec `onPick`, la ligne est un bouton qui arrête la simulation à cette journée.
function Day({ day, clubId, state, rowRef, onPick }) {
  const match = day.matches.find((m) => m.home.id === clubId || m.away.id === clubId);
  const home = match?.home.id === clubId;
  const opponent = match && (home ? match.away : match.home);
  const result = state === "played" && match ? matchResult(match, clubId) : null;
  const note = result ? scoreNote(match, clubId) : null;
  const Row = onPick ? "button" : "div";
  return (
    <li className={`simulation__day simulation__day--${state}`} ref={rowRef}>
      <Row className="simulation__row" {...(onPick ? { type: "button", onClick: onPick } : {})}>
        <span className="simulation__when">
          <strong>{matchdayLabel(day)}</strong>
          <span className="muted num">{formatCompactDate(day.date)}</span>
        </span>
        {opponent ? (
          <span className="simulation__opponent">
            <ClubCrest name={opponent.name} size={18} />
            <span className="simulation__name">{opponent.name}</span>
            <span className="muted simulation__venue">{VENUES[match.neutral ? "neutral" : home ? "home" : "away"]}</span>
          </span>
        ) : (
          <span className="muted simulation__opponent">Ton club ne joue pas</span>
        )}
        <span className="simulation__result">
          {result && (
            <>
              <span className={`pill pill--${result}`}>{result}</span>
              <span className="simulation__score num">
                {home ? match.home_score : match.away_score} – {home ? match.away_score : match.home_score}
                {note && <small className="match__note">{note}</small>}
              </span>
            </>
          )}
          {state === "current" && <span className="muted">En cours…</span>}
        </span>
      </Row>
    </li>
  );
}

// Ce que la simulation a donné : notre bilan, le classement avant et après, et ce qui
// attend le manager (blessés, départs annoncés, sélections, affaires tranchées sans lui).
function Summary({ results, clubId, startRank }) {
  const outcomes = results
    .map((result) => result.played.matches.find((m) => m.home.id === clubId || m.away.id === clubId))
    .filter(Boolean)
    .map((match) => matchResult(match, clubId));
  const count = (letter) => outcomes.filter((result) => result === letter).length;
  const endRank = rankOf(results.at(-1).season, clubId);
  const { injuries, signings, callUps } = gather(results);
  const called = callUps.reduce((sum, notice) => sum + notice.players.length, 0);
  // Une affaire encore en attente quand la journée suivante se joue est tranchée d'office.
  const settled = results.slice(0, -1).reduce((sum, result) => sum + result.affairs.length, 0);
  const names = (people) =>
    people.slice(0, 3).join(", ") + (people.length > 3 ? ` et ${plural(people.length - 3, "autre")}` : "");

  const rows = [
    {
      label: "Bilan",
      value: outcomes.length > 0 ? `${count("V")} V · ${count("N")} N · ${count("D")} D` : "–",
      hint: `${plural(results.length, "journée")} simulée${results.length > 1 ? "s" : ""}`,
    },
  ];
  if (startRank && endRank) {
    rows.push(
      startRank === endRank
        ? { label: "Classement", value: formatRank(endRank) }
        : { label: "Classement", from: formatRank(startRank), to: formatRank(endRank) },
    );
  }
  if (injuries.length > 0) {
    rows.push({ label: "Blessés", value: injuries.length, hint: names(injuries.map((item) => item.player.name)) });
  }
  if (signings.length > 0) {
    rows.push({ label: "Signés ailleurs", value: signings.length, hint: names(signings.map((item) => item.player.name)) });
  }
  if (called > 0) rows.push({ label: "Retenus en sélection", value: called });
  if (settled > 0) rows.push({ label: "Affaires tranchées par le staff", value: settled });

  return <SummaryRows rows={rows} />;
}
