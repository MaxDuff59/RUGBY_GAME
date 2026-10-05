import { Box, Building, Floodlights, Pitch, Scene } from "./Scene3D.jsx";

// Centre d'entraînement et centre de formation en 3D : chaque niveau ajoute des
// installations (terrains, bâtiments, halle couverte, éclairage). La liste sert
// aussi au panneau de la fenêtre « Voir », niveau par niveau.

export const SIZE = 560;

const SYNTHETIC = "#3b5a45";
const HALL = "#d6d6d0";
const HALL_ROOF = "#5e6168";
const POOL = "#a9b7bf";

export const CAMPUS = {
  training: [
    {
      level: 1,
      label: "Terrain d'honneur et vestiaires",
      items: [
        { type: "pitch", x: 60, y: 300, w: 220, d: 150 },
        { type: "building", x: 310, y: 320, w: 70, d: 40, h: 14, label: "Vestiaires" },
      ],
    },
    {
      level: 2,
      label: "Salle de musculation",
      items: [{ type: "building", x: 310, y: 380, w: 50, d: 36, h: 12, label: "Muscu" }],
    },
    {
      level: 3,
      label: "Deuxième terrain, synthétique",
      items: [{ type: "pitch", x: 300, y: 70, w: 200, d: 130, color: SYNTHETIC }],
    },
    {
      level: 4,
      label: "Centre de récupération : kiné et bassin",
      items: [
        { type: "building", x: 400, y: 320, w: 60, d: 40, h: 12, label: "Kiné" },
        { type: "pool", x: 405, y: 372, w: 50, d: 24 },
      ],
    },
    {
      level: 5,
      label: "Halle couverte et éclairage",
      items: [
        { type: "building", x: 60, y: 80, w: 200, d: 150, h: 30, color: HALL, roof: HALL_ROOF, label: "Halle" },
        { type: "lights", x: 60, y: 300, w: 220, d: 150 },
      ],
    },
  ],
  academy: [
    {
      level: 1,
      label: "Terrain et internat",
      items: [
        { type: "pitch", x: 60, y: 300, w: 220, d: 150 },
        { type: "building", x: 320, y: 300, w: 90, d: 40, h: 20, label: "Internat" },
      ],
    },
    {
      level: 2,
      label: "Salles de cours",
      items: [{ type: "building", x: 320, y: 360, w: 70, d: 36, h: 10, label: "Cours" }],
    },
    {
      level: 3,
      label: "Deuxième terrain",
      items: [{ type: "pitch", x: 300, y: 80, w: 180, d: 120 }],
    },
    {
      level: 4,
      label: "Salle de musculation et restaurant",
      items: [
        { type: "building", x: 430, y: 300, w: 50, d: 36, h: 12, label: "Muscu" },
        { type: "building", x: 410, y: 360, w: 70, d: 36, h: 10, label: "Resto" },
      ],
    },
    {
      level: 5,
      label: "Halle couverte et éclairage",
      items: [
        { type: "building", x: 60, y: 80, w: 200, d: 150, h: 28, color: HALL, roof: HALL_ROOF, label: "Halle" },
        { type: "lights", x: 60, y: 300, w: 220, d: 150 },
      ],
    },
  ],
};

function Item({ item, yaw }) {
  switch (item.type) {
    case "pitch":
      return <Pitch x={item.x} y={item.y} w={item.w} d={item.d} color={item.color} />;
    case "building":
      return (
        <Building
          x={item.x}
          y={item.y}
          w={item.w}
          d={item.d}
          h={item.h}
          color={item.color}
          roof={item.roof}
          upright={-yaw}
        >
          {item.label}
        </Building>
      );
    case "pool":
      return (
        <>
          <Box x={item.x - 4} y={item.y - 4} w={item.w + 8} d={item.d + 8} h={2} color="#f7f7f4" />
          <Box x={item.x} y={item.y} z={2.3} w={item.w} d={item.d} h={0} color={POOL} />
        </>
      );
    case "lights":
      return <Floodlights x={item.x} y={item.y} w={item.w} d={item.d} />;
    default:
      return null;
  }
}

export default function CampusView({ kind, level, view, onTurn }) {
  const unlocked = CAMPUS[kind].filter((stage) => stage.level <= level);
  return (
    <Scene size={SIZE} yaw={view.yaw} tilt={view.tilt} onTurn={onTurn}>
      <Box x={0} y={0} w={SIZE} d={SIZE} h={0} color="#cfd6c6" className="ground" />
      {unlocked.map((stage) =>
        stage.items.map((item, index) => <Item key={`${stage.level}-${index}`} item={item} yaw={view.yaw} />),
      )}
    </Scene>
  );
}
