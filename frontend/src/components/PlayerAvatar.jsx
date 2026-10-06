// Photo de profil d'un joueur. Les joueurs sont inventés : pas encore de photo,
// on montre une silhouette vide. `src` prendra la photo le jour où il y en aura.
export default function PlayerAvatar({ src, size = 28, className = "" }) {
  const style = { width: size, height: size };
  if (src) {
    return <img className={`player-avatar ${className}`} src={src} alt="" style={style} />;
  }
  return (
    <span className={`player-avatar player-avatar--blank ${className}`} style={style} aria-hidden="true">
      <svg viewBox="0 0 32 32" width="100%" height="100%">
        <circle cx="16" cy="12.5" r="5.5" />
        <path d="M5 30c0-6.5 4.9-10.5 11-10.5S27 23.5 27 30z" />
      </svg>
    </span>
  );
}
