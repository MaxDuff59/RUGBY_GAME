// Graphique radar des attributs (sur 20) d'un joueur.
// `axes` : [{ key, short }], `values` : { [key]: nombre }.
// Marge autour du cercle extérieur pour les libellés (ils restent dans le viewBox).
const SIZE = 240;
const CENTER = SIZE / 2;
const RADIUS = 68;
const MAX = 20;

function point(index, value, count) {
  const angle = -Math.PI / 2 + (index / count) * Math.PI * 2;
  const r = (value / MAX) * RADIUS;
  return [CENTER + r * Math.cos(angle), CENTER + r * Math.sin(angle)];
}

export default function Radar({ axes, values }) {
  const count = axes.length;
  const rings = [5, 10, 15, 20];

  return (
    <svg className="radar" viewBox={`0 0 ${SIZE} ${SIZE}`} role="img" aria-label="Attributs du joueur">
      {rings.map((ring) => (
        <polygon
          key={ring}
          className={`radar__ring${ring === 20 ? " radar__ring--outer" : ""}`}
          points={axes.map((_, i) => point(i, ring, count).join(",")).join(" ")}
        />
      ))}
      {axes.map((axis, i) => {
        const [x, y] = point(i, MAX, count);
        return <line key={axis.key} className="radar__axis" x1={CENTER} y1={CENTER} x2={x} y2={y} />;
      })}
      <polygon
        className="radar__area radar__area--player"
        points={axes.map((axis, i) => point(i, values[axis.key], count).join(",")).join(" ")}
      />
      {axes.map((axis, i) => {
        const [x, y] = point(i, values[axis.key], count);
        return <circle key={axis.key} className="radar__dot" cx={x} cy={y} r={3} />;
      })}
      {axes.map((axis, i) => {
        const [x, y] = point(i, MAX + 4.4, count);
        const anchor = Math.abs(x - CENTER) < 8 ? "middle" : x < CENTER ? "end" : "start";
        return (
          <text key={axis.key} className="radar__label" x={x} y={y} textAnchor={anchor} dominantBaseline="middle">
            <tspan className="radar__label-key">{axis.short}</tspan>
            <tspan className="radar__label-value" dx="4">{values[axis.key]}</tspan>
          </text>
        );
      })}
    </svg>
  );
}
