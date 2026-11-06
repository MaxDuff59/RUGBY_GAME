// Le pictogramme des remplacements : une flèche verte vers le haut (celui qui entre) et une
// flèche rouge vers le bas (celui qui sort), l'une sous l'autre. `kind` : "both" (le
// remplacement), "in" (la flèche verte seule) ou "out" (la rouge seule).
export default function SubIcon({ kind = "both", title }) {
  const both = kind === "both";
  const up = (y) => <path d={`M5 ${y} L9 ${y + 5} H6.5 V${y + 8} H3.5 V${y + 5} H1 Z`} className="sub-icon__in" />;
  const down = (y) => <path d={`M5 ${y + 8} L9 ${y + 3} H6.5 V${y} H3.5 V${y + 3} H1 Z`} className="sub-icon__out" />;
  return (
    <svg
      className={`sub-icon sub-icon--${kind}`}
      viewBox={both ? "0 0 10 18" : "0 0 10 9"}
      aria-hidden={title ? undefined : "true"}
      role={title ? "img" : undefined}
    >
      {title && <title>{title}</title>}
      {kind !== "out" && up(0.5)}
      {kind === "out" && down(0.5)}
      {both && down(9.5)}
    </svg>
  );
}
