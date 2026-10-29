// Accès à l'API. Toutes les fonctions renvoient le JSON de la réponse,
// ou lèvent une ApiError (avec le statut HTTP et le message du backend).

export const BASE_URL = "/api";

// Levé quand l'API répond 401 (session expirée ou absente) : l'application
// repasse par l'écran de connexion, d'où que l'on soit.
export const UNAUTHORIZED_EVENT = "rugby:unauthorized";

export class ApiError extends Error {
  constructor(status, detail) {
    super(detail ?? `Erreur HTTP ${status}`);
    this.status = status;
  }
}

async function request(path, { method = "GET", body } = {}) {
  const response = await fetch(BASE_URL + path, {
    method,
    headers: body ? { "Content-Type": "application/json" } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  });

  if (!response.ok) {
    let detail;
    try {
      detail = (await response.json()).detail;
    } catch {
      // Réponse sans JSON : on garde le message générique.
    }
    if (response.status === 401) window.dispatchEvent(new Event(UNAUTHORIZED_EVENT));
    throw new ApiError(response.status, detail);
  }
  if (response.status === 204) return null;
  return response.json();
}

const post = (path, body) => request(path, { method: "POST", body });

const del = (path) => request(path, { method: "DELETE" });

export const api = {
  // Compte (cookie de session posé par l'API)
  me: () => request("/auth/me"),
  register: (email, password) => post("/auth/register", { email, password }),
  login: (email, password) => post("/auth/login", { email, password }),
  logout: () => post("/auth/logout"),
  // Jouer sans compte : un invité, retrouvé par son seul cookie.
  guest: () => post("/auth/guest"),
  // Jeu complet (2 €, Stripe) : page de paiement, puis confirmation au retour.
  checkout: () => post("/billing/checkout"),
  confirmPayment: (sessionId) => post("/billing/confirm", { session_id: sessionId }),

  // Parties sauvegardées (trois emplacements par compte)
  listSaves: () => request("/saves"),
  loadSave: (slot) => post(`/saves/${slot}/load`),
  newSave: (slot) => post(`/saves/${slot}/new`),
  deleteSave: (slot) => del(`/saves/${slot}`),

  // Clubs et carrière
  listLeagues: () => request("/leagues"),
  listClubs: () => request("/clubs"),
  getClub: (clubId) => request(`/clubs/${clubId}`),
  // XV choisi par le manager : un identifiant (ou null) par place, dans l'ordre de lineup_ids.
  setLineup: (clubId, playerIds) => request(`/clubs/${clubId}/lineup`, { method: "PUT", body: { player_ids: playerIds } }),
  resetLineup: (clubId) => del(`/clubs/${clubId}/lineup`),
  setCaptain: (clubId, playerId) => request(`/clubs/${clubId}/captain`, { method: "PUT", body: { player_id: playerId } }),
  getClubNotes: (clubId) => request(`/clubs/${clubId}/notes`),
  getPlayer: (playerId) => request(`/players/${playerId}`),
  getCareer: () => request("/career"),
  getLastDismissal: () => request("/career/dismissal"),
  startCareer: (managerName, clubId, difficulty = "normal") =>
    post("/career", { manager_name: managerName, club_id: clubId, difficulty }),
  // Carrière de sélectionneur : `nation` est le code de la sélection (ex. "FRA").
  startSelectorCareer: (managerName, nation) => post("/career", { manager_name: managerName, nation }),

  // Sélections nationales : calendrier international, sélections à diriger, liste d'une nation
  getInternationals: () => request("/internationals"),
  listNations: () => request("/internationals/nations"),
  getNationSquad: (competition, code) => request(`/internationals/${competition}/${code}`),

  // Journal : articles, matchs de chaque compétition, mouvements de joueurs (toute carrière)
  getJournal: () => request("/journal"),

  // Sélectionneur : où il en est, sa liste de 42, son XV, et le monde qui avance jour par jour
  getSelection: () => request("/selection"),
  getSelectionPool: () => request("/selection/pool"),
  announceList: (playerIds) => post("/selection/list", { player_ids: playerIds }),
  replaceInList: (playerOut, playerIn) =>
    post("/selection/replace", { player_out: playerOut, player_in: playerIn }),
  getSelectionTeam: () => request("/selection/team"),
  setSelectionLineup: (playerIds) =>
    request("/selection/lineup", { method: "PUT", body: { player_ids: playerIds } }),
  resetSelectionLineup: () => del("/selection/lineup"),
  advanceSelection: () => post("/selection/advance"),

  // Saison : calendrier, journée suivante, saison suivante
  // Sans championnat : celui du club dirigé.
  getCurrentSeason: (league = null) =>
    request(league ? `/seasons/current?league=${encodeURIComponent(league)}` : "/seasons/current"),
  playMatchday: () => post("/seasons/current/play"),
  getSeasonReview: () => request("/seasons/current/review"),
  getCareerHistory: () => request("/career/history"),
  acceptOffer: (clubId) => post(`/career/offers/${clubId}`),
  acceptNationOffer: (code) => post(`/career/offers/nation/${code}`),
  // Contrat du manager : échéance, prolongation demandée à la direction, départ.
  getManagerContract: () => request("/career/contract"),
  askExtension: (seasons) => post("/career/contract/extend", { seasons }),
  leaveClub: () => post("/career/leave"),
  startNextSeason: () => post("/seasons/next"),
  getMatch: (matchId) => request(`/matches/${matchId}`),

  // Match en direct (le match du club dirigé, minute par minute)
  getLive: () => request("/live"),
  startLive: () => post("/live"),
  advanceLive: (minutes = 1) => post("/live/advance", { minutes }),
  setLiveTactics: (tactics) => post("/live/tactics", tactics),
  talkLive: (key) => post("/live/talk", { key }),
  decideLive: (option) => post("/live/decide", { option }),
  substituteLive: (playerOut, playerIn) =>
    post("/live/substitute", { player_out: playerOut, player_in: playerIn }),
  finishLive: () => post("/live/finish"),

  // Mode compétition : une partie qui ne joue que la Coupe d'Europe ou la Coupe du monde.
  getCompetition: () => request("/competition"),
  chooseCompetition: (code) => post("/competition", { code }),
  restartCompetition: () => post("/competition/restart"),
  chooseCompetitionTeam: (managerName, teamId, difficulty) =>
    post("/competition/team", { manager_name: managerName, team_id: teamId, difficulty }),

  // Match libre : deux équipes au choix (clubs ou sélections), hors de toute partie.
  friendlyTeams: () => request("/friendly/teams"),
  getFriendly: () => request("/friendly"),
  // L'affiche se prépare, le XV se compose, puis le coup d'envoi lance le direct.
  prepareFriendly: (homeId, awayId, myId) =>
    post("/friendly", { home_id: homeId, away_id: awayId, my_id: myId }),
  getFriendlyTeam: () => request("/friendly/team"),
  setFriendlyLineup: (playerIds) => request("/friendly/lineup", { method: "PUT", body: { player_ids: playerIds } }),
  resetFriendlyLineup: () => del("/friendly/lineup"),
  kickOffFriendly: () => post("/friendly/kickoff"),
  dropFriendly: () => del("/friendly"),
  replayFriendly: () => post("/friendly/replay"),
  advanceFriendly: (minutes = 1) => post("/friendly/advance", { minutes }),
  setFriendlyTactics: (tactics) => post("/friendly/tactics", tactics),
  talkFriendly: (key) => post("/friendly/talk", { key }),
  decideFriendly: (option) => post("/friendly/decide", { option }),
  substituteFriendly: (playerOut, playerIn) =>
    post("/friendly/substitute", { player_out: playerOut, player_in: playerIn }),
  finishFriendly: () => post("/friendly/finish"),

  // Gestion du club dirigé
  getFinances: () => request("/finances"),
  getStaff: () => request("/staff"),
  getTraining: () => request("/training"),
  getHonours: () => request("/honours"),
  getInbox: () => request("/inbox"),
  scoutPlayer: (playerId) => post(`/scouting/${playerId}`),
  setTraining: (change) => request("/training", { method: "PUT", body: change }),
  hireStaff: (staffId) => post(`/staff/hire/${staffId}`),
  fireStaff: (staffId) => post(`/staff/${staffId}/fire`),
  getFacilities: () => request("/facilities"),
  upgradeFacility: (kind) => post(`/facilities/${kind}/upgrade`),
  installAmenity: (side, kind) => post(`/facilities/stadium/stands/${side}/amenities`, { kind }),
  // Maillots dessinés par le manager, par tenue (home, away, third) ; resetJersey revient
  // aux couleurs du club. Le third s'achète d'abord.
  saveJersey: (kind, jersey) => request(`/facilities/jerseys/${kind}`, { method: "PUT", body: jersey }),
  resetJersey: (kind) => del(`/facilities/jerseys/${kind}`),
  buyThirdKit: () => post("/facilities/jerseys/third/buy"),
  // Sponsors du maillot : [{ sponsor, placement }], trois au plus, un par emplacement.
  setSponsors: (deals) => request("/facilities/sponsors", { method: "PUT", body: { deals } }),
  getTransfers: () => request("/transfers"),
  approachPlayer: (playerId) => request(`/transfers/${playerId}`),
  openNegotiation: (playerId, kind, injuryId = null) =>
    post(`/transfers/${playerId}/open`, { kind, injury_id: injuryId }),
  makeOffer: (negotiationId, offer) => post(`/transfers/negotiations/${negotiationId}/offer`, offer),
  abandonNegotiation: (negotiationId) =>
    request(`/transfers/negotiations/${negotiationId}`, { method: "DELETE" }),
  sellPlayer: (playerId) => post(`/transfers/sell/${playerId}`),
  getContracts: () => request("/contracts"),
  extendContract: (playerId, years) => post(`/contracts/${playerId}/extend`, { years }),
  getAcademy: () => request("/academy"),
  promoteYouth: (playerId) => post(`/academy/promote/${playerId}`),
  demotePro: (playerId) => post(`/academy/demote/${playerId}`),
  getMedical: () => request("/medical"),
  chooseProtocol: (injuryId, protocol) => post(`/medical/${injuryId}/protocol/${protocol}`),
  getAffairs: () => request("/affairs"),
  answerAffair: (affairId, choice) => post(`/affairs/${affairId}/answer`, { choice }),
};
