import { useEffect, useLayoutEffect, useRef, useState } from "react";

// Bouton en deux parties : l'action courante à gauche, une flèche à droite qui ouvre
// un menu d'actions voisines. Sans `options`, un bouton ordinaire.
//
// `options` : `{ key, label, hint, onSelect }`, `hint` en discret à droite du libellé.
// Le menu se ferme par un clic ailleurs, la touche Échap ou un choix. Il s'ouvre sous le
// bouton, ou au-dessus quand la place manque en bas (bord de l'écran, barre d'onglets).
export default function SplitButton({ children, onClick, disabled = false, options = [], menuLabel, menuTitle }) {
  const [open, setOpen] = useState(false);
  // Le bouton lâche le focus une fois cliqué : sinon la touche Entrée le relancerait
  // (une journée simulée de plus à chaque Entrée sur le tableau de bord).
  const act = (event) => {
    event.currentTarget.blur();
    onClick(event);
  };
  const [above, setAbove] = useState(false);
  const root = useRef(null);
  const menu = useRef(null);

  useLayoutEffect(() => {
    if (!open || !menu.current) return;
    const floor = document.querySelector(".tabbar")?.getBoundingClientRect().top ?? window.innerHeight;
    const button = root.current.getBoundingClientRect();
    const height = menu.current.offsetHeight + 14;
    setAbove(button.bottom + height > floor && button.top - height > 0);
  }, [open]);

  useEffect(() => {
    if (!open) return undefined;
    const onPointer = (event) => !root.current?.contains(event.target) && setOpen(false);
    const onKey = (event) => event.key === "Escape" && setOpen(false);
    document.addEventListener("pointerdown", onPointer);
    window.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("pointerdown", onPointer);
      window.removeEventListener("keydown", onKey);
    };
  }, [open]);

  if (options.length === 0) {
    return (
      <button type="button" className="button" disabled={disabled} onClick={act}>
        {children}
      </button>
    );
  }

  return (
    <div className="split" ref={root}>
      <button type="button" className="button split__main" disabled={disabled} onClick={act}>
        {children}
      </button>
      <button
        type="button"
        className="button split__toggle"
        disabled={disabled}
        aria-label={menuLabel}
        aria-haspopup="menu"
        aria-expanded={open}
        onClick={() => setOpen((value) => !value)}
      >
        <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
          <path d="M4 6l4 4 4-4" />
        </svg>
      </button>
      {open && !disabled && (
        <div className={`split__menu${above ? " split__menu--above" : ""}`} role="menu" aria-label={menuLabel} ref={menu}>
          {menuTitle && <p className="eyebrow split__title">{menuTitle}</p>}
          {options.map((option) => (
            <button
              key={option.key}
              type="button"
              role="menuitem"
              className="split__item"
              onClick={() => {
                setOpen(false);
                option.onSelect();
              }}
            >
              <span>{option.label}</span>
              {option.hint && <span className="muted num">{option.hint}</span>}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
