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

// Postes du staff, dans l'ordre d'affichage, avec ce qu'ils apporteront au jeu.
export const STAFF_ROLES = {
  FORWARDS_COACH: { label: "Entraîneur des avants", scope: "Mêlée et touche" },
  ATTACK_COACH: { label: "Entraîneur de l'attaque", scope: "Jeu à la main, lignes arrières" },
  DEFENCE_COACH: { label: "Entraîneur de la défense", scope: "Plaquage, organisation défensive" },
  KICKING_COACH: { label: "Entraîneur du jeu au pied", scope: "Buteurs et jeu au pied" },
  FITNESS_COACH: { label: "Préparateur physique", scope: "Vitesse, puissance, fatigue" },
  ANALYST: { label: "Analyste", scope: "Préparation des matchs, recrutement" },
  PHYSIO: { label: "Kinésithérapeute", scope: "Récupération" },
  DOCTOR: { label: "Médecin", scope: "Blessures" },
};

export const FACILITIES = {
  stadium: { label: "Stade", unit: "places", scope: "Billetterie les jours de match" },
  training: { label: "Centre d'entraînement", unit: "niveau", scope: "Progression des joueurs" },
  academy: { label: "Centre de formation", unit: "niveau", scope: "Jeunes joueurs chaque saison" },
};

const oneDecimal = new Intl.NumberFormat("fr-FR", {
  minimumFractionDigits: 1,
  maximumFractionDigits: 1,
});

const upToTwoDecimals = new Intl.NumberFormat("fr-FR", { maximumFractionDigits: 2 });

const integer = new Intl.NumberFormat("fr-FR");

// 12.345 -> "12,3"
export const formatNote = (value) => oneDecimal.format(value);

// 12000 -> "12 000"
export const formatInteger = (value) => integer.format(value);

// 2850000 -> "2,85 M€", 40000 -> "40 k€", 500 -> "500 €"
export function formatMoney(euros) {
  const abs = Math.abs(euros);
  if (abs >= 1_000_000) return `${upToTwoDecimals.format(euros / 1_000_000)} M€`;
  if (abs >= 1_000) return `${integer.format(Math.round(euros / 1_000))} k€`;
  return `${integer.format(euros)} €`;
}

// +12 / -3 / 0, avec le signe affiché.
export const formatDiff = (value) => (value > 0 ? `+${value}` : String(value));

// 1 -> "1er", 2 -> "2e"
export const formatRank = (rank) => (rank === 1 ? "1er" : `${rank}e`);
