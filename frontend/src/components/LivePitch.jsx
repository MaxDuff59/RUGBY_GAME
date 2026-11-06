import { useEffect, useMemo, useRef, useState } from "react";

import { defaultJersey, distance } from "../jersey.js";
import { inkOn } from "../clubs.js";
import { IN_GOAL, LENGTH, MID_Y, POST_GAP, WIDTH, clamp, numberOf, teamOf } from "../pitch/geometry.js";
import { direct, pitchContext } from "../pitch/director.js";
import { frameAt, schedule } from "../pitch/timeline.js";
import { kits } from "../scene/context.js";
import ClubCrest from "./ClubCrest.jsx";

// Le terrain 2D du match en direct : vu de dessus, un rond numéroté par joueur aux
// couleurs de son maillot, le ballon et l'arbitre. Chaque minute rejoue ce que le moteur
// a joué (src/pitch/director.js) : temps de jeu au ras des rucks, touches, mêlées,
// mauls, essais, coups de pied ; un choix crucial ou un dilemme attend sur sa mise en
// place. Notre équipe attaque toujours vers la droite (vers le haut avec `vertical`).
//
// `interval` : la durée d'une minute de jeu au rythme du chrono (ms) ; une action
// essentielle plus longue (un essai, une pénalité) retient le chrono : `onHold(ms)`.
// `onLineups` : le bouton « Compositions » (les XV et les bancs, en fenêtre) ; `onHide` :
// « Masquer » le terrain.

const GRASS = "#2E4A38";
const SURROUND = "#27402F";
const LINE = "rgba(247, 247, 244, 0.82)";
const RADIUS = 1.65;

const reducedMotion = () => window.matchMedia?.("(prefers-reduced-motion: reduce)").matches ?? false;

// Les couleurs de chaque équipe sur la pelouse : le maillot du jour (domicile ou
// extérieur, sans se ressembler), sa couleur secondaire en liseré. Vus en petits ronds
// sur le vert, deux bleus se confondent vite : l'équipe qui se déplace passe à sa tenue
// extérieure, puis au third, tant que les deux restent trop proches.
const CLASH = 170;

function paint(jersey) {
  let fill = jersey.base;
  let trim = jersey.trim ?? jersey.motif;
  if (distance(fill, GRASS) < 70) [fill, trim] = [trim, fill];
  return { fill, trim, ink: inkOn(fill) };
}

function teamColors(live) {
  const { home: homeKit } = kits(live.home.club.name, live.away.club.name);
  const home = paint(homeKit);
  let away = null;
  for (const kind of ["home", "away", "third"]) {
    const candidate = paint(defaultJersey(live.away.club.name, kind));
    if (!away || distance(candidate.fill, home.fill) > distance(away.fill, home.fill)) away = candidate;
    if (distance(candidate.fill, home.fill) >= CLASH) {
      away = candidate;
      break;
    }
  }
  const mineHome = live.home.club.id === live.my_club_id;
  return { us: mineHome ? home : away, them: mineHome ? away : home };
}

export default function LivePitch({ live, interval, playing, vertical = false, onHold, onHide, onLineups }) {
  const memo = useRef(null);
  const raf = useRef(0);
  const [frame, setFrame] = useState(null);
  // Les réglages du moment, lus quand une nouvelle minute arrive.
  const tempoRef = useRef({ interval, playing, onHold });
  tempoRef.current = { interval, playing, onHold };

  useEffect(() => {
    const result = direct(pitchContext(live), memo.current);
    if (!result) return;
    memo.current = result.memo;
    const { timeline } = result;
    cancelAnimationFrame(raf.current);
    const { interval: ms, playing: running, onHold: hold } = tempoRef.current;
    if (!result.animate || !timeline.beats.length) {
      setFrame(timeline.stateAt(timeline.length));
      hold?.(0);
      return;
    }
    const plan = schedule(timeline, {
      tempo: clamp(1500 / ms, 1, 8),
      budget: running ? ms * 0.95 : Infinity,
      reduced: reducedMotion(),
    });
    hold?.(running ? Math.max(0, plan.total - ms) : 0);
    const cache = new Map();
    const begin = performance.now();
    const step = (now) => {
      const elapsed = now - begin;
      setFrame(frameAt(timeline, plan, elapsed, cache));
      if (elapsed < plan.total) raf.current = requestAnimationFrame(step);
    };
    raf.current = requestAnimationFrame(step);
  }, [live]);

  useEffect(() => () => cancelAnimationFrame(raf.current), []);

  const colors = useMemo(() => teamColors(live), [live.home.club.name, live.away.club.name, live.my_club_id]);
  const ctx = useMemo(() => pitchContext(live), [live]);
  const mine = ctx.mine.club;
  const theirs = ctx.theirs.club;
  // Coordonnées du terrain (x le long, y en travers) vers celles du dessin.
  const project = vertical ? ([x, y]) => [y, LENGTH - x] : ([x, y]) => [x, y];
  const viewBox = vertical ? "-3.5 -11.5 77 123" : "-11.5 -3.5 123 77";
  const caption = frame?.caption;
  const gone = new Set(frame?.gone ?? []);
  const down = new Set(frame?.down ?? []);
  const keys = frame ? Object.keys(frame.pos).filter((key) => key !== "ref" && !gone.has(key)) : [];
  // Les joueurs au sol d'abord, le joueur mis en avant par-dessus les autres.
  keys.sort((a, b) => down.has(b) - down.has(a) || (a === frame.focus) - (b === frame.focus));

  return (
    <section className={`card live-pitch${vertical ? " live-pitch--vertical" : ""}`}>
      <div className="live-card__head live-pitch__head">
        <span className="live-pitch__caption" aria-live="polite">
          {caption ? (
            <>
              <span className="num live-pitch__minute">{live.minute}'</span>
              {caption}
            </>
          ) : live.minute === 0 ? (
            "Les équipes sont en place pour le coup d'envoi"
          ) : (
            " "
          )}
        </span>
        {onLineups && (
          <button type="button" className="button button--small live-pitch__lineups" onClick={onLineups}>
            Compositions
          </button>
        )}
        {onHide && (
          <button type="button" className="link-button live-pitch__hide" onClick={onHide}>
            Masquer
          </button>
        )}
      </div>
      <div className="live-pitch__field">
        <svg viewBox={viewBox} preserveAspectRatio="xMidYMid meet" role="img" aria-label={caption ?? "Terrain"}>
          <Field vertical={vertical} />
          {frame &&
            keys.map((key) => {
              const [cx, cy] = project(frame.pos[key]);
              const team = teamOf(key);
              const paint = colors[team];
              const person = ctx.person(key);
              const lifted = frame.lift === key;
              const flat = down.has(key);
              return (
                <g key={key} transform={`translate(${cx.toFixed(2)} ${cy.toFixed(2)})`} className="live-pitch__player">
                  <title>{person ? `${numberOf(key)} · ${person.name}` : numberOf(key)}</title>
                  {frame.focus === key && <circle r={RADIUS + 1.05} className="live-pitch__focus" />}
                  {flat ? (
                    <ellipse
                      rx={vertical ? 1.05 : 2.0}
                      ry={vertical ? 2.0 : 1.05}
                      fill={paint.fill}
                      stroke={paint.trim}
                      strokeWidth={0.3}
                      opacity={0.92}
                    />
                  ) : (
                    <circle
                      r={lifted ? RADIUS + 0.45 : RADIUS}
                      fill={paint.fill}
                      stroke={lifted ? "#F7F7F4" : paint.trim}
                      strokeWidth={lifted ? 0.5 : 0.32}
                    />
                  )}
                  <text className="live-pitch__number" fill={paint.ink} dy="0.66">
                    {numberOf(key)}
                  </text>
                </g>
              );
            })}
          {frame?.pos.ref && <Referee at={project(frame.pos.ref)} />}
          {frame?.ball && <Ball at={project([frame.ball.x, frame.ball.y])} h={frame.ball.h} />}
        </svg>
      </div>
      <div className="live-pitch__legend">
        <span className="live-pitch__side with-crest">
          <span className="live-pitch__swatch" style={{ background: colors.them.fill, borderColor: colors.them.trim }} />
          <ClubCrest name={theirs.name} size={16} />
          {theirs.name}
          <span className="muted">{vertical ? "↓" : "←"}</span>
        </span>
        <span className="live-pitch__side live-pitch__side--mine with-crest">
          <span className="muted">{vertical ? "↑" : "→"}</span>
          {mine.name}
          <ClubCrest name={mine.name} size={16} />
          <span className="live-pitch__swatch" style={{ background: colors.us.fill, borderColor: colors.us.trim }} />
        </span>
      </div>
    </section>
  );
}

function Referee({ at: [x, y] }) {
  return (
    <g transform={`translate(${x.toFixed(2)} ${y.toFixed(2)})`}>
      <title>Arbitre</title>
      <circle r={0.95} className="live-pitch__ref" />
    </g>
  );
}

// Le ballon, et son ombre quand il vole : plus il monte, plus il grossit et s'élève.
function Ball({ at: [x, y], h }) {
  const lift = Math.min(h, 16);
  const scale = 1 + lift / 16;
  return (
    <g className="live-pitch__ball">
      {lift > 0.15 && <ellipse cx={x} cy={y} rx={0.75} ry={0.48} className="live-pitch__shadow" />}
      <ellipse cx={x} cy={y - lift * 0.42} rx={0.88 * scale} ry={0.56 * scale} className="live-pitch__leather" />
    </g>
  );
}

// La pelouse et ses lignes : en-buts, 22 m, ligne médiane, 10 m et 5 m en tirets, les
// lignes des 5 et 15 m le long des touches, les perches.
function Field({ vertical }) {
  const transform = vertical ? "matrix(0 -1 1 0 0 100)" : undefined;
  const stripes = Array.from({ length: 10 }, (_, i) => i);
  const post = (x) => (
    <g key={x}>
      <line x1={x} y1={MID_Y - POST_GAP / 2} x2={x} y2={MID_Y + POST_GAP / 2} stroke="#F7F7F4" strokeWidth={0.5} />
      <circle cx={x} cy={MID_Y - POST_GAP / 2} r={0.5} fill="#F7F7F4" />
      <circle cx={x} cy={MID_Y + POST_GAP / 2} r={0.5} fill="#F7F7F4" />
    </g>
  );
  return (
    <g transform={transform}>
      <rect x={-IN_GOAL - 1.5} y={-3.5} width={LENGTH + 2 * IN_GOAL + 3} height={WIDTH + 7} fill={SURROUND} />
      <rect x={-IN_GOAL} y={0} width={LENGTH + 2 * IN_GOAL} height={WIDTH} fill={GRASS} />
      {stripes.map((i) => (i % 2 === 0 ? <rect key={i} x={i * 10} y={0} width={10} height={WIDTH} fill="rgba(255,255,255,0.035)" /> : null))}
      <rect x={-IN_GOAL} y={0} width={IN_GOAL} height={WIDTH} fill="rgba(0,0,0,0.09)" />
      <rect x={LENGTH} y={0} width={IN_GOAL} height={WIDTH} fill="rgba(0,0,0,0.09)" />
      <g stroke={LINE} fill="none" strokeWidth={0.3}>
        <rect x={-IN_GOAL} y={0} width={LENGTH + 2 * IN_GOAL} height={WIDTH} />
        <line x1={0} y1={0} x2={0} y2={WIDTH} strokeWidth={0.45} />
        <line x1={LENGTH} y1={0} x2={LENGTH} y2={WIDTH} strokeWidth={0.45} />
        {[22, 50, 78].map((x) => (
          <line key={x} x1={x} y1={0} x2={x} y2={WIDTH} />
        ))}
        {[40, 60].map((x) => (
          <line key={x} x1={x} y1={0} x2={x} y2={WIDTH} strokeDasharray="2 2" />
        ))}
        {[5, 95].map((x) => (
          <line key={x} x1={x} y1={5} x2={x} y2={WIDTH - 5} strokeDasharray="1.2 3.2" />
        ))}
        {[5, 15, WIDTH - 15, WIDTH - 5].map((y) => (
          <line key={y} x1={5} y1={y} x2={LENGTH - 5} y2={y} strokeDasharray="1.2 3.2" opacity={0.75} />
        ))}
      </g>
      {post(0)}
      {post(LENGTH)}
    </g>
  );
}
