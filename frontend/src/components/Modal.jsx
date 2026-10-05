import { useEffect } from "react";

// Fenêtre par-dessus la page ; se ferme par le fond, la touche Échap ou le bouton.
// `compact` : fenêtre étroite, à la hauteur de son contenu.
export default function Modal({ children, onClose, compact = false, className = "" }) {
  useEffect(() => {
    const onKey = (event) => event.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);
  return (
    <div className="modal-backdrop" onClick={onClose}>
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
