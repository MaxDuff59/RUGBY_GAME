import { useCallback, useEffect, useRef, useState } from "react";
import { useOutletContext } from "react-router-dom";

import { api } from "../api.js";
import Level from "../components/Level.jsx";
import SortHeader from "../components/SortHeader.jsx";
import {
  DEALS,
  NEGOTIATION_STAGES,
  POSITIONS,
  formatContractEnd,
  formatMoney,
  formatNote,
  formatShortDate,
} from "../format.js";
import { useApi } from "../hooks/useApi.js";
import { useSort } from "../hooks/useSort.js";

// Filtres par voie de recrutement.
const WAYS = [
  { key: null, label: "Tous" },
  { key: "precontract", label: "Pré-contrat" },
  { key: "transfer", label: "Transfert" },
  { key: "loan", label: "Prêt" },
];

const hasWay = (listing, way) =>
  way === null ||
  (way === "precontract" && listing.precontract) ||
  (way === "transfer" && listing.transfer_fee !== null) ||
  (way === "loan" && listing.loanable);

// Recrutement : approcher un joueur, négocier avec son club puis avec lui ; vendre les siens.
export default function Transfers() {
  const { career } = useOutletContext();
  const market = useApi(useCallback(api.getTransfers, []));
  const myClub = useApi(useCallback(() => api.getClub(career.club_id), [career.club_id]));

  const [position, setPosition] = useState(null); // null = tous les postes
  const [way, setWay] = useState(null);
  const [targetId, setTargetId] = useState(null); // joueur approché
  const [actionError, setActionError] = useState(null);
  const listingSort = useSort(market.data?.listings ?? [], { key: "player.value", dir: "desc" });
  const squadSort = useSort(myClub.data?.players ?? [], { key: "value", dir: "desc" });

  async function act(call) {
    setActionError(null);
    try {
      market.setData(await call());
      myClub.reload(); // l'effectif a changé
    } catch (err) {
      setActionError(err);
    }
  }

  function sell(player) {
    if (window.confirm(`Vendre ${player.name} pour ${formatMoney(player.value)} ?`)) {
      act(() => api.sellPlayer(player.id));
    }
  }

  // Pendant un rechargement (après une offre, une vente...), on garde la page en
  // place avec les données précédentes : sinon la modale se démonterait.
  const firstLoad = (market.loading && !market.data) || (myClub.loading && !myClub.data);
  if (firstLoad) return <p className="status">Chargement…</p>;
  if (market.error) return <p className="status status--error">{market.error.message}</p>;
  if (myClub.error) return <p className="status status--error">{myClub.error.message}</p>;

  const data = market.data;
  const squadFull = data.squad_size >= data.squad_max;
  const squadAtMinimum = data.squad_size <= data.squad_min;
  const listings = listingSort.rows.filter(
    (listing) =>
      (position === null || listing.player.position === position) && hasWay(listing, way),
  );
  const listingHeader = (key, label, first = "desc", left = false) => (
    <SortHeader sortKey={key} label={label} sort={listingSort.sort} onToggle={listingSort.toggle} first={first} left={left} />
  );
  const squadHeader = (key, label, first = "desc", left = false) => (
    <SortHeader sortKey={key} label={label} sort={squadSort.sort} onToggle={squadSort.toggle} first={first} left={left} />
  );

  return (
    <>
      <header className="page-head">
        <div>
          <h1 className="title">Transferts</h1>
          <p className="muted" style={{ margin: "8px 0 0" }}>
            Saison {data.season_year}-{String(data.season_year + 1).slice(2)}. Les transferts en cours de contrat
            sont rares et chers : vise les joueurs en dernière année de contrat, ou un prêt.
          </p>
        </div>
        <div className="page-head__stats">
          <Stat value={formatMoney(data.balance)} label="trésorerie" />
          <Stat value={data.squad_size} label={`joueurs (de ${data.squad_min} à ${data.squad_max})`} />
          <Stat value={formatNote(data.my_level)} label="niveau de ton XV" />
        </div>
      </header>

      {actionError && <p className="status--error">{actionError.message}</p>}

      {targetId !== null && (
        <Modal onClose={() => setTargetId(null)}>
          <Negotiation
            playerId={targetId}
            squadFull={squadFull}
            onClose={() => setTargetId(null)}
            onChange={(overview, concluded) => {
              if (overview) market.setData(overview);
              else market.reload();
              if (concluded) myClub.reload();
            }}
          />
        </Modal>
      )}

      {data.negotiations.length > 0 && (
        <section className="section">
          <div className="section__head">
            <h2 className="eyebrow">Négociations · {data.negotiations.length}</h2>
            <span className="muted">En cours, et accords qui attendent l'intersaison</span>
          </div>
          <div className="card">
            <ul className="injury-list">
              {data.negotiations.map((negotiation) => (
                <li key={negotiation.id}>
                  <span className={`tag ${negotiation.stage === "agreed" ? "tag--injured" : "tag--fragile"}`}>
                    {DEALS[negotiation.kind].label}
                  </span>
                  <span style={{ fontWeight: 600 }}>{negotiation.player_name}</span>
                  <span className="muted">{negotiation.club_name}</span>
                  <span className="muted">{NEGOTIATION_STAGES[negotiation.stage]}</span>
                  {negotiation.stage !== "agreed" && (
                    <button type="button" className="button button--small" onClick={() => setTargetId(negotiation.player_id)}>
                      Reprendre
                    </button>
                  )}
                </li>
              ))}
            </ul>
          </div>
        </section>
      )}

      <section className="section">
        <div className="section__head">
          <h2 className="eyebrow">Marché · {listings.length} joueurs</h2>
          <span className="muted">Clique sur « Approcher » pour connaître les conditions</span>
        </div>

        <div className="chips" role="group" aria-label="Filtrer par voie">
          {WAYS.map((item) => (
            <button key={item.label} type="button" className="chip" aria-pressed={way === item.key} onClick={() => setWay(item.key)}>
              {item.label}
            </button>
          ))}
        </div>
        <div className="chips" role="group" aria-label="Filtrer par poste">
          <button type="button" className="chip" aria-pressed={position === null} onClick={() => setPosition(null)}>
            Tous
          </button>
          {Object.entries(POSITIONS).map(([key, info]) => (
            <button key={key} type="button" className="chip" aria-pressed={position === key} onClick={() => setPosition(key)}>
              {info.label}
            </button>
          ))}
        </div>

        <div className="card table-wrap">
          <table className="table">
            <thead>
              <tr>
                {listingHeader("player.name", "Joueur", "asc", true)}
                {listingHeader("club_name", "Club", "asc", true)}
                {listingHeader("player.age", "Âge", "asc")}
                {listingHeader("player.overall", "Note")}
                {listingHeader("player.value", "Valeur")}
                {listingHeader("player.wage", "Salaire")}
                {listingHeader("years_left", "Contrat", "asc")}
                {listingHeader("playing_time", "Statut", "asc", true)}
                <th scope="col" className="left">Voies</th>
                <th scope="col"></th>
              </tr>
            </thead>
            <tbody>
              {listings.map((listing) => {
                const { player } = listing;
                return (
                  <tr key={player.id} className={player.id === targetId ? "table__row--selected" : undefined}>
                    <td className="left">
                      <div style={{ fontWeight: 600 }}>{player.name}</div>
                      <div className="muted">{POSITIONS[player.position].label}</div>
                    </td>
                    <td className="left">
                      <div>{listing.club_name}</div>
                      <div className="muted">niveau {formatNote(listing.club_level)}</div>
                    </td>
                    <td className="muted">{player.age}</td>
                    <td className="note">{formatNote(player.overall)}</td>
                    <td>{formatMoney(player.value)}</td>
                    <td className="muted">{formatMoney(player.wage)}</td>
                    <td className={listing.precontract ? "cell--strong" : "muted"}>
                      {formatContractEnd(player.contract_until)}
                    </td>
                    <td className="left muted">{listing.playing_time}</td>
                    <td className="left">
                      <Ways listing={listing} />
                    </td>
                    <td>
                      <button type="button" className="button button--small" onClick={() => setTargetId(player.id)}>
                        Approcher
                      </button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
          <p className="table__note">
            Contrat : fin en juin de l'année indiquée, en gras quand il reste une saison (négociable sans
            indemnité). Statut : sa place dans son club. Salaires par saison.
          </p>
        </div>
      </section>

      <section className="section">
        <h2 className="eyebrow">Vendre · ton effectif</h2>
        <div className="card table-wrap">
          <table className="table">
            <thead>
              <tr>
                {squadHeader("name", "Joueur", "asc", true)}
                {squadHeader("age", "Âge", "asc")}
                {squadHeader("overall", "Note")}
                {squadHeader("wage", "Salaire")}
                {squadHeader("contract_until", "Contrat", "asc")}
                {squadHeader("value", "Valeur")}
                <th scope="col"></th>
              </tr>
            </thead>
            <tbody>
              {squadSort.rows.map((player) => (
                <tr key={player.id}>
                  <td className="left">
                    <div style={{ fontWeight: 600 }}>{player.name}</div>
                    <div className="muted">{POSITIONS[player.position].label}</div>
                  </td>
                  <td className="muted">{player.age}</td>
                  <td className="note">{formatNote(player.overall)}</td>
                  <td className="muted">{formatMoney(player.wage)}</td>
                  <td className="muted">
                    {player.loaned_from ? `Prêt · ${player.loaned_from_name}` : formatContractEnd(player.contract_until)}
                  </td>
                  <td style={{ fontWeight: 600 }}>{formatMoney(player.value)}</td>
                  <td>
                    <button
                      type="button"
                      className="button button--small"
                      disabled={squadAtMinimum || player.loaned_from !== null}
                      title={
                        player.loaned_from !== null
                          ? "Un joueur prêté ne se vend pas"
                          : squadAtMinimum
                            ? `Effectif minimum (${data.squad_min})`
                            : undefined
                      }
                      onClick={() => sell(player)}
                    >
                      Vendre
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="table__note">Un joueur se vend à sa valeur, à un club du championnat.</p>
        </div>
      </section>
    </>
  );
}

function Stat({ value, label }) {
  return (
    <div className="stat">
      <span className="big-num">{value}</span>
      <span className="muted">{label}</span>
    </div>
  );
}

// Les voies ouvertes pour un joueur du marché, en étiquettes.
function Ways({ listing }) {
  if (listing.talks_closed_until) {
    return <span className="tag tag--injured">Ne discute plus · jusqu'au {formatShortDate(listing.talks_closed_until)}</span>;
  }
  const ways = [];
  if (listing.precontract) ways.push(<span key="p" className="tag tag--severe">Pré-contrat</span>);
  if (listing.transfer_fee !== null) {
    ways.push(<span key="t" className="tag tag--moderate">Transfert · {formatMoney(listing.transfer_fee)}</span>);
  }
  if (listing.loanable) ways.push(<span key="l" className="tag tag--light">Prêt</span>);
  if (ways.length === 0) return <span className="muted">Intransférable</span>;
  return <span style={{ display: "inline-flex", flexWrap: "wrap", gap: 4 }}>{ways}</span>;
}

// Fenêtre par-dessus la page ; se ferme par le fond, la touche Échap ou le bouton.
function Modal({ children, onClose }) {
  useEffect(() => {
    const onKey = (event) => event.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);
  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal" role="dialog" aria-modal="true" onClick={(event) => event.stopPropagation()}>
        {children}
      </div>
    </div>
  );
}

// Approche d'un joueur : sa situation, choix de la voie, puis le fil de la négociation.
function Negotiation({ playerId, squadFull, onClose, onChange }) {
  const target = useApi(useCallback(() => api.approachPlayer(playerId), [playerId]));
  const [negotiation, setNegotiation] = useState(null);
  const [talk, setTalk] = useState([]); // fil : { who: "me" | "them", text, ok }
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);

  // La négociation déjà ouverte avec ce joueur, s'il y en a une.
  useEffect(() => {
    const existing = target.data?.negotiation ?? null;
    setNegotiation(existing);
    setTalk(existing ? [{ who: "them", text: existing.message, ok: false }] : []);
    setError(null);
  }, [target.data]);

  const say = (line) => setTalk((previous) => [...previous, line]);

  // Le fil montre toujours les derniers messages (on remonte pour voir les anciens).
  const talkRef = useRef(null);
  useEffect(() => {
    const list = talkRef.current;
    if (list) list.scrollTop = list.scrollHeight;
  }, [talk]);

  async function run(call, onDone) {
    setBusy(true);
    setError(null);
    try {
      onDone(await call());
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }

  const open = (kind) =>
    run(
      () => api.openNegotiation(playerId, kind),
      (opened) => {
        setNegotiation(opened);
        setTalk([{ who: "them", text: opened.message, ok: false }]);
        onChange(null, false);
      },
    );

  const offer = (payload, label) => {
    say({ who: "me", text: label });
    return run(
      () => api.makeOffer(negotiation.id, payload),
      (result) => {
        setNegotiation(result.negotiation);
        say({ who: "them", text: result.message, ok: result.accepted });
        onChange(result.overview, result.concluded);
      },
    );
  };

  const abandon = () =>
    run(
      () => api.abandonNegotiation(negotiation.id),
      (overview) => {
        setNegotiation(null);
        setTalk([]);
        onChange(overview, false);
      },
    );

  if (target.loading) return <p className="status">Approche…</p>;
  if (target.error) return <p className="status status--error">{target.error.message}</p>;

  const { player, club } = target.data;
  const [yearsMin, yearsMax] = target.data.preferred_years;
  const openStage = negotiation && (negotiation.stage === "club" || negotiation.stage === "player");

  return (
    <>
      <div className="section__head">
        <div>
          <h2 className="eyebrow">Approche</h2>
          <div className="header__name">{player.name}</div>
          <div className="muted">
            {POSITIONS[player.position].label} · {player.age} ans · note {formatNote(player.overall)} ·{" "}
            {club.name}
          </div>
        </div>
        <button type="button" className="button button--small" onClick={onClose}>
          Fermer
        </button>
      </div>

      <div className="situation">
        <Fact label="Salaire actuel" value={`${formatMoney(player.wage)} / saison`} />
        <Fact label="Contrat" value={`jusqu'en juin ${formatContractEnd(player.contract_until)} (${target.data.years_left} saison${target.data.years_left > 1 ? "s" : ""})`} />
        <Fact label="Dans son club" value={`${target.data.playing_time_now} · niveau ${formatNote(target.data.club_level)}`} />
        <Fact label="Chez toi" value={`${target.data.playing_time_here} · niveau ${formatNote(target.data.my_level)}`} />
        <Fact label="Il cherche" value={`un contrat de ${yearsMin} à ${yearsMax} saisons`} />
      </div>

      {error && <p className="status--error" style={{ margin: 0 }}>{error.message}</p>}

      {target.data.talks_closed_until && !negotiation && (
        <p className="negotiation__message" style={{ margin: 0 }}>
          Il ne veut plus discuter avec vous avant le {formatShortDate(target.data.talks_closed_until)}.
        </p>
      )}
      {target.data.grudges > 0 && !target.data.talks_closed_until && !negotiation && (
        <p className="negotiation__message" style={{ margin: 0 }}>
          Il n'a pas oublié vos {target.data.grudges > 1 ? `${target.data.grudges} ruptures passées` : "dernières discussions"} :
          il ouvrira plus haut et sera moins patient.
        </p>
      )}

      {!negotiation && (
        <div className="deal-options">
          {target.data.options.map((option) => (
            <button
              key={option.kind}
              type="button"
              className="protocol"
              disabled={busy || !option.available || (option.kind !== "precontract" && squadFull)}
              title={option.kind !== "precontract" && squadFull ? "Effectif complet" : undefined}
              onClick={() => open(option.kind)}
            >
              <span className="protocol__name">{DEALS[option.kind].label}</span>
              {option.fee_demand !== null && option.fee_demand !== undefined && (
                <span className="protocol__line">Le club en espère <strong>{formatMoney(option.fee_demand)}</strong></span>
              )}
              {option.wage_demand !== null && option.wage_demand !== undefined && (
                <span className="protocol__line">Il espère <strong>{formatMoney(option.wage_demand)}</strong> / saison</span>
              )}
              {option.kind === "loan" && option.available && (
                <span className="protocol__line">Salaire à ta charge : <strong>{formatMoney(option.wage)}</strong> / saison</span>
              )}
              <span className="protocol__line">{option.reason}</span>
            </button>
          ))}
        </div>
      )}

      {negotiation && (
        <>
          <div className="section__head" style={{ flexWrap: "wrap", gap: 12 }}>
            <span className="muted">
              <span className="tag tag--fragile">{DEALS[negotiation.kind].label}</span>{" "}
              {NEGOTIATION_STAGES[negotiation.stage]}
              {openStage && negotiation.rounds > 0 && ` · ${negotiation.rounds} refus`}
              {" · ouverte le "}
              {formatShortDate(negotiation.opened_on)}
            </span>
            {openStage && (
              <span className="patience muted">
                Patience
                <Level value={negotiation.patience} max={6} label={`patience ${negotiation.patience} sur 6`} />
              </span>
            )}
          </div>
          <ul className="talk" aria-live="polite" ref={talkRef}>
            {talk.map((line, index) => (
              <li key={index} className={line.who === "me" ? "talk--me" : line.ok ? "talk--ok" : undefined}>
                {line.text}
              </li>
            ))}
          </ul>
          {openStage && (
            <OfferForm
              key={negotiation.stage}
              negotiation={negotiation}
              player={player}
              years={[yearsMin, yearsMax]}
              busy={busy}
              onOffer={offer}
              onAbandon={abandon}
            />
          )}
          {!openStage && (
            <div>
              <button type="button" className="button" onClick={onClose}>Fermer</button>
            </div>
          )}
        </>
      )}
    </>
  );
}

function Fact({ label, value }) {
  return (
    <div className="stat">
      <span className="eyebrow">{label}</span>
      <span>{value}</span>
    </div>
  );
}

// Formulaire de l'étape en cours : indemnité (club), ou salaire et durée (joueur).
// Pré-rempli avec un point de départ raisonnable (valeur du joueur, salaire
// actuel), pas avec la demande : à toi de monter.
function OfferForm({ negotiation, player, years: [yearsMin, yearsMax], busy, onOffer, onAbandon }) {
  const clubStage = negotiation.stage === "club";
  const isLoan = negotiation.kind === "loan";
  const [fee, setFee] = useState(player.value);
  const [wage, setWage] = useState(player.wage);
  const [years, setYears] = useState(Math.min(yearsMax, Math.max(yearsMin, 2)));

  function submit(event) {
    event.preventDefault();
    if (clubStage) onOffer({ fee: Number(fee) }, `Tu proposes ${formatMoney(Number(fee))} d'indemnité.`);
    else if (isLoan) onOffer({}, "Tu confirmes le prêt.");
    else {
      const n = Number(years);
      onOffer(
        { wage: Number(wage), years: n },
        `Tu proposes ${formatMoney(Number(wage))} par saison sur ${n} saison${n > 1 ? "s" : ""}.`,
      );
    }
  }

  return (
    <form className="offer-form" onSubmit={submit}>
      {clubStage && (
        <div className="field">
          <label htmlFor="offer-fee">Indemnité proposée (€) · demande : {formatMoney(negotiation.fee_demand)}</label>
          <input id="offer-fee" className="input" type="number" min="0" step="5000" value={fee} onChange={(e) => setFee(e.target.value)} />
        </div>
      )}
      {!clubStage && !isLoan && (
        <>
          <div className="field">
            <label htmlFor="offer-wage">Salaire (€ / saison) · demande : {formatMoney(negotiation.wage_demand)}</label>
            <input id="offer-wage" className="input" type="number" min="0" step="1000" value={wage} onChange={(e) => setWage(e.target.value)} />
          </div>
          <div className="field">
            <label htmlFor="offer-years">Durée (saisons)</label>
            <select id="offer-years" className="input" value={years} onChange={(e) => setYears(e.target.value)}>
              {[1, 2, 3, 4, 5].map((n) => (
                <option key={n} value={n}>{n}</option>
              ))}
            </select>
          </div>
        </>
      )}
      <button type="submit" className="button button--primary" disabled={busy}>
        {isLoan ? `Confirmer le prêt (${formatMoney(negotiation.wage_demand)} / saison)` : "Faire l'offre"}
      </button>
      <button type="button" className="button" disabled={busy} onClick={onAbandon}>
        Quitter la table
      </button>
      {!isLoan && (
        <span className="muted">
          Monte à chaque offre : une offre qui ne bouge pas l'agace, une offre dérisoire l'insulte. Proche de sa
          demande, il peut faire un dernier effort. À bout de patience, il ne discute plus.
        </span>
      )}
    </form>
  );
}
