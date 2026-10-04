import { useCallback, useState } from "react";
import { useOutletContext } from "react-router-dom";

import { api } from "../api.js";
import { POSITIONS, formatMoney, formatNote } from "../format.js";
import { useApi } from "../hooks/useApi.js";

// Marché des transferts : acheter chez les autres clubs, vendre ses joueurs.
export default function Transfers() {
  const { career } = useOutletContext();
  const market = useApi(useCallback(api.getTransfers, []));
  const myClub = useApi(useCallback(() => api.getClub(career.club_id), [career.club_id]));

  const [position, setPosition] = useState(null); // null = tous les postes
  const [affordableOnly, setAffordableOnly] = useState(false);
  const [actionError, setActionError] = useState(null);

  async function act(call) {
    setActionError(null);
    try {
      market.setData(await call());
      myClub.reload(); // l'effectif a changé
    } catch (err) {
      setActionError(err);
    }
  }

  function buy(listing) {
    const { player } = listing;
    const message = `Acheter ${player.name} (${listing.club_name}) pour ${formatMoney(listing.asking_price)} ? Salaire : ${formatMoney(player.wage)} par saison.`;
    if (window.confirm(message)) act(() => api.buyPlayer(player.id));
  }

  function sell(player) {
    if (window.confirm(`Vendre ${player.name} pour ${formatMoney(player.value)} ?`)) {
      act(() => api.sellPlayer(player.id));
    }
  }

  if (market.loading || myClub.loading) return <p className="status">Chargement…</p>;
  if (market.error) return <p className="status status--error">{market.error.message}</p>;
  if (myClub.error) return <p className="status status--error">{myClub.error.message}</p>;

  const data = market.data;
  const squadFull = data.squad_size >= data.squad_max;
  const squadAtMinimum = data.squad_size <= data.squad_min;
  const listings = data.listings.filter(
    (listing) =>
      (position === null || listing.player.position === position) &&
      (!affordableOnly || listing.affordable),
  );
  const myPlayers = [...myClub.data.players].sort((a, b) => b.value - a.value);

  return (
    <>
      <header className="page-head">
        <h1 className="title">Transferts</h1>
        <div className="page-head__stats">
          <div className="stat">
            <span className="big-num">{formatMoney(data.balance)}</span>
            <span className="muted">trésorerie</span>
          </div>
          <div className="stat">
            <span className="big-num">{data.squad_size}</span>
            <span className="muted">joueurs (de {data.squad_min} à {data.squad_max})</span>
          </div>
        </div>
      </header>

      {actionError && <p className="status--error">{actionError.message}</p>}

      <section className="section">
        <div className="section__head">
          <h2 className="eyebrow">Acheter · {listings.length} joueurs</h2>
          <label className="muted" style={{ display: "flex", gap: 8, alignItems: "center" }}>
            <input type="checkbox" checked={affordableOnly} onChange={(e) => setAffordableOnly(e.target.checked)} />
            Seulement ce que je peux payer
          </label>
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
                <th scope="col" className="left">Joueur</th>
                <th scope="col" className="left">Club</th>
                <th scope="col">Âge</th>
                <th scope="col">Note</th>
                <th scope="col">Valeur</th>
                <th scope="col">Salaire</th>
                <th scope="col">Prix demandé</th>
                <th scope="col"></th>
              </tr>
            </thead>
            <tbody>
              {listings.map((listing) => {
                const { player } = listing;
                const blocked = !listing.affordable || squadFull;
                return (
                  <tr key={player.id}>
                    <td className="left">
                      <div style={{ fontWeight: 600 }}>{player.name}</div>
                      <div className="muted">{POSITIONS[player.position].label}</div>
                    </td>
                    <td className="left muted">{listing.club_name}</td>
                    <td className="muted">{player.age}</td>
                    <td className="note">{formatNote(player.overall)}</td>
                    <td>{formatMoney(player.value)}</td>
                    <td className="muted">{formatMoney(player.wage)}</td>
                    <td style={{ fontWeight: 600 }}>{formatMoney(listing.asking_price)}</td>
                    <td>
                      <button
                        type="button"
                        className="button button--small button--primary"
                        disabled={blocked}
                        title={squadFull ? "Effectif complet" : !listing.affordable ? "Trésorerie insuffisante" : undefined}
                        onClick={() => buy(listing)}
                      >
                        Acheter
                      </button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
          <p className="table__note">Les clubs vendent 25 % au-dessus de la valeur du joueur. Salaires par saison.</p>
        </div>
      </section>

      <section className="section">
        <h2 className="eyebrow">Vendre · ton effectif</h2>
        <div className="card table-wrap">
          <table className="table">
            <thead>
              <tr>
                <th scope="col" className="left">Joueur</th>
                <th scope="col">Âge</th>
                <th scope="col">Note</th>
                <th scope="col">Salaire</th>
                <th scope="col">Valeur</th>
                <th scope="col"></th>
              </tr>
            </thead>
            <tbody>
              {myPlayers.map((player) => (
                <tr key={player.id}>
                  <td className="left">
                    <div style={{ fontWeight: 600 }}>{player.name}</div>
                    <div className="muted">{POSITIONS[player.position].label}</div>
                  </td>
                  <td className="muted">{player.age}</td>
                  <td className="note">{formatNote(player.overall)}</td>
                  <td className="muted">{formatMoney(player.wage)}</td>
                  <td style={{ fontWeight: 600 }}>{formatMoney(player.value)}</td>
                  <td>
                    <button
                      type="button"
                      className="button button--small"
                      disabled={squadAtMinimum}
                      title={squadAtMinimum ? `Effectif minimum (${data.squad_min})` : undefined}
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
