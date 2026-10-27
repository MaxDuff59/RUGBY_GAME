import { useCallback, useEffect, useRef, useState } from "react";
import { Link, useNavigate, useOutletContext } from "react-router-dom";

import { api } from "../api.js";
import ClubCrest from "../components/ClubCrest.jsx";
import { useConfirm } from "../components/ConfirmDialog.jsx";
import Modal from "../components/Modal.jsx";
import Momentum from "../components/Momentum.jsx";
import WeatherIcon from "../components/WeatherIcon.jsx";
import {
  CRUNCH_OPTIONS,
  EVENTS,
  MATCH_STATS,
  POSITION_SHORT,
  POSITIONS,
  TACTICS,
  TALK_MOMENTS,
  TALK_OUTCOMES,
  TALKS,
  WEATHER,
  CROWD_MOODS,
  crowdEffect,
  formatCrowd,
  formatLongDate,
  formatNote,
  matchdayTitle,
} from "../format.js";
import { useApi } from "../hooks/useApi.js";
import { PHONE_QUERY, useMediaQuery } from "../hooks/useMediaQuery.js";

// Vitesse du chrono : durée réelle d'une minute de jeu.
const SPEEDS = [
  { label: "×1", ms: 1500 },
  { label: "×2", ms: 750 },
  { label: "×4", ms: 375 },
  { label: "×8", ms: 180 },
];

// Événements qui mettent le match en pause quand ils touchent notre équipe.
const PAUSING = new Set(["injury", "yellow_card", "red_card"]);

// Le match du club dirigé en direct : tableau d'affichage et chrono, événements
// de chaque équipe de son côté, compositions avec la note sur 10 de chaque joueur.
// Sous le tableau, « Plan de jeu » et « Discours » mettent le match en pause et
// ouvrent leur fenêtre ; en pause, on fait aussi les remplacements. En fin de match
// serrée, une pénalité décisive arrête le chrono : c'est le choix crucial.
export default function Match() {
  const { career } = useOutletContext();
  const navigate = useNavigate();
  return (
    <LiveScreen
      calls={CAREER_CALLS}
      empty={(onStarted) => <NoLiveMatch career={career} onStarted={onStarted} />}
      // Fin de journée : les autres matchs se jouent, et le tableau de bord raconte la suite.
      onFinished={(result) => navigate("/", { replace: true, state: { played: result } })}
      handOverText="Le reste du match se joue sans toi : le staff gère le banc. La journée se termine ensuite comme d'habitude."
    />
  );
}

const CAREER_CALLS = {
  get: api.getLive,
  advance: api.advanceLive,
  tactics: api.setLiveTactics,
  talk: api.talkLive,
  decide: api.decideLive,
  substitute: api.substituteLive,
  finish: api.finishLive,
};

// L'écran du match en direct, quel que soit le match : `calls` sont ses appels à l'API
// (ceux de la carrière, ou du match libre), `empty(onStarted)` ce qu'on montre sans match
// en cours. `finish` (« Terminer », ou le bouton du match fini) joue la fin ; sa réponse
// va à `onFinished`, ou s'affiche sans lui. Avec `onDone`, le bouton du match fini
// (`doneLabel`) appelle `onDone` à la place.
export function LiveScreen({ calls, title, empty, onFinished, onDone, doneLabel = "Continuer", handOverText }) {
  const current = useApi(calls.get);
  const [playing, setPlaying] = useState(false);
  const [speed, setSpeed] = useState(1);
  const [notice, setNotice] = useState(null); // pourquoi le match s'est arrêté
  const [busy, setBusy] = useState(false); // une requête est en cours
  const [error, setError] = useState(null);
  const [finishing, setFinishing] = useState(false);
  const phone = useMediaQuery(PHONE_QUERY);
  const [lineupClub, setLineupClub] = useState(null); // téléphone : la composition montrée (la nôtre par défaut)
  const [panel, setPanel] = useState(null); // fenêtre ouverte : "plan", "talk" ou "crunch"
  const confirm = useConfirm();
  const live = current.data;
  const { setData } = current;
  const lastRequest = useRef(0); // durée de la dernière minute demandée au serveur, en ms

  // Avance d'une minute, puis s'arrête sur ce qui mérite une décision.
  const tick = useCallback(async () => {
    if (!live || live.finished || busy) return;
    setBusy(true);
    try {
      const sent = performance.now();
      const next = await calls.advance(1);
      lastRequest.current = performance.now() - sent;
      setData(next);
      const fresh = next.events.slice(live.events.length);
      const mine = fresh.find((e) => e.club_id === next.my_club_id && PAUSING.has(e.type));
      if (next.finished) {
        setPlaying(false);
        setNotice(null);
      } else if (next.crunch) {
        setPlaying(false);
        setNotice("Choix crucial");
      } else if (mine) {
        setPlaying(false);
        setNotice(`${EVENTS[mine.type]} : ${mine.player_name}`);
      } else if (next.minute === next.half_time) {
        setPlaying(false);
        setNotice("Mi-temps");
      }
    } catch (err) {
      setError(err);
      setPlaying(false);
    } finally {
      setBusy(false);
    }
  }, [live, busy, setData, calls]);

  // Le chrono : une minute de jeu à chaque intervalle tant que le match tourne. Le temps
  // de réponse du serveur compte dans l'intervalle : ×8 va vraiment huit fois plus vite.
  useEffect(() => {
    if (!playing || !live || live.finished) return undefined;
    const timer = setTimeout(tick, Math.max(0, SPEEDS[speed].ms - lastRequest.current));
    return () => clearTimeout(timer);
  }, [playing, live, speed, tick]);

  // Une pénalité décisive attend le manager : sa fenêtre s'ouvre (aussi au retour sur
  // la page). Il peut la fermer pour faire un changement, puis la rouvrir.
  const crunchMinute = live?.crunch?.minute;
  useEffect(() => {
    if (crunchMinute !== undefined) setPanel("crunch");
  }, [crunchMinute]);

  // La barre d'espace met en pause et relance, comme le bouton du tableau d'affichage ;
  // pas pendant une saisie, ni quand une fenêtre est ouverte (plan, discours, confirmation),
  // ni quand une décision attend.
  const canToggle = Boolean(live) && !live.finished && !live.crunch && !finishing && panel === null;
  useEffect(() => {
    if (!canToggle) return undefined;
    const onKey = (event) => {
      if (event.code !== "Space" || event.repeat || event.ctrlKey || event.metaKey || event.altKey) return;
      if (event.target.closest?.("input, textarea, select, [contenteditable]")) return;
      if (document.querySelector('[aria-modal="true"]')) return;
      // Sinon l'espace « cliquerait » aussi le bouton qui a le focus, ou ferait défiler.
      event.preventDefault();
      if (playing) {
        setPlaying(false);
      } else {
        setNotice(null);
        setPlaying(true);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [canToggle, playing]);

  async function act(call) {
    setBusy(true);
    setError(null);
    try {
      setData(await call());
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }

  const start = () => {
    if (live.crunch) {
      setPanel("crunch");
      return;
    }
    setNotice(null);
    setPlaying(true);
  };

  async function finish() {
    setFinishing(true);
    setError(null);
    try {
      const result = await calls.finish();
      if (onFinished) {
        onFinished(result);
      } else {
        setData(result);
        setNotice(null);
        setFinishing(false);
      }
    } catch (err) {
      setError(err);
      setFinishing(false);
    }
  }

  // Plan de jeu et discours : le match s'arrête le temps de la décision.
  const openPanel = (kind) => {
    setPlaying(false);
    setPanel(kind);
  };

  const resume = () => {
    setPanel(null);
    start();
  };

  const handOver = () => {
    setPlaying(false);
    confirm.ask({
      eyebrow: "Terminer le match",
      title: "Laisser le staff finir ?",
      text: handOverText,
      confirmLabel: "Terminer le match",
      // La barre d'espace sert à relancer le chrono : tapée par réflexe, elle annule.
      cautious: true,
      onConfirm: finish,
    });
  };

  if (current.loading) return <p className="status">Chargement…</p>;
  if (current.error?.status === 404) return empty(current.setData);
  if (current.error) return <p className="status status--error">{current.error.message}</p>;

  const myId = live.my_club_id;
  const sides = [live.home, live.away];
  const shownSide = sides.find((side) => side.club.id === lineupClub) ?? sides.find((side) => side.club.id === myId) ?? live.home;
  const mySide = sides.find((side) => side.club.id === myId);

  return (
    <div className="live">
      {confirm.dialog}
      <Scoreboard
        live={live}
        title={title}
        doneLabel={doneLabel}
        playing={playing}
        speed={speed}
        setSpeed={setSpeed}
        notice={notice}
        error={error}
        busy={busy}
        finishing={finishing}
        onPlay={start}
        onPause={() => setPlaying(false)}
        onHandOver={handOver}
        onFinish={live.finished && onDone ? onDone : finish}
      />
      <Actions live={live} side={mySide} onOpen={openPanel} />
      <Momentum
        bars={live.momentum}
        slots={live.last_minute}
        halfTime={live.half_time}
        home={live.home.club}
        away={live.away.club}
        myId={myId}
        finished={live.finished}
        events={live.events}
        nameOf={(e) => (e.type === "substitution" ? `${e.other_player_name} entre` : e.player_name)}
      />
      {panel === "plan" && (
        <PlanDialog
          tactics={mySide.tactics}
          busy={busy}
          error={error}
          onChange={(tactics) => act(() => calls.tactics(tactics))}
          resumeLabel={live.minute === 0 ? "Coup d'envoi" : "Reprendre le match"}
          onClose={() => setPanel(null)}
          onResume={resume}
        />
      )}
      {panel === "crunch" && (
        <CrunchDialog
          live={live}
          side={mySide}
          busy={busy}
          error={error}
          onDecide={(option) => act(() => calls.decide(option))}
          onClose={() => setPanel(null)}
          onResume={resume}
        />
      )}
      {panel === "talk" && (
        <TalkDialog
          live={live}
          side={mySide}
          busy={busy}
          error={error}
          onTalk={(key) => act(() => calls.talk(key))}
          resumeLabel={live.minute === 0 ? "Coup d'envoi" : "Reprendre le match"}
          onClose={() => setPanel(null)}
          onResume={resume}
        />
      )}
      <div className="live__grid fill">
        {phone ? (
          // Téléphone : un seul fil des faits de jeu, puis la composition d'une équipe au choix.
          <>
            <Feed sides={sides} events={live.events} />
            <div className="chips live__teams" role="group" aria-label="Composition">
              {sides.map((side) => (
                <button
                  key={side.club.id}
                  type="button"
                  className="chip with-crest"
                  aria-pressed={shownSide.club.id === side.club.id}
                  onClick={() => setLineupClub(side.club.id)}
                >
                  <ClubCrest name={side.club.name} size={18} />
                  {side.club.id === myId ? "Notre XV" : side.club.name}
                </button>
              ))}
            </div>
            <Lineup
              key={shownSide.club.id}
              side={shownSide}
              mine={shownSide.club.id === myId}
              paused={!playing && !live.finished}
              busy={busy}
              onSubstitute={(out, into) => act(() => calls.substitute(out, into))}
            />
          </>
        ) : (
          <>
            {sides.map((side) => (
              <Events key={side.club.id} side={side} events={live.events} mine={side.club.id === myId} />
            ))}
            {sides.map((side) => (
              <Lineup
                key={side.club.id}
                side={side}
                mine={side.club.id === myId}
                paused={!playing && !live.finished}
                busy={busy}
                onSubstitute={(out, into) => act(() => calls.substitute(out, into))}
              />
            ))}
          </>
        )}
      </div>
    </div>
  );
}

// --- Pas de match en cours ----------------------------------------------------------------

function NoLiveMatch({ career, onStarted }) {
  if (career.kind === "nation") return <NoLiveTest />;
  return <NoLiveClubMatch career={career} onStarted={onStarted} />;
}

// Sélectionneur : le match se lance depuis son tableau de bord, le jour où il tombe.
function NoLiveTest() {
  return (
    <section className="hero">
      <p className="eyebrow">Match en direct</p>
      <h1 className="hero__title">Aucun match en cours</h1>
      <p className="hero__sub">Le match de la sélection se lance le jour où il tombe</p>
      <div className="hero__actions">
        <Link to="/" className="button button--primary">
          Retour à la sélection
        </Link>
      </div>
    </section>
  );
}

function NoLiveClubMatch({ career, onStarted }) {
  const season = useApi(useCallback(api.getCurrentSeason, []));
  const affairs = useApi(useCallback(api.getAffairs, []));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);

  if (season.loading) return <p className="status">Chargement…</p>;
  if (season.error) return <p className="status status--error">{season.error.message}</p>;
  const next = season.data.next_match ?? season.data.next_matchday;
  const myMatch = next?.matches.find((m) => m.home.id === career.club_id || m.away.id === career.club_id);
  const pending = affairs.data?.pending?.length ?? 0;

  async function start() {
    setBusy(true);
    setError(null);
    try {
      onStarted(await api.startLive());
    } catch (err) {
      setError(err);
      setBusy(false);
    }
  }

  return (
    <section className="hero">
      <p className="eyebrow">Match en direct</p>
      {myMatch ? (
        <>
          <div className="hero__club">
            <ClubCrest name={myMatch.home.name} size={56} />
            <h1 className="hero__title">
              {myMatch.home.name} – {myMatch.away.name}
            </h1>
            <ClubCrest name={myMatch.away.name} size={56} />
          </div>
          <p className="hero__sub">
            {matchdayTitle(next)} · {formatLongDate(next.date)}
          </p>
          <div className="hero__actions">
            {pending > 0 ? (
              <Link to="/" className="button button--primary">
                {pending} affaire{pending > 1 ? "s" : ""} à régler d'abord
              </Link>
            ) : (
              <button type="button" className="button button--primary" disabled={busy} onClick={start}>
                {busy ? "Coup d'envoi…" : "Lancer le match"}
              </button>
            )}
            <span className="muted">
              Le chrono défile à la vitesse que tu choisis ; mets en pause pour changer la tactique ou faire un
              remplacement.
            </span>
          </div>
          {error && <p className="status--error" style={{ margin: 0 }}>{error.message}</p>}
        </>
      ) : (
        <>
          <h1 className="hero__title">{season.data.phase === "finished" ? "Saison terminée" : "Tu ne joues pas"}</h1>
          <p className="hero__sub">
            {season.data.phase === "finished"
              ? "Lance la saison suivante depuis le tableau de bord."
              : "Ton club n'est pas concerné par la prochaine journée."}
          </p>
          <div className="hero__actions">
            <Link to="/" className="button">
              Tableau de bord
            </Link>
          </div>
        </>
      )}
    </section>
  );
}

// --- Tableau d'affichage ----------------------------------------------------------------

function Scoreboard({
  live,
  title,
  doneLabel,
  playing,
  speed,
  setSpeed,
  notice,
  error,
  busy,
  finishing,
  onPlay,
  onPause,
  onHandOver,
  onFinish,
}) {
  const label = title ?? matchdayTitle(live);
  return (
    <header className="scoreboard card">
      <Team side={live.home} mine={live.home.club.id === live.my_club_id} />
      <span className="scoreboard__score scoreboard__score--home">{live.home.score}</span>
      <div className="scoreboard__center">
        <Clock minute={live.minute} running={playing} interval={SPEEDS[speed].ms} />
        <span className="scoreboard__period">{period(live)}</span>
        <span className="muted scoreboard__meta">
          {label}
          {live.derby && ` · ${live.derby}`} · {formatLongDate(live.date)}
          {live.neutral && " · terrain neutre"}
        </span>
        <span className="muted scoreboard__weather" title={WEATHER[live.weather].scope}>
          <WeatherIcon weather={live.weather} />
          {WEATHER[live.weather].label}
          {live.crowd && (
            <span title={crowdEffect(live.crowd)}>
              {" · "}
              {formatCrowd(live.crowd)}
            </span>
          )}
        </span>
        {live.crowd?.mood && (
          <span
            className={`scoreboard__mood scoreboard__mood--${live.crowd.mood}${live.home.club.id === live.my_club_id ? " scoreboard__mood--ours" : ""}`}
            title={crowdEffect(live.crowd)}
          >
            {CROWD_MOODS[live.crowd.mood]} · {live.home.club.name}
          </span>
        )}
        {live.home.shootout !== null && (
          <span className="scoreboard__shootout num">
            Tirs au but {live.home.shootout} – {live.away.shootout}
          </span>
        )}
        <div className="scoreboard__controls">
          {live.finished ? (
            <button type="button" className="button button--primary" disabled={finishing} onClick={onFinish}>
              {finishing ? "Fin de journée…" : doneLabel}
            </button>
          ) : (
            <>
              <button
                type="button"
                className="button button--primary scoreboard__play"
                title="Barre d'espace"
                onClick={playing ? onPause : onPlay}
              >
                {playing ? "Pause" : live.crunch ? "Choix crucial" : live.minute === 0 ? "Coup d'envoi" : "Reprendre"}
              </button>
              <div className="chips" role="group" aria-label="Vitesse du chrono">
                {SPEEDS.map((s, index) => (
                  <button
                    key={s.label}
                    type="button"
                    className="chip chip--small"
                    aria-pressed={speed === index}
                    onClick={() => setSpeed(index)}
                  >
                    {s.label}
                  </button>
                ))}
              </div>
              <button type="button" className="button button--small" disabled={busy || finishing} onClick={onHandOver}>
                Terminer
              </button>
            </>
          )}
        </div>
        {/* Toujours là, invisible sans message : le tableau garde sa hauteur. */}
        <span
          className={`scoreboard__notice${error ? " status--error" : ""}${notice || error ? "" : " scoreboard__notice--empty"}`}
          aria-hidden={notice || error ? undefined : "true"}
        >
          {error ? error.message : notice ? `Pause · ${notice}` : "\u00a0"}
        </span>
      </div>
      <span className="scoreboard__score">{live.away.score}</span>
      <Team side={live.away} mine={live.away.club.id === live.my_club_id} away />
    </header>
  );
}

function Team({ side, mine, away = false }) {
  return (
    <div className={`scoreboard__team${away ? " scoreboard__team--away" : ""}`}>
      <ClubCrest name={side.club.name} size={44} />
      <span className={`scoreboard__name${mine ? " scoreboard__name--mine" : ""}`}>{side.club.name}</span>
      <span className="muted">
        {side.tries} essai{side.tries > 1 ? "s" : ""}
        {side.missing > 0 && ` · à ${15 - side.missing}`}
      </span>
    </div>
  );
}

// Période affichée sous le chrono.
function period(live) {
  if (live.finished) return live.home.shootout !== null ? "Terminé aux tirs au but" : "Terminé";
  if (live.minute === 0) return "Avant le coup d'envoi";
  if (live.extra_time) return live.minute <= 90 ? "Prolongation · 1re période" : "Prolongation · 2e période";
  if (live.minute === live.half_time) return "Mi-temps";
  return live.minute < live.half_time ? "1re mi-temps" : "2e mi-temps";
}

// Le chrono « MM:SS » : les secondes défilent entre deux minutes de jeu, au rythme choisi.
function Clock({ minute, running, interval }) {
  const [seconds, setSeconds] = useState(0);
  const startRef = useRef(null);
  useEffect(() => {
    setSeconds(0);
    startRef.current = performance.now();
    if (!running) return undefined;
    let frame;
    const loop = () => {
      const elapsed = performance.now() - startRef.current;
      setSeconds(Math.min(59, Math.floor((elapsed / interval) * 60)));
      frame = requestAnimationFrame(loop);
    };
    frame = requestAnimationFrame(loop);
    return () => cancelAnimationFrame(frame);
  }, [minute, running, interval]);
  const pad = (n) => String(n).padStart(2, "0");
  return (
    <span className="scoreboard__clock" aria-live="off">
      {pad(minute)}:{pad(running ? seconds : 0)}
    </span>
  );
}

// --- Événements d'une équipe --------------------------------------------------------------

function Events({ side, events, mine }) {
  const ours = events.filter((e) => e.club_id === side.club.id).reverse();
  return (
    <section className={`card live-events${mine ? " live-events--mine" : ""}`}>
      <div className="live-card__head">
        <span className="eyebrow with-crest">
          <ClubCrest name={side.club.name} size={18} />
          {side.club.name}
        </span>
        <span className="muted">{ours.length ? `${ours.length} fait${ours.length > 1 ? "s" : ""} de jeu` : "Rien à signaler"}</span>
      </div>
      <ul className="live-events__list">
        {ours.map((e, index) => (
          <EventRow key={`${e.minute}-${e.type}-${e.player_id}-${index}`} event={e} />
        ))}
      </ul>
    </section>
  );
}

// Téléphone : les faits de jeu des deux équipes dans une seule carte, dans l'ordre du
// match, ceux de l'équipe à domicile calés à gauche, ceux de l'extérieur à droite. La
// liste montre les dix derniers et reste calée en bas ; on remonte pour les précédents.
function Feed({ sides, events }) {
  const [home, away] = sides;
  const listRef = useRef(null);
  useEffect(() => {
    const list = listRef.current;
    if (list) list.scrollTop = list.scrollHeight;
  }, [events.length]);
  return (
    <section className="card live-events live-feed">
      <div className="live-card__head">
        <span className="eyebrow with-crest">
          <ClubCrest name={home.club.name} size={18} />
          {home.club.name}
        </span>
        <span className="eyebrow with-crest live-feed__away">
          {away.club.name}
          <ClubCrest name={away.club.name} size={18} />
        </span>
      </div>
      <ul className="live-events__list live-feed__list" ref={listRef}>
        {events.length === 0 && <li className="live-event live-event--none muted">Rien à signaler</li>}
        {events.map((e, index) => (
          <EventRow key={`${e.minute}-${e.type}-${e.player_id}-${index}`} event={e} away={e.club_id === away.club.id} />
        ))}
      </ul>
    </section>
  );
}

// Une ligne de fait de jeu : minute, repère, libellé et joueur, points marqués.
function EventRow({ event: e, away = false }) {
  return (
    <li className={`live-event live-event--${e.type}${away ? " live-event--away" : ""}`}>
      <span className="live-event__minute num">{e.minute}'</span>
      <Mark type={e.type} />
      <span className="live-event__text">
        <span className="live-event__label">{EVENTS[e.type]}</span>
        {e.type === "substitution" ? (
          <span className="muted">
            {" "}
            {e.other_player_name} entre, {e.player_name} sort
          </span>
        ) : (
          e.player_name && <span className="muted"> · {e.player_name}</span>
        )}
        {e.points > 0 && <span className="live-event__points num">+{e.points}</span>}
      </span>
    </li>
  );
}

// Repère visuel d'un événement : plein pour les points, carton pour les cartons, croix pour la blessure.
function Mark({ type }) {
  if (type === "yellow_card" || type === "red_card") return <span className={`card-mark card-mark--${type}`} aria-hidden="true" />;
  if (type === "try") return <span className="live-mark live-mark--try" aria-hidden="true" />;
  if (type === "penalty_goal" || type === "drop_goal" || type === "conversion" || type === "shootout_goal") {
    return <span className="live-mark live-mark--kick" aria-hidden="true" />;
  }
  if (type === "injury") return <span className="live-mark live-mark--injury" aria-hidden="true">+</span>;
  if (type === "substitution") return <span className="live-mark live-mark--sub" aria-hidden="true">⇄</span>;
  return <span className="live-mark live-mark--miss" aria-hidden="true" />;
}

// --- Composition d'une équipe --------------------------------------------------------------

// Colonnes de la vue « Statistiques » d'une composition.
const LIVE_STATS = ["carries", "tackles", "missed_tackles", "line_breaks"];

function Lineup({ side, mine, paused, busy, onSubstitute }) {
  const [outgoing, setOutgoing] = useState(null); // joueur qu'on va remplacer
  const [stats, setStats] = useState(false); // statistiques à la place de l'énergie
  const columns = stats ? 4 + LIVE_STATS.length : 5;
  const canManage = mine && paused && !busy;
  const byNumber = Object.fromEntries(side.players.filter((p) => p.slot_number !== null).map((p) => [p.slot_number, p]));
  const slots = Array.from({ length: 15 }, (_, i) => i + 1).map((number) => byNumber[number] ?? null);
  const bench = side.players.filter((p) => p.slot_number === null);
  const outgoingPlayer = outgoing ? side.players.find((p) => p.id === outgoing) : null;

  useEffect(() => {
    if (!paused) setOutgoing(null);
  }, [paused]);

  const substitute = (incoming) => {
    if (!outgoing) return;
    onSubstitute(outgoing, incoming.id);
    setOutgoing(null);
  };

  return (
    <section className={`card live-lineup${mine ? " live-lineup--mine" : ""}`}>
      <div className="live-card__head">
        <span className="eyebrow">{mine ? "Notre XV" : side.club.name}</span>
        <span className="muted live-lineup__meta">
          {side.substitutions_left} remplacement{side.substitutions_left > 1 ? "s" : ""} restant
          {side.substitutions_left > 1 ? "s" : ""}
          <button type="button" className="chip chip--small" aria-pressed={stats} onClick={() => setStats(!stats)}>
            Statistiques
          </button>
        </span>
      </div>

      {mine && (
        <p className="live-lineup__hint muted">
          {!paused
            ? "Mets le match en pause pour faire un remplacement."
            : outgoingPlayer
              ? `${outgoingPlayer.last_name} va sortir : choisis qui entre sur le banc.`
              : "Clique sur un joueur du terrain pour le remplacer."}
        </p>
      )}

      <div className="live-lineup__scroll">
      <table className="table live-table">
        <thead>
          <tr>
            <th scope="col" className="left">N°</th>
            <th scope="col" className="left">Joueur</th>
            <th scope="col" className="left">Poste</th>
            {stats ? (
              LIVE_STATS.map((key) => {
                const { label, short } = MATCH_STATS.find((stat) => stat.key === key);
                return (
                  <th key={key} scope="col" title={label}>
                    {short}
                  </th>
                );
              })
            ) : (
              <th scope="col" title="Énergie restante">Énergie</th>
            )}
            <th scope="col" title="Note du match sur 10">Note</th>
          </tr>
        </thead>
        <tbody>
          {slots.map((player, index) => (
            <PlayerRow
              key={player ? player.id : `empty-${index + 1}`}
              number={index + 1}
              player={player}
              kickerId={side.kicker_id}
              captainId={side.captain_id}
              stats={stats}
              columns={columns}
              selectable={canManage && player?.status === "field"}
              selected={player?.id === outgoing}
              onSelect={() => setOutgoing(player.id === outgoing ? null : player.id)}
            />
          ))}
          <tr>
            <th colSpan={columns} className="table__group">
              Banc
            </th>
          </tr>
          {bench.map((player) => (
            <PlayerRow
              key={player.id}
              number={player.number}
              player={player}
              kickerId={side.kicker_id}
              captainId={side.captain_id}
              stats={stats}
              columns={columns}
              bench
              incoming={Boolean(canManage && outgoing && player.status === "bench")}
              onSelect={() => substitute(player)}
            />
          ))}
        </tbody>
      </table>
      </div>
    </section>
  );
}

function PlayerRow({
  number,
  player,
  kickerId,
  captainId,
  stats,
  columns,
  bench = false,
  selectable = false,
  selected = false,
  incoming = false,
  onSelect,
}) {
  if (!player) {
    return (
      <tr className="live-row live-row--empty">
        <td className="left jersey">{number}</td>
        <td className="left muted" colSpan={columns - 1}>
          Place vide
        </td>
      </tr>
    );
  }
  const clickable = selectable || incoming;
  const classes = [
    "live-row",
    clickable ? "table__row--clickable" : "",
    selected ? "table__row--selected" : "",
    bench && player.status !== "bench" ? "table__row--bench" : "",
    player.status === "sin_bin" ? "live-row--absent" : "",
  ]
    .filter(Boolean)
    .join(" ");
  return (
    <tr
      className={classes}
      tabIndex={clickable ? 0 : undefined}
      onClick={clickable ? onSelect : undefined}
      onKeyDown={
        clickable
          ? (event) => {
              if (event.key === "Enter" || event.key === " ") {
                event.preventDefault();
                onSelect();
              }
            }
          : undefined
      }
    >
      <td className="left jersey">{number}</td>
      <td className="left">
        <span className="live-row__name">
          {player.last_name}
          {player.yellow > 0 && !player.red && <span className="card-mark card-mark--yellow_card" title="Carton jaune" />}
          {player.red && <span className="card-mark card-mark--red_card" title="Carton rouge" />}
          {player.id === captainId && (
            <span className="live-row__captain" title="Capitaine : moins de cartons, l'équipe un peu plus sereine tant qu'il est sur le terrain">
              C
            </span>
          )}
          {player.id === kickerId && <span className="muted live-row__kicker" title="Buteur">B</span>}
        </span>
        <Status player={player} incoming={incoming} />
      </td>
      <td className="left muted">{POSITION_SHORT[player.slot ?? player.position]}</td>
      {stats ? (
        LIVE_STATS.map((key) => (
          <td key={key} className={`num${!player.stats || player.stats[key] === 0 ? " muted" : ""}`}>
            {player.stats ? player.stats[key] : "–"}
          </td>
        ))
      ) : (
        <td>
          <Energy value={player.energy} frozen={player.slot_number === null} />
        </td>
      )}
      <td className={`note${player.rating !== null && player.rating >= 7.5 ? " cell--strong" : ""}`}>
        {player.rating !== null ? formatNote(player.rating) : <span className="muted">–</span>}
      </td>
    </tr>
  );
}

// Sous le nom : ce qui compte pour la décision (sorti, blessé, exclu, fatigué, entré à…).
function Status({ player, incoming }) {
  if (incoming) return <span className="live-row__status live-row__status--accent">Faire entrer</span>;
  switch (player.status) {
    case "sin_bin":
      return <span className="live-row__status">Banc des pénalités · retour {player.back_at}'</span>;
    case "sent_off":
      return <span className="live-row__status">Exclu {player.until}'</span>;
    case "injured":
      return <span className="live-row__status">Blessé · sorti {player.until}'</span>;
    case "replaced":
      return <span className="live-row__status">Remplacé {player.until}'</span>;
    case "bench":
      return <span className="live-row__status">{POSITIONS[player.position].label}</span>;
    default: {
      const parts = [];
      if (player.since > 0) parts.push(`entré ${player.since}'`);
      return parts.length ? <span className="live-row__status">{parts.join(" · ")}</span> : null;
    }
  }
}

// Barre d'énergie verticale, qui se vide au fil du match ; en accent sous 30 %.
// `frozen` : joueur hors du terrain (sorti, ou pas encore entré).
function Energy({ value, frozen }) {
  const percent = Math.round(value * 100);
  const low = value < 0.3;
  return (
    <span className={`energy${frozen ? " energy--frozen" : ""}`} title={`Énergie : ${percent} %`}>
      <span className="energy__bar" role="img" aria-label={`Énergie ${percent} %`}>
        <span className={`energy__fill${low ? " energy__fill--low" : ""}`} style={{ height: `${percent}%` }} />
      </span>
      <span className="energy__value num">{percent}</span>
    </span>
  );
}

// --- Plan de jeu et discours --------------------------------------------------------------

const percent = (value) => `${value > 0 ? "+" : value < 0 ? "−" : ""}${Math.abs(Math.round(value * 100))} %`;

// Nervosité de l'équipe, en un mot (elle pèse sur les cartons).
function temper(heat) {
  if (heat >= 0.6) return "Survoltée";
  if (heat >= 0.2) return "Nerveuse";
  if (heat <= -0.2) return "Sereine";
  return null;
}

// Sous le tableau d'affichage : le plan de jeu en cours, le discours possible, et
// l'élan que les discours ont donné à l'équipe.
function Actions({ live, side, onOpen }) {
  const plan = TACTICS.map((axis) => axis.options.find((o) => o.key === side.tactics[axis.key])?.label).join(" · ");
  const { moment, next_at: nextAt } = live.talk;
  const locker = moment === "kickoff" || moment === "break";
  const mood = temper(side.heat);
  const lastTalk = side.talks.at(-1);
  return (
    <div className="live-actions">
      <button type="button" className="live-action" disabled={live.finished} onClick={() => onOpen("plan")}>
        <span className="live-action__label">Plan de jeu</span>
        <span className="live-action__value">{plan}</span>
      </button>
      <button
        type="button"
        className={`live-action${locker ? " live-action--due" : ""}`}
        disabled={live.finished || !moment}
        onClick={() => onOpen("talk")}
      >
        <span className="live-action__label">Discours</span>
        <span className="live-action__value">
          {moment
            ? TALK_MOMENTS[moment]
            : live.finished
              ? "Match terminé"
              : nextAt
                ? `Possible à la ${nextAt}'`
                : "Pas maintenant"}
        </span>
      </button>
      <Spirit spirit={side.spirit} mood={mood} lastTalk={lastTalk} />
    </div>
  );
}

// L'élan va de −12 % à +15 % : la jauge part du centre, à droite quand il porte, à
// gauche (en rouge) quand il pèse. Sous elle, le dernier discours.
const SPIRIT_SCALE = 0.15;

function Spirit({ spirit, mood, lastTalk }) {
  const flat = Math.abs(spirit) < 0.005;
  const down = spirit < 0 && !flat;
  const width = flat ? 0 : Math.min(50, (Math.abs(spirit) / SPIRIT_SCALE) * 50);
  const note = lastTalk ? `${TALKS[lastTalk.key].label} · ${lastTalk.minute}'` : "Aucun discours";
  return (
    <div className="live-actions__spirit" title="L'élan multiplie les notes collectives et s'estompe au fil des minutes">
      <div className="spirit__head">
        <span className="live-action__label">
          Élan{mood && <span className="spirit__mood"> · {mood}</span>}
        </span>
        <span className={`spirit__value num${down ? " spirit__value--down" : ""}`}>{flat ? "–" : percent(spirit)}</span>
      </div>
      <span className="spirit__track" aria-hidden="true">
        <span
          className={`spirit__fill${down ? " spirit__fill--down" : ""}`}
          style={down ? { right: "50%", width: `${width}%` } : { left: "50%", width: `${width}%` }}
        />
      </span>
      <span className="muted spirit__note" title={note}>
        {note}
      </span>
    </div>
  );
}

// Plan de jeu : les trois curseurs de la tactique, en pastilles (changement immédiat).
function PlanDialog({ tactics, busy, error, resumeLabel, onChange, onClose, onResume }) {
  return (
    <Modal compact className="modal--dialog live-dialog" onClose={onClose}>
      <div>
        <p className="eyebrow">Match en pause</p>
        <h2 className="confirm__title">Plan de jeu</h2>
      </div>
      {TACTICS.map((axis) => {
        const current = axis.options.find((o) => o.key === tactics[axis.key]);
        return (
          <div key={axis.key} className="plan__axis">
            <span className="tactics__label">{axis.label}</span>
            <div className="chips" role="group" aria-label={axis.label}>
              {axis.options.map((option) => (
                <button
                  key={option.key}
                  type="button"
                  className="chip"
                  aria-pressed={option.key === current?.key}
                  disabled={busy}
                  onClick={() => option.key !== current?.key && onChange({ [axis.key]: option.key })}
                >
                  {option.label}
                </button>
              ))}
            </div>
            <span className="muted plan__scope">{current?.scope}</span>
          </div>
        );
      })}
      {error && <p className="status--error" style={{ margin: 0 }}>{error.message}</p>}
      <div className="confirm__actions">
        <button type="button" className="button" onClick={onClose}>
          Fermer
        </button>
        <button type="button" className="button button--primary" disabled={busy} autoFocus onClick={onResume}>
          {resumeLabel}
        </button>
      </div>
    </Modal>
  );
}

// Chance qu'un discours porte, et risque qu'il se retourne, en mots.
const chance = (value) => (value >= 0.55 ? "Bonnes chances" : value >= 0.4 ? "Une chance sur deux" : "Peu de chances");
const risk = (value) => (value < 0.1 ? "sans risque" : value < 0.3 ? "risqué" : "quitte ou double");

// Discours : au vestiaire (avant le coup d'envoi, à la pause) ou du bord du terrain.
// Une fois le discours tenu, la fenêtre montre son issue.
function TalkDialog({ live, side, busy, error, resumeLabel, onTalk, onClose, onResume }) {
  const [spokenAt, setSpokenAt] = useState(null); // nombre de discours avant le nôtre
  const heard = spokenAt !== null ? side.talks[spokenAt] : null;
  const { moment, options } = live.talk;
  const talk = (key) => {
    setSpokenAt(side.talks.length);
    onTalk(key);
  };
  return (
    <Modal compact className="modal--dialog live-dialog" onClose={busy ? () => {} : onClose}>
      <div>
        <p className="eyebrow">{heard ? `Discours · ${heard.minute}'` : TALK_MOMENTS[moment] ?? "Discours"}</p>
        <h2 className="confirm__title">{heard ? TALKS[heard.key].label : "Parler à l'équipe"}</h2>
      </div>

      {heard ? (
        <div className={`talk__outcome talk__outcome--${heard.outcome}`}>
          <span className="talk__verdict">{TALK_OUTCOMES[heard.outcome]}</span>
          <p className="confirm__text">{TALKS[heard.key][heard.outcome]}</p>
          <span className="muted talk__effect">
            {Math.abs(heard.spirit) >= 0.005 ? `Élan ${percent(heard.spirit)}` : "Élan inchangé"}
            {heard.heat >= 0.1 && " · les nerfs s'échauffent"}
            {heard.heat <= -0.1 && " · les esprits se calment"}
          </span>
        </div>
      ) : spokenAt !== null && !error ? (
        <p className="muted">Les joueurs écoutent…</p>
      ) : (
        <ul className="talk__options">
          {options.map((option) => (
            <li key={option.key}>
              <button type="button" className="talk__option" disabled={busy || !moment} onClick={() => talk(option.key)}>
                <span className="talk__name">{TALKS[option.key].label}</span>
                <span className="muted talk__scope">{TALKS[option.key].scope}</span>
                <span className={`talk__odds${option.backfire >= 0.3 ? " talk__odds--risky" : ""}`}>
                  {chance(option.success)} · {risk(option.backfire)}
                </span>
              </button>
            </li>
          ))}
        </ul>
      )}

      {error && <p className="status--error" style={{ margin: 0 }}>{error.message}</p>}
      <div className="confirm__actions">
        <button type="button" className="button" disabled={busy} onClick={onClose}>
          {heard ? "Fermer" : "Ne rien dire"}
        </button>
        {heard && (
          <button type="button" className="button button--primary" autoFocus onClick={onResume}>
            {resumeLabel}
          </button>
        )}
      </div>
    </Modal>
  );
}

// --- Choix crucial ------------------------------------------------------------------------

const points = (n) => `${n} pt${n > 1 ? "s" : ""}`;

// Ce que `scored` points font au score, quand on a `margin` points d'avance.
function swing(margin, scored) {
  const after = margin + scored;
  if (margin > 0) return after >= 8 ? "deux scores d'avance" : "creuse l'écart";
  if (after === 0) return "égalise";
  return after > 0 ? "passe devant" : "reste derrière";
}

// Où en est le match : l'écart et le temps qui reste.
function situation(margin, left) {
  const score = margin === 0 ? "À égalité" : margin > 0 ? `Devant de ${points(margin)}` : `Menés de ${points(-margin)}`;
  const time = left <= 0 ? "dernière action du match" : `${left} minute${left > 1 ? "s" : ""} à jouer`;
  return `${score}, ${time}`;
}

// La pénalité d'une fin de match serrée : les perches, la touche, la mêlée ou la jouer
// vite, chacune avec ses chances et ce qu'elle fait au score. Une fois le choix fait, la
// fenêtre montre ce qu'il a donné.
function CrunchDialog({ live, side, busy, error, onDecide, onClose, onResume }) {
  const [choice, setChoice] = useState(null); // { option, from } : l'option et les événements d'avant
  const other = side === live.home ? live.away : live.home;
  const fresh = choice ? live.events.slice(choice.from) : [];
  const done = choice !== null && !live.crunch && !busy;
  const crunch = live.crunch;
  const margin = side.score - other.score;
  const kicker = side.players.find((p) => p.id === side.kicker_id);
  const decide = (option) => {
    setChoice({ option, from: live.events.length });
    onDecide(option);
  };

  if (done) {
    const scored = fresh.find((e) => e.type === "try" || e.type === "penalty_goal");
    const conversion = fresh.find((e) => e.type === "conversion" || e.type === "conversion_missed");
    const verdict = scored?.type === "try" ? "Essai !" : scored ? "Les 3 points" : "Raté";
    let text = CRUNCH_OPTIONS[choice.option].missed;
    if (scored?.type === "try") {
      text = `${scored.player_name} aplatit. ${conversion?.type === "conversion" ? "Transformé par" : "Transformation manquée par"} ${conversion?.player_name}.`;
    } else if (scored) {
      text = `${scored.player_name} passe la pénalité.`;
    }
    const after = side.score - other.score;
    return (
      <Modal compact className="modal--dialog live-dialog" onClose={onClose}>
        <div>
          <p className="eyebrow">Choix crucial · {fresh[0]?.minute ?? live.minute}'</p>
          <h2 className="confirm__title">{CRUNCH_OPTIONS[choice.option].label}</h2>
        </div>
        <div className={`talk__outcome talk__outcome--${scored ? "lifted" : "backfired"}`}>
          <span className="talk__verdict">{verdict}</span>
          <p className="confirm__text">{text}</p>
          <span className="muted talk__effect">
            {side.club.name} {side.score} – {other.score} {other.club.name}
            {live.finished ? " · coup de sifflet final" : live.extra_time && after === 0 ? " · prolongation" : ""}
          </span>
        </div>
        <div className="confirm__actions">
          {live.finished ? (
            <button type="button" className="button button--primary" autoFocus onClick={onClose}>
              Fermer
            </button>
          ) : (
            <button type="button" className="button button--primary" autoFocus onClick={onResume}>
              Reprendre le match
            </button>
          )}
        </div>
      </Modal>
    );
  }

  return (
    <Modal compact className="modal--dialog live-dialog" onClose={busy ? () => {} : onClose}>
      <div>
        <p className="eyebrow">
          Choix crucial{live.derby && ` · ${live.derby}`} · {crunch?.minute ?? live.minute}'
        </p>
        <h2 className="confirm__title">Pénalité pour nous</h2>
      </div>
      <p className="crunch__situation">{situation(margin, live.last_minute - live.minute)}</p>
      {choice !== null && !error ? (
        <p className="muted">Le ballon est posé…</p>
      ) : (
        <ul className="talk__options">
          {(crunch?.options ?? []).map((option) => {
            const kick = option.key === "kick";
            const outcome = kick
              ? `${points(3)} · ${swing(margin, 3)}`
              : swing(margin, 5) === swing(margin, 7)
                ? `${points(5)} ou 7 · ${swing(margin, 5)}`
                : `${points(5)} · ${swing(margin, 5)}, ${swing(margin, 7)} si transformé`;
            return (
              <li key={option.key}>
                <button type="button" className="talk__option" disabled={busy} onClick={() => decide(option.key)}>
                  <span className="talk__name">{CRUNCH_OPTIONS[option.key].label}</span>
                  <span className="muted talk__scope">
                    {CRUNCH_OPTIONS[option.key].scope} · {outcome}
                  </span>
                  <span className="talk__odds">
                    <span className="crunch__chance num">{Math.round(option.success * 100)} %</span>
                    {kick ? "de réussite" : "d'essai"}
                  </span>
                </button>
              </li>
            );
          })}
        </ul>
      )}
      {crunch && kicker && (
        <span className="muted plan__scope">
          Buteur : {kicker.name} · transformation {Math.round(crunch.conversion * 100)} %. Fermer la fenêtre laisse le
          temps d'un changement.
        </span>
      )}
      {error && <p className="status--error" style={{ margin: 0 }}>{error.message}</p>}
      <div className="confirm__actions">
        <button type="button" className="button" disabled={busy} onClick={onClose}>
          Faire un changement
        </button>
      </div>
    </Modal>
  );
}
