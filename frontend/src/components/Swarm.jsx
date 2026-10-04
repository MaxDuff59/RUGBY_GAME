import { useLayoutEffect, useRef, useState } from "react";

import { formatNote } from "../format.js";

// Essaim horizontal : un point par joueur du poste dans le championnat, placé selon
// sa valeur (échelle 1-20). Le joueur est en accent, ses coéquipiers en noir, les
// autres en gris. À droite : sa valeur et son percentile.
// points : [{ id, value, tone }] ; tone : "player" | "teammate" | undefined.
//
// Le dessin remplit la place qu'on lui donne : la hauteur du viewBox est fixe et
// sa largeur suit les proportions réelles de l'élément, donc les points
// grossissent avec la hauteur de la ligne.
const HEIGHT = 46;
const PAD = 6;
const MIN = 1;
const MAX = 20;
const RADIUS = 2.1;
const PLAYER_RADIUS = 3.8;

// Les attributs sont entiers : sans cela, tous les joueurs d'une même valeur
// s'empileraient en colonne. On étale chaque valeur sur ±0,4, de façon stable
// (fonction de l'identifiant) ; le joueur, lui, reste exactement à sa valeur.
const JITTER = 0.4;
const jitter = (p) => (p.tone === "player" ? 0 : (((p.id * 7919) % 100) / 100 - 0.5) * 2 * JITTER);

// Empile les points qui se chevauchent : chaque point prend la première rangée
// libre (0, +1, -1, +2, -2…) où il ne touche aucun point déjà placé. Le joueur
// est placé en premier, donc toujours sur l'axe.
function layout(points, scale) {
  const placed = [];
  const sorted = [...points].sort(
    (a, b) => (b.tone === "player") - (a.tone === "player") || a.value - b.value || a.id - b.id,
  );
  for (const p of sorted) {
    const x = scale(p.value + jitter(p));
    const r = p.tone === "player" ? PLAYER_RADIUS : RADIUS;
    let row = 0;
    for (let step = 0; ; step += 1) {
      row = step === 0 ? 0 : step % 2 ? Math.ceil(step / 2) : -step / 2;
      const y = HEIGHT / 2 + row * (RADIUS * 2 + 0.3);
      const free = placed.every((q) => Math.hypot(q.x - x, q.y - y) >= q.r + r + 0.3);
      if (free || step > 60) {
        placed.push({ ...p, x, y, r });
        break;
      }
    }
  }
  return placed;
}

// Largeur du viewBox qui respecte les proportions de l'élément SVG.
function useViewBoxWidth(ref) {
  const [width, setWidth] = useState(230);
  useLayoutEffect(() => {
    const svg = ref.current;
    if (!svg) return undefined;
    const measure = () => {
      const box = svg.getBoundingClientRect();
      if (box.height > 0) setWidth(Math.max(120, Math.round((HEIGHT * box.width) / box.height)));
    };
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(svg);
    return () => observer.disconnect();
  }, [ref]);
  return width;
}

export default function Swarm({ label, points, playerId }) {
  const svgRef = useRef(null);
  const width = useViewBoxWidth(svgRef);
  const scale = (value) => PAD + ((value - MIN) / (MAX - MIN)) * (width - 2 * PAD);

  const me = points.find((p) => p.id === playerId);
  const others = points.filter((p) => p.id !== playerId);
  const below = others.filter((p) => p.value < me.value).length;
  const percentile = others.length ? Math.round((below / others.length) * 100) : 0;
  const dots = layout(points, scale);
  // Le joueur se dessine en dernier, par-dessus les autres.
  dots.sort((a, b) => (a.tone === "player") - (b.tone === "player"));

  return (
    <div className="swarm">
      <span className="swarm__label">{label}</span>
      <svg
        ref={svgRef}
        className="swarm__chart"
        viewBox={`0 0 ${width} ${HEIGHT}`}
        preserveAspectRatio="xMidYMid meet"
        role="img"
        aria-label={`${label} : ${formatNote(me.value)}, ${percentile}e percentile`}
      >
        <line className="swarm__axis" x1={PAD} y1={HEIGHT / 2} x2={width - PAD} y2={HEIGHT / 2} />
        {[1, 5, 10, 15, 20].map((tick) => (
          <line key={tick} className="swarm__tick" x1={scale(tick)} y1={HEIGHT / 2 - 3} x2={scale(tick)} y2={HEIGHT / 2 + 3} />
        ))}
        {dots.map((dot) => (
          <circle
            key={dot.id}
            className={`swarm__dot${dot.tone ? ` swarm__dot--${dot.tone}` : ""}`}
            cx={dot.x}
            cy={dot.y}
            r={dot.r}
          />
        ))}
      </svg>
      <div className="swarm__figures">
        <span className="swarm__value num">{formatNote(me.value)}</span>
        <span className="swarm__percentile muted">{percentile}<sup>e</sup> pct.</span>
      </div>
    </div>
  );
}
