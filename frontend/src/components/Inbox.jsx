import { useCallback, useEffect, useRef, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";

import { api } from "../api.js";
import { useApi } from "../hooks/useApi.js";

// La boîte « à traiter », à droite de l'en-tête : ce qui attend une décision (affaire,
// blessé sans protocole, négociation, fins de contrat, offres...). Le bouton dit combien,
// en accent quand l'un d'eux presse ; il ouvre la liste, chaque ligne mène à sa page.
// La liste se relit à chaque changement de page.
export default function Inbox() {
  const { pathname } = useLocation();
  const navigate = useNavigate();
  const load = useCallback(() => api.getInbox(), []);
  const inbox = useApi(load);
  const { reload } = inbox;
  const [open, setOpen] = useState(false);
  const box = useRef(null);

  useEffect(() => {
    reload();
    setOpen(false);
  }, [pathname, reload]);

  useEffect(() => {
    if (!open) return undefined;
    const close = (event) => {
      if (event.key === "Escape" || (event.type === "mousedown" && !box.current?.contains(event.target))) {
        setOpen(false);
      }
    };
    window.addEventListener("keydown", close);
    window.addEventListener("mousedown", close);
    return () => {
      window.removeEventListener("keydown", close);
      window.removeEventListener("mousedown", close);
    };
  }, [open]);

  const items = inbox.data?.items ?? [];
  const urgent = items.some((item) => item.urgent);

  return (
    <div className="inbox" ref={box}>
      <button
        type="button"
        className={`inbox__button${urgent ? " inbox__button--urgent" : ""}`}
        aria-expanded={open}
        onClick={() => setOpen(!open)}
      >
        À traiter
        <span className="inbox__count num">{items.length}</span>
      </button>
      {open && (
        <div className="inbox__panel card" role="dialog" aria-label="À traiter">
          {items.length === 0 ? (
            <p className="muted inbox__empty">Rien ne presse : tout est réglé.</p>
          ) : (
            <ul className="inbox__list">
              {items.map((item, index) => (
                <li key={`${item.kind}-${index}`}>
                  <button
                    type="button"
                    className={`inbox__item${item.urgent ? " inbox__item--urgent" : ""}`}
                    onClick={() => {
                      setOpen(false);
                      navigate(item.link);
                    }}
                  >
                    <span className="inbox__title">{item.title}</span>
                    <span className="muted inbox__detail">{item.detail}</span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}
