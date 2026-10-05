// Accès à l'API. Toutes les fonctions renvoient le JSON de la réponse,
// ou lèvent une ApiError (avec le statut HTTP et le message du backend).

const BASE_URL = "/api";

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
    throw new ApiError(response.status, detail);
  }
  return response.json();
}

const post = (path, body) => request(path, { method: "POST", body });

const del = (path) => request(path, { method: "DELETE" });

export const api = {
  // Parties sauvegardées (trois emplacements)
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
  getClubNotes: (clubId) => request(`/clubs/${clubId}/notes`),
  getPlayer: (playerId) => request(`/players/${playerId}`),
  getCareer: () => request("/career"),
  getLastDismissal: () => request("/career/dismissal"),
  startCareer: (managerName, clubId) =>
    post("/career", { manager_name: managerName, club_id: clubId }),

  // Saison : calendrier, journée suivante, saison suivante
  // Sans championnat : celui du club dirigé.
  getCurrentSeason: (league = null) =>
    request(league ? `/seasons/current?league=${encodeURIComponent(league)}` : "/seasons/current"),
  playMatchday: () => post("/seasons/current/play"),
  getSeasonReview: () => request("/seasons/current/review"),
  startNextSeason: () => post("/seasons/next"),
  getMatch: (matchId) => request(`/matches/${matchId}`),

  // Match en direct (le match du club dirigé, minute par minute)
  getLive: () => request("/live"),
  startLive: () => post("/live"),
  advanceLive: (minutes = 1) => post("/live/advance", { minutes }),
  setLiveTactics: (tactics) => post("/live/tactics", tactics),
  substituteLive: (playerOut, playerIn) =>
    post("/live/substitute", { player_out: playerOut, player_in: playerIn }),
  finishLive: () => post("/live/finish"),

  // Gestion du club dirigé
  getFinances: () => request("/finances"),
  getStaff: () => request("/staff"),
  hireStaff: (staffId) => post(`/staff/hire/${staffId}`),
  fireStaff: (staffId) => post(`/staff/${staffId}/fire`),
  getFacilities: () => request("/facilities"),
  upgradeFacility: (kind) => post(`/facilities/${kind}/upgrade`),
  installAmenity: (side, kind) => post(`/facilities/stadium/stands/${side}/amenities`, { kind }),
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
