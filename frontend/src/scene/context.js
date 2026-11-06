import { clubInfo, clubTheme, inkOn } from "../clubs.js";
import { defaultJersey, distance } from "../jersey.js";

// Ce que le plateau d'une scène (stage.js) doit savoir du match en direct.

// Les maillots des deux clubs : chacun le sien à domicile ; l'équipe qui se déplace
// passe à sa tenue extérieure (puis au third) si les deux se ressemblent trop.
export function kits(homeName, awayName) {
  const home = defaultJersey(homeName, "home");
  let away = defaultJersey(awayName, "home");
  if (distance(away.base, home.base) < 120) away = defaultJersey(awayName, "away");
  if (distance(away.base, home.base) < 90) away = defaultJersey(awayName, "third");
  return { home, away };
}

// L'heure du match n'est pas connue : les phases finales et un match sur trois se jouent
// le soir, toujours les mêmes.
const evening = (live) => live.knockout || (live.match_id * 2654435761) % 3 === 0;

export function sceneContext(live, side, phone, prefs) {
  const homeName = live.home.club.name;
  const awayName = live.away.club.name;
  const jerseys = kits(homeName, awayName);
  const homeColors = clubInfo(homeName).colors;
  const awayColors = clubInfo(awayName).colors;
  const pressure =
    live.dilemma?.pressure ?? (live.crunch ? 1.5 * (live.knockout ? 1.25 : 1) * (live.stage === "final" ? 1.5 : 1) : 1);
  return {
    home: { name: homeName, jersey: jerseys.home, colors: homeColors, ink: inkOn(homeColors[0]) },
    away: { name: awayName, jersey: jerseys.away, colors: awayColors, ink: inkOn(awayColors[0]) },
    us: side === live.home ? "home" : "away",
    accent: clubTheme(side.club.name).accent,
    weather: live.weather,
    evening: evening(live),
    pressure,
    seed: live.match_id * 131 + (live.dilemma?.minute ?? live.crunch?.minute ?? live.minute),
    muted: !prefs.sound,
    phone,
  };
}
