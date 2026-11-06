import { Box, Building, Floodlights, Pitch, Scene } from "./Scene3D.jsx";

// Centre d'entraînement et centre de formation en 3D : chaque niveau ajoute des
// installations (terrains, bâtiments, halle couverte, éclairage). La liste sert
// aussi au panneau de la fenêtre « Voir », niveau par niveau.
// Les deux sites ne se ressemblent pas : l'entraînement est un complexe sportif de
// pros (terrain d'honneur et sa tribune, bloc vestiaires-muscu, bassin, parking) ;
// la formation un campus (internat en hauteur, cours, restaurant, petits terrains des
// jeunes, arbres, toits brun-rouge). Le décor (`CAMPUS_DECOR`) est là dès le niveau 0.

export const SIZE = 560;

const SYNTHETIC = "#3b5a45";
const HALL = "#d6d6d0";
const HALL_ROOF = "#5e6168";
const POOL = "#a9b7bf";
const ROAD = "#b9bab4";
const PARKING = "#c9cac4";
const STAND = "#e2e2dc";
// Le campus de formation : façades crème et toits brun-rouge.
const CAMPUS_WALL = "#efe9df";
const CAMPUS_ROOF = "#7a4a3c";

export const CAMPUS = {
  training: [
    {
      level: 1,
      label: "Terrain d'honneur et vestiaires",
      items: [
        { type: "pitch", x: 40, y: 250, w: 260, d: 170 },
        { type: "building", x: 60, y: 222, w: 220, d: 18, h: 9, color: STAND, roof: HALL_ROOF },
        { type: "building", x: 330, y: 250, w: 100, d: 52, h: 18, label: "Vestiaires" },
      ],
    },
    {
      level: 2,
      label: "Salle de musculation",
      items: [{ type: "building", x: 330, y: 312, w: 100, d: 46, h: 14, label: "Muscu" }],
    },
    {
      level: 3,
      label: "Deuxième terrain, synthétique",
      items: [{ type: "pitch", x: 40, y: 30, w: 230, d: 150, color: SYNTHETIC }],
    },
    {
      level: 4,
      label: "Centre de récupération : kiné et bassin",
      items: [
        { type: "building", x: 445, y: 250, w: 85, d: 52, h: 12, label: "Kiné" },
        { type: "pool", x: 450, y: 322, w: 76, d: 36 },
      ],
    },
    {
      level: 5,
      label: "Halle couverte et éclairage",
      items: [
        { type: "building", x: 300, y: 30, w: 225, d: 160, h: 32, color: HALL, roof: HALL_ROOF, label: "Halle" },
        { type: "lights", x: 40, y: 250, w: 260, d: 170 },
      ],
    },
  ],
  academy: [
    {
      level: 1,
      label: "Terrain et internat",
      items: [
        { type: "pitch", x: 290, y: 300, w: 235, d: 155 },
        {
          type: "building",
          x: 40,
          y: 290,
          w: 80,
          d: 150,
          h: 44,
          color: CAMPUS_WALL,
          roof: CAMPUS_ROOF,
          label: "Internat",
        },
      ],
    },
    {
      level: 2,
      label: "Salles de cours",
      items: [
        {
          type: "building",
          x: 140,
          y: 385,
          w: 120,
          d: 60,
          h: 18,
          color: CAMPUS_WALL,
          roof: CAMPUS_ROOF,
          label: "Cours",
        },
      ],
    },
    {
      level: 3,
      label: "Deux terrains pour les jeunes",
      items: [
        { type: "pitch", x: 290, y: 40, w: 112, d: 86 },
        { type: "pitch", x: 415, y: 40, w: 112, d: 86 },
      ],
    },
    {
      level: 4,
      label: "Salle de musculation et restaurant",
      items: [
        {
          type: "building",
          x: 140,
          y: 300,
          w: 120,
          d: 56,
          h: 12,
          color: CAMPUS_WALL,
          roof: CAMPUS_ROOF,
          label: "Resto",
        },
        {
          type: "building",
          x: 150,
          y: 205,
          w: 90,
          d: 50,
          h: 14,
          color: CAMPUS_WALL,
          roof: CAMPUS_ROOF,
          label: "Muscu",
        },
      ],
    },
    {
      level: 5,
      label: "Halle couverte et éclairage",
      items: [
        { type: "building", x: 30, y: 30, w: 225, d: 145, h: 26, color: HALL, roof: CAMPUS_ROOF, label: "Halle" },
        { type: "lights", x: 290, y: 300, w: 235, d: 155 },
      ],
    },
  ],
};

// Ce qui entoure chaque site, quel que soit son niveau.
const trees = (points) => points.map(([x, y]) => ({ type: "tree", x, y }));
const cars = (points) => points.map(([x, y], i) => ({ type: "car", x, y, color: CAR_COLORS[i % CAR_COLORS.length] }));
const CAR_COLORS = ["#5e6168", "#16181b", "#a9abb0", "#7a1f2b", "#f7f7f4"];

const CAMPUS_DECOR = {
  training: [
    { type: "flat", x: 0, y: 500, w: SIZE, d: 26, color: ROAD },
    { type: "flat", x: 445, y: 395, w: 90, d: 95, color: PARKING },
    ...cars([
      [452, 402],
      [468, 402],
      [500, 402],
      [516, 402],
      [452, 462],
      [484, 462],
      [516, 462],
    ]),
    ...trees([
      [330, 440],
      [370, 450],
      [410, 440],
    ]),
  ],
  academy: [
    { type: "flat", x: 270, y: 150, w: 20, d: 400, color: PARKING },
    { type: "flat", x: 30, y: 470, w: 240, d: 20, color: PARKING },
    ...trees([
      [300, 175],
      [340, 195],
      [385, 172],
      [430, 196],
      [475, 175],
      [515, 195],
      [50, 505],
      [95, 525],
      [140, 505],
      [185, 525],
      [230, 505],
      [300, 490],
      [350, 515],
      [400, 490],
      [450, 515],
      [500, 490],
      [20, 230],
      [60, 250],
    ]),
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
    case "flat":
      return <Box x={item.x} y={item.y} z={0.2} w={item.w} d={item.d} h={0} color={item.color} />;
    case "tree":
      return (
        <>
          <Box x={item.x + 6} y={item.y + 6} w={4} d={4} h={8} color="#6b5a48" />
          <Box x={item.x} y={item.y} z={8} w={16} d={16} h={14} color="#6f8f5e" />
        </>
      );
    case "car":
      return <Box x={item.x} y={item.y} w={10} d={20} h={6} color={item.color} />;
    default:
      return null;
  }
}

export default function CampusView({ kind, level, view, onTurn }) {
  const unlocked = CAMPUS[kind].filter((stage) => stage.level <= level);
  return (
    <Scene size={SIZE} yaw={view.yaw} tilt={view.tilt} onTurn={onTurn}>
      <Box x={0} y={0} w={SIZE} d={SIZE} h={0} color="#cfd6c6" className="ground" />
      {CAMPUS_DECOR[kind].map((item, index) => (
        <Item key={`decor-${index}`} item={item} yaw={view.yaw} />
      ))}
      {unlocked.map((stage) =>
        stage.items.map((item, index) => <Item key={`${stage.level}-${index}`} item={item} yaw={view.yaw} />),
      )}
    </Scene>
  );
}
