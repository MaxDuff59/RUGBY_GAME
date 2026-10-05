import { useState } from "react";

import Modal from "./Modal.jsx";

// Fenêtre de confirmation : ce qu'on s'apprête à faire, ce que ça coûte et ce
// que ça change, puis un bouton pour trancher.
//
// `rows` : lignes du récapitulatif, `{ label, value, hint }` ou, pour un
// avant/après, `{ label, from, to, hint }`.
// `onConfirm` renvoie une promesse : la fenêtre attend, affiche l'erreur
// éventuelle et reste ouverte, ou se ferme quand l'action a réussi.
export default function ConfirmDialog({
  eyebrow,
  title,
  text,
  rows = [],
  warning,
  confirmLabel = "Confirmer",
  cancelLabel = "Annuler",
  onConfirm,
  onClose,
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);

  async function confirm() {
    setBusy(true);
    setError(null);
    try {
      await onConfirm();
      onClose();
    } catch (err) {
      setError(err);
      setBusy(false);
    }
  }

  return (
    <Modal compact className="modal--dialog" onClose={busy ? () => {} : onClose}>
      <div>
        {eyebrow && <p className="eyebrow">{eyebrow}</p>}
        <h2 className="confirm__title">{title}</h2>
      </div>

      {text && <p className="confirm__text">{text}</p>}

      {rows.length > 0 && (
        <dl className="confirm__rows">
          {rows.map((row) => (
            <div key={row.label} className="confirm__row">
              <dt>{row.label}</dt>
              <dd>
                <span className="confirm__value">
                  {row.from !== undefined ? (
                    <>
                      <span className="confirm__from">{row.from}</span>
                      <span className="confirm__arrow" aria-label="devient">→</span>
                      {row.to}
                    </>
                  ) : (
                    row.value
                  )}
                </span>
                {row.hint && <span className="confirm__hint">{row.hint}</span>}
              </dd>
            </div>
          ))}
        </dl>
      )}

      {warning && <p className="confirm__warning">{warning}</p>}
      {error && <p className="status--error" style={{ margin: 0 }}>{error.message}</p>}

      <div className="confirm__actions">
        <button type="button" className="button" disabled={busy} onClick={onClose}>
          {cancelLabel}
        </button>
        <button type="button" className="button button--primary" disabled={busy} autoFocus onClick={confirm}>
          {busy ? "Un instant…" : confirmLabel}
        </button>
      </div>
    </Modal>
  );
}

// Une page garde une demande de confirmation à la fois : `ask(options)` ouvre
// la fenêtre, `dialog` est à rendre dans la page.
export function useConfirm() {
  const [request, setRequest] = useState(null);
  return {
    ask: setRequest,
    dialog: request ? <ConfirmDialog {...request} onClose={() => setRequest(null)} /> : null,
  };
}
