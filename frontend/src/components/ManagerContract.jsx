import { useCallback, useState } from "react";

import { api } from "../api.js";
import { formatContractEnd, formatLongDate, formatMoney, formatNote } from "../format.js";
import { useApi } from "../hooks/useApi.js";
import { useConfirm } from "./ConfirmDialog.jsx";
import Modal from "./Modal.jsx";
import { NOTE_LINES, levelOf } from "./NoteLine.jsx";

const BOARD = NOTE_LINES.find((line) => line.key === "board");
const SUPPORTERS = NOTE_LINES.find((line) => line.key === "supporters");

const seasonsLabel = (n) => `${n} saison${n > 1 ? "s" : ""}`;

// Ce que répond la direction à une demande de prolongation.
const ANSWERS = {
  accepted: (reply) => `Accordé : te voilà sous contrat jusqu'en ${formatContractEnd(reply.contract.until)}.`,
  countered: (reply) => `La direction ne s'engage que pour ${seasonsLabel(reply.seasons)} de plus.`,
  refused: () => "Refusé : la direction ne veut pas s'engager pour l'instant.",
};

// Le contrat du manager (`contract`, GET /career/contract) : son échéance, ce qu'en
// pense la direction, la demande de prolongation et le départ. En fin de contrat, la
// direction dit d'elle-même ce qu'elle propose. `onChange` reçoit le contrat à jour
// après une prolongation ; partir mène au choix d'un nouveau club.
export default function ManagerContract({ contract, onChange }) {
  const confirm = useConfirm();
  const [asked, setAsked] = useState(1);
  const [reply, setReply] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);

  async function ask(seasons) {
    setBusy(true);
    setError(null);
    try {
      const result = await api.askExtension(seasons);
      setReply(result);
      onChange(result.contract);
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }

  function leave() {
    const early = contract.resign_cost > 0;
    confirm.ask({
      eyebrow: "Mon contrat",
      title: `Quitter ${contract.club.name}`,
      text: early
        ? "Tu pars avant la fin de ton contrat. Tu choisiras ensuite un nouveau club, parmi ceux à ta portée."
        : "Ton contrat s'achève : tu pars libre, et tu choisiras un nouveau club parmi ceux à ta portée.",
      rows: early ? [{ label: "Réputation", value: `−${formatNote(contract.resign_cost)}`, hint: "sur 100" }] : [],
      warning: early ? "Un club qui t'aurait recruté aurait payé ton départ : ici, personne ne paie, et ça se sait." : null,
      confirmLabel: "Quitter le club",
      cautious: true,
      onConfirm: async () => {
        await api.leaveClub();
        window.location.assign("/start");
      },
    });
  }

  const options = Array.from({ length: contract.max_ask }, (_, index) => index + 1);
  const choice = Math.min(asked, contract.max_ask);

  return (
    <div className="manager-contract">
      {confirm.dialog}
      <div className="manager-contract__head">
        <p className="manager-contract__until">
          {contract.expiring ? "Fin de contrat" : `Sous contrat jusqu'en ${formatContractEnd(contract.until)}`}
        </p>
        <p className="muted">
          {contract.club.name}
          {contract.expiring
            ? " · il s'achève avec la saison"
            : ` · ${seasonsLabel(contract.seasons_left)} à jouer`}
        </p>
      </div>

      <dl className="manager-contract__notes">
        <div>
          <dt className="muted">Direction</dt>
          <dd>
            <span className="num">{formatNote(contract.board)}</span> {levelOf(BOARD, contract.board)}
          </dd>
        </div>
        <div>
          <dt className="muted">Supporters</dt>
          <dd>
            <span className="num">{formatNote(contract.supporters)}</span> {levelOf(SUPPORTERS, contract.supporters)}
          </dd>
        </div>
        {contract.indemnity > 0 && (
          <div>
            <dt className="muted">Indemnité de départ</dt>
            <dd title="Versée à ton club par celui qui te recruterait">{formatMoney(contract.indemnity)}</dd>
          </div>
        )}
      </dl>

      <Stance contract={contract} reply={reply} />

      {reply?.outcome === "countered" && (
        <div className="manager-contract__actions">
          <button type="button" className="button button--primary" disabled={busy} onClick={() => ask(reply.seasons)}>
            Accepter {seasonsLabel(reply.seasons)} de plus
          </button>
        </div>
      )}

      {reply?.outcome !== "countered" && contract.blocked === null && options.length > 0 && (
        <div className="manager-contract__actions">
          {contract.expiring && contract.renewal > 0 ? (
            <button type="button" className="button button--primary" disabled={busy} onClick={() => ask(contract.renewal)}>
              Prolonger jusqu'en {formatContractEnd(contract.until + contract.renewal)}
            </button>
          ) : (
            !contract.expiring && (
              <>
                <select
                  className="input manager-contract__years"
                  aria-label="Saisons de prolongation demandées"
                  value={choice}
                  onChange={(event) => setAsked(Number(event.target.value))}
                >
                  {options.map((n) => (
                    <option key={n} value={n}>
                      {seasonsLabel(n)} de plus · jusqu'en {formatContractEnd(contract.until + n)}
                    </option>
                  ))}
                </select>
                <button type="button" className="button button--primary" disabled={busy} onClick={() => ask(choice)}>
                  {busy ? "Un instant…" : "Demander"}
                </button>
              </>
            )
          )}
        </div>
      )}

      {error && <p className="status--error">{error.message}</p>}

      <div className="manager-contract__leave">
        <button type="button" className="button button--small" onClick={leave}>
          Quitter le club
        </button>
        <span className="muted">
          {contract.resign_cost > 0
            ? `Partir avant la fin de son contrat coûte ${formatNote(contract.resign_cost)} points de réputation.`
            : "Ton contrat s'achève : partir ne te coûte rien."}
        </span>
      </div>
    </div>
  );
}

// Ce qu'a dit (ou dirait) la direction.
function Stance({ contract, reply }) {
  if (reply) return <p className={reply.outcome === "refused" ? "manager-contract__no" : undefined}>{ANSWERS[reply.outcome](reply)}</p>;
  if (contract.expiring) {
    return contract.renewal > 0 ? (
      <p>
        La direction veut te garder : elle te propose {seasonsLabel(contract.renewal)} de plus. Sinon, signe ailleurs ou
        pars.
      </p>
    ) : (
      <p className="manager-contract__no">
        La direction ne te renouvelle pas. Signe dans un club qui te veut, ou pars : tu choisiras un club à ta portée.
      </p>
    );
  }
  if (contract.blocked === "too_long") {
    return <p className="muted">Ton contrat court déjà sur quatre saisons : la direction n'ira pas plus loin.</p>;
  }
  if (contract.blocked === "too_soon") {
    return (
      <p className="muted">
        La direction veut d'abord te voir à l'œuvre : encore {contract.matches_needed} match
        {contract.matches_needed > 1 ? "s" : ""} avant de parler prolongation.
      </p>
    );
  }
  if (contract.blocked === "refused") {
    return (
      <p className="muted">
        La direction t'a dit non. Reviens à la charge à partir du {formatLongDate(contract.retry_on)}.
      </p>
    );
  }
  return (
    <p className="muted">
      Demande une prolongation : la direction répond selon sa confiance, et l'humeur des supporters pèse aussi.
    </p>
  );
}

// Le contrat dans sa fenêtre, chargé à l'ouverture (barre latérale, palmarès).
export function ManagerContractModal({ onClose, onChange }) {
  const { data: contract, error, setData } = useApi(useCallback(api.getManagerContract, []));
  const change = (next) => {
    setData(next);
    onChange?.(next);
  };
  return (
    <Modal compact className="modal--dialog" onClose={onClose}>
      <div>
        <p className="eyebrow">Carrière</p>
        <h2 className="confirm__title">Mon contrat</h2>
      </div>
      {error && <p className="status--error">{error.message}</p>}
      {!contract && !error && <p className="status">Chargement…</p>}
      {contract && <ManagerContract contract={contract} onChange={change} />}
      <div className="confirm__actions">
        <button type="button" className="button" onClick={onClose}>
          Fermer
        </button>
      </div>
    </Modal>
  );
}
