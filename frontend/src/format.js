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

// Étapes de la saison.
export const STAGES = {
  regular: "Saison régulière",
  barrage: "Barrages",
  semi: "Demi-finales",
  final: "Finale",
};

// Domaines des opérations financières.
export const CATEGORIES = {
  ticketing: "Billetterie",
  sponsors: "Sponsors",
  wages: "Salaires",
  transfer: "Transferts",
  staff: "Staff",
  facilities: "Infrastructures",
  prize: "Primes",
  medical: "Médical",
};

// --- Médical ------------------------------------------------------------------------

export const SEVERITIES = {
  light: { label: "Légère", short: "Lég." },
  moderate: { label: "Modérée", short: "Mod." },
  severe: { label: "Grave", short: "Grave" },
};

export const INJURY_SOURCES = {
  match: "en match",
  training: "à l'entraînement",
};

// Protocoles de soins, dans l'ordre du plus prudent au plus risqué.
export const PROTOCOLS = {
  cautious: { label: "Prudent", scope: "Convalescence allongée, rechute rare" },
  standard: { label: "Normal", scope: "Durée médicale, risque de rechute modéré" },
  accelerated: { label: "Retour anticipé", scope: "Plus court et payant, rechute fréquente" },
};

// 0.04 -> "4 %", 0.125 -> "12,5 %"
export const formatPercent = (ratio) => `${upToOneDecimal.format(ratio * 100)} %`;

// 1 -> "1 semaine", 6 -> "6 semaines"
export const formatWeeks = (weeks) => `${weeks} semaine${weeks > 1 ? "s" : ""}`;

// "J12" pour une journée, "Barrages" / "Demi-finales" / "Finale" sinon.
export const matchdayLabel = (match) =>
  match.stage === "regular" ? `J${match.matchday}` : STAGES[match.stage];

const oneDecimal = new Intl.NumberFormat("fr-FR", {
  minimumFractionDigits: 1,
  maximumFractionDigits: 1,
});

const upToTwoDecimals = new Intl.NumberFormat("fr-FR", { maximumFractionDigits: 2 });

const upToOneDecimal = new Intl.NumberFormat("fr-FR", { maximumFractionDigits: 1 });

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

// -137346 -> "−137 k€", 66000 -> "+66 k€"
export function formatSignedMoney(euros) {
  const sign = euros > 0 ? "+" : euros < 0 ? "−" : "";
  return sign + formatMoney(Math.abs(euros));
}

// +12 / -3 / 0, avec le signe affiché.
export const formatDiff = (value) => (value > 0 ? `+${value}` : String(value));

// 1 -> "1er", 2 -> "2e"
export const formatRank = (rank) => (rank === 1 ? "1er" : `${rank}e`);

// --- Dates --------------------------------------------------------------------------
// L'API envoie des dates "AAAA-MM-JJ" ; on les lit en heure locale pour éviter
// qu'un décalage horaire fasse glisser le jour.

export function parseDate(iso) {
  const [year, month, day] = iso.split("-").map(Number);
  return new Date(year, month - 1, day);
}

export function toIso(date) {
  const pad = (n) => String(n).padStart(2, "0");
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`;
}

const shortDay = new Intl.DateTimeFormat("fr-FR", { weekday: "short", day: "numeric", month: "short" });
const longDay = new Intl.DateTimeFormat("fr-FR", { weekday: "long", day: "numeric", month: "long", year: "numeric" });
const monthYear = new Intl.DateTimeFormat("fr-FR", { month: "long", year: "numeric" });
const numericDay = new Intl.DateTimeFormat("fr-FR", { day: "2-digit", month: "2-digit", year: "numeric" });

// "sam. 5 sept."
export const formatShortDate = (iso) => shortDay.format(parseDate(iso));
// "samedi 5 septembre 2026"
export const formatLongDate = (iso) => longDay.format(parseDate(iso));
// "septembre 2026"
export const formatMonthYear = (date) => monthYear.format(date);
// "05/09/2026"
export const formatNumericDate = (iso) => numericDay.format(parseDate(iso));

export function addDays(date, days) {
  const next = new Date(date);
  next.setDate(next.getDate() + days);
  return next;
}

// Lundi de la semaine qui contient `date`.
export function startOfWeek(date) {
  const monday = new Date(date);
  monday.setDate(date.getDate() - ((date.getDay() + 6) % 7));
  monday.setHours(0, 0, 0, 0);
  return monday;
}
