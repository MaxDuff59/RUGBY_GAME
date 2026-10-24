// Pictogrammes de la navigation mobile : un trait, pas de remplissage, dans la couleur
// du texte courant. Chaque entrée du menu (Layout) a sa clé.
const PATHS = {
  club: <path d="M12 3l7 2.6V11c0 4.8-3.3 8.3-7 10-3.7-1.7-7-5.2-7-10V5.6L12 3z" />,
  // Journal : une page pliée, ses lignes de texte
  journal: (
    <>
      <path d="M16.5 8.5H20v9.2a1.75 1.75 0 0 1-3.5 0V4.5H4v13.2a1.8 1.8 0 0 0 1.8 1.8h12.4" />
      <path d="M7 8.5h6.5M7 12h6.5M7 15.5h4" />
    </>
  ),
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
  // Palmarès : une coupe à deux anses sur son socle
  palmares: (
    <>
      <path d="M7.5 4h9v5.5a4.5 4.5 0 0 1-9 0V4z" />
      <path d="M7.5 6H4.5v1.5A3 3 0 0 0 7.6 10.5M16.5 6h3v1.5a3 3 0 0 1-3.1 3M12 14v3.5M8.5 20h7l-.8-2.5h-5.4z" />
    </>
  ),
  // Entraînement : un plot d'entraînement sur sa base
  entrainement: (
    <>
      <path d="M9.5 5h5l3.5 13H6L9.5 5z" />
      <path d="M8.2 10h7.6M7.2 14h9.6M3.5 18h17" />
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
  // Sélections nationales : un globe
  selections: (
    <>
      <circle cx="12" cy="12" r="8.5" />
      <path d="M3.5 12h17M12 3.5c2.6 2.4 3.9 5.2 3.9 8.5s-1.3 6.1-3.9 8.5M12 3.5C9.4 5.9 8.1 8.7 8.1 12s1.3 6.1 3.9 8.5" />
    </>
  ),
  // Liste du sélectionneur : des lignes cochées
  liste: (
    <>
      <path d="M9.5 6.5h10M9.5 12h10M9.5 17.5h10" />
      <path d="M3.8 6.4l1.3 1.3L7.4 5M3.8 11.9l1.3 1.3 2.3-2.7M3.8 17.4l1.3 1.3 2.3-2.7" />
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
