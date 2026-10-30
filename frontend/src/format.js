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
// `effect` : ce que change chaque poste (engine/coaching.py), après « +5 % » ;
// `points` : un effet en points de réussite plutôt qu'en pourcentage.
export const STAFF_ROLES = {
  FORWARDS_COACH: { label: "Entraîneur des avants", scope: "Mêlée, touche et paquet", effect: "conquête et paquet" },
  ATTACK_COACH: { label: "Entraîneur de l'attaque", scope: "Jeu à la main, lignes arrières", effect: "attaque" },
  DEFENCE_COACH: { label: "Entraîneur de la défense", scope: "Plaquage, organisation défensive", effect: "défense" },
  KICKING_COACH: { label: "Entraîneur du jeu au pied", scope: "Buteurs", effect: "de réussite au pied", points: true },
  FITNESS_COACH: { label: "Préparateur physique", scope: "Fraîcheur entre deux matchs", effect: "de récupération" },
  ANALYST: { label: "Analyste vidéo", scope: "Préparation des matchs : occasions", effect: "de territoire" },
  PHYSIO: { label: "Kinésithérapeute", scope: "Durée des convalescences", effect: "de convalescence" },
  DOCTOR: { label: "Médecin", scope: "Rechutes des joueurs revenus de blessure", effect: "de rechutes" },
};

// Ce qu'apporte un membre du staff : 0.05 -> « +5 % attaque », -0.045 au pied ->
// « −4,5 pts de réussite au pied ». Un entraîneur de 3 étoiles ne change rien.
export function formatStaffEffect(role, value) {
  const { effect, points } = STAFF_ROLES[role];
  if (Math.abs(value) < 0.0005) return "Sans effet";
  const sign = value > 0 ? "+" : "−";
  const percent = Math.abs(value) * 100;
  const amount = percent >= 10 ? integer.format(Math.round(percent)) : upToOneDecimal.format(percent);
  return `${sign}${amount} ${points ? "pts" : "%"} ${effect}`;
}

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

// "J12" pour une journée, "Barrages" / "Demi-finales" / "Finale" sinon ; "Coupe · J1"
// pour une journée de Coupe d'Europe (`cup`), "Challenge · J1" pour le Challenge européen.
export const matchdayLabel = (match) => {
  const label = match.stage === "regular" ? `J${match.matchday}` : STAGES[match.stage];
  if (!match.cup) return label;
  return `${match.competition === CHALLENGE_NAME ? "Challenge" : "Coupe"} · ${label}`;
};

// Le nom du Challenge européen (api/cup.py) ; une journée de coupe sans nom est de la
// Coupe d'Europe.
const CHALLENGE_NAME = "Challenge européen";

// "Journée 12 sur 26" (sans `regularMatchdays` : "Journée 12"), "Demi-finales",
// "Coupe d'Europe · Poules, journée 2 sur 4", "Challenge européen · Quarts de finale".
export function matchdayTitle(day, regularMatchdays = null) {
  if (day.cup) {
    const rounds = day.pool_rounds ?? CUP_POOL_ROUNDS;
    const stage = day.stage === "regular" ? `Poules, journée ${day.matchday} sur ${rounds}` : STAGES[day.stage];
    return `${day.competition ?? "Coupe d'Europe"} · ${stage}`;
  }
  if (day.stage !== "regular") return STAGES[day.stage];
  return regularMatchdays ? `Journée ${day.matchday} sur ${regularMatchdays}` : `Journée ${day.matchday}`;
}

// Les journées de poule de la Coupe d'Europe (engine/europe.py), sans précision de l'API.
const CUP_POOL_ROUNDS = 4;

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

// Le public d'un match (engine/crowd.py) : « 14 500 spectateurs · Chaudron », et en
// info-bulle ce qu'il pèse sur le match.
export const formatCrowd = (crowd) => `${integer.format(crowd.spectators)} spectateurs · ${crowd.label}`;
export const crowdEffect = (crowd) =>
  `Ambiance ${Math.round(crowd.atmosphere * 100)} / 100 : le territoire de l'équipe qui reçoit ×${oneDecimal.format(crowd.advantage)}, et les sifflets gênent le buteur adverse.`;

// Ce que fait le stade pendant le match (engine/crowd.py, `Mood`).
export const CROWD_MOODS = {
  roaring: "Le stade s'enflamme",
  tense: "Le stade pousse",
  subdued: "Le stade s'éteint",
  silent: "Le stade se tait",
};

// Statistiques d'un joueur sur un match (PlayerMatchStats), dans l'ordre d'affichage.
export const MATCH_STATS = [
  { key: "carries", label: "Ballons portés", one: "ballon porté", short: "Port." },
  { key: "line_breaks", label: "Franchissements", one: "franchissement", short: "Franch." },
  { key: "tackles", label: "Plaquages réussis", one: "plaquage réussi", short: "Plaq." },
  { key: "missed_tackles", label: "Plaquages manqués", one: "plaquage manqué", short: "Manq." },
  { key: "turnovers", label: "Ballons grattés", one: "ballon gratté", short: "Gratt." },
  { key: "lineouts_won", label: "Touches prises", one: "touche prise", short: "Touch." },
  { key: "lineout_steals", label: "Touches volées", one: "touche volée", short: "Vol." },
];

// Potentiel estimé d'un joueur (engine/development.py) : « 14-16 » (trait d'union
// insécable), ou « 15 » quand le club le connaît assez pour trancher. Le vrai
// potentiel reste caché.
export function formatPotential(player) {
  const low = Math.round(player.potential_low);
  const high = Math.round(player.potential_high);
  return low === high ? String(low) : `${low}\u2011${high}`;
}

// Points d'attributs gagnés depuis le début de la saison : « +4 », ou « – ».
export const formatGain = (points) => (points > 0 ? `+${points}` : "–");

// Les niveaux de difficulté d'une carrière de club (engine/difficulty.py).
export const DIFFICULTIES = {
  easy: { label: "Facile", scope: "Direction patiente, recettes +20 %, recrues 10 % moins chères." },
  normal: { label: "Normal", scope: "Le jeu tel qu'il est." },
  hard: { label: "Difficile", scope: "Direction exigeante, recettes −15 %, recrues 12 % plus chères." },
};

// Les trophées de fin de saison (engine/awards.py) : libellé et valeur.
export const AWARDS = {
  player: { label: "Joueur de la saison", format: (v) => `${formatNote(v)} de moyenne` },
  revelation: { label: "Révélation", format: (v) => `${formatNote(v)} de moyenne` },
  tries: { label: "Meilleur marqueur", format: (v) => `${v} essai${v > 1 ? "s" : ""}` },
  points: { label: "Meilleur réalisateur", format: (v) => `${v} pts` },
  tackles: { label: "Plaqueur de la saison", format: (v) => `${v} plaquages` },
};

// La semaine d'entraînement (engine/training.py) : son rythme et son thème.
export const TRAINING_INTENSITIES = {
  light: { label: "Légère", scope: "On récupère : plus frais au coup d'envoi, moins de blessés." },
  normal: { label: "Normale", scope: "Le rythme habituel du staff." },
  intense: { label: "Intense", scope: "On charge : on progresse plus vite, au prix de la fraîcheur." },
};
export const TRAINING_THEMES = {
  none: { label: "Sans thème", match: "Pas d'effet sur le match." },
  set_piece: { label: "Conquête", match: "Match suivant : conquête et paquet +4 %, le reste −1 %." },
  attack: { label: "Jeu courant", match: "Match suivant : attaque +4 %, le reste −1 %." },
  defence: { label: "Défense", match: "Match suivant : défense +4 %, le reste −1 %." },
  kicking: { label: "Jeu au pied", match: "Match suivant : coups de pied au but +3 points de réussite." },
  fitness: { label: "Physique", match: "Match suivant : 8 % d'énergie dépensée en moins." },
};

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

// Le choix crucial d'une fin de match serrée (engine/match_engine.py, PenaltyOption) :
// le libellé, ce qui se joue, et ce qu'on voit quand ça échoue.
export const CRUNCH_OPTIONS = {
  kick: {
    label: "Prendre les points",
    scope: "Face aux perches, pour le buteur",
    missed: "Le ballon passe à côté des perches.",
  },
  touch: {
    label: "Jouer la touche",
    scope: "Touche à 5 mètres, puis le maul des avants",
    missed: "Le maul est stoppé avant la ligne.",
  },
  scrum: {
    label: "Prendre la mêlée",
    scope: "Mêlée à 5 mètres : l'essai en force, pack contre pack",
    missed: "La mêlée adverse tient bon.",
  },
  play: {
    label: "La jouer vite",
    scope: "Jouée à la main, les trois-quarts lancés",
    missed: "La défense remonte et tient.",
  },
};

// Carrière de joueur : les dilemmes du joueur incarné en match (engine/dilemmas.py).
// Pour chaque situation, ce qui se passe et ses voies : le libellé, ce qui se joue, et
// ce qu'on voit quand elle réussit (`won`) ou échoue (`lost`).
export const DILEMMAS = {
  one_on_one: {
    title: "Un contre un",
    text: "Le ballon arrive dans tes mains, un défenseur monte sur toi.",
    options: {
      step: {
        label: "Crochet",
        scope: "Vitesse, appuis",
        won: "Ton crochet le laisse sur place : franchissement !",
        lost: "Il ne se laisse pas prendre : plaqué, ballon perdu.",
      },
      fend: {
        label: "Raffût",
        scope: "Puissance, jeu à la main",
        won: "Ton raffût l'envoie au sol : tu files !",
        lost: "Il encaisse et t'arrache le ballon.",
      },
      pass: {
        label: "Passe au soutien",
        scope: "Passe, la voie sûre",
        won: "Passe propre, le jeu continue.",
        lost: "Passe dans les pieds : ballon perdu.",
      },
    },
  },
  try_line: {
    title: "À cinq mètres de la ligne",
    text: "Tu portes le ballon à cinq mètres de l'en-but, la défense est regroupée.",
    options: {
      dive: {
        label: "Plonger seul",
        scope: "Puissance, vitesse : l'essai pour toi",
        won: "Tu traverses et tu aplatis !",
        lost: "Bloqué au-dessus de la ligne, ballon tenu.",
      },
      offload: {
        label: "Décaler un partenaire",
        scope: "Passe : l'essai pour l'équipe",
        won: "Ta passe décisive envoie un partenaire à l'essai !",
        lost: "La passe est interceptée.",
      },
      recycle: {
        label: "Jouer le temps de jeu",
        scope: "La voie sûre : la faute adverse",
        won: "La défense craque : pénalité pour nous.",
        lost: "Le ballon est ralenti, l'action s'éteint.",
      },
    },
  },
  tackle: {
    title: "Un attaquant lancé",
    text: "Un attaquant adverse arrive lancé dans ton couloir.",
    options: {
      smash: {
        label: "Plaquage offensif",
        scope: "Plaquage, puissance : le ballon à récupérer",
        won: "Plaquage dévastateur, ballon récupéré !",
        lost: "Tu le manques.",
      },
      hold: {
        label: "Plaquer avec l'aide",
        scope: "La voie sûre : attendre le deuxième plaqueur",
        won: "Plaquage à deux, il ne passe pas.",
        lost: "Tu glisses sur lui.",
      },
      ball: {
        label: "Viser le ballon",
        scope: "Puissance : le plaquage haut, risqué",
        won: "Ballon arraché dans le contact !",
        lost: "Plaquage trop haut : l'arbitre siffle.",
      },
    },
  },
  ruck: {
    title: "Ballon au sol",
    text: "Le porteur adverse est au sol, tu arrives le premier sur le ruck.",
    options: {
      jackal: {
        label: "Gratter le ballon",
        scope: "Puissance, plaquage : risqué devant l'arbitre",
        won: "Tu grattes : ballon pour nous !",
        lost: "Mains au sol : pénalité contre nous.",
      },
      counter: {
        label: "Contre-ruck",
        scope: "Puissance : repousser le ruck",
        won: "Le ruck recule, ballon récupéré !",
        lost: "Le ruck tient, rien de grave.",
      },
      fold: {
        label: "Se replacer en défense",
        scope: "La voie sûre",
        won: "Tu tiens ta place dans la ligne.",
        lost: "Un temps de retard sur le replacement.",
      },
    },
  },
  scrum: {
    title: "Mêlée",
    text: "Mêlée à trente mètres : le paquet attend ton signal.",
    options: {
      drive: {
        label: "Faire reculer",
        scope: "Mêlée, puissance : la pénalité à gagner",
        won: "La mêlée adverse recule : pénalité pour nous !",
        lost: "Tu te relèves : pénalité contre nous.",
      },
      steady: {
        label: "Stabiliser",
        scope: "La voie sûre : sortir un bon ballon",
        won: "Mêlée stable, bon ballon pour les trois-quarts.",
        lost: "La mêlée tourne, ballon perdu.",
      },
    },
  },
  lineout: {
    title: "Touche dans leurs 22",
    text: "Touche à dix mètres de leur ligne, le lancer est pour nous.",
    options: {
      maul: {
        label: "Saisie et maul",
        scope: "Touche, puissance : l'essai au bout du maul",
        won: "Le maul avance et tu aplatis au bout !",
        lost: "Le maul est stoppé, ballon perdu.",
      },
      front: {
        label: "Sauter devant",
        scope: "La voie sûre : un ballon propre",
        won: "Ballon propre en tête de touche.",
        lost: "Lancer contré, ballon perdu.",
      },
    },
  },
  kick: {
    title: "À portée des perches",
    text: "Tu reçois le ballon à 35 mètres des perches, la défense monte vite.",
    options: {
      drop: {
        label: "Tenter le drop",
        scope: "Jeu au pied : 3 points",
        won: "Le drop passe entre les perches !",
        lost: "Le drop passe à côté.",
      },
      grubber: {
        label: "Petit coup de pied à suivre",
        scope: "Jeu au pied, vitesse",
        won: "Tu récupères ton propre coup de pied : franchissement !",
        lost: "La défense récupère le ballon.",
      },
      hands: {
        label: "Jouer à la main",
        scope: "La voie sûre",
        won: "Le jeu continue, bien lancé.",
        lost: "Passe ratée, en-avant.",
      },
    },
  },
};

// Situations ajoutées par poste, et le deux contre un qui suit un franchissement.
Object.assign(DILEMMAS, {
  cross_kick: {
    title: "La défense monte en pointe",
    text: "Tu as le ballon, ton ailier est seul à l'opposé du terrain.",
    options: {
      cross: {
        label: "Transversale au pied",
        scope: "Jeu au pied : l'essai de l'ailier",
        won: "Ta transversale tombe dans les bras de l'ailier : essai !",
        lost: "Le ballon file en touche.",
      },
      flat: {
        label: "Passe plate dans l'intervalle",
        scope: "Passe : percer la ligne",
        won: "La passe trouve l'intervalle : la ligne est percée !",
        lost: "La passe est interceptée.",
      },
      touch: {
        label: "Trouver la touche",
        scope: "La voie sûre : le territoire",
        won: "Belle touche, quarante mètres gagnés.",
        lost: "Le coup de pied reste en jeu, mal placé.",
      },
    },
  },
  box_kick: {
    title: "Ballon de ruck dans ton camp",
    text: "Le ballon sort du ruck dans ton camp, la défense adverse est en place.",
    options: {
      box: {
        label: "Chandelle",
        scope: "Jeu au pied : le ballon à disputer",
        won: "Chandelle parfaite, ballon récupéré !",
        lost: "Trop longue, l'arrière adverse la cueille.",
      },
      snipe: {
        label: "Partir au ras",
        scope: "Vitesse, puissance : surprendre",
        won: "Tu pars au ras et tu perces !",
        lost: "Pris au ras du ruck, ballon perdu.",
      },
      serve: {
        label: "Servir l'ouvreur",
        scope: "La voie sûre",
        won: "Service propre, le jeu continue.",
        lost: "Service raté, en-avant.",
      },
    },
  },
  touchline: {
    title: "Le long de la touche",
    text: "Tu reçois le ballon lancé le long de la touche, l'arrière adverse arrive.",
    options: {
      outside: {
        label: "Déborder",
        scope: "Vitesse : passer par l'extérieur",
        won: "Tu le déposes sur l'aile !",
        lost: "Poussé en touche.",
      },
      inside: {
        label: "Repiquer à l'intérieur",
        scope: "Appuis, jeu à la main",
        won: "Ton repiqué le prend à contre-pied.",
        lost: "Le repiqué est contré, ballon perdu.",
      },
      chip: {
        label: "Petit par-dessus",
        scope: "Jeu au pied : l'essai pour toi",
        won: "Tu récupères ton par-dessus et tu aplatis !",
        lost: "Le rebond te trahit.",
      },
    },
  },
  counter: {
    title: "Long coup de pied adverse",
    text: "Tu réceptionnes un long coup de pied dans tes 22.",
    options: {
      run: {
        label: "Relancer",
        scope: "Vitesse, jeu à la main : le contre",
        won: "Relance de quarante mètres !",
        lost: "Pris dans tes 22.",
      },
      up_and_under: {
        label: "Chandelle",
        scope: "Jeu au pied : le ballon à disputer",
        won: "Chandelle récupérée par tes partenaires.",
        lost: "Ils récupèrent ta chandelle.",
      },
      touch: {
        label: "Trouver la touche",
        scope: "La voie sûre",
        won: "Touche trouvée, danger écarté.",
        lost: "Le coup de pied reste en jeu.",
      },
    },
  },
  throw: {
    title: "Lancer en touche",
    text: "Touche dans leurs 22, c'est à toi de lancer.",
    options: {
      back: {
        label: "Lancer au fond",
        scope: "Touche : lancer les trois-quarts",
        won: "Lancer parfait au fond, les trois-quarts percent !",
        lost: "Lancer intercepté.",
      },
      maul: {
        label: "Lancer devant, maul",
        scope: "Touche, puissance : l'essai au bout du maul",
        won: "Le maul avance et tu aplatis au bout !",
        lost: "Le maul est stoppé.",
      },
      front: {
        label: "Lancer devant",
        scope: "La voie sûre",
        won: "Ballon propre en tête de touche.",
        lost: "Lancer pas droit.",
      },
    },
  },
  provocation: {
    title: "Provocation",
    text: "Après le coup de sifflet, un adversaire te pousse et te chambre.",
    options: {
      hit_back: {
        label: "Riposter",
        scope: "Montrer qu'on ne te marche pas dessus",
        won: "L'arbitre n'a rien vu. Le message est passé.",
        lost: "L'arbitre a tout vu.",
      },
      referee: {
        label: "Prendre l'arbitre à témoin",
        scope: "La faute peut lui coûter",
        won: "L'arbitre sanctionne ton provocateur : pénalité pour nous.",
        lost: "L'arbitre ne veut rien savoir.",
      },
      walk_away: {
        label: "Tourner les talons",
        scope: "La voie sûre",
        won: "Tu ne réponds pas. Sang-froid.",
        lost: "Tu restes troublé un moment.",
      },
    },
  },
  two_on_one: {
    title: "Deux contre un",
    text: "Tu as franchi ! Un seul défenseur devant toi, un partenaire à ta hauteur.",
    options: {
      finish: {
        label: "Finir seul",
        scope: "Vitesse, puissance : l'essai pour toi",
        won: "Tu l'évites et tu files à l'essai !",
        lost: "Rattrapé avant la ligne.",
      },
      dummy: {
        label: "Feinte de passe",
        scope: "Vitesse, jeu à la main : le défenseur mord ?",
        won: "Il mord à la feinte : essai !",
        lost: "Il ne mord pas, plaqué.",
      },
      give: {
        label: "Servir le partenaire",
        scope: "Passe : l'essai pour l'équipe",
        won: "Passe parfaite, ton partenaire aplatit !",
        lost: "La passe part en avant.",
      },
    },
  },
});

// Ce que l'issue d'un dilemme a changé au match (engine/dilemmas.py, Effect), quand
// le libellé de la voie ne suffit pas.
export const DILEMMA_EFFECTS = {
  try_conceded: "Ils filent à l'essai.",
  yellow: "Carton jaune : dix minutes sur le banc.",
  penalty_conceded: "Pénalité contre nous.",
};

// Ce que l'entraîneur dit au joueur incarné (api/hero.py, `coach_notes`).
export const COACH_NOTES = {
  card: "« Un carton, c'est l'équipe à quatorze. Je ne veux plus voir ça. »",
  risks: "« Joue simple. Tu as voulu trop en faire. »",
  praise: "« Très bon match. Continue comme ça. »",
  starter: "« Tu as gagné ta place : tu commences le prochain match. »",
  doubt: "« Tu dois regagner ma confiance. Tu entreras plus tard. »",
  aggravated: "« Jouer blessé t'a coûté cher : ta blessure s'est aggravée. »",
  brave: "« Tu as serré les dents. Le groupe l'a vu. »",
};

// Le mercato du joueur incarné (engine/hero_market.py) : les offres, sa place promise,
// et les agents.
export const OFFER_KINDS = { extend: "Prolongation", transfer: "Transfert", loan: "Prêt d'une saison" };
export const OFFER_ROLES = { starter: "titulaire", rotation: "dans la rotation", prospect: "à faire ses preuves" };
export const AGENTS = {
  none: { label: "Sans agent", scope: "Tu négocies seul : pas de commission." },
  local: { label: "Agent local", scope: "Une offre de plus, des salaires +10 %, 5 % de commission." },
  star: {
    label: "Agent star",
    scope: "Deux offres de plus, de plus grands clubs, des salaires +25 %, 10 % de commission.",
  },
};

// Où le joueur incarné en est dans son club (api/hero.py).
export const HERO_STATUS = {
  starter: "Titulaire",
  bench: "Remplaçant",
  injured: "Blessé",
  suspended: "Suspendu",
  retired: "Retraité",
};

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
