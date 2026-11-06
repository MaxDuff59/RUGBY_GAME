// Le XV sur le terrain : places numérotées et composition.

// Places du XV : numéro, poste, position en % du terrain (attaque vers le haut). Le
// rond du numéro est centré sur le point, le nom et la note pendent dessous : les lignes
// sont espacées d'environ 13 % pour que deux joueurs voisins ne se chevauchent pas.
// Le 10 se place en bas à droite du 9 ; les centres 12 et 13 sont sur la même
// ligne, un peu en retrait des ailiers 11 et 14.
export const SLOTS = [
  { number: 1, position: "PROP", x: 24, y: 8 },
  { number: 2, position: "HOOKER", x: 50, y: 8 },
  { number: 3, position: "PROP", x: 76, y: 8 },
  { number: 4, position: "LOCK", x: 37, y: 21 },
  { number: 5, position: "LOCK", x: 63, y: 21 },
  { number: 6, position: "BACK_ROW", x: 15, y: 33 },
  { number: 8, position: "BACK_ROW", x: 50, y: 36 },
  { number: 7, position: "BACK_ROW", x: 85, y: 33 },
  { number: 9, position: "SCRUM_HALF", x: 38, y: 49 },
  { number: 10, position: "FLY_HALF", x: 62, y: 57 },
  { number: 11, position: "WING", x: 11, y: 67 },
  { number: 14, position: "WING", x: 89, y: 67 },
  { number: 12, position: "CENTRE", x: 34, y: 71 },
  { number: 13, position: "CENTRE", x: 66, y: 71 },
  { number: 15, position: "FULLBACK", x: 50, y: 84 },
];

// Lignes du terrain : en-but, 22 m, milieu, 22 m, en-but (en % de la hauteur).
export const PITCH_LINES = [
  { top: 6, solid: true },
  { top: 28, solid: false },
  { top: 50, solid: true },
  { top: 72, solid: false },
  { top: 94, solid: true },
];

// Proportions du terrain (largeur / hauteur).
export const PITCH_RATIO = 7 / 9;

// Numéro de chaque place dans l'ordre des XV renvoyés par l'API (lineup_ids) :
// le moteur range ses places par poste (SLOT_NUMBERS dans engine/match_engine.py).
export const LINEUP_NUMBERS = [1, 3, 2, 4, 5, 6, 7, 8, 9, 10, 12, 13, 11, 14, 15];

// Associe à chaque place du terrain son titulaire. Un XV complet se lit place par
// place (un joueur peut y être aligné hors poste). Si l'effectif est incomplet, le
// moteur a complété avec d'autres joueurs : on les met où il reste de la place.
// Renvoie [{ slot, player }] pour les places pourvues.
export function buildLineup(players, lineupIds) {
  const remaining = lineupIds.map((id) => players.find((p) => p.id === id)).filter(Boolean);
  if (remaining.length === LINEUP_NUMBERS.length) {
    return SLOTS.map((slot) => ({ slot, player: remaining[LINEUP_NUMBERS.indexOf(slot.number)] }));
  }
  const lineup = SLOTS.map((slot) => {
    const index = remaining.findIndex((p) => p.position === slot.position);
    return { slot, player: index === -1 ? null : remaining.splice(index, 1)[0] };
  });
  for (const entry of lineup) {
    if (!entry.player && remaining.length) entry.player = remaining.shift();
  }
  return lineup.filter((entry) => entry.player);
}

// Le XV à envoyer à l'API : un identifiant (ou null) par place, dans l'ordre de lineup_ids.
export function lineupChoice(lineup) {
  const ids = LINEUP_NUMBERS.map(() => null);
  for (const { slot, player } of lineup) ids[LINEUP_NUMBERS.indexOf(slot.number)] = player.id;
  return ids;
}

// Numéro de maillot de chaque titulaire : Map(id -> numéro).
export function jerseyNumbers(players, lineupIds) {
  return new Map(buildLineup(players, lineupIds).map(({ slot, player }) => [player.id, slot.number]));
}

// Le joueur `candidate` prend la place `slotNumber` ; s'il était titulaire ailleurs, il
// échange avec celui qui l'occupait. Renvoie le XV suivant ([{ slot, player }]).
export function movePlayer(lineup, slotNumber, candidate) {
  const place = lineup.findIndex((entry) => entry.slot.number === slotNumber);
  const from = lineup.findIndex((entry) => entry.player.id === candidate.id);
  if (place === -1 || place === from) return lineup;
  const leaving = lineup[place].player;
  return lineup.map((entry, index) => {
    if (index === place) return { ...entry, player: candidate };
    if (index === from) return { ...entry, player: leaving };
    return entry;
  });
}

// Pourquoi un joueur ne peut pas être aligné (null s'il le peut).
export function unavailability(player) {
  if (player.injury?.status === "active") return "Blessé";
  if (player.suspended_matches > 0) return "Suspendu";
  if (player.duty?.away) return "En sélection";
  return null;
}

// Sa note à un poste, celle que le staff regarde pour composer (position_ratings de
// l'API) ; à défaut, sa note générale.
export function ratingAt(team, player, position) {
  return team.position_ratings?.[player.id]?.[position] ?? player.overall;
}

// Numéros de la feuille de match : titulaires (1 à 15) et remplaçants (16 à 23).
// Map(id -> numéro).
export function matchSheet(team) {
  const numbers = jerseyNumbers(team.players, team.strength.lineup_ids);
  (team.strength.bench_ids ?? []).forEach((id, index) => numbers.set(id, 16 + index));
  return numbers;
}
