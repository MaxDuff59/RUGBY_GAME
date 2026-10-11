// Pictogrammes de la navigation mobile : un trait, pas de remplissage, dans la couleur
// du texte courant. Chaque entrée du menu (Layout) a sa clé.
const PATHS = {
  club: <path d="M12 3l7 2.6V11c0 4.8-3.3 8.3-7 10-3.7-1.7-7-5.2-7-10V5.6L12 3z" />,
  calendrier: (
    <>
      <rect x="3.5" y="5" width="17" height="15" rx="2" />
      <path d="M3.5 10h17M8 3v4M16 3v4" />
    </>
  ),
  effectif: (
    <>
      <circle cx="9" cy="8" r="3.2" />
      <path d="M3.5 19.5c0-3 2.5-5 5.5-5s5.5 2 5.5 5" />
      <path d="M15.5 5.2a3.2 3.2 0 0 1 0 5.6M16.5 14.6c2.3.4 4 2.2 4 4.9" />
    </>
  ),
  medical: (
    <>
      <rect x="3.5" y="7" width="17" height="13" rx="2" />
      <path d="M9 7V4.5h6V7M12 11v5M9.5 13.5h5" />
    </>
  ),
  formation: (
    <>
      <path d="M2.5 9.5L12 5l9.5 4.5L12 14 2.5 9.5z" />
      <path d="M6.5 11.8V16c0 1.4 2.5 2.8 5.5 2.8s5.5-1.4 5.5-2.8v-4.2M21.5 9.5v5" />
    </>
  ),
  staff: (
    <>
      <rect x="5" y="4.5" width="14" height="16" rx="2" />
      <path d="M9 4.5V3h6v1.5M9 10.5h6M9 14.5h4" />
    </>
  ),
  transferts: <path d="M4 8.5h14l-3.2-3.2M20 15.5H6l3.2 3.2" />,
  infrastructures: (
    <>
      <path d="M3 9c0-2 4-3.5 9-3.5S21 7 21 9v6c0 2-4 3.5-9 3.5S3 17 3 15V9z" />
      <path d="M3 9c0 2 4 3.5 9 3.5S21 11 21 9M12 12.5v6" />
    </>
  ),
  finances: (
    <>
      <rect x="2.5" y="6" width="19" height="12" rx="2" />
      <circle cx="12" cy="12" r="2.8" />
      <path d="M6 12h.01M18 12h.01" />
    </>
  ),
  plus: (
    <>
      <circle cx="5.5" cy="12" r="1.6" fill="currentColor" stroke="none" />
      <circle cx="12" cy="12" r="1.6" fill="currentColor" stroke="none" />
      <circle cx="18.5" cy="12" r="1.6" fill="currentColor" stroke="none" />
    </>
  ),
};

export default function NavIcon({ name, size = 22 }) {
  return (
    <svg
      className="nav-icon"
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.75"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      {PATHS[name]}
    </svg>
  );
}
