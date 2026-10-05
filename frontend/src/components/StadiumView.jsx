import { Box, Building, Pitch, Scene } from "./Scene3D.jsx";

// Le stade en 3D : le terrain, quatre tribunes dont la taille suit la capacité, et
// les aménagements installés (panneaux au bord du terrain, buvettes et boutique
// derrière, loges et écran géant dans la tribune). Chaque tribune est cliquable.

export const SIZE = 560;
const PITCH = { x: 155, y: 200, w: 250, d: 160 };
const GAP = 10;

export const SHORT_SIDES = { north: "Nord", south: "Sud", east: "Est", west: "Ouest" };

const CONCRETE = "#d6d6d0";
const CONCRETE_SELECTED = "#e9d5d8";
const ROOF = "#5e6168";
const GLASS = "#3a3d44";
const INK = "#16181b";
const ACCENT = "var(--accent)";

// Forme des tribunes selon la capacité : plus profondes, plus hautes, plus de gradins,
// un toit à partir de 16 000 places et les angles fermés à partir de 25 000.
export function geometry(capacity) {
  const steps = capacity <= 9_000 ? 2 : capacity <= 20_000 ? 3 : 4;
  return {
    depth: Math.round(34 + (capacity / 1_000) * 1.2),
    steps,
    stepHeight: Math.round(10 + capacity / 4_000),
    roof: capacity >= 16_000,
    corners: capacity >= 25_000,
  };
}

// Repère d'une tribune : `along` court le long du terrain, `out` s'en éloigne.
// `place(along, out, length, thickness)` rend la position et la taille dans le monde.
function frame(side) {
  switch (side) {
    case "north":
      return {
        length: PITCH.w,
        place: (a, o, la, lo) => ({ x: PITCH.x + a, y: PITCH.y - GAP - o - lo, w: la, d: lo }),
      };
    case "south":
      return {
        length: PITCH.w,
        place: (a, o, la, lo) => ({ x: PITCH.x + a, y: PITCH.y + PITCH.d + GAP + o, w: la, d: lo }),
      };
    case "west":
      return {
        length: PITCH.d,
        place: (a, o, la, lo) => ({ x: PITCH.x - GAP - o - lo, y: PITCH.y + a, w: lo, d: la }),
      };
    default:
      return {
        length: PITCH.d,
        place: (a, o, la, lo) => ({ x: PITCH.x + PITCH.w + GAP + o, y: PITCH.y + a, w: lo, d: la }),
      };
  }
}

function Stand({ stand, shape, selected, onSelect, yaw }) {
  const { length, place } = frame(stand.side);
  const { depth, steps, stepHeight, roof } = shape;
  const stepDepth = depth / steps;
  const top = steps * stepHeight;
  const select = () => onSelect(stand.side);
  const color = selected ? CONCRETE_SELECTED : CONCRETE;
  const className = selected ? "stand__face stand__face--selected" : "stand__face";

  const sponsors = stand.amenities.filter((kind) => kind === "sponsor");
  const behind = stand.amenities.filter((kind) => kind === "buvette" || kind === "shop");
  const boxes = stand.amenities.filter((kind) => kind === "boxes");
  const screen = stand.amenities.includes("screen");

  return (
    <div className="stand">
      {Array.from({ length: steps }, (_, i) => (
        <Box
          key={i}
          {...place(0, i * stepDepth, length, stepDepth)}
          h={(i + 1) * stepHeight}
          color={color}
          className={className}
          onClick={select}
          title={stand.label}
        />
      ))}

      {/* Le nom flotte au-dessus de la tribune, toujours face au spectateur. */}
      <Box
        {...place(length / 2 - 40, depth / 2 - 14, 80, 28)}
        z={(roof ? top + 20 : top) + 1}
        h={0}
        color="transparent"
        className="stand__name"
        onClick={select}
        upright={-yaw}
      >
        {SHORT_SIDES[stand.side]}
      </Box>

      {roof && (
        <>
          <Box
            {...place(-4, depth * 0.45, length + 8, depth * 0.55 + 4)}
            z={top + 16}
            h={3}
            color={ROOF}
            className="roof"
            onClick={select}
          />
          <Box {...place(0, depth - 4, 4, 4)} h={top + 16} color={ROOF} onClick={select} />
          <Box {...place(length - 4, depth - 4, 4, 4)} h={top + 16} color={ROOF} onClick={select} />
        </>
      )}

      {sponsors.map((_, k) => {
        const span = length / sponsors.length;
        return (
          <Box
            key={`sponsor-${k}`}
            {...place(k * span + 5, -7, span - 10, 4)}
            z={0.5}
            h={5}
            color={ACCENT}
            onClick={select}
          />
        );
      })}

      {behind.map((kind, j) => {
        const centre = (length * (j + 1)) / (behind.length + 1);
        if (kind === "shop") {
          return (
            <Building
              key={`behind-${j}`}
              {...place(centre - 13, depth + 8, 26, 14)}
              h={11}
              color={INK}
              roof={ACCENT}
              onClick={select}
            />
          );
        }
        return (
          <Building
            key={`behind-${j}`}
            {...place(centre - 9, depth + 8, 18, 12)}
            h={8}
            onClick={select}
          />
        );
      })}

      {boxes.map((_, q) => {
        const start = length * 0.12;
        const span = (length * 0.76) / boxes.length;
        return (
          <Box
            key={`boxes-${q}`}
            {...place(start + q * span + 4, (steps - 1) * stepDepth - 5, span - 8, 8)}
            z={(steps - 1) * stepHeight}
            h={stepHeight * 0.75}
            color={GLASS}
            onClick={select}
          />
        );
      })}

      {screen && (
        <Box
          {...place(length / 2 - 24, depth - 7, 48, 4)}
          z={roof ? top + 19 : top}
          h={20}
          color={INK}
          onClick={select}
        />
      )}
    </div>
  );
}

function Corners({ shape }) {
  const { depth, steps, stepHeight } = shape;
  const h = Math.round(steps * stepHeight * 0.6);
  const left = PITCH.x - GAP - depth;
  const right = PITCH.x + PITCH.w + GAP;
  const topY = PITCH.y - GAP - depth;
  const bottom = PITCH.y + PITCH.d + GAP;
  return [
    [left, topY],
    [right, topY],
    [left, bottom],
    [right, bottom],
  ].map(([x, y]) => <Box key={`${x}-${y}`} x={x} y={y} w={depth} d={depth} h={h} color={CONCRETE} />);
}

export default function StadiumView({ stadium, selected, onSelect, view, onTurn }) {
  const shape = geometry(stadium.capacity);
  return (
    <Scene size={SIZE} yaw={view.yaw} tilt={view.tilt} onTurn={onTurn}>
      <Box x={0} y={0} w={SIZE} d={SIZE} h={0} color="#e2e2dc" className="ground" />
      <Pitch {...PITCH} />
      {shape.corners && <Corners shape={shape} />}
      {stadium.stands.map((stand) => (
        <Stand
          key={stand.side}
          stand={stand}
          shape={shape}
          selected={selected === stand.side}
          onSelect={onSelect}
          yaw={view.yaw}
        />
      ))}
    </Scene>
  );
}
