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

export const api = {
  // Clubs et carrière
  listClubs: () => request("/clubs"),
  getClub: (clubId) => request(`/clubs/${clubId}`),
  getClubNotes: (clubId) => request(`/clubs/${clubId}/notes`),
  getPlayer: (playerId) => request(`/players/${playerId}`),
  getCareer: () => request("/career"),
  getLastDismissal: () => request("/career/dismissal"),
  startCareer: (managerName, clubId) =>
    post("/career", { manager_name: managerName, club_id: clubId }),

  // Saison : calendrier, journée suivante, saison suivante
  getCurrentSeason: () => request("/seasons/current"),
  playMatchday: () => post("/seasons/current/play"),
  startNextSeason: () => post("/seasons/next"),
  getMatch: (matchId) => request(`/matches/${matchId}`),

  // Gestion du club dirigé
  getFinances: () => request("/finances"),
  getStaff: () => request("/staff"),
  hireStaff: (staffId) => post(`/staff/hire/${staffId}`),
  fireStaff: (staffId) => post(`/staff/${staffId}/fire`),
  getFacilities: () => request("/facilities"),
  upgradeFacility: (kind) => post(`/facilities/${kind}/upgrade`),
  getTransfers: () => request("/transfers"),
  approachPlayer: (playerId) => request(`/transfers/${playerId}`),
  openNegotiation: (playerId, kind) => post(`/transfers/${playerId}/open`, { kind }),
  makeOffer: (negotiationId, offer) => post(`/transfers/negotiations/${negotiationId}/offer`, offer),
  abandonNegotiation: (negotiationId) =>
    request(`/transfers/negotiations/${negotiationId}`, { method: "DELETE" }),
  sellPlayer: (playerId) => post(`/transfers/sell/${playerId}`),
  getAcademy: () => request("/academy"),
  promoteYouth: (playerId) => post(`/academy/promote/${playerId}`),
  demotePro: (playerId) => post(`/academy/demote/${playerId}`),
  getMedical: () => request("/medical"),
  chooseProtocol: (injuryId, protocol) => post(`/medical/${injuryId}/protocol/${protocol}`),
  getAffairs: () => request("/affairs"),
  answerAffair: (affairId, choice) => post(`/affairs/${affairId}/answer`, { choice }),
};
