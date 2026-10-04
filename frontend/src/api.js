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

export const api = {
  listClubs: () => request("/clubs"),
  getClub: (clubId) => request(`/clubs/${clubId}`),
  getCareer: () => request("/career"),
  startCareer: (managerName, clubId) =>
    request("/career", { method: "POST", body: { manager_name: managerName, club_id: clubId } }),
  getSeason: (year) => request(`/seasons/${year}`),
  simulateSeason: (year) => request("/seasons", { method: "POST", body: { year } }),
};
