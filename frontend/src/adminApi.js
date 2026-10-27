// Appels du backoffice (routes /backoffice de l'API), réservés au compte de l'administrateur.
// Mêmes règles que api.js : JSON en retour, ApiError en cas d'échec, 401 vers la connexion.

import { ApiError, BASE_URL, UNAUTHORIZED_EVENT } from "./api.js";

// `empty` : une réponse sans contenu (204).
async function request(path, { method = "GET", body, empty = false } = {}) {
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
      // Réponse sans JSON : message générique.
    }
    if (response.status === 401) window.dispatchEvent(new Event(UNAUTHORIZED_EVENT));
    // Erreur de validation (422) : FastAPI renvoie une liste, on garde la première.
    if (Array.isArray(detail)) detail = detail[0]?.msg;
    throw new ApiError(response.status, detail);
  }
  return empty ? null : response.json();
}

const put = (path, body) => request(path, { method: "PUT", body });
const del = (path) => request(path, { method: "DELETE" });
const club = (name) => `/backoffice/clubs/${encodeURIComponent(name)}`;
const player = (clubName, name) => `/backoffice/players/${encodeURIComponent(clubName)}/${encodeURIComponent(name)}`;

export const adminApi = {
  me: () => request("/backoffice/me"),
  overview: () => request("/backoffice/overview"),

  users: () => request("/backoffice/users"),
  user: (id) => request(`/backoffice/users/${id}`),
  setPremium: (id, premium) => put(`/backoffice/users/${id}/premium`, { premium }),
  resetSeasons: (id) => request(`/backoffice/users/${id}/seasons/reset`, { method: "POST" }),

  clubs: () => request("/backoffice/clubs"),
  createClub: (form) => request("/backoffice/clubs", { method: "POST", body: form }),
  club: (name) => request(club(name)),
  saveClub: (name, form) => put(club(name), form),
  resetClub: (name) => del(club(name)),
  saveRoster: (name, roster) => put(`${club(name)}/roster`, roster),
  resetRoster: (name) => del(`${club(name)}/roster`),
  // `data` : l'image en base64, sans l'en-tête « data:… ».
  uploadLogo: (name, data) => put(`${club(name)}/logo`, { data }),
  deleteLogo: (name) => del(`${club(name)}/logo`),

  // Joueurs : un joueur se désigne par son club et son nom.
  players: () => request("/backoffice/players"),
  overallRules: () => request("/backoffice/players/overall-rules"),
  createPlayer: (form) => request("/backoffice/players", { method: "POST", body: form }),
  player: (clubName, name) => request(player(clubName, name)),
  savePlayer: (clubName, name, form) => put(player(clubName, name), form),
  deletePlayer: (clubName, name) => request(player(clubName, name), { method: "DELETE", empty: true }),
  uploadPlayerPhoto: (clubName, name, data) => put(`${player(clubName, name)}/photo`, { data }),
  deletePlayerPhoto: (clubName, name) => del(`${player(clubName, name)}/photo`),

  // Championnats : chaque appel renvoie la liste à jour.
  leagues: () => request("/backoffice/leagues"),
  createLeague: (form) => request("/backoffice/leagues", { method: "POST", body: form }),
  saveLeague: (code, form) => put(`/backoffice/leagues/${code}`, form),
};
