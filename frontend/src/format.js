// Libellés et formats partagés par les pages.

export const POSITIONS = {
  PROP: { label: "Pilier", forward: true },
  HOOKER: { label: "Talonneur", forward: true },
  LOCK: { label: "Deuxième ligne", forward: true },
  BACK_ROW: { label: "Troisième ligne", forward: true },
  SCRUM_HALF: { label: "Demi de mêlée", forward: false },
  FLY_HALF: { label: "Demi d'ouverture", forward: false },
  CENTRE: { label: "Centre", forward: false },
  WING: { label: "Ailier", forward: false },
  FULLBACK: { label: "Arrière", forward: false },
};

// Ordre des postes, du 1 au 15.
export const POSITION_ORDER = Object.keys(POSITIONS);

// Les 8 attributs, avec l'abréviation affichée en tête de colonne.
export const ATTRIBUTES = [
  { key: "pace", short: "VIT", label: "Vitesse" },
  { key: "power", short: "PUI", label: "Puissance" },
  { key: "handling", short: "MAIN", label: "Jeu à la main" },
  { key: "passing", short: "PAS", label: "Passe" },
  { key: "kicking", short: "PIED", label: "Jeu au pied" },
  { key: "tackling", short: "PLA", label: "Plaquage" },
  { key: "scrum", short: "MÊL", label: "Mêlée" },
  { key: "lineout", short: "TOU", label: "Touche" },
];

const oneDecimal = new Intl.NumberFormat("fr-FR", {
  minimumFractionDigits: 1,
  maximumFractionDigits: 1,
});

// 12.345 -> "12,3"
export const formatNote = (value) => oneDecimal.format(value);

// +12 / -3 / 0, avec le signe affiché.
export const formatDiff = (value) => (value > 0 ? `+${value}` : String(value));

// 1 -> "1er", 2 -> "2e"
export const formatRank = (rank) => (rank === 1 ? "1er" : `${rank}e`);
