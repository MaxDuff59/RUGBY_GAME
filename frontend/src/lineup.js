// Le XV sur le terrain : places numérotées et composition.

// Places du XV : numéro, poste, position en % du terrain (attaque vers le haut).
// Le 10 se place en bas à droite du 9 ; les centres 12 et 13 sont sur la même
// ligne, un peu en retrait des ailiers 11 et 14.
export const SLOTS = [
  { number: 1, position: "PROP", x: 28, y: 12 },
  { number: 2, position: "HOOKER", x: 50, y: 12 },
  { number: 3, position: "PROP", x: 72, y: 12 },
  { number: 4, position: "LOCK", x: 39, y: 23 },
  { number: 5, position: "LOCK", x: 61, y: 23 },
  { number: 6, position: "BACK_ROW", x: 20, y: 33 },
  { number: 8, position: "BACK_ROW", x: 50, y: 36 },
  { number: 7, position: "BACK_ROW", x: 80, y: 33 },
  { number: 9, position: "SCRUM_HALF", x: 42, y: 50 },
  { number: 10, position: "FLY_HALF", x: 55, y: 60 },
  { number: 11, position: "WING", x: 12, y: 72 },
  { number: 14, position: "WING", x: 88, y: 72 },
  { number: 12, position: "CENTRE", x: 38, y: 78 },
  { number: 13, position: "CENTRE", x: 62, y: 78 },
  { number: 15, position: "FULLBACK", x: 50, y: 90 },
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
