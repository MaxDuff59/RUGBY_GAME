// Petits formats du backoffice.

// Les clubs regroupés par championnat, dans l'ordre de l'API.
export function byLeague(clubs) {
  const groups = new Map();
  for (const club of clubs) {
    if (!groups.has(club.league_name)) groups.set(club.league_name, []);
    groups.get(club.league_name).push(club);
  }
  return [...groups.entries()];
}

// Les dates des comptes sont en UTC, sans fuseau dans le JSON.
const toDate = (iso) => new Date(/[zZ]|[+-]\d\d:\d\d$/.test(iso) ? iso : `${iso}Z`);
const day = new Intl.DateTimeFormat("fr-FR", { day: "numeric", month: "short", year: "numeric" });
const dayTime = new Intl.DateTimeFormat("fr-FR", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });

export const formatDay = (iso) => (iso ? day.format(toDate(iso)) : "—");
export const formatDayTime = (iso) => (iso ? dayTime.format(toDate(iso)) : "—");
