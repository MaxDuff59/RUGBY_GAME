import { EVENTS } from "../format.js";

// Une période de domination : sur cinq minutes, une équipe fait au moins 70 % du danger
// (barres cumulées), et le match n'y a pas été calme.
const DOMINANCE_WINDOW = 5;
const DOMINANCE_SHARE = 0.7;
const DOMINANCE_MIN_TOTAL = 120;

// Pour chaque minute, l'équipe qui domine les cinq minutes autour : 1 (qui reçoit),
// -1 (l'autre) ou 0.
function dominance(bars) {
  const half = Math.floor(DOMINANCE_WINDOW / 2);
  return bars.map((_, index) => {
    const window = bars.slice(Math.max(0, index - half), index + half + 1);
    const up = window.reduce((sum, v) => sum + Math.max(v, 0), 0);
    const down = window.reduce((sum, v) => sum + Math.max(-v, 0), 0);
    const total = up + down;
    if (total < DOMINANCE_MIN_TOTAL) return 0;
    if (up >= DOMINANCE_SHARE * total) return 1;
    if (down >= DOMINANCE_SHARE * total) return -1;
    return 0;
  });
}

// Les repères posés au-dessus (équipe qui reçoit) ou au-dessous du graphique.
const MARKS = { try: "try", yellow_card: "yellow", red_card: "red", substitution: "sub" };

// La domination d'un match, minute par minute (engine/momentum.py) : au-dessus de l'axe
// l'équipe qui reçoit, en dessous l'autre ; plus la barre est haute, plus l'équipe a
// menacé (un essai : la barre entière). Les temps forts sont en plein, le reste estompé.
// Des repères situent essais, cartons et remplacements ; la mi-temps est marquée.
//
// `bars` : une valeur par minute jouée, de -100 à 100 ; `slots` : les minutes du match
// (80, ou 100 avec la prolongation) ; `home` / `away` : `{ id, name }` ; `events` : les
// faits de jeu (`minute`, `type`, `club_id`), `nameOf(event)` le joueur concerné.
// En direct, le graphique se remplit au fil du chrono et donne le temps fort en cours ;
// le match fini (`finished`), les minutes de temps forts de chaque équipe.
export default function Momentum({ bars, slots, halfTime = 40, home, away, myId, finished, events = [], nameOf = () => null }) {
  const dominant = dominance(bars);
  const homeMine = home.id === myId;
  const colour = (up) => (up === homeMine ? "var(--accent)" : "var(--ink)");
  const names = { 1: home.name, [-1]: away.name };
  const now = dominance(bars.slice(-DOMINANCE_WINDOW)).at(-1) ?? 0;
  const strong = (sign) => dominant.filter((d, i) => d === sign && Math.sign(bars[i]) === sign).length;
  const summary = finished
    ? `Temps forts · ${names[1]} ${strong(1)}' · ${names[-1]} ${strong(-1)}'`
    : now
      ? `Temps fort · ${names[now]}`
      : "Match équilibré";
  const breaks = [halfTime, ...(slots > 80 ? [80] : [])];
  const marks = events.filter((e) => MARKS[e.type] && e.minute >= 1 && e.minute <= slots);

  const markRow = (clubId, side) => (
    <div className={`momentum__marks momentum__marks--${side}`} aria-hidden="true">
      {marks
        .filter((e) => e.club_id === clubId)
        .map((e, index) => {
          const name = nameOf(e);
          return (
            <span
              key={index}
              className={`momentum__mark momentum__mark--${MARKS[e.type]}`}
              style={{
                left: `${((e.minute - 0.5) / slots) * 100}%`,
                ...(e.type === "try" ? { background: colour(clubId === home.id) } : {}),
              }}
              title={`${e.minute}' · ${EVENTS[e.type]}${name ? ` · ${name}` : ""}`}
            />
          );
        })}
    </div>
  );

  return (
    <section className="momentum" aria-label="Momentum du match">
      <div className="momentum__head">
        <span className="live-action__label">Momentum</span>
        <span className="momentum__now">{summary}</span>
        <span className="momentum__legend">
          <span>
            <i style={{ background: colour(true) }} />
            {home.name}
          </span>
          <span>
            <i style={{ background: colour(false) }} />
            {away.name}
          </span>
          <span className="momentum__hint">En plein : temps forts · pâle : jeu partagé</span>
        </span>
      </div>
      <div className="momentum__plot">
        {markRow(home.id, "home")}
        <svg className="momentum__chart" viewBox={`0 -100 ${slots} 200`} preserveAspectRatio="none" role="img">
          <title>Momentum minute par minute</title>
          {breaks.map((minute) => (
            <line key={minute} x1={minute} x2={minute} y1={-100} y2={100} className="momentum__break" />
          ))}
          <line x1={0} x2={slots} y1={0} y2={0} className="momentum__axis" />
          {bars.map((value, index) =>
            value === 0 ? null : (
              <rect
                key={index}
                x={index + 0.12}
                width={0.76}
                y={value > 0 ? -value : 0}
                height={Math.abs(value)}
                fill={colour(value > 0)}
                opacity={dominant[index] === Math.sign(value) ? 1 : 0.32}
              >
                <title>{`${index + 1}' · ${names[Math.sign(value)]}`}</title>
              </rect>
            ),
          )}
        </svg>
        {markRow(away.id, "away")}
      </div>
    </section>
  );
}
