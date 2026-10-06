import { useCallback, useEffect, useRef, useState } from "react";
import { Link, useNavigate, useOutletContext } from "react-router-dom";

import { api } from "../api.js";
import ClubCrest from "../components/ClubCrest.jsx";
import { useConfirm } from "../components/ConfirmDialog.jsx";
import {
  EVENTS,
  POSITION_SHORT,
  POSITIONS,
  STAGES,
  TACTICS,
  formatLongDate,
  formatNote,
} from "../format.js";
import { useApi } from "../hooks/useApi.js";

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
// En pause, on change la tactique et on fait des remplacements.
export default function Match() {
  const { career } = useOutletContext();
  const navigate = useNavigate();
  const current = useApi(useCallback(api.getLive, []));
  const [playing, setPlaying] = useState(false);
  const [speed, setSpeed] = useState(1);
  const [notice, setNotice] = useState(null); // pourquoi le match s'est arrêté
  const [busy, setBusy] = useState(false); // une requête est en cours
  const [error, setError] = useState(null);
  const [finishing, setFinishing] = useState(false);
  const confirm = useConfirm();
  const live = current.data;
  const { setData } = current;

  // Avance d'une minute, puis s'arrête sur ce qui mérite une décision.
  const tick = useCallback(async () => {
    if (!live || live.finished || busy) return;
    setBusy(true);
    try {
      const next = await api.advanceLive(1);
      setData(next);
      const fresh = next.events.slice(live.events.length);
      const mine = fresh.find((e) => e.club_id === next.my_club_id && PAUSING.has(e.type));
      if (next.finished) {
        setPlaying(false);
        setNotice(null);
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
  }, [live, busy, setData]);

  // Le chrono : une minute de jeu à chaque intervalle tant que le match tourne.
  useEffect(() => {
    if (!playing || !live || live.finished) return undefined;
    const timer = setTimeout(tick, SPEEDS[speed].ms);
    return () => clearTimeout(timer);
  }, [playing, live, speed, tick]);

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
    setNotice(null);
    setPlaying(true);
  };

  // Fin de journée : les autres matchs se jouent, et le tableau de bord raconte la suite.
  async function finish() {
    setFinishing(true);
    setError(null);
    try {
      const result = await api.finishLive();
      navigate("/", { replace: true, state: { played: result } });
    } catch (err) {
      setError(err);
      setFinishing(false);
    }
  }

  const handOver = () => {
    setPlaying(false);
    confirm.ask({
      eyebrow: "Terminer le match",
      title: "Laisser le staff finir ?",
      text: "Le reste du match se joue sans toi : le staff gère le banc. La journée se termine ensuite comme d'habitude.",
      confirmLabel: "Terminer le match",
      onConfirm: finish,
    });
  };

  if (current.loading) return <p className="status">Chargement…</p>;
  if (current.error?.status === 404) return <NoLiveMatch career={career} onStarted={current.setData} />;
  if (current.error) return <p className="status status--error">{current.error.message}</p>;

  const myId = live.my_club_id;
  const sides = [live.home, live.away];

  return (
    <div className="live">
      {confirm.dialog}
      <Scoreboard
        live={live}
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
        onFinish={finish}
      />
      <div className="live__grid fill">
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
            onTactics={(tactics) => act(() => api.setLiveTactics(tactics))}
            onSubstitute={(out, into) => act(() => api.substituteLive(out, into))}
          />
        ))}
      </div>
    </div>
  );
}

// --- Pas de match en cours ----------------------------------------------------------------

function NoLiveMatch({ career, onStarted }) {
  const season = useApi(useCallback(api.getCurrentSeason, []));
  const affairs = useApi(useCallback(api.getAffairs, []));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);

  if (season.loading) return <p className="status">Chargement…</p>;
  if (season.error) return <p className="status status--error">{season.error.message}</p>;
  const next = season.data.next_matchday;
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
            {next.stage === "regular" ? `Journée ${next.matchday}` : STAGES[next.stage]} · {formatLongDate(next.date)}
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

function Scoreboard({ live, playing, speed, setSpeed, notice, error, busy, finishing, onPlay, onPause, onHandOver, onFinish }) {
  const label = live.stage === "regular" ? `Journée ${live.matchday}` : STAGES[live.stage];
  return (
    <header className="scoreboard card">
      <Team side={live.home} mine={live.home.club.id === live.my_club_id} />
      <span className="scoreboard__score">{live.home.score}</span>
      <div className="scoreboard__center">
        <Clock minute={live.minute} running={playing} interval={SPEEDS[speed].ms} />
        <span className="scoreboard__period">{period(live)}</span>
        <span className="muted scoreboard__meta">
          {label} · {formatLongDate(live.date)}
          {live.neutral && " · terrain neutre"}
        </span>
        {live.home.shootout !== null && (
          <span className="scoreboard__shootout num">
            Tirs au but {live.home.shootout} – {live.away.shootout}
          </span>
        )}
        <div className="scoreboard__controls">
          {live.finished ? (
            <button type="button" className="button button--primary" disabled={finishing} onClick={onFinish}>
              {finishing ? "Fin de journée…" : "Continuer"}
            </button>
          ) : (
            <>
              <button type="button" className="button button--primary scoreboard__play" onClick={playing ? onPause : onPlay}>
                {playing ? "Pause" : live.minute === 0 ? "Coup d'envoi" : "Reprendre"}
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
        {(notice || error) && (
          <span className={`scoreboard__notice${error ? " status--error" : ""}`}>
            {error ? error.message : `Pause · ${notice}`}
          </span>
        )}
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
          <li key={`${e.minute}-${e.type}-${e.player_id}-${index}`} className={`live-event live-event--${e.type}`}>
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
            </span>
            {e.points > 0 && <span className="live-event__points num">+{e.points}</span>}
          </li>
        ))}
      </ul>
    </section>
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

function Lineup({ side, mine, paused, busy, onTactics, onSubstitute }) {
  const [outgoing, setOutgoing] = useState(null); // joueur qu'on va remplacer
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
        <span className="muted">
          {side.substitutions_left} remplacement{side.substitutions_left > 1 ? "s" : ""} restant
          {side.substitutions_left > 1 ? "s" : ""}
        </span>
      </div>

      {mine && <Tactics tactics={side.tactics} disabled={!canManage} onChange={onTactics} />}

      {mine && (
        <p className="live-lineup__hint muted">
          {!paused
            ? "Mets le match en pause pour changer la tactique ou faire un remplacement."
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
            <th scope="col" title="Énergie restante">Énergie</th>
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
              selectable={canManage && player?.status === "field"}
              selected={player?.id === outgoing}
              onSelect={() => setOutgoing(player.id === outgoing ? null : player.id)}
            />
          ))}
          <tr>
            <th colSpan={5} className="table__group">
              Banc
            </th>
          </tr>
          {bench.map((player) => (
            <PlayerRow
              key={player.id}
              number={player.number}
              player={player}
              kickerId={side.kicker_id}
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

function PlayerRow({ number, player, kickerId, bench = false, selectable = false, selected = false, incoming = false, onSelect }) {
  if (!player) {
    return (
      <tr className="live-row live-row--empty">
        <td className="left jersey">{number}</td>
        <td className="left muted" colSpan={4}>
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
          {player.id === kickerId && <span className="muted live-row__kicker" title="Buteur">B</span>}
        </span>
        <Status player={player} incoming={incoming} />
      </td>
      <td className="left muted">{POSITION_SHORT[player.slot ?? player.position]}</td>
      <td>
        <Energy value={player.energy} frozen={player.slot_number === null} />
      </td>
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

// Les trois curseurs de la tactique, en listes déroulantes (changement immédiat).
function Tactics({ tactics, disabled, onChange }) {
  return (
    <div className="tactics">
      {TACTICS.map((axis) => (
        <label key={axis.key} className="tactics__axis">
          <span className="tactics__label">{axis.label}</span>
          <select
            className="input tactics__select"
            value={tactics[axis.key]}
            disabled={disabled}
            title={axis.options.find((o) => o.key === tactics[axis.key])?.scope}
            onChange={(event) => onChange({ [axis.key]: event.target.value })}
          >
            {axis.options.map((option) => (
              <option key={option.key} value={option.key}>
                {option.label}
              </option>
            ))}
          </select>
        </label>
      ))}
    </div>
  );
}
