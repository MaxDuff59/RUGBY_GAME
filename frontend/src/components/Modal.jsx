import { useEffect } from "react";

// Fenêtre par-dessus la page ; se ferme par le fond, la touche Échap ou le bouton.
// `compact` : fenêtre étroite, à la hauteur de son contenu. `light` : fond à peine
// assombri, quand la page doit rester lisible derrière.
export default function Modal({ children, onClose, compact = false, light = false, className = "" }) {
  useEffect(() => {
    const onKey = (event) => event.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);
  return (
    <div className={`modal-backdrop${light ? " modal-backdrop--light" : ""}`} onClick={onClose}>
      <div
        className={`modal${compact ? " modal--compact" : ""}${className ? ` ${className}` : ""}`}
        role="dialog"
        aria-modal="true"
        onClick={(event) => event.stopPropagation()}
      >
        {children}
      </div>
    </div>
  );
}
