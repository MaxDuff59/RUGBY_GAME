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

// Nationalité sportive d'un joueur (code à trois lettres de l'API) ; un pays absent
// d'ici s'affiche par son code.
export const NATIONALITIES = {
  FRA: "France",
  ENG: "Angleterre",
  IRE: "Irlande",
  SCO: "Écosse",
  WAL: "Pays de Galles",
  ITA: "Italie",
  NZL: "Nouvelle-Zélande",
  RSA: "Afrique du Sud",
  AUS: "Australie",
  ARG: "Argentine",
  FIJ: "Fidji",
  GEO: "Géorgie",
  SAM: "Samoa",
  TON: "Tonga",
  JPN: "Japon",
  POR: "Portugal",
  ESP: "Espagne",
  ROM: "Roumanie",
  NAM: "Namibie",
  ZIM: "Zimbabwe",
  USA: "États-Unis",
  CAN: "Canada",
  URU: "Uruguay",
  CHI: "Chili",
  NED: "Pays-Bas",
  BEL: "Belgique",
  GER: "Allemagne",
  ALG: "Algérie",
  MOR: "Maroc",
};

export const nationalityLabel = (code) => (code ? (NATIONALITIES[code] ?? code) : null);

// Au pluriel, en minuscules : « il faut au moins 4 piliers ».
export const POSITION_PLURALS = {
  PROP: "piliers",
  HOOKER: "talonneurs",
  LOCK: "deuxièmes lignes",
  BACK_ROW: "troisièmes lignes",
  SCRUM_HALF: "demis de mêlée",
  FLY_HALF: "demis d'ouverture",
  CENTRE: "centres",
  WING: "ailiers",
  FULLBACK: "arrières",
};

// Les 9 attributs, avec l'abréviation affichée en tête de colonne.
export const ATTRIBUTES = [
  { key: "pace", short: "VIT", label: "Vitesse" },
  { key: "power", short: "PUI", label: "Puissance" },
  { key: "handling", short: "MAIN", label: "Jeu à la main" },
  { key: "passing", short: "PAS", label: "Passe" },
  { key: "kicking", short: "PIED", label: "Jeu au pied" },
  { key: "tackling", short: "PLA", label: "Plaquage" },
  { key: "scrum", short: "MÊL", label: "Mêlée" },
  { key: "lineout", short: "TOU", label: "Touche" },
  { key: "stamina", short: "END", label: "Endurance" },
];

// Attributs qui comptent le plus à chaque poste (ceux de la note au poste du moteur),
// dans l'ordre d'importance.
export const KEY_ATTRIBUTES = {
  PROP: ["scrum", "power", "tackling"],
  HOOKER: ["scrum", "lineout", "power"],
  LOCK: ["lineout", "power", "tackling"],
  BACK_ROW: ["power", "tackling", "handling", "stamina"],
  SCRUM_HALF: ["passing", "handling", "pace"],
  FLY_HALF: ["kicking", "passing", "handling"],
  CENTRE: ["pace", "handling", "tackling", "passing"],
  WING: ["pace", "handling", "power"],
  FULLBACK: ["kicking", "pace", "handling"],
};

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
  quarter: "Quarts de finale",
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
  affairs: "Vie du club",
  hospitality: "Buvettes et loges",
};

// Un match dans sa fenêtre internationale : « Journée 3 » d'un tournoi ou d'une poule,
// « Test 2 » d'une tournée, « Quarts de finale » en Coupe du monde.
export const testLabel = (window, match) =>
  match.stage !== "regular" ? STAGES[match.stage] : `${window.has_table ? "Journée" : "Test"} ${match.matchday}`;

// Un samedi d'une fenêtre : le libellé de ses matchs, ou, pour un tour de Coupe du monde
// dont les affiches ne sont pas encore connues, celui du tour (les trois derniers samedis).
export function windowDayLabel(window, date) {
  const match = window.matches.find((m) => m.date === date);
  if (match) return testLabel(window, match);
  const left = window.dates.length - window.dates.indexOf(date);
  return { 3: STAGES.quarter, 2: STAGES.semi, 1: STAGES.final }[left] ?? window.name;
}

// --- Recrutement --------------------------------------------------------------------

// Les trois voies pour recruter, dans l'ordre d'affichage.
export const DEALS = {
  precontract: { label: "Pré-contrat", scope: "Dernière année de contrat : il signe pour la saison prochaine, sans indemnité" },
  transfer: { label: "Transfert", scope: "Indemnité au club, puis salaire au joueur ; il arrive tout de suite" },
  loan: { label: "Prêt", scope: "Jusqu'à la fin de la saison, salaire à ta charge" },
  free: { label: "Agent libre", scope: "Sans club : salaire au joueur, il arrive tout de suite" },
  joker: { label: "Joker médical", scope: "Pige jusqu'au retour d'un blessé de longue durée, en plus de l'effectif" },
};

export const NEGOTIATION_STAGES = {
  club: "Indemnité à convenir avec le club",
  player: "Salaire à convenir avec le joueur",
  agreed: "Accord signé · arrive à l'intersaison",
  done: "Arrivé",
  failed: "Rompue",
};

// 2026 -> "2027" : un contrat qui couvre la saison 2026-27 se termine en juin 2027.
export const formatContractEnd = (contractUntil) => String(contractUntil + 1);

// Dernière saison sous contrat d'un joueur sans club : 2025 -> "2025-26".
export const formatLastSeason = (contractUntil) => `${contractUntil}-${String(contractUntil + 1).slice(2)}`;

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

// --- Match en direct ------------------------------------------------------------------

// Libellé de chaque événement d'un match (sans le nom du joueur).
export const EVENTS = {
  try: "Essai",
  conversion: "Transformation",
  conversion_missed: "Transformation manquée",
  penalty_goal: "Pénalité",
  penalty_missed: "Pénalité manquée",
  drop_goal: "Drop",
  injury: "Blessure",
  yellow_card: "Carton jaune",
  red_card: "Carton rouge",
  substitution: "Remplacement",
  shootout_goal: "Tir au but réussi",
  shootout_missed: "Tir au but manqué",
};

// Le temps d'un match (engine/weather.py) et ce qu'il change au jeu.
export const WEATHER = {
  clear: { label: "Temps sec", scope: "Rien ne gêne le jeu" },
  rain: { label: "Pluie", scope: "Ballon glissant : moins d'essais, le jeu au pied et les avants en profitent" },
  wind: { label: "Vent", scope: "Coups de pied au but plus durs, drops rares" },
  heat: { label: "Chaleur", scope: "Les joueurs se vident plus vite : l'endurance compte double" },
};

// Statistiques d'un joueur sur un match (PlayerMatchStats), dans l'ordre d'affichage.
export const MATCH_STATS = [
  { key: "carries", label: "Ballons portés", short: "Port." },
  { key: "line_breaks", label: "Franchissements", short: "Franch." },
  { key: "tackles", label: "Plaquages réussis", short: "Plaq." },
  { key: "missed_tackles", label: "Plaquages manqués", short: "Manq." },
  { key: "turnovers", label: "Ballons grattés", short: "Gratt." },
  { key: "lineouts_won", label: "Touches prises", short: "Touch." },
  { key: "lineout_steals", label: "Touches volées", short: "Vol." },
];

// Ce qu'un joueur suspendu doit encore purger (engine/discipline.py).
export const formatSuspension = (matches) => `Suspendu ${matches} match${matches > 1 ? "s" : ""}`;

// Les trois curseurs de la tactique, avec leurs options dans l'ordre d'affichage.
export const TACTICS = [
  {
    key: "game_plan",
    label: "Plan de jeu",
    options: [
      { key: "kicking", label: "Au pied", scope: "Occupation : territoire et pénalités, moins d'essais" },
      { key: "balanced", label: "Équilibré", scope: "Ni l'un ni l'autre" },
      { key: "hands", label: "À la main", scope: "Plus d'essais marqués… et encaissés" },
    ],
  },
  {
    key: "defence",
    label: "Défense",
    options: [
      { key: "cautious", label: "Prudente", scope: "Moins de fautes et de cartons, défense moins dense" },
      { key: "normal", label: "Normale", scope: "L'équilibre du staff" },
      { key: "aggressive", label: "Agressive", scope: "Défense qui monte, plus de pénalités et de cartons" },
    ],
  },
  {
    key: "penalties",
    label: "Pénalités",
    options: [
      { key: "kick", label: "Au pied", scope: "Trois points face aux perches" },
      { key: "touch", label: "En touche", scope: "Touche puis maul : l'essai se joue entre les deux paquets" },
      { key: "play", label: "Jouées", scope: "Vite à la main par les arrières, rien si ça échoue" },
    ],
  },
];

// Où le manager prend la parole (engine/team_talk.py).
export const TALK_MOMENTS = {
  kickoff: "Vestiaire · avant le coup d'envoi",
  break: "Vestiaire · à la pause",
  touchline: "Bord du terrain",
};

// Les discours : libellé, ce que fait le manager, et ce que donne chaque issue.
export const TALKS = {
  fire_up: {
    label: "Discours enflammé",
    scope: "Les tripes sur la table avant d'entrer.",
    lifted: "Les joueurs sortent du vestiaire en hurlant. Ça va cogner.",
    flat: "Bel effort. Les joueurs hochent la tête poliment.",
    backfired: "Trop d'émotion : le XV entre crispé, les mains tremblent.",
  },
  focus: {
    label: "Rester concentrés",
    scope: "Le plan, rien que le plan. Têtes froides.",
    lifted: "Regards fixes, gestes sûrs : le groupe est dans son match.",
    flat: "Message reçu, sans plus.",
    backfired: "Trop calme : l'équipe entre endormie.",
  },
  pressure: {
    label: "Mettre la pression",
    scope: "« C'est le match de la saison. » Ça passe ou ça casse.",
    lifted: "Le groupe relève le défi : il veut écrire l'histoire.",
    flat: "La pression glisse sur les joueurs.",
    backfired: "Le poids de l'enjeu écrase le groupe.",
  },
  encourage: {
    label: "Encourager",
    scope: "Valoriser ce qui marche, donner confiance.",
    lifted: "Les têtes se relèvent : l'équipe repart avec confiance.",
    flat: "Des mots gentils, vite oubliés.",
    backfired: "Les joueurs se relâchent, ils se croient arrivés.",
  },
  tactical: {
    label: "Recadrer au tableau",
    scope: "Calmement, deux ou trois ajustements précis.",
    lifted: "Le message passe : chacun sait ce qu'il a à faire.",
    flat: "Le tableau noir n'a pas passionné grand monde.",
    backfired: "Trop d'informations : le groupe ressort embrouillé.",
  },
  rant: {
    label: "Remonter les bretelles",
    scope: "Une engueulade en règle. Vexe si l'on mène.",
    lifted: "Piqués au vif, les joueurs veulent prouver qu'il avait tort.",
    flat: "Ils ont déjà entendu ça. Ça rentre par une oreille…",
    backfired: "Le vestiaire se braque : les cadres font la tête.",
  },
  smash_tv: {
    label: "Coup de poing dans la télé",
    scope: "L'écran vole en éclats. Le pari le plus risqué.",
    lifted: "Électrochoc ! Le XV ressort comme une meute de fauves.",
    flat: "Un silence gêné. Personne ne sait trop quoi en penser.",
    backfired: "Les joueurs sont tétanisés, la peur a pris le dessus.",
  },
  leaders: {
    label: "Laisser parler les cadres",
    scope: "Le manager se tait, les anciens prennent la parole.",
    lifted: "Les cadres trouvent les mots : le groupe se resserre.",
    flat: "Les cadres cherchent leurs mots. Rien ne se passe.",
    backfired: "Les cadres se disputent devant tout le monde.",
  },
  cheer: {
    label: "Encourager",
    scope: "Applaudir, pousser depuis la touche.",
    lifted: "Les joueurs entendent le banc et accélèrent.",
    flat: "Noyé dans le bruit du stade.",
    backfired: "Les joueurs n'en ont rien à faire.",
  },
  shout: {
    label: "Hausser le ton",
    scope: "Crier sur la touche. Plus de rage, plus de fautes.",
    lifted: "Le cri a réveillé tout le monde.",
    flat: "Personne n'a entendu.",
    backfired: "Les joueurs perdent leurs nerfs.",
  },
  calm: {
    label: "Calmer les esprits",
    scope: "Faire redescendre la tension : moins de cartons.",
    lifted: "Les têtes se refroidissent, le jeu redevient propre.",
    flat: "Le message passe à moitié.",
    backfired: "Trop calme : l'équipe perd son mordant.",
  },
};

// L'issue d'un discours, en un mot.
export const TALK_OUTCOMES = {
  lifted: "Ça porte",
  flat: "Sans effet",
  backfired: "Ça se retourne",
};

// Abréviation d'un poste pour les compositions serrées.
export const POSITION_SHORT = {
  PROP: "PIL",
  HOOKER: "TAL",
  LOCK: "2L",
  BACK_ROW: "3L",
  SCRUM_HALF: "DM",
  FLY_HALF: "DO",
  CENTRE: "CEN",
  WING: "AIL",
  FULLBACK: "ARR",
};

// --- Résultats ----------------------------------------------------------------------

// Résultat d'un match joué pour un club : "V", "N" ou "D". En phase finale, les
// tirs au but départagent un nul.
export function matchResult(match, clubId) {
  const home = match.home.id === clubId;
  let diff = (match.home_score - match.away_score) * (home ? 1 : -1);
  if (diff === 0 && match.home_shootout !== null) {
    diff = (match.home_shootout - match.away_shootout) * (home ? 1 : -1);
  }
  return diff > 0 ? "V" : diff < 0 ? "D" : "N";
}

// Mention après le score d'une phase finale : "a.p." après prolongation,
// "t.a.b. 4-3" après tirs au but (vu du club `clubId`, sinon du club qui reçoit).
export function scoreNote(match, clubId = match.home.id) {
  if (match.home_shootout !== null) {
    const home = match.home.id === clubId;
    const [mine, theirs] = home
      ? [match.home_shootout, match.away_shootout]
      : [match.away_shootout, match.home_shootout];
    return `t.a.b. ${mine}-${theirs}`;
  }
  return match.extra_time ? "a.p." : null;
}

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

// Heure de la dernière sauvegarde (horloge réelle) : « le 5 oct. à 10:39 ».
const savedDay = new Intl.DateTimeFormat("fr-FR", { day: "numeric", month: "short" });
const savedTime = new Intl.DateTimeFormat("fr-FR", { hour: "2-digit", minute: "2-digit" });
export function formatSavedAt(iso) {
  const date = new Date(iso);
  return `le ${savedDay.format(date)} à ${savedTime.format(date)}`;
}
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
