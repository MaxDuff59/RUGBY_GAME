import { useEffect, useRef, useState } from "react";

// Petite scène en 3D faite uniquement de transformations CSS, sans bibliothèque.
// Le monde est un plan posé à plat : x vers la droite, y vers le bas, z vers le haut.
// On l'incline vers le spectateur (`tilt`) et on le fait tourner autour de la
// verticale (`yaw`) en glissant la souris. Tout est construit avec des `Box` : des
// pavés dont on dessine le dessus et les quatre côtés.

const TILT_MIN = 32;
const TILT_MAX = 72;

export function Scene({ size, yaw, tilt, onTurn, children, className = "" }) {
  const frame = useRef(null);
  const drag = useRef(null);
  const moved = useRef(false);
  const [scale, setScale] = useState(1);

  // Le monde a une taille fixe : on le réduit pour qu'il tienne dans son cadre.
  useEffect(() => {
    const element = frame.current;
    if (!element) return undefined;
    const fit = () => {
      const { width, height } = element.getBoundingClientRect();
      setScale(Math.min(1.3, width / (size * 1.15), height / (size * 0.8)));
    };
    fit();
    const observer = new ResizeObserver(fit);
    observer.observe(element);
    return () => observer.disconnect();
  }, [size]);

  function onPointerDown(event) {
    drag.current = { x: event.clientX, y: event.clientY, yaw, tilt };
    event.currentTarget.setPointerCapture(event.pointerId);
  }

  function onPointerMove(event) {
    if (!drag.current) return;
    const dx = event.clientX - drag.current.x;
    const dy = event.clientY - drag.current.y;
    if (Math.abs(dx) + Math.abs(dy) > 4) drag.current.moved = true;
    onTurn({
      yaw: drag.current.yaw + dx * 0.45,
      tilt: Math.min(TILT_MAX, Math.max(TILT_MIN, drag.current.tilt - dy * 0.3)),
    });
  }

  function onPointerUp() {
    moved.current = Boolean(drag.current?.moved);
    drag.current = null;
  }

  // Après un glissement, le clic qui le termine ne doit pas sélectionner quoi que ce soit.
  function onClickCapture(event) {
    if (moved.current) {
      event.stopPropagation();
      moved.current = false;
    }
  }

  return (
    <div
      ref={frame}
      className={`scene ${className}`}
      onPointerDown={onPointerDown}
      onPointerMove={onPointerMove}
      onPointerUp={onPointerUp}
      onPointerCancel={onPointerUp}
      onClickCapture={onClickCapture}
    >
      <div
        className="scene__world"
        style={{
          width: size,
          height: size,
          transform: `translate(-50%, -50%) scale(${scale}) rotateX(${tilt}deg) rotateZ(${yaw}deg)`,
        }}
      >
        {children}
      </div>
    </div>
  );
}

// Un pavé posé en (x, y) à la hauteur z, de largeur w (selon x), profondeur d (selon y)
// et hauteur h. `h: 0` ne dessine que le dessus (un sol, un terrain). Les enfants sont
// posés sur le dessus ; `upright` les fait pivoter pour contrer la rotation du monde.
export function Box({
  x,
  y,
  z = 0,
  w,
  d,
  h,
  color,
  className = "",
  style,
  onClick,
  title,
  children,
  upright,
}) {
  const face = (extra) => ({
    position: "absolute",
    transformOrigin: "0 0",
    background: color,
    ...extra,
  });
  const common = { onClick, title };
  return (
    <>
      <div
        {...common}
        className={`face face--top ${className}`}
        style={{
          ...face({ left: x, top: y, width: w, height: d, transform: `translateZ(${z + h}px)` }),
          ...style,
        }}
      >
        {children && (
          <div
            className="face__label"
            style={upright !== undefined ? { transform: `rotate(${upright}deg)` } : undefined}
          >
            {children}
          </div>
        )}
      </div>
      {h > 0 && (
        <>
          <div
            {...common}
            className={`face face--side ${className}`}
            style={face({ left: x, top: y, width: w, height: h, transform: `translateZ(${z}px) rotateX(90deg)` })}
          />
          <div
            {...common}
            className={`face face--side ${className}`}
            style={face({ left: x, top: y + d, width: w, height: h, transform: `translateZ(${z}px) rotateX(90deg)` })}
          />
          <div
            {...common}
            className={`face face--end ${className}`}
            style={face({
              left: x,
              top: y,
              width: d,
              height: h,
              transform: `translateZ(${z}px) rotateZ(90deg) rotateX(90deg)`,
            })}
          />
          <div
            {...common}
            className={`face face--end ${className}`}
            style={face({
              left: x + w,
              top: y,
              width: d,
              height: h,
              transform: `translateZ(${z}px) rotateZ(90deg) rotateX(90deg)`,
            })}
          />
        </>
      )}
    </>
  );
}

// Un bâtiment : un corps clair et un toit sombre, qui porte le nom en clair.
export function Building({ x, y, w, d, h, color = "#f7f7f4", roof = "#16181b", children, upright, ...rest }) {
  return (
    <>
      <Box x={x} y={y} w={w} d={d} h={h} color={color} {...rest} />
      <Box
        x={x}
        y={y}
        z={h}
        w={w}
        d={d}
        h={1.5}
        color={roof}
        className="roof"
        upright={upright}
        {...rest}
      >
        {children}
      </Box>
    </>
  );
}

// Terrain de rugby vu de dessus : lignes d'essai, 22 m, médiane et poteaux.
export function Pitch({ x, y, w, d, color = "var(--pitch)", z = 0.4 }) {
  const stroke = "rgba(255,255,255,0.55)";
  return (
    <Box x={x} y={y} z={z} w={w} d={d} h={0} color={color} className="pitch">
      <svg viewBox="0 0 100 60" preserveAspectRatio="none" className="pitch__lines">
        <rect x="6" y="2" width="88" height="56" fill="none" stroke={stroke} strokeWidth="0.6" />
        {[6, 25, 50, 75, 94].map((at) => (
          <line key={at} x1={at} y1="2" x2={at} y2="58" stroke={stroke} strokeWidth="0.6" />
        ))}
        <line x1="6" y1="26" x2="6" y2="34" stroke="#fff" strokeWidth="1.4" />
        <line x1="94" y1="26" x2="94" y2="34" stroke="#fff" strokeWidth="1.4" />
      </svg>
    </Box>
  );
}

// Quatre mâts d'éclairage autour d'un rectangle.
export function Floodlights({ x, y, w, d, height = 44 }) {
  const corners = [
    [x - 8, y - 8],
    [x + w + 4, y - 8],
    [x - 8, y + d + 4],
    [x + w + 4, y + d + 4],
  ];
  return corners.map(([cx, cy]) => (
    <Floodlight key={`${cx}-${cy}`} x={cx} y={cy} height={height} />
  ));
}

function Floodlight({ x, y, height }) {
  return (
    <>
      <Box x={x} y={y} w={3} d={3} h={height} color="#8a8d93" />
      <Box x={x - 3} y={y - 1} z={height} w={9} d={5} h={2} color="#16181b" />
    </>
  );
}
