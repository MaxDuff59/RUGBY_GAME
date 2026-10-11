// Situation d'un joueur sur le marché ou dans l'effectif, en pastille : pictogramme au
// trait, couleur par situation et libellé court. Lisible d'un coup d'œil sur une ligne.
const ICONS = {
  // Agent libre : cadenas ouvert
  free: (
    <>
      <rect x="4" y="10.5" width="12" height="8.5" rx="1.5" />
      <path d="M7 10.5V7a3 3 0 0 1 6 0" />
    </>
  ),
  // Fin de contrat : sablier
  ending: <path d="M6 3h8M6 17h8M7 3c0 4 3 4.5 3 7s-3 3-3 7M13 3c0 4-3 4.5-3 7s3 3 3 7" />,
  // Prêt : aller-retour
  loan: <path d="M4 7.5h9l-2.5-2.5M16 12.5H7l2.5 2.5" />,
  // Transfert : sortie vers la droite
  transfer: <path d="M10 4H4.5v12H10M8 10h8m-3-3 3 3-3 3" />,
  // Réserviste : banc
  bench: <path d="M3.5 9.5h13M5 9.5v5M15 9.5v5M5 12.5h10" />,
  // Ne discute plus : bulle barrée
  closed: <path d="M4 4.5h12v8H9l-3.5 3v-3H4z M3 3l14 14" />,
  // Intransférable : cadenas fermé
  locked: (
    <>
      <rect x="4" y="9" width="12" height="8.5" rx="1.5" />
      <path d="M7 9V6.5a3 3 0 0 1 6 0V9" />
    </>
  ),
  // Joker médical : croix
  joker: <path d="M10 4v12M4 10h12" />,
};

export default function StatusBadge({ kind, label, title }) {
  return (
    <span className={`badge badge--${kind}`} title={title ?? label}>
      <svg
        width="14"
        height="14"
        viewBox="0 0 20 20"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinecap="round"
        strokeLinejoin="round"
        aria-hidden="true"
      >
        {ICONS[kind]}
      </svg>
      {label}
    </span>
  );
}
