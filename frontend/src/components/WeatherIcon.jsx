import { WEATHER } from "../format.js";

// Pictogramme au trait du temps d'un match, dans la couleur du texte courant ;
// son libellé (et ce qu'il change au jeu) en info-bulle.
const PATHS = {
  clear: (
    <>
      <circle cx="12" cy="12" r="4" />
      <path d="M12 3v2.5M12 18.5V21M3 12h2.5M18.5 12H21M5.6 5.6l1.8 1.8M16.6 16.6l1.8 1.8M5.6 18.4l1.8-1.8M16.6 7.4l1.8-1.8" />
    </>
  ),
  rain: (
    <>
      <path d="M7 15.5a4 4 0 0 1-.4-8 5.5 5.5 0 0 1 10.6 1.3A3.4 3.4 0 0 1 17 15.5H7z" />
      <path d="M8.5 18.5l-1 2M12.5 18.5l-1 2M16.5 18.5l-1 2" />
    </>
  ),
  wind: <path d="M3 9h11a2.5 2.5 0 1 0-2.5-2.5M3 13h15a2.5 2.5 0 1 1-2.5 2.5M3 17h7" />,
  heat: (
    <>
      <path d="M10 4.5a2 2 0 0 1 4 0v9.3a4 4 0 1 1-4 0V4.5z" />
      <path d="M12 10v6" />
    </>
  ),
};

export default function WeatherIcon({ weather, size = 16, className = "" }) {
  if (!weather || !PATHS[weather]) return null;
  const { label, scope } = WEATHER[weather];
  return (
    <svg
      className={`weather-icon${className ? ` ${className}` : ""}`}
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.7"
      strokeLinecap="round"
      strokeLinejoin="round"
      role="img"
      aria-label={label}
    >
      <title>{`${label} · ${scope}`}</title>
      {PATHS[weather]}
    </svg>
  );
}
